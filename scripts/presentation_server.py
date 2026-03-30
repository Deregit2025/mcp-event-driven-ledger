"""
scripts/presentation_server.py
================================
Lightweight HTTP server for the Apex Ledger presentation dashboard.
Uses psycopg2 (synchronous) to avoid asyncio event loop issues.

Run:
    pip install psycopg2-binary
    python scripts/presentation_server.py

Endpoints:
    GET /health
    GET /audit-trail?app_id=APEX-TEST-01
    GET /compliance?app_id=APEX-TEST-01
    GET /compliance/temporal?app_id=APEX-TEST-01&as_of=2026-03-25T10:00:00Z
    GET /upcasting?app_id=APEX-TEST-01
    GET /stats
"""
import json
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DB_DSN = "postgresql://ledger:ledger@localhost:5432/apex_ledger"


def get_conn():
    return psycopg2.connect(DB_DSN, cursor_factory=psycopg2.extras.RealDictCursor)


# ── DB QUERIES ────────────────────────────────────────────────────────────────

def get_audit_trail(app_id: str) -> dict:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT stream_id, stream_position, global_position,
                   event_type, event_version, payload, recorded_at
            FROM events
            WHERE stream_id IN (%s, %s, %s, %s, %s)
            ORDER BY recorded_at ASC, global_position ASC
        """, (
            f"loan-{app_id}", f"credit-{app_id}",
            f"fraud-{app_id}", f"compliance-{app_id}",
            f"audit-loan-{app_id}",
        ))
        rows = cur.fetchall()
        events = []
        for r in rows:
            p = r["payload"]
            p = p if isinstance(p, dict) else json.loads(p)
            events.append({
                "stream_id": r["stream_id"],
                "stream_position": r["stream_position"],
                "global_position": r["global_position"],
                "event_type": r["event_type"],
                "event_version": r["event_version"],
                "payload": p,
                "recorded_at": str(r["recorded_at"]),
            })
        return {"application_id": app_id, "total_events": len(events), "events": events}
    finally:
        conn.close()


def get_compliance(app_id: str) -> dict:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT event_type, payload, recorded_at
            FROM events WHERE stream_id = %s
            ORDER BY stream_position ASC
        """, (f"compliance-{app_id}",))
        rows = cur.fetchall()
        events = []
        summary = {"rules_evaluated": 0, "rules_passed": 0, "rules_failed": 0,
                   "rules_noted": 0, "has_hard_block": False, "overall_verdict": None, "completed_at": None}
        for r in rows:
            p = r["payload"]
            p = p if isinstance(p, dict) else json.loads(p)
            et = r["event_type"]
            if et == "ComplianceRulePassed":
                summary["rules_evaluated"] += 1; summary["rules_passed"] += 1
            elif et == "ComplianceRuleFailed":
                summary["rules_evaluated"] += 1; summary["rules_failed"] += 1
                if p.get("is_hard_block"): summary["has_hard_block"] = True
            elif et == "ComplianceRuleNoted":
                summary["rules_evaluated"] += 1; summary["rules_noted"] += 1
            elif et == "ComplianceCheckCompleted":
                summary["overall_verdict"] = p.get("overall_verdict")
                summary["has_hard_block"] = p.get("has_hard_block", False)
                summary["rules_evaluated"] = p.get("rules_evaluated", summary["rules_evaluated"])
                summary["rules_passed"] = p.get("rules_passed", summary["rules_passed"])
                summary["rules_failed"] = p.get("rules_failed", summary["rules_failed"])
                summary["completed_at"] = str(r["recorded_at"])
            events.append({"event_type": et, "payload": p, "recorded_at": str(r["recorded_at"])})
        return {"application_id": app_id, "summary": summary, "events": events}
    finally:
        conn.close()


def get_compliance_temporal(app_id: str, as_of: str) -> dict:
    conn = get_conn()
    try:
        try:
            as_of_dt = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        except Exception:
            return {"error": "invalid_timestamp", "as_of": as_of}
        cur = conn.cursor()
        cur.execute("""
            SELECT event_type, payload, recorded_at
            FROM events WHERE stream_id = %s AND recorded_at <= %s
            ORDER BY stream_position ASC
        """, (f"compliance-{app_id}", as_of_dt))
        rows = cur.fetchall()
        if not rows:
            return {"application_id": app_id, "as_of": as_of,
                    "status": "no_events_before_timestamp", "overall_verdict": "PENDING",
                    "rules_evaluated": 0, "message": "No compliance events existed at this timestamp"}
        summary = {"rules_evaluated": 0, "rules_passed": 0, "rules_failed": 0,
                   "overall_verdict": "IN_PROGRESS", "has_hard_block": False}
        for r in rows:
            p = r["payload"]
            p = p if isinstance(p, dict) else json.loads(p)
            et = r["event_type"]
            if et == "ComplianceRulePassed":
                summary["rules_evaluated"] += 1; summary["rules_passed"] += 1
            elif et == "ComplianceRuleFailed":
                summary["rules_evaluated"] += 1; summary["rules_failed"] += 1
            elif et == "ComplianceCheckCompleted":
                summary["overall_verdict"] = p.get("overall_verdict", "CLEAR")
                summary["rules_evaluated"] = p.get("rules_evaluated", summary["rules_evaluated"])
                summary["rules_passed"] = p.get("rules_passed", summary["rules_passed"])
        return {"application_id": app_id, "as_of": as_of, "temporal_query": True, **summary}
    finally:
        conn.close()


def get_upcasting(app_id: str) -> dict:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT event_id, event_type, event_version, payload, recorded_at
            FROM events WHERE event_type = 'CreditAnalysisCompleted'
            AND stream_id = %s ORDER BY global_position ASC LIMIT 1
        """, (f"credit-{app_id}",))
        row = cur.fetchone()
        if not row:
            return {"error": "no_credit_event_found", "app_id": app_id}
        raw = row["payload"]
        raw = raw if isinstance(raw, dict) else json.loads(raw)
        upcasted = dict(raw)
        stored_version = row["event_version"]
        loaded_version = stored_version
        if stored_version == 1:
            loaded_version = 2
            upcasted["model_versions"] = {"credit_analysis": raw.get("model_version", "legacy-pre-2026")}
            upcasted["confidence_score"] = None
            upcasted["regulatory_basis"] = ["APRA-2024-inferred"]
        return {"event_id": str(row["event_id"]), "stream_id": f"credit-{app_id}",
                "stored_version": stored_version, "loaded_version": loaded_version,
                "stored_payload": raw, "loaded_payload": upcasted,
                "immutability_proof": {"db_row_unchanged": True},
                "recorded_at": str(row["recorded_at"])}
    finally:
        conn.close()


def get_stats() -> dict:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM events")
        total = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) as cnt FROM event_streams")
        streams = cur.fetchone()["cnt"]
        cur.execute("SELECT event_type, COUNT(*) as cnt FROM events GROUP BY event_type ORDER BY cnt DESC LIMIT 10")
        event_types = [{"type": r["event_type"], "count": r["cnt"]} for r in cur.fetchall()]
        cur.execute("SELECT stream_id, event_type, recorded_at FROM events ORDER BY global_position DESC LIMIT 5")
        recent = [{"stream_id": r["stream_id"], "event_type": r["event_type"], "recorded_at": str(r["recorded_at"])} for r in cur.fetchall()]
        return {"total_events": total, "total_streams": streams,
                "top_event_types": event_types, "recent_events": recent,
                "status": "healthy", "checked_at": datetime.now(timezone.utc).isoformat()}
    finally:
        conn.close()


async def get_compliance(app_id: str) -> dict:
    conn = await asyncpg.connect(DB_URL)
    try:
        rows = await conn.fetch("""
            SELECT event_type, event_version, payload, recorded_at
            FROM events
            WHERE stream_id = $1
            ORDER BY stream_position ASC
        """, f"compliance-{app_id}")
        events = []
        summary = {
            "rules_evaluated": 0, "rules_passed": 0,
            "rules_failed": 0, "rules_noted": 0,
            "has_hard_block": False, "overall_verdict": None,
            "completed_at": None,
        }
        for r in rows:
            p = r["payload"]
            p = p if isinstance(p, dict) else json.loads(p)
            et = r["event_type"]
            if et == "ComplianceRulePassed":
                summary["rules_evaluated"] += 1
                summary["rules_passed"] += 1
            elif et == "ComplianceRuleFailed":
                summary["rules_evaluated"] += 1
                summary["rules_failed"] += 1
                if p.get("is_hard_block"):
                    summary["has_hard_block"] = True
            elif et == "ComplianceRuleNoted":
                summary["rules_evaluated"] += 1
                summary["rules_noted"] += 1
            elif et == "ComplianceCheckCompleted":
                summary["overall_verdict"] = p.get("overall_verdict")
                summary["has_hard_block"] = p.get("has_hard_block", False)
                summary["rules_evaluated"] = p.get("rules_evaluated", summary["rules_evaluated"])
                summary["rules_passed"] = p.get("rules_passed", summary["rules_passed"])
                summary["rules_failed"] = p.get("rules_failed", summary["rules_failed"])
                summary["completed_at"] = str(r["recorded_at"])
            events.append({"event_type": et, "payload": p, "recorded_at": str(r["recorded_at"])})
        return {"application_id": app_id, "summary": summary, "events": events}
    finally:
        await conn.close()


async def get_compliance_temporal(app_id: str, as_of: str) -> dict:
    conn = await asyncpg.connect(DB_URL)
    try:
        try:
            as_of_dt = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        except Exception:
            return {"error": "invalid_timestamp", "as_of": as_of}
        rows = await conn.fetch("""
            SELECT event_type, payload, recorded_at
            FROM events
            WHERE stream_id = $1 AND recorded_at <= $2
            ORDER BY stream_position ASC
        """, f"compliance-{app_id}", as_of_dt)
        if not rows:
            return {"application_id": app_id, "as_of": as_of, "status": "no_events_before_timestamp", "overall_verdict": "PENDING", "rules_evaluated": 0, "message": "No compliance events existed at this timestamp"}
        summary = {"rules_evaluated": 0, "rules_passed": 0, "rules_failed": 0, "overall_verdict": "IN_PROGRESS", "has_hard_block": False}
        for r in rows:
            p = r["payload"]
            p = p if isinstance(p, dict) else json.loads(p)
            et = r["event_type"]
            if et == "ComplianceRulePassed":
                summary["rules_evaluated"] += 1; summary["rules_passed"] += 1
            elif et == "ComplianceRuleFailed":
                summary["rules_evaluated"] += 1; summary["rules_failed"] += 1
            elif et == "ComplianceCheckCompleted":
                summary["overall_verdict"] = p.get("overall_verdict", "CLEAR")
                summary["rules_evaluated"] = p.get("rules_evaluated", summary["rules_evaluated"])
                summary["rules_passed"] = p.get("rules_passed", summary["rules_passed"])
        return {"application_id": app_id, "as_of": as_of, "temporal_query": True, **summary}
    finally:
        await conn.close()


async def get_upcasting(app_id: str) -> dict:
    conn = await asyncpg.connect(DB_URL)
    try:
        row = await conn.fetchrow("""
            SELECT event_id, event_type, event_version, payload, recorded_at
            FROM events
            WHERE event_type = 'CreditAnalysisCompleted'
              AND stream_id = $1
            ORDER BY global_position ASC LIMIT 1
        """, f"credit-{app_id}")
        if not row:
            return {"error": "no_credit_event_found", "app_id": app_id}
        raw = row["payload"]
        raw = raw if isinstance(raw, dict) else json.loads(raw)
        upcasted = dict(raw)
        stored_version = row["event_version"]
        loaded_version = stored_version
        if stored_version == 1:
            loaded_version = 2
            mv = raw.get("model_version", "legacy-pre-2026")
            upcasted["model_versions"] = {"credit_analysis": mv}
            upcasted["confidence_score"] = None
            upcasted["regulatory_basis"] = ["APRA-2024-inferred"]
        return {"event_id": str(row["event_id"]), "stream_id": f"credit-{app_id}", "stored_version": stored_version, "loaded_version": loaded_version, "stored_payload": raw, "loaded_payload": upcasted, "immutability_proof": {"stored_has_model_versions": "model_versions" in raw, "loaded_has_model_versions": "model_versions" in upcasted, "db_row_unchanged": True}, "recorded_at": str(row["recorded_at"])}
    finally:
        await conn.close()


async def get_stats() -> dict:
    conn = await asyncpg.connect(DB_URL)
    try:
        total = await conn.fetchval("SELECT COUNT(*) FROM events")
        streams = await conn.fetchval("SELECT COUNT(*) FROM event_streams")
        event_types = await conn.fetch("SELECT event_type, COUNT(*) as cnt FROM events GROUP BY event_type ORDER BY cnt DESC LIMIT 10")
        recent = await conn.fetch("SELECT stream_id, event_type, recorded_at FROM events ORDER BY global_position DESC LIMIT 5")
        return {"total_events": total, "total_streams": streams, "top_event_types": [{"type": r["event_type"], "count": r["cnt"]} for r in event_types], "recent_events": [{"stream_id": r["stream_id"], "event_type": r["event_type"], "recorded_at": str(r["recorded_at"])} for r in recent], "status": "healthy", "checked_at": datetime.now(timezone.utc).isoformat()}
    finally:
        await conn.close()


# ── HTTP SERVER ───────────────────────────────────────────────────────────────

def run_async(coro):
    pass  # no longer needed


class Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # suppress default logging

    def send_json(self, data, status=200):
        body = json.dumps(data, default=str, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        app_id = qs.get("app_id", ["APEX-TEST-01"])[0]
        path = parsed.path

        try:
            if path == "/health":
                self.send_json({"status": "ok", "server": "apex-ledger-presentation"})
            elif path == "/stats":
                self.send_json(get_stats())
            elif path == "/audit-trail":
                self.send_json(get_audit_trail(app_id))
            elif path == "/compliance":
                self.send_json(get_compliance(app_id))
            elif path == "/compliance/temporal":
                as_of = qs.get("as_of", [""])[0]
                self.send_json(get_compliance_temporal(app_id, as_of))
            elif path == "/upcasting":
                self.send_json(get_upcasting(app_id))
            else:
                self.send_json({"error": "not_found"}, 404)

        except Exception as e:
            self.send_json({"error": str(e)}, 500)


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  Apex Ledger — Presentation Server")
    print("=" * 55)
    try:
        conn = get_conn()
        conn.close()
        print(f"✅ Connected to PostgreSQL")
    except Exception as e:
        print(f"❌ DB connection failed: {e}")
        return
    server = HTTPServer(("0.0.0.0", 8765), Handler)
    print(f"✅ Server running at http://127.0.0.1:8765")
    print(f"   Open scripts/presentation.html in your browser")
    print(f"   Press Ctrl+C to stop")
    print("=" * 55)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()