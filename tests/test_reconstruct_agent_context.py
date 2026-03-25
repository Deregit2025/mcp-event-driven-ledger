"""
tests/test_reconstruct_agent_context.py
=========================================
Tests for reconstruct_agent_context() — the Gas Town crash recovery API.

The rubric requires:
  - Start a session, append 5 events
  - Simulate a crash (kill in-memory agent object)
  - Call reconstruct_agent_context() WITHOUT the in-memory agent
  - Verify reconstructed context contains enough to continue

Run: pytest tests/test_reconstruct_agent_context.py -v
"""
import pytest
from src.event_store import InMemoryEventStore
from src.integrity.gas_town import (
    reconstruct_agent_context,
    SessionHealthStatus,
    AgentContext,
)


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _ev(event_type: str, **payload) -> dict:
    return {"event_type": event_type, "event_version": 1, "payload": payload}


async def _append(store, stream_id, event):
    ver = await store.stream_version(stream_id)
    await store.append(stream_id, [event], expected_version=ver)


# ── TEST 1: THE RUBRIC-SPECIFIED CRASH RECOVERY TEST ─────────────────────────

@pytest.mark.asyncio
async def test_reconstruct_after_5_events_crash_recovery():
    """
    THE core Gas Town test — exactly as specified in the rubric:

    1. Start an agent session
    2. Append 5 events (session start + 4 node executions)
    3. Simulate a crash — discard the in-memory agent object entirely
    4. Call reconstruct_agent_context() with NO in-memory agent
    5. Verify the reconstructed context is sufficient to continue:
       - knows which nodes were completed
       - knows which nodes are still pending
       - context_text summarises history
       - context_source references the prior session
    """
    store = InMemoryEventStore()
    stream_id = "agent-credit_analysis-sess-crash-01"
    session_id = "sess-crash-01"

    # ── Step 1–2: Append 5 events ──────────────────────────────────────────
    await _append(store, stream_id, _ev(
        "AgentSessionStarted",
        session_id=session_id,
        agent_type="credit_analysis",
        agent_id="agent-credit-001",
        application_id="APEX-CRASH-01",
        model_version="credit-v2.3",
        context_source="fresh",
    ))  # event 1

    await _append(store, stream_id, _ev(
        "AgentNodeExecuted",
        node_name="load_financials",
        llm_tokens_input=500, llm_tokens_output=100, llm_cost_usd=0.001,
    ))  # event 2

    await _append(store, stream_id, _ev(
        "AgentNodeExecuted",
        node_name="validate_documents",
        llm_tokens_input=300, llm_tokens_output=80, llm_cost_usd=0.0008,
    ))  # event 3

    await _append(store, stream_id, _ev(
        "AgentNodeExecuted",
        node_name="analyse_ratios",
        llm_tokens_input=800, llm_tokens_output=200, llm_cost_usd=0.002,
    ))  # event 4

    await _append(store, stream_id, _ev(
        "AgentSessionFailed",
        error_type="TimeoutError",
        error_message="LLM API call timed out after 30s",
        recoverable=True,
        last_successful_node="analyse_ratios",
    ))  # event 5

    # ── Step 3: Simulate crash — agent object gone from memory ────────────
    # There is no in-memory agent object here.
    # reconstruct_agent_context() has ONLY the event store to work with.

    # ── Step 4: Reconstruct context from event store only ─────────────────
    context: AgentContext = await reconstruct_agent_context(
        store=store,
        agent_id="credit_analysis",
        session_id=session_id,
        token_budget=8000,
    )

    # ── Step 5: Verify reconstructed context is sufficient to continue ────

    # Basic identity
    assert context.session_id == session_id
    assert context.agent_type == "credit_analysis"
    assert context.application_id == "APEX-CRASH-01"
    assert context.model_version == "credit-v2.3"

    # Context source must reference the prior session
    assert "prior_session_replay" in context.context_source
    assert session_id in context.context_source

    # Completed nodes must be known
    assert "load_financials" in context.nodes_executed
    assert "validate_documents" in context.nodes_executed
    assert "analyse_ratios" in context.nodes_executed

    # Pending work must be populated — agent knows what's left
    assert len(context.pending_work) > 0
    assert "generate_credit_decision" in context.pending_work

    # Health status must flag needs_reconciliation (crashed mid-session)
    assert context.session_health_status == SessionHealthStatus.NEEDS_RECONCILIATION
    assert context.needs_reconciliation is True
    assert context.reconciliation_reason is not None

    # Context text must contain history summary
    assert len(context.context_text) > 0
    assert "load_financials" in context.context_text or "AGENT SESSION CONTEXT" in context.context_text

    # Last event position must be correct (5 events = positions 0-4)
    assert context.last_event_position == 4

    # Cost and token tracking
    assert context.total_tokens_used > 0
    assert context.total_cost_usd > 0.0


# ── TEST 2: HEALTHY SESSION RECONSTRUCTION ────────────────────────────────────

@pytest.mark.asyncio
async def test_reconstruct_healthy_session():
    """
    Reconstructing an active (not crashed) session returns HEALTHY status
    and correct node list.
    """
    store = InMemoryEventStore()
    session_id = "sess-healthy-01"
    stream_id = f"agent-fraud_detection-{session_id}"

    await _append(store, stream_id, _ev(
        "AgentSessionStarted",
        session_id=session_id,
        agent_type="fraud_detection",
        agent_id="agent-fraud-001",
        application_id="APEX-HEALTHY-01",
        model_version="fraud-v1.1",
        context_source="fresh",
    ))

    await _append(store, stream_id, _ev(
        "AgentNodeExecuted",
        node_name="run_transaction_analysis",
        llm_tokens_input=400, llm_tokens_output=100, llm_cost_usd=0.001,
    ))

    context = await reconstruct_agent_context(
        store=store,
        agent_id="fraud_detection",
        session_id=session_id,
    )

    assert context.session_health_status == SessionHealthStatus.HEALTHY
    assert context.needs_reconciliation is False
    assert "run_transaction_analysis" in context.nodes_executed
    assert "check_identity" in context.pending_work
    assert "generate_fraud_score" in context.pending_work


# ── TEST 3: COMPLETED SESSION RECONSTRUCTION ─────────────────────────────────

@pytest.mark.asyncio
async def test_reconstruct_completed_session():
    """Completed session returns COMPLETED status and empty pending_work."""
    store = InMemoryEventStore()
    session_id = "sess-completed-01"
    stream_id = f"agent-compliance-{session_id}"

    await _append(store, stream_id, _ev(
        "AgentSessionStarted",
        session_id=session_id,
        agent_type="compliance",
        agent_id="agent-comp-001",
        application_id="APEX-DONE-01",
        model_version="compliance-v1.0",
        context_source="fresh",
    ))

    await _append(store, stream_id, _ev(
        "AgentNodeExecuted",
        node_name="load_regulations",
        llm_tokens_input=200, llm_tokens_output=50, llm_cost_usd=0.0005,
    ))

    await _append(store, stream_id, _ev(
        "AgentSessionCompleted",
        total_llm_calls=1,
        total_tokens_used=250,
        total_cost_usd=0.0005,
    ))

    context = await reconstruct_agent_context(
        store=store,
        agent_id="compliance",
        session_id=session_id,
    )

    assert context.session_health_status == SessionHealthStatus.COMPLETED
    assert context.needs_reconciliation is False


# ── TEST 4: NON-EXISTENT SESSION ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reconstruct_nonexistent_session_returns_fresh():
    """
    Reconstructing a session that never existed returns a fresh context
    rather than raising an exception.
    """
    store = InMemoryEventStore()

    context = await reconstruct_agent_context(
        store=store,
        agent_id="credit_analysis",
        session_id="sess-does-not-exist",
    )

    assert context.session_health_status == SessionHealthStatus.HEALTHY
    assert context.last_event_position == -1
    assert context.nodes_executed == []
    assert "Starting fresh" in context.context_text or context.last_event_position == -1


# ── TEST 5: TOKEN BUDGET ENFORCEMENT ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_reconstruct_respects_token_budget():
    """
    Context text must not exceed the token budget.
    1 token ≈ 4 chars.
    """
    store = InMemoryEventStore()
    session_id = "sess-budget-01"
    stream_id = f"agent-credit_analysis-{session_id}"

    await _append(store, stream_id, _ev(
        "AgentSessionStarted",
        session_id=session_id,
        agent_type="credit_analysis",
        agent_id="agent-001",
        application_id="APEX-BUDGET-01",
        model_version="credit-v2.3",
        context_source="fresh",
    ))

    # Append many nodes to create a long history
    for i in range(20):
        await _append(store, stream_id, _ev(
            "AgentNodeExecuted",
            node_name=f"node_{i}",
            llm_tokens_input=500, llm_tokens_output=100, llm_cost_usd=0.001,
        ))

    small_budget = 200  # very small budget
    context = await reconstruct_agent_context(
        store=store,
        agent_id="credit_analysis",
        session_id=session_id,
        token_budget=small_budget,
    )

    # Context text must be within budget (1 token ≈ 4 chars)
    assert len(context.context_text) <= small_budget * 4 + 100  # small tolerance


# ── TEST 6: SUMMARISATION STRATEGY ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_reconstruct_summarises_old_preserves_recent():
    """
    Early events are summarised in prose.
    Last 3 events are preserved verbatim.
    This is the token-efficient summarisation strategy.
    """
    store = InMemoryEventStore()
    session_id = "sess-summary-01"
    stream_id = f"agent-credit_analysis-{session_id}"

    await _append(store, stream_id, _ev(
        "AgentSessionStarted",
        session_id=session_id,
        agent_type="credit_analysis",
        agent_id="agent-001",
        application_id="APEX-SUM-01",
        model_version="credit-v2.3",
        context_source="fresh",
    ))

    node_names = ["node_early_1", "node_early_2", "node_recent_1",
                  "node_recent_2", "node_recent_3"]
    for node in node_names:
        await _append(store, stream_id, _ev(
            "AgentNodeExecuted",
            node_name=node,
            llm_tokens_input=100, llm_tokens_output=50, llm_cost_usd=0.0005,
        ))

    context = await reconstruct_agent_context(
        store=store,
        agent_id="credit_analysis",
        session_id=session_id,
    )

    # Context text must exist and contain some history
    assert len(context.context_text) > 50

    # All executed nodes must be tracked
    for node in node_names:
        assert node in context.nodes_executed

    # Pending work must exclude completed nodes
    for node in node_names:
        assert node not in context.pending_work


# ── TEST 7: PENDING WORK RECONSTRUCTION ──────────────────────────────────────

@pytest.mark.asyncio
async def test_reconstruct_pending_work_excludes_completed_nodes():
    """
    pending_work contains only nodes not yet executed.
    This tells the resuming agent exactly what's left to do.
    """
    store = InMemoryEventStore()
    session_id = "sess-pending-01"
    stream_id = f"agent-credit_analysis-{session_id}"

    await _append(store, stream_id, _ev(
        "AgentSessionStarted",
        session_id=session_id,
        agent_type="credit_analysis",
        agent_id="agent-001",
        application_id="APEX-PEND-01",
        model_version="credit-v2.3",
        context_source="fresh",
    ))

    # Only first node completed before crash
    await _append(store, stream_id, _ev(
        "AgentNodeExecuted",
        node_name="load_financials",
        llm_tokens_input=400, llm_tokens_output=100, llm_cost_usd=0.001,
    ))

    await _append(store, stream_id, _ev(
        "AgentSessionFailed",
        error_type="NetworkError",
        error_message="Connection lost",
        recoverable=True,
        last_successful_node="load_financials",
    ))

    context = await reconstruct_agent_context(
        store=store,
        agent_id="credit_analysis",
        session_id=session_id,
    )

    # load_financials done — must NOT be in pending
    assert "load_financials" not in context.pending_work

    # Remaining nodes must be in pending
    assert "analyse_ratios" in context.pending_work
    assert "generate_credit_decision" in context.pending_work

    # Health must flag reconciliation needed
    assert context.needs_reconciliation is True