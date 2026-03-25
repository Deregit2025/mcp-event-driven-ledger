"""
src/mcp/tools.py
=================
MCP tool definitions for the Apex Ledger.

Tools are write-side operations — they execute commands that append
events to the event store. Each tool validates inputs, calls the
appropriate command handler, and returns structured results.

Tool naming follows MCP convention: ledger_{action}
"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ── TOOL SCHEMAS ──────────────────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "ledger_submit_application",
        "description": (
            "Submit a new loan application to Apex Financial Services. "
            "Creates the loan event stream and writes ApplicationSubmitted. "
            "Returns the stream_id created."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "application_id": {
                    "type": "string",
                    "description": "Unique application ID, e.g. APEX-0042",
                },
                "applicant_id": {
                    "type": "string",
                    "description": "Applicant company ID, e.g. COMP-007",
                },
                "requested_amount_usd": {
                    "type": "number",
                    "description": "Requested loan amount in USD",
                },
                "loan_purpose": {
                    "type": "string",
                    "description": "One of: working_capital, equipment, real_estate, acquisition, refinancing, other",
                },
                "loan_term_months": {
                    "type": "integer",
                    "description": "Loan term in months (default 60)",
                    "default": 60,
                },
                "submission_channel": {
                    "type": "string",
                    "description": "One of: web, api, broker, branch (default web)",
                    "default": "web",
                },
            },
            "required": ["application_id", "applicant_id", "requested_amount_usd", "loan_purpose"],
        },
    },
    {
        "name": "ledger_start_agent_session",
        "description": (
            "Start an agent session — Gas Town anchor event. "
            "PRECONDITION: Must be called before any agent decision tools "
            "(ledger_record_credit_analysis, ledger_record_fraud_screening, etc). "
            "Calling decision tools without an active session returns PreconditionFailed. "
            "Returns the session stream_id."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_type": {
                    "type": "string",
                    "description": "One of: document_processing, credit_analysis, fraud_detection, compliance, orchestrator",
                },
                "session_id": {"type": "string", "description": "Unique session identifier"},
                "agent_id": {"type": "string", "description": "Agent instance identifier"},
                "application_id": {"type": "string", "description": "Application being processed"},
                "model_version": {"type": "string", "description": "LLM model version string"},
                "context_source": {
                    "type": "string",
                    "description": "How context was initialised: fresh or prior_session_replay:{id}",
                    "default": "fresh",
                },
            },
            "required": ["agent_type", "session_id", "agent_id", "application_id", "model_version"],
        },
    },
    {
        "name": "ledger_record_credit_analysis",
        "description": (
            "Record that a CreditAnalysisAgent has completed its analysis. "
            "PRECONDITION: Requires an active agent session created by ledger_start_agent_session. "
            "Enforces business rules: no prior credit analysis unless overridden; "
            "confidence < 0.60 requires recommendation=REFER."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "application_id": {"type": "string"},
                "session_id": {"type": "string"},
                "agent_type": {"type": "string", "default": "credit_analysis"},
                "risk_tier": {
                    "type": "string",
                    "description": "One of: LOW, MEDIUM, HIGH, VERY_HIGH, DECLINED",
                },
                "recommended_limit_usd": {"type": "number"},
                "confidence": {"type": "number", "description": "0.0–1.0"},
                "rationale": {"type": "string"},
                "model_version": {"type": "string"},
                "key_concerns": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["application_id", "session_id", "risk_tier",
                         "recommended_limit_usd", "confidence", "rationale", "model_version"],
        },
    },
    {
        "name": "ledger_record_fraud_screening",
        "description": (
            "Record that a FraudDetectionAgent has completed fraud screening. "
            "PRECONDITION: Requires an active agent session created by ledger_start_agent_session."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "application_id": {"type": "string"},
                "session_id": {"type": "string"},
                "agent_type": {"type": "string", "default": "fraud_detection"},
                "fraud_score": {"type": "number", "description": "0.0–1.0 (higher = more suspicious)"},
                "risk_level": {"type": "string", "description": "LOW, MEDIUM, HIGH, CRITICAL"},
                "recommendation": {"type": "string", "description": "APPROVE, REVIEW, REJECT"},
                "screening_model_version": {"type": "string"},
            },
            "required": ["application_id", "session_id", "fraud_score",
                         "risk_level", "recommendation", "screening_model_version"],
        },
    },
    {
        "name": "ledger_record_compliance_check",
        "description": (
            "Record that a ComplianceAgent has completed its rule evaluation. "
            "PRECONDITION: Requires an active agent session created by ledger_start_agent_session. "
            "A HARD_BLOCK forces the final decision to DECLINE regardless of other analyses."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "application_id": {"type": "string"},
                "session_id": {"type": "string"},
                "agent_type": {"type": "string", "default": "compliance"},
                "rules_evaluated": {"type": "integer"},
                "rules_passed": {"type": "integer"},
                "rules_failed": {"type": "integer"},
                "rules_noted": {"type": "integer", "default": 0},
                "has_hard_block": {"type": "boolean"},
                "overall_verdict": {"type": "string", "description": "CLEAR or BLOCKED"},
            },
            "required": ["application_id", "session_id", "rules_evaluated",
                         "rules_passed", "rules_failed", "has_hard_block", "overall_verdict"],
        },
    },
    {
        "name": "ledger_generate_decision",
        "description": (
            "Generate the orchestrator's final decision on a loan application. "
            "PRECONDITION: All three analyses (credit, fraud, compliance) must be recorded first. "
            "Enforces: confidence floor (< 0.6 forces REFER), compliance clearance, "
            "contributing sessions must reference valid agent sessions for this application."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "application_id": {"type": "string"},
                "orchestrator_session_id": {"type": "string"},
                "recommendation": {"type": "string", "description": "APPROVE, DECLINE, or REFER"},
                "confidence": {"type": "number", "description": "0.0–1.0"},
                "executive_summary": {"type": "string"},
                "key_risks": {"type": "array", "items": {"type": "string"}},
                "approved_amount_usd": {"type": "number"},
                "conditions": {"type": "array", "items": {"type": "string"}},
                "contributing_sessions": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["application_id", "orchestrator_session_id",
                         "recommendation", "confidence", "executive_summary"],
        },
    },
    {
        "name": "ledger_record_human_review",
        "description": (
            "Record a human loan officer's final review decision. "
            "PRECONDITION: A DecisionGenerated event must exist for this application — "
            "call ledger_generate_decision first. "
            "If override=true, override_reason is required. "
            "Automatically appends ApplicationApproved or ApplicationDeclined based on final_decision."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "application_id": {"type": "string"},
                "reviewer_id": {"type": "string", "description": "Human reviewer identifier"},
                "override": {
                    "type": "boolean",
                    "description": "True if reviewer is overriding the AI recommendation",
                },
                "original_recommendation": {
                    "type": "string",
                    "description": "The AI recommendation being reviewed: APPROVE, DECLINE, or REFER",
                },
                "final_decision": {
                    "type": "string",
                    "description": "Final binding decision: APPROVE or DECLINE",
                },
                "override_reason": {
                    "type": "string",
                    "description": "Required when override=true. Explanation for the override.",
                },
                "approved_amount_usd": {
                    "type": "number",
                    "description": "Approved loan amount (required when final_decision=APPROVE)",
                },
                "interest_rate_pct": {"type": "number", "default": 5.0},
                "term_months": {"type": "integer", "default": 60},
                "conditions": {"type": "array", "items": {"type": "string"}},
                "decline_reasons": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["application_id", "reviewer_id", "override",
                         "original_recommendation", "final_decision"],
        },
    },
    {
        "name": "ledger_run_integrity_check",
        "description": (
            "Run a cryptographic integrity check on a loan application's event stream. "
            "Computes SHA-256 hash chain over all events and verifies against stored chain. "
            "Returns chain_valid=false and tamper_detected=true if any stored event was modified. "
            "Appends an AuditIntegrityCheckRun event to the audit stream. "
            "Rate-limited: call at most once per minute per application."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "application_id": {
                    "type": "string",
                    "description": "Application ID to verify, e.g. APEX-0042",
                },
                "entity_type": {
                    "type": "string",
                    "description": "Stream type to verify: loan, credit, fraud, compliance (default: loan)",
                    "default": "loan",
                },
            },
            "required": ["application_id"],
        },
    },
]


# ── ALIAS NORMALISERS ────────────────────────────────────────────────────────

_LOAN_PURPOSE_ALIASES: dict[str, str] = {
    "equipment": "equipment_financing",
    "real estate": "real_estate",
    "bridge loan": "bridge",
}

_AGENT_TYPE_ALIASES: dict[str, str] = {
    "orchestrator": "decision_orchestrator",
    "decision": "decision_orchestrator",
    "doc_processing": "document_processing",
    "docs": "document_processing",
    "fraud": "fraud_detection",
    "credit": "credit_analysis",
}


def _normalise_loan_purpose(value: str) -> str:
    return _LOAN_PURPOSE_ALIASES.get(value.lower(), value)


def _normalise_agent_type(value: str) -> str:
    return _AGENT_TYPE_ALIASES.get(value.lower(), value)


# ── TOOL EXECUTOR ─────────────────────────────────────────────────────────────

class LedgerToolExecutor:
    """Executes MCP tool calls against the event store."""

    def __init__(self, store):
        self.store = store

    async def execute(self, tool_name: str, arguments: dict) -> dict[str, Any]:
        handlers = {
            "ledger_submit_application":      self._submit_application,
            "ledger_start_agent_session":     self._start_agent_session,
            "ledger_record_credit_analysis":  self._record_credit_analysis,
            "ledger_record_fraud_screening":  self._record_fraud_screening,
            "ledger_record_compliance_check": self._record_compliance_check,
            "ledger_generate_decision":       self._generate_decision,
            "ledger_record_human_review":     self._record_human_review,
            "ledger_run_integrity_check":     self._run_integrity_check,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return {
                "error_type": "UnknownTool",
                "message": f"Unknown tool: {tool_name}",
                "suggested_action": "check_tool_name_and_retry",
            }
        try:
            return await handler(arguments)
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return {
                "error_type": type(e).__name__,
                "message": str(e),
                "suggested_action": getattr(e, "suggested_action", "check_inputs_and_retry"),
            }

    async def _submit_application(self, args: dict) -> dict:
        from src.commands.handlers import handle_submit_application
        stream_id = await handle_submit_application(
            self.store,
            application_id=args["application_id"],
            applicant_id=args["applicant_id"],
            requested_amount_usd=args["requested_amount_usd"],
            loan_purpose=_normalise_loan_purpose(args["loan_purpose"]),
            loan_term_months=args.get("loan_term_months", 60),
            submission_channel=args.get("submission_channel", "web"),
        )
        return {"stream_id": stream_id, "status": "submitted"}

    async def _start_agent_session(self, args: dict) -> dict:
        from src.commands.handlers import handle_start_agent_session
        stream_id = await handle_start_agent_session(
            self.store,
            agent_type=_normalise_agent_type(args["agent_type"]),
            session_id=args["session_id"],
            agent_id=args["agent_id"],
            application_id=args["application_id"],
            model_version=args["model_version"],
            context_source=args.get("context_source", "fresh"),
        )
        return {"stream_id": stream_id, "status": "session_started"}

    async def _record_credit_analysis(self, args: dict) -> dict:
        from src.commands.handlers import handle_credit_analysis_completed
        await handle_credit_analysis_completed(
            self.store,
            application_id=args["application_id"],
            session_id=args["session_id"],
            agent_type=args.get("agent_type", "credit_analysis"),
            risk_tier=args["risk_tier"],
            recommended_limit_usd=args["recommended_limit_usd"],
            confidence=args["confidence"],
            rationale=args["rationale"],
            model_version=args["model_version"],
            key_concerns=args.get("key_concerns", []),
        )
        return {"status": "credit_analysis_recorded"}

    async def _record_fraud_screening(self, args: dict) -> dict:
        from src.commands.handlers import handle_fraud_screening_completed
        await handle_fraud_screening_completed(
            self.store,
            application_id=args["application_id"],
            session_id=args["session_id"],
            agent_type=args.get("agent_type", "fraud_detection"),
            fraud_score=args["fraud_score"],
            risk_level=args["risk_level"],
            recommendation=args["recommendation"],
            screening_model_version=args["screening_model_version"],
        )
        return {"status": "fraud_screening_recorded"}

    async def _record_compliance_check(self, args: dict) -> dict:
        from src.commands.handlers import handle_compliance_check
        await handle_compliance_check(
            self.store,
            application_id=args["application_id"],
            session_id=args["session_id"],
            agent_type=args.get("agent_type", "compliance"),
            rules_evaluated=args["rules_evaluated"],
            rules_passed=args["rules_passed"],
            rules_failed=args["rules_failed"],
            rules_noted=args.get("rules_noted", 0),
            has_hard_block=args["has_hard_block"],
            overall_verdict=args["overall_verdict"],
        )
        return {
            "status": "compliance_recorded",
            "has_hard_block": args["has_hard_block"],
            "verdict": args["overall_verdict"],
        }

    async def _generate_decision(self, args: dict) -> dict:
        from src.commands.handlers import handle_generate_decision
        await handle_generate_decision(
            self.store,
            application_id=args["application_id"],
            orchestrator_session_id=args["orchestrator_session_id"],
            recommendation=args["recommendation"],
            confidence=args["confidence"],
            executive_summary=args["executive_summary"],
            key_risks=args.get("key_risks", []),
            approved_amount_usd=args.get("approved_amount_usd"),
            conditions=args.get("conditions", []),
            contributing_sessions=args.get("contributing_sessions", []),
        )
        return {
            "status": "decision_generated",
            "recommendation": args["recommendation"],
        }

    async def _record_human_review(self, args: dict) -> dict:
        from src.commands.handlers import handle_human_review_completed
        await handle_human_review_completed(
            self.store,
            application_id=args["application_id"],
            reviewer_id=args["reviewer_id"],
            override=args["override"],
            original_recommendation=args["original_recommendation"],
            final_decision=args["final_decision"],
            override_reason=args.get("override_reason"),
            approved_amount_usd=args.get("approved_amount_usd"),
            interest_rate_pct=args.get("interest_rate_pct", 5.0),
            term_months=args.get("term_months", 60),
            conditions=args.get("conditions", []),
            decline_reasons=args.get("decline_reasons", []),
        )
        return {
            "status": "human_review_recorded",
            "final_decision": args["final_decision"],
            "override": args["override"],
        }

    async def _run_integrity_check(self, args: dict) -> dict:
        from src.integrity.audit_chain import run_integrity_check
        result = await run_integrity_check(
            self.store,
            entity_type=args.get("entity_type", "loan"),
            entity_id=args["application_id"],
        )
        if result.error:
            return {
                "error_type": "IntegrityCheckFailed",
                "message": result.error,
                "suggested_action": "check_event_store_connectivity",
            }
        return {
            "status": "integrity_check_complete",
            "application_id": args["application_id"],
            "events_verified": result.events_verified,
            "chain_valid": result.chain_valid,
            "tamper_detected": result.tamper_detected,
            "current_hash": result.current_hash[:16] + "...",
            "check_timestamp": result.check_timestamp,
        }