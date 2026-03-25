"""
tests/test_upcasting.py
========================
Tests for UpcasterRegistry and the two required upcasters:
  - CreditAnalysisCompleted v1 → v2
  - DecisionGenerated        v1 → v2

All tests use InMemoryEventStore — no database required.
"""
import pytest
from src.upcasting.registry import UpcasterRegistry
from src.upcasting.upcasters import registry


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _make_event(event_type: str, version: int, **payload) -> dict:
    return {
        "event_type": event_type,
        "event_version": version,
        "payload": payload,
    }


# ── UPCASTER REGISTRY ────────────────────────────────────────────────────────

def test_registry_registered_types():
    """Both required event types are registered."""
    types = registry.registered_types()
    assert "CreditAnalysisCompleted" in types
    assert "DecisionGenerated" in types


def test_registry_no_upcaster_passthrough():
    """Event with no registered upcaster passes through unchanged."""
    event = _make_event("ApplicationSubmitted", 1, application_id="APEX-001")
    result = registry.upcast(dict(event))
    assert result["event_type"] == "ApplicationSubmitted"
    assert result["event_version"] == 1


def test_registry_already_current_version_unchanged():
    """An event already at v2 is not re-upcasted."""
    event = _make_event(
        "CreditAnalysisCompleted", 2,
        application_id="APEX-001",
        model_versions={"credit_analysis": "credit-v2.3"},
        regulatory_basis=["APRA-2026-Q1"],
    )
    result = registry.upcast(dict(event))
    assert result["event_version"] == 2
    # model_versions must be unchanged
    assert result["payload"]["model_versions"] == {"credit_analysis": "credit-v2.3"}


# ── IMMUTABILITY ──────────────────────────────────────────────────────────────

def test_upcaster_does_not_mutate_original_event():
    """upcast() must never mutate the original event dict."""
    original = _make_event(
        "CreditAnalysisCompleted", 1,
        application_id="APEX-IMM-001",
        decision={"confidence": 0.80, "risk_tier": "MEDIUM"},
    )
    original_payload_id = id(original["payload"])
    _ = registry.upcast(dict(original))
    # Original payload object must not have been modified
    assert "model_versions" not in original["payload"]
    assert original["event_version"] == 1


def test_upcaster_does_not_mutate_original_payload():
    """The payload dict passed to the upcaster is copied, never mutated."""
    payload = {
        "application_id": "APEX-IMM-002",
        "decision": {"confidence": 0.72},
    }
    event = {"event_type": "CreditAnalysisCompleted", "event_version": 1, "payload": payload}
    registry.upcast(dict(event))
    # Original payload must still lack model_versions
    assert "model_versions" not in payload


# ── CreditAnalysisCompleted v1 → v2 ──────────────────────────────────────────

def test_credit_analysis_v1_to_v2_version_bumped():
    """Event version is incremented from 1 to 2."""
    event = _make_event("CreditAnalysisCompleted", 1, application_id="APEX-001")
    result = registry.upcast(event)
    assert result["event_version"] == 2


def test_credit_analysis_v1_to_v2_model_versions_dict_created():
    """model_versions dict is created from old model_version string."""
    event = _make_event(
        "CreditAnalysisCompleted", 1,
        application_id="APEX-001",
        model_version="credit-v2.3.0",
    )
    result = registry.upcast(event)
    mv = result["payload"]["model_versions"]
    assert isinstance(mv, dict)
    assert mv.get("credit_analysis") == "credit-v2.3.0"


def test_credit_analysis_v1_no_model_version_uses_sentinel():
    """Missing model_version uses 'legacy-pre-2026' sentinel."""
    event = _make_event("CreditAnalysisCompleted", 1, application_id="APEX-002")
    result = registry.upcast(event)
    mv = result["payload"]["model_versions"]
    assert mv.get("credit_analysis") == "legacy-pre-2026"


def test_credit_analysis_v1_regulatory_basis_inferred():
    """regulatory_basis is added with '-inferred' suffix."""
    event = _make_event("CreditAnalysisCompleted", 1, application_id="APEX-003")
    result = registry.upcast(event)
    rb = result["payload"]["regulatory_basis"]
    assert isinstance(rb, list)
    assert any("inferred" in v for v in rb)


def test_credit_analysis_v1_confidence_score_null():
    """confidence_score must NOT be fabricated — left as None/absent."""
    event = _make_event("CreditAnalysisCompleted", 1, application_id="APEX-004")
    result = registry.upcast(event)
    # confidence_score either absent or explicitly None — never fabricated
    payload = result["payload"]
    assert payload.get("confidence_score") is None or "confidence_score" not in payload


def test_credit_analysis_v1_existing_model_versions_not_overwritten():
    """If model_versions is already present, it is not overwritten."""
    event = _make_event(
        "CreditAnalysisCompleted", 1,
        application_id="APEX-005",
        model_versions={"credit_analysis": "already-set"},
    )
    result = registry.upcast(event)
    assert result["payload"]["model_versions"]["credit_analysis"] == "already-set"


def test_credit_analysis_v1_existing_regulatory_basis_not_overwritten():
    """If regulatory_basis is already present, it is not overwritten."""
    event = _make_event(
        "CreditAnalysisCompleted", 1,
        application_id="APEX-006",
        regulatory_basis=["APRA-2026-Q1"],
    )
    result = registry.upcast(event)
    assert result["payload"]["regulatory_basis"] == ["APRA-2026-Q1"]


# ── DecisionGenerated v1 → v2 ─────────────────────────────────────────────────

def test_decision_generated_v1_to_v2_version_bumped():
    """Event version is incremented from 1 to 2."""
    event = _make_event("DecisionGenerated", 1, application_id="APEX-001")
    result = registry.upcast(event)
    assert result["event_version"] == 2


def test_decision_generated_v1_with_contributing_sessions_uses_lookup_sentinel():
    """If contributing_sessions present, model_versions uses _requires_lookup sentinel."""
    event = _make_event(
        "DecisionGenerated", 1,
        application_id="APEX-001",
        contributing_sessions=["sess-001", "sess-002"],
    )
    result = registry.upcast(event)
    mv = result["payload"]["model_versions"]
    assert "_requires_lookup" in mv
    assert "sess-001" in mv["_requires_lookup"]
    assert "sess-002" in mv["_requires_lookup"]


def test_decision_generated_v1_no_contributing_sessions_uses_legacy_sentinel():
    """Without contributing_sessions, model_versions uses 'legacy-pre-2026'."""
    event = _make_event("DecisionGenerated", 1, application_id="APEX-002")
    result = registry.upcast(event)
    mv = result["payload"]["model_versions"]
    assert "orchestrator" in mv
    assert mv["orchestrator"] == "legacy-pre-2026"


def test_decision_generated_v1_existing_model_versions_not_overwritten():
    """If model_versions already present in v1 payload, not overwritten."""
    event = _make_event(
        "DecisionGenerated", 1,
        application_id="APEX-003",
        model_versions={"orchestrator": "orch-v1.0"},
    )
    result = registry.upcast(event)
    assert result["payload"]["model_versions"]["orchestrator"] == "orch-v1.0"


# ── CHAIN UPCASTING ───────────────────────────────────────────────────────────

def test_chain_upcasting_applies_multiple_in_sequence():
    """
    A registry with two chained upcasters (v1→v2, v2→v3) applies both.
    """
    r = UpcasterRegistry()

    @r.upcaster("TestEvent", from_version=1, to_version=2)
    def step1(payload):
        payload = dict(payload)
        payload["field_a"] = "added_by_v1_to_v2"
        return payload

    @r.upcaster("TestEvent", from_version=2, to_version=3)
    def step2(payload):
        payload = dict(payload)
        payload["field_b"] = "added_by_v2_to_v3"
        return payload

    event = {"event_type": "TestEvent", "event_version": 1, "payload": {}}
    result = r.upcast(event)

    assert result["event_version"] == 3
    assert result["payload"]["field_a"] == "added_by_v1_to_v2"
    assert result["payload"]["field_b"] == "added_by_v2_to_v3"


def test_chain_starts_from_stored_version():
    """If event is at v2, only v2→v3 upcaster runs, not v1→v2."""
    r = UpcasterRegistry()
    calls = []

    @r.upcaster("TestEvent", from_version=1, to_version=2)
    def step1(payload):
        calls.append("v1_to_v2")
        return payload

    @r.upcaster("TestEvent", from_version=2, to_version=3)
    def step2(payload):
        calls.append("v2_to_v3")
        return payload

    event = {"event_type": "TestEvent", "event_version": 2, "payload": {}}
    r.upcast(event)

    assert "v1_to_v2" not in calls
    assert "v2_to_v3" in calls


# ── INTEGRATION: EventStore applies upcasters on load ────────────────────────

@pytest.mark.asyncio
async def test_event_store_applies_upcasters_on_load_stream():
    """
    InMemoryEventStore with a upcaster_registry applies upcasters
    when load_stream() is called — stored v1 comes back as v2.
    """
    from src.event_store import InMemoryEventStore

    store = InMemoryEventStore(upcaster_registry=registry)

    # Store a v1 CreditAnalysisCompleted
    await store.append(
        "credit-APEX-UC-001",
        [{
            "event_type": "CreditAnalysisCompleted",
            "event_version": 1,
            "payload": {
                "application_id": "APEX-UC-001",
                "model_version": "credit-v2.3.0",
            },
        }],
        expected_version=-1,
    )

    events = await store.load_stream("credit-APEX-UC-001")
    assert len(events) == 1
    e = events[0]

    # Must come back as v2
    assert e["event_version"] == 2
    assert "model_versions" in e["payload"]
    assert e["payload"]["model_versions"]["credit_analysis"] == "credit-v2.3.0"


@pytest.mark.asyncio
async def test_event_store_stored_row_not_modified():
    """
    The raw event appended to InMemoryEventStore must remain at v1.
    Upcasting is a read-time transformation — never writes back.
    """
    from src.event_store import InMemoryEventStore

    store = InMemoryEventStore(upcaster_registry=registry)

    v1_event = {
        "event_type": "CreditAnalysisCompleted",
        "event_version": 1,
        "payload": {"application_id": "APEX-UC-002"},
    }

    await store.append("credit-APEX-UC-002", [v1_event], expected_version=-1)

    # Load without upcaster to verify the stored row is still v1
    raw_store = InMemoryEventStore()  # no registry
    # Copy internal storage for inspection
    raw_events = store._streams["credit-APEX-UC-002"]
    assert raw_events[0]["event_version"] == 1  # stored as v1 — immutable
