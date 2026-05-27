import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.llm_router import LLMRouter, _MODEL_FALLBACK_CHAIN


def _make_response(content="Hello!", tool_calls=None):
    """Build a minimal mock Groq response object."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_router_with_mock():
    """Return (LLMRouter, mock_client) with Groq client patched."""
    with patch("services.llm_router.AsyncGroq") as MockGroq:
        mock_client = AsyncMock()
        MockGroq.return_value = mock_client
        router = LLMRouter()
    router.client = mock_client  # attach for assertions
    return router, mock_client


# ── model selection ───────────────────────────────────────────────────────────

async def test_short_context_uses_default_model():
    router, mock_client = _make_router_with_mock()
    mock_client.chat.completions.create = AsyncMock(return_value=_make_response())

    messages = [{"role": "user", "content": "Hi"}]
    _, model = await router.send_chat_completion(messages)

    assert model == router.default_model
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == router.default_model


async def test_long_context_switches_to_large_model():
    router, mock_client = _make_router_with_mock()
    mock_client.chat.completions.create = AsyncMock(return_value=_make_response())

    long_content = "x" * 16000
    messages = [{"role": "user", "content": long_content}]
    _, model = await router.send_chat_completion(messages)

    assert model == "llama-3.3-70b-versatile"


async def test_returns_response_object():
    router, mock_client = _make_router_with_mock()
    expected = _make_response("Test answer")
    mock_client.chat.completions.create = AsyncMock(return_value=expected)

    response, _ = await router.send_chat_completion([{"role": "user", "content": "test"}])
    assert response.choices[0].message.content == "Test answer"


# ── fallback on error ─────────────────────────────────────────────────────────

async def test_fallback_to_next_model_on_error():
    router, mock_client = _make_router_with_mock()
    fallback_response = _make_response("Fallback answer")

    call_count = 0
    async def side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Primary model unavailable")
        return fallback_response

    mock_client.chat.completions.create = side_effect

    response, model = await router.send_chat_completion([{"role": "user", "content": "test"}])
    assert response.choices[0].message.content == "Fallback answer"
    assert call_count == 2


async def test_raises_when_all_models_fail():
    router, mock_client = _make_router_with_mock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("All down"))

    with pytest.raises(Exception, match="All down"):
        await router.send_chat_completion([{"role": "user", "content": "test"}])


# ── tools forwarding ──────────────────────────────────────────────────────────

async def test_tools_included_when_provided():
    router, mock_client = _make_router_with_mock()
    mock_client.chat.completions.create = AsyncMock(return_value=_make_response())

    tools = [{"type": "function", "function": {"name": "get_time"}}]
    await router.send_chat_completion([{"role": "user", "content": "time?"}], tools=tools)

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert "tools" in call_kwargs
    assert call_kwargs["tools"] == tools


async def test_tools_omitted_when_not_provided():
    router, mock_client = _make_router_with_mock()
    mock_client.chat.completions.create = AsyncMock(return_value=_make_response())

    await router.send_chat_completion([{"role": "user", "content": "hi"}])

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert "tools" not in call_kwargs


# ── streaming fallback ────────────────────────────────────────────────────────

async def test_stream_falls_back_to_non_streaming_on_error():
    router, mock_client = _make_router_with_mock()

    # First call (streaming) raises; second call (non-streaming fallback) succeeds
    call_count = 0
    async def side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if kwargs.get("stream"):
            raise Exception("Stream unavailable")
        return _make_response("Fallback text")

    mock_client.chat.completions.create = side_effect

    events = []
    async for event in router.stream_chat_completion([{"role": "user", "content": "hi"}]):
        events.append(event)

    types = [e[0] for e in events]
    assert "text" in types or "done" in types
    assert call_count == 2  # stream attempt + fallback
