"""
src/aggregates/loan_application.py
===================================
LoanApplicationAggregate — full implementation.

Merges:
  - Starter ground rules: ApplicationState enum, VALID_TRANSITIONS, dataclass structure
  - Full implementation: all apply() handlers, all 6 business rule assertions

Stream ID format: loan-{application_id}

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
    ApplicationState.NEW: [
        ApplicationState.SUBMITTED,
    ],
    ApplicationState.SUBMITTED: [
        ApplicationState.DOCUMENTS_PENDING,
    ],
    ApplicationState.DOCUMENTS_PENDING: [
        ApplicationState.DOCUMENTS_UPLOADED,
    ],
    ApplicationState.DOCUMENTS_UPLOADED: [
        ApplicationState.DOCUMENTS_PROCESSED,
    ],
    ApplicationState.DOCUMENTS_PROCESSED: [
        ApplicationState.CREDIT_ANALYSIS_REQUESTED,
    ],
    ApplicationState.CREDIT_ANALYSIS_REQUESTED: [
        ApplicationState.CREDIT_ANALYSIS_COMPLETE,
    ],
    ApplicationState.CREDIT_ANALYSIS_COMPLETE: [
        ApplicationState.FRAUD_SCREENING_REQUESTED,
    ],
    ApplicationState.FRAUD_SCREENING_REQUESTED: [
        ApplicationState.FRAUD_SCREENING_COMPLETE,
    ],
    ApplicationState.FRAUD_SCREENING_COMPLETE: [
        ApplicationState.COMPLIANCE_CHECK_REQUESTED,
    ],
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
    # Terminal states
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


# ── AGGREGATE ─────────────────────────────────────────────────────────────────

@dataclass
class LoanApplicationAggregate:
    application_id: str
    state: ApplicationState = ApplicationState.NEW

    # From ApplicationSubmitted
    applicant_id: str | None = None
    requested_amount_usd: Decimal | None = None
    loan_purpose: str | None = None
    submission_channel: str | None = None

    # Analysis results
    credit_confidence: float | None = None
    credit_risk_tier: str | None = None
    fraud_score: float | None = None
    compliance_verdict: str | None = None
    compliance_has_hard_block: bool = False

    # Business rule 3 — model version locking
    has_credit_analysis: bool = False
    analysis_overridden: bool = False

    # Business rule 6 — causal chain
    valid_session_ids: set = field(default_factory=set)
    contributing_agent_sessions: list = field(default_factory=list)

    # Document tracking
    documents_uploaded: list = field(default_factory=list)
    document_package_ready: bool = False

    # Decision
    approved_amount: float | None = None
    version: int = -1

    # ── LOAD ──────────────────────────────────────────────────────────────────

    @classmethod
    async def load(
        cls,
        store,
        application_id: str,
    ) -> "LoanApplicationAggregate":
        """Load and replay event stream to rebuild aggregate state."""
        agg = cls(application_id=application_id)
        stream_events = await store.load_stream(f"loan-{application_id}")
        for event in stream_events:
            agg.apply(event)
        return agg

    # ── APPLY ─────────────────────────────────────────────────────────────────

    def apply(self, event: dict) -> None:
        """
        Apply one event to update aggregate state.
        Pure function — no IO, no side effects.
        """
        et = event.get("event_type")
        p = event.get("payload", {})
        self.version += 1

        if et == "ApplicationSubmitted":
            self.state = ApplicationState.SUBMITTED
            self.applicant_id = p.get("applicant_id")
            self.requested_amount_usd = (
                Decimal(str(p["requested_amount_usd"]))
                if p.get("requested_amount_usd") is not None else None
            )
            self.loan_purpose = p.get("loan_purpose")
            self.submission_channel = p.get("submission_channel")

        elif et == "DocumentUploadRequested":
            self.state = ApplicationState.DOCUMENTS_PENDING

        elif et == "DocumentUploaded":
            self.state = ApplicationState.DOCUMENTS_UPLOADED
            doc_id = p.get("document_id")
            if doc_id and doc_id not in self.documents_uploaded:
                self.documents_uploaded.append(doc_id)

        elif et == "DocumentUploadFailed":
            pass  # stays in DOCUMENTS_PENDING

        elif et == "PackageReadyForAnalysis":
            self.document_package_ready = True
            self.state = ApplicationState.DOCUMENTS_PROCESSED

        elif et == "CreditAnalysisRequested":
            self.state = ApplicationState.CREDIT_ANALYSIS_REQUESTED
            agent_id = p.get("assigned_agent_id", "")
            if agent_id:
                self.valid_session_ids.add(agent_id)

        elif et in ("CreditAnalysisCompleted", "CreditAnalysisDeferred"):
            self.state = ApplicationState.CREDIT_ANALYSIS_COMPLETE
            self.has_credit_analysis = True
            decision = p.get("decision", {})
            if isinstance(decision, dict):
                self.credit_confidence = decision.get("confidence")
                self.credit_risk_tier = decision.get("risk_tier")
            session_id = p.get("session_id", "")
            if session_id:
                self.valid_session_ids.add(session_id)

        elif et == "FraudScreeningRequested":
            self.state = ApplicationState.FRAUD_SCREENING_REQUESTED
            agent_id = p.get("assigned_agent_id", "")
            if agent_id:
                self.valid_session_ids.add(agent_id)

        elif et == "FraudScreeningCompleted":
            self.state = ApplicationState.FRAUD_SCREENING_COMPLETE
            self.fraud_score = p.get("fraud_score")
            session_id = p.get("session_id", "")
            if session_id:
                self.valid_session_ids.add(session_id)

        elif et == "ComplianceCheckRequested":
            self.state = ApplicationState.COMPLIANCE_CHECK_REQUESTED

        elif et == "ComplianceCheckCompleted":
            self.state = ApplicationState.COMPLIANCE_CHECK_COMPLETE
            self.compliance_verdict = p.get("overall_verdict")
            self.compliance_has_hard_block = p.get("has_hard_block", False)

        elif et == "DecisionRequested":
            self.state = ApplicationState.PENDING_DECISION

        elif et == "DecisionGenerated":
            rec = p.get("recommendation", "")
            self.contributing_agent_sessions = p.get("contributing_sessions", [])
            if rec == "REFER":
                self.state = ApplicationState.PENDING_HUMAN_REVIEW
            # APPROVE/DECLINE stays PENDING_DECISION until final event

        elif et == "HumanReviewRequested":
            self.state = ApplicationState.PENDING_HUMAN_REVIEW

        elif et == "HumanReviewCompleted":
            pass  # final state set by ApplicationApproved/Declined

        elif et == "HumanReviewOverride":
            # Business rule 3: override allows new credit analysis
            self.analysis_overridden = True
            self.has_credit_analysis = False

        elif et == "ApplicationApproved":
            self.state = ApplicationState.APPROVED
            self.approved_amount = p.get("approved_amount_usd")

        elif et == "ApplicationDeclined":
            decline_reasons = p.get("decline_reasons", [])
            is_compliance = any("REG-" in str(r) for r in decline_reasons)
            if is_compliance or self.compliance_has_hard_block:
                self.state = ApplicationState.DECLINED_COMPLIANCE
            else:
                self.state = ApplicationState.DECLINED

        # Unknown events silently ignored — forward compatibility

    # ── BUSINESS RULE ASSERTIONS ──────────────────────────────────────────────

    def assert_valid_transition(self, target: ApplicationState) -> None:
        """Rule 1: only valid state transitions allowed."""
        allowed = VALID_TRANSITIONS.get(self.state, [])
        if target not in allowed:
            raise ValueError(
                f"Invalid transition {self.state} → {target}. "
                f"Allowed: {[s.value for s in allowed]}"
            )

    def assert_not_terminal(self) -> None:
        """Raise if application is already in a terminal state."""
        if self.state in TERMINAL_STATES:
            raise ValueError(
                f"Application {self.application_id} is in terminal state "
                f"{self.state}. No further transitions allowed."
            )

    def assert_documents_processed(self) -> None:
        """Rule 2: documents must be processed before credit analysis."""
        if not self.document_package_ready:
            raise ValueError(
                "Document package is not ready. "
                "Run DocumentProcessingAgent first."
            )

    def assert_no_prior_credit_analysis(self) -> None:
        """
        Rule 3: model version locking.
        A second CreditAnalysisCompleted requires a prior HumanReviewOverride.
        """
        if self.has_credit_analysis and not self.analysis_overridden:
            raise ValueError(
                f"Application {self.application_id} already has a credit analysis. "
                "A HumanReviewOverride is required before reanalysis."
            )

    def assert_analyses_complete(self) -> None:
        """Rule 3/5: all analyses must complete before decision."""
        if self.credit_confidence is None:
            raise ValueError(
                "Credit analysis has not completed. "
                "CreditAnalysisCompleted is required before DecisionGenerated."
            )
        if self.fraud_score is None:
            raise ValueError(
                "Fraud screening has not completed. "
                "FraudScreeningCompleted is required before DecisionGenerated."
            )
        if self.compliance_verdict is None:
            raise ValueError(
                "Compliance check has not completed. "
                "ComplianceCheckCompleted is required before DecisionGenerated."
            )

    def assert_valid_orchestrator_decision(
        self,
        recommendation: str,
        confidence: float,
    ) -> None:
        """
        Rule 4: confidence < 0.60 → must be REFER.
        Rule 5: compliance hard block → must be DECLINE.
        """
        if confidence < 0.60 and recommendation != "REFER":
            raise ValueError(
                f"Confidence {confidence:.2f} < 0.60 requires recommendation=REFER, "
                f"got {recommendation}. The orchestrator cannot override this rule."
            )
        if self.compliance_has_hard_block and recommendation != "DECLINE":
            raise ValueError(
                f"Compliance hard block requires recommendation=DECLINE, "
                f"got {recommendation}. Cannot APPROVE or REFER when compliance is BLOCKED."
            )

    def assert_valid_contributing_sessions(
        self,
        contributing_sessions: list[str],
    ) -> None:
        """
        Rule 6: causal chain enforcement.
        All contributing sessions must have processed this application.
        """
        invalid = [
            s for s in contributing_sessions
            if s not in self.valid_session_ids
        ]
        if invalid:
            raise ValueError(
                f"Invalid contributing sessions for application "
                f"{self.application_id}: {invalid}. "
                "These sessions did not process this application."
            )

    # ── PROPERTIES ────────────────────────────────────────────────────────────

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def can_accept_documents(self) -> bool:
        return self.state in (
            ApplicationState.DOCUMENTS_PENDING,
            ApplicationState.DOCUMENTS_UPLOADED,
        )