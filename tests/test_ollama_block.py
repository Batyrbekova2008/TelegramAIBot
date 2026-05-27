"""
Tests for Block 3: Ollama integration (Tasks 13-17)

Tests run without a real Ollama instance — OllamaService is mocked.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── OllamaService — is_available (Task 13) ────────────────────────────────────

async def test_is_available_returns_false_when_server_down(mocker):
    from services.ollama_service import OllamaService
    svc = OllamaService()
    mocker.patch("httpx.AsyncClient", side_effect=Exception("connection refused"))
    result = await svc.is_available()
    assert result is False


async def test_is_available_returns_true_when_server_up(mocker):
    from services.ollama_service import OllamaService
    svc = OllamaService()
    mock_resp = MagicMock(status_code=200)
    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)
    mock_http.get = AsyncMock(return_value=mock_resp)
    mocker.patch("httpx.AsyncClient", return_value=mock_http)
    result = await svc.is_available()
    assert result is True


# ── OllamaService — chat (Task 13) ────────────────────────────────────────────

async def test_chat_returns_string(mocker):
    from services.ollama_service import OllamaService
    svc = OllamaService()
    mock_msg = MagicMock()
    mock_msg.content = "Hello from Ollama"
    mock_resp = MagicMock()
    mock_resp.message = mock_msg
    mock_client = AsyncMock()
    mock_client.chat = AsyncMock(return_value=mock_resp)
    svc.client = mock_client

    result = await svc.chat(messages=[{"role": "user", "content": "hi"}])
    assert result == "Hello from Ollama"


async def test_chat_with_tools_parses_valid_tool_calls(mocker):
    from services.ollama_service import OllamaService
    svc = OllamaService()

    mock_tc = MagicMock()
    mock_tc.function.name = "get_weather"
    mock_tc.function.arguments = '{"city": "Almaty"}'

    mock_msg = MagicMock()
    mock_msg.content = ""
    mock_msg.tool_calls = [mock_tc]
    mock_resp = MagicMock()
    mock_resp.message = mock_msg
    mock_client = AsyncMock()
    mock_client.chat = AsyncMock(return_value=mock_resp)
    svc.client = mock_client

    result = await svc.chat_with_tools(
        messages=[{"role": "user", "content": "weather?"}],
        tools=[{"type": "function", "function": {"name": "get_weather"}}],
    )
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["name"] == "get_weather"
    assert result["tool_calls"][0]["arguments"]["city"] == "Almaty"
    assert result["parse_errors"] == []


async def test_chat_with_tools_records_parse_error(mocker):
    from services.ollama_service import OllamaService
    svc = OllamaService()

    mock_tc = MagicMock()
    mock_tc.function.name = "bad_tool"
    mock_tc.function.arguments = "INVALID_JSON{"

    mock_msg = MagicMock()
    mock_msg.content = ""
    mock_msg.tool_calls = [mock_tc]
    mock_resp = MagicMock()
    mock_resp.message = mock_msg
    mock_client = AsyncMock()
    mock_client.chat = AsyncMock(return_value=mock_resp)
    svc.client = mock_client

    result = await svc.chat_with_tools(
        messages=[{"role": "user", "content": "test"}],
        tools=[],
    )
    assert len(result["parse_errors"]) >= 1


# ── OllamaService — pull_model (Task 17) ─────────────────────────────────────

async def test_pull_model_yields_complete(mocker):
    from services.ollama_service import OllamaService
    svc = OllamaService()

    progress_items = [
        MagicMock(status="downloading", completed=50, total=100),
        MagicMock(status="complete", completed=100, total=100),
    ]

    # pull() is an async generator — returns iterable directly (no await)
    async def mock_pull(model_name, stream=True):
        for item in progress_items:
            yield item

    svc.client = MagicMock()
    svc.client.pull = mock_pull

    updates = []
    async for update in svc.pull_model("llama3.2:3b"):
        updates.append(update)

    statuses = [u["status"] for u in updates]
    assert "complete" in statuses


async def test_pull_model_handles_disk_error(mocker):
    from services.ollama_service import OllamaService
    svc = OllamaService()

    async def mock_pull(model_name, stream=True):
        raise Exception("no space left on device — disk full")
        yield  # make it a generator

    svc.client = MagicMock()
    svc.client.pull = mock_pull

    updates = []
    async for update in svc.pull_model("bigmodel"):
        updates.append(update)

    assert any(u.get("reason") == "insufficient_disk" for u in updates)


# ── VectorStore — cosine similarity (Task 14) ─────────────────────────────────

def test_vector_store_empty_search():
    from services.rag_service import VectorStore
    vs = VectorStore()
    results = vs.search([0.1, 0.2, 0.3])
    assert results == []


def test_vector_store_finds_similar_doc():
    from services.rag_service import VectorStore, Document
    vs = VectorStore()
    vs.add(Document("d1", "python programming", embedding=[1.0, 0.0, 0.0]))
    vs.add(Document("d2", "javascript web",     embedding=[0.0, 1.0, 0.0]))
    vs.add(Document("d3", "data science",       embedding=[0.0, 0.0, 1.0]))

    results = vs.search([1.0, 0.0, 0.0], top_k=1)
    assert len(results) == 1
    assert results[0][0].doc_id == "d1"
    assert results[0][1] > 0.9


def test_vector_store_top_k_limit():
    from services.rag_service import VectorStore, Document
    import numpy as np
    vs = VectorStore()
    for i in range(10):
        emb = np.random.rand(64).tolist()
        vs.add(Document(f"d{i}", f"doc {i}", embedding=emb))
    results = vs.search(np.random.rand(64).tolist(), top_k=3)
    assert len(results) == 3


def test_vector_store_serialize_deserialize():
    from services.rag_service import VectorStore, Document
    vs = VectorStore()
    vs.add(Document("d1", "hello", embedding=[0.1, 0.2]))
    serialized = vs.to_json()
    vs2 = VectorStore.from_json(serialized)
    assert len(vs2) == 1
    assert vs2._docs[0].doc_id == "d1"


# ── RAGService — add_document (Task 14) ──────────────────────────────────────

async def test_rag_add_document_when_ollama_unavailable(mocker):
    from services.rag_service import RAGService
    from services.ollama_service import OllamaService

    svc = OllamaService()
    mocker.patch.object(svc, "is_available", AsyncMock(return_value=False))
    rag = RAGService(ollama=svc)

    ok = await rag.add_document("test", "some content")
    assert ok is False
    assert len(rag.store) == 0


async def test_rag_add_document_indexes_when_available(mocker):
    from services.rag_service import RAGService
    from services.ollama_service import OllamaService

    svc = OllamaService()
    mocker.patch.object(svc, "is_available", AsyncMock(return_value=True))
    mocker.patch.object(svc, "embed", AsyncMock(return_value=[0.1, 0.2, 0.3]))
    rag = RAGService(ollama=svc)

    ok = await rag.add_document("doc1", "hello world", metadata={"source": "test"})
    assert ok is True
    assert len(rag.store) == 1


async def test_rag_ask_returns_no_results_when_empty(mocker):
    from services.rag_service import RAGService
    from services.ollama_service import OllamaService

    svc = OllamaService()
    mocker.patch.object(svc, "is_available", AsyncMock(return_value=True))
    mocker.patch.object(svc, "embed", AsyncMock(return_value=[0.0, 0.0, 0.0]))
    rag = RAGService(ollama=svc)

    result = await rag.ask("test question")
    assert result["retrieved"] == 0
    assert "sources" in result


# ── BenchmarkService (Task 15) ────────────────────────────────────────────────

async def test_benchmark_collects_groq_results(mocker):
    from services.benchmark_service import BenchmarkService
    from services.ollama_service import OllamaService
    from unittest.mock import MagicMock

    # Mock Groq client
    mock_groq = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Sample answer from Groq"
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_groq.chat = MagicMock()
    mock_groq.chat.completions = MagicMock()
    mock_groq.chat.completions.create = AsyncMock(return_value=mock_resp)

    # Mock Ollama unavailable
    svc = OllamaService()
    mocker.patch.object(svc, "is_available", AsyncMock(return_value=False))

    bench = BenchmarkService(groq_client=mock_groq, ollama=svc)
    questions = ["What is recursion?", "What is HTTP?"]
    data = await bench.run(questions=questions)

    assert len(data["groq"]["results"]) == 2
    assert data["groq"]["stats"]["count"] == 2
    assert data["groq"]["stats"]["errors"] == 0


def test_benchmark_to_excel_produces_valid_bytes(mocker):
    from services.benchmark_service import BenchmarkService
    from services.ollama_service import OllamaService
    import openpyxl
    from io import BytesIO

    svc = OllamaService()
    bench = BenchmarkService(groq_client=MagicMock(), ollama=svc)

    dummy_data = {
        "timestamp": "2025-01-01",
        "groq_model": "llama-3.1-8b-instant",
        "ollama_model": "N/A",
        "groq": {
            "stats": {"count": 2, "errors": 0, "p50_latency": 0.5,
                      "p95_latency": 0.9, "p99_latency": 1.0, "mean_tps": 120},
            "results": [
                {"question": "Q1", "latency": 0.5, "tokens": 50, "tps": 100, "error": False, "answer": "A1"},
                {"question": "Q2", "latency": 0.9, "tokens": 80, "tps": 89, "error": False, "answer": "A2"},
            ],
        },
        "ollama": {"stats": {}, "results": []},
    }
    excel_bytes = bench.to_excel(dummy_data)
    assert len(excel_bytes) > 100
    # Verify it's a valid Excel file
    wb = openpyxl.load_workbook(BytesIO(excel_bytes))
    assert "Summary" in wb.sheetnames
