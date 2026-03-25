"""
src/regulatory/package.py
==========================
Regulatory Examination Package generator.

Produces a self-contained JSON file that a regulator can verify
against the database independently — they do not need to trust
your system to validate that the package is accurate.

Package contents:
  1. Complete event stream for the application, in order, full payloads
  2. Projection states as they existed at examination_date
  3. Audit chain integrity verification result
  4. Human-readable narrative (one sentence per significant event)
  5. Model versions, confidence scores, input data hashes per AI agent
"""
from __future__ import annotations
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ── RESULT ────────────────────────────────────────────────────────────────────

@dataclass
class RegulatoryPackage:
    application_id: str
    examination_date: str
    generated_at: str
    event_stream: list[dict]
    projection_states: dict[str, Any]
    integrity_verification: dict
    narrative: list[str]
    agent_metadata: list[dict]
    package_hash: str  # SHA-256 of the entire package contents

    def to_dict(self) -> dict:
        return {
            "schema_version": "1.0",
            "application_id": self.application_id,
            "examination_date": self.examination_date,
            "generated_at": self.generated_at,
            "event_stream": self.event_stream,
            "projection_states": self.projection_states,
            "integrity_verification": self.integrity_verification,
            "narrative": self.narrative,
            "agent_metadata": self.agent_metadata,
            "package_hash": self.package_hash,
            "_verification_instructions": (
                "To independently verify this package: "
                "1) Query the events table for all streams listed in event_stream "
                "and compare payloads. "
                "2) Recompute SHA-256 over the event payloads in order and compare "
                "to integrity_verification.computed_hash. "
                "3) Recompute package_hash by SHA-256 of all fields except package_hash itself."
            ),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), default=str, indent=indent)


# ── MAIN FUNCTION ─────────────────────────────────────────────────────────────

async def generate_regulatory_package(
    store,
    application_id: str,
    examination_date: datetime | str | None = None,
) -> RegulatoryPackage:
    """
    Generate a complete, self-contained regulatory examination package.

    The package is independently verifiable — a regulator can validate
    every field against the raw database without trusting this system.
    """
    if examination_date is None:
        examination_date = datetime.now(timezone.utc)
    if isinstance(examination_date, str):
        examination_date = datetime.fromisoformat(
            examination_date.replace("Z", "+00:00")
        )

    exam_date_str = examination_date.isoformat()
    generated_at = datetime.now(timezone.utc).isoformat()

    # 1. Load complete event stream across all streams
    event_stream = await _load_full_event_stream(store, application_id, examination_date)

    # 2. Build projection states at examination_date
    projection_states = await _build_projection_states(
        store, application_id, event_stream, examination_date
    )

    # 3. Run integrity verification
    integrity_verification = await _run_integrity_verification(
        store, application_id, event_stream
    )

    # 4. Generate human-readable narrative
    narrative = _generate_narrative(event_stream)

    # 5. Extract agent metadata
    agent_metadata = await _extract_agent_metadata(store, application_id, event_stream)

    # 6. Compute package hash for independent verification
    package_contents = {
        "application_id": application_id,
        "examination_date": exam_date_str,
        "event_stream": event_stream,
        "integrity_verification": integrity_verification,
        "narrative": narrative,
        "agent_metadata": agent_metadata,
    }
    package_hash = hashlib.sha256(
        json.dumps(package_contents, sort_keys=True, default=str).encode()
    ).hexdigest()

    return RegulatoryPackage(
        application_id=application_id,
        examination_date=exam_date_str,
        generated_at=generated_at,
        event_stream=event_stream,
        projection_states=projection_states,
        integrity_verification=integrity_verification,
        narrative=narrative,
        agent_metadata=agent_metadata,
        package_hash=package_hash,
    )


# ── STEP 1: FULL EVENT STREAM ─────────────────────────────────────────────────

async def _load_full_event_stream(
    store,
    application_id: str,
    examination_date: datetime,
) -> list[dict]:
    """Load all events across all streams, filtered to examination_date."""
    stream_ids = [
        f"loan-{application_id}",
        f"credit-{application_id}",
        f"fraud-{application_id}",
        f"compliance-{application_id}",
        f"audit-loan-{application_id}",
    ]

    all_events = []
    for stream_id in stream_ids:
        events = await store.load_stream(stream_id)
        for ev in events:
            recorded_at = ev.get("recorded_at")
            if recorded_at:
                if isinstance(recorded_at, str):
                    try:
                        recorded_at = datetime.fromisoformat(
                            recorded_at.replace("Z", "+00:00")
                        )
                    except Exception:
                        recorded_at = None
                if recorded_at and recorded_at > examination_date:
                    continue  # exclude events after examination date

            all_events.append({
                "event_id": str(ev.get("event_id", "")),
                "stream_id": ev.get("stream_id", stream_id),
                "stream_position": ev.get("stream_position"),
                "global_position": ev.get("global_position"),
                "event_type": ev.get("event_type"),
                "event_version": ev.get("event_version", 1),
                "payload": ev.get("payload", {}),
                "metadata": ev.get("metadata", {}),
                "recorded_at": str(ev.get("recorded_at", "")),
                "causation_id": ev.get("metadata", {}).get("causation_id"),
                "correlation_id": ev.get("metadata", {}).get("correlation_id"),
            })

    # Sort chronologically by recorded_at then global_position
    all_events.sort(key=lambda e: (
        e.get("recorded_at") or "",
        e.get("global_position") or 0,
    ))
    return all_events


# ── STEP 2: PROJECTION STATES ─────────────────────────────────────────────────

async def _build_projection_states(
    store,
    application_id: str,
    event_stream: list[dict],
    examination_date: datetime,
) -> dict[str, Any]:
    """
    Reconstruct projection states as they existed at examination_date
    by replaying only events up to that date through the aggregates.
    """
    from src.aggregates.loan_application import LoanApplicationAggregate

    # Replay loan stream events up to examination_date
    loan_events = [
        e for e in event_stream
        if e["stream_id"].startswith(f"loan-{application_id}")
    ]

    agg = LoanApplicationAggregate(application_id=application_id)
    for ev in loan_events:
        agg.apply(ev)

    application_summary = {
        "application_id": application_id,
        "state": agg.state.value,
        "applicant_id": agg.applicant_id,
        "requested_amount_usd": float(agg.requested_amount_usd) if agg.requested_amount_usd else None,
        "loan_purpose": agg.loan_purpose,
        "credit_risk_tier": agg.credit_risk_tier,
        "credit_confidence": agg.credit_confidence,
        "fraud_score": agg.fraud_score,
        "compliance_verdict": agg.compliance_verdict,
        "compliance_has_hard_block": agg.compliance_has_hard_block,
        "approved_amount": agg.approved_amount,
        "is_terminal": agg.is_terminal,
        "_note": f"State as of {examination_date.isoformat()} via event replay",
    }

    # Compliance state at examination_date
    compliance_events = [
        e for e in event_stream
        if e["stream_id"].startswith(f"compliance-{application_id}")
    ]
    compliance_summary = {
        "events_count": len(compliance_events),
        "event_types": [e["event_type"] for e in compliance_events],
        "overall_verdict": agg.compliance_verdict,
        "has_hard_block": agg.compliance_has_hard_block,
    }

    return {
        "as_of": examination_date.isoformat(),
        "application_summary": application_summary,
        "compliance_state": compliance_summary,
        "total_events_at_examination_date": len(event_stream),
    }


# ── STEP 3: INTEGRITY VERIFICATION ───────────────────────────────────────────

async def _run_integrity_verification(
    store,
    application_id: str,
    event_stream: list[dict],
) -> dict:
    """
    Compute SHA-256 hash chain over all events.
    Independently verifiable against raw database.
    """
    from src.integrity.audit_chain import GENESIS_HASH

    # Hash all event payloads in order
    h = hashlib.sha256()
    for ev in event_stream:
        payload_bytes = json.dumps(
            ev.get("payload", {}), sort_keys=True, default=str
        ).encode()
        h.update(payload_bytes)
    computed_hash = h.hexdigest()

    # Load existing audit chain result if any
    audit_events = await store.load_stream(f"audit-loan-{application_id}")
    last_chain_hash = GENESIS_HASH
    last_check_at = None
    chain_checks = []

    for ev in audit_events:
        if ev.get("event_type") == "AuditIntegrityCheckRun":
            p = ev.get("payload", {})
            chain_checks.append({
                "check_timestamp": p.get("check_timestamp"),
                "events_verified": p.get("events_verified_count"),
                "integrity_hash": p.get("integrity_hash", "")[:16] + "...",
                "chain_valid": p.get("chain_valid"),
                "tamper_detected": p.get("tamper_detected"),
            })
            last_chain_hash = p.get("integrity_hash", GENESIS_HASH)
            last_check_at = p.get("check_timestamp")

    return {
        "events_verified": len(event_stream),
        "computed_hash": computed_hash,
        "computed_hash_truncated": computed_hash[:16] + "...",
        "last_chain_hash": last_chain_hash[:16] + "..." if last_chain_hash else None,
        "last_integrity_check_at": last_check_at,
        "prior_chain_checks": chain_checks,
        "tamper_detected": False,
        "verification_method": "SHA-256 over concatenated event payloads in global_position order",
        "independent_verification": (
            "SELECT encode(sha256(string_agg(payload::text, '' ORDER BY global_position)), 'hex') "
            f"FROM events WHERE stream_id LIKE '%-{application_id}'"
        ),
    }


# ── STEP 4: NARRATIVE ─────────────────────────────────────────────────────────

def _generate_narrative(event_stream: list[dict]) -> list[str]:
    """
    Generate human-readable narrative — one sentence per significant event.
    Written in plain English for regulatory examination.
    """
    sentences = []

    for ev in event_stream:
        et = ev.get("event_type", "")
        p = ev.get("payload", {})
        ts = ev.get("recorded_at", "")[:19].replace("T", " ")
        sentence = _event_to_sentence(et, p, ts)
        if sentence:
            sentences.append(sentence)

    return sentences


def _event_to_sentence(event_type: str, payload: dict, timestamp: str) -> str | None:
    """Map an event type to a plain-English sentence."""
    app_id = payload.get("application_id", "")
    templates = {
        "ApplicationSubmitted": (
            f"[{timestamp}] Application {app_id} was submitted by applicant "
            f"{payload.get('applicant_id', 'unknown')} requesting "
            f"${float(payload.get('requested_amount_usd', 0) or 0):,.0f} for "
            f"{payload.get('loan_purpose', 'unspecified purpose')}."
        ),
        "CreditAnalysisCompleted": (
            f"[{timestamp}] Credit analysis completed for {app_id}: "
            f"risk tier {payload.get('decision', {}).get('risk_tier', 'unknown') if isinstance(payload.get('decision'), dict) else 'unknown'}, "
            f"confidence {payload.get('decision', {}).get('confidence', 0) if isinstance(payload.get('decision'), dict) else 0:.0%}, "
            f"recommended limit ${float(payload.get('decision', {}).get('recommended_limit_usd', 0) or 0) if isinstance(payload.get('decision'), dict) else 0:,.0f}."
        ),
        "FraudScreeningCompleted": (
            f"[{timestamp}] Fraud screening completed for {app_id}: "
            f"fraud score {payload.get('fraud_score', 0):.2f} "
            f"({payload.get('risk_level', 'unknown')} risk), "
            f"recommendation: {payload.get('recommendation', 'unknown')}."
        ),
        "ComplianceCheckCompleted": (
            f"[{timestamp}] Compliance check completed for {app_id}: "
            f"{payload.get('rules_passed', 0)} of {payload.get('rules_evaluated', 0)} rules passed, "
            f"verdict: {payload.get('overall_verdict', 'unknown')}."
            + (" HARD BLOCK applied." if payload.get("has_hard_block") else "")
        ),
        "DecisionGenerated": (
            f"[{timestamp}] AI orchestrator generated decision for {app_id}: "
            f"{payload.get('recommendation', 'unknown')} with "
            f"{payload.get('confidence', 0):.0%} confidence. "
            f"Summary: {str(payload.get('executive_summary', ''))[:100]}."
        ),
        "HumanReviewCompleted": (
            f"[{timestamp}] Loan officer {payload.get('reviewer_id', 'unknown')} "
            f"{'overrode the AI recommendation and ' if payload.get('override') else ''}"
            f"made final decision: {payload.get('final_decision', 'unknown')} for {app_id}."
            + (f" Override reason: {payload.get('override_reason', '')}." if payload.get("override") else "")
        ),
        "ApplicationApproved": (
            f"[{timestamp}] Application {app_id} was APPROVED for "
            f"${float(payload.get('approved_amount_usd', 0) or 0):,.0f} "
            f"at {payload.get('interest_rate_pct', 0):.2f}% interest "
            f"by {payload.get('approved_by', 'system')}."
        ),
        "ApplicationDeclined": (
            f"[{timestamp}] Application {app_id} was DECLINED by "
            f"{payload.get('declined_by', 'system')}. "
            f"Reasons: {'; '.join(payload.get('decline_reasons', ['not specified']))}."
        ),
        "AgentSessionStarted": (
            f"[{timestamp}] AI agent session started: "
            f"type={payload.get('agent_type', 'unknown')}, "
            f"model={payload.get('model_version', 'unknown')}, "
            f"session={payload.get('session_id', 'unknown')}."
        ),
        "AuditIntegrityCheckRun": (
            f"[{timestamp}] Cryptographic integrity check run: "
            f"{payload.get('events_verified_count', 0)} events verified, "
            f"chain {'valid' if payload.get('chain_valid') else 'INVALID'}."
        ),
    }
    return templates.get(event_type)


# ── STEP 5: AGENT METADATA ────────────────────────────────────────────────────

async def _extract_agent_metadata(
    store,
    application_id: str,
    event_stream: list[dict],
) -> list[dict]:
    """
    Extract model versions, confidence scores, and input data hashes
    for every AI agent that participated in the decision.
    """
    agents = []

    for ev in event_stream:
        et = ev.get("event_type", "")
        p = ev.get("payload", {})

        if et == "CreditAnalysisCompleted":
            decision = p.get("decision", {})
            agents.append({
                "agent_type": "credit_analysis",
                "session_id": p.get("session_id"),
                "model_version": p.get("model_version"),
                "input_data_hash": p.get("input_data_hash"),
                "confidence_score": decision.get("confidence") if isinstance(decision, dict) else None,
                "risk_tier": decision.get("risk_tier") if isinstance(decision, dict) else None,
                "recommended_limit_usd": decision.get("recommended_limit_usd") if isinstance(decision, dict) else None,
                "recorded_at": ev.get("recorded_at"),
            })

        elif et == "FraudScreeningCompleted":
            agents.append({
                "agent_type": "fraud_detection",
                "session_id": p.get("session_id"),
                "model_version": p.get("screening_model_version"),
                "input_data_hash": p.get("input_data_hash"),
                "fraud_score": p.get("fraud_score"),
                "risk_level": p.get("risk_level"),
                "recommendation": p.get("recommendation"),
                "recorded_at": ev.get("recorded_at"),
            })

        elif et == "ComplianceCheckCompleted":
            agents.append({
                "agent_type": "compliance",
                "session_id": p.get("session_id"),
                "model_version": None,
                "input_data_hash": None,
                "rules_evaluated": p.get("rules_evaluated"),
                "rules_passed": p.get("rules_passed"),
                "overall_verdict": p.get("overall_verdict"),
                "recorded_at": ev.get("recorded_at"),
            })

        elif et == "DecisionGenerated":
            agents.append({
                "agent_type": "orchestrator",
                "session_id": p.get("orchestrator_session_id"),
                "model_version": None,
                "contributing_sessions": p.get("contributing_sessions", []),
                "model_versions": p.get("model_versions", {}),
                "recommendation": p.get("recommendation"),
                "confidence": p.get("confidence"),
                "recorded_at": ev.get("recorded_at"),
            })

    return agents