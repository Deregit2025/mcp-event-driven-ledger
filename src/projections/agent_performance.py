"""
src/projections/agent_performance.py
======================================
AgentPerformanceLedgerProjection — metrics per agent type per model version.

CRITICAL: This projection maintains running averages — a non-idempotent operation.
The ProjectionDaemon's advisory lock MUST be active before running this projection.
Duplicate processing would corrupt running averages silently.

Tracks:
  - Session counts (total, successful, failed)
  - Decision distribution (approve, decline, refer)
  - Average confidence score
  - Total LLM cost and tokens
  - Average cost per session
  - Average duration
"""
from __future__ import annotations
import asyncpg


class AgentPerformanceLedgerProjection:

    @property
    def name(self) -> str:
        return "agent_performance_ledger"

    async def handle(self, event: dict, conn: asyncpg.Connection) -> None:
        et = event["event_type"]
        p = event.get("payload", {})

        handler = getattr(self, f"_on_{_snake(et)}", None)
        if handler:
            await handler(p, event, conn)

    # ── EVENT HANDLERS ────────────────────────────────────────────────────────

    async def _on_agent_session_started(self, p, event, conn):
        """Ensure a row exists for this agent_type + model_version."""
        agent_type = p.get("agent_type", "unknown")
        model_version = p.get("model_version", "unknown")
        await conn.execute("""
            INSERT INTO agent_performance_ledger (agent_type, model_version)
            VALUES ($1, $2)
            ON CONFLICT (agent_type, model_version) DO NOTHING
        """, agent_type, model_version)

    async def _on_agent_session_completed(self, p, event, conn):
        """
        Update running averages on session completion.
        Uses weighted average formula: new_avg = (old_avg × n + new_val) / (n + 1)
        """
        agent_type = p.get("agent_type", "unknown")
        model_version = p.get("model_version", "unknown")
        cost = p.get("total_cost_usd") or 0.0
        tokens = p.get("total_tokens_used") or 0
        duration_ms = p.get("duration_ms") or 0.0

        # Ensure row exists
        await conn.execute("""
            INSERT INTO agent_performance_ledger (agent_type, model_version)
            VALUES ($1, $2)
            ON CONFLICT (agent_type, model_version) DO NOTHING
        """, agent_type, model_version)

        # Read current state
        row = await conn.fetchrow("""
            SELECT total_sessions, avg_cost_per_session, avg_duration_ms,
                   total_llm_cost_usd, total_tokens_used, successful_sessions
            FROM agent_performance_ledger
            WHERE agent_type = $1 AND model_version = $2
            FOR UPDATE
        """, agent_type, model_version)

        n = row["total_sessions"] or 0
        old_avg_cost = row["avg_cost_per_session"] or 0.0
        old_avg_dur = row["avg_duration_ms"] or 0.0

        # Weighted running average
        new_avg_cost = (old_avg_cost * n + cost) / (n + 1) if n >= 0 else cost
        new_avg_dur = (old_avg_dur * n + duration_ms) / (n + 1) if n >= 0 else duration_ms

        await conn.execute("""
            UPDATE agent_performance_ledger SET
                total_sessions = total_sessions + 1,
                successful_sessions = successful_sessions + 1,
                total_llm_cost_usd = total_llm_cost_usd + $3,
                total_tokens_used = total_tokens_used + $4,
                avg_cost_per_session = $5,
                avg_duration_ms = $6,
                last_session_at = $7,
                updated_at = NOW()
            WHERE agent_type = $1 AND model_version = $2
        """,
            agent_type, model_version,
            cost, tokens,
            new_avg_cost, new_avg_dur,
            event.get("recorded_at"),
        )

    async def _on_agent_session_failed(self, p, event, conn):
        """Increment failed session counter."""
        agent_type = p.get("agent_type", "unknown")
        model_version = p.get("model_version", "unknown")

        await conn.execute("""
            INSERT INTO agent_performance_ledger (agent_type, model_version, failed_sessions)
            VALUES ($1, $2, 1)
            ON CONFLICT (agent_type, model_version) DO UPDATE SET
                total_sessions = agent_performance_ledger.total_sessions + 1,
                failed_sessions = agent_performance_ledger.failed_sessions + 1,
                updated_at = NOW()
        """, agent_type, model_version)

    async def _on_credit_analysis_completed(self, p, event, conn):
        """Track credit decision distribution and confidence averages."""
        decision = p.get("decision", {})
        if not isinstance(decision, dict):
            return

        agent_type = "credit_analysis"
        model_version = p.get("screening_model_version") or p.get("model_version", "unknown")
        confidence = decision.get("confidence") or 0.0
        risk_tier = decision.get("risk_tier", "")

        # Map risk tier to decision bucket
        if risk_tier in ("LOW", "MEDIUM"):
            decision_col = "approve_count"
        elif risk_tier == "HIGH":
            decision_col = "decline_count"
        else:
            decision_col = "refer_count"

        # Update confidence running average
        row = await conn.fetchrow("""
            SELECT total_sessions, avg_confidence
            FROM agent_performance_ledger
            WHERE agent_type = $1 AND model_version = $2
            FOR UPDATE
        """, agent_type, model_version)

        if row:
            n = row["total_sessions"] or 0
            old_avg = row["avg_confidence"] or 0.0
            new_avg = (old_avg * n + confidence) / (n + 1) if n > 0 else confidence

            await conn.execute(f"""
                UPDATE agent_performance_ledger SET
                    {decision_col} = {decision_col} + 1,
                    avg_confidence = $3,
                    updated_at = NOW()
                WHERE agent_type = $1 AND model_version = $2
            """, agent_type, model_version, new_avg)


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _snake(event_type: str) -> str:
    import re
    return re.sub(r'(?<!^)(?=[A-Z])', '_', event_type).lower()