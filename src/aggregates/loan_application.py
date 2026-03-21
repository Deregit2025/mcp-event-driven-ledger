"""
src/aggregates/loan_application.py
===================================
LoanApplicationAggregate — full implementation.

apply() dispatches to per-event handler methods (_apply_*).
Invalid transitions raise DomainError subclasses — not generic exceptions.
stream_version property exposes the precise version for handlers to use.

BUSINESS RULES ENFORCED:
  1. State machine — only valid transitions allowed
  2. Documents must be processed before credit analysis
  3. Model version locking — one CreditAnalysisCompleted unless overridden
  4. confidence < 0.60 → recommendation must be REFER
  5. Compliance BLOCKED → only DECLINE allowed
  6. Causal chain — contributing sessions must be valid
"""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
import re


# ── STATE MACHINE ─────────────────────────────────────────────────────────────

class ApplicationState(str, Enum):
    NEW = "NEW"
    SUBMITTED = "SUBMITTED"
    DOCUMENTS_PENDING = "DOCUMENTS_PENDING"
    DOCUMENTS_UPLOADED = "DOCUMENTS_UPLOADED"
    DOCUMENTS_PROCESSED = "DOCUMENTS_PROCESSED"
    CREDIT_ANALYSIS_REQUESTED = "CREDIT_ANALYSIS_REQUESTED"
    CREDIT_ANALYSIS_COMPLETE = "CREDIT_ANALYSIS_COMPLETE"
    FRAUD_SCREENING_REQUESTED = "FRAUD_SCREENING_REQUESTED"
    FRAUD_SCREENING_COMPLETE = "FRAUD_SCREENING_COMPLETE"
    COMPLIANCE_CHECK_REQUESTED = "COMPLIANCE_CHECK_REQUESTED"
    COMPLIANCE_CHECK_COMPLETE = "COMPLIANCE_CHECK_COMPLETE"
    PENDING_DECISION = "PENDING_DECISION"
    PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    DECLINED_COMPLIANCE = "DECLINED_COMPLIANCE"
    REFERRED = "REFERRED"


VALID_TRANSITIONS: dict[ApplicationState, list[ApplicationState]] = {
    ApplicationState.NEW: [ApplicationState.SUBMITTED],
    ApplicationState.SUBMITTED: [ApplicationState.DOCUMENTS_PENDING],
    ApplicationState.DOCUMENTS_PENDING: [ApplicationState.DOCUMENTS_UPLOADED],
    ApplicationState.DOCUMENTS_UPLOADED: [ApplicationState.DOCUMENTS_PROCESSED],
    ApplicationState.DOCUMENTS_PROCESSED: [ApplicationState.CREDIT_ANALYSIS_REQUESTED],
    ApplicationState.CREDIT_ANALYSIS_REQUESTED: [ApplicationState.CREDIT_ANALYSIS_COMPLETE],
    ApplicationState.CREDIT_ANALYSIS_COMPLETE: [ApplicationState.FRAUD_SCREENING_REQUESTED],
    ApplicationState.FRAUD_SCREENING_REQUESTED: [ApplicationState.FRAUD_SCREENING_COMPLETE],
    ApplicationState.FRAUD_SCREENING_COMPLETE: [ApplicationState.COMPLIANCE_CHECK_REQUESTED],
    ApplicationState.COMPLIANCE_CHECK_REQUESTED: [
        ApplicationState.COMPLIANCE_CHECK_COMPLETE,
        ApplicationState.DECLINED_COMPLIANCE,
    ],
    ApplicationState.COMPLIANCE_CHECK_COMPLETE: [
        ApplicationState.PENDING_DECISION,
        ApplicationState.DECLINED_COMPLIANCE,
    ],
    ApplicationState.PENDING_DECISION: [
        ApplicationState.APPROVED,
        ApplicationState.DECLINED,
        ApplicationState.PENDING_HUMAN_REVIEW,
    ],
    ApplicationState.PENDING_HUMAN_REVIEW: [
        ApplicationState.APPROVED,
        ApplicationState.DECLINED,
        ApplicationState.REFERRED,
    ],
    ApplicationState.APPROVED: [],
    ApplicationState.DECLINED: [],
    ApplicationState.DECLINED_COMPLIANCE: [],
    ApplicationState.REFERRED: [],
}

TERMINAL_STATES = {
    ApplicationState.APPROVED,
    ApplicationState.DECLINED,
    ApplicationState.DECLINED_COMPLIANCE,
    ApplicationState.REFERRED,
}


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _to_snake(event_type: str) -> str:
    """CamelCase → snake_case. e.g. ApplicationSubmitted → application_submitted"""
    return re.sub(r'(?<!^)(?=[A-Z])', '_', event_type).lower()


# ── AGGREGATE ─────────────────────────────────────────────────────────────────

@dataclass
class LoanApplicationAggregate:
    application_id: str
    state: ApplicationState = ApplicationState.NEW
    applicant_id: str | None = None
    requested_amount_usd: Decimal | None = None
    loan_purpose: str | None = None
    submission_channel: str | None = None
    credit_confidence: float | None = None
    credit_risk_tier: str | None = None
    fraud_score: float | None = None
    compliance_verdict: str | None = None
    compliance_has_hard_block: bool = False
    has_credit_analysis: bool = False
    analysis_overridden: bool = False
    valid_session_ids: set = field(default_factory=set)
    contributing_agent_sessions: list = field(default_factory=list)
    documents_uploaded: list = field(default_factory=list)
    document_package_ready: bool = False
    approved_amount: float | None = None
    version: int = -1

    # ── LOAD ──────────────────────────────────────────────────────────────────

    @classmethod
    async def load(cls, store, application_id: str) -> "LoanApplicationAggregate":
        """Load and replay event stream to rebuild aggregate state."""
        agg = cls(application_id=application_id)
        stream_events = await store.load_stream(f"loan-{application_id}")
        for event in stream_events:
            agg.apply(event)
        return agg

    # ── DISPATCHER ────────────────────────────────────────────────────────────

    def apply(self, event: dict) -> None:
        """
        Dispatch to per-event handler method.
        Unknown event types silently ignored — forward compatibility.
        """
        et = event.get("event_type", "")
        self.version += 1
        handler = getattr(self, f"_apply_{_to_snake(et)}", None)
        if handler:
            handler(event.get("payload", {}))

    # ── PER-EVENT HANDLERS ────────────────────────────────────────────────────

    def _apply_application_submitted(self, p: dict) -> None:
        self.state = ApplicationState.SUBMITTED
        self.applicant_id = p.get("applicant_id")
        self.requested_amount_usd = (
            Decimal(str(p["requested_amount_usd"]))
            if p.get("requested_amount_usd") is not None else None
        )
        self.loan_purpose = p.get("loan_purpose")
        self.submission_channel = p.get("submission_channel")

    def _apply_document_upload_requested(self, p: dict) -> None:
        self.state = ApplicationState.DOCUMENTS_PENDING

    def _apply_document_uploaded(self, p: dict) -> None:
        self.state = ApplicationState.DOCUMENTS_UPLOADED
        doc_id = p.get("document_id")
        if doc_id and doc_id not in self.documents_uploaded:
            self.documents_uploaded.append(doc_id)

    def _apply_document_upload_failed(self, p: dict) -> None:
        pass

    def _apply_package_ready_for_analysis(self, p: dict) -> None:
        self.document_package_ready = True
        self.state = ApplicationState.DOCUMENTS_PROCESSED

    def _apply_credit_analysis_requested(self, p: dict) -> None:
        self.state = ApplicationState.CREDIT_ANALYSIS_REQUESTED
        agent_id = p.get("assigned_agent_id", "")
        if agent_id:
            self.valid_session_ids.add(agent_id)

    def _apply_credit_analysis_completed(self, p: dict) -> None:
        self.state = ApplicationState.CREDIT_ANALYSIS_COMPLETE
        self.has_credit_analysis = True
        decision = p.get("decision", {})
        if isinstance(decision, dict):
            self.credit_confidence = decision.get("confidence")
            self.credit_risk_tier = decision.get("risk_tier")
        session_id = p.get("session_id", "")
        if session_id:
            self.valid_session_ids.add(session_id)

    def _apply_credit_analysis_deferred(self, p: dict) -> None:
        self.state = ApplicationState.CREDIT_ANALYSIS_COMPLETE

    def _apply_fraud_screening_requested(self, p: dict) -> None:
        self.state = ApplicationState.FRAUD_SCREENING_REQUESTED
        agent_id = p.get("assigned_agent_id", "")
        if agent_id:
            self.valid_session_ids.add(agent_id)

    def _apply_fraud_screening_completed(self, p: dict) -> None:
        self.state = ApplicationState.FRAUD_SCREENING_COMPLETE
        self.fraud_score = p.get("fraud_score")
        session_id = p.get("session_id", "")
        if session_id:
            self.valid_session_ids.add(session_id)

    def _apply_compliance_check_requested(self, p: dict) -> None:
        self.state = ApplicationState.COMPLIANCE_CHECK_REQUESTED

    def _apply_compliance_check_completed(self, p: dict) -> None:
        self.state = ApplicationState.COMPLIANCE_CHECK_COMPLETE
        self.compliance_verdict = p.get("overall_verdict")
        self.compliance_has_hard_block = p.get("has_hard_block", False)

    def _apply_decision_requested(self, p: dict) -> None:
        self.state = ApplicationState.PENDING_DECISION

    def _apply_decision_generated(self, p: dict) -> None:
        self.contributing_agent_sessions = p.get("contributing_sessions", [])
        if p.get("recommendation") == "REFER":
            self.state = ApplicationState.PENDING_HUMAN_REVIEW

    def _apply_human_review_requested(self, p: dict) -> None:
        self.state = ApplicationState.PENDING_HUMAN_REVIEW

    def _apply_human_review_completed(self, p: dict) -> None:
        pass

    def _apply_human_review_override(self, p: dict) -> None:
        self.analysis_overridden = True
        self.has_credit_analysis = False

    def _apply_application_approved(self, p: dict) -> None:
        self.state = ApplicationState.APPROVED
        self.approved_amount = p.get("approved_amount_usd")

    def _apply_application_declined(self, p: dict) -> None:
        decline_reasons = p.get("decline_reasons", [])
        is_compliance = any("REG-" in str(r) for r in decline_reasons)
        if is_compliance or self.compliance_has_hard_block:
            self.state = ApplicationState.DECLINED_COMPLIANCE
        else:
            self.state = ApplicationState.DECLINED

    # ── BUSINESS RULE ASSERTIONS ──────────────────────────────────────────────

    def assert_valid_transition(self, target: ApplicationState) -> None:
        """Rule 1: raises InvalidStateTransitionError for invalid transitions."""
        from src.models.events import InvalidStateTransitionError
        allowed = VALID_TRANSITIONS.get(self.state, [])
        if target not in allowed:
            raise InvalidStateTransitionError(
                application_id=self.application_id,
                current_state=self.state.value,
                target_state=target.value,
                allowed_states=[s.value for s in allowed],
            )

    def assert_not_terminal(self) -> None:
        """Raises InvalidStateTransitionError if in a terminal state."""
        from src.models.events import InvalidStateTransitionError
        if self.state in TERMINAL_STATES:
            raise InvalidStateTransitionError(
                application_id=self.application_id,
                current_state=self.state.value,
                target_state="any",
                allowed_states=[],
            )

    def assert_documents_processed(self) -> None:
        """Rule 2: documents must be processed before credit analysis."""
        if not self.document_package_ready:
            raise ValueError(
                "Document package is not ready. "
                "Run DocumentProcessingAgent first."
            )

    def assert_no_prior_credit_analysis(self) -> None:
        """Rule 3: raises ModelVersionLockedError if already analysed."""
        from src.models.events import ModelVersionLockedError
        if self.has_credit_analysis and not self.analysis_overridden:
            raise ModelVersionLockedError(
                application_id=self.application_id,
            )

    def assert_analyses_complete(self) -> None:
        """Rules 3/5: raises domain errors if analyses are incomplete."""
        from src.models.events import (
            InvalidStateTransitionError,
            ComplianceDependencyError,
        )
        if self.credit_confidence is None:
            raise InvalidStateTransitionError(
                application_id=self.application_id,
                current_state=self.state.value,
                target_state="PENDING_DECISION",
                allowed_states=[],
            )
        if self.fraud_score is None:
            raise InvalidStateTransitionError(
                application_id=self.application_id,
                current_state=self.state.value,
                target_state="PENDING_DECISION",
                allowed_states=[],
            )
        if self.compliance_verdict is None:
            raise ComplianceDependencyError(
                application_id=self.application_id,
            )

    def assert_valid_orchestrator_decision(
        self,
        recommendation: str,
        confidence: float,
    ) -> None:
        """Rule 4: confidence < 0.60 must be REFER. Rule 5: hard block must be DECLINE."""
        if confidence < 0.60 and recommendation != "REFER":
            raise ValueError(
                f"Confidence {confidence:.2f} < 0.60 requires recommendation=REFER, "
                f"got {recommendation}."
            )
        if self.compliance_has_hard_block and recommendation != "DECLINE":
            raise ValueError(
                f"Compliance hard block requires recommendation=DECLINE, "
                f"got {recommendation}."
            )

    def assert_valid_contributing_sessions(
        self,
        contributing_sessions: list[str],
    ) -> None:
        """Rule 6: causal chain enforcement."""
        from src.models.events import CausalChainError
        invalid = [
            s for s in contributing_sessions
            if s not in self.valid_session_ids
        ]
        if invalid:
            raise CausalChainError(
                application_id=self.application_id,
                invalid_sessions=invalid,
            )

    # ── PROPERTIES ────────────────────────────────────────────────────────────

    @property
    def stream_version(self) -> int:
        """
        Precise stream version for use as expected_version in store.append().
        Handlers must use this value — never call store.stream_version() separately.
        """
        return self.version

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def can_accept_documents(self) -> bool:
        return self.state in (
            ApplicationState.DOCUMENTS_PENDING,
            ApplicationState.DOCUMENTS_UPLOADED,
        )