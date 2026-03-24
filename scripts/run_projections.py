"""
scripts/run_projections.py
One-shot projection runner — processes all existing events once.
"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.projections.daemon import ProjectionDaemon
from src.projections.application_summary import ApplicationSummaryProjection
from src.projections.agent_performance import AgentPerformanceLedgerProjection
from src.projections.compliance_audit import ComplianceAuditViewProjection

DB_URL = "postgresql://ledger:ledger@localhost:5432/apex_ledger"

async def run():
    daemon = ProjectionDaemon(DB_URL)
    daemon.register(ApplicationSummaryProjection())
    daemon.register(AgentPerformanceLedgerProjection())
    daemon.register(ComplianceAuditViewProjection())
    await daemon.connect()

    async with daemon._pool.acquire() as conn:
        for projection in daemon._projections:
            print(f"\nProcessing {projection.name}...")
            checkpoint = await daemon._load_checkpoint(conn, projection.name)
            rows = await conn.fetch(
                "SELECT event_id, stream_id, stream_position, global_position,"
                "       event_type, event_version, payload, metadata, recorded_at"
                " FROM events WHERE global_position > $1"
                " ORDER BY global_position ASC",
                checkpoint,
            )
            print(f"  Found {len(rows)} events")
            errors = 0
            for row in rows:
                event = {
                    "event_id": str(row["event_id"]),
                    "stream_id": row["stream_id"],
                    "stream_position": row["stream_position"],
                    "global_position": row["global_position"],
                    "event_type": row["event_type"],
                    "event_version": row["event_version"],
                    "payload": (dict(row["payload"]) if isinstance(row["payload"], dict) else __import__('json').loads(row["payload"])) if row["payload"] else {},
                    "metadata": (dict(row["metadata"]) if isinstance(row["metadata"], dict) else __import__('json').loads(row["metadata"])) if row["metadata"] else {},
                    "recorded_at": row["recorded_at"],
                }
                try:
                    async with conn.transaction():
                        await projection.handle(event, conn)
                        await daemon._save_checkpoint(
                            conn, projection.name, event["global_position"]
                        )
                except Exception as e:
                    errors += 1
                    print(f"  ERROR on {event['event_type']} pos={event['global_position']}: {e}")

            print(f"  Done — {len(rows) - errors} processed, {errors} errors")

    await daemon.close()
    print("\nAll projections populated.")

asyncio.run(run())