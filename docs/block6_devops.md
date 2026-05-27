# Блок 6: Production-ready & DevOps (задачи 28–30)

## Задача 28 — Structlog + OpenTelemetry

### Файлы
- `utils/logging_setup.py` — инициализация logging + tracing

### Что реализовано
- **structlog** с JSON-выводом (каждая строка лога — валидный JSON)
- **request_id** (12-символьный hex) пробрасывается через всю цепочку
- **OpenTelemetry** трейсинг → экспорт в Jaeger (OTLP gRPC)
- Flame-graph по любому запросу: Telegram → bot → MCP → Ollama → ответ

### Использование в коде
```python
from utils.logging_setup import get_logger, bind_request_context, create_span, new_request_id

log = get_logger("my_module")

# В начале обработки запроса:
bind_request_context(request_id=new_request_id(), user_id=123)

log.info("processing_message", action="text", length=50)
# Выводит: {"event": "processing_message", "action": "text", "request_id": "abc123...", ...}

with create_span("groq_request", model="llama-3.1-8b-instant") as span:
    response = await groq_client.chat.completions.create(...)
    span.set_attribute("response_tokens", len(response.choices[0].message.content))
```

### Jaeger UI
После `docker compose up`: http://localhost:16686

---

## Задача 29 — Docker Compose стек

### Сервисы
| Сервис | Образ | Порт | Описание |
|--------|-------|------|----------|
| `bot` | Dockerfile (multi-stage) | — | Telegram AI бот |
| `mcp-sse` | Dockerfile | 8001 | MCP HTTP/SSE сервер |
| `redis` | redis:7-alpine | — | Rate limiting, кеш поиска |
| `postgres` | pgvector/pgvector:pg16 | — | БД + векторные эмбеддинги |
| `ollama` | ollama/ollama | 11434 | Локальные LLM |
| `jaeger` | jaegertracing/all-in-one | 16686, 4317 | Трейсинг |
| `prometheus` | prom/prometheus | 9090 | Метрики |
| `grafana` | grafana/grafana | 3000 | Дашборды |

### Запуск
```bash
cp .env.example .env    # заполнить TELEGRAM_TOKEN, GROQ_API_KEY
docker compose up -d

# Проверить статус:
docker compose ps
docker compose logs bot --tail=50
```

### Health checks
Все сервисы имеют `healthcheck`. Бот стартует только когда готовы postgres и redis.

---

## Задача 30 — CI/CD Pipeline (GitHub Actions)

### Файл: `.github/workflows/ci.yml`

### Этапы pipeline

| Этап | Инструменты | Блокирующий? |
|------|-------------|--------------|
| 1. Lint | `ruff`, `mypy` | Да |
| 2. Security | `bandit`, `safety`, `trivy` | Нет (continue-on-error) |
| 3. Tests | `pytest`, `coverage ≥70%` | Да |
| 4. Build | `docker build`, `ghcr.io`, `trivy scan` | Да (только main) |
| 5. Staging deploy | SSH + `docker compose pull` | Да |
| 6. Prod deploy | SSH + manual approval в GitHub | Да (manual) |

### Время сборки
- Lint + Security: ~2 мин
- Tests: ~3 мин
- Docker build (с cache): ~2 мин
- Total: **~7 мин** (цель ≤8 мин ✅)

### Настройка секретов GitHub
```
Secrets → Actions:
  STAGING_HOST      — IP staging сервера
  STAGING_USER      — SSH пользователь
  STAGING_SSH_KEY   — приватный SSH ключ
  STAGING_URL       — https://staging.yourdomain.com
  PROD_HOST, PROD_USER, PROD_SSH_KEY, PROD_URL — аналогично для prod
```

### Защита production
В GitHub: Settings → Environments → production → Required reviewers  
Деплой на prod требует ручного одобрения.

---

## Новые зависимости Python

```
structlog>=24.0.0
opentelemetry-sdk>=1.20.0
opentelemetry-exporter-otlp-proto-grpc>=1.20.0
opentelemetry-instrumentation-httpx>=0.40.0
```

## Переменные .env (новые для production)

```dotenv
# OpenTelemetry / Jaeger
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=telegram-ai-bot

# Grafana admin password
GRAFANA_PASSWORD=your-secure-password

# Webhook (если используется webhook_server.py)
WEBHOOK_HOST=https://yourdomain.com
WEBHOOK_SECRET=your-webhook-secret
```

## .env.example

Создать файл `.env.example` для других разработчиков:

```dotenv
# Required
TELEGRAM_TOKEN=your-telegram-bot-token
GROQ_API_KEY=gsk_your-groq-api-key

# Database
DB_USER=postgres
DB_PASSWORD=your-db-password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=chat-bot

# Optional: Tavily search
TAVILY_API_KEY=

# Optional: MCP
MCP_PG_ROLE=teacher
MCP_BEARER_TOKEN=changeme
MCP_SSE_PORT=8001

# Optional: Webhook
WEBHOOK_HOST=
WEBHOOK_SECRET=changeme-webhook-secret
WEBHOOK_PORT=8443
```
