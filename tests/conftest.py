import os
import sys

# Ensure the TelegramAIBot root is importable from any working directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Provide fallback env vars so pydantic-settings doesn't fail when .env is absent
os.environ.setdefault("TELEGRAM_TOKEN", "0000000000:AAFakeTokenForTestingPurposesOnly")
os.environ.setdefault("GROQ_API_KEY", "gsk_fakekeyfakekey123456789fakekey")
os.environ.setdefault("GROQ_MODEL", "llama-3.1-8b-instant")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("DB_PASSWORD", "postgres")
os.environ.setdefault("DB_NAME", "chat-bot")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
