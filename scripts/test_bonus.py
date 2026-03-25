"""
scripts/test_bonus.py
======================
Smoke test for Phase 6 bonus deliverables:
  - generate_regulatory_package()
  - run_what_if()

Run: python scripts/test_bonus.py
"""
import asyncio
from src.event_store import InMemoryEventStore
from src.upcasting.upcasters import registry
from src.mcp.tools import LedgerToolExecutor
from src.regulatory.package import generate_regulatory_package
from src.whatif.projector import run_what_if


async def run_lifecycle(store, app_id: str):
    """Run a full loan lifecycle via MCP tools."""
    tools = LedgerToolExecutor(store)

    await tools.execute("ledger_submit_application", {
        "application_id": app_id,
        "applicant_id": "COMP-001",
        "requested_amount_usd": 500000,
        "loan_purpose": "working_capital",
    })
    await tools.execute("ledger_start_agent_session", {
        "agent_type": "credit_analysis",
        "session_id": "sess-c-01",
        "agent_id": "agent-c-01",
        "application_id": app_id,
        "model_version": "claude-sonnet-4-6",
    })
    await tools.execute("ledger_record_credit_analysis", {
        "application_id": app_id,
        "session_id": "sess-c-01",
        "risk_tier": "MEDIUM",
        "recommended_limit_usd": 450000,
        "confidence": 0.85,
        "rationale": "Strong financials, moderate risk",
        "model_version": "claude-sonnet-4-6",
    })
    await tools.execute("ledger_start_agent_session", {
        "agent_type": "fraud_detection",
        "session_id": "sess-f-01",
        "agent_id": "agent-f-01",
        "application_id": app_id,
        "model_version": "claude-sonnet-4-6",
    })
    await tools.execute("ledger_record_fraud_screening", {
        "application_id": app_id,
        "session_id": "sess-f-01",
        "fraud_score": 0.1,
        "risk_level": "LOW",
        "recommendation": "APPROVE",
        "screening_model_version": "claude-sonnet-4-6",
    })
    await tools.execute("ledger_start_agent_session", {
        "agent_type": "compliance",
        "session_id": "sess-co-01",
        "agent_id": "agent-co-01",
        "application_id": app_id,
        "model_version": "claude-sonnet-4-6",
    })
    await tools.execute("ledger_record_compliance_check", {
        "application_id": app_id,
        "session_id": "sess-co-01",
        "rules_evaluated": 5,
        "rules_passed": 5,
        "rules_failed": 0,
        "has_hard_block": False,
        "overall_verdict": "CLEAR",
    })
    await tools.execute("ledger_start_agent_session", {
        "agent_type": "orchestrator",
        "session_id": "sess-o-01",
        "agent_id": "agent-o-01",
        "application_id": app_id,
        "model_version": "claude-sonnet-4-6",
    })
    await tools.execute("ledger_generate_decision", {
        "application_id": app_id,
        "orchestrator_session_id": "sess-o-01",
        "recommendation": "APPROVE",
        "confidence": 0.85,
        "executive_summary": "All checks passed. Low fraud, clear compliance, medium credit risk.",
    })
    await tools.execute("ledger_record_human_review", {
        "application_id": app_id,
        "reviewer_id": "HUMAN-001",
        "override": False,
        "original_recommendation": "APPROVE",
        "final_decision": "APPROVE",
        "approved_amount_usd": 450000,
    })


async def main():
    app_id = "APEX-BONUS-01"
    store = InMemoryEventStore(upcaster_registry=registry)

    print("Running full lifecycle...")
    await run_lifecycle(store, app_id)
    print("Lifecycle complete.\n")

    # ── TEST 1: Regulatory Package ────────────────────────────────────────────
    print("=" * 60)
    print("TEST 1: Regulatory Examination Package")
    print("=" * 60)

    pkg = await generate_regulatory_package(store, app_id)

    print(f"Application ID:     {pkg.application_id}")
    print(f"Events in stream:   {len(pkg.event_stream)}")
    print(f"Narrative lines:    {len(pkg.narrative)}")
    print(f"Agent metadata:     {len(pkg.agent_metadata)} agents")
    print(f"Package hash:       {pkg.package_hash[:16]}...")
    print(f"Chain valid:        {pkg.integrity_verification.get('tamper_detected') == False}")
    print()
    print("Narrative:")
    for line in pkg.narrative:
        print(f"  {line}")
    print()
    print("Agent metadata:")
    for agent in pkg.agent_metadata:
        print(f"  {agent['agent_type']}: model={agent.get('model_version')}, session={agent.get('session_id')}")

    assert len(pkg.event_stream) >= 7, "Expected at least 7 events"
    assert len(pkg.narrative) >= 5, "Expected at least 5 narrative sentences"
    assert len(pkg.agent_metadata) >= 3, "Expected at least 3 agents"
    assert pkg.package_hash, "Package hash must be non-empty"
    print("\n✅ Regulatory package test PASSED\n")

    # ── TEST 2: What-If Projector ─────────────────────────────────────────────
    print("=" * 60)
    print("TEST 2: What-If Counterfactual (MEDIUM → HIGH risk tier)")
    print("=" * 60)

    # Counterfactual: credit analysis returns HIGH instead of MEDIUM
    counterfactual_events = [{
        "event_type": "CreditAnalysisCompleted",
        "event_version": 2,
        "payload": {
            "application_id": app_id,
            "session_id": "sess-c-01",
            "decision": {
                "risk_tier": "HIGH",
                "recommended_limit_usd": 200000,
                "confidence": 0.75,
                "rationale": "High risk — counterfactual scenario",
                "key_concerns": ["poor debt service coverage"],
                "data_quality_caveats": [],
                "policy_overrides_applied": [],
            },
            "model_version": "claude-sonnet-4-6",
            "input_data_hash": "counterfactual-hash",
        },
        "metadata": {},
    }]

    result = await run_what_if(
        store=store,
        application_id=app_id,
        branch_at_event_type="CreditAnalysisCompleted",
        counterfactual_events=counterfactual_events,
    )

    print(f"Branch point:           {result.branch_at_event_type}")
    print(f"Events in real:         {result.events_replayed_real}")
    print(f"Events in counterfactual: {result.events_replayed_counterfactual}")
    print(f"Counterfactual injected: {result.counterfactual_events_injected}")
    print(f"Events skipped:         {result.events_skipped_as_dependent}")
    print()
    print(f"Real outcome:           {result.real_outcome['state']}")
    print(f"Counterfactual outcome: {result.counterfactual_outcome['state']}")
    print(f"Real risk tier:         {result.real_outcome['credit_risk_tier']}")
    print(f"Counterfactual tier:    {result.counterfactual_outcome['credit_risk_tier']}")
    print(f"Divergences found:      {len(result.divergence_events)}")
    print()
    print("Divergences:")
    for d in result.divergence_events:
        print(f"  {d}")
    print()
    print("Summary:")
    print(result.summary)

    assert result.real_outcome["credit_risk_tier"] == "MEDIUM", "Real should be MEDIUM"
    assert result.counterfactual_outcome["credit_risk_tier"] == "HIGH", "Counterfactual should be HIGH"
    assert len(result.divergence_events) > 0, "Should have divergences"
    print("\n✅ What-if projector test PASSED\n")

    print("=" * 60)
    print("ALL BONUS TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())