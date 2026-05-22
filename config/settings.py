from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, Field

class Settings(BaseSettings):
    # Telegram бот токені (.env файлынан оқылады)
    TELEGRAM_TOKEN: SecretStr

    # Groq API кілті мен қолданылатын модель
    GROQ_API_KEY: SecretStr
    GROQ_MODEL: str = "llama-3.1-8b-instant"

    # ТЗ бойынша лимиттер (Rate Limiting үшін)
    GROQ_MODEL_RPM: int = 30
    GROQ_MODEL_TPM: int = 40000

    # Redis баптаулары (fakeredis қолданылғандықтан дефолтты күйде қалады)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # .env файлдарын қолдау және валидация параметрлері
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Проект бойынша қолданылатын ортақ конфиг объектісі
config = Settings()