"""
src/mcp/resources.py
=====================
MCP resource definitions for the Apex Ledger.

Resources are read-only views — they NEVER replay streams directly
except where explicitly justified (audit-trail, agent sessions).
All other resources read from projections.

Resource URI templates:
  ledger://applications/{id}                  → ApplicationSummary projection
  ledger://applications/{id}/audit-trail      → raw event replay (justified)
  ledger://applications/{id}/compliance       → ComplianceAuditView projection
  ledger://agents/{id}/performance            → AgentPerformanceLedger projection
  ledger://sessions/{session_id}              → AgentSession stream (justified)
  ledger://ledger/health                      → ProjectionDaemon lag metrics
"""
from __future__ import annotations
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ── RESOURCE DEFINITIONS ──────────────────────────────────────────────────────

RESOURCE_TEMPLATES = [
    {
        "uriTemplate": "ledger://applications/{application_id}",
        "name": "Application Summary",
        "description": (
            "Current state of a loan application from the ApplicationSummary projection. "
            "Eventually consistent — typically ≤500ms lag from event commit. "
            "For strong consistency use the audit-trail resource instead."
        ),
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "ledger://applications/{application_id}/audit-trail",
        "name": "Application Audit Trail",
        "description": (
            "Complete, authoritative event history for a loan application. "
            "Reads directly from the event store — no projection lag. "
            "Justified exception: audit trails require strong consistency by regulation. "
            "Covers loan, credit, fraud, and compliance streams."
        ),
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "ledger://applications/{application_id}/compliance",
        "name": "Application Compliance View",
        "description": (
            "Compliance audit state for a loan application from the ComplianceAuditView projection. "
            "Supports temporal query: append ?as_of=ISO8601_TIMESTAMP to get state at a past moment. "
            "SLO: p99 < 200ms. Use for regulatory examination and compliance officer queries."
        ),
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "ledger://agents/{agent_id}/performance",
        "name": "Agent Performance Ledger",
        "description": (
            "Aggregated performance metrics for an agent across all model versions. "
            "Reads from the AgentPerformanceLedger projection. "
            "SLO: p99 < 50ms. Use to compare model version performance."
        ),
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "ledger://sessions/{session_id}",
        "name": "Agent Session History",
        "description": (
            "Full event history for an agent session. "
            "Reads directly from the AgentSession stream — justified for Gas Town crash recovery. "
            "SLO: p99 < 300ms."
        ),
        "mimeType": "application/json",
    },
    {
        "uri": "ledger://ledger/health",
        "name": "Ledger Health",
        "description": (
            "Health status of the event store and all projection daemons. "
            "Includes per-projection lag measurements and SLO breach status. "
            "SLO: p99 < 10ms — this is the watchdog endpoint."
        ),
        "mimeType": "application/json",
    },
]


# ── RESOURCE READER ───────────────────────────────────────────────────────────

class LedgerResourceReader:
    """Reads MCP resource URIs and returns structured content."""

    def __init__(self, store, projection_daemon=None, db_pool=None):
        self.store = store
        self.daemon = projection_daemon
        self.db_pool = db_pool  # asyncpg pool for projection reads

    async def read(self, uri: str) -> dict[str, Any]:
        try:
            content = await self._dispatch(uri)
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps(content, default=str, indent=2),
                    }
                ]
            }
        except Exception as e:
            logger.error(f"Resource read failed for {uri}: {e}")
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps({
                            "error": type(e).__name__,
                            "message": str(e),
                            "uri": uri,
                        }, indent=2),
                    }
                ]
            }

    async def _dispatch(self, uri: str) -> Any:
        # Strip query string for routing, keep for handlers
        base_uri = uri.split("?")[0]
        query_str = uri[len(base_uri):]  # e.g. "?as_of=2026-01-01T00:00:00Z"

        if base_uri == "ledger://ledger/health":
            return await self._read_health()

        if base_uri.startswith("ledger://applications/"):
            rest = base_uri.removeprefix("ledger://applications/")

            if rest.endswith("/audit-trail"):
                app_id = rest.removesuffix("/audit-trail")
                return await self._read_audit_trail(app_id)

            if rest.endswith("/compliance"):
                app_id = rest.removesuffix("/compliance")
                as_of = _parse_as_of(query_str)
                return await self._read_compliance(app_id, as_of)

            # Plain application summary
            return await self._read_application_summary(rest)

        if base_uri.startswith("ledger://agents/") and "/performance" in base_uri:
            agent_id = base_uri.removeprefix("ledger://agents/").removesuffix("/performance")
            return await self._read_agent_performance(agent_id)

        if base_uri.startswith("ledger://sessions/"):
            session_id = base_uri.removeprefix("ledger://sessions/")
            return await self._read_session(session_id)

        raise ValueError(f"Unknown resource URI: {uri}")

    # ── READERS ───────────────────────────────────────────────────────────────

    async def _read_application_summary(self, application_id: str) -> dict:
        """
        Read from ApplicationSummary projection (PostgreSQL table).
        Falls back to aggregate replay if projection not available.
        """
        if self.db_pool:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM application_summary WHERE application_id = $1",
                    application_id,
                )
                if row:
                    return {
                        **dict(row),
                        "_meta": {
                            "source": "application_summary_projection",
                            "consistency": "eventual",
                            "slo_ms": 500,
                        },
                    }

        # Fallback: aggregate replay (strong consistency)
        from src.aggregates.loan_application import LoanApplicationAggregate
        agg = await LoanApplicationAggregate.load(self.store, application_id)
        return {
            "application_id": application_id,
            "state": agg.state.value,
            "applicant_id": agg.applicant_id,
            "requested_amount_usd": float(agg.requested_amount_usd) if agg.requested_amount_usd else None,
            "loan_purpose": agg.loan_purpose,
            "submission_channel": agg.submission_channel,
            "credit_confidence": agg.credit_confidence,
            "credit_risk_tier": agg.credit_risk_tier,
            "fraud_score": agg.fraud_score,
            "compliance_verdict": agg.compliance_verdict,
            "compliance_has_hard_block": agg.compliance_has_hard_block,
            "approved_amount": agg.approved_amount,
            "is_terminal": agg.is_terminal,
            "stream_version": agg.stream_version,
            "_meta": {
                "source": "event_store_replay_fallback",
                "consistency": "strong",
                "note": "Projection unavailable — read directly from event store",
            },
        }

    async def _read_audit_trail(self, application_id: str) -> dict:
        """
        Raw event replay across all 4 streams.
        Justified exception: audit trails require strong consistency.
        """
        stream_prefixes = [
            f"loan-{application_id}",
            f"credit-{application_id}",
            f"fraud-{application_id}",
            f"compliance-{application_id}",
        ]
        all_events = []
        for stream_id in stream_prefixes:
            for e in await self.store.load_stream(stream_id):
                all_events.append({
                    "event_id": str(e.get("event_id", "")),
                    "stream_id": e.get("stream_id", stream_id),
                    "stream_position": e.get("stream_position"),
                    "global_position": e.get("global_position"),
                    "event_type": e.get("event_type"),
                    "event_version": e.get("event_version", 1),
                    "payload": e.get("payload", {}),
                    "recorded_at": str(e.get("recorded_at", "")),
                    "causation_id": e.get("metadata", {}).get("causation_id"),
                    "correlation_id": e.get("metadata", {}).get("correlation_id"),
                })

        all_events.sort(key=lambda e: (e.get("recorded_at") or "", e.get("global_position") or 0))
        return {
            "application_id": application_id,
            "total_events": len(all_events),
            "streams_covered": stream_prefixes,
            "events": all_events,
            "_meta": {"source": "event_store_replay", "consistency": "strong"},
        }

    async def _read_compliance(self, application_id: str, as_of=None) -> dict:
        """
        Read from ComplianceAuditView projection.
        Supports temporal query via as_of timestamp (uses snapshots).
        """
        if self.db_pool:
            async with self.db_pool.acquire() as conn:
                if as_of:
                    # Temporal query — use snapshot table
                    from src.projections.compliance_audit import ComplianceAuditViewProjection
                    proj = ComplianceAuditViewProjection()
                    state = await proj.get_compliance_at(conn, application_id, as_of)
                    if state:
                        return {
                            "application_id": application_id,
                            "as_of": str(as_of),
                            "temporal_query": True,
                            **state,
                            "_meta": {
                                "source": "compliance_audit_snapshot",
                                "consistency": "eventual",
                                "slo_ms": 200,
                            },
                        }
                    return {
                        "application_id": application_id,
                        "as_of": str(as_of),
                        "error": "no_snapshot_before_timestamp",
                        "message": "No compliance snapshot exists before the requested timestamp.",
                    }

                # Current state
                row = await conn.fetchrow(
                    "SELECT * FROM compliance_audit_view WHERE application_id = $1",
                    application_id,
                )
                if row:
                    return {
                        **dict(row),
                        "_meta": {
                            "source": "compliance_audit_view_projection",
                            "consistency": "eventual",
                            "slo_ms": 200,
                        },
                    }

        # Fallback: replay compliance stream
        events = await self.store.load_stream(f"compliance-{application_id}")
        return {
            "application_id": application_id,
            "raw_events": [
                {
                    "event_type": e.get("event_type"),
                    "payload": e.get("payload", {}),
                    "recorded_at": str(e.get("recorded_at", "")),
                }
                for e in events
            ],
            "_meta": {
                "source": "event_store_replay_fallback",
                "consistency": "strong",
                "note": "DB pool unavailable — direct stream read",
            },
        }

    async def _read_agent_performance(self, agent_id: str) -> dict:
        """
        Read from AgentPerformanceLedger projection.
        Returns all model versions for this agent_id.
        """
        if self.db_pool:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT * FROM agent_performance_ledger
                    WHERE agent_type = $1
                    ORDER BY last_session_at DESC NULLS LAST
                    """,
                    agent_id,
                )
                if rows:
                    return {
                        "agent_id": agent_id,
                        "model_versions": [dict(r) for r in rows],
                        "_meta": {
                            "source": "agent_performance_ledger_projection",
                            "consistency": "eventual",
                            "slo_ms": 50,
                        },
                    }

        return {
            "agent_id": agent_id,
            "model_versions": [],
            "_meta": {
                "source": "projection_unavailable",
                "note": "No DB pool configured or no data found for this agent_id",
            },
        }

    async def _read_session(self, session_id: str) -> dict:
        """
        Read agent session history — direct stream load.
        Justified: used for Gas Town crash recovery requiring exact event sequence.
        """
        agent_types = [
            "credit_analysis", "fraud_detection", "compliance",
            "document_processing", "orchestrator", "decision_orchestrator",
        ]
        for agent_type in agent_types:
            stream_id = f"agent-{agent_type}-{session_id}"
            events = await self.store.load_stream(stream_id)
            if events:
                from src.aggregates.agent_session import AgentSessionAggregate
                agg = AgentSessionAggregate(session_id=session_id)
                for e in events:
                    agg.apply(e)
                return {
                    "session_id": session_id,
                    "agent_type": agg.agent_type,
                    "application_id": agg.application_id,
                    "model_version": agg.model_version,
                    "status": agg.status.value,
                    "context_source": agg.context_source,
                    "nodes_executed": agg.nodes_executed,
                    "last_successful_node": agg.last_successful_node,
                    "total_llm_calls": agg.total_llm_calls,
                    "total_tokens_used": agg.total_tokens_used,
                    "total_cost_usd": agg.total_cost_usd,
                    "is_crashed": agg.is_crashed,
                    "recovered_from_session_id": agg.recovered_from_session_id,
                    "stream_version": agg.stream_version,
                    "raw_events": [
                        {
                            "event_type": e.get("event_type"),
                            "stream_position": e.get("stream_position"),
                            "recorded_at": str(e.get("recorded_at", "")),
                        }
                        for e in events
                    ],
                    "_meta": {
                        "source": "agent_session_stream_replay",
                        "consistency": "strong",
                        "slo_ms": 300,
                    },
                }

        return {
            "error": "session_not_found",
            "session_id": session_id,
            "message": f"No agent stream found for session '{session_id}'",
        }

    async def _read_health(self) -> dict:
        health = {
            "status": "healthy",
            "event_store": "connected",
            "projections": {},
            "slo_definitions": {
                "application_summary": 500,
                "agent_performance_ledger": 50,
                "compliance_audit_view": 200,
            },
        }
        if self.daemon:
            daemon_health = self.daemon.get_health()
            health["projections"] = daemon_health.get("projections", {})
            health["slo_breaches"] = daemon_health.get("slo_breaches", [])
            if daemon_health.get("slo_breaches"):
                health["status"] = "degraded"
        else:
            health["projections"] = {"note": "No projection daemon configured"}
        return health


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _parse_as_of(query_str: str):
    """Parse ?as_of=ISO8601 from query string. Returns datetime or None."""
    if not query_str or "as_of=" not in query_str:
        return None
    try:
        from datetime import datetime, timezone
        val = query_str.split("as_of=")[1].split("&")[0]
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        return dt
    except Exception:
        return None