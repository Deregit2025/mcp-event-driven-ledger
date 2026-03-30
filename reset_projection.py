import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect('postgresql://ledger:ledger@localhost:5432/apex_ledger')
    try:
        await conn.execute("TRUNCATE agent_performance_ledger;")
        await conn.execute("DELETE FROM projection_checkpoints WHERE projection_name='agent_performance_ledger';")
        print("Successfully reset agent_performance_ledger")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
