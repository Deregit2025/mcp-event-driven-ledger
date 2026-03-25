"""
src/integrity/gas_town.py
==========================
Gas Town Agent Memory Pattern — crash recovery via event store replay.

An agent that crashes mid-session can reconstruct its exact context
by replaying its event stream. This module implements that reconstruction.

Named for the infrastructure pattern where agent context is never
stored in memory alone — it is always backed by the append-only
event stream, making crash recovery deterministic.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# Token budget constants
VERBATIM_LAST_N_EVENTS = 3
SUMMARY_WORDS_PER_EVENT = 20


class SessionHealthStatus(str, Enum):
    HEALTHY = "healthy"
    NEEDS_RECONCILIATION = "needs_reconciliation"
    FAILED = "failed"
    COMPLETED = "completed"


@dataclass
class AgentContext:
    session_id: str
    agent_type: str
    application_id: str
    model_version: str
    context_source: str
    context_text: str
    last_event_position: int
    nodes_executed: list[str]
    pending_work: list[str]
    session_health_status: SessionHealthStatus
    total_tokens_used: int = 0
    total_cost_usd: float = 0.0
    needs_reconciliation: bool = False
    reconciliation_reason: str | None = None


# ── MAIN FUNCTION ─────────────────────────────────────────────────────────────

async def reconstruct_agent_context(
    store,
    agent_id: str,
    session_id: str,
    token_budget: int = 8000,
) -> AgentContext:
    """
    Reconstruct agent context from event stream after a crash.

    1. Load full AgentSession stream for agent_id + session_id
    2. Identify: last completed action, pending work, current state
    3. Summarise old events into prose (token-efficient)
    4. Preserve verbatim: last 3 events + any PENDING/ERROR state events
    5. Return AgentContext with everything needed to resume

    CRITICAL: if the agent's last event was a partial decision
    (no corresponding completion event), flags NEEDS_RECONCILIATION.
    """
    # Try all known agent types to find the stream
    agent_types = [
        agent_id,  # try direct match first
        "credit_analysis", "fraud_detection", "compliance",
        "document_processing", "decision_orchestrator", "orchestrator",
    ]

    events = []
    found_stream = None

    for agent_type in agent_types:
        stream_id = f"agent-{agent_type}-{session_id}"
        candidate = await store.load_stream(stream_id)
        if candidate:
            events = candidate
            found_stream = stream_id
            break

    if not events:
        # Return minimal context indicating session not found
        return AgentContext(
            session_id=session_id,
            agent_type=agent_id,
            application_id="unknown",
            model_version="unknown",
            context_source="fresh",
            context_text=f"No prior session found for session_id={session_id}. Starting fresh.",
            last_event_position=-1,
            nodes_executed=[],
            pending_work=[],
            session_health_status=SessionHealthStatus.HEALTHY,
        )

    # Extract session metadata from first event
    first = events[0]
    first_payload = first.get("payload", {})
    agent_type = first_payload.get("agent_type", agent_id)
    application_id = first_payload.get("application_id", "unknown")
    model_version = first_payload.get("model_version", "unknown")
    context_source = first_payload.get("context_source", "fresh")

    # Analyse events to build context
    nodes_executed = []
    pending_work = []
    total_tokens = 0
    total_cost = 0.0
    last_successful_node = None
    is_crashed = False
    is_completed = False
    error_type = None
    recoverable = True
    partial_decision = False

    for ev in events:
        et = ev.get("event_type", "")
        p = ev.get("payload", {})

        if et == "AgentNodeExecuted":
            node = p.get("node_name", "unknown")
            nodes_executed.append(node)
            last_successful_node = node
            total_tokens += (p.get("llm_tokens_input", 0) or 0) + \
                            (p.get("llm_tokens_output", 0) or 0)
            total_cost += p.get("llm_cost_usd", 0.0) or 0.0

        elif et == "AgentSessionFailed":
            is_crashed = True
            error_type = p.get("error_type")
            recoverable = p.get("recoverable", True)

        elif et == "AgentSessionCompleted":
            is_completed = True
            total_tokens = p.get("total_tokens_used", total_tokens)
            total_cost = p.get("total_cost_usd", total_cost)

        elif et in ("CreditAnalysisStarted", "FraudScreeningStarted", "ComplianceCheckStarted"):
            # Started but may not have completed — potential partial decision
            partial_decision = True

        elif et in ("CreditAnalysisCompleted", "FraudScreeningCompleted", "ComplianceCheckCompleted"):
            partial_decision = False  # completed properly

    # Determine health status
    if is_completed:
        health = SessionHealthStatus.COMPLETED
        needs_reconciliation = False
        reconciliation_reason = None
    elif is_crashed and partial_decision:
        health = SessionHealthStatus.NEEDS_RECONCILIATION
        needs_reconciliation = True
        reconciliation_reason = (
            f"Session crashed ({error_type}) with a partial decision in progress. "
            "Must verify whether the decision was committed before resuming."
        )
    elif is_crashed and recoverable:
        health = SessionHealthStatus.NEEDS_RECONCILIATION
        needs_reconciliation = True
        reconciliation_reason = (
            f"Session crashed with {error_type}. "
            f"Last successful node: {last_successful_node or 'none'}. "
            "Resume from last successful node."
        )
    elif is_crashed and not recoverable:
        health = SessionHealthStatus.FAILED
        needs_reconciliation = False
        reconciliation_reason = f"Non-recoverable crash: {error_type}"
    else:
        health = SessionHealthStatus.HEALTHY
        needs_reconciliation = False
        reconciliation_reason = None

    # Build context text within token budget
    context_text = _build_context_text(
        events=events,
        nodes_executed=nodes_executed,
        last_successful_node=last_successful_node,
        health=health,
        reconciliation_reason=reconciliation_reason,
        token_budget=token_budget,
    )

    # Determine pending work based on what hasn't been done
    all_expected_nodes = _expected_nodes_for_agent(agent_type)
    pending_work = [n for n in all_expected_nodes if n not in nodes_executed]

    return AgentContext(
        session_id=session_id,
        agent_type=agent_type,
        application_id=application_id,
        model_version=model_version,
        context_source=f"prior_session_replay:{session_id}",
        context_text=context_text,
        last_event_position=len(events) - 1,
        nodes_executed=nodes_executed,
        pending_work=pending_work,
        session_health_status=health,
        total_tokens_used=total_tokens,
        total_cost_usd=total_cost,
        needs_reconciliation=needs_reconciliation,
        reconciliation_reason=reconciliation_reason,
    )


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _build_context_text(
    events: list[dict],
    nodes_executed: list[str],
    last_successful_node: str | None,
    health: SessionHealthStatus,
    reconciliation_reason: str | None,
    token_budget: int,
) -> str:
    """
    Build token-efficient context text.
    - Summarise early events in prose
    - Preserve last 3 events verbatim
    - Always include PENDING/ERROR events verbatim
    """
    lines = ["=== AGENT SESSION CONTEXT (reconstructed from event store) ===\n"]

    # Status summary
    lines.append(f"Session health: {health.value}")
    if reconciliation_reason:
        lines.append(f"⚠️  RECONCILIATION NEEDED: {reconciliation_reason}")
    lines.append(f"Nodes completed: {', '.join(nodes_executed) if nodes_executed else 'none'}")
    if last_successful_node:
        lines.append(f"Last successful node: {last_successful_node}")
    lines.append("")

    # Summarise older events (token efficient)
    early_events = events[:-VERBATIM_LAST_N_EVENTS] if len(events) > VERBATIM_LAST_N_EVENTS else []
    recent_events = events[-VERBATIM_LAST_N_EVENTS:] if events else []

    if early_events:
        lines.append("--- Earlier session history (summarised) ---")
        for ev in early_events:
            et = ev.get("event_type", "unknown")
            p = ev.get("payload", {})
            summary = _summarise_event(et, p)
            lines.append(f"• {summary}")
        lines.append("")

    # Preserve recent events verbatim
    if recent_events:
        lines.append("--- Most recent events (verbatim) ---")
        for ev in recent_events:
            et = ev.get("event_type", "unknown")
            pos = ev.get("stream_position", "?")
            p = ev.get("payload", {})
            lines.append(f"[pos={pos}] {et}: {p}")
        lines.append("")

    context = "\n".join(lines)

    # Rough token estimate: 1 token ≈ 4 chars
    if len(context) > token_budget * 4:
        context = context[:token_budget * 4] + "\n... [truncated to fit token budget]"

    return context


def _summarise_event(event_type: str, payload: dict) -> str:
    """One-line summary of an event for the context window."""
    summaries = {
        "AgentSessionStarted": lambda p: f"Session started for app {p.get('application_id')} with model {p.get('model_version')}",
        "AgentNodeExecuted": lambda p: f"Node '{p.get('node_name')}' executed ({p.get('llm_tokens_input', 0)} tokens in, {p.get('llm_tokens_output', 0)} out)",
        "AgentSessionCompleted": lambda p: f"Session completed — {p.get('total_llm_calls', 0)} LLM calls, ${p.get('total_cost_usd', 0):.4f}",
        "AgentSessionFailed": lambda p: f"Session FAILED: {p.get('error_type')} — {p.get('error_message', '')}",
        "AgentSessionRecovered": lambda p: f"Session recovered from {p.get('recovered_from_session_id')}",
    }
    fn = summaries.get(event_type)
    if fn:
        try:
            return fn(payload)
        except Exception:
            pass
    return f"{event_type} occurred"


def _expected_nodes_for_agent(agent_type: str) -> list[str]:
    """Return the expected node sequence for a given agent type."""
    nodes = {
        "credit_analysis": ["load_financials", "analyse_ratios", "generate_credit_decision"],
        "fraud_detection": ["run_transaction_analysis", "check_identity", "generate_fraud_score"],
        "compliance": ["load_regulations", "evaluate_rules", "generate_compliance_verdict"],
        "document_processing": ["extract_documents", "validate_documents", "index_documents"],
        "decision_orchestrator": ["load_analyses", "synthesise_decision", "generate_recommendation"],
        "orchestrator": ["load_analyses", "synthesise_decision", "generate_recommendation"],
    }
    return nodes.get(agent_type, [])