import logging
from groq import AsyncGroq
from config.settings import config
from typing import AsyncGenerator

# Ordered fallback chain: fast → capable → minimal
_MODEL_FALLBACK_CHAIN = [
    config.GROQ_MODEL,           # default (llama-3.1-8b-instant)
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",      # guaranteed last resort
]

class LLMRouter:
    def __init__(self):
        self.client = AsyncGroq(api_key=config.GROQ_API_KEY.get_secret_value())
        self.default_model = config.GROQ_MODEL

    async def send_chat_completion(self, messages, tools=None, temperature=0.3):
        total_content_len = sum(len(str(m.get("content", ""))) for m in messages)

        primary_model = self.default_model
        if total_content_len > 15000:
            primary_model = "llama-3.3-70b-versatile"

        # Build fallback list starting from primary, no duplicates
        candidates = [primary_model] + [m for m in _MODEL_FALLBACK_CHAIN if m != primary_model]

        kwargs_base = {"messages": messages, "temperature": temperature, "timeout": 10}
        if tools:
            kwargs_base["tools"] = tools

        last_exc = None
        for model in candidates:
            try:
                response = await self.client.chat.completions.create(
                    model=model, **kwargs_base
                )
                if model != primary_model:
                    logging.warning("Switched to fallback model %s (primary %s failed)", model, primary_model)
                return response, model
            except Exception as e:
                logging.error("Groq API error with model %s: %s", model, e)
                last_exc = e

        raise last_exc

    async def stream_chat_completion(
        self, messages, tools=None, temperature=0.3
    ) -> AsyncGenerator:
        """
        Async generator yielding tuples:
          ("text", chunk_str, model)        — incremental text delta
          ("tool_calls", raw_dict, model)   — assembled tool calls (no text emitted)
          ("done", full_text, model)        — stream finished normally

        Falls back to non-streaming send_chat_completion on any stream error.
        """
        total_content_len = sum(len(str(m.get("content", ""))) for m in messages)
        active_model = "llama-3.3-70b-versatile" if total_content_len > 15000 else self.default_model

        kwargs = {
            "model": active_model,
            "messages": messages,
            "temperature": temperature,
            "timeout": 10,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        try:
            stream = await self.client.chat.completions.create(**kwargs)
            content_parts: list[str] = []
            tool_calls_acc: dict = {}

            async for chunk in stream:
                choice = chunk.choices[0]
                delta = choice.delta

                if delta.content:
                    content_parts.append(delta.content)
                    yield ("text", delta.content, active_model)

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {"id": tc.id or "", "name": "", "args": ""}
                        if tc.function:
                            if tc.function.name:
                                tool_calls_acc[idx]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_calls_acc[idx]["args"] += tc.function.arguments

            if tool_calls_acc:
                yield ("tool_calls", tool_calls_acc, active_model)
            else:
                yield ("done", "".join(content_parts), active_model)

        except Exception as e:
            logging.warning("Streaming failed (%s), falling back: %s", active_model, e)
            response, model = await self.send_chat_completion(messages, tools, temperature)
            msg = response.choices[0].message
            if msg.content:
                yield ("text", msg.content, model)
                yield ("done", msg.content, model)
            elif msg.tool_calls:
                raw = {
                    i: {"id": tc.id, "name": tc.function.name, "args": tc.function.arguments or "{}"}
                    for i, tc in enumerate(msg.tool_calls)
                }
                yield ("tool_calls", raw, model)

llm_router = LLMRouter()