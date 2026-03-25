"""
src/aggregates/compliance_record.py
=====================================
ComplianceRecordAggregate — separate aggregate from LoanApplication.

WHY SEPARATE:
  Compliance runs 3 rules concurrently. Each concurrent write would
  contend for the loan stream version → O(N²) OCC retries.
  On its own stream, compliance writes only contend with each other.
  The LoanApplication checks compliance clearance via a READ (no contention).

STREAM ID FORMAT: compliance-{application_id}
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class ComplianceStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    CLEARED = "CLEARED"
    BLOCKED = "BLOCKED"


@dataclass
class ComplianceRecordAggregate:
    application_id: str

    status: ComplianceStatus = ComplianceStatus.PENDING
    rules_evaluated: int = 0
    rules_passed: int = 0
    rules_failed: int = 0
    rules_noted: int = 0
    has_hard_block: bool = False
    overall_verdict: str | None = None
    hard_block_rule_ids: list[str] = field(default_factory=list)
    session_id: str | None = None
    version: int = -1

    # ── LOAD ──────────────────────────────────────────────────────────────────

    @classmethod
    async def load(cls, store, application_id: str) -> "ComplianceRecordAggregate":
        """Replay compliance stream to rebuild aggregate state."""
        agg = cls(application_id=application_id)
        events = await store.load_stream(f"compliance-{application_id}")
        for event in events:
            agg.apply(event)
        return agg

    # ── DISPATCHER ────────────────────────────────────────────────────────────

    def apply(self, event: dict) -> None:
        """Apply one event — pure function, no IO."""
        et = event.get("event_type", "")
        p = event.get("payload", {})
        self.version += 1

        handler = {
            "ComplianceCheckInitiated":  self._apply_check_initiated,
            "ComplianceRulePassed":      self._apply_rule_passed,
            "ComplianceRuleFailed":      self._apply_rule_failed,
            "ComplianceRuleNoted":       self._apply_rule_noted,
            "ComplianceCheckCompleted":  self._apply_check_completed,
        }.get(et)

        if handler:
            handler(p)

    # ── PER-EVENT HANDLERS ────────────────────────────────────────────────────

    def _apply_check_initiated(self, p: dict) -> None:
        self.status = ComplianceStatus.IN_PROGRESS
        self.session_id = p.get("session_id")

    def _apply_rule_passed(self, p: dict) -> None:
        self.rules_evaluated += 1
        self.rules_passed += 1

    def _apply_rule_failed(self, p: dict) -> None:
        self.rules_evaluated += 1
        self.rules_failed += 1
        if p.get("severity") == "HARD_BLOCK" or p.get("is_hard_block"):
            self.has_hard_block = True
            rule_id = p.get("rule_id")
            if rule_id and rule_id not in self.hard_block_rule_ids:
                self.hard_block_rule_ids.append(rule_id)

    def _apply_rule_noted(self, p: dict) -> None:
        self.rules_evaluated += 1
        self.rules_noted += 1

    def _apply_check_completed(self, p: dict) -> None:
        verdict = p.get("overall_verdict", "")
        self.overall_verdict = verdict
        if verdict == "CLEAR" and not self.has_hard_block:
            self.status = ComplianceStatus.CLEARED
        else:
            self.status = ComplianceStatus.BLOCKED
        # Override counters with final authoritative values if provided
        if p.get("rules_evaluated") is not None:
            self.rules_evaluated = p["rules_evaluated"]
        if p.get("rules_passed") is not None:
            self.rules_passed = p["rules_passed"]
        if p.get("rules_failed") is not None:
            self.rules_failed = p["rules_failed"]
        if p.get("rules_noted") is not None:
            self.rules_noted = p["rules_noted"]
        if p.get("has_hard_block") is not None:
            self.has_hard_block = p["has_hard_block"]

    # ── ASSERTIONS ────────────────────────────────────────────────────────────

    def assert_clearance_issued(self) -> None:
        """Raises ComplianceDependencyError if not cleared."""
        from src.models.events import ComplianceDependencyError
        if self.status != ComplianceStatus.CLEARED:
            raise ComplianceDependencyError(application_id=self.application_id)

    def assert_not_blocked(self) -> None:
        """Raises ValueError if a hard block is present."""
        if self.has_hard_block:
            raise ValueError(
                f"Application '{self.application_id}' has a compliance hard block "
                f"on rules: {self.hard_block_rule_ids}. Decision must be DECLINE."
            )

    # ── PROPERTIES ────────────────────────────────────────────────────────────

    @property
    def stream_version(self) -> int:
        """Precise stream version for use as expected_version in store.append()."""
        return self.version

    @property
    def is_cleared(self) -> bool:
        return self.status == ComplianceStatus.CLEARED

    @property
    def is_blocked(self) -> bool:
        return self.status == ComplianceStatus.BLOCKED or self.has_hard_block
