"""
src/aggregates/audit_ledger.py
================================
AuditLedgerAggregate — cryptographic hash chain for tamper detection.

Stores AuditIntegrityCheckRun events. Each check run records a hash
of the events table at that point in time. To detect tampering:
  - Replay all AuditIntegrityCheckRun events
  - Re-hash the events table
  - Compare against last stored hash

STREAM ID FORMAT: audit-ledger (singleton stream)

The cryptographic hash chain gives regulators a mechanism to verify
that no events were deleted, modified, or inserted out of order after
the fact. This is the immutability guarantee required by APRA-2026.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AuditLedgerAggregate:
    """
    Singleton aggregate tracking audit integrity check history.
    There is one audit ledger per system (stream: 'audit-ledger').
    """
    total_checks_run: int = 0
    last_check_at: datetime | None = None
    last_hash: str | None = None
    last_global_position_checked: int = 0
    integrity_failures: list[dict] = field(default_factory=list)
    version: int = -1

    # ── LOAD ──────────────────────────────────────────────────────────────────

    @classmethod
    async def load(cls, store) -> "AuditLedgerAggregate":
        """Replay audit-ledger stream to reconstruct history."""
        agg = cls()
        events = await store.load_stream("audit-ledger")
        for event in events:
            agg.apply(event)
        return agg

    # ── DISPATCHER ────────────────────────────────────────────────────────────

    def apply(self, event: dict) -> None:
        """Apply one event."""
        et = event.get("event_type", "")
        p = event.get("payload", {})
        self.version += 1

        if et == "AuditIntegrityCheckRun":
            self._apply_integrity_check_run(p)

    # ── PER-EVENT HANDLERS ────────────────────────────────────────────────────

    def _apply_integrity_check_run(self, p: dict) -> None:
        self.total_checks_run += 1
        self.last_hash = p.get("events_hash")
        self.last_global_position_checked = p.get("up_to_global_position", 0)

        recorded_at = p.get("checked_at")
        if isinstance(recorded_at, str):
            try:
                from datetime import timezone
                self.last_check_at = datetime.fromisoformat(recorded_at)
            except ValueError:
                pass
        elif isinstance(recorded_at, datetime):
            self.last_check_at = recorded_at

        # Track failures (integrity_passed=False means tampering detected)
        if not p.get("integrity_passed", True):
            self.integrity_failures.append({
                "check_number": self.total_checks_run,
                "events_hash": self.last_hash,
                "up_to_global_position": self.last_global_position_checked,
                "failure_reason": p.get("failure_reason", "hash_mismatch"),
            })

    # ── HELPERS ───────────────────────────────────────────────────────────────

    @staticmethod
    def compute_events_hash(events: list[dict]) -> str:
        """
        Compute a deterministic SHA-256 hash over a list of stored events.

        Hash covers: event_id, stream_id, stream_position, event_type,
        event_version, payload — in global_position order.
        Tampering with any of these makes the hash mismatch detectable.
        """
        import hashlib, json

        h = hashlib.sha256()
        for event in sorted(events, key=lambda e: e.get("global_position", 0)):
            canonical = json.dumps({
                "event_id": str(event.get("event_id", "")),
                "stream_id": event.get("stream_id", ""),
                "stream_position": event.get("stream_position", 0),
                "event_type": event.get("event_type", ""),
                "event_version": event.get("event_version", 1),
                "payload": event.get("payload", {}),
            }, sort_keys=True, ensure_ascii=True)
            h.update(canonical.encode("utf-8"))
        return h.hexdigest()

    # ── ASSERTIONS ────────────────────────────────────────────────────────────

    def assert_no_integrity_failures(self) -> None:
        """Raises if any integrity check has ever detected tampering."""
        if self.integrity_failures:
            raise ValueError(
                f"Audit integrity failures detected: {len(self.integrity_failures)} "
                f"failed checks. Last failure at position "
                f"{self.integrity_failures[-1]['up_to_global_position']}."
            )

    # ── PROPERTIES ────────────────────────────────────────────────────────────

    @property
    def stream_version(self) -> int:
        return self.version

    @property
    def has_been_checked(self) -> bool:
        return self.total_checks_run > 0

    @property
    def is_clean(self) -> bool:
        """True if no integrity failures have ever been recorded."""
        return len(self.integrity_failures) == 0
