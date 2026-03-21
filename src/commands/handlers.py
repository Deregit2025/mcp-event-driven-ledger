"""
src/commands/handlers.py
=========================
Command handlers — load → validate → determine → append pattern.

Each handler:
  1. Loads the aggregate from the event store
  2. Validates business rules against current state
  3. Determines which events to append
  4. Appends them atomically via the event store

Handlers never talk directly to agents or projections.
They are the write side of CQRS.
"""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal

from schema.events import (
    ApplicationSubmitted,
    DocumentUploadRequested,
    CreditAnalysisRequested,
    FraudScreeningRequested,
    ComplianceCheckRequested,
    DecisionRequested,
    DecisionGenerated,
    HumanReviewRequested,
    HumanReviewCompleted,
    ApplicationApproved,
    ApplicationDeclined,
    AgentSessionStarted,
    AgentType,
    LoanPurpose,
    DocumentType,
)
from src.aggregates.loan_application import (
    LoanApplicationAggregate,
    ApplicationState,
)
from src.aggregates.agent_session import AgentSessionAggregate


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── SUBMIT APPLICATION ────────────────────────────────────────────────────────

async def handle_submit_application(
    store,
    application_id: str,
    applicant_id: str,
    requested_amount_usd: float,
    loan_purpose: str,
    loan_term_months: int = 60,
    submission_channel: str = "web",
    contact_email: str = "",
    contact_name: str = "",
    application_reference: str = "",
) -> str:
    """
    Submit a new loan application.
    Creates the loan-{application_id} stream.
    Returns stream_id.
    """
    # Check stream does not already exist
    ver = await store.stream_version(f"loan-{application_id}")
    if ver != -1:
        raise ValueError(
            f"Application {application_id} already exists at version {ver}."
        )

    event = ApplicationSubmitted(
        application_id=application_id,
        applicant_id=applicant_id,
        requested_amount_usd=Decimal(str(requested_amount_usd)),
        loan_purpose=LoanPurpose(loan_purpose),
        loan_term_months=loan_term_months,
        submission_channel=submission_channel,
        contact_email=contact_email,
        contact_name=contact_name,
        submitted_at=_now(),
        application_reference=application_reference or application_id,
    ).to_store_dict()

    await store.append(
        stream_id=f"loan-{application_id}",
        events=[event],
        expected_version=-1,
    )
    return f"loan-{application_id}"


# ── START AGENT SESSION ───────────────────────────────────────────────────────

async def handle_start_agent_session(
    store,
    agent_type: str,
    session_id: str,
    agent_id: str,
    application_id: str,
    model_version: str,
    context_source: str = "fresh",
    context_token_count: int = 0,
    langgraph_graph_version: str = "1.0.0",
) -> str:
    """
    Start an agent session — Gas Town anchor.
    Writes AgentSessionStarted as the very first event.
    Returns stream_id.
    """
    stream_id = f"agent-{agent_type}-{session_id}"
    ver = await store.stream_version(stream_id)
    if ver != -1:
        raise ValueError(
            f"Session {session_id} already exists on stream {stream_id}."
        )

    event = AgentSessionStarted(
        session_id=session_id,
        agent_type=AgentType(agent_type),
        agent_id=agent_id,
        application_id=application_id,
        model_version=model_version,
        langgraph_graph_version=langgraph_graph_version,
        context_source=context_source,
        context_token_count=context_token_count,
        started_at=_now(),
    ).to_store_dict()

    await store.append(
        stream_id=stream_id,
        events=[event],
        expected_version=-1,
    )
    return stream_id


# ── REQUEST DOCUMENT UPLOAD ───────────────────────────────────────────────────

async def handle_request_document_upload(
    store,
    application_id: str,
    required_document_types: list[str] | None = None,
    requested_by: str = "system",
) -> None:
    """Request documents from the applicant after submission."""
    app = await LoanApplicationAggregate.load(store, application_id)
    app.assert_valid_transition(ApplicationState.DOCUMENTS_PENDING)

    doc_types = [DocumentType(d) for d in (required_document_types or [
        "income_statement", "balance_sheet", "application_proposal"
    ])]

    from schema.events import DocumentUploadRequested
    event = DocumentUploadRequested(
        application_id=application_id,
        required_document_types=doc_types,
        deadline=_now(),
        requested_by=requested_by,
    ).to_store_dict()

    await store.append(
        stream_id=f"loan-{application_id}",
        events=[event],
        expected_version=app.version,
    )


# ── CREDIT ANALYSIS COMPLETED ─────────────────────────────────────────────────

async def handle_credit_analysis_completed(
    store,
    application_id: str,
    session_id: str,
    risk_tier: str,
    recommended_limit_usd: float,
    confidence: float,
    rationale: str,
    model_version: str,
    key_concerns: list[str] | None = None,
    data_quality_caveats: list[str] | None = None,
    policy_overrides: list[str] | None = None,
) -> None:
    """
    Record that a CreditAnalysisAgent has completed its analysis.
    Validates confidence floor — confidence < 0.60 forces REFER later.
    """
    from schema.events import CreditAnalysisCompleted, CreditDecision, RiskTier
    app = await LoanApplicationAggregate.load(store, application_id)

    decision = CreditDecision(
        risk_tier=RiskTier(risk_tier),
        recommended_limit_usd=Decimal(str(recommended_limit_usd)),
        confidence=confidence,
        rationale=rationale,
        key_concerns=key_concerns or [],
        data_quality_caveats=data_quality_caveats or [],
        policy_overrides_applied=policy_overrides or [],
    )

    import hashlib, json
    input_hash = hashlib.sha256(
        json.dumps({"app": application_id, "session": session_id}, sort_keys=True).encode()
    ).hexdigest()[:16]

    event = CreditAnalysisCompleted(
        application_id=application_id,
        session_id=session_id,
        decision=decision,
        model_version=model_version,
        model_deployment_id=f"dep-{session_id[:8]}",
        input_data_hash=input_hash,
        analysis_duration_ms=0,
        completed_at=_now(),
    ).to_store_dict()

    credit_ver = await store.stream_version(f"credit-{application_id}")
    await store.append(
        stream_id=f"credit-{application_id}",
        events=[event],
        expected_version=credit_ver,
        causation_id=session_id,
    )


# ── FRAUD SCREENING COMPLETED ─────────────────────────────────────────────────

async def handle_fraud_screening_completed(
    store,
    application_id: str,
    session_id: str,
    fraud_score: float,
    risk_level: str,
    recommendation: str,
    screening_model_version: str,
    anomalies_found: int = 0,
) -> None:
    """Record FraudDetectionAgent completing its screening."""
    from schema.events import FraudScreeningCompleted
    import hashlib, json

    input_hash = hashlib.sha256(
        json.dumps({"app": application_id, "session": session_id}).encode()
    ).hexdigest()[:16]

    event = FraudScreeningCompleted(
        application_id=application_id,
        session_id=session_id,
        fraud_score=fraud_score,
        risk_level=risk_level,
        anomalies_found=anomalies_found,
        recommendation=recommendation,
        screening_model_version=screening_model_version,
        input_data_hash=input_hash,
        completed_at=_now(),
    ).to_store_dict()

    fraud_ver = await store.stream_version(f"fraud-{application_id}")
    await store.append(
        stream_id=f"fraud-{application_id}",
        events=[event],
        expected_version=fraud_ver,
        causation_id=session_id,
    )


# ── COMPLIANCE CHECK COMPLETED ────────────────────────────────────────────────

async def handle_compliance_check(
    store,
    application_id: str,
    session_id: str,
    rules_evaluated: int,
    rules_passed: int,
    rules_failed: int,
    rules_noted: int,
    has_hard_block: bool,
    overall_verdict: str,
) -> None:
    """Record ComplianceAgent completing its rule evaluation."""
    from schema.events import ComplianceCheckCompleted, ComplianceVerdict

    event = ComplianceCheckCompleted(
        application_id=application_id,
        session_id=session_id,
        rules_evaluated=rules_evaluated,
        rules_passed=rules_passed,
        rules_failed=rules_failed,
        rules_noted=rules_noted,
        has_hard_block=has_hard_block,
        overall_verdict=ComplianceVerdict(overall_verdict),
        completed_at=_now(),
    ).to_store_dict()

    compliance_ver = await store.stream_version(f"compliance-{application_id}")
    await store.append(
        stream_id=f"compliance-{application_id}",
        events=[event],
        expected_version=compliance_ver,
    )


# ── GENERATE DECISION ─────────────────────────────────────────────────────────

async def handle_generate_decision(
    store,
    application_id: str,
    orchestrator_session_id: str,
    recommendation: str,
    confidence: float,
    executive_summary: str,
    key_risks: list[str] | None = None,
    approved_amount_usd: float | None = None,
    conditions: list[str] | None = None,
    contributing_sessions: list[str] | None = None,
    model_versions: dict | None = None,
) -> None:
    """
    Generate the final orchestrator decision.
    Enforces business rules:
      - confidence < 0.60 → must be REFER
      - compliance BLOCKED → must be DECLINE
    """
    app = await LoanApplicationAggregate.load(store, application_id)
    app.assert_analyses_complete()
    app.assert_valid_orchestrator_decision(recommendation, confidence)

    event = DecisionGenerated(
        application_id=application_id,
        orchestrator_session_id=orchestrator_session_id,
        recommendation=recommendation,
        confidence=confidence,
        approved_amount_usd=(
            Decimal(str(approved_amount_usd))
            if approved_amount_usd else None
        ),
        conditions=conditions or [],
        executive_summary=executive_summary,
        key_risks=key_risks or [],
        contributing_sessions=contributing_sessions or [],
        model_versions=model_versions or {},
        generated_at=_now(),
    ).to_store_dict()

    await store.append(
        stream_id=f"loan-{application_id}",
        events=[event],
        expected_version=app.version,
        causation_id=orchestrator_session_id,
    )


# ── HUMAN REVIEW COMPLETED ────────────────────────────────────────────────────

async def handle_human_review_completed(
    store,
    application_id: str,
    reviewer_id: str,
    override: bool,
    original_recommendation: str,
    final_decision: str,
    override_reason: str | None = None,
    approved_amount_usd: float | None = None,
    interest_rate_pct: float = 5.0,
    term_months: int = 60,
    conditions: list[str] | None = None,
    decline_reasons: list[str] | None = None,
) -> None:
    """
    Record a human loan officer's review decision.
    If override=True, override_reason is required.
    Appends HumanReviewCompleted + ApplicationApproved or ApplicationDeclined.
    """
    if override and not override_reason:
        raise ValueError(
            "override_reason is required when override=True. "
            "The loan officer must justify overriding the AI recommendation."
        )

    app = await LoanApplicationAggregate.load(store, application_id)

    review_event = HumanReviewCompleted(
        application_id=application_id,
        reviewer_id=reviewer_id,
        override=override,
        original_recommendation=original_recommendation,
        final_decision=final_decision,
        override_reason=override_reason,
        reviewed_at=_now(),
    ).to_store_dict()

    events = [review_event]

    if final_decision == "APPROVE":
        approve_event = ApplicationApproved(
            application_id=application_id,
            approved_amount_usd=Decimal(str(
                approved_amount_usd or app.requested_amount_usd or 0
            )),
            interest_rate_pct=interest_rate_pct,
            term_months=term_months,
            conditions=conditions or [],
            approved_by=reviewer_id,
            effective_date=_now().date().isoformat(),
            approved_at=_now(),
        ).to_store_dict()
        events.append(approve_event)

    elif final_decision == "DECLINE":
        decline_event = ApplicationDeclined(
            application_id=application_id,
            decline_reasons=decline_reasons or ["Declined by loan officer review"],
            declined_by=reviewer_id,
            adverse_action_notice_required=True,
            declined_at=_now(),
        ).to_store_dict()
        events.append(decline_event)

    await store.append(
        stream_id=f"loan-{application_id}",
        events=events,
        expected_version=app.version,
    )