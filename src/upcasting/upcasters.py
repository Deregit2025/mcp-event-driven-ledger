"""
src/upcasting/upcasters.py
===========================
The two required upcasters for Apex Ledger.

Both upcasters are pure functions — no IO, no database calls, no side effects.
They transform old event payloads in memory at read time.
The database rows are NEVER modified — immutability is guaranteed.

Inference strategy:
  - Use sentinel values rather than null where meaning is known
  - Use null where a fabricated value would corrupt calculations
  - Mark inferred values explicitly (e.g. '-inferred' suffix)
"""
from __future__ import annotations
from src.upcasting.registry import UpcasterRegistry

# Global registry — import this and pass to EventStore
registry = UpcasterRegistry()


# ── UPCASTER 1 — CreditAnalysisCompleted v1 → v2 ─────────────────────────────
# v2 adds: model_versions (dict), regulatory_basis (list)
# v1 had: model_version (plain string)

@registry.upcaster("CreditAnalysisCompleted", from_version=1, to_version=2)
def upcast_credit_analysis_v1_to_v2(payload: dict) -> dict:
    """
    Transforms CreditAnalysisCompleted from v1 to v2.

    Changes:
      - model_version (str) → model_versions (dict)
      - regulatory_basis added (inferred from APRA-2024)

    Inference rules:
      - model_versions: use existing model_version string if present,
        otherwise use sentinel 'legacy-pre-2026'
      - regulatory_basis: use 'APRA-2024-inferred' suffix to mark as inferred
        (not fabricated — we know APRA-2024 applied, just cannot prove it
        from the event data alone)
    """
    payload = dict(payload)  # copy — never mutate original

    # Build model_versions dict from old model_version string
    if "model_versions" not in payload:
        model_version = payload.get("model_version", "legacy-pre-2026")
        payload["model_versions"] = {
            "credit_analysis": model_version or "legacy-pre-2026"
        }

    # Add regulatory_basis — inferred, not fabricated
    if "regulatory_basis" not in payload:
        payload["regulatory_basis"] = ["APRA-2024-inferred"]

    # confidence_score intentionally left as-is (null if missing)
    # Never fabricate a confidence value — it is used in business rule 4
    # A fabricated 0.75 would silently corrupt AgentPerformanceLedger averages

    return payload


# ── UPCASTER 2 — DecisionGenerated v1 → v2 ───────────────────────────────────
# v2 adds: model_versions (dict tracking all contributing models)
# v1 had no model tracking at all

@registry.upcaster("DecisionGenerated", from_version=1, to_version=2)
def upcast_decision_generated_v1_to_v2(payload: dict) -> dict:
    """
    Transforms DecisionGenerated from v1 to v2.

    Changes:
      - model_versions (dict) added

    Inference rules:
      - If contributing_sessions exist, store them as '_requires_lookup'
        sentinel — the caller can resolve model versions by loading each
        session stream. Upcasters are synchronous so cannot do async lookups.
      - If no contributing sessions, use 'legacy-pre-2026' sentinel.

    Why sentinel instead of null:
      - Null would suggest model versions are unknown
      - Sentinel '_requires_lookup' communicates that they ARE knowable
        via session streams — just not resolvable in a sync pure function
    """
    payload = dict(payload)  # copy — never mutate original

    if "model_versions" not in payload:
        contributing = payload.get("contributing_sessions", [])
        if contributing:
            # Sentinel: caller must look up session streams to resolve
            payload["model_versions"] = {
                "_requires_lookup": contributing
            }
        else:
            # No contributing sessions recorded — pre-versioning legacy
            payload["model_versions"] = {
                "orchestrator": "legacy-pre-2026"
            }

    return payload