"""
MCP Client: connects to @modelcontextprotocol/server-filesystem (Task 7)

Usage:
    client = FilesystemMCPClient(allowed_dir="data/")
    async with client:
        listing = await client.list_directory(".")
        content = await client.read_file("readme.txt")
"""

import logging
import os
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

log = logging.getLogger("mcp.filesystem")

# Absolute path to the directory served by the filesystem MCP server
_PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_ALLOWED_DIR = str(_PROJECT_ROOT / "data")


class FilesystemMCPClient:
    def __init__(self, allowed_dir: str = DEFAULT_ALLOWED_DIR):
        self.allowed_dir = os.path.abspath(allowed_dir)
        self._read = None
        self._write = None
        self._session: ClientSession | None = None
        self._stdio_ctx = None
        self._session_ctx = None
        self._tools: list[dict] = []

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *_):
        await self.close()

    async def connect(self):
        params = StdioServerParameters(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", self.allowed_dir],
        )
        self._stdio_ctx = stdio_client(params)
        self._read, self._write = await self._stdio_ctx.__aenter__()
        self._session_ctx = ClientSession(self._read, self._write)
        self._session = await self._session_ctx.__aenter__()
        await self._session.initialize()
        result = await self._session.list_tools()
        self._tools = [
            {"name": t.name, "description": t.description or ""}
            for t in result.tools
        ]
        log.info("Connected to filesystem MCP server. Tools: %s", [t["name"] for t in self._tools])

    async def close(self):
        if self._session_ctx:
            try:
                await self._session_ctx.__aexit__(None, None, None)
            except Exception:
                pass
        if self._stdio_ctx:
            try:
                await self._stdio_ctx.__aexit__(None, None, None)
            except Exception:
                pass
        self._session = None

    def get_tools(self) -> list[dict]:
        return list(self._tools)

    async def list_tools(self) -> list[dict]:
        if not self._session:
            raise RuntimeError("Not connected")
        result = await self._session.list_tools()
        return [{"name": t.name, "description": t.description or ""} for t in result.tools]

    async def call_tool(self, name: str, arguments: dict | None = None) -> str:
        if not self._session:
            raise RuntimeError("Not connected")
        result = await self._session.call_tool(name, arguments or {})
        parts = []
        for content in result.content:
            if hasattr(content, "text"):
                parts.append(content.text)
            else:
                parts.append(str(content))
        return "\n".join(parts)

    async def list_directory(self, path: str = ".") -> str:
        """List contents of a directory (relative to allowed_dir)."""
        return await self.call_tool("list_directory", {"path": self._resolve(path)})

    async def read_file(self, path: str) -> str:
        """Read a file (relative to allowed_dir)."""
        return await self.call_tool("read_file", {"path": self._resolve(path)})

    def _resolve(self, rel_path: str) -> str:
        base = Path(self.allowed_dir)
        target = (base / rel_path).resolve()
        # Ensure we stay inside allowed_dir (security guard)
        if not str(target).startswith(str(base)):
            raise ValueError(f"Path '{rel_path}' escapes allowed directory")
        return str(target)


async def get_filesystem_client() -> FilesystemMCPClient:
    """Factory: create and connect a filesystem MCP client."""
    client = FilesystemMCPClient()
    await client.connect()
    return client
