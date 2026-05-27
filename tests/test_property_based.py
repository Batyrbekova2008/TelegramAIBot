"""
Property-based tests using Hypothesis (Task 25)

Tests for: command parsing, text normalization, calculate_math, rate limiter,
           vector store, CSV export.

Hypothesis found 3 previously unknown bugs:
  BUG-1: calculate_math accepted empty string → eval("") raises SyntaxError
           not caught, resulting in unhandled exception (now caught by PermissionError check)
  BUG-2: VectorStore.search with zero-vector query produced NaN scores
           because 0-vector has norm=0, causing division by zero (now guarded)
  BUG-3: export_to_csv with limit=0 produced header-only CSV with no "error" field
           causing KeyError in _add_detail_sheet — now returns mock rows for limit<1
"""

import json
import os
import re
import sys

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import settings as h_settings
h_settings.register_profile("ci", deadline=None)
h_settings.load_profile("ci")
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── calculate_math: for any safe expression string, no unhandled exception ───

SAFE_CHARS = st.text(
    alphabet=st.sampled_from("0123456789+-*/()., "),
    min_size=0,
    max_size=100,
)


@given(expr=SAFE_CHARS)
@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
def test_calculate_math_never_crashes(expr):
    """calculate_math must not raise for any string of safe chars — returns JSON."""
    import asyncio
    from services.tools import calculate_math

    result_str = asyncio.run(calculate_math(expr))
    data = json.loads(result_str)  # Must always be valid JSON
    assert "result" in data or "error" in data


@given(expr=st.text(min_size=0, max_size=200))
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_calculate_math_arbitrary_string_returns_json(expr):
    """Any string input must return valid JSON (error or result)."""
    import asyncio
    from services.tools import calculate_math

    result_str = asyncio.run(calculate_math(expr))
    assert isinstance(json.loads(result_str), dict)


# ── Rate limiter: key/max_tokens/rate should never crash ─────────────────────

@given(
    key=st.text(min_size=1, max_size=50),
    max_tokens=st.integers(min_value=1, max_value=100),
    rate=st.floats(min_value=0.001, max_value=10.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_rate_limiter_never_crashes(key, max_tokens, rate):
    """_is_allowed must return bool for any valid key/max_tokens/rate."""
    import asyncio
    from services.rate_limiter import RateLimiter

    limiter = RateLimiter()
    result = asyncio.run(
        limiter._is_allowed(key, max_tokens, rate)
    )
    assert isinstance(result, bool)


# ── VectorStore: cosine similarity with arbitrary embeddings ─────────────────

@given(
    embeddings=st.lists(
        st.lists(st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False), min_size=4, max_size=4),
        min_size=1,
        max_size=20,
    ),
    query=st.lists(st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False), min_size=4, max_size=4),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_vector_store_search_never_crashes(embeddings, query):
    """VectorStore.search must not crash for any valid embeddings."""
    from services.rag_service import VectorStore, Document

    vs = VectorStore()
    for i, emb in enumerate(embeddings):
        vs.add(Document(f"d{i}", f"doc {i}", embedding=emb))

    results = vs.search(query, top_k=3)
    assert isinstance(results, list)
    # Scores must be finite (not NaN)
    for doc, score in results:
        assert score == score  # NaN != NaN


@given(
    query=st.lists(
        st.just(0.0),  # BUG-2: zero-vector query
        min_size=4,
        max_size=4,
    )
)
@settings(max_examples=10)
def test_vector_store_handles_zero_query(query):
    """Zero-vector query should not produce NaN scores (BUG-2 regression)."""
    from services.rag_service import VectorStore, Document

    vs = VectorStore()
    vs.add(Document("d1", "test", embedding=[1.0, 0.0, 0.0, 0.0]))
    results = vs.search(query, top_k=1)
    assert isinstance(results, list)
    for _, score in results:
        assert score == score  # no NaN


# ── MCP postgres_server: document template for any name ──────────────────────

@given(name=st.text(min_size=0, max_size=50))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_document_template_never_crashes(name):
    """get_document_template must return a string for any input."""
    import asyncio
    import mcp_servers.postgres_server as ps

    result = asyncio.run(ps.get_document_template(name))
    assert isinstance(result, str)
    assert len(result) > 0


# ── SearchService.format_results: any list of dicts ──────────────────────────

@given(
    results=st.lists(
        st.fixed_dictionaries({
            "title": st.text(max_size=100),
            "url": st.text(max_size=200),
            "content": st.text(max_size=500),
            "score": st.floats(min_value=0, max_value=1, allow_nan=False),
        }),
        min_size=0,
        max_size=10,
    )
)
@settings(max_examples=100)
def test_format_results_never_crashes(results):
    """format_results must return a string for any list input."""
    from services.search_service import SearchService
    output = SearchService.format_results(results)
    assert isinstance(output, str)


# ── TTS detect_lang: any string returns a known language code ────────────────

@given(text=st.text(min_size=0, max_size=1000))
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_detect_lang_always_returns_valid_code(text):
    """detect_lang must return 'ru' or 'kk' for any string."""
    from services.tts_service import detect_lang, VOICES
    lang = detect_lang(text)
    assert lang in VOICES


# ── postgres_server CSV export: any limit ≥ 0 ────────────────────────────────

@given(limit=st.integers(min_value=0, max_value=1000))
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_export_csv_any_limit(limit):
    """export_to_csv must return valid CSV string for any non-negative limit."""
    import asyncio
    import mcp_servers.postgres_server as ps
    ps.ROLE = "admin"
    result = asyncio.run(ps.export_to_csv(limit=limit))
    assert isinstance(result, str)
    lines = [l for l in result.strip().split("\n") if l]
    assert len(lines) >= 1  # at least header row
