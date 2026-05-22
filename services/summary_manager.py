import json
import tiktoken
from typing import List, Dict, Any
import fakeredis.aioredis as fake_aioredis
from config.settings import config
from groq import AsyncGroq

tokenizer = tiktoken.get_encoding("cl100k_base")
MAX_CONTEXT_TOKENS = 8000

class SummaryManager:
    def __init__(self):
        self.redis = fake_aioredis.FakeRedis(decode_responses=True)
        self.client = AsyncGroq(api_key=config.GROQ_API_KEY.get_secret_value())

    def _count_tokens(self, text: str) -> int:
        return len(tokenizer.encode(text))

    def _get_history_key(self, chat_id: int) -> str:
        return f"chat_history:{chat_id}"

    async def get_history(self, chat_id: int) -> List[Dict[str, Any]]:
        key = self._get_history_key(chat_id)
        raw_data = await self.redis.get(key)
        return json.loads(raw_data) if raw_data else []

    async def save_history(self, chat_id: int, history: List[Dict[str, Any]]):
        key = self._get_history_key(chat_id)
        await self.redis.set(key, json.dumps(history))

    async def add_message(self, chat_id: int, role: str, content: str):
        history = await self.get_history(chat_id)
        history.append({"role": role, "content": content})

        total_text = " ".join([m["content"] for m in history if isinstance(m.get("content"), str)])

        if self._count_tokens(total_text) > MAX_CONTEXT_TOKENS:
            history = await self._summarize_old_messages(history)

        await self.save_history(chat_id, history)  # ← БҰЛ ЖАҢА ҚОСЫЛҒАН ЖОЛЫ

    async def _summarize_old_messages(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        mid = len(history) // 2
        to_summarize = history[:mid]
        to_keep = history[mid:]

        text_to_summarize = "\n".join([f"{m['role']}: {m['content']}" for m in to_summarize])

        summary_response = await self.client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "Диалог мазмұнын қысқаша қорытындыла. Маңызды деректерді сақта."},
                {"role": "user", "content": text_to_summarize}
            ]
        )
        summary_text = summary_response.choices[0].message.content

        return [{"role": "system", "content": f"Алдыңғы диалогтың қысқаша мазмұны: {summary_text}"}] + to_keep

summary_manager = SummaryManager()