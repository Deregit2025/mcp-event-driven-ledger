"""
scripts/demo_narr05.py
======================
Live demo of NARR-05: Human Override scenario.

  Orchestrator recommends DECLINE due to high debt ratio.
  Loan officer LO-Sarah-Chen overrides to APPROVE with conditions.

Demonstrates:
  - Full agent pipeline (credit → fraud → compliance → decision)
  - DecisionGenerated with recommendation=DECLINE
  - HumanReviewCompleted with override=True
  - ApplicationApproved with amount + conditions

Usage:
    python scripts/demo_narr05.py
    python scripts/demo_narr05.py --verbose
    python scripts/demo_narr05.py --real-llm   # uses ANTHROPIC_API_KEY
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv()

# ── ANSI colours ──────────────────────────────────────────────────────────────
RESET  = "\033[0m"; BOLD   = "\033[1m"
GREEN  = "\033[32m"; CYAN   = "\033[36m"
YELLOW = "\033[33m"; RED    = "\033[31m"
DIM    = "\033[2m";  MAGENTA = "\033[35m"

APP_ID = "APEX-N05-DEMO"


# ── MOCK INFRASTRUCTURE ────────────────────────────────────────────────────────

class _MockContent:
    def __init__(self, t): self.text = t
class _MockUsage:
    input_tokens = 150; output_tokens = 100
class _MockResponse:
    def __init__(self, t):
        self.content = [_MockContent(t)]; self.usage = _MockUsage()
class _MockMessages:
    def __init__(self, r):
        self._r = list(r); self._i = 0
    async def create(self, **_):
        t = self._r[self._i % len(self._r)]; self._i += 1
        return _MockResponse(t)
class MockAnthropicClient:
    def __init__(self, *r): self.messages = _MockMessages(list(r))

class MockRegistry:
    async def get_company(self, cid):
        return {"company_id": cid, "name": "Pacific Rim Trading Co.", "industry": "import_export",
                "jurisdiction": "CA", "legal_type": "LLC", "founded_year": 2019,
                "employee_count": 42, "trajectory": "GROWTH"}
    async def get_financial_history(self, cid, years=None): return []
    async def get_compliance_flags(self, cid, active_only=False): return []
    async def get_loan_relationships(self, cid): return []


# ── HELPERS ────────────────────────────────────────────────────────────────────

def hdr(title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'━' * 62}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'━' * 62}{RESET}")

def ok(msg: str) -> None:  print(f"  {GREEN}✓{RESET}  {msg}")
def info(msg: str) -> None: print(f"     {DIM}{msg}{RESET}")
def warn(msg: str) -> None: print(f"  {YELLOW}⚑{RESET}  {msg}")
def step(msg: str) -> None: print(f"\n  {MAGENTA}▶{RESET}  {BOLD}{msg}{RESET}")


async def _advance_to_credit(store) -> None:
    """Submit → upload docs → pre-populate docpkg → add CreditAnalysisRequested."""
    from src.commands.handlers import handle_submit_application

    await handle_submit_application(
        store, application_id=APP_ID,
        applicant_id="COMP-PRT-001",
        requested_amount_usd=750_000,
        loan_purpose="acquisition",
        loan_term_months=84,
        submission_channel="broker",
    )
    ok(f"ApplicationSubmitted  loan-{APP_ID}")

    # Upload docs
    loan_ver = await store.stream_version(f"loan-{APP_ID}")
    await store.append(f"loan-{APP_ID}", [
        {"event_type": "DocumentUploaded", "event_version": 1, "payload": {
            "application_id": APP_ID, "document_id": "doc-is-001",
            "document_type": "income_statement", "file_path": "/data/doc-is-001.pdf",
            "file_size_bytes": 102400, "uploaded_at": "2026-01-15T10:00:00"}},
        {"event_type": "DocumentUploaded", "event_version": 1, "payload": {
            "application_id": APP_ID, "document_id": "doc-bs-001",
            "document_type": "balance_sheet", "file_path": "/data/doc-bs-001.pdf",
            "file_size_bytes": 81920, "uploaded_at": "2026-01-15T10:01:00"}},
    ], expected_version=loan_ver)
    ok("2 × DocumentUploaded")

    # Pre-populate docpkg stream (simulates doc pipeline already ran)
    pkg_stream = f"docpkg-{APP_ID}"
    await store.append(pkg_stream, [
        {"event_type": "ExtractionCompleted", "event_version": 1, "payload": {
            "package_id": f"pkg-{APP_ID}", "document_id": "doc-is-001",
            "document_type": "income_statement",
            "facts": {"total_revenue": 4_200_000, "net_income": 310_000,
                      "ebitda": 520_000, "gross_profit": 1_400_000},
            "tables_extracted": 3, "raw_text_length": 5000,
            "processing_ms": 800, "completed_at": "2026-01-15T10:05:00"}},
        {"event_type": "ExtractionCompleted", "event_version": 1, "payload": {
            "package_id": f"pkg-{APP_ID}", "document_id": "doc-bs-001",
            "document_type": "balance_sheet",
            "facts": {"total_assets": 6_000_000, "total_liabilities": 4_200_000,
                      "total_equity": 1_800_000, "current_assets": 1_100_000,
                      "current_liabilities": 800_000},
            "tables_extracted": 2, "raw_text_length": 4200,
            "processing_ms": 650, "completed_at": "2026-01-15T10:06:00"}},
    ], expected_version=await store.stream_version(pkg_stream))
    ok("ExtractionCompleted events pre-populated (IS + BS)")

    # PackageReadyForAnalysis
    await store.append(pkg_stream, [{
        "event_type": "PackageReadyForAnalysis", "event_version": 1,
        "payload": {"package_id": f"pkg-{APP_ID}", "application_id": APP_ID,
                    "documents_processed": 2, "has_quality_flags": False,
                    "quality_flag_count": 0, "ready_at": "2026-01-15T10:07:00"},
    }], expected_version=await store.stream_version(pkg_stream))

    # CreditAnalysisRequested
    await store.append(f"loan-{APP_ID}", [{
        "event_type": "CreditAnalysisRequested", "event_version": 1,
        "payload": {"application_id": APP_ID, "requested_at": "2026-01-15T10:07:00",
                    "requested_by": "doc_agent", "priority": "NORMAL"},
    }], expected_version=await store.stream_version(f"loan-{APP_ID}"))
    ok("PackageReadyForAnalysis + CreditAnalysisRequested written")


# ── MAIN DEMO ──────────────────────────────────────────────────────────────────

async def run(args) -> None:
    from src.event_store import InMemoryEventStore
    from agents.base_agent import CreditAnalysisAgent
    from agents.stub_agents import FraudDetectionAgent, ComplianceAgent, DecisionOrchestratorAgent
    from src.commands.handlers import handle_human_review_completed
    from src.mcp.server import create_server

    USE_REAL_LLM = args.real_llm and bool(os.getenv("ANTHROPIC_API_KEY"))

    def _client(*responses):
        if USE_REAL_LLM:
            from anthropic import AsyncAnthropic
            return AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        return MockAnthropicClient(*responses)

    print(f"\n{BOLD}{'═' * 62}{RESET}")
    print(f"{BOLD}  NARR-05 DEMO — Human Override: DECLINE → APPROVE{RESET}")
    print(f"{BOLD}  Application: {APP_ID}{RESET}")
    print(f"{BOLD}  LLM: {'REAL (Anthropic Claude)' if USE_REAL_LLM else 'MOCK'}{RESET}")
    print(f"{BOLD}{'═' * 62}{RESET}")

    store = InMemoryEventStore()
    registry = MockRegistry()
    t_start = time.time()

    # ── Setup ──────────────────────────────────────────────────────────────────
    hdr("Step 1 — Submit & Prepare Application")
    await _advance_to_credit(store)

    # ── Credit Analysis ────────────────────────────────────────────────────────
    hdr("Step 2 — Credit Analysis")
    step("Running CreditAnalysisAgent…")
    credit_json = json.dumps({
        "risk_tier": "HIGH",
        "recommended_limit_usd": 600_000,
        "confidence": 0.72,
        "rationale": (
            "High leverage ratio (debt/assets=0.70) raises repayment concern. "
            "EBITDA coverage of 0.69x is below the 1.0x threshold. "
            "Revenue growth is positive but insufficient to offset leverage risk."
        ),
        "key_concerns": ["high_debt_ratio", "low_ebitda_coverage", "limited_equity_cushion"],
        "data_quality_caveats": [],
        "policy_overrides_applied": [],
    })
    credit_agent = CreditAnalysisAgent(
        agent_id="agent-credit-N05", agent_type="credit_analysis",
        store=store, registry=registry, client=_client(credit_json),
    )
    t = time.time()
    await credit_agent.process_application(APP_ID)
    credit_events = await store.load_stream(f"credit-{APP_ID}")
    completed = next((e for e in reversed(credit_events)
                      if e["event_type"] == "CreditAnalysisCompleted"), None)
    d = completed["payload"]["decision"] if completed else {}
    ok(f"CreditAnalysisCompleted  ({int((time.time()-t)*1000)}ms)")
    info(f"risk_tier={d.get('risk_tier')}  confidence={d.get('confidence', 0):.0%}")
    info(f"key_concerns={d.get('key_concerns', [])}")
    warn("⟶ HIGH risk — orchestrator will likely recommend DECLINE")

    # ── Fraud Detection ────────────────────────────────────────────────────────
    hdr("Step 3 — Fraud Detection")
    step("Running FraudDetectionAgent…")
    fraud_json = json.dumps({
        "fraud_score": 0.06, "risk_level": "LOW",
        "recommendation": "PROCEED", "anomalies": [],
    })
    fraud_agent = FraudDetectionAgent(
        agent_id="agent-fraud-N05", agent_type="fraud_detection",
        store=store, registry=registry, client=_client(fraud_json),
    )
    t = time.time()
    await fraud_agent.process_application(APP_ID)
    fraud_events = await store.load_stream(f"fraud-{APP_ID}")
    fsc = next((e for e in reversed(fraud_events)
                if e["event_type"] == "FraudScreeningCompleted"), None)
    ok(f"FraudScreeningCompleted  ({int((time.time()-t)*1000)}ms)")
    if fsc:
        info(f"fraud_score={fsc['payload'].get('fraud_score')}  risk={fsc['payload'].get('risk_level')}")

    # ── Compliance ────────────────────────────────────────────────────────────
    hdr("Step 4 — Compliance Check")
    step("Running ComplianceAgent (jurisdiction=CA — all rules should pass)…")
    comp_agent = ComplianceAgent(
        agent_id="agent-comp-N05", agent_type="compliance",
        store=store, registry=registry, client=None,
    )
    t = time.time()
    await comp_agent.process_application(APP_ID)
    comp_events = await store.load_stream(f"compliance-{APP_ID}")
    rules_passed = sum(1 for e in comp_events if e["event_type"] == "ComplianceRulePassed")
    rules_noted  = sum(1 for e in comp_events if e["event_type"] == "ComplianceRuleNoted")
    ok(f"ComplianceCheckCompleted  ({int((time.time()-t)*1000)}ms)")
    info(f"rules_passed={rules_passed}  rules_noted={rules_noted}  hard_block=False")

    # ── Decision Orchestrator ──────────────────────────────────────────────────
    hdr("Step 5 — Decision Orchestration (expected: DECLINE)")
    step("Running DecisionOrchestratorAgent…")
    decline_json = json.dumps({
        "recommendation": "DECLINE",
        "confidence": 0.72,
        "approved_amount_usd": None,
        "executive_summary": (
            "Despite clean fraud and compliance records, the applicant's HIGH credit risk tier "
            "and debt/asset ratio of 0.70 exceed Apex's policy thresholds for acquisition lending. "
            "EBITDA coverage of 0.69x creates meaningful repayment risk over the 84-month term. "
            "Recommendation: DECLINE."
        ),
        "key_risks": ["high_debt_ratio", "low_ebitda_coverage", "acquisition_risk"],
    })
    orch_agent = DecisionOrchestratorAgent(
        agent_id="agent-orch-N05", agent_type="decision_orchestrator",
        store=store, registry=registry, client=_client(decline_json),
    )
    t = time.time()
    await orch_agent.process_application(APP_ID)
    ms = int((time.time() - t) * 1000)

    loan_events = await store.load_stream(f"loan-{APP_ID}")
    decision_gen = next(
        (e for e in loan_events if e["event_type"] == "DecisionGenerated"), None
    )
    assert decision_gen is not None, "DecisionGenerated not found!"
    rec = decision_gen["payload"]["recommendation"]
    ok(f"DecisionGenerated  ({ms}ms)")
    info(f"recommendation={rec}  confidence={decision_gen['payload'].get('confidence', 0):.0%}")
    warn(f"⟶ Orchestrator recommendation: {RED}{BOLD}{rec}{RESET}")

    # ── Human Override ─────────────────────────────────────────────────────────
    hdr("Step 6 — Human Override by Loan Officer Sarah Chen")
    step("LO-Sarah-Chen reviews and OVERRIDES to APPROVE…")
    info("Reason: Strong character references + new real-estate collateral provided.")
    info("Conditions: Quarterly financial reporting + Personal guarantee from CEO.")

    await handle_human_review_completed(
        store,
        application_id=APP_ID,
        reviewer_id="LO-Sarah-Chen",
        override=True,
        original_recommendation="DECLINE",
        final_decision="APPROVE",
        override_reason=(
            "Applicant provided additional real-estate collateral (assessed $1.2M) "
            "and strong character references from two blue-chip clients. "
            "Revised LTV is acceptable. Board approval obtained."
        ),
        approved_amount_usd=750_000,
        conditions=[
            "Quarterly financial reporting required for loan duration",
            "Personal guarantee from CEO required at closing",
        ],
    )

    # ── Verify final state ─────────────────────────────────────────────────────
    loan_events = await store.load_stream(f"loan-{APP_ID}")
    review_completed = next(
        (e for e in loan_events if e["event_type"] == "HumanReviewCompleted"), None
    )
    approved = next(
        (e for e in loan_events if e["event_type"] == "ApplicationApproved"), None
    )

    assert review_completed is not None
    assert review_completed["payload"]["override"] is True
    assert review_completed["payload"]["reviewer_id"] == "LO-Sarah-Chen"
    assert approved is not None
    assert float(str(approved["payload"]["approved_amount_usd"])) == 750_000.0

    ok("HumanReviewCompleted  override=True  reviewer=LO-Sarah-Chen")
    ok(f"ApplicationApproved  amount=${float(str(approved['payload']['approved_amount_usd'])):,.0f}")
    for i, cond in enumerate(approved["payload"].get("conditions", []), 1):
        info(f"  condition {i}: {cond}")

    # ── MCP Resource Read ──────────────────────────────────────────────────────
    hdr("Step 7 — Read Back via MCP Resource Layer")
    step("Reading ledger://applications/{id}/audit-trail …")
    server = create_server(store=store)
    resource_result = await server.resources.read(
        f"ledger://applications/{APP_ID}/audit-trail"
    )
    content = json.loads(resource_result["contents"][0]["text"])
    ok(f"Audit trail loaded: {content['total_events']} events across "
       f"{len(content['streams_covered'])} streams")

    step("Reading ledger://applications/{id} (application summary) …")
    summary_result = await server.resources.read(f"ledger://applications/{APP_ID}")
    summary = json.loads(summary_result["contents"][0]["text"])
    if "error" in summary:
        warn(f"Summary read returned error: {summary['message']}")
    else:
        ok(f"Application state={summary.get('state')}  "
           f"approved=${float(summary.get('approved_amount', 0) or 0):,.0f}")

    if args.verbose:
        hdr("Full Audit Trail")
        for event in content["events"]:
            stream = event.get("stream_id", "?")
            etype  = event.get("event_type", "?")
            pos    = event.get("stream_position", "?")
            print(f"  {DIM}[{stream}:{pos}]{RESET}  {etype}")

    # ── Final Summary ──────────────────────────────────────────────────────────
    elapsed = time.time() - t_start
    print(f"\n{BOLD}{'═' * 62}{RESET}")
    print(f"{BOLD}  NARR-05 COMPLETE — All assertions passed ✓{RESET}")
    print(f"{BOLD}{'═' * 62}{RESET}")
    print(f"\n  {GREEN}✓{RESET}  DecisionGenerated     recommendation=DECLINE")
    print(f"  {GREEN}✓{RESET}  HumanReviewCompleted  override=True  reviewer=LO-Sarah-Chen")
    print(f"  {GREEN}✓{RESET}  ApplicationApproved   amount=$750,000  conditions=2")
    print(f"  {GREEN}✓{RESET}  Audit trail           {content['total_events']} events")
    print(f"\n  Elapsed: {elapsed:.2f}s\n")


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="NARR-05 live demo — Human Override scenario.")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Print the full chronological audit trail")
    p.add_argument("--real-llm", action="store_true",
                   help="Use real Anthropic API (requires ANTHROPIC_API_KEY in .env)")
    asyncio.run(run(p.parse_args()))
