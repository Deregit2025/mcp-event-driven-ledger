import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect("postgresql://ledger:ledger@localhost:5432/apex_ledger")
    rows = await conn.fetch(
        "SELECT event_type, recorded_at FROM events "
        "WHERE stream_id = 'compliance-APEX-DEMO-01' "
        "ORDER BY recorded_at"
    )
    for r in rows:
        print(r["event_type"], "→", r["recorded_at"])
    await conn.close()

asyncio.run(main())