import logging
from groq import AsyncGroq
from config.settings import config

class LLMRouter:
    def __init__(self):
        self.client = AsyncGroq(api_key=config.GROQ_API_KEY.get_secret_value())
        self.default_model = config.GROQ_MODEL

    async def send_chat_completion(self, messages, tools=None, temperature=0.3):
        try:
            total_content_len = sum(len(str(m.get("content", ""))) for m in messages)
            
            active_model = self.default_model
            if total_content_len > 15000:
                active_model = "llama-3.3-70b-versatile"

            kwargs = {
                "model": active_model,
                "messages": messages,
                "temperature": temperature
            }

            # tools болса ғана қосамыз, tool_choice қоспаймыз
            if tools:
                kwargs["tools"] = tools

            response = await self.client.chat.completions.create(**kwargs)
            return response, active_model

        except Exception as e:
            logging.error(f"Groq API қатесі: {e}")
            raise e

llm_router = LLMRouter()