import asyncio
import asyncpg
import json

async def main():
    conn = await asyncpg.connect('postgresql://ledger:ledger@localhost:5432/apex_ledger')
    try:
        # Patch old events to have the legacy model name
        await conn.execute("""
            UPDATE events 
            SET payload = jsonb_set(payload, '{model_version}', '"claude-sonnet-4-20250514"') 
            WHERE event_type IN ('AgentSessionCompleted', 'AgentSessionFailed', 'DecisionGenerated') 
            AND NOT (payload ? 'model_version');
        """)
        
        # Reset projection
        await conn.execute("TRUNCATE agent_performance_ledger;")
        await conn.execute("DELETE FROM projection_checkpoints WHERE projection_name='agent_performance_ledger';")
        print("Historical events patched and projection reset successfully")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
