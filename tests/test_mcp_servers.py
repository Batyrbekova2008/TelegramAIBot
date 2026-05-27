"""
Tests for Block 2: MCP servers (Tasks 7-12)

Covered:
  - postgres_server: role permissions, tools, resources, prompts (Tasks 8, 9, 11)
  - mcp_client: FilesystemMCPClient path validation (Task 7)
  - mcp_aggregator: tool listing and routing logic (Task 10)
  - sse_server: auth middleware (Task 12)
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── postgres_server — role permissions (Task 9) ───────────────────────────────

@pytest.fixture(autouse=True)
def _reset_pg_role():
    """Reset postgres_server role to 'student' before each test."""
    import mcp_servers.postgres_server as ps
    original = ps.ROLE
    yield
    ps.ROLE = original


def _set_role(role: str):
    import mcp_servers.postgres_server as ps
    ps.ROLE = role


async def test_student_can_call_query_users():
    _set_role("student")
    import mcp_servers.postgres_server as ps
    ps._check_role("query_users")   # should not raise


async def test_student_blocked_from_get_user_stats():
    _set_role("student")
    import mcp_servers.postgres_server as ps
    with pytest.raises(PermissionError, match="teacher"):
        ps._check_role("get_user_stats")


async def test_student_blocked_from_export_to_csv():
    _set_role("student")
    import mcp_servers.postgres_server as ps
    with pytest.raises(PermissionError):
        ps._check_role("export_to_csv")


async def test_teacher_can_call_query_users_and_stats():
    _set_role("teacher")
    import mcp_servers.postgres_server as ps
    ps._check_role("query_users")
    ps._check_role("get_user_stats")


async def test_teacher_blocked_from_export():
    _set_role("teacher")
    import mcp_servers.postgres_server as ps
    with pytest.raises(PermissionError, match="admin"):
        ps._check_role("export_to_csv")


async def test_admin_can_call_all_tools():
    _set_role("admin")
    import mcp_servers.postgres_server as ps
    for tool in ("query_users", "get_user_stats", "export_to_csv"):
        ps._check_role(tool)   # none should raise


# ── postgres_server — tools return valid data ─────────────────────────────────

async def test_query_users_returns_json_list():
    _set_role("student")
    import mcp_servers.postgres_server as ps
    result = await ps.query_users(limit=3)
    data = json.loads(result)
    assert isinstance(data, list)
    assert len(data) <= 3


async def test_query_users_mock_has_required_fields():
    _set_role("student")
    import mcp_servers.postgres_server as ps
    result = await ps.query_users(limit=10)
    data = json.loads(result)
    for row in data:
        assert "user_id" in row
        assert "username" in row


async def test_get_user_stats_returns_json():
    _set_role("teacher")
    import mcp_servers.postgres_server as ps
    result = await ps.get_user_stats(user_id=1)
    data = json.loads(result)
    assert "user_id" in data
    assert "stats" in data


async def test_export_to_csv_has_header():
    _set_role("admin")
    import mcp_servers.postgres_server as ps
    result = await ps.export_to_csv(limit=5)
    first_line = result.strip().split("\n")[0]
    assert "user_id" in first_line or "username" in first_line


async def test_export_to_csv_has_data_rows():
    _set_role("admin")
    import mcp_servers.postgres_server as ps
    result = await ps.export_to_csv(limit=5)
    lines = [l for l in result.strip().split("\n") if l]
    assert len(lines) >= 2   # header + at least one data row


# ── postgres_server — resources (Task 11) ────────────────────────────────────

async def test_document_template_essay():
    import mcp_servers.postgres_server as ps
    result = await ps.get_document_template("essay")
    assert "topic" in result.lower() or "тақырып" in result.lower()


async def test_document_template_unknown_returns_error():
    import mcp_servers.postgres_server as ps
    result = await ps.get_document_template("nonexistent")
    assert "not found" in result.lower() or "available" in result.lower()


async def test_users_resource_returns_json():
    import mcp_servers.postgres_server as ps
    result = await ps.get_users_resource()
    data = json.loads(result)
    assert isinstance(data, list)


# ── postgres_server — prompts (Task 11) ──────────────────────────────────────

async def test_analyze_code_prompt_contains_code():
    import mcp_servers.postgres_server as ps
    code = "def foo(): pass"
    result = await ps.analyze_code(code=code)
    assert "foo" in result


async def test_explain_topic_prompt_contains_topic():
    import mcp_servers.postgres_server as ps
    result = await ps.explain_topic(topic="recursion")
    assert "recursion" in result.lower()


async def test_summarize_dialog_prompt_contains_dialog():
    import mcp_servers.postgres_server as ps
    dialog = "Alice: Hi\nBob: Hello"
    result = await ps.summarize_dialog(dialog=dialog)
    assert "Alice" in result or "dialog" in result.lower()


# ── mcp_client — path validation (Task 7) ────────────────────────────────────

def test_filesystem_client_rejects_path_traversal():
    from services.mcp_client import FilesystemMCPClient
    client = FilesystemMCPClient(allowed_dir="/tmp/safe")
    with pytest.raises(ValueError, match="escapes"):
        client._resolve("../../etc/passwd")


def test_filesystem_client_accepts_valid_path():
    import tempfile, os
    from services.mcp_client import FilesystemMCPClient
    with tempfile.TemporaryDirectory() as tmpdir:
        client = FilesystemMCPClient(allowed_dir=tmpdir)
        resolved = client._resolve("subdir/file.txt")
        assert resolved.startswith(os.path.abspath(tmpdir))


# ── mcp_aggregator — tool listing and routing (Task 10) ──────────────────────

async def test_aggregator_routes_to_correct_server(mocker):
    from services.mcp_aggregator import MCPAggregator, _ServerConn
    agg = MCPAggregator()

    # Mock servers with preset tools and a call method
    mock_fs = mocker.AsyncMock(spec=_ServerConn)
    mock_fs.prefix = "fs__"
    mock_fs.tools = [{"name": "fs__list_directory", "description": "list dir"}]
    mock_fs.call = mocker.AsyncMock(return_value="file1.txt\nfile2.txt")

    mock_pg = mocker.AsyncMock(spec=_ServerConn)
    mock_pg.prefix = "pg__"
    mock_pg.tools = [{"name": "pg__query_users", "description": "users"}]
    mock_pg.call = mocker.AsyncMock(return_value='[{"user_id":1}]')

    agg._servers = [mock_fs, mock_pg]

    # list_all_tools should merge both
    tools = agg.list_all_tools()
    assert len(tools) == 2
    names = [t["name"] for t in tools]
    assert "fs__list_directory" in names
    assert "pg__query_users" in names

    # Routing: fs__ call goes to mock_fs
    result = await agg.call_tool("fs__list_directory", {})
    assert result == "file1.txt\nfile2.txt"
    mock_fs.call.assert_called_once_with("list_directory", {})

    # Routing: pg__ call goes to mock_pg
    result2 = await agg.call_tool("pg__query_users", {"limit": 5})
    mock_pg.call.assert_called_once_with("query_users", {"limit": 5})


async def test_aggregator_returns_error_for_unknown_tool(mocker):
    from services.mcp_aggregator import MCPAggregator
    agg = MCPAggregator()
    agg._servers = []
    result = await agg.call_tool("unknown__tool", {})
    assert "Unknown" in result


# ── sse_server — auth middleware (Task 12) ────────────────────────────────────

async def test_sse_server_rejects_missing_token():
    from starlette.testclient import TestClient
    import mcp_servers.sse_server as ss
    ss.BEARER_TOKEN = "test-secret"
    client = TestClient(ss.app, raise_server_exceptions=False)
    resp = client.get("/sse")
    assert resp.status_code == 401


async def test_sse_server_health_no_auth():
    from starlette.testclient import TestClient
    import mcp_servers.sse_server as ss
    client = TestClient(ss.app, raise_server_exceptions=False)
    resp = client.get("/health")
    assert resp.status_code == 200


async def test_sse_server_rejects_wrong_token():
    from starlette.testclient import TestClient
    import mcp_servers.sse_server as ss
    ss.BEARER_TOKEN = "correct-token"
    client = TestClient(ss.app, raise_server_exceptions=False)
    resp = client.get("/sse", headers={"Authorization": "Bearer wrong-token"})
    assert resp.status_code == 401
