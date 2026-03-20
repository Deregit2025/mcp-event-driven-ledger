"""
tests/test_concurrency.py
==========================
MANDATED TEST: Double-decision concurrency test.

Two concurrent asyncio tasks append to the same stream at expected_version=3.
Asserts:
  - Exactly one succeeds
  - One raises OptimisticConcurrencyError
  - Total stream length = 4
"""
import asyncio
import pytest
from src.event_store import EventStore, OptimisticConcurrencyError


def _ev(event_type: str, **payload) -> dict:
    return {"event_type": event_type, "event_version": 1, "payload": payload}


@pytest.mark.asyncio
async def test_double_decision_exactly_one_wins():
    """
    MANDATED TEST: Two concurrent CreditAnalysisAgents both try to append
    CreditAnalysisCompleted at expected_version=3. Exactly one must win.
    """
    from src.event_store import InMemoryEventStore
    store = InMemoryEventStore()

    # Build stream to version 3 (positions 0,1,2,3 = 4 events)
    await store.append("credit-APEX-0031", [_ev("CreditRecordOpened")],         expected_version=-1)
    await store.append("credit-APEX-0031", [_ev("HistoricalProfileConsumed")],   expected_version=0)
    await store.append("credit-APEX-0031", [_ev("ExtractedFactsConsumed")],      expected_version=1)
    await store.append("credit-APEX-0031", [_ev("SomeIntermediateEvent")],       expected_version=2)

    assert await store.stream_version("credit-APEX-0031") == 3

    results = []
    errors = []

    async def agent_attempt(agent_name: str):
        try:
            await store.append(
                "credit-APEX-0031",
                [_ev("CreditAnalysisCompleted",
                     agent=agent_name,
                     risk_tier="MEDIUM",
                     confidence=0.82)],
                expected_version=3,
            )
            results.append(f"{agent_name}:success")
        except OptimisticConcurrencyError as e:
            errors.append(f"{agent_name}:occ:{e.expected}:{e.actual}")

    # Fire both agents simultaneously
    await asyncio.gather(
        agent_attempt("agent-A"),
        agent_attempt("agent-B"),
    )

    # Exactly one must succeed
    assert len(results) == 1, (
        f"Expected exactly 1 success, got {len(results)}: {results}"
    )

    # Exactly one must get OCC error
    assert len(errors) == 1, (
        f"Expected exactly 1 OCC error, got {len(errors)}: {errors}"
    )

    # Stream must have exactly 5 events (positions 0-4)
    events = await store.load_stream("credit-APEX-0031")
    assert len(events) == 5, (
        f"Expected 5 total events, got {len(events)}"
    )

    # Final version must be 4
    final_version = await store.stream_version("credit-APEX-0031")
    assert final_version == 4, (
        f"Expected final version 4, got {final_version}"
    )

    # The last event must be CreditAnalysisCompleted
    assert events[-1]["event_type"] == "CreditAnalysisCompleted"


@pytest.mark.asyncio
async def test_concurrent_appends_to_different_streams_both_succeed():
    """
    Two agents on DIFFERENT streams must never interfere with each other.
    Both appends should succeed.
    """
    from src.event_store import InMemoryEventStore
    store = InMemoryEventStore()

    results = []

    async def append_to_stream(stream_id: str):
        await store.append(stream_id, [_ev("Event")], expected_version=-1)
        results.append(stream_id)

    await asyncio.gather(
        append_to_stream("credit-APEX-0001"),
        append_to_stream("credit-APEX-0002"),
    )

    assert len(results) == 2
    assert await store.stream_version("credit-APEX-0001") == 0
    assert await store.stream_version("credit-APEX-0002") == 0


@pytest.mark.asyncio
async def test_five_concurrent_appends_exactly_one_wins():
    """
    Five agents simultaneously attempt the same append.
    Exactly one must win; four must get OCC errors.
    """
    from src.event_store import InMemoryEventStore
    store = InMemoryEventStore()

    await store.append("loan-APEX-TEST", [_ev("ApplicationSubmitted")], expected_version=-1)

    successes = []
    occ_errors = []

    async def attempt(i: int):
        try:
            await store.append(
                "loan-APEX-TEST",
                [_ev("DecisionGenerated", agent=f"agent-{i}")],
                expected_version=0,
            )
            successes.append(i)
        except OptimisticConcurrencyError:
            occ_errors.append(i)

    await asyncio.gather(*[attempt(i) for i in range(5)])

    assert len(successes) == 1, f"Expected 1 success, got {successes}"
    assert len(occ_errors) == 4, f"Expected 4 OCC errors, got {occ_errors}"
    assert await store.stream_version("loan-APEX-TEST") == 1


@pytest.mark.asyncio
async def test_occ_error_contains_correct_versions():
    """
    OptimisticConcurrencyError must contain stream_id, expected, and actual versions.
    These are used by agents to understand what happened.
    """
    from src.event_store import InMemoryEventStore
    store = InMemoryEventStore()

    await store.append("loan-APEX-ERR", [_ev("E1")], expected_version=-1)
    await store.append("loan-APEX-ERR", [_ev("E2")], expected_version=0)

    with pytest.raises(OptimisticConcurrencyError) as exc_info:
        await store.append("loan-APEX-ERR", [_ev("E3")], expected_version=0)

    err = exc_info.value
    assert err.stream_id == "loan-APEX-ERR"
    assert err.expected == 0
    assert err.actual == 1