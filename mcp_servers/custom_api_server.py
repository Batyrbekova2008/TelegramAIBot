"""
MCP Server: Custom API tools (used as 3rd server in aggregator, Task 10)

Exposes simple utility tools that complement filesystem and postgres servers.
Run: python mcp_servers/custom_api_server.py
"""

import json
import os
from datetime import datetime

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("custom-api-server")


@mcp.tool()
async def get_api_status() -> str:
    """Return current API health status and timestamp."""
    return json.dumps({
        "status": "ok",
        "server": "custom-api",
        "timestamp": datetime.utcnow().isoformat(),
    })


@mcp.tool()
async def fetch_url_summary(url: str) -> str:
    """Fetch a public URL and return first 500 characters of its content."""
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(url)
            return json.dumps({
                "url": url,
                "status_code": resp.status_code,
                "preview": resp.text[:500],
            })
    except Exception as e:
        return json.dumps({"error": str(e), "url": url})


@mcp.tool()
async def translate_text(text: str, target_lang: str = "en") -> str:
    """Return a mock translation note (real integration requires paid API)."""
    return json.dumps({
        "original": text,
        "target_lang": target_lang,
        "note": "Real translation requires Google/DeepL API key.",
    })


if __name__ == "__main__":
    mcp.run(transport="stdio")
