"""
src/integrity/audit_chain.py
=============================
Cryptographic audit chain for the Apex Ledger.

Implements SHA-256 hash chain over event streams.
Each AuditIntegrityCheckRun records:
  - Hash of all event payloads since last check
  - Chain hash: sha256(previous_hash + current_batch_hash)

Any post-hoc modification of stored events breaks the chain.
"""
from __future__ import annotations
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64  # Starting hash for chains with no prior check


@dataclass
class IntegrityCheckResult:
    entity_type: str
    entity_id: str
    events_verified: int
    chain_valid: bool
    tamper_detected: bool
    previous_hash: str
    current_hash: str
    check_timestamp: str
    error: str | None = None


# ── MAIN FUNCTION ─────────────────────────────────────────────────────────────

async def run_integrity_check(
    store,
    entity_type: str,
    entity_id: str,
) -> IntegrityCheckResult:
    """
    1. Load all events for the entity's primary stream
    2. Load the last AuditIntegrityCheckRun event from the audit stream (if any)
    3. Hash the payloads of all events since the last check
    4. Verify hash chain: new_hash = sha256(previous_hash + batch_hash)
    5. Append new AuditIntegrityCheckRun event to audit-{entity_type}-{entity_id}
    6. Return IntegrityCheckResult
    """
    primary_stream = f"loan-{entity_id}" if entity_type == "loan" else f"{entity_type}-{entity_id}"
    audit_stream = f"audit-{entity_type}-{entity_id}"

    try:
        # 1. Load primary stream events
        all_events = await store.load_stream(primary_stream)

        # 2. Load last integrity check from audit stream
        audit_events = await store.load_stream(audit_stream)
        last_check = None
        last_position = 0
        previous_hash = GENESIS_HASH

        for ev in reversed(audit_events):
            if ev.get("event_type") == "AuditIntegrityCheckRun":
                last_check = ev
                payload = ev.get("payload", {})
                previous_hash = payload.get("integrity_hash", GENESIS_HASH)
                last_position = payload.get("events_verified_count", 0)
                break

        # 3. Get events since last check
        events_to_verify = all_events[last_position:]

        # 4. Hash event payloads
        batch_hash = _hash_events(events_to_verify)

        # 5. Chain hash: sha256(previous_hash + batch_hash)
        chain_input = (previous_hash + batch_hash).encode()
        current_hash = hashlib.sha256(chain_input).hexdigest()

        # 6. Verify chain integrity if prior check exists
        chain_valid = True
        tamper_detected = False

        if last_check:
            # Re-compute what the previous batch hash should have been
            prior_events = all_events[:last_position]
            expected_batch = _hash_events(prior_events)
            prior_payload = last_check.get("payload", {})
            stored_hash = prior_payload.get("integrity_hash", "")

            # Reconstruct expected chain hash
            prior_previous = prior_payload.get("previous_hash", GENESIS_HASH)
            expected_chain = hashlib.sha256(
                (prior_previous + expected_batch).encode()
            ).hexdigest()

            if expected_chain != stored_hash:
                chain_valid = False
                tamper_detected = True
                logger.warning(
                    f"TAMPER DETECTED on {primary_stream}: "
                    f"expected {expected_chain[:16]}... got {stored_hash[:16]}..."
                )

        now = datetime.now(timezone.utc).isoformat()
        total_verified = len(all_events)

        # 7. Append AuditIntegrityCheckRun to audit stream
        check_event = _build_check_event(
            entity_type=entity_type,
            entity_id=entity_id,
            events_verified_count=total_verified,
            integrity_hash=current_hash,
            previous_hash=previous_hash,
            chain_valid=chain_valid,
            tamper_detected=tamper_detected,
            check_timestamp=now,
        )

        audit_ver = await store.stream_version(audit_stream)
        await store.append(
            stream_id=audit_stream,
            events=[check_event],
            expected_version=audit_ver,
            correlation_id=entity_id,
        )

        return IntegrityCheckResult(
            entity_type=entity_type,
            entity_id=entity_id,
            events_verified=total_verified,
            chain_valid=chain_valid,
            tamper_detected=tamper_detected,
            previous_hash=previous_hash,
            current_hash=current_hash,
            check_timestamp=now,
        )

    except Exception as e:
        logger.error(f"Integrity check failed for {entity_type}/{entity_id}: {e}")
        return IntegrityCheckResult(
            entity_type=entity_type,
            entity_id=entity_id,
            events_verified=0,
            chain_valid=False,
            tamper_detected=False,
            previous_hash=GENESIS_HASH,
            current_hash=GENESIS_HASH,
            check_timestamp=datetime.now(timezone.utc).isoformat(),
            error=str(e),
        )


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _hash_events(events: list[dict]) -> str:
    """SHA-256 hash of all event payloads concatenated in order."""
    h = hashlib.sha256()
    for ev in events:
        payload_bytes = json.dumps(
            ev.get("payload", {}), sort_keys=True, default=str
        ).encode()
        h.update(payload_bytes)
    return h.hexdigest()


def _build_check_event(
    entity_type: str,
    entity_id: str,
    events_verified_count: int,
    integrity_hash: str,
    previous_hash: str,
    chain_valid: bool,
    tamper_detected: bool,
    check_timestamp: str,
) -> dict:
    """Build the AuditIntegrityCheckRun store dict."""
    import uuid
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "AuditIntegrityCheckRun",
        "event_version": 1,
        "payload": {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "check_timestamp": check_timestamp,
            "events_verified_count": events_verified_count,
            "integrity_hash": integrity_hash,
            "previous_hash": previous_hash,
            "chain_valid": chain_valid,
            "tamper_detected": tamper_detected,
        },
        "metadata": {},
    }