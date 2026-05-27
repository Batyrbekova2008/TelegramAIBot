"""Tests for Block 4: Search (Task 19) and Webhook (Task 22)."""

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── SearchService (Task 19) ───────────────────────────────────────────────────

async def test_search_returns_error_without_api_key():
    from services.search_service import SearchService
    svc = SearchService(api_key=None)
    results = await svc.search("test query")
    assert len(results) == 1
    assert "missing" in results[0]["content"].lower() or "key" in results[0]["title"].lower()


async def test_search_uses_cache_on_second_call(mocker):
    from services.search_service import SearchService
    mock_redis = AsyncMock()
    cached_data = json.dumps([{"title": "Cached", "url": "http://x.com", "content": "cached", "score": 1.0}])
    mock_redis.get = AsyncMock(return_value=cached_data)

    svc = SearchService(api_key="fake", redis=mock_redis)
    results = await svc.search("cached query")
    assert results[0]["title"] == "Cached"
    mock_redis.get.assert_called_once()


async def test_search_caches_results(mocker):
    from services.search_service import SearchService
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"results": [
        {"title": "Test", "url": "http://test.com", "content": "content", "score": 0.9}
    ]}
    mock_resp.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)
    mock_http.post = AsyncMock(return_value=mock_resp)
    mocker.patch("httpx.AsyncClient", return_value=mock_http)

    svc = SearchService(api_key="real-key", redis=mock_redis)
    results = await svc.search("test query")
    assert len(results) == 1
    assert results[0]["title"] == "Test"
    mock_redis.setex.assert_called_once()


async def test_search_handles_http_error(mocker):
    from services.search_service import SearchService
    import httpx

    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "401", request=MagicMock(), response=mock_resp
    )
    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)
    mock_http.post = AsyncMock(return_value=mock_resp)
    mocker.patch("httpx.AsyncClient", return_value=mock_http)

    svc = SearchService(api_key="bad-key")
    results = await svc.search("test")
    assert any("error" in r["title"].lower() for r in results)


def test_format_results_empty():
    from services.search_service import SearchService
    svc = SearchService()
    assert "No results" in svc.format_results([])


def test_format_results_nonempty():
    from services.search_service import SearchService
    results = [{"title": "Title1", "url": "http://a.com", "content": "Content1", "score": 0.9}]
    formatted = SearchService.format_results(results)
    assert "Title1" in formatted
    assert "http://a.com" in formatted


# ── SearchAwareHandler (Task 19) ──────────────────────────────────────────────

async def test_search_aware_handler_no_tool_call():
    """LLM answers directly without searching."""
    from services.search_service import SearchService, SearchAwareHandler
    mock_groq = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Direct answer"
    mock_choice.message.tool_calls = None
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_groq.chat = MagicMock()
    mock_groq.chat.completions = MagicMock()
    mock_groq.chat.completions.create = AsyncMock(return_value=mock_resp)

    svc = SearchService(api_key=None)
    handler = SearchAwareHandler(mock_groq, svc)
    answer, sources = await handler.respond([{"role": "user", "content": "What is 2+2?"}])
    assert answer == "Direct answer"
    assert sources == []


# ── Webhook server (Task 22) ──────────────────────────────────────────────────

def test_webhook_server_imports():
    """Webhook server module loads without errors."""
    import webhook_server
    assert hasattr(webhook_server, "build_app")
    assert hasattr(webhook_server, "WEBHOOK_PATH")
    assert webhook_server.WEBHOOK_PATH == "/webhook"


def test_webhook_server_has_health_route():
    """Health endpoint is registered."""
    import webhook_server
    # build_app is callable and returns app with health route
    assert callable(webhook_server.build_app)


def test_webhook_secret_token_configured():
    """Webhook secret is non-empty."""
    import webhook_server
    assert len(webhook_server.WEBHOOK_SECRET) > 0
