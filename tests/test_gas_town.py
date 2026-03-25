"""
tests/test_gas_town.py
=======================
Gas Town pattern tests — AgentSessionAggregate crash recovery.

'Gas Town' refers to the pattern where an agent's session stream IS
its memory. On crash, the agent replays its stream to reconstruct
exactly what it has done and resumes without re-doing completed work.

Run: pytest tests/test_gas_town.py -v
"""
import pytest
from src.aggregates.agent_session import AgentSessionAggregate, SessionStatus
from src.event_store import InMemoryEventStore


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _ev(event_type: str, **payload) -> dict:
    return {"event_type": event_type, "event_version": 1, "payload": payload}


async def _build_session(store, session_id: str, agent_type: str = "credit_analysis", events: list = None):
    """Helper: append a sequence of events to an agent session stream."""
    stream_id = f"agent-{agent_type}-{session_id}"
    if events is None:
        events = []
    for i, event in enumerate(events):
        ver = await store.stream_version(stream_id)
        await store.append(stream_id, [event], expected_version=ver)
    return stream_id


# ── CONTEXT LOADED GUARD (Gas Town Rule) ──────────────────────────────────────

@pytest.mark.asyncio
async def test_context_not_loaded_raises_before_session_started():
    """Agent cannot do work without AgentSessionStarted — Gas Town rule."""
    from src.models.events import AgentContextNotLoadedError

    agg = AgentSessionAggregate(session_id="sess-gt-001")
    with pytest.raises(AgentContextNotLoadedError):
        agg.assert_context_loaded()


@pytest.mark.asyncio
async def test_context_loaded_after_session_started():
    """After AgentSessionStarted, context_loaded becomes True."""
    store = InMemoryEventStore()
    stream_id = f"agent-credit_analysis-sess-gt-002"

    await store.append(stream_id, [_ev(
        "AgentSessionStarted",
        session_id="sess-gt-002",
        agent_type="credit_analysis",
        agent_id="agent-001",
        application_id="APEX-001",
        model_version="credit-v2.3",
        context_source="fresh",
    )], expected_version=-1)

    agg = await AgentSessionAggregate.load(store, "credit_analysis", "sess-gt-002")
    assert agg.context_loaded is True
    agg.assert_context_loaded()  # must not raise


# ── NORMAL LIFECYCLE ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_session_progresses_through_normal_lifecycle():
    """Session goes: ACTIVE → nodes execute → COMPLETED."""
    store = InMemoryEventStore()
    stream_id = "agent-credit_analysis-sess-gt-003"

    await store.append(stream_id, [_ev(
        "AgentSessionStarted",
        session_id="sess-gt-003",
        agent_type="credit_analysis",
        agent_id="agent-001",
        application_id="APEX-003",
        model_version="credit-v2.3",
        context_source="fresh",
    )], expected_version=-1)

    await store.append(stream_id, [_ev(
        "AgentNodeExecuted",
        node_name="load_documents",
        llm_tokens_input=500,
        llm_tokens_output=100,
        llm_cost_usd=0.0010,
    )], expected_version=0)

    await store.append(stream_id, [_ev(
        "AgentNodeExecuted",
        node_name="analyse_financials",
        llm_tokens_input=800,
        llm_tokens_output=200,
        llm_cost_usd=0.0020,
    )], expected_version=1)

    await store.append(stream_id, [_ev(
        "AgentSessionCompleted",
        total_llm_calls=2,
        total_tokens_used=1600,
        total_cost_usd=0.0030,
    )], expected_version=2)

    agg = await AgentSessionAggregate.load(store, "credit_analysis", "sess-gt-003")

    assert agg.status == SessionStatus.COMPLETED
    assert "load_documents" in agg.nodes_executed
    assert "analyse_financials" in agg.nodes_executed
    assert agg.total_llm_calls == 2
    assert agg.total_cost_usd == 0.0030


# ── CRASH DETECTION ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_crash_detected_as_needs_reconciliation():
    """AgentSessionFailed with recoverable=True sets NEEDS_RECONCILIATION."""
    store = InMemoryEventStore()
    stream_id = "agent-fraud_detection-sess-gt-004"

    await store.append(stream_id, [_ev(
        "AgentSessionStarted",
        session_id="sess-gt-004",
        agent_type="fraud_detection",
        agent_id="agent-002",
        application_id="APEX-004",
        model_version="fraud-v1.1",
        context_source="fresh",
    )], expected_version=-1)

    await store.append(stream_id, [_ev(
        "AgentNodeExecuted",
        node_name="run_transaction_analysis",
        llm_tokens_input=300,
        llm_tokens_output=50,
        llm_cost_usd=0.0005,
    )], expected_version=0)

    await store.append(stream_id, [_ev(
        "AgentSessionFailed",
        error_type="TimeoutError",
        error_message="LLM call timed out",
        recoverable=True,
        last_successful_node="run_transaction_analysis",
    )], expected_version=1)

    agg = await AgentSessionAggregate.load(store, "fraud_detection", "sess-gt-004")

    assert agg.status == SessionStatus.NEEDS_RECONCILIATION
    assert agg.is_crashed is True
    assert agg.error_type == "TimeoutError"
    assert agg.recoverable is True
    assert agg.last_successful_node == "run_transaction_analysis"


@pytest.mark.asyncio
async def test_non_recoverable_crash_sets_failed_status():
    """AgentSessionFailed with recoverable=False sets FAILED status."""
    store = InMemoryEventStore()
    stream_id = "agent-compliance-sess-gt-005"

    await store.append(stream_id, [_ev(
        "AgentSessionStarted",
        session_id="sess-gt-005",
        agent_type="compliance",
        agent_id="agent-003",
        application_id="APEX-005",
        model_version="compliance-v1.0",
        context_source="fresh",
    )], expected_version=-1)

    await store.append(stream_id, [_ev(
        "AgentSessionFailed",
        error_type="AuthorizationError",
        error_message="API key revoked",
        recoverable=False,
    )], expected_version=0)

    agg = await AgentSessionAggregate.load(store, "compliance", "sess-gt-005")
    assert agg.status == SessionStatus.FAILED
    assert agg.is_crashed is False  # not recoverable


# ── CRASH RECOVERY (Gas Town Pattern) ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_recovery_replays_completed_nodes():
    """
    After crash, a new session replays the stream and knows which nodes
    are already done — no duplicated work.
    """
    store = InMemoryEventStore()
    stream_id = "agent-credit_analysis-sess-gt-006"

    # Session crashes after completing node 1
    await store.append(stream_id, [_ev(
        "AgentSessionStarted",
        session_id="sess-gt-006",
        agent_type="credit_analysis",
        agent_id="agent-001",
        application_id="APEX-006",
        model_version="credit-v2.3",
        context_source="fresh",
    )], expected_version=-1)

    await store.append(stream_id, [_ev(
        "AgentNodeExecuted",
        node_name="load_financials",
        llm_tokens_input=500, llm_tokens_output=100, llm_cost_usd=0.001,
    )], expected_version=0)

    await store.append(stream_id, [_ev(
        "AgentSessionFailed",
        error_type="TimeoutError",
        recoverable=True,
        last_successful_node="load_financials",
    )], expected_version=1)

    # Recovery: replay stream
    agg = await AgentSessionAggregate.load(store, "credit_analysis", "sess-gt-006")
    assert agg.node_already_executed("load_financials") is True
    assert agg.node_already_executed("analyse_ratios") is False


@pytest.mark.asyncio
async def test_recovered_session_context_source_contains_prior_session_id():
    """
    After AgentSessionRecovered, context_source contains prior session reference.
    This is the NARR-03 test pattern.
    """
    store = InMemoryEventStore()
    stream_id = "agent-fraud_detection-sess-gt-007"

    await store.append(stream_id, [_ev(
        "AgentSessionStarted",
        session_id="sess-gt-007",
        agent_type="fraud_detection",
        agent_id="agent-002",
        application_id="APEX-007",
        model_version="fraud-v1.1",
        context_source="fresh",
    )], expected_version=-1)

    await store.append(stream_id, [_ev(
        "AgentSessionFailed",
        error_type="TimeoutError",
        recoverable=True,
        last_successful_node=None,
    )], expected_version=0)

    await store.append(stream_id, [_ev(
        "AgentSessionRecovered",
        recovered_from_session_id="sess-gt-007",
        recovery_point="start",
    )], expected_version=1)

    agg = await AgentSessionAggregate.load(store, "fraud_detection", "sess-gt-007")
    assert agg.status == SessionStatus.RECOVERED
    assert agg.is_active is True
    assert "prior_session_replay" in agg.context_source
    assert "sess-gt-007" in agg.context_source


# ── MODEL VERSION LOCKING ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_model_version_mismatch_raises():
    """Agent cannot switch model versions mid-session."""
    store = InMemoryEventStore()
    stream_id = "agent-credit_analysis-sess-gt-008"

    await store.append(stream_id, [_ev(
        "AgentSessionStarted",
        session_id="sess-gt-008",
        agent_type="credit_analysis",
        agent_id="agent-001",
        application_id="APEX-008",
        model_version="credit-v2.3.0",
        context_source="fresh",
    )], expected_version=-1)

    agg = await AgentSessionAggregate.load(store, "credit_analysis", "sess-gt-008")
    with pytest.raises(ValueError, match="mismatch"):
        agg.assert_model_version_consistent("credit-v2.4.0")


@pytest.mark.asyncio
async def test_same_model_version_passes():
    """Same model version mid-session is accepted."""
    store = InMemoryEventStore()
    stream_id = "agent-credit_analysis-sess-gt-009"

    await store.append(stream_id, [_ev(
        "AgentSessionStarted",
        session_id="sess-gt-009",
        agent_type="credit_analysis",
        agent_id="agent-001",
        application_id="APEX-009",
        model_version="credit-v2.3.0",
        context_source="fresh",
    )], expected_version=-1)

    agg = await AgentSessionAggregate.load(store, "credit_analysis", "sess-gt-009")
    agg.assert_model_version_consistent("credit-v2.3.0")  # must not raise


# ── CANNOT APPEND TO COMPLETED SESSION ────────────────────────────────────────

@pytest.mark.asyncio
async def test_completed_session_rejects_more_events():
    """AgentSessionCompleted is terminal — no more work can be appended."""
    store = InMemoryEventStore()
    stream_id = "agent-credit_analysis-sess-gt-010"

    await store.append(stream_id, [_ev(
        "AgentSessionStarted",
        session_id="sess-gt-010",
        agent_type="credit_analysis",
        agent_id="agent-001",
        application_id="APEX-010",
        model_version="credit-v2.3",
        context_source="fresh",
    )], expected_version=-1)

    await store.append(stream_id, [_ev(
        "AgentSessionCompleted",
        total_llm_calls=0,
        total_tokens_used=0,
        total_cost_usd=0.0,
    )], expected_version=0)

    agg = await AgentSessionAggregate.load(store, "credit_analysis", "sess-gt-010")
    assert agg.status == SessionStatus.COMPLETED
    with pytest.raises(ValueError, match="completed"):
        agg.assert_not_completed()


# ── TOKEN / COST ACCUMULATION ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_token_and_cost_accumulate_across_nodes():
    """Total tokens and cost accumulate correctly across multiple nodes."""
    store = InMemoryEventStore()
    stream_id = "agent-credit_analysis-sess-gt-011"

    await store.append(stream_id, [_ev(
        "AgentSessionStarted",
        session_id="sess-gt-011",
        agent_type="credit_analysis",
        agent_id="agent-001",
        application_id="APEX-011",
        model_version="credit-v2.3",
        context_source="fresh",
    )], expected_version=-1)

    await store.append(stream_id, [_ev(
        "AgentNodeExecuted",
        node_name="node_a",
        llm_tokens_input=400, llm_tokens_output=100, llm_cost_usd=0.0010,
    )], expected_version=0)

    await store.append(stream_id, [_ev(
        "AgentNodeExecuted",
        node_name="node_b",
        llm_tokens_input=600, llm_tokens_output=200, llm_cost_usd=0.0020,
    )], expected_version=1)

    agg = await AgentSessionAggregate.load(store, "credit_analysis", "sess-gt-011")

    assert agg.total_llm_calls == 2
    assert agg.total_tokens_used == 1300  # 400+100 + 600+200
    assert abs(agg.total_cost_usd - 0.0030) < 0.00001


# ── STREAM VERSION PROPERTY ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stream_version_matches_event_count():
    """stream_version property returns correct version for use in store.append()."""
    store = InMemoryEventStore()
    stream_id = "agent-credit_analysis-sess-gt-012"

    await store.append(stream_id, [_ev(
        "AgentSessionStarted",
        session_id="sess-gt-012",
        agent_type="credit_analysis",
        agent_id="agent-001",
        application_id="APEX-012",
        model_version="credit-v2.3",
        context_source="fresh",
    )], expected_version=-1)

    agg = await AgentSessionAggregate.load(store, "credit_analysis", "sess-gt-012")
    # Stream has 1 event (position 0), version is 0
    assert agg.stream_version == 0
    assert agg.stream_version == await store.stream_version(stream_id)
