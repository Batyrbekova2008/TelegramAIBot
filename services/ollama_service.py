"""
Ollama integration service (Tasks 13, 16, 17)

Task 13: /private — переключение на локальный Ollama (приватный режим)
Task 16: Function calling через Ollama (tool use для совместимых моделей)
Task 17: Динамическая загрузка моделей (/model pull <name>)

Ollama API: http://localhost:11434
Graceful degradation — если Ollama недоступна, возвращает понятную ошибку.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator

import httpx
from ollama import AsyncClient

OLLAMA_HOST = "http://localhost:11434"
DEFAULT_PRIVATE_MODEL = "llama3.2:3b"
PULL_UPDATE_INTERVAL = 5.0  # seconds between progress updates

log = logging.getLogger("ollama")


class OllamaService:
    def __init__(self, host: str = OLLAMA_HOST):
        self.host = host
        self.client = AsyncClient(host=host)

    # ── Connectivity ──────────────────────────────────────────────────────────

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as http:
                r = await http.get(f"{self.host}/api/tags")
                return r.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        try:
            response = await self.client.list()
            return [m.model for m in response.models]
        except Exception as e:
            log.warning("list_models failed: %s", e)
            return []

    # ── Task 13: Private mode chat ────────────────────────────────────────────

    async def chat(
        self,
        messages: list[dict],
        model: str = DEFAULT_PRIVATE_MODEL,
        stream: bool = False,
    ) -> AsyncGenerator[str, None] | str:
        if stream:
            return self._stream_chat(messages, model)
        try:
            response = await self.client.chat(
                model=model,
                messages=messages,
            )
            return response.message.content or ""
        except Exception as e:
            log.error("Ollama chat error: %s", e)
            raise

    async def _stream_chat(self, messages: list[dict], model: str) -> AsyncGenerator[str, None]:
        try:
            async for part in await self.client.chat(
                model=model,
                messages=messages,
                stream=True,
            ):
                chunk = part.message.content
                if chunk:
                    yield chunk
        except Exception as e:
            log.error("Ollama stream error: %s", e)
            yield f"\n[Ollama error: {e}]"

    # ── Task 16: Function calling ─────────────────────────────────────────────

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        model: str = "llama3.1:8b",
    ) -> dict:
        """
        Call Ollama model with tools. Returns dict with:
          - content: text response (may be empty if tool_calls present)
          - tool_calls: list of {name, arguments} dicts
          - model: model used
          - parse_errors: list of JSON parse errors encountered
        """
        try:
            response = await self.client.chat(
                model=model,
                messages=messages,
                tools=tools,
            )
            msg = response.message
            tool_calls = []
            parse_errors = []

            if msg.tool_calls:
                for tc in msg.tool_calls:
                    try:
                        args = tc.function.arguments
                        if isinstance(args, str):
                            args = json.loads(args)
                        tool_calls.append({
                            "name": tc.function.name,
                            "arguments": args,
                        })
                    except (json.JSONDecodeError, AttributeError) as e:
                        parse_errors.append(str(e))
                        log.warning("Tool call JSON parse error: %s | raw=%s", e, tc)

            return {
                "content": msg.content or "",
                "tool_calls": tool_calls,
                "model": model,
                "parse_errors": parse_errors,
            }
        except Exception as e:
            log.error("Ollama tool call error: %s", e)
            raise

    # ── Task 17: Dynamic model management ────────────────────────────────────

    async def pull_model(
        self,
        model_name: str,
        progress_callback=None,
    ) -> AsyncGenerator[dict, None]:
        """
        Pull a model, yielding progress dicts every PULL_UPDATE_INTERVAL seconds.
        progress_callback(status_text) is called with updates.
        """
        last_update = 0.0
        try:
            async for progress in self.client.pull(model_name, stream=True):
                import time
                now = time.monotonic()
                status = getattr(progress, "status", str(progress))
                completed = getattr(progress, "completed", None)
                total = getattr(progress, "total", None)

                pct = None
                if completed and total and total > 0:
                    pct = int(100 * completed / total)

                if now - last_update >= PULL_UPDATE_INTERVAL:
                    last_update = now
                    update = {"status": status, "percent": pct}
                    if progress_callback:
                        await progress_callback(update)
                    yield update

            yield {"status": "complete", "percent": 100}

        except Exception as e:
            error_msg = str(e)
            if "no space" in error_msg.lower() or "disk" in error_msg.lower():
                yield {"status": "error", "reason": "insufficient_disk", "detail": error_msg}
            elif "network" in error_msg.lower() or "connection" in error_msg.lower():
                yield {"status": "error", "reason": "network_error", "detail": error_msg}
            else:
                yield {"status": "error", "reason": "unknown", "detail": error_msg}

    async def delete_model(self, model_name: str) -> bool:
        try:
            await self.client.delete(model_name)
            return True
        except Exception as e:
            log.error("delete_model(%s) failed: %s", model_name, e)
            return False

    # ── Embeddings (used by RAG service) ─────────────────────────────────────

    async def embed(self, text: str, model: str = "nomic-embed-text") -> list[float]:
        response = await self.client.embeddings(model=model, prompt=text)
        return response.embedding


ollama_service = OllamaService()
