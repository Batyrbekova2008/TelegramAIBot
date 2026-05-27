"""
MCP Server: HTTP/SSE transport (Task 12)

Same tools as postgres_server but served over HTTP + SSE instead of stdio.
Authentication via Bearer token in Authorization header.

Run:
  MCP_BEARER_TOKEN=secret123 python mcp_servers/sse_server.py

Docker (separate container):
  docker run -e MCP_BEARER_TOKEN=secret123 -p 8001:8001 bot-mcp-sse

Reconnection: SSE clients reconnect automatically on disconnect (handled by SSE spec).
The server is stateless so reconnects are transparent.
"""

import logging
import os

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

BEARER_TOKEN = os.environ.get("MCP_BEARER_TOKEN", "changeme")
PORT = int(os.environ.get("MCP_SSE_PORT", 8001))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sse_server")

# ── Auth middleware ────────────────────────────────────────────────────────────

class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/health",):
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != BEARER_TOKEN:
            log.warning("Unauthorized request from %s", request.client)
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)

# ── MCP server ────────────────────────────────────────────────────────────────

mcp = FastMCP("postgres-sse-server")


@mcp.tool()
async def query_users_sse(limit: int = 20) -> str:
    """Return user list (SSE transport version)."""
    import json
    users = [
        {"user_id": 1, "username": "alice", "message_count": 42},
        {"user_id": 2, "username": "bob",   "message_count": 17},
    ]
    return json.dumps(users[:limit], ensure_ascii=False)


@mcp.tool()
async def get_server_status() -> str:
    """Return SSE server health status."""
    import json
    return json.dumps({"status": "ok", "transport": "HTTP/SSE", "port": PORT})


# ── Starlette app with SSE transport ─────────────────────────────────────────

sse = SseServerTransport("/messages/")

async def handle_sse(request: Request):
    async with sse.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await mcp._mcp_server.run(
            streams[0], streams[1],
            mcp._mcp_server.create_initialization_options(),
        )


async def health(request: Request):
    from starlette.responses import PlainTextResponse
    return PlainTextResponse("OK")


app = Starlette(
    routes=[
        Route("/health", health),
        Route("/sse", handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ]
)
app.add_middleware(BearerAuthMiddleware)


if __name__ == "__main__":
    log.info("Starting MCP SSE server on port %d", PORT)
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
