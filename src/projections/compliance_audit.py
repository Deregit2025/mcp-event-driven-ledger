"""
src/projections/compliance_audit.py
=====================================
ComplianceAuditViewProjection — current compliance status per application.

Supports temporal queries via compliance_audit_snapshots table.
Snapshot strategy: save snapshot every 10 compliance events.
"""
from __future__ import annotations
import json
import asyncpg


SNAPSHOT_EVERY_N_EVENTS = 10


class ComplianceAuditViewProjection:

    @property
    def name(self) -> str:
        return "compliance_audit_view"

    async def handle(self, event: dict, conn: asyncpg.Connection) -> None:
        et = event["event_type"]
        p = event.get("payload", {})

        handler = getattr(self, f"_on_{_snake(et)}", None)
        if handler:
            await handler(p, event, conn)

    # ── EVENT HANDLERS ────────────────────────────────────────────────────────

    async def _on_compliance_check_initiated(self, p, event, conn):
        app_id = p.get("application_id")
        if not app_id:
            return
        await conn.execute("""
            INSERT INTO compliance_audit_view (
                application_id, regulation_set,
                rules_evaluated, rules_passed, rules_failed, rules_noted,
                has_hard_block, initiated_at, last_event_at, updated_at
            ) VALUES ($1, $2, 0, 0, 0, 0, FALSE, $3, $3, NOW())
            ON CONFLICT (application_id) DO UPDATE SET
                regulation_set = $2,
                initiated_at = $3,
                last_event_at = $3,
                updated_at = NOW()
        """,
            app_id,
            p.get("regulation_set"),
            event.get("recorded_at"),
        )

    async def _on_compliance_rule_passed(self, p, event, conn):
        app_id = p.get("application_id")
        if not app_id:
            return
        await _ensure_row(conn, app_id)
        await conn.execute("""
            UPDATE compliance_audit_view SET
                rules_evaluated = rules_evaluated + 1,
                rules_passed = rules_passed + 1,
                last_event_at = $2,
                updated_at = NOW()
            WHERE application_id = $1
        """, app_id, event.get("recorded_at"))
        await self._maybe_snapshot(conn, app_id, event)

    async def _on_compliance_rule_failed(self, p, event, conn):
        app_id = p.get("application_id")
        if not app_id:
            return
        await _ensure_row(conn, app_id)
        is_hard_block = p.get("severity") == "HARD_BLOCK"
        await conn.execute("""
            UPDATE compliance_audit_view SET
                rules_evaluated = rules_evaluated + 1,
                rules_failed = rules_failed + 1,
                has_hard_block = has_hard_block OR $2,
                block_rule_id = CASE WHEN $2 THEN $3 ELSE block_rule_id END,
                last_event_at = $4,
                updated_at = NOW()
            WHERE application_id = $1
        """, app_id, is_hard_block, p.get("rule_id"), event.get("recorded_at"))
        await self._maybe_snapshot(conn, app_id, event)

    async def _on_compliance_rule_noted(self, p, event, conn):
        app_id = p.get("application_id")
        if not app_id:
            return
        await _ensure_row(conn, app_id)
        await conn.execute("""
            UPDATE compliance_audit_view SET
                rules_evaluated = rules_evaluated + 1,
                rules_noted = rules_noted + 1,
                last_event_at = $2,
                updated_at = NOW()
            WHERE application_id = $1
        """, app_id, event.get("recorded_at"))
        await self._maybe_snapshot(conn, app_id, event)

    async def _on_compliance_check_completed(self, p, event, conn):
        app_id = p.get("application_id")
        if not app_id:
            return
        await _ensure_row(conn, app_id)
        await conn.execute("""
            UPDATE compliance_audit_view SET
                overall_verdict = $2,
                has_hard_block = $3,
                completed_at = $4,
                last_event_at = $4,
                updated_at = NOW()
            WHERE application_id = $1
        """,
            app_id,
            p.get("overall_verdict"),
            p.get("has_hard_block", False),
            event.get("recorded_at"),
        )
        # Always snapshot on completion
        await self._save_snapshot(conn, app_id, event)

    # ── SNAPSHOT ──────────────────────────────────────────────────────────────

    async def _maybe_snapshot(self, conn, app_id, event) -> None:
        """Save a snapshot every N compliance events."""
        row = await conn.fetchrow(
            "SELECT rules_evaluated FROM compliance_audit_view WHERE application_id = $1",
            app_id,
        )
        if row and (row["rules_evaluated"] % SNAPSHOT_EVERY_N_EVENTS == 0):
            await self._save_snapshot(conn, app_id, event)

    async def _save_snapshot(self, conn, app_id, event) -> None:
        """Save point-in-time snapshot of compliance state."""
        row = await conn.fetchrow(
            "SELECT * FROM compliance_audit_view WHERE application_id = $1",
            app_id,
        )
        if not row:
            return
        state = {
            "rules_evaluated": row["rules_evaluated"],
            "rules_passed": row["rules_passed"],
            "rules_failed": row["rules_failed"],
            "rules_noted": row["rules_noted"],
            "has_hard_block": row["has_hard_block"],
            "overall_verdict": row["overall_verdict"],
            "block_rule_id": row["block_rule_id"],
        }
        await conn.execute("""
            INSERT INTO compliance_audit_snapshots
                (application_id, global_position, state, snapshot_at)
            VALUES ($1, $2, $3::jsonb, NOW())
        """,
            app_id,
            event["global_position"],
            json.dumps(state),
        )

    async def get_compliance_at(
        self,
        conn,
        application_id: str,
        at_timestamp,
    ) -> dict | None:
        """
        Temporal query: what was the compliance state at a given timestamp?
        Uses snapshots for efficiency — no full event replay needed.
        """
        row = await conn.fetchrow("""
            SELECT state FROM compliance_audit_snapshots
            WHERE application_id = $1
              AND snapshot_at <= $2
            ORDER BY snapshot_at DESC
            LIMIT 1
        """, application_id, at_timestamp)

        if not row:
            return None
        return dict(row["state"])


# ── HELPERS ───────────────────────────────────────────────────────────────────

async def _ensure_row(conn, app_id: str) -> None:
    """Create row if it does not exist."""
    await conn.execute("""
        INSERT INTO compliance_audit_view (application_id)
        VALUES ($1)
        ON CONFLICT (application_id) DO NOTHING
    """, app_id)


def _snake(event_type: str) -> str:
    import re
    return re.sub(r'(?<!^)(?=[A-Z])', '_', event_type).lower()