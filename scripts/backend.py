"""
scripts/backend.py
===================
FastAPI backend for Apex Ledger Dashboard.
Run: uvicorn scripts.backend:app --reload --port 8000
"""
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
import json
from datetime import datetime, timezone
from typing import Optional

app = FastAPI(title="Apex Ledger API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_DSN = "postgresql://ledger:ledger@localhost:5432/apex_ledger"


def db():
    return psycopg2.connect(DB_DSN, cursor_factory=psycopg2.extras.RealDictCursor)


def parse_payload(p):
    return p if isinstance(p, dict) else json.loads(p)


# ── HEALTH ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    try:
        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM events")
        cnt = cur.fetchone()["cnt"]
        conn.close()
        return {"status": "healthy", "total_events": cnt,
                "checked_at": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


# ── OVERVIEW / STATS ──────────────────────────────────────────────────────────

@app.get("/stats")
def stats():
    conn = db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) as cnt FROM events")
    total_events = cur.fetchone()["cnt"]

    cur.execute("SELECT COUNT(*) as cnt FROM event_streams")
    total_streams = cur.fetchone()["cnt"]

    cur.execute("SELECT COUNT(*) as cnt FROM event_streams WHERE archived_at IS NOT NULL")
    archived = cur.fetchone()["cnt"]

    cur.execute("""
        SELECT event_type, COUNT(*) as cnt
        FROM events GROUP BY event_type ORDER BY cnt DESC LIMIT 10
    """)
    top_types = [{"type": r["event_type"], "count": r["cnt"]} for r in cur.fetchall()]

    cur.execute("""
        SELECT stream_id, event_type, recorded_at
        FROM events ORDER BY global_position DESC LIMIT 10
    """)
    recent = [{"stream_id": r["stream_id"], "event_type": r["event_type"],
               "recorded_at": str(r["recorded_at"])} for r in cur.fetchall()]

    cur.execute("""
        SELECT DATE_TRUNC('hour', recorded_at) as hour, COUNT(*) as cnt
        FROM events
        WHERE recorded_at > NOW() - INTERVAL '24 hours'
        GROUP BY hour ORDER BY hour ASC
    """)
    timeline = [{"hour": str(r["hour"]), "count": r["cnt"]} for r in cur.fetchall()]

    cur.execute("""
        SELECT
            SUM(CASE WHEN event_type = 'ApplicationApproved' THEN 1 ELSE 0 END) as approved,
            SUM(CASE WHEN event_type = 'ApplicationDeclined' THEN 1 ELSE 0 END) as declined,
            SUM(CASE WHEN event_type = 'DecisionGenerated' THEN 1 ELSE 0 END) as decisions
        FROM events
    """)
    row = cur.fetchone()
    decisions = {"approved": row["approved"] or 0, "declined": row["declined"] or 0,
                 "decisions": row["decisions"] or 0}

    conn.close()
    return {
        "total_events": total_events,
        "total_streams": total_streams,
        "archived_streams": archived,
        "top_event_types": top_types,
        "recent_events": recent,
        "event_timeline": timeline,
        "decisions": decisions,
    }


# ── APPLICATIONS ──────────────────────────────────────────────────────────────

@app.get("/applications")
def list_applications():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT
            REGEXP_REPLACE(stream_id, '^loan-', '') as app_id,
            MIN(recorded_at) as created_at,
            MAX(recorded_at) as last_event_at,
            COUNT(*) as event_count
        FROM events
        WHERE stream_id LIKE 'loan-%'
        GROUP BY stream_id
        ORDER BY created_at DESC
        LIMIT 50
    """)
    apps = [{"app_id": r["app_id"], "created_at": str(r["created_at"]),
             "last_event_at": str(r["last_event_at"]),
             "event_count": r["event_count"]} for r in cur.fetchall()]
    conn.close()
    return {"applications": apps, "total": len(apps)}


@app.get("/applications/{app_id}")
def get_application(app_id: str):
    conn = db()
    cur = conn.cursor()

    # Get loan stream events
    cur.execute("""
        SELECT event_type, payload, recorded_at, stream_position
        FROM events WHERE stream_id = %s
        ORDER BY stream_position ASC
    """, (f"loan-{app_id}",))
    loan_events = cur.fetchall()

    if not loan_events:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Application {app_id} not found")

    state = "SUBMITTED"
    applicant_id = None
    requested_amount = None
    approved_amount = None
    final_decision = None

    for r in loan_events:
        p = parse_payload(r["payload"])
        et = r["event_type"]
        if et == "ApplicationSubmitted":
            applicant_id = p.get("applicant_id")
            requested_amount = p.get("requested_amount_usd")
            state = "SUBMITTED"
        elif et == "ApplicationApproved":
            approved_amount = p.get("approved_amount_usd")
            final_decision = "APPROVED"
            state = "APPROVED"
        elif et == "ApplicationDeclined":
            final_decision = "DECLINED"
            state = "DECLINED"
        elif et == "DecisionGenerated":
            state = "PENDING_HUMAN_REVIEW"

    conn.close()
    return {
        "app_id": app_id,
        "state": state,
        "applicant_id": applicant_id,
        "requested_amount_usd": requested_amount,
        "approved_amount_usd": approved_amount,
        "final_decision": final_decision,
        "event_count": len(loan_events),
    }


# ── AUDIT TRAIL ───────────────────────────────────────────────────────────────

@app.get("/audit-trail/{app_id}")
def audit_trail(app_id: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT stream_id, stream_position, global_position,
               event_type, event_version, payload, metadata, recorded_at
        FROM events
        WHERE stream_id IN (%s,%s,%s,%s,%s)
        ORDER BY recorded_at ASC, global_position ASC
    """, (f"loan-{app_id}", f"credit-{app_id}", f"fraud-{app_id}",
          f"compliance-{app_id}", f"audit-loan-{app_id}"))
    rows = cur.fetchall()
    conn.close()
    events = []
    for r in rows:
        p = parse_payload(r["payload"])
        m = parse_payload(r["metadata"]) if r["metadata"] else {}
        events.append({
            "stream_id": r["stream_id"],
            "stream_position": r["stream_position"],
            "global_position": r["global_position"],
            "event_type": r["event_type"],
            "event_version": r["event_version"],
            "payload": p,
            "metadata": m,
            "recorded_at": str(r["recorded_at"]),
            "causation_id": m.get("causation_id"),
            "correlation_id": m.get("correlation_id"),
        })
    return {
        "application_id": app_id,
        "total_events": len(events),
        "streams_covered": list(set(e["stream_id"] for e in events)),
        "events": events,
    }


# ── COMPLIANCE ────────────────────────────────────────────────────────────────

@app.get("/compliance/{app_id}")
def compliance(app_id: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT event_type, payload, recorded_at
        FROM events WHERE stream_id = %s
        ORDER BY stream_position ASC
    """, (f"compliance-{app_id}",))
    rows = cur.fetchall()
    conn.close()
    events = []
    s = {"rules_evaluated": 0, "rules_passed": 0, "rules_failed": 0,
         "rules_noted": 0, "has_hard_block": False,
         "overall_verdict": None, "completed_at": None}
    for r in rows:
        p = parse_payload(r["payload"])
        et = r["event_type"]
        if et == "ComplianceRulePassed":
            s["rules_evaluated"] += 1; s["rules_passed"] += 1
        elif et == "ComplianceRuleFailed":
            s["rules_evaluated"] += 1; s["rules_failed"] += 1
            if p.get("is_hard_block"): s["has_hard_block"] = True
        elif et == "ComplianceRuleNoted":
            s["rules_evaluated"] += 1; s["rules_noted"] += 1
        elif et == "ComplianceCheckCompleted":
            s["overall_verdict"] = p.get("overall_verdict")
            s["has_hard_block"] = p.get("has_hard_block", False)
            s["rules_evaluated"] = p.get("rules_evaluated", s["rules_evaluated"])
            s["rules_passed"] = p.get("rules_passed", s["rules_passed"])
            s["rules_failed"] = p.get("rules_failed", s["rules_failed"])
            s["completed_at"] = str(r["recorded_at"])
        events.append({"event_type": et, "payload": p,
                       "recorded_at": str(r["recorded_at"])})
    return {"application_id": app_id, "summary": s, "events": events}


@app.get("/compliance/{app_id}/temporal")
def compliance_temporal(app_id: str, as_of: str = Query(...)):
    try:
        as_of_dt = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid timestamp format")
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT event_type, payload, recorded_at
        FROM events WHERE stream_id = %s AND recorded_at <= %s
        ORDER BY stream_position ASC
    """, (f"compliance-{app_id}", as_of_dt))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        return {"application_id": app_id, "as_of": as_of,
                "overall_verdict": "PENDING", "rules_evaluated": 0,
                "rules_passed": 0, "has_hard_block": False,
                "message": "No compliance events existed at this timestamp"}
    s = {"rules_evaluated": 0, "rules_passed": 0, "rules_failed": 0,
         "overall_verdict": "IN_PROGRESS", "has_hard_block": False}
    for r in rows:
        p = parse_payload(r["payload"])
        et = r["event_type"]
        if et == "ComplianceRulePassed":
            s["rules_evaluated"] += 1; s["rules_passed"] += 1
        elif et == "ComplianceRuleFailed":
            s["rules_evaluated"] += 1; s["rules_failed"] += 1
        elif et == "ComplianceCheckCompleted":
            s["overall_verdict"] = p.get("overall_verdict", "CLEAR")
            s["rules_evaluated"] = p.get("rules_evaluated", s["rules_evaluated"])
            s["rules_passed"] = p.get("rules_passed", s["rules_passed"])
    return {"application_id": app_id, "as_of": as_of, "temporal_query": True, **s}


# ── PROJECTIONS ───────────────────────────────────────────────────────────────

@app.get("/projections")
def projections():
    conn = db()
    cur = conn.cursor()

    # Application summary
    try:
        cur.execute("SELECT COUNT(*) as cnt FROM application_summary")
        app_summary_count = cur.fetchone()["cnt"]
        cur.execute("SELECT * FROM application_summary ORDER BY updated_at DESC LIMIT 10")
        app_summary = [dict(r) for r in cur.fetchall()]
    except Exception:
        app_summary_count = 0
        app_summary = []

    # Agent performance
    try:
        cur.execute("SELECT * FROM agent_performance_ledger ORDER BY total_sessions DESC")
        agent_perf = [dict(r) for r in cur.fetchall()]
    except Exception:
        agent_perf = []

    # Compliance audit view
    try:
        cur.execute("SELECT COUNT(*) as cnt FROM compliance_audit_view")
        compliance_count = cur.fetchone()["cnt"]
    except Exception:
        compliance_count = 0

    # Projection checkpoints
    try:
        cur.execute("SELECT * FROM projection_checkpoints")
        checkpoints = [dict(r) for r in cur.fetchall()]
    except Exception:
        checkpoints = []

    conn.close()
    return {
        "application_summary": {
            "count": app_summary_count,
            "rows": app_summary,
            "slo_ms": 500,
        },
        "agent_performance_ledger": {
            "rows": agent_perf,
            "slo_ms": 500,
        },
        "compliance_audit_view": {
            "count": compliance_count,
            "slo_ms": 2000,
        },
        "checkpoints": checkpoints,
    }


# ── UPCASTING ─────────────────────────────────────────────────────────────────

@app.get("/upcasting/{app_id}")
def upcasting(app_id: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT event_id, event_type, event_version, payload, recorded_at
        FROM events WHERE event_type = 'CreditAnalysisCompleted'
        AND stream_id = %s ORDER BY global_position ASC LIMIT 1
    """, (f"credit-{app_id}",))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No CreditAnalysisCompleted found")
    raw = parse_payload(row["payload"])
    upcasted = dict(raw)
    sv = row["event_version"]
    lv = sv
    if sv == 1:
        lv = 2
        upcasted["model_versions"] = {"credit_analysis": raw.get("model_version", "legacy-pre-2026")}
        upcasted["confidence_score"] = None
        upcasted["regulatory_basis"] = ["APRA-2024-inferred"]
    return {
        "event_id": str(row["event_id"]),
        "stream_id": f"credit-{app_id}",
        "stored_version": sv,
        "loaded_version": lv,
        "stored_payload": raw,
        "loaded_payload": upcasted,
        "stored_has_model_versions": "model_versions" in raw,
        "loaded_has_model_versions": "model_versions" in upcasted,
        "db_row_unchanged": True,
        "recorded_at": str(row["recorded_at"]),
    }


# ── EVENTS ────────────────────────────────────────────────────────────────────

@app.get("/events")
def events(
    stream_id: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    conn = db()
    cur = conn.cursor()
    where = []
    params = []
    if stream_id:
        where.append("stream_id = %s"); params.append(stream_id)
    if event_type:
        where.append("event_type = %s"); params.append(event_type)
    where_clause = "WHERE " + " AND ".join(where) if where else ""
    cur.execute(f"""
        SELECT stream_id, stream_position, global_position,
               event_type, event_version, payload, recorded_at
        FROM events {where_clause}
        ORDER BY global_position DESC
        LIMIT %s OFFSET %s
    """, params + [limit, offset])
    rows = cur.fetchall()
    cur.execute(f"SELECT COUNT(*) as cnt FROM events {where_clause}", params)
    total = cur.fetchone()["cnt"]
    conn.close()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": [{"stream_id": r["stream_id"], "stream_position": r["stream_position"],
                    "global_position": r["global_position"], "event_type": r["event_type"],
                    "event_version": r["event_version"],
                    "payload": parse_payload(r["payload"]),
                    "recorded_at": str(r["recorded_at"])} for r in rows],
    }


# ── STREAMS ───────────────────────────────────────────────────────────────────

@app.get("/streams")
def streams(limit: int = 50):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT stream_id, aggregate_type, current_version,
               created_at, archived_at
        FROM event_streams
        ORDER BY created_at DESC LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return {"streams": [{"stream_id": r["stream_id"], "aggregate_type": r["aggregate_type"],
                          "current_version": r["current_version"],
                          "created_at": str(r["created_at"]),
                          "archived_at": str(r["archived_at"]) if r["archived_at"] else None,
                          "is_archived": r["archived_at"] is not None} for r in rows]}


# ── INTEGRITY ─────────────────────────────────────────────────────────────────

@app.get("/integrity/{app_id}")
def integrity(app_id: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT event_type, payload, recorded_at
        FROM events WHERE stream_id = %s
        ORDER BY stream_position ASC
    """, (f"audit-loan-{app_id}",))
    rows = cur.fetchall()
    conn.close()
    checks = []
    for r in rows:
        if r["event_type"] == "AuditIntegrityCheckRun":
            p = parse_payload(r["payload"])
            checks.append({
                "check_timestamp": p.get("check_timestamp"),
                "events_verified": p.get("events_verified_count"),
                "chain_valid": p.get("chain_valid"),
                "tamper_detected": p.get("tamper_detected"),
                "integrity_hash": (p.get("integrity_hash") or "")[:16] + "...",
            })
    return {"application_id": app_id, "integrity_checks": checks,
            "total_checks": len(checks)}


# ── MCP TOOLS LIST ────────────────────────────────────────────────────────────

@app.get("/mcp/tools")
def mcp_tools():
    import sys
    sys.path.insert(0, ".")
    from src.mcp.tools import TOOL_DEFINITIONS
    return {"tools": TOOL_DEFINITIONS, "total": len(TOOL_DEFINITIONS)}


@app.get("/mcp/resources")
def mcp_resources():
    import sys
    sys.path.insert(0, ".")
    from src.mcp.resources import RESOURCE_TEMPLATES
    return {"resources": RESOURCE_TEMPLATES, "total": len(RESOURCE_TEMPLATES)}


# ── PRESENTATION DEMOS & ACTIONS ──────────────────────────────────────────────

from pydantic import BaseModel
import subprocess
import os
import time

class PipelineRunRequest(BaseModel):
    application_id: str
    amount: float = 500000
    jurisdiction: str = "CA"

@app.post("/pipeline/run")
def run_pipeline(req: PipelineRunRequest):
    """Triggers the run_pipeline.py script."""
    cmd = [
        "python", "scripts/run_pipeline.py",
        "--application", req.application_id,
        "--amount", str(req.amount),
        "--jurisdiction", req.jurisdiction
    ]
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        # We invoke it blocking, but the timeout prevents it from hanging
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90, encoding="utf-8", env=env)
        return {"status": "completed", "output": result.stdout, "error": result.stderr, "returncode": result.returncode}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "output": "Timed out after 90 seconds.", "error": ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/demos/gastown")
async def run_gastown_demo():
    """Triggers a simulated crash/recovery cycle and returns structured progress data."""
    from src.event_store import EventStore
    from src.integrity.gas_town import reconstruct_agent_context
    from agents.base_agent import CreditAnalysisAgent
    from src.commands.handlers import handle_submit_application
    from uuid import uuid4
    import asyncio

    db_url = os.getenv("DATABASE_URL", "postgresql://ledger:ledger@localhost:5432/apex_ledger")
    store = EventStore(db_url)
    await store.connect()

    try:
        app_id = f"APEX-GAS-{uuid4().hex[:4].upper()}"
        # Phase 1: Create Application
        await handle_submit_application(store, app_id, "COMP-GAS-DEMO", 750000, "expansion", 48, "api")

        # Phase 2: Run Doomed Agent
        class DoomedAgent(CreditAnalysisAgent):
            async def _node_load_facts(self, state):
                # We raise error here to simulate crash
                raise TimeoutError("LLM API Timeout (Simulated)")

        agent = DoomedAgent("agent-gas-town-demo", "credit_analysis", store, None, None, "claude-3-5-sonnet")
        
        # We manually run nodes to capture progress for the UI
        # But for this demo handler, we just run it and catch the crash
        try:
            await agent.process_application(app_id)
        except Exception:
            pass
        
        session_id = agent.session_id
        
        # Phase 3: Reconstruct
        context = await reconstruct_agent_context(store, "credit_analysis", session_id)
        
        await store.close()
        
        return {
            "status": "crashed_and_reconstructed",
            "application_id": app_id,
            "session_id": session_id,
            "crash_details": {
                "node": "load_extracted_facts",
                "error": "TimeoutError: LLM API Timeout (Simulated)"
            },
            "reconstruction": {
                "nodes_executed": context.nodes_executed,
                "pending_work": context.pending_work,
                "health": context.session_health_status,
                "total_tokens": context.total_tokens_used,
                "total_cost": context.total_cost_usd
            }
        }
    except Exception as e:
        if store: await store.close()
        raise HTTPException(status_code=500, detail=str(e))

class QueryRequest(BaseModel):
    query: str

@app.post("/query")
def run_live_query(req: QueryRequest):
    """Executes a Read-Only SQL query against the CQRS read models."""
    q = req.query.strip()
    # Basic protection to prevent naive destructive commands
    if not q.lower().startswith("select"):
        raise HTTPException(status_code=400, detail="Only SELECT queries are allowed.")
    
    conn = db()
    try:
        cur = conn.cursor()
        cur.execute(q)
        rows = [dict(r) for r in cur.fetchall()]
        return {"rows": rows, "count": len(rows)}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

class WhatIfRequest(BaseModel):
    application_id: str
    risk_tier_override: str

@app.post("/demos/whatif")
def run_whatif_demo(req: WhatIfRequest):
    """Simulates a counterfactual query on the Decision matrix."""
    # We will simulate the Decision agent's logic for the UI demonstration immediately
    # In a full implementation, this might rebuild a stream and run the agent in memory
    time.sleep(1) # simulate agent thinking
    is_high = req.risk_tier_override.upper() == "HIGH"
    return {
        "original": {
            "risk_tier": "MEDIUM",
            "decision": "APPROVE",
            "confidence": 0.81,
            "rationale": "Applicant demonstrates stable revenue and adequate debt service coverage. All rules cleared."
        },
        "counterfactual": {
            "risk_tier": req.risk_tier_override.upper(),
            "decision": "REFER" if is_high else "APPROVE",
            "confidence": 0.95 if is_high else 0.85,
            "rationale": "Risk tier elevated to HIGH. Policy DE-004 requires mandatory human escalation for high-risk applications. Final decision deferred." if is_high else "Risk tier acceptable. Proceed with standard approval."
        }
    }

@app.post("/demos/upcasting")
async def run_upcasting_demo():
    """Simulates a Schema Evolution cycle: v1 Stored -> v2 Loaded."""
    from src.event_store import EventStore
    from src.upcasting.upcasters import registry
    from uuid import uuid4
    
    db_url = os.getenv("DATABASE_URL", "postgresql://ledger:ledger@localhost:5432/apex_ledger")
    store = EventStore(db_url, upcaster_registry=registry)
    await store.connect()
    
    try:
        app_id = f"APEX-UPCAST-{uuid4().hex[:4].upper()}"
        stream_id = f"credit-{app_id}"
        
        # 1. Store a Version 1 event (legacy schema)
        v1_payload = {
            "application_id": app_id,
            "model_version": "credit-v1.0.0-legacy",
            "decision": "APPROVE"
        }
        
        # We append directly to the store
        await store.append(stream_id, [{
            "event_type": "CreditAnalysisCompleted",
            "event_version": 1,
            "payload": v1_payload
        }], expected_version=-1)
        
        # 2. Load it back (Upcaster Registry should transform it to v2)
        loaded_events = await store.load_stream(stream_id)
        v2_event = loaded_events[0]
        
        # 3. Check raw database content (to prove it's still v1)
        import psycopg2; import psycopg2.extras
        conn = psycopg2.connect(db_url)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT event_version, payload FROM events WHERE stream_id = %s", (stream_id,))
        raw_db_row = cur.fetchone()
        conn.close()
        
        await store.close()
        
        return {
            "application_id": app_id,
            "raw_db": {
                "version": raw_db_row["event_version"],
                "payload": raw_db_row["payload"] if isinstance(raw_db_row["payload"], dict) else json.loads(raw_db_row["payload"])
            },
            "loaded_app": {
                "version": v2_event["event_version"],
                "payload": v2_event["payload"]
            },
            "guarantee": "The database row remains Version 1. The application sees Version 2. This is read-time Schema Evolution."
        }
    except Exception as e:
        if store: await store.close()
        raise HTTPException(status_code=500, detail=str(e))

