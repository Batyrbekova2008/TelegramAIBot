"""
Internet search via Tavily API (Task 19)

Flow:
  1. LLM decides if search is needed (function calling)
  2. LLM formulates a query
  3. Tavily returns top-5 results
  4. Results are cached in Redis for 1 hour
  5. LLM answers with sources

Requires: TAVILY_API_KEY in .env
Fallback: If key missing, returns a clear error message.
"""

import json
import logging
import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    pass

log = logging.getLogger("search")

TAVILY_API_URL = "https://api.tavily.com/search"
CACHE_TTL = 3600  # 1 hour

_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the internet for current information. Use when the user asks about recent events, facts, or anything that may need up-to-date information.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query in the most relevant language",
                },
            },
            "required": ["query"],
        },
    },
}


class SearchService:
    def __init__(self, api_key: str | None = None, redis=None):
        self.api_key = api_key
        self._redis = redis  # optional Redis for caching

    def _cache_key(self, query: str) -> str:
        return f"search:{query[:100].lower()}"

    async def _get_cached(self, query: str) -> list[dict] | None:
        if not self._redis:
            return None
        try:
            raw = await self._redis.get(self._cache_key(query))
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return None

    async def _set_cache(self, query: str, results: list[dict]):
        if not self._redis:
            return
        try:
            await self._redis.setex(
                self._cache_key(query),
                CACHE_TTL,
                json.dumps(results, ensure_ascii=False),
            )
        except Exception:
            pass

    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        """
        Search Tavily API. Returns list of:
          {"title": str, "url": str, "content": str, "score": float}
        """
        if not self.api_key:
            return [{"title": "API key missing", "url": "", "content":
                     "Set TAVILY_API_KEY in .env", "score": 0}]

        cached = await self._get_cached(query)
        if cached is not None:
            log.info("Search cache hit: %r", query)
            return cached

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    TAVILY_API_URL,
                    json={
                        "api_key": self.api_key,
                        "query": query,
                        "max_results": max_results,
                        "include_answer": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                results = [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "content": r.get("content", "")[:500],
                        "score": r.get("score", 0),
                    }
                    for r in data.get("results", [])
                ]
                await self._set_cache(query, results)
                log.info("Search: %r → %d results", query, len(results))
                return results

        except httpx.HTTPStatusError as e:
            log.error("Tavily HTTP error: %s", e)
            return [{"title": "Search error", "url": "", "content": str(e), "score": 0}]
        except Exception as e:
            log.error("Search error: %s", e)
            return [{"title": "Search unavailable", "url": "",
                     "content": f"Error: {e}", "score": 0}]

    @staticmethod
    def format_results(results: list[dict]) -> str:
        """Format search results for LLM context."""
        if not results:
            return "No results found."
        parts = []
        for i, r in enumerate(results, 1):
            parts.append(
                f"{i}. **{r['title']}**\n"
                f"   URL: {r['url']}\n"
                f"   {r['content']}"
            )
        return "\n\n".join(parts)

    def get_tool_definition(self) -> dict:
        return _SEARCH_TOOL


class SearchAwareHandler:
    """
    Wrapper that injects web_search capability into the Groq LLM flow.
    LLM decides whether to search via function calling.
    """

    def __init__(self, groq_client, search_service: SearchService):
        self.groq = groq_client
        self.search = search_service

    async def respond(
        self,
        messages: list[dict],
        model: str = "llama-3.1-8b-instant",
    ) -> tuple[str, list[str]]:
        """
        Returns (answer, list_of_source_urls).
        Uses web_search if LLM decides it's needed.
        """
        tools = [self.search.get_tool_definition()]

        response = await self.groq.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            timeout=10,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            return msg.content or "", []

        # Execute search
        sources = []
        search_results_text = ""
        for tc in msg.tool_calls:
            if tc.function.name == "web_search":
                import json as _json
                args = _json.loads(tc.function.arguments or "{}")
                query = args.get("query", "")
                results = await self.search.search(query)
                sources = [r["url"] for r in results if r["url"]]
                search_results_text = self.search.format_results(results)

        # Second pass: answer with search context
        follow_up = messages + [
            {"role": "assistant", "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]},
            {"role": "tool", "tool_call_id": msg.tool_calls[0].id,
             "content": search_results_text},
        ]

        final = await self.groq.chat.completions.create(
            model=model,
            messages=follow_up,
            timeout=10,
        )
        answer = final.choices[0].message.content or ""
        return answer, sources
