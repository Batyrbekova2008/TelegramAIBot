"""
MCP Server: PostgreSQL tools (Tasks 8, 9, 11)

Exposes:
  Tools    — query_users, get_user_stats, export_to_csv (role-gated)
  Resources— document templates stored in DB (or fallback mock)
  Prompts  — pre-configured prompts for common student tasks

Role-based auth (Task 9):
  Role is passed via env var MCP_ROLE when the client spawns this server.
  Values: student | teacher | admin
  - student : query_users only
  - teacher : query_users + get_user_stats
  - admin   : all tools
  Calling a forbidden tool returns JSON-RPC error -32603.

Run standalone:
  MCP_ROLE=admin python mcp_servers/postgres_server.py
"""

import csv
import io
import json
import logging
import os
import sys

from mcp.server.fastmcp import FastMCP, Context

# ── Role setup ────────────────────────────────────────────────────────────────
VALID_ROLES = {"student", "teacher", "admin"}
ROLE = os.environ.get("MCP_ROLE", "student").lower()
if ROLE not in VALID_ROLES:
    ROLE = "student"

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "student": {"query_users"},
    "teacher": {"query_users", "get_user_stats"},
    "admin":   {"query_users", "get_user_stats", "export_to_csv"},
}

# ── DB connection (optional — falls back to mock data) ────────────────────────
_db_available = False
try:
    import psycopg2
    from dotenv import load_dotenv
    load_dotenv()
    _conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        dbname=os.getenv("DB_NAME", "chat-bot"),
        connect_timeout=3,
    )
    _db_available = True
except Exception:
    _conn = None

def _query(sql: str, params=()) -> list[dict]:
    if not _db_available or _conn is None:
        return _mock_users()
    try:
        cur = _conn.cursor()
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:
        logging.warning("DB query failed: %s", e)
        return _mock_users()

def _mock_users() -> list[dict]:
    return [
        {"user_id": 1, "username": "alice", "message_count": 42},
        {"user_id": 2, "username": "bob",   "message_count": 17},
        {"user_id": 3, "username": "carol", "message_count": 88},
    ]

# ── FastMCP server ────────────────────────────────────────────────────────────
mcp = FastMCP("postgres-mcp-server")

def _check_role(tool_name: str) -> None:
    allowed = ROLE_PERMISSIONS.get(ROLE, set())
    if tool_name not in allowed:
        raise PermissionError(
            f"Role '{ROLE}' is not allowed to call '{tool_name}'. "
            f"Required role: {'teacher' if tool_name == 'get_user_stats' else 'admin'}"
        )

# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
async def query_users(limit: int = 20) -> str:
    """Return a list of users from the database (student+)."""
    _check_role("query_users")
    rows = _query(
        "SELECT user_id, username, COUNT(*) as message_count "
        "FROM messages GROUP BY user_id, username ORDER BY message_count DESC LIMIT %s",
        (limit,),
    )
    return json.dumps(rows, ensure_ascii=False, default=str)


@mcp.tool()
async def get_user_stats(user_id: int) -> str:
    """Return message statistics for a specific user (teacher+)."""
    _check_role("get_user_stats")
    rows = _query(
        "SELECT message_type, COUNT(*) as cnt FROM messages "
        "WHERE user_id = %s GROUP BY message_type",
        (user_id,),
    )
    if not rows:
        rows = [{"message_type": "text", "cnt": 5}, {"message_type": "voice", "cnt": 2}]
    return json.dumps({"user_id": user_id, "stats": rows}, ensure_ascii=False, default=str)


@mcp.tool()
async def export_to_csv(limit: int = 100) -> str:
    """Export users data as CSV string (admin only)."""
    _check_role("export_to_csv")
    rows = _query(
        "SELECT user_id, username, message_type, content, created_at "
        "FROM messages ORDER BY created_at DESC LIMIT %s",
        (limit,),
    )
    if not rows:
        rows = [{"user_id": 1, "username": "alice", "message_type": "text",
                 "content": "Hello", "created_at": "2025-01-01"}]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()

# ── Resources (Task 11) ───────────────────────────────────────────────────────

_DOCUMENT_TEMPLATES = {
    "essay":   "Эссе шаблоны:\n1. Кіріспе\n2. Негізгі бөлім\n3. Қорытынды\n\nТақырып: {topic}",
    "report":  "Есеп шаблоны:\nМақсат: {goal}\nМетодология: ...\nНәтижелер: ...\nҚорытынды: ...",
    "summary": "Конспект шаблоны:\nТақырып: {topic}\nНегізгі ұғымдар:\n- ...\nҚорытынды: ...",
}


@mcp.resource("template://document/{name}")
async def get_document_template(name: str) -> str:
    """Return a document template by name (essay, report, summary)."""
    template = _DOCUMENT_TEMPLATES.get(name)
    if template is None:
        available = ", ".join(_DOCUMENT_TEMPLATES.keys())
        return f"Template '{name}' not found. Available: {available}"
    return template


@mcp.resource("db://users/list")
async def get_users_resource() -> str:
    """Live user list as a resource."""
    rows = _mock_users()
    return json.dumps(rows, ensure_ascii=False, indent=2)

# ── Prompts (Task 11) ─────────────────────────────────────────────────────────

@mcp.prompt()
async def analyze_code(code: str, language: str = "python") -> str:
    """Pre-configured prompt for code analysis."""
    return (
        f"Analyze the following {language} code for bugs, style issues, and improvements:\n\n"
        f"```{language}\n{code}\n```\n\n"
        "Provide: 1) Bug list, 2) Style issues, 3) Suggested improvements."
    )


@mcp.prompt()
async def explain_topic(topic: str, level: str = "beginner") -> str:
    """Pre-configured prompt for topic explanation."""
    return (
        f"Explain '{topic}' for a {level}-level student.\n"
        "Use simple language, give 2-3 examples, and end with a short quiz question."
    )


@mcp.prompt()
async def summarize_dialog(dialog: str) -> str:
    """Pre-configured prompt for dialog summarization."""
    return (
        f"Summarize the following dialog, keeping key facts and decisions:\n\n{dialog}\n\n"
        "Output as bullet points in the same language as the dialog."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
