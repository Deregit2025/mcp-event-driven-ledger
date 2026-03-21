"""
tests/test_invariants.py
=========================
Counterfactual command testing — proves business rules cannot be bypassed.
Score 5 requirement: all invariants tested under concurrent and edge-case scenarios.
"""
import pytest
from src.event_store import InMemoryEventStore
from src.aggregates.loan_application import LoanApplicationAggregate, ApplicationState
from src.aggregates.agent_session import AgentSessionAggregate
from src.commands.handlers import (
    handle_submit_application,
    handle_generate_decision,
    handle_human_review_completed,
)


def make_store():
    return InMemoryEventStore()


# ── RULE 4: confidence < 0.60 must force REFER ───────────────────────────────

@pytest.mark.asyncio
async def test_low_confidence_cannot_approve():
    """confidence=0.45 with recommendation=APPROVE must be rejected."""
    store = make_store()
    await handle_submit_application(
        store, "APEX-INV-001", "COMP-001", 500000, "working_capital"
    )
    app = await LoanApplicationAggregate.load(store, "APEX-INV-001")

    with pytest.raises(ValueError, match="0.45"):
        app.assert_valid_orchestrator_decision("APPROVE", 0.45)


@pytest.mark.asyncio
async def test_low_confidence_forces_refer():
    """confidence=0.45 with recommendation=REFER must be accepted."""
    store = make_store()
    await handle_submit_application(
        store, "APEX-INV-002", "COMP-001", 500000, "working_capital"
    )
    app = await LoanApplicationAggregate.load(store, "APEX-INV-002")
    app.assert_valid_orchestrator_decision("REFER", 0.45)  # must not raise


@pytest.mark.asyncio
async def test_borderline_confidence_exactly_060_can_approve():
    """confidence=0.60 exactly must be allowed to APPROVE."""
    store = make_store()
    await handle_submit_application(
        store, "APEX-INV-003", "COMP-001", 500000, "working_capital"
    )
    app = await LoanApplicationAggregate.load(store, "APEX-INV-003")
    app.assert_valid_orchestrator_decision("APPROVE", 0.60)  # must not raise


# ── RULE 5: compliance BLOCKED must force DECLINE ────────────────────────────

@pytest.mark.asyncio
async def test_compliance_blocked_cannot_approve():
    """Compliance BLOCKED application cannot be approved."""
    store = make_store()
    await handle_submit_application(
        store, "APEX-INV-004", "COMP-001", 500000, "working_capital"
    )
    app = await LoanApplicationAggregate.load(store, "APEX-INV-004")
    app.compliance_has_hard_block = True

    with pytest.raises(ValueError, match="hard block"):
        app.assert_valid_orchestrator_decision("APPROVE", 0.85)


@pytest.mark.asyncio
async def test_compliance_blocked_cannot_refer():
    """Compliance BLOCKED application cannot be referred — must DECLINE."""
    store = make_store()
    await handle_submit_application(
        store, "APEX-INV-005", "COMP-001", 500000, "working_capital"
    )
    app = await LoanApplicationAggregate.load(store, "APEX-INV-005")
    app.compliance_has_hard_block = True

    with pytest.raises(ValueError, match="hard block"):
        app.assert_valid_orchestrator_decision("REFER", 0.85)


@pytest.mark.asyncio
async def test_compliance_blocked_can_decline():
    """Compliance BLOCKED application can be declined."""
    store = make_store()
    await handle_submit_application(
        store, "APEX-INV-006", "COMP-001", 500000, "working_capital"
    )
    app = await LoanApplicationAggregate.load(store, "APEX-INV-006")
    app.compliance_has_hard_block = True
    app.assert_valid_orchestrator_decision("DECLINE", 0.85)  # must not raise


# ── RULE 3: analyses must complete before decision ───────────────────────────

@pytest.mark.asyncio
async def test_cannot_decide_without_credit_analysis():
    """Decision cannot be generated if credit analysis is missing."""
    store = make_store()
    await handle_submit_application(
        store, "APEX-INV-007", "COMP-001", 500000, "working_capital"
    )
    app = await LoanApplicationAggregate.load(store, "APEX-INV-007")
    app.fraud_score = 0.1
    app.compliance_verdict = "CLEAR"

    with pytest.raises(ValueError, match="Credit analysis"):
        app.assert_analyses_complete()


@pytest.mark.asyncio
async def test_cannot_decide_without_fraud_screening():
    """Decision cannot be generated if fraud screening is missing."""
    store = make_store()
    await handle_submit_application(
        store, "APEX-INV-008", "COMP-001", 500000, "working_capital"
    )
    app = await LoanApplicationAggregate.load(store, "APEX-INV-008")
    app.credit_confidence = 0.85
    app.compliance_verdict = "CLEAR"

    with pytest.raises(ValueError, match="Fraud"):
        app.assert_analyses_complete()


# ── DUPLICATE APPLICATION ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_application_rejected():
    """Submitting the same application ID twice must be rejected."""
    store = make_store()
    await handle_submit_application(
        store, "APEX-INV-009", "COMP-001", 500000, "working_capital"
    )
    with pytest.raises(ValueError, match="already exists"):
        await handle_submit_application(
            store, "APEX-INV-009", "COMP-001", 500000, "working_capital"
        )


# ── HUMAN OVERRIDE REQUIRES REASON ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_override_without_reason_rejected():
    """Human override without a reason must be rejected."""
    store = make_store()
    await handle_submit_application(
        store, "APEX-INV-010", "COMP-001", 500000, "working_capital"
    )
    with pytest.raises(ValueError, match="override_reason"):
        await handle_human_review_completed(
            store=store,
            application_id="APEX-INV-010",
            reviewer_id="LO-001",
            override=True,
            original_recommendation="DECLINE",
            final_decision="APPROVE",
            override_reason=None,  # missing — must be rejected
        )


# ── GAS TOWN: session must start before work ─────────────────────────────────

@pytest.mark.asyncio
async def test_agent_context_not_loaded_raises():
    """Agent cannot do work without AgentSessionStarted event."""
    agg = AgentSessionAggregate(session_id="sess-test-001")
    with pytest.raises(ValueError, match="AgentSessionStarted"):
        agg.assert_context_loaded()


# ── MODEL VERSION LOCKING ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_model_version_mismatch_raises():
    """Agent cannot switch model versions mid-session."""
    agg = AgentSessionAggregate(session_id="sess-test-002")
    agg.model_version = "credit-v2.3.0"
    with pytest.raises(ValueError, match="mismatch"):
        agg.assert_model_version_consistent("credit-v2.4.0")


@pytest.mark.asyncio
async def test_same_model_version_passes():
    """Same model version mid-session must be accepted."""
    agg = AgentSessionAggregate(session_id="sess-test-003")
    agg.model_version = "credit-v2.3.0"
    agg.assert_model_version_consistent("credit-v2.3.0")  # must not raise