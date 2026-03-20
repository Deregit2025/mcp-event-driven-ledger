"""
src/aggregates/agent_session.py
================================
AgentSessionAggregate — Gas Town pattern implementation.

Replays the agent session stream to reconstruct what the agent
has done and whether it needs reconciliation after a crash.

KEY INVARIANTS:
  - AgentSessionStarted must be the first event (Gas Town anchor)
  - Every LangGraph node produces one AgentNodeExecuted event
  - On crash: AgentSessionFailed with recoverable=True
  - On recovery: AgentSessionRecovered references the crashed session
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class SessionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RECOVERED = "RECOVERED"
    NEEDS_RECONCILIATION = "NEEDS_RECONCILIATION"


@dataclass
class AgentSessionAggregate:
    session_id: str
    agent_type: str | None = None
    agent_id: str | None = None
    application_id: str | None = None
    model_version: str | None = None
    context_source: str | None = None

    status: SessionStatus = SessionStatus.ACTIVE
    nodes_executed: list[str] = field(default_factory=list)
    last_successful_node: str | None = None

    total_llm_calls: int = 0
    total_tokens_used: int = 0
    total_cost_usd: float = 0.0

    error_type: str | None = None
    error_message: str | None = None
    recoverable: bool = False

    recovered_from_session_id: str | None = None
    recovery_point: str | None = None

    context_loaded: bool = False
    version: int = -1

    @classmethod
    async def load(
        cls,
        store,
        agent_type: str,
        session_id: str,
    ) -> "AgentSessionAggregate":
        """Replay session stream to reconstruct agent state."""
        agg = cls(session_id=session_id)
        stream_id = f"agent-{agent_type}-{session_id}"
        events = await store.load_stream(stream_id)
        for event in events:
            agg.apply(event)
        return agg

    def apply(self, event: dict) -> None:
        """Apply one event — pure function, no IO."""
        et = event.get("event_type")
        p = event.get("payload", {})
        self.version += 1

        if et == "AgentSessionStarted":
            self.agent_type = p.get("agent_type")
            self.agent_id = p.get("agent_id")
            self.application_id = p.get("application_id")
            self.model_version = p.get("model_version")
            self.context_source = p.get("context_source", "fresh")
            self.status = SessionStatus.ACTIVE
            self.context_loaded = True

        elif et == "AgentNodeExecuted":
            node = p.get("node_name")
            if node and node not in self.nodes_executed:
                self.nodes_executed.append(node)
            self.last_successful_node = node
            tok_in = p.get("llm_tokens_input") or 0
            tok_out = p.get("llm_tokens_output") or 0
            cost = p.get("llm_cost_usd") or 0.0
            if tok_in or tok_out:
                self.total_llm_calls += 1
                self.total_tokens_used += tok_in + tok_out
            self.total_cost_usd += cost

        elif et == "AgentSessionCompleted":
            self.status = SessionStatus.COMPLETED
            self.total_llm_calls = p.get("total_llm_calls", self.total_llm_calls)
            self.total_tokens_used = p.get("total_tokens_used", self.total_tokens_used)
            self.total_cost_usd = p.get("total_cost_usd", self.total_cost_usd)

        elif et == "AgentSessionFailed":
            self.error_type = p.get("error_type")
            self.error_message = p.get("error_message")
            self.recoverable = p.get("recoverable", False)
            self.last_successful_node = p.get("last_successful_node")
            if self.recoverable:
                self.status = SessionStatus.NEEDS_RECONCILIATION
            else:
                self.status = SessionStatus.FAILED

        elif et == "AgentSessionRecovered":
            self.recovered_from_session_id = p.get("recovered_from_session_id")
            self.recovery_point = p.get("recovery_point")
            self.status = SessionStatus.RECOVERED
            self.context_source = f"prior_session_replay:{self.recovered_from_session_id}"

    # ── ASSERTIONS ────────────────────────────────────────────────────────────

    def assert_context_loaded(self) -> None:
        """Gas Town rule: AgentSessionStarted must exist before any work."""
        if not self.context_loaded:
            raise ValueError(
                f"Session {self.session_id} has no AgentSessionStarted event. "
                "Call start_session() before any node execution."
            )

    def assert_not_completed(self) -> None:
        if self.status == SessionStatus.COMPLETED:
            raise ValueError(
                f"Session {self.session_id} is already completed. "
                "Cannot append more events to a completed session."
            )

    def node_already_executed(self, node_name: str) -> bool:
        """Used during crash recovery to skip already-completed nodes."""
        return node_name in self.nodes_executed

    @property
    def is_crashed(self) -> bool:
        return self.status == SessionStatus.NEEDS_RECONCILIATION

    @property
    def is_active(self) -> bool:
        return self.status in (
            SessionStatus.ACTIVE,
            SessionStatus.RECOVERED,
        )