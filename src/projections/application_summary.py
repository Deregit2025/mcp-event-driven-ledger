"""
src/projections/application_summary.py
========================================
ApplicationSummaryProjection — one row per loan application.

Handles all LoanApplication stream events.
Uses INSERT ... ON CONFLICT DO UPDATE (idempotent — safe to reprocess).
"""
from __future__ import annotations
import asyncpg


class ApplicationSummaryProjection:

    @property
    def name(self) -> str:
        return "application_summary"

    async def handle(self, event: dict, conn: asyncpg.Connection) -> None:
        et = event["event_type"]
        p = event.get("payload", {})
        app_id = p.get("application_id")

        if not app_id:
            return  # not a loan application event

        handler = getattr(self, f"_on_{_snake(et)}", None)
        if handler:
            await handler(app_id, p, event, conn)

    # ── EVENT HANDLERS ────────────────────────────────────────────────────────

    async def _on_application_submitted(self, app_id, p, event, conn):
        await conn.execute("""
            INSERT INTO application_summary (
                application_id, state, applicant_id,
                requested_amount_usd, loan_purpose, submission_channel,
                submitted_at, last_event_type, last_event_at, updated_at
            ) VALUES ($1,'SUBMITTED',$2,$3,$4,$5,$6,$7,$8,NOW())
            ON CONFLICT (application_id) DO UPDATE SET
                state = 'SUBMITTED',
                applicant_id = $2,
                requested_amount_usd = $3,
                loan_purpose = $4,
                submission_channel = $5,
                submitted_at = $6,
                last_event_type = $7,
                last_event_at = $8,
                updated_at = NOW()
        """,
            app_id,
            p.get("applicant_id"),
            p.get("requested_amount_usd"),
            p.get("loan_purpose"),
            p.get("submission_channel"),
            event.get("recorded_at"),
            event["event_type"],
            event.get("recorded_at"),
        )

    async def _on_credit_analysis_completed(self, app_id, p, event, conn):
        decision = p.get("decision", {})
        await _update(conn, app_id, event, {
            "state": "CREDIT_ANALYSIS_COMPLETE",
            "credit_risk_tier": decision.get("risk_tier") if isinstance(decision, dict) else None,
            "credit_confidence": decision.get("confidence") if isinstance(decision, dict) else None,
        })

    async def _on_fraud_screening_completed(self, app_id, p, event, conn):
        await _update(conn, app_id, event, {
            "state": "FRAUD_SCREENING_COMPLETE",
            "fraud_score": p.get("fraud_score"),
        })

    async def _on_compliance_check_completed(self, app_id, p, event, conn):
        await _update(conn, app_id, event, {
            "state": "COMPLIANCE_CHECK_COMPLETE",
            "compliance_verdict": p.get("overall_verdict"),
        })

    async def _on_decision_generated(self, app_id, p, event, conn):
        rec = p.get("recommendation", "")
        state = "PENDING_HUMAN_REVIEW" if rec == "REFER" else "PENDING_DECISION"
        await _update(conn, app_id, event, {"state": state})

    async def _on_human_review_completed(self, app_id, p, event, conn):
        await _update(conn, app_id, event, {
            "final_decision": p.get("final_decision"),
        })

    async def _on_application_approved(self, app_id, p, event, conn):
        await _update(conn, app_id, event, {
            "state": "APPROVED",
            "final_decision": "APPROVE",
            "approved_amount_usd": p.get("approved_amount_usd"),
            "decided_at": event.get("recorded_at"),
        })

    async def _on_application_declined(self, app_id, p, event, conn):
        await _update(conn, app_id, event, {
            "state": "DECLINED",
            "final_decision": "DECLINE",
            "decided_at": event.get("recorded_at"),
        })

    async def _on_document_upload_requested(self, app_id, p, event, conn):
        await _update(conn, app_id, event, {"state": "DOCUMENTS_PENDING"})

    async def _on_document_uploaded(self, app_id, p, event, conn):
        await _update(conn, app_id, event, {"state": "DOCUMENTS_UPLOADED"})

    async def _on_package_ready_for_analysis(self, app_id, p, event, conn):
        await _update(conn, app_id, event, {"state": "DOCUMENTS_PROCESSED"})

    async def _on_credit_analysis_requested(self, app_id, p, event, conn):
        await _update(conn, app_id, event, {"state": "CREDIT_ANALYSIS_REQUESTED"})

    async def _on_fraud_screening_requested(self, app_id, p, event, conn):
        await _update(conn, app_id, event, {"state": "FRAUD_SCREENING_REQUESTED"})

    async def _on_compliance_check_requested(self, app_id, p, event, conn):
        await _update(conn, app_id, event, {"state": "COMPLIANCE_CHECK_REQUESTED"})

    async def _on_decision_requested(self, app_id, p, event, conn):
        await _update(conn, app_id, event, {"state": "PENDING_DECISION"})


# ── HELPERS ───────────────────────────────────────────────────────────────────

async def _update(conn, app_id, event, fields: dict) -> None:
    """Generic upsert for application_summary."""
    fields["last_event_type"] = event["event_type"]
    fields["last_event_at"] = event.get("recorded_at")

    set_clauses = ", ".join(
        f"{k} = ${i+2}" for i, k in enumerate(fields.keys())
    )
    values = [app_id] + list(fields.values())
    values.append(app_id)

    await conn.execute(f"""
        INSERT INTO application_summary (application_id, {', '.join(fields.keys())}, updated_at)
        VALUES ($1, {', '.join(f'${i+2}' for i in range(len(fields)))}, NOW())
        ON CONFLICT (application_id) DO UPDATE SET
            {set_clauses},
            updated_at = NOW()
    """, *values[:-1])


def _snake(event_type: str) -> str:
    import re
    return re.sub(r'(?<!^)(?=[A-Z])', '_', event_type).lower()