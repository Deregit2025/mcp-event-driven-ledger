from __future__ import annotations

"""
src/models/events.py
=====================
Re-exports all 45 canonical event types from schema/events.py.
Also defines StoredEvent, StreamMetadata, and structured exception models.

Single source of truth: schema/events.py
This file adds the storage and exception layer on top.
"""

# ── Re-export everything from canonical schema ────────────────────────────────
from schema.events import (
    # Base
    BaseEvent,
    EVENT_REGISTRY,
    deserialize_event,
    # Enums
    RiskTier,
    ApplicationState,
    DocumentType,
    DocumentFormat,
    AgentType,
    LoanPurpose,
    FraudAnomalyType,
    ComplianceVerdict,
    # Value objects
    FinancialFacts,
    FraudAnomaly,
    CreditDecision,
    # LoanApplication events
    ApplicationSubmitted,
    DocumentUploadRequested,
    DocumentUploaded,
    DocumentUploadFailed,
    CreditAnalysisRequested,
    FraudScreeningRequested,
    ComplianceCheckRequested,
    DecisionRequested,
    DecisionGenerated,
    HumanReviewRequested,
    HumanReviewCompleted,
    ApplicationApproved,
    ApplicationDeclined,
    # DocumentPackage events
    PackageCreated,
    DocumentAdded,
    DocumentFormatValidated,
    DocumentFormatRejected,
    ExtractionStarted,
    ExtractionCompleted,
    ExtractionFailed,
    QualityAssessmentCompleted,
    PackageReadyForAnalysis,
    # AgentSession events
    AgentSessionStarted,
    AgentInputValidated,
    AgentInputValidationFailed,
    AgentNodeExecuted,
    AgentToolCalled,
    AgentOutputWritten,
    AgentSessionCompleted,
    AgentSessionFailed,
    AgentSessionRecovered,
    # CreditRecord events
    CreditRecordOpened,
    HistoricalProfileConsumed,
    ExtractedFactsConsumed,
    CreditAnalysisCompleted,
    CreditAnalysisDeferred,
    # ComplianceRecord events
    ComplianceCheckInitiated,
    ComplianceRulePassed,
    ComplianceRuleFailed,
    ComplianceRuleNoted,
    ComplianceCheckCompleted,
    # FraudScreening events
    FraudScreeningInitiated,
    FraudAnomalyDetected,
    FraudScreeningCompleted,
    # AuditLedger events
    AuditIntegrityCheckRun,
)

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


# ── STORED EVENT ──────────────────────────────────────────────────────────────

@dataclass
class StoredEvent:
    """
    An event as it exists in the event store — includes all storage metadata.

    The difference from BaseEvent:
    - BaseEvent is the domain model (what happened)
    - StoredEvent is the storage model (what happened + where + when + order)

    Used by projections and agents when they need full storage context.
    """
    # Storage identity
    event_id: str
    stream_id: str
    stream_position: int        # position within stream (0-based)
    global_position: int        # global ordering across all streams

    # Event data
    event_type: str
    event_version: int
    payload: dict[str, Any]
    metadata: dict[str, Any]

    # Timestamps
    recorded_at: datetime

    @property
    def causation_id(self) -> str | None:
        """The event or command that caused this event."""
        return self.metadata.get("causation_id")

    @property
    def correlation_id(self) -> str | None:
        """The root business transaction this event belongs to."""
        return self.metadata.get("correlation_id")

    @property
    def is_first_in_stream(self) -> bool:
        return self.stream_position == 0

    @classmethod
    def from_dict(cls, d: dict) -> "StoredEvent":
        """Construct from a raw database row dict."""
        return cls(
            event_id=str(d["event_id"]),
            stream_id=d["stream_id"],
            stream_position=d["stream_position"],
            global_position=d["global_position"],
            event_type=d["event_type"],
            event_version=d.get("event_version", 1),
            payload=d.get("payload", {}),
            metadata=d.get("metadata", {}),
            recorded_at=d["recorded_at"],
        )

    def to_domain_event(self) -> BaseEvent:
        """
        Deserialize payload into the canonical domain event class.
        Uses EVENT_REGISTRY to find the correct class.
        """
        return deserialize_event(self.event_type, self.payload)


# ── STREAM METADATA ───────────────────────────────────────────────────────────

@dataclass
class StreamMetadata:
    """
    Metadata about a stream without loading any events.
    Returned by EventStore.get_stream_metadata().
    Used for health checks, audit queries, and stream lifecycle management.
    """
    stream_id: str
    aggregate_type: str         # e.g. "loan", "agent", "compliance"
    current_version: int        # -1 if empty, 0+ otherwise
    created_at: datetime | None
    updated_at: datetime | None
    archived_at: datetime | None = None

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    @property
    def is_empty(self) -> bool:
        return self.current_version == -1

    @property
    def event_count(self) -> int:
        """Number of events in the stream (current_version + 1)."""
        return max(0, self.current_version + 1)

    @classmethod
    def from_dict(cls, d: dict) -> "StreamMetadata":
        return cls(
            stream_id=d["stream_id"],
            aggregate_type=d["aggregate_type"],
            current_version=d["current_version"],
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
            archived_at=d.get("archived_at"),
        )


# ── STRUCTURED EXCEPTIONS ─────────────────────────────────────────────────────

class DomainError(Exception):
    """
    Base class for all domain errors.
    Structured fields make errors consumable by LLMs and MCP tools.

    Every DomainError has:
    - error_type: machine-readable error class name
    - message: human-readable description
    - suggested_action: what the caller should do next
    - context: additional structured data
    """

    def __init__(
        self,
        message: str,
        suggested_action: str = "contact_support",
        context: dict | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_type = self.__class__.__name__
        self.suggested_action = suggested_action
        self.context = context or {}

    def to_dict(self) -> dict:
        """Serialize to dict for MCP tool responses."""
        return {
            "error_type": self.error_type,
            "message": self.message,
            "suggested_action": self.suggested_action,
            "context": self.context,
        }

    def __repr__(self) -> str:
        return f"{self.error_type}({self.message!r})"


class OptimisticConcurrencyError(DomainError):
    """
    Raised when expected_version doesn't match current stream version.
    Two agents tried to write to the same stream simultaneously.
    The losing agent must reload the stream and retry.
    """

    def __init__(self, stream_id: str, expected: int, actual: int):
        self.stream_id = stream_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            message=(
                f"Concurrency conflict on stream '{stream_id}': "
                f"expected version {expected}, found {actual}"
            ),
            suggested_action="reload_stream_and_retry",
            context={
                "stream_id": stream_id,
                "expected_version": expected,
                "actual_version": actual,
                "version_gap": actual - expected,
            },
        )


class StreamNotFoundError(DomainError):
    """Raised when a stream does not exist."""

    def __init__(self, stream_id: str):
        self.stream_id = stream_id
        super().__init__(
            message=f"Stream '{stream_id}' does not exist",
            suggested_action="verify_stream_id_and_retry",
            context={"stream_id": stream_id},
        )


class StreamArchivedError(DomainError):
    """Raised when attempting to append to an archived stream."""

    def __init__(self, stream_id: str):
        self.stream_id = stream_id
        super().__init__(
            message=f"Stream '{stream_id}' is archived and read-only",
            suggested_action="do_not_retry_stream_is_permanently_closed",
            context={"stream_id": stream_id},
        )


class InvalidStateTransitionError(DomainError):
    """Raised when an aggregate transition is not valid."""

    def __init__(
        self,
        application_id: str,
        current_state: str,
        target_state: str,
        allowed_states: list[str] | None = None,
    ):
        self.application_id = application_id
        self.current_state = current_state
        self.target_state = target_state
        super().__init__(
            message=(
                f"Invalid state transition for application '{application_id}': "
                f"{current_state} → {target_state}"
            ),
            suggested_action="check_current_state_and_use_valid_transition",
            context={
                "application_id": application_id,
                "current_state": current_state,
                "target_state": target_state,
                "allowed_states": allowed_states or [],
            },
        )


class ComplianceDependencyError(DomainError):
    """Raised when a decision is attempted without compliance clearance."""

    def __init__(self, application_id: str):
        self.application_id = application_id
        super().__init__(
            message=(
                f"Application '{application_id}' cannot proceed to decision: "
                "compliance check has not completed"
            ),
            suggested_action="run_compliance_agent_before_generating_decision",
            context={"application_id": application_id},
        )


class ModelVersionLockedError(DomainError):
    """Raised when a second credit analysis is attempted without override."""

    def __init__(self, application_id: str, existing_model: str = "unknown"):
        self.application_id = application_id
        super().__init__(
            message=(
                f"Application '{application_id}' already has a credit analysis "
                f"from model '{existing_model}'. "
                "A HumanReviewOverride is required before reanalysis."
            ),
            suggested_action="issue_human_review_override_before_reanalysis",
            context={
                "application_id": application_id,
                "existing_model": existing_model,
            },
        )


class AgentContextNotLoadedError(DomainError):
    """Raised when an agent tries to act without AgentSessionStarted."""

    def __init__(self, session_id: str, agent_type: str):
        self.session_id = session_id
        super().__init__(
            message=(
                f"Agent session '{session_id}' has no AgentSessionStarted event. "
                "Call start_session() before any node execution — Gas Town rule."
            ),
            suggested_action="call_start_agent_session_first",
            context={
                "session_id": session_id,
                "agent_type": agent_type,
            },
        )


class CausalChainError(DomainError):
    """Raised when contributing sessions are invalid for this application."""

    def __init__(self, application_id: str, invalid_sessions: list[str]):
        self.application_id = application_id
        super().__init__(
            message=(
                f"Application '{application_id}' has invalid contributing sessions: "
                f"{invalid_sessions}"
            ),
            suggested_action="verify_all_contributing_sessions_processed_this_application",
            context={
                "application_id": application_id,
                "invalid_sessions": invalid_sessions,
            },
        )