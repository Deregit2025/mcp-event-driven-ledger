import asyncio
from src.event_store import EventStore
from src.mcp.server import create_server
import json
import os

async def main():
    store = EventStore(os.environ.get("DATABASE_URL", "postgresql://ledger:ledger@localhost:5432/apex_ledger"))
    await store.connect()
    print("Store connected.")
    
    server = create_server(store=store)
    tools = server.tools
    
    # 1. Test Application Summary
    print("\n--- Testing ledger_get_application ---")
    res = await tools.execute("ledger_get_application", {"application_id": "APEX-TEST-01"})
    print("Is Error:", "error_type" in res)
    print(json.dumps(res, indent=2)[:300] + "...")
    
    # 2. Test Audit Trail
    print("\n--- Testing ledger_get_audit_trail ---")
    res = await tools.execute("ledger_get_audit_trail", {"application_id": "APEX-TEST-01"})
    print("Is Error:", "error_type" in res)
    print(json.dumps(res, indent=2)[:300] + "...")
    
    # 3. Test Agent Performance
    print("\n--- Testing ledger_get_agent_performance ---")
    res = await tools.execute("ledger_get_agent_performance", {"agent_id": "credit_analysis"})
    print("Is Error:", "error_type" in res)
    print(json.dumps(res, indent=2)[:300] + "...")
    
    # 4. Test Session (grab first session from agent performance, or hardcode if not available)
    print("\n--- Testing ledger_get_session ---")
    res = await tools.execute("ledger_get_session", {"session_id": "sess-credit-APEX-TEST-01"})
    print("Is Error:", "error_type" in res)
    print(json.dumps(res, indent=2)[:300] + "...")

if __name__ == "__main__":
    asyncio.run(main())
