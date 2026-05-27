"""
MCP Aggregator: connects to 3 servers simultaneously (Task 10)

Servers:
  fs__   — @modelcontextprotocol/server-filesystem (allowed_dir=data/)
  pg__   — mcp_servers/postgres_server.py   (role from MCP_PG_ROLE env)
  api__  — mcp_servers/custom_api_server.py

The aggregator merges tool lists with server-specific prefixes and
routes call_tool() requests to the correct backend server.

Usage:
    agg = MCPAggregator()
    await agg.connect_all()
    tools = agg.list_all_tools()          # [{"name": "fs__list_directory", ...}, ...]
    result = await agg.call_tool("pg__query_users", {"limit": 10})
    await agg.close_all()
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

log = logging.getLogger("mcp.aggregator")

_PROJECT_ROOT = Path(__file__).parent.parent
_VENV_PYTHON = str(_PROJECT_ROOT / "venv" / "Scripts" / "python.exe")
if not os.path.exists(_VENV_PYTHON):
    _VENV_PYTHON = "python"

# ── Per-server connection state ───────────────────────────────────────────────

class _ServerConn:
    def __init__(self, prefix: str, params: StdioServerParameters):
        self.prefix = prefix
        self.params = params
        self._stdio_ctx = None
        self._session_ctx = None
        self.session: ClientSession | None = None
        self.tools: list[dict] = []

    async def connect(self):
        try:
            self._stdio_ctx = stdio_client(self.params)
            read, write = await self._stdio_ctx.__aenter__()
            self._session_ctx = ClientSession(read, write)
            self.session = await self._session_ctx.__aenter__()
            await self.session.initialize()
            result = await self.session.list_tools()
            self.tools = [
                {
                    "name": f"{self.prefix}{t.name}",
                    "original_name": t.name,
                    "description": f"[{self.prefix}] {t.description or ''}",
                }
                for t in result.tools
            ]
            log.info("[%s] Connected, %d tools: %s", self.prefix, len(self.tools), [t["name"] for t in self.tools])
        except Exception as e:
            log.warning("[%s] Connection failed: %s", self.prefix, e)
            self.session = None
            self.tools = []

    async def close(self):
        for ctx in (self._session_ctx, self._stdio_ctx):
            if ctx:
                try:
                    await ctx.__aexit__(None, None, None)
                except Exception:
                    pass
        self.session = None

    async def call(self, original_name: str, arguments: dict) -> str:
        if not self.session:
            return f"[{self.prefix}] Server unavailable"
        try:
            result = await self.session.call_tool(original_name, arguments)
            parts = [c.text if hasattr(c, "text") else str(c) for c in result.content]
            return "\n".join(parts)
        except Exception as e:
            log.error("[%s] call_tool(%s) failed: %s", self.prefix, original_name, e)
            return f"[{self.prefix}] Error: {e}"


# ── Aggregator ────────────────────────────────────────────────────────────────

class MCPAggregator:
    def __init__(self):
        pg_role = os.environ.get("MCP_PG_ROLE", "teacher")
        data_dir = str(_PROJECT_ROOT / "data")
        pg_server = str(_PROJECT_ROOT / "mcp_servers" / "postgres_server.py")
        api_server = str(_PROJECT_ROOT / "mcp_servers" / "custom_api_server.py")

        self._servers: list[_ServerConn] = [
            _ServerConn(
                prefix="fs__",
                params=StdioServerParameters(
                    command="npx",
                    args=["-y", "@modelcontextprotocol/server-filesystem", data_dir],
                ),
            ),
            _ServerConn(
                prefix="pg__",
                params=StdioServerParameters(
                    command=_VENV_PYTHON,
                    args=[pg_server],
                    env={**os.environ, "MCP_ROLE": pg_role},
                ),
            ),
            _ServerConn(
                prefix="api__",
                params=StdioServerParameters(
                    command=_VENV_PYTHON,
                    args=[api_server],
                ),
            ),
        ]

    async def connect_all(self):
        await asyncio.gather(*[s.connect() for s in self._servers])

    async def close_all(self):
        await asyncio.gather(*[s.close() for s in self._servers])

    def list_all_tools(self) -> list[dict]:
        tools = []
        for s in self._servers:
            tools.extend(s.tools)
        return tools

    async def call_tool(self, prefixed_name: str, arguments: dict | None = None) -> str:
        arguments = arguments or {}
        for server in self._servers:
            if prefixed_name.startswith(server.prefix):
                original = prefixed_name[len(server.prefix):]
                return await server.call(original, arguments)
        return f"Unknown tool: {prefixed_name}"

    def is_ready(self) -> bool:
        return any(s.session is not None for s in self._servers)
