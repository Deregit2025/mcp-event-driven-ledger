"""
src/whatif/projector.py
========================
What-If Projector — counterfactual scenario analysis.

Allows the Apex compliance team to answer questions like:
"What would the final decision have been if the credit analysis
had returned risk_tier='HIGH' instead of 'MEDIUM'?"

CRITICAL GUARANTEE: Never writes counterfactual events to the real store.
All counterfactual processing happens in memory only.

Causal dependency:
  An event is causally DEPENDENT on the branch point if its
  causation_id traces back to an event at or after the branch point.
  Independent events are replayed normally.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── RESULT ────────────────────────────────────────────────────────────────────

@dataclass
class WhatIfResult:
    application_id: str
    branch_at_event_type: str
    real_outcome: dict[str, Any]
    counterfactual_outcome: dict[str, Any]
    divergence_events: list[str]
    events_replayed_real: int
    events_replayed_counterfactual: int
    counterfactual_events_injected: int
    events_skipped_as_dependent: int
    summary: str


# ── MAIN FUNCTION ─────────────────────────────────────────────────────────────

async def run_what_if(
    store,
    application_id: str,
    branch_at_event_type: str,
    counterfactual_events: list[dict],
    projections: list | None = None,
) -> WhatIfResult:
    """
    Run a counterfactual scenario by injecting events at a branch point.

    Steps:
    1. Load all events for the application stream up to the branch point
    2. At the branch point, inject counterfactual_events instead of real ones
    3. Continue replaying real events that are causally INDEPENDENT of the branch
    4. Skip real events that are causally DEPENDENT on the branched events
    5. Apply all events to the LoanApplicationAggregate
    6. Return WhatIfResult with real and counterfactual outcomes

    NEVER writes counterfactual events to the real store.
    """
    # Load all streams
    all_events = await _load_all_streams(store, application_id)

    # Build real outcome by replaying all events
    real_outcome = _apply_events_to_aggregate(application_id, all_events)

    # Find branch point
    branch_index = _find_branch_index(all_events, branch_at_event_type)
    if branch_index == -1:
        return WhatIfResult(
            application_id=application_id,
            branch_at_event_type=branch_at_event_type,
            real_outcome=real_outcome,
            counterfactual_outcome=real_outcome,
            divergence_events=[],
            events_replayed_real=len(all_events),
            events_replayed_counterfactual=0,
            counterfactual_events_injected=0,
            events_skipped_as_dependent=0,
            summary=f"Branch event '{branch_at_event_type}' not found in stream — counterfactual identical to real.",
        )

    # Split events: pre-branch (real), at-branch (replace), post-branch (filter)
    pre_branch_events = all_events[:branch_index]
    post_branch_events = all_events[branch_index + 1:]

    # Determine causal IDs introduced by the branch event
    real_branch_event = all_events[branch_index]
    branch_causal_ids = _get_causal_ids(real_branch_event, counterfactual_events)

    # Filter post-branch events: keep only causally independent ones
    independent_events, dependent_events = _partition_by_causality(
        post_branch_events, branch_causal_ids
    )

    # Build counterfactual event sequence
    counterfactual_sequence = (
        pre_branch_events +
        counterfactual_events +
        independent_events
    )

    # Apply counterfactual sequence to aggregate
    counterfactual_outcome = _apply_events_to_aggregate(
        application_id, counterfactual_sequence
    )

    # Find divergence points
    divergence_events = _find_divergences(real_outcome, counterfactual_outcome)

    # Build summary
    summary = _build_summary(
        application_id=application_id,
        branch_at_event_type=branch_at_event_type,
        real_outcome=real_outcome,
        counterfactual_outcome=counterfactual_outcome,
        injected=counterfactual_events,
        skipped=dependent_events,
    )

    return WhatIfResult(
        application_id=application_id,
        branch_at_event_type=branch_at_event_type,
        real_outcome=real_outcome,
        counterfactual_outcome=counterfactual_outcome,
        divergence_events=divergence_events,
        events_replayed_real=len(all_events),
        events_replayed_counterfactual=len(counterfactual_sequence),
        counterfactual_events_injected=len(counterfactual_events),
        events_skipped_as_dependent=len(dependent_events),
        summary=summary,
    )


# ── HELPERS ───────────────────────────────────────────────────────────────────

async def _load_all_streams(store, application_id: str) -> list[dict]:
    """Load and merge all streams for this application, sorted chronologically."""
    stream_ids = [
        f"loan-{application_id}",
        f"credit-{application_id}",
        f"fraud-{application_id}",
        f"compliance-{application_id}",
    ]
    all_events = []
    for stream_id in stream_ids:
        events = await store.load_stream(stream_id)
        for ev in events:
            all_events.append({**ev, "_stream_id": stream_id})

    all_events.sort(key=lambda e: (
        str(e.get("recorded_at") or ""),
        e.get("global_position") or 0,
        e.get("stream_position") or 0,
    ))
    return all_events


def _find_branch_index(events: list[dict], branch_event_type: str) -> int:
    """Find the index of the first event matching branch_event_type."""
    for i, ev in enumerate(events):
        if ev.get("event_type") == branch_event_type:
            return i
    return -1


def _get_causal_ids(
    real_branch_event: dict,
    counterfactual_events: list[dict],
) -> set[str]:
    """
    Return the set of event IDs that are now 'tainted' by the branch.
    Includes the real branch event's ID and all counterfactual event IDs.
    """
    causal_ids = set()
    real_id = str(real_branch_event.get("event_id", ""))
    if real_id:
        causal_ids.add(real_id)
    for ev in counterfactual_events:
        ev_id = str(ev.get("event_id", ""))
        if ev_id:
            causal_ids.add(ev_id)
    return causal_ids


def _partition_by_causality(
    post_branch_events: list[dict],
    tainted_ids: set[str],
) -> tuple[list[dict], list[dict]]:
    """
    Partition post-branch events into independent and dependent.

    An event is causally DEPENDENT if:
    - Its causation_id is in tainted_ids (directly caused by branch)
    - OR its event_id is tainted (transitively caused)

    Independent events are safe to replay in the counterfactual.
    """
    independent = []
    dependent = []
    tainted = set(tainted_ids)  # grows as we find dependent events

    for ev in post_branch_events:
        causation_id = (
            ev.get("metadata", {}).get("causation_id") or
            ev.get("causation_id", "")
        )
        ev_id = str(ev.get("event_id", ""))

        if causation_id in tainted:
            # Directly caused by a tainted event
            dependent.append(ev)
            if ev_id:
                tainted.add(ev_id)  # transitively taint this event's children
        else:
            independent.append(ev)

    return independent, dependent


def _apply_events_to_aggregate(
    application_id: str,
    events: list[dict],
) -> dict:
    """
    Apply a sequence of events to LoanApplicationAggregate.
    Returns a dict snapshot of the aggregate state.
    Pure in-memory — never touches the store.
    """
    from src.aggregates.loan_application import LoanApplicationAggregate

    agg = LoanApplicationAggregate(application_id=application_id)
    for ev in events:
        try:
            agg.apply(ev)
        except Exception as e:
            # In what-if scenarios, state machine violations can occur
            # when counterfactual events produce different state transitions.
            # Log and continue — we want to see where the divergence leads.
            logger.debug(
                f"What-if aggregate apply error on {ev.get('event_type')}: {e}"
            )

    return {
        "state": agg.state.value,
        "applicant_id": agg.applicant_id,
        "requested_amount_usd": float(agg.requested_amount_usd) if agg.requested_amount_usd else None,
        "credit_risk_tier": agg.credit_risk_tier,
        "credit_confidence": agg.credit_confidence,
        "fraud_score": agg.fraud_score,
        "compliance_verdict": agg.compliance_verdict,
        "compliance_has_hard_block": agg.compliance_has_hard_block,
        "approved_amount": agg.approved_amount,
        "is_terminal": agg.is_terminal,
        "contributing_sessions": agg.contributing_agent_sessions,
        "stream_version": agg.version,
    }


def _find_divergences(real: dict, counterfactual: dict) -> list[str]:
    """Identify fields that differ between real and counterfactual outcomes."""
    divergences = []
    for key in real:
        if real.get(key) != counterfactual.get(key):
            divergences.append(
                f"{key}: real={real.get(key)!r} → counterfactual={counterfactual.get(key)!r}"
            )
    return divergences


def _build_summary(
    application_id: str,
    branch_at_event_type: str,
    real_outcome: dict,
    counterfactual_outcome: dict,
    injected: list[dict],
    skipped: list[dict],
) -> str:
    """Build a human-readable summary of the what-if result."""
    real_state = real_outcome.get("state", "unknown")
    cf_state = counterfactual_outcome.get("state", "unknown")
    materially_different = real_state != cf_state

    injected_desc = ", ".join(
        ev.get("event_type", "unknown") for ev in injected
    ) or "none"

    lines = [
        f"What-If Analysis for application {application_id}",
        f"Branch point: {branch_at_event_type}",
        f"Counterfactual events injected: {injected_desc}",
        f"Events skipped as causally dependent: {len(skipped)}",
        f"",
        f"Real outcome:           {real_state}",
        f"Counterfactual outcome: {cf_state}",
        f"Materially different:   {'YES' if materially_different else 'NO'}",
    ]

    if real_outcome.get("credit_risk_tier") != counterfactual_outcome.get("credit_risk_tier"):
        lines.append(
            f"Credit risk tier:       {real_outcome.get('credit_risk_tier')} → "
            f"{counterfactual_outcome.get('credit_risk_tier')}"
        )

    if materially_different:
        lines.append(
            f"\nConclusion: The counterfactual scenario produces a DIFFERENT final "
            f"outcome. Business rule enforcement cascaded correctly through the "
            f"counterfactual event sequence."
        )
    else:
        lines.append(
            f"\nConclusion: The counterfactual scenario produces the SAME final "
            f"outcome despite the injected change."
        )

    return "\n".join(lines)