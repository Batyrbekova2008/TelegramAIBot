"""
Integration / E2E scenario tests (Task 24)

15 scenarios covering the full bot flow using mocked external services.
Tests use aiogram's test utilities + mocked Groq/Ollama.
"""

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_message(text: str, user_id: int = 123, chat_id: int = 456, first_name: str = "Alik"):
    """Create a minimal mock aiogram Message object."""
    msg = MagicMock()
    msg.text = text
    msg.from_user = MagicMock()
    msg.from_user.id = user_id
    msg.from_user.username = "testuser"
    msg.from_user.first_name = first_name
    msg.chat = MagicMock()
    msg.chat.id = chat_id
    msg.answer = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))
    msg.bot = MagicMock()
    msg.bot.get_file = AsyncMock()
    msg.bot.download_file = AsyncMock()
    return msg


def _make_groq_response(content: str, tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ── Scenario 1: /start greeting ───────────────────────────────────────────────

async def test_scenario_start_greets_by_name():
    from handlers.messages import handle_start
    msg = _make_message("/start", first_name="Alik")
    await handle_start(msg)
    msg.answer.assert_called_once()
    call_text = msg.answer.call_args[0][0]
    assert "AI" in call_text or "Сәлем" in call_text


# ── Scenario 2: /help shows commands ─────────────────────────────────────────

async def test_scenario_help_shows_html():
    from handlers.messages import handle_help
    msg = _make_message("/help")
    await handle_help(msg)
    msg.answer.assert_called_once()
    call_kwargs = msg.answer.call_args.kwargs
    assert call_kwargs.get("parse_mode") == "HTML"


# ── Scenario 3: text message → Groq response ─────────────────────────────────

async def test_scenario_text_message_gets_ai_response(mocker):
    from handlers.messages import handle_text
    msg = _make_message("Что такое Python?")
    sent_msg = MagicMock()
    sent_msg.edit_text = AsyncMock()
    msg.answer = AsyncMock(return_value=sent_msg)

    mocker.patch("services.rate_limiter.RateLimiter.check_limits", AsyncMock(return_value=True))
    mocker.patch("services.summary_manager.SummaryManager.add_message", AsyncMock())
    mocker.patch("services.summary_manager.SummaryManager.get_history",
                 AsyncMock(return_value=[{"role": "user", "content": "Что такое Python?"}]))
    mocker.patch("config.database.save_message", AsyncMock())

    # Mock streaming: one text chunk then done
    async def mock_stream(*args, **kwargs):
        yield ("text", "Python — это язык программирования.", "llama-3.1-8b-instant")
        yield ("done", "Python — это язык программирования.", "llama-3.1-8b-instant")

    mocker.patch("services.llm_router.LLMRouter.stream_chat_completion", mock_stream)
    await handle_text(msg)
    sent_msg.edit_text.assert_called()


# ── Scenario 4: rate limit blocks excess requests ────────────────────────────

async def test_scenario_rate_limit_blocks_request(mocker):
    from handlers.messages import handle_text
    msg = _make_message("flood")
    mocker.patch("services.rate_limiter.RateLimiter.check_limits", AsyncMock(return_value=False))
    await handle_text(msg)
    call_text = msg.answer.call_args[0][0]
    assert "Тым көп" in call_text or "сұраныс" in call_text


# ── Scenario 5: voice message → transcription + AI ────────────────────────────

async def test_scenario_voice_transcription(mocker):
    from handlers.messages import handle_voice
    import tempfile, os

    msg = _make_message("")
    msg.text = None
    msg.voice = MagicMock()
    msg.voice.file_id = "file123"
    msg.audio = None

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp.write(b"fake audio")
        tmp_path = tmp.name

    mock_file = MagicMock()
    mock_file.file_path = "path/to/audio.ogg"
    msg.bot.get_file = AsyncMock(return_value=mock_file)
    msg.bot.download_file = AsyncMock()
    msg.answer = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))
    msg.answer_voice = AsyncMock()

    mocker.patch("services.rate_limiter.RateLimiter.check_limits", AsyncMock(return_value=True))

    mock_transcription = MagicMock()
    mock_transcription.text = "Привет мир"
    mocker.patch("groq.AsyncGroq.audio", create=True)
    mocker.patch("handlers.messages.groq_client.audio.transcriptions.create",
                 AsyncMock(return_value=mock_transcription))

    mocker.patch("services.summary_manager.SummaryManager.add_message", AsyncMock())
    mocker.patch("services.summary_manager.SummaryManager.get_history",
                 AsyncMock(return_value=[{"role": "user", "content": "Привет мир"}]))
    mocker.patch("services.llm_router.LLMRouter.send_chat_completion",
                 AsyncMock(return_value=(_make_groq_response("Привет!"), "model")))
    mocker.patch("config.database.save_message", AsyncMock())
    mocker.patch("services.tts_service.text_to_speech", AsyncMock(return_value=tmp_path))

    await handle_voice(msg)
    os.unlink(tmp_path)
    msg.answer.assert_called()


# ── Scenario 6: photo → vision analysis ──────────────────────────────────────

async def test_scenario_photo_analysis(mocker):
    from handlers.messages import handle_photo
    import tempfile, os

    msg = _make_message("")
    msg.text = None
    msg.photo = [MagicMock(file_id="photo123")]
    msg.caption = None

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(b"fake image data")
        tmp_path = tmp.name

    mock_file = MagicMock()
    mock_file.file_path = "photos/test.jpg"
    msg.bot.get_file = AsyncMock(return_value=mock_file)
    msg.bot.download_file = AsyncMock()
    msg.answer = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))

    mocker.patch("services.rate_limiter.RateLimiter.check_limits", AsyncMock(return_value=True))
    mocker.patch("handlers.messages.groq_client.chat.completions.create",
                 AsyncMock(return_value=_make_groq_response("Image shows a cat.")))
    mocker.patch("config.database.save_message", AsyncMock())

    # Patch tempfile so it writes to our known path
    mocker.patch("tempfile.NamedTemporaryFile", return_value=MagicMock(
        __enter__=lambda s: s, __exit__=MagicMock(return_value=False),
        name=tmp_path
    ))
    # Patch open to return fake image bytes
    mocker.patch("builtins.open", mocker.mock_open(read_data=b"fake"))
    mocker.patch("os.unlink", MagicMock())

    await handle_photo(msg)
    os.unlink(tmp_path)
    msg.answer.assert_called()


# ── Scenario 7: /files command ───────────────────────────────────────────────

async def test_scenario_files_command_calls_mcp(mocker):
    from handlers.mcp_handlers import handle_files
    msg = _make_message("/files")
    status_msg = MagicMock()
    status_msg.edit_text = AsyncMock()
    msg.answer = AsyncMock(return_value=status_msg)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.list_directory = AsyncMock(return_value='[{"type":"file","name":"readme.txt"}]')
    mocker.patch("handlers.mcp_handlers.FilesystemMCPClient", return_value=mock_client)

    await handle_files(msg)
    mock_client.list_directory.assert_called_once_with(".")
    status_msg.edit_text.assert_called_once()


# ── Scenario 8: /mcp shows tools ─────────────────────────────────────────────

async def test_scenario_mcp_lists_tools():
    from handlers.mcp_handlers import handle_mcp_list
    msg = _make_message("/mcp")
    mock_agg = MagicMock()
    mock_agg.is_ready.return_value = True
    mock_agg.list_all_tools.return_value = [
        {"name": "fs__list_directory", "description": "list dir"},
        {"name": "pg__query_users", "description": "users"},
    ]
    await handle_mcp_list(msg, mcp_aggregator=mock_agg)
    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "fs__list_directory" in text or "Filesystem" in text


# ── Scenario 9: /mcp with aggregator not ready ────────────────────────────────

async def test_scenario_mcp_not_ready():
    from handlers.mcp_handlers import handle_mcp_list
    msg = _make_message("/mcp")
    await handle_mcp_list(msg, mcp_aggregator=None)
    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "не инициализирован" in text or "агрегатор" in text


# ── Scenario 10: /private toggles mode ───────────────────────────────────────

async def test_scenario_private_toggle_ollama_unavailable(mocker):
    from handlers.ollama_handlers import handle_private_toggle, _private_chats
    _private_chats.discard(456)
    msg = _make_message("/private")
    mocker.patch("handlers.ollama_handlers.ollama_service.is_available", AsyncMock(return_value=False))
    await handle_private_toggle(msg)
    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "недоступна" in text or "Ollama" in text
    assert 456 not in _private_chats


async def test_scenario_private_toggle_on(mocker):
    from handlers.ollama_handlers import handle_private_toggle, _private_chats
    _private_chats.discard(456)
    msg = _make_message("/private")
    mocker.patch("handlers.ollama_handlers.ollama_service.is_available", AsyncMock(return_value=True))
    mocker.patch("handlers.ollama_handlers.ollama_service.list_models", AsyncMock(return_value=["llama3.2:3b"]))
    await handle_private_toggle(msg)
    assert 456 in _private_chats
    _private_chats.discard(456)


# ── Scenario 11: /ask with empty RAG index ───────────────────────────────────

async def test_scenario_ask_empty_index(mocker):
    from handlers.ollama_handlers import handle_ask, rag
    mocker.patch.object(rag, "ask", AsyncMock(return_value={
        "answer": "Индекс пуст",
        "sources": [],
        "retrieved": 0,
    }))
    msg = _make_message("/ask что такое Python")
    status = MagicMock()
    status.edit_text = AsyncMock()
    msg.answer = AsyncMock(return_value=status)
    await handle_ask(msg)
    status.edit_text.assert_called_once()


# ── Scenario 12: /benchmark Ollama unavailable ───────────────────────────────

async def test_scenario_benchmark_groq_only(mocker):
    from handlers.ollama_handlers import handle_benchmark
    msg = _make_message("/benchmark")
    status = MagicMock()
    status.edit_text = AsyncMock()
    msg.answer = AsyncMock(return_value=status)
    msg.answer_document = AsyncMock()

    mock_data = {
        "timestamp": "2025-01-01",
        "groq_model": "llama-3.1-8b-instant",
        "ollama_model": "N/A",
        "groq": {"stats": {"p50_latency": 0.5, "p95_latency": 0.9, "p99_latency": 1.0, "mean_tps": 100}, "results": []},
        "ollama": {"stats": {}, "results": []},
    }
    mocker.patch("services.benchmark_service.BenchmarkService.run", AsyncMock(return_value=mock_data))
    mocker.patch("services.benchmark_service.BenchmarkService.to_excel", return_value=b"xlsx_data")
    await handle_benchmark(msg)
    status.edit_text.assert_called()


# ── Scenario 13: /model list ─────────────────────────────────────────────────

async def test_scenario_model_list(mocker):
    from handlers.ollama_handlers import handle_model
    msg = _make_message("/model list")
    mocker.patch("handlers.ollama_handlers.ollama_service.is_available", AsyncMock(return_value=True))
    mocker.patch("handlers.ollama_handlers.ollama_service.list_models",
                 AsyncMock(return_value=["llama3.2:3b", "nomic-embed-text"]))
    await handle_model(msg)
    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "llama3.2" in text


# ── Scenario 14: tool call in text handler ────────────────────────────────────

async def test_scenario_text_triggers_tool_call(mocker):
    from handlers.messages import handle_text
    import json

    msg = _make_message("Какое сейчас время?")
    sent_msg = MagicMock()
    sent_msg.edit_text = AsyncMock()
    msg.answer = AsyncMock(return_value=sent_msg)

    mocker.patch("services.rate_limiter.RateLimiter.check_limits", AsyncMock(return_value=True))
    mocker.patch("services.summary_manager.SummaryManager.add_message", AsyncMock())
    mocker.patch("services.summary_manager.SummaryManager.get_history",
                 AsyncMock(return_value=[{"role": "user", "content": "time?"}]))
    mocker.patch("config.database.save_message", AsyncMock())

    # Stream yields tool_calls
    tool_calls_raw = {0: {"id": "tc1", "name": "get_current_time", "args": "{}"}}
    mocker.patch("services.llm_router.LLMRouter.stream_chat_completion",
                 return_value=_make_tool_stream(tool_calls_raw))
    mocker.patch("services.llm_router.LLMRouter.send_chat_completion",
                 AsyncMock(return_value=(_make_groq_response("Сейчас 12:00"), "model")))

    await handle_text(msg)
    sent_msg.edit_text.assert_called()


async def _make_tool_stream(tool_calls_raw):
    yield ("tool_calls", tool_calls_raw, "model")


# ── Scenario 15: context summarization triggers ───────────────────────────────

async def test_scenario_summary_manager_adds_messages():
    from services.summary_manager import SummaryManager
    sm = SummaryManager()
    await sm.add_message(999, "user", "Hello")
    history = await sm.get_history(999)
    assert any(m["role"] == "user" and m["content"] == "Hello" for m in history)
