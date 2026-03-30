"""
scripts/run_pipeline.py
=======================
Process one loan application through the full Apex Ledger agent pipeline.

Usage:
    python scripts/run_pipeline.py --application APEX-0007
    python scripts/run_pipeline.py --application APEX-0007 --phase credit
    python scripts/run_pipeline.py --application APEX-0007 --phase all --verbose

Phases: submit | document | credit | fraud | compliance | decision | all (default)

The script uses InMemoryEventStore by default so it runs without a database.
Set DATABASE_URL in .env to persist results to PostgreSQL.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger("pipeline")

# ── ANSI colours (auto-disabled on Windows without colour support) ─────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
CYAN   = "\033[36m"
YELLOW = "\033[33m"
RED    = "\033[31m"
DIM    = "\033[2m"


def _hdr(msg: str) -> None:
    print(f"\n{BOLD}{CYAN}{'-' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {msg}{RESET}")
    print(f"{BOLD}{CYAN}{'-' * 60}{RESET}")


def _ok(msg: str) -> None:
    print(f"  {GREEN}[OK]{RESET} {msg}")


def _info(msg: str) -> None:
    print(f"  {DIM}{msg}{RESET}")


def _warn(msg: str) -> None:
    print(f"  {YELLOW}[WARN] {msg}{RESET}")


def _err(msg: str) -> None:
    print(f"  {RED}[ERR] {msg}{RESET}")


# ── MOCK INFRASTRUCTURE ────────────────────────────────────────────────────────

class _MockContent:
    def __init__(self, text): self.text = text

class _MockUsage:
    input_tokens = 120; output_tokens = 90

class _MockResponse:
    def __init__(self, text):
        self.content = [_MockContent(text)]; self.usage = _MockUsage()

class _MockMessages:
    def __init__(self, responses: list[str]):
        self._responses = list(responses); self._idx = 0
    async def create(self, **_kw):
        text = self._responses[self._idx % len(self._responses)]
        self._idx += 1
        return _MockResponse(text)

class MockAnthropicClient:
    """Returns pre-built JSON without network calls. Used when --mock-llm is set."""
    def __init__(self, *responses):
        self.messages = _MockMessages(list(responses))


class MockRegistry:
    """Minimal in-memory registry for standalone runs."""
    def __init__(self, jurisdiction="CA"):
        self._jurisdiction = jurisdiction

    async def get_company(self, company_id):
        return {
            "company_id": company_id, "name": f"Demo Corp ({company_id})",
            "industry": "technology", "jurisdiction": self._jurisdiction,
            "legal_type": "LLC", "founded_year": 2020,
            "employee_count": 75, "trajectory": "STABLE",
        }

    async def get_financial_history(self, company_id, years=None):
        return []

    async def get_compliance_flags(self, company_id, active_only=False):
        return []

    async def get_loan_relationships(self, company_id):
        return []


# ── PHASE RUNNERS ──────────────────────────────────────────────────────────────

async def phase_submit(store, app_id: str, args) -> None:
    _hdr("PHASE 1 — Submit Application")
    from src.commands.handlers import handle_submit_application

    await handle_submit_application(
        store,
        application_id=app_id,
        applicant_id=args.applicant_id,
        requested_amount_usd=args.amount,
        loan_purpose=args.purpose,
        loan_term_months=args.term_months,
        submission_channel="api",
    )
    _ok(f"ApplicationSubmitted → loan-{app_id}")
    _info(f"applicant={args.applicant_id}  amount=${args.amount:,.0f}  purpose={args.purpose}")


async def phase_document(store, app_id: str, args) -> None:
    _hdr("PHASE 2 — Document Processing")
    from agents.stub_agents import DocumentProcessingAgent

    # Write DocumentUploaded events so the agent has something to process
    ver = await store.stream_version(f"loan-{app_id}")
    doc_events = [
        {
            "event_type": "DocumentUploaded", "event_version": 1,
            "payload": {
                "application_id": app_id, "document_id": "doc-is-001",
                "document_type": "income_statement",
                "file_path": "/data/doc-is-001.pdf", "file_size_bytes": 102400,
                "uploaded_at": "2026-01-15T10:00:00",
            },
        },
        {
            "event_type": "DocumentUploaded", "event_version": 1,
            "payload": {
                "application_id": app_id, "document_id": "doc-bs-001",
                "document_type": "balance_sheet",
                "file_path": "/data/doc-bs-001.pdf", "file_size_bytes": 81920,
                "uploaded_at": "2026-01-15T10:01:00",
            },
        },
    ]
    await store.append(f"loan-{app_id}", doc_events, expected_version=ver)
    _ok("2 × DocumentUploaded written to loan stream")

    # Mock LLM response for quality assessment
    qa_response = json.dumps({
        "overall_confidence": 0.92, "is_coherent": True,
        "critical_missing_fields": [],
        "anomalies": [], "reextraction_recommended": False,
        "auditor_notes": "All financials present and internally consistent.",
        "balance_sheet_balances": True,
    })
    client = _build_client(args, qa_response)

    agent = DocumentProcessingAgent(
        agent_id="agent-doc-001", agent_type="document_processing",
        store=store, registry=MockRegistry(), client=client,
    )
    t = time.time()
    await agent.process_application(app_id)
    ms = int((time.time() - t) * 1000)
    _ok(f"DocumentProcessingAgent completed in {ms}ms  session={agent.session_id}")
    _info(f"→ QualityAssessmentCompleted + PackageReadyForAnalysis written to docpkg-{app_id}")
    _info(f"→ CreditAnalysisRequested written to loan-{app_id}")


async def phase_credit(store, app_id: str, args) -> None:
    _hdr("PHASE 3 — Credit Analysis")
    from agents.base_agent import CreditAnalysisAgent

    credit_response = json.dumps({
        "risk_tier": "MEDIUM",
        "recommended_limit_usd": int(args.amount * 0.8),
        "confidence": 0.78,
        "rationale": "Solid revenue base with moderate leverage. Debt service coverage within acceptable range.",
        "key_concerns": ["debt_service_coverage"],
        "data_quality_caveats": [],
        "policy_overrides_applied": [],
    })
    client = _build_client(args, credit_response)

    agent = CreditAnalysisAgent(
        agent_id="agent-credit-001", agent_type="credit_analysis",
        store=store, registry=MockRegistry(), client=client,
    )
    t = time.time()
    await agent.process_application(app_id)
    ms = int((time.time() - t) * 1000)

    # Read back the result
    credit_events = await store.load_stream(f"credit-{app_id}")
    completed = next(
        (e for e in reversed(credit_events) if e["event_type"] == "CreditAnalysisCompleted"), None
    )
    if completed:
        d = completed["payload"].get("decision", {})
        _ok(f"CreditAnalysisCompleted in {ms}ms  session={agent.session_id}")
        _info(f"  risk_tier={d.get('risk_tier')}  limit=${d.get('recommended_limit_usd', 0):,.0f}"
              f"  confidence={d.get('confidence', 0):.0%}")
        if d.get("key_concerns"):
            _info(f"  key_concerns={d['key_concerns']}")
    else:
        _warn("CreditAnalysisCompleted not found in credit stream")


async def phase_fraud(store, app_id: str, args) -> None:
    _hdr("PHASE 4 — Fraud Detection")
    from agents.stub_agents import FraudDetectionAgent

    fraud_response = json.dumps({
        "fraud_score": 0.04, "risk_level": "LOW",
        "recommendation": "PROCEED", "anomalies": [],
    })
    client = _build_client(args, fraud_response)

    agent = FraudDetectionAgent(
        agent_id="agent-fraud-001", agent_type="fraud_detection",
        store=store, registry=MockRegistry(), client=client,
    )
    t = time.time()
    await agent.process_application(app_id)
    ms = int((time.time() - t) * 1000)

    fraud_events = await store.load_stream(f"fraud-{app_id}")
    completed = next(
        (e for e in reversed(fraud_events) if e["event_type"] == "FraudScreeningCompleted"), None
    )
    if completed:
        p = completed["payload"]
        _ok(f"FraudScreeningCompleted in {ms}ms  session={agent.session_id}")
        _info(f"  fraud_score={p.get('fraud_score')}  risk={p.get('risk_level')}"
              f"  recommendation={p.get('recommendation')}")
    else:
        _warn("FraudScreeningCompleted not found in fraud stream")


async def phase_compliance(store, app_id: str, args) -> None:
    _hdr("PHASE 5 — Compliance Check")
    from agents.stub_agents import ComplianceAgent

    agent = ComplianceAgent(
        agent_id="agent-comp-001", agent_type="compliance",
        store=store, registry=MockRegistry(jurisdiction=args.jurisdiction), client=None,
    )
    t = time.time()
    await agent.process_application(app_id)
    ms = int((time.time() - t) * 1000)

    comp_events = await store.load_stream(f"compliance-{app_id}")
    passed = sum(1 for e in comp_events if e["event_type"] == "ComplianceRulePassed")
    failed = sum(1 for e in comp_events if e["event_type"] == "ComplianceRuleFailed")
    completed = next(
        (e for e in reversed(comp_events) if e["event_type"] == "ComplianceCheckCompleted"), None
    )

    _ok(f"ComplianceCheckCompleted in {ms}ms  session={agent.session_id}")
    _info(f"  rules_passed={passed}  rules_failed={failed}")
    if completed:
        _info(f"  verdict={completed['payload'].get('overall_verdict')}"
              f"  hard_block={completed['payload'].get('has_hard_block')}")

    # Warn about MT jurisdiction hard block
    loan_events = await store.load_stream(f"loan-{app_id}")
    if any(e["event_type"] == "ApplicationDeclined" for e in loan_events):
        _warn("ApplicationDeclined written — compliance hard block triggered (likely REG-003 MT)")


async def phase_decision(store, app_id: str, args) -> None:
    _hdr("PHASE 6 — Decision Orchestration")
    from agents.stub_agents import DecisionOrchestratorAgent

    # Check compliance result — skip decision if hard block already declined
    loan_events = await store.load_stream(f"loan-{app_id}")
    if any(e["event_type"] == "ApplicationDeclined" for e in loan_events):
        _warn("Skipping decision phase — application already declined by compliance hard block")
        return

    decision_response = json.dumps({
        "recommendation": "APPROVE",
        "confidence": 0.81,
        "approved_amount_usd": int(args.amount * 0.8),
        "executive_summary": (
            "Applicant demonstrates stable revenue and adequate debt service coverage. "
            "Credit risk is within MEDIUM tier tolerance. Fraud signals are minimal. "
            "All compliance rules cleared. Recommendation: APPROVE."
        ),
        "key_risks": ["debt_service_coverage"],
    })
    client = _build_client(args, decision_response)

    agent = DecisionOrchestratorAgent(
        agent_id="agent-orch-001", agent_type="decision_orchestrator",
        store=store, registry=MockRegistry(), client=client,
    )
    t = time.time()
    await agent.process_application(app_id)
    ms = int((time.time() - t) * 1000)

    # Reload loan stream for final state
    loan_events = await store.load_stream(f"loan-{app_id}")
    decision_gen = next(
        (e for e in reversed(loan_events) if e["event_type"] == "DecisionGenerated"), None
    )
    approved = next(
        (e for e in reversed(loan_events) if e["event_type"] == "ApplicationApproved"), None
    )
    declined = next(
        (e for e in reversed(loan_events) if e["event_type"] == "ApplicationDeclined"), None
    )

    _ok(f"DecisionOrchestratorAgent completed in {ms}ms  session={agent.session_id}")
    if decision_gen:
        rec = decision_gen["payload"].get("recommendation", "?")
        conf = decision_gen["payload"].get("confidence", 0)
        _info(f"  DecisionGenerated → recommendation={rec}  confidence={conf:.0%}")
    if approved:
        amt = approved["payload"].get("approved_amount_usd", 0)
        _ok(f"  ApplicationApproved → amount=${float(amt):,.0f}")
    if declined:
        _warn(f"  ApplicationDeclined → {declined['payload'].get('decline_reasons', [])}")


# ── AUDIT SUMMARY ──────────────────────────────────────────────────────────────

async def print_audit_summary(store, app_id: str, verbose: bool) -> None:
    _hdr("AUDIT TRAIL SUMMARY")
    streams = [
        f"loan-{app_id}",
        f"docpkg-{app_id}",
        f"credit-{app_id}",
        f"fraud-{app_id}",
        f"compliance-{app_id}",
    ]
    total = 0
    for stream_id in streams:
        events = await store.load_stream(stream_id)
        if events:
            total += len(events)
            print(f"  {CYAN}{stream_id}{RESET}  ({len(events)} events)")
            if verbose:
                for e in events:
                    print(f"    {DIM}[{e.get('stream_position', '?')}] {e['event_type']}{RESET}")

    print(f"\n  {BOLD}Total: {total} events across {len([s for s in streams])}"
          f" streams{RESET}")


# ── HELPERS ────────────────────────────────────────────────────────────────────

def _build_client(args, mock_response: str):
    """Return real Anthropic client or mock depending on --mock-llm flag."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if args.mock_llm or not api_key:
        return MockAnthropicClient(mock_response)
    from anthropic import AsyncAnthropic
    kwargs = {"api_key": api_key}
    if api_key.startswith("sk-or-"):
        kwargs["base_url"] = "https://openrouter.ai/api/v1"
        # Also need to map model name if needed, but openrouter treats standard headers automatically usually.
    return AsyncAnthropic(**kwargs)


async def _build_store(args):
    """Return InMemoryEventStore or PostgreSQL EventStore."""
    db_url = args.db_url or os.getenv("DATABASE_URL")
    if db_url and not args.in_memory:
        try:
            from src.event_store import EventStore
            from src.upcasting.upcasters import registry as upcaster_registry
            store = EventStore(db_url, upcaster_registry=upcaster_registry)
            await store.connect()
            logger.info(f"Connected to PostgreSQL: {db_url}")
            return store
        except Exception as e:
            _warn(f"PostgreSQL unavailable ({e}) — falling back to InMemoryEventStore")
    from src.event_store import InMemoryEventStore
    return InMemoryEventStore()


# ── MAIN ──────────────────────────────────────────────────────────────────────

PHASE_ORDER = ["submit", "document", "credit", "fraud", "compliance", "decision"]
PHASE_MAP = {
    "submit":     phase_submit,
    "document":   phase_document,
    "credit":     phase_credit,
    "fraud":      phase_fraud,
    "compliance": phase_compliance,
    "decision":   phase_decision,
}


async def main() -> None:
    p = argparse.ArgumentParser(
        description="Run the Apex Ledger agent pipeline for one application."
    )
    p.add_argument("--application", "-a", required=True,
                   help="Application ID, e.g. APEX-0007")
    p.add_argument("--phase", "-p", default="all",
                   choices=["all"] + PHASE_ORDER,
                   help="Pipeline phase to run (default: all)")
    p.add_argument("--applicant-id", default="COMP-001",
                   help="Applicant company ID (default: COMP-001)")
    p.add_argument("--amount", "-A", type=float, default=500_000,
                   help="Requested loan amount USD (default: 500000)")
    p.add_argument("--purpose", default="working_capital",
                   help="Loan purpose (default: working_capital)")
    p.add_argument("--term-months", type=int, default=60,
                   help="Loan term in months (default: 60)")
    p.add_argument("--jurisdiction", default="CA",
                   help="Applicant jurisdiction for compliance (default: CA)")
    p.add_argument("--db-url", default=None,
                   help="PostgreSQL DATABASE_URL (overrides .env)")
    p.add_argument("--in-memory", action="store_true",
                   help="Force InMemoryEventStore even if DATABASE_URL is set")
    has_key = bool(os.getenv("ANTHROPIC_API_KEY"))
    p.add_argument("--mock-llm", action="store_true", default=not has_key,
                   help="Use mock LLM responses (default: True if no ANTHROPIC_API_KEY)")
    p.add_argument("--real-llm", dest="mock_llm", action="store_false",
                   help="Use real Anthropic API (requires ANTHROPIC_API_KEY in .env)")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Print every event in the audit trail")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    print(f"\n{BOLD}Apex Ledger Pipeline — {args.application}{RESET}")
    print(f"  phase={args.phase}  amount=${args.amount:,.0f}"
          f"  applicant={args.applicant_id}  jurisdiction={args.jurisdiction}")
    print(f"  llm={'REAL (Anthropic)' if not args.mock_llm else 'MOCK'}")

    store = await _build_store(args)
    start = time.time()

    phases_to_run = PHASE_ORDER if args.phase == "all" else [args.phase]

    for phase_name in phases_to_run:
        try:
            await PHASE_MAP[phase_name](store, args.application, args)
        except Exception as e:
            _err(f"Phase '{phase_name}' failed: {type(e).__name__}: {e}")
            if args.verbose:
                import traceback; traceback.print_exc()
            break

    await print_audit_summary(store, args.application, args.verbose)

    elapsed = time.time() - start
    print(f"\n  {BOLD}Total elapsed: {elapsed:.2f}s{RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())
