"""
src/mcp/server.py
==================
MCP server for the Apex Ledger.

Exposes the event store to Claude Desktop (or any MCP client) via:
  - Tools: write-side (append events, run commands)
  - Resources: read-side (query projections)

Uses sys.stdout.write directly for Windows compatibility —
asyncio connect_write_pipe breaks on Windows ProactorEventLoop.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import sys

logger = logging.getLogger(__name__)


# ── SERVER FACTORY ────────────────────────────────────────────────────────────

def create_server(store=None, daemon=None, db_pool=None):
    from src.upcasting.upcasters import registry as upcaster_registry
    from src.mcp.tools import LedgerToolExecutor, TOOL_DEFINITIONS
    from src.mcp.resources import LedgerResourceReader, RESOURCE_TEMPLATES

    if store is None:
        from src.event_store import InMemoryEventStore
        store = InMemoryEventStore(upcaster_registry=upcaster_registry)
        logger.warning("Using InMemoryEventStore — data will not persist between restarts")

    resource_reader = LedgerResourceReader(store, projection_daemon=daemon, db_pool=db_pool)
    tool_executor = LedgerToolExecutor(store, resource_reader=resource_reader)

    return LedgerMCPServer(
        store=store,
        tool_executor=tool_executor,
        resource_reader=resource_reader,
        tool_definitions=TOOL_DEFINITIONS,
        resource_templates=RESOURCE_TEMPLATES,
    )


# ── SERVER ────────────────────────────────────────────────────────────────────

class LedgerMCPServer:
    """
    Minimal MCP server — handles JSON-RPC 2.0 messages over stdio.
    Uses sys.stdout.write for Windows compatibility.
    """

    def __init__(self, store, tool_executor, resource_reader,
                 tool_definitions, resource_templates):
        self.store = store
        self.tools = tool_executor
        self.resources = resource_reader
        self.tool_definitions = tool_definitions
        self.resource_templates = resource_templates

    # ── STDIO TRANSPORT ───────────────────────────────────────────────────────

    async def run_stdio(self) -> None:
        """
        Run on stdin/stdout — Windows-compatible implementation.
        Reads stdin in a thread (avoids ProactorEventLoop pipe issues on Windows).
        Writes to stdout directly via sys.stdout.write.
        """
        logger.info("Apex Ledger MCP server starting on stdio")
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def _read_stdin():
            """Blocking stdin reader — runs in a thread."""
            try:
                for line in sys.stdin:
                    stripped = line.strip()
                    if stripped:
                        loop.call_soon_threadsafe(queue.put_nowait, stripped)
            except Exception as e:
                logger.error(f"Stdin reader error: {e}")
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

        import threading
        t = threading.Thread(target=_read_stdin, daemon=True)
        t.start()

        while True:
            try:
                raw = await queue.get()
                if raw is None:  # sentinel — stdin closed
                    break
                message = json.loads(raw)
                response = await self._handle_message(message)
                if response is not None:
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON received: {e}")
            except Exception as e:
                logger.error(f"Server error: {e}")

    # ── MESSAGE HANDLER ───────────────────────────────────────────────────────

    async def _handle_message(self, msg: dict) -> dict | None:
        method = msg.get("method", "")
        msg_id = msg.get("id")
        params = msg.get("params", {})

        handlers = {
            "initialize":              self._handle_initialize,
            "notifications/initialized": self._handle_notification,
            "tools/list":              self._handle_tools_list,
            "tools/call":              self._handle_tool_call,
            "resources/list":          self._handle_resources_list,
            "resources/read":          self._handle_resource_read,
            "ping":                    self._handle_ping,
        }

        handler = handlers.get(method)
        if not handler:
            # Silently ignore unknown notifications (no id = notification)
            if msg_id is None:
                return None
            return self._error(msg_id, -32601, f"Method not found: {method}")

        try:
            result = await handler(params)
            # Notifications return None — no response sent
            if msg_id is None or result is None:
                return None
            return {"jsonrpc": "2.0", "id": msg_id, "result": result}
        except Exception as e:
            logger.error(f"Handler error for {method}: {e}")
            if msg_id is None:
                return None
            return self._error(msg_id, -32000, str(e))

    # ── METHOD HANDLERS ───────────────────────────────────────────────────────

    async def _handle_initialize(self, params: dict) -> dict:
        client_version = params.get("protocolVersion", "2024-11-05")
        return {
            "protocolVersion": client_version,
            "capabilities": {
                "tools": {},
                "resources": {"subscribe": False, "listChanged": False},
            },
            "serverInfo": {"name": "apex-ledger", "version": "1.0.0"},
        }

    async def _handle_notification(self, params: dict) -> None:
        """Acknowledge notifications/initialized — no response needed."""
        return None

    async def _handle_ping(self, params: dict) -> dict:
        return {}

    async def _handle_tools_list(self, params: dict) -> dict:
        return {"tools": self.tool_definitions}

    async def _handle_tool_call(self, params: dict) -> dict:
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        result = await self.tools.execute(tool_name, arguments)
        is_error = "error_type" in result or "error" in result
        return {
            "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
            "isError": is_error,
        }

    async def _handle_resources_list(self, params: dict) -> dict:
        return {"resources": self.resource_templates}

    async def _handle_resource_read(self, params: dict) -> dict:
        uri = params.get("uri", "")
        return await self.resources.read(uri)

    @staticmethod
    def _error(msg_id, code: int, message: str) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": code, "message": message},
        }


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

async def main():
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stderr,  # MCP servers MUST log to stderr, never stdout
    )

    db_url = os.getenv("DATABASE_URL")
    store = None
    db_pool = None

    if db_url:
        from src.event_store import EventStore
        from src.upcasting.upcasters import registry as upcaster_registry
        store = EventStore(db_url, upcaster_registry=upcaster_registry)
        await store.connect()
        logger.info("Connected to PostgreSQL event store")

        # Optional: connect asyncpg pool for projection reads
        try:
            import asyncpg
            db_pool = await asyncpg.create_pool(db_url)
            logger.info("Connected asyncpg pool for projection reads")
        except Exception as e:
            logger.warning(f"Could not create asyncpg pool: {e} — projection reads degraded")
    else:
        logger.warning("DATABASE_URL not set — using InMemoryEventStore")

    server = create_server(store=store, db_pool=db_pool)
    await server.run_stdio()


if __name__ == "__main__":
    asyncio.run(main())