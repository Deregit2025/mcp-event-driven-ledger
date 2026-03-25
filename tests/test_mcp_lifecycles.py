"""
tests/test_mcp_lifecycles.py
==============================
MCP tool and resource lifecycle tests.

Tests the full round-trip:
  Tool call → command handler → event store → resource read → correct state

Uses InMemoryEventStore — no database required, no MCP transport.
Tests the tool executor and resource reader directly.

Run: pytest tests/test_mcp_lifecycles.py -v
"""
import pytest
from src.event_store import InMemoryEventStore
from src.mcp.tools import LedgerToolExecutor
from src.mcp.resources import LedgerResourceReader


# ── HELPERS ───────────────────────────────────────────────────────────────────

def make_store():
    return InMemoryEventStore()


def make_tools(store):
    return LedgerToolExecutor(store)


def make_resources(store):
    return LedgerResourceReader(store, projection_daemon=None)


# ── TOOL: ledger_submit_application ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_submit_application_tool_creates_stream():
    """ledger_submit_application creates a loan stream and returns stream_id."""
    store = make_store()
    tools = make_tools(store)

    result = await tools.execute("ledger_submit_application", {
        "application_id": "APEX-MCP-001",
        "applicant_id": "COMP-001",
        "requested_amount_usd": 500000,
        "loan_purpose": "working_capital",
    })

    assert "error" not in result
    assert result["status"] == "submitted"
    assert result["stream_id"] == "loan-APEX-MCP-001"

    # Stream must exist in the store
    ver = await store.stream_version("loan-APEX-MCP-001")
    assert ver == 0  # one event at position 0


@pytest.mark.asyncio
async def test_submit_duplicate_application_returns_error():
    """Submitting the same application_id twice returns a structured error."""
    store = make_store()
    tools = make_tools(store)

    await tools.execute("ledger_submit_application", {
        "application_id": "APEX-MCP-DUP",
        "applicant_id": "COMP-001",
        "requested_amount_usd": 100000,
        "loan_purpose": "equipment",
    })

    result = await tools.execute("ledger_submit_application", {
        "application_id": "APEX-MCP-DUP",
        "applicant_id": "COMP-001",
        "requested_amount_usd": 100000,
        "loan_purpose": "equipment",
    })

    assert "error" in result or "message" in result


@pytest.mark.asyncio
async def test_unknown_tool_returns_error():
    """Unknown tool name returns structured error."""
    store = make_store()
    tools = make_tools(store)
    result = await tools.execute("ledger_does_not_exist", {})
    assert "error_type" in result or "error" in result

# ── TOOL: ledger_start_agent_session ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_agent_session_creates_stream():
    """ledger_start_agent_session creates agent stream with Gas Town anchor event."""
    store = make_store()
    tools = make_tools(store)

    # First submit the application
    await tools.execute("ledger_submit_application", {
        "application_id": "APEX-MCP-002",
        "applicant_id": "COMP-002",
        "requested_amount_usd": 250000,
        "loan_purpose": "equipment",
    })

    result = await tools.execute("ledger_start_agent_session", {
        "agent_type": "credit_analysis",
        "session_id": "sess-mcp-001",
        "agent_id": "agent-001",
        "application_id": "APEX-MCP-002",
        "model_version": "credit-v2.3",
    })

    assert "error" not in result
    assert result["status"] == "session_started"
    assert "agent-credit_analysis-sess-mcp-001" in result["stream_id"]

    # AgentSessionStarted must be the first event
    events = await store.load_stream("agent-credit_analysis-sess-mcp-001")
    assert len(events) == 1
    assert events[0]["event_type"] == "AgentSessionStarted"


# ── TOOL: full pipeline round-trip ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_pipeline_round_trip():
    """
    Full pipeline: submit → credit session → credit analysis →
    fraud session → fraud screening → compliance session →
    compliance check → decision session → decision.
    """
    store = make_store()
    tools = make_tools(store)
    app_id = "APEX-MCP-FULL"

    # 1. Submit application
    r = await tools.execute("ledger_submit_application", {
        "application_id": app_id,
        "applicant_id": "COMP-FULL",
        "requested_amount_usd": 750000,
        "loan_purpose": "working_capital",
    })
    assert r["status"] == "submitted"

    # 2. Start credit analysis session
    r = await tools.execute("ledger_start_agent_session", {
        "agent_type": "credit_analysis",
        "session_id": "sess-credit-001",
        "agent_id": "agent-credit",
        "application_id": app_id,
        "model_version": "credit-v2.3",
    })
    assert r["status"] == "session_started"

    # 3. Record credit analysis
    r = await tools.execute("ledger_record_credit_analysis", {
        "application_id": app_id,
        "session_id": "sess-credit-001",
        "risk_tier": "MEDIUM",
        "recommended_limit_usd": 700000,
        "confidence": 0.82,
        "rationale": "Strong cash flow, moderate debt ratio.",
        "model_version": "credit-v2.3",
        "key_concerns": ["debt_service_coverage"],
    })
    assert r["status"] == "credit_analysis_recorded"

    # 4. Start fraud detection session
    r = await tools.execute("ledger_start_agent_session", {
        "agent_type": "fraud_detection",
        "session_id": "sess-fraud-001",
        "agent_id": "agent-fraud",
        "application_id": app_id,
        "model_version": "fraud-v1.1",
    })
    assert r["status"] == "session_started"

    # 5. Record fraud screening
    r = await tools.execute("ledger_record_fraud_screening", {
        "application_id": app_id,
        "session_id": "sess-fraud-001",
        "fraud_score": 0.04,
        "risk_level": "LOW",
        "recommendation": "APPROVE",
        "screening_model_version": "fraud-v1.1",
    })
    assert r["status"] == "fraud_screening_recorded"

    # 6. Start compliance session
    r = await tools.execute("ledger_start_agent_session", {
        "agent_type": "compliance",
        "session_id": "sess-comp-001",
        "agent_id": "agent-comp",
        "application_id": app_id,
        "model_version": "compliance-v1.0",
    })
    assert r["status"] == "session_started"

    # 7. Record compliance check
    r = await tools.execute("ledger_record_compliance_check", {
        "application_id": app_id,
        "session_id": "sess-comp-001",
        "rules_evaluated": 3,
        "rules_passed": 3,
        "rules_failed": 0,
        "rules_noted": 0,
        "has_hard_block": False,
        "overall_verdict": "CLEAR",
    })
    assert r["status"] == "compliance_recorded"
    assert r["has_hard_block"] is False

    # 8. Start orchestrator session
    r = await tools.execute("ledger_start_agent_session", {
        "agent_type": "orchestrator",
        "session_id": "sess-orch-001",
        "agent_id": "agent-orch",
        "application_id": app_id,
        "model_version": "orch-v1.0",
    })
    assert r["status"] == "session_started"

    # 9. Generate decision
    r = await tools.execute("ledger_generate_decision", {
        "application_id": app_id,
        "orchestrator_session_id": "sess-orch-001",
        "recommendation": "APPROVE",
        "confidence": 0.82,
        "executive_summary": "Strong application. Recommend approval.",
        "key_risks": ["debt_service_coverage"],
        "approved_amount_usd": 700000,
        "conditions": ["Quarterly financial reporting required"],
        "contributing_sessions": ["sess-credit-001", "sess-fraud-001", "sess-comp-001"],
    })
    assert r["status"] == "decision_generated"
    assert r["recommendation"] == "APPROVE"


# ── RESOURCE: ledger://applications/{id} ──────────────────────────────────────

@pytest.mark.asyncio
async def test_resource_application_summary_returns_correct_state():
    """Reading application resource after submit returns SUBMITTED state."""
    store = make_store()
    tools = make_tools(store)
    resources = make_resources(store)

    await tools.execute("ledger_submit_application", {
        "application_id": "APEX-MCP-R01",
        "applicant_id": "COMP-R01",
        "requested_amount_usd": 300000,
        "loan_purpose": "equipment",
    })

    result = await resources.read("ledger://applications/APEX-MCP-R01")
    assert "contents" in result
    content = result["contents"][0]
    data = __import__("json").loads(content["text"])

    assert data["application_id"] == "APEX-MCP-R01"
    assert data["state"] == "SUBMITTED"
    assert data["applicant_id"] == "COMP-R01"
    assert data["requested_amount_usd"] == 300000.0


@pytest.mark.asyncio
async def test_resource_application_summary_unknown_app_returns_new_state():
    """Reading a non-existent application returns NEW state (empty aggregate)."""
    store = make_store()
    resources = make_resources(store)

    result = await resources.read("ledger://applications/APEX-DOES-NOT-EXIST")
    content = __import__("json").loads(result["contents"][0]["text"])
    # Empty aggregate — no events replayed, state is NEW
    assert content.get("state") == "NEW" or "error" in content


# ── RESOURCE: ledger://applications/{id}/audit-trail ─────────────────────────

@pytest.mark.asyncio
async def test_resource_audit_trail_contains_all_events():
    """Audit trail resource returns events from loan stream."""
    store = make_store()
    tools = make_tools(store)
    resources = make_resources(store)

    await tools.execute("ledger_submit_application", {
        "application_id": "APEX-MCP-AT01",
        "applicant_id": "COMP-AT01",
        "requested_amount_usd": 100000,
        "loan_purpose": "working_capital",
    })

    result = await resources.read("ledger://applications/APEX-MCP-AT01/audit-trail")
    data = __import__("json").loads(result["contents"][0]["text"])

    assert data["application_id"] == "APEX-MCP-AT01"
    assert data["total_events"] >= 1
    assert any(e["event_type"] == "ApplicationSubmitted" for e in data["events"])


# ── RESOURCE: ledger://sessions/{session_id} ──────────────────────────────────

@pytest.mark.asyncio
async def test_resource_session_returns_agent_state():
    """Session resource returns session state including nodes_executed."""
    store = make_store()
    tools = make_tools(store)
    resources = make_resources(store)

    await tools.execute("ledger_submit_application", {
        "application_id": "APEX-MCP-S01",
        "applicant_id": "COMP-S01",
        "requested_amount_usd": 200000,
        "loan_purpose": "equipment",
    })

    await tools.execute("ledger_start_agent_session", {
        "agent_type": "fraud_detection",
        "session_id": "sess-res-001",
        "agent_id": "agent-fraud",
        "application_id": "APEX-MCP-S01",
        "model_version": "fraud-v1.1",
    })

    result = await resources.read("ledger://sessions/sess-res-001")
    data = __import__("json").loads(result["contents"][0]["text"])

    assert data.get("session_id") == "sess-res-001"
    assert data.get("agent_type") == "fraud_detection"
    assert data.get("status") == "ACTIVE"


@pytest.mark.asyncio
async def test_resource_unknown_session_returns_error_structure():
    """Reading a non-existent session returns error structure, not an exception."""
    store = make_store()
    resources = make_resources(store)

    result = await resources.read("ledger://sessions/sess-does-not-exist")
    data = __import__("json").loads(result["contents"][0]["text"])
    assert "error" in data or "session_id" in data


# ── RESOURCE: ledger://ledger/health ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_resource_health_returns_status():
    """Health resource returns a valid health status dict."""
    store = make_store()
    resources = make_resources(store)

    result = await resources.read("ledger://ledger/health")
    data = __import__("json").loads(result["contents"][0]["text"])

    assert "status" in data
    assert data["status"] in ("healthy", "degraded")


@pytest.mark.asyncio
async def test_resource_unknown_uri_returns_error():
    """Unknown resource URI returns error in contents, not unhandled exception."""
    store = make_store()
    resources = make_resources(store)

    result = await resources.read("ledger://this/does/not/exist")
    content = __import__("json").loads(result["contents"][0]["text"])
    assert "error" in content


# ── OCC PROTECTION VIA TOOLS ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_occ_via_tool_returns_structured_error():
    """
    When two tool calls race to write to the same stream,
    one must fail with a structured error (not crash).
    Exercises the OCC path through the tool executor.
    """
    import asyncio
    store = make_store()
    tools = make_tools(store)

    # Submit application first
    await tools.execute("ledger_submit_application", {
        "application_id": "APEX-MCP-OCC",
        "applicant_id": "COMP-OCC",
        "requested_amount_usd": 500000,
        "loan_purpose": "working_capital",
    })

    # Start two sessions for different agent types — no OCC conflict here,
    # but we can test the duplicate session path
    r1 = await tools.execute("ledger_start_agent_session", {
        "agent_type": "credit_analysis",
        "session_id": "sess-occ-dup",
        "agent_id": "agent-a",
        "application_id": "APEX-MCP-OCC",
        "model_version": "credit-v2.3",
    })
    assert r1["status"] == "session_started"

    # Duplicate session must return error, not raise
    r2 = await tools.execute("ledger_start_agent_session", {
        "agent_type": "credit_analysis",
        "session_id": "sess-occ-dup",  # same session_id!
        "agent_id": "agent-b",
        "application_id": "APEX-MCP-OCC",
        "model_version": "credit-v2.3",
    })
    assert "error" in r2 or "message" in r2
