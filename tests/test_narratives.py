"""
tests/test_narratives.py
========================
Narrative scenario tests — the primary correctness gate.
All 5 tests drive a complete application through the real agent pipeline.

Run: pytest tests/test_narratives.py -v -s
"""
from __future__ import annotations
import sys, asyncio, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


# ─── TEST INFRASTRUCTURE ─────────────────────────────────────────────────────

class _MockContent:
    def __init__(self, text): self.text = text

class _MockUsage:
    input_tokens = 100; output_tokens = 80

class _MockResponse:
    def __init__(self, text):
        self.content = [_MockContent(text)]
        self.usage = _MockUsage()

class _MockMessages:
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self._idx = 0
    async def create(self, **_kw):
        text = self._responses[self._idx % len(self._responses)]
        self._idx += 1
        return _MockResponse(text)

class MockAnthropicClient:
    """Returns pre-built JSON strings without any network call."""
    def __init__(self, *responses):
        self.messages = _MockMessages(list(responses))


class MockRegistry:
    """In-memory read-only registry for tests."""
    def __init__(self, company=None, financials=None, flags=None, loans=None):
        self._company = company or {}
        self._financials = financials or []
        self._flags = flags or []
        self._loans = loans or []

    async def get_company(self, company_id):
        return self._company or {"company_id": company_id, "name": "Test Corp",
                                  "industry": "technology", "jurisdiction": "CA",
                                  "legal_type": "LLC", "founded_year": 2020,
                                  "employee_count": 50, "trajectory": "STABLE"}

    async def get_financial_history(self, company_id, years=None):
        return self._financials

    async def get_compliance_flags(self, company_id, active_only=False):
        return self._flags

    async def get_loan_relationships(self, company_id):
        return self._loans


def _make_store():
    from src.event_store import InMemoryEventStore
    return InMemoryEventStore()


async def _submit_app(store, app_id, applicant_id="COMP-TEST",
                      amount=500_000, purpose="working_capital"):
    """Write ApplicationSubmitted to the loan stream."""
    from src.commands.handlers import handle_submit_application
    await handle_submit_application(
        store,
        application_id=app_id,
        applicant_id=applicant_id,
        requested_amount_usd=amount,
        loan_purpose=purpose,
    )


async def _upload_docs(store, app_id, doc_ids=None):
    """Write DocumentUploaded events to the loan stream."""
    doc_ids = doc_ids or ["doc-is-001", "doc-bs-001"]
    ver = await store.stream_version(f"loan-{app_id}")
    events = [
        {
            "event_type": "DocumentUploaded", "event_version": 1,
            "payload": {
                "application_id": app_id,
                "document_id": did,
                "document_type": "income_statement" if i == 0 else "balance_sheet",
                "file_path": f"/data/{did}.pdf",
                "file_size_bytes": 102400,
                "uploaded_at": "2026-01-15T10:00:00",
            },
        }
        for i, did in enumerate(doc_ids)
    ]
    await store.append(f"loan-{app_id}", events, expected_version=ver)


async def _pre_populate_docpkg(store, app_id, missing_ebitda=False):
    """Pre-populate docpkg stream with ExtractionCompleted events."""
    is_facts = {
        "total_revenue": 3_500_000,
        "net_income": 420_000,
        "gross_profit": 1_200_000,
    }
    if not missing_ebitda:
        is_facts["ebitda"] = 600_000

    bs_facts = {
        "total_assets": 5_000_000,
        "total_liabilities": 2_500_000,
        "total_equity": 2_500_000,
        "current_assets": 1_200_000,
        "current_liabilities": 600_000,
    }

    events = [
        {
            "event_type": "ExtractionCompleted", "event_version": 1,
            "payload": {
                "package_id": f"pkg-{app_id}",
                "document_id": "doc-is-001",
                "document_type": "income_statement",
                "facts": is_facts,
                "tables_extracted": 3, "raw_text_length": 5000,
                "processing_ms": 800,
                "completed_at": "2026-01-15T10:05:00",
            },
        },
        {
            "event_type": "ExtractionCompleted", "event_version": 1,
            "payload": {
                "package_id": f"pkg-{app_id}",
                "document_id": "doc-bs-001",
                "document_type": "balance_sheet",
                "facts": bs_facts,
                "tables_extracted": 2, "raw_text_length": 4200,
                "processing_ms": 650,
                "completed_at": "2026-01-15T10:06:00",
            },
        },
    ]
    pkg_ver = await store.stream_version(f"docpkg-{app_id}")
    await store.append(f"docpkg-{app_id}", events, expected_version=pkg_ver)


async def _advance_to_credit_stage(store, app_id):
    """Submit app, upload docs, pre-populate docpkg, add PackageReadyForAnalysis + CreditAnalysisRequested."""
    await _submit_app(store, app_id)
    await _upload_docs(store, app_id)
    await _pre_populate_docpkg(store, app_id)
    # PackageReadyForAnalysis on docpkg stream
    await store.append(f"docpkg-{app_id}", [{
        "event_type": "PackageReadyForAnalysis", "event_version": 1,
        "payload": {"package_id": f"pkg-{app_id}", "application_id": app_id,
                    "documents_processed": 2, "has_quality_flags": False,
                    "quality_flag_count": 0, "ready_at": "2026-01-15T10:07:00"},
    }], expected_version=await store.stream_version(f"docpkg-{app_id}"))
    # CreditAnalysisRequested on loan stream
    await store.append(f"loan-{app_id}", [{
        "event_type": "CreditAnalysisRequested", "event_version": 1,
        "payload": {"application_id": app_id, "requested_at": "2026-01-15T10:07:00",
                    "requested_by": "doc_agent", "priority": "NORMAL"},
    }], expected_version=await store.stream_version(f"loan-{app_id}"))


async def _make_credit_agent(store, client=None, agent_id="agent-credit-001"):
    from agents.base_agent import CreditAnalysisAgent
    client = client or MockAnthropicClient(json.dumps({
        "risk_tier": "MEDIUM", "recommended_limit_usd": 400_000,
        "confidence": 0.78, "rationale": "Strong cash flow with moderate debt.",
        "key_concerns": ["debt_service_coverage"], "data_quality_caveats": [],
        "policy_overrides_applied": [],
    }))
    return CreditAnalysisAgent(
        agent_id=agent_id, agent_type="credit_analysis",
        store=store, registry=MockRegistry(), client=client,
    )


async def _advance_to_fraud_stage(store, app_id):
    """Run credit analysis, resulting in FraudScreeningRequested on loan stream."""
    await _advance_to_credit_stage(store, app_id)
    agent = await _make_credit_agent(store)
    await agent.process_application(app_id)


async def _advance_to_compliance_stage(store, app_id, registry=None):
    """Run everything up through fraud detection → ComplianceCheckRequested."""
    await _advance_to_fraud_stage(store, app_id)
    from agents.stub_agents import FraudDetectionAgent
    client = MockAnthropicClient(json.dumps({
        "fraud_score": 0.04, "risk_level": "LOW",
        "recommendation": "PROCEED", "anomalies": [],
    }))
    fraud_agent = FraudDetectionAgent(
        agent_id="agent-fraud-001", agent_type="fraud_detection",
        store=store, registry=registry or MockRegistry(), client=client,
    )
    await fraud_agent.process_application(app_id)


async def _advance_to_decision_stage(store, app_id, registry=None):
    """Run everything up through compliance → DecisionRequested."""
    await _advance_to_compliance_stage(store, app_id, registry=registry)
    from agents.stub_agents import ComplianceAgent
    compliance_agent = ComplianceAgent(
        agent_id="agent-comp-001", agent_type="compliance",
        store=store, registry=registry or MockRegistry(), client=None,
    )
    await compliance_agent.process_application(app_id)


# ─── NARRATIVE TESTS ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_narr01_concurrent_occ_collision():
    """
    NARR-01: Two CreditAnalysisAgent instances run simultaneously on the same app.
    Expected: exactly one CreditAnalysisCompleted in credit stream (not two),
              second agent gets OCC, reloads, retries successfully.
    """
    store = _make_store()
    await _advance_to_credit_stage(store, "APEX-N01")

    # Both agents compete to be first to write CreditAnalysisCompleted
    credit_json = json.dumps({
        "risk_tier": "MEDIUM", "recommended_limit_usd": 400_000,
        "confidence": 0.78, "rationale": "Solid financials.",
        "key_concerns": [], "data_quality_caveats": [], "policy_overrides_applied": [],
    })
    agent_a = await _make_credit_agent(
        store,
        client=MockAnthropicClient(credit_json),
        agent_id="agent-credit-A",
    )
    agent_b = await _make_credit_agent(
        store,
        client=MockAnthropicClient(credit_json),
        agent_id="agent-credit-B",
    )

    # Run both concurrently — OCC retry in _append_with_retry handles the collision
    await asyncio.gather(
        agent_a.process_application("APEX-N01"),
        agent_b.process_application("APEX-N01"),
        return_exceptions=True,
    )

    credit_events = await store.load_stream("credit-APEX-N01")
    completed = [e for e in credit_events if e["event_type"] == "CreditAnalysisCompleted"]

    # NARR-01 gate: exactly one credit result, not two
    assert len(completed) == 1, (
        f"Expected exactly 1 CreditAnalysisCompleted, got {len(completed)}: "
        f"{[e.get('payload', {}).get('session_id') for e in completed]}"
    )

    # FraudScreeningRequested must be on loan stream (agent wrote it)
    loan_events = await store.load_stream("loan-APEX-N01")
    fraud_reqs = [e for e in loan_events if e["event_type"] == "FraudScreeningRequested"]
    assert len(fraud_reqs) >= 1


@pytest.mark.asyncio
async def test_narr02_document_extraction_failure():
    """
    NARR-02: Income statement PDF with missing EBITDA line.
    Expected: QualityAssessmentCompleted with critical_missing_fields=['ebitda'],
              CreditAnalysisCompleted.confidence <= 0.75,
              CreditAnalysisCompleted.data_quality_caveats is non-empty.
    """
    store = _make_store()
    await _submit_app(store, "APEX-N02")
    await _upload_docs(store, "APEX-N02")
    # Pre-populate docpkg WITHOUT ebitda
    await _pre_populate_docpkg(store, "APEX-N02", missing_ebitda=True)

    # Doc processing agent — LLM returns that ebitda is missing
    qa_response = json.dumps({
        "overall_confidence": 0.60, "is_coherent": False,
        "critical_missing_fields": ["ebitda"],
        "anomalies": ["EBITDA not present in income statement"],
        "reextraction_recommended": True, "auditor_notes": "EBITDA missing.",
        "balance_sheet_balances": True,
    })
    from agents.stub_agents import DocumentProcessingAgent
    doc_agent = DocumentProcessingAgent(
        agent_id="agent-doc-001", agent_type="document_processing",
        store=store, registry=MockRegistry(), client=MockAnthropicClient(qa_response),
    )
    await doc_agent.process_application("APEX-N02")

    # Verify QualityAssessmentCompleted with missing ebitda
    pkg_events = await store.load_stream("docpkg-APEX-N02")
    qa_events = [e for e in pkg_events if e["event_type"] == "QualityAssessmentCompleted"]
    assert len(qa_events) >= 1
    qa_payload = qa_events[-1]["payload"]
    assert "ebitda" in qa_payload["critical_missing_fields"], (
        f"Expected ebitda in critical_missing_fields, got: {qa_payload['critical_missing_fields']}"
    )

    # Credit agent — mock LLM returns low confidence due to missing ebitda
    credit_response = json.dumps({
        "risk_tier": "MEDIUM", "recommended_limit_usd": 300_000,
        "confidence": 0.65,
        "rationale": "EBITDA unavailable, limiting confidence.",
        "key_concerns": ["missing_ebitda"],
        "data_quality_caveats": ["EBITDA not present — debt service coverage ratio unverifiable"],
        "policy_overrides_applied": [],
    })
    credit_agent = await _make_credit_agent(
        store, client=MockAnthropicClient(credit_response)
    )
    await credit_agent.process_application("APEX-N02")

    credit_events = await store.load_stream("credit-APEX-N02")
    completed = next((e for e in reversed(credit_events)
                      if e["event_type"] == "CreditAnalysisCompleted"), None)
    assert completed is not None
    decision = completed["payload"]["decision"]

    # NARR-02 gates
    confidence = float(decision["confidence"])
    assert confidence <= 0.75, f"Expected confidence <= 0.75, got {confidence}"
    caveats = decision.get("data_quality_caveats", [])
    assert len(caveats) > 0, "Expected non-empty data_quality_caveats"


@pytest.mark.asyncio
async def test_narr03_agent_crash_recovery():
    """
    NARR-03: FraudDetectionAgent crashes mid-session.
    Expected: only ONE FraudScreeningCompleted event in fraud stream,
              second AgentSessionStarted has context_source starting with 'prior_session_replay:'.
    """
    store = _make_store()
    await _advance_to_fraud_stage(store, "APEX-N03")

    # The advance_to_fraud_stage already ran a full credit agent and wrote FraudScreeningRequested.
    # Simulate a crashed fraud session by writing session events manually
    crashed_session_id = "sess-fra-crashed001"
    crashed_stream = f"agent-fraud_detection-{crashed_session_id}"
    crash_events = [
        {
            "event_type": "AgentSessionStarted", "event_version": 1,
            "payload": {
                "session_id": crashed_session_id, "agent_type": "fraud_detection",
                "agent_id": "agent-fraud-crashed", "application_id": "APEX-N03",
                "model_version": "fraud-v1", "context_source": "fresh",
                "context_token_count": 0, "started_at": "2026-01-15T10:10:00",
            },
        },
        {
            "event_type": "AgentNodeExecuted", "event_version": 1,
            "payload": {
                "session_id": crashed_session_id, "agent_type": "fraud_detection",
                "node_name": "validate_inputs", "node_sequence": 1,
                "input_keys": ["loan_stream"], "output_keys": ["fraud_screening_initiated"],
                "llm_called": False, "duration_ms": 45, "executed_at": "2026-01-15T10:10:01",
            },
        },
        {
            "event_type": "AgentSessionFailed", "event_version": 1,
            "payload": {
                "session_id": crashed_session_id, "agent_type": "fraud_detection",
                "application_id": "APEX-N03",
                "error_type": "RuntimeError",
                "error_message": "Simulated LLM timeout during cross-reference",
                "last_successful_node": "node_1",
                "recoverable": True,
                "failed_at": "2026-01-15T10:10:05",
            },
        },
    ]
    await store.append(crashed_stream, crash_events, expected_version=-1)

    # Recovery: new fraud agent started with recover_from_session
    from agents.stub_agents import FraudDetectionAgent
    client = MockAnthropicClient(json.dumps({
        "fraud_score": 0.04, "risk_level": "LOW",
        "recommendation": "PROCEED", "anomalies": [],
    }))
    recovery_agent = FraudDetectionAgent(
        agent_id="agent-fraud-recovery", agent_type="fraud_detection",
        store=store, registry=MockRegistry(), client=client,
    )
    await recovery_agent.process_application(
        "APEX-N03", recover_from_session=crashed_session_id
    )

    # NARR-03 gate 1: exactly one FraudScreeningCompleted
    fraud_events = await store.load_stream("fraud-APEX-N03")
    completed = [e for e in fraud_events if e["event_type"] == "FraudScreeningCompleted"]
    assert len(completed) == 1, (
        f"Expected exactly 1 FraudScreeningCompleted, got {len(completed)}"
    )

    # NARR-03 gate 2: recovery session has context_source starting with 'prior_session_replay:'
    recovery_stream = f"agent-fraud_detection-{recovery_agent.session_id}"
    recovery_events = await store.load_stream(recovery_stream)
    started = next((e for e in recovery_events if e["event_type"] == "AgentSessionStarted"), None)
    assert started is not None
    context_source = started["payload"]["context_source"]
    assert context_source.startswith("prior_session_replay:"), (
        f"Expected context_source to start with 'prior_session_replay:', got '{context_source}'"
    )
    assert crashed_session_id in context_source


@pytest.mark.asyncio
async def test_narr04_compliance_hard_block():
    """
    NARR-04: Montana applicant (jurisdiction='MT') triggers REG-003.
    Expected: ComplianceRuleFailed(rule_id='REG-003', is_hard_block=True),
              NO DecisionGenerated event,
              ApplicationDeclined with adverse_action_notice_required=True.
    """
    # Registry returns a Montana company
    mt_registry = MockRegistry(company={
        "company_id": "COMP-MT-001", "name": "Big Sky Ventures",
        "industry": "agriculture", "jurisdiction": "MT",
        "legal_type": "LLC", "founded_year": 2019,
        "employee_count": 25, "trajectory": "STABLE",
        "compliance_flags": [],
    })

    store = _make_store()
    await _advance_to_compliance_stage(store, "APEX-N04", registry=mt_registry)

    # Run ComplianceAgent with MT company
    from agents.stub_agents import ComplianceAgent
    compliance_agent = ComplianceAgent(
        agent_id="agent-comp-N04", agent_type="compliance",
        store=store, registry=mt_registry, client=None,
    )
    await compliance_agent.process_application("APEX-N04")

    # NARR-04 gate 1: ComplianceRuleFailed for REG-003 with is_hard_block=True
    compliance_events = await store.load_stream("compliance-APEX-N04")
    reg003_fail = next(
        (e for e in compliance_events
         if e["event_type"] == "ComplianceRuleFailed"
         and e["payload"]["rule_id"] == "REG-003"),
        None,
    )
    assert reg003_fail is not None, "Expected ComplianceRuleFailed for REG-003"
    assert reg003_fail["payload"]["is_hard_block"] is True

    # NARR-04 gate 2: NO DecisionGenerated or DecisionRequested
    loan_events = await store.load_stream("loan-APEX-N04")
    decision_events = [e for e in loan_events
                       if e["event_type"] in ("DecisionGenerated", "DecisionRequested")]
    assert len(decision_events) == 0, (
        f"Expected no decision events, found: {[e['event_type'] for e in decision_events]}"
    )

    # NARR-04 gate 3: ApplicationDeclined with adverse_action_notice_required=True
    declined = next(
        (e for e in loan_events if e["event_type"] == "ApplicationDeclined"), None
    )
    assert declined is not None, "Expected ApplicationDeclined on loan stream"
    assert declined["payload"]["adverse_action_notice_required"] is True


@pytest.mark.asyncio
async def test_narr05_human_override():
    """
    NARR-05: Orchestrator recommends DECLINE; human loan officer overrides to APPROVE.
    Expected: DecisionGenerated(recommendation='DECLINE'),
              HumanReviewCompleted(override=True, reviewer_id='LO-Sarah-Chen'),
              ApplicationApproved(approved_amount_usd=750000).
    """
    store = _make_store()
    await _advance_to_decision_stage(store, "APEX-N05")

    # Orchestrator — LLM mock returns DECLINE (will then be handled by human)
    from agents.stub_agents import DecisionOrchestratorAgent
    decline_json = json.dumps({
        "recommendation": "DECLINE",
        "confidence": 0.72,
        "approved_amount_usd": None,
        "executive_summary": "High debt ratio and limited collateral. Not recommended.",
        "key_risks": ["high_debt_ratio", "limited_collateral"],
    })
    orch_agent = DecisionOrchestratorAgent(
        agent_id="agent-orch-N05", agent_type="decision_orchestrator",
        store=store, registry=MockRegistry(), client=MockAnthropicClient(decline_json),
    )
    await orch_agent.process_application("APEX-N05")

    loan_events = await store.load_stream("loan-APEX-N05")

    # NARR-05 gate 1: DecisionGenerated with DECLINE
    decision_gen = next(
        (e for e in loan_events if e["event_type"] == "DecisionGenerated"), None
    )
    assert decision_gen is not None
    assert decision_gen["payload"]["recommendation"] == "DECLINE", (
        f"Expected DECLINE recommendation, got: {decision_gen['payload']['recommendation']}"
    )

    # Human loan officer overrides the decision
    from src.commands.handlers import handle_human_review_completed
    await handle_human_review_completed(
        store,
        application_id="APEX-N05",
        reviewer_id="LO-Sarah-Chen",
        override=True,
        original_recommendation="DECLINE",
        final_decision="APPROVE",
        override_reason="Strong character references and new collateral provided.",
        approved_amount_usd=750_000,
        conditions=["Quarterly financial reporting required", "Personal guarantee from CEO"],
    )

    # Reload after human review
    loan_events = await store.load_stream("loan-APEX-N05")

    # NARR-05 gate 2: HumanReviewCompleted with override=True, reviewer_id correct
    review_completed = next(
        (e for e in loan_events if e["event_type"] == "HumanReviewCompleted"), None
    )
    assert review_completed is not None
    assert review_completed["payload"]["override"] is True
    assert review_completed["payload"]["reviewer_id"] == "LO-Sarah-Chen"

    # NARR-05 gate 3: ApplicationApproved with correct amount and 2 conditions
    approved = next(
        (e for e in loan_events if e["event_type"] == "ApplicationApproved"), None
    )
    assert approved is not None
    approved_amount = float(str(approved["payload"]["approved_amount_usd"]).replace(",", ""))
    assert approved_amount == 750_000, (
        f"Expected approved_amount_usd=750000, got {approved_amount}"
    )
    conditions = approved["payload"].get("conditions", [])
    assert len(conditions) == 2, (
        f"Expected 2 conditions, got {len(conditions)}: {conditions}"
    )
