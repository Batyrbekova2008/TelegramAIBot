# Telegram AI Bot

Многофункциональный Telegram-бот с AI-ассистентом: Groq LLM, локальный Ollama, MCP-серверы, RAG-поиск, голосовые сообщения, анализ изображений и многое другое.

---

## Содержание

1. [Стек технологий](#стек-технологий)
2. [Требования](#требования)
3. [Быстрый старт](#быстрый-старт)
4. [Полная установка](#полная-установка)
5. [Переменные окружения](#переменные-окружения)
6. [Команды бота](#команды-бота)
7. [Запуск через Docker](#запуск-через-docker)
8. [Тесты](#тесты)
9. [Структура проекта](#структура-проекта)
10. [Дополнительные режимы запуска](#дополнительные-режимы-запуска)

---

## Стек технологий

| Слой | Технология |
|------|------------|
| Язык | Python 3.12+ |
| Telegram | aiogram 3.x |
| LLM (облако) | Groq API — llama-3.1-8b-instant / llama-3.3-70b-versatile |
| LLM (локально) | Ollama — llama3.2:3b, llama3.1:8b |
| STT | Groq Whisper (whisper-large-v3) |
| TTS | edge-tts (Microsoft Neural Voices) |
| Vision | llama-4-scout-17b-16e-instruct (Groq) |
| RAG | Ollama nomic-embed-text + numpy (cosine similarity) |
| MCP | mcp Python SDK 1.x (client + server) |
| Rate limiting | Token Bucket + fakeredis / Redis |
| История чата | fakeredis + tiktoken (авто-суммаризация при >8K токенов) |
| База данных | PostgreSQL + SQLAlchemy + pgvector |
| Конфигурация | pydantic-settings |
| Логирование | structlog (JSON) + OpenTelemetry → Jaeger |
| Поиск | Tavily API (с кешем в Redis) |
| CI/CD | GitHub Actions (lint → test → docker build → staging → prod) |

---

## Требования

### Обязательные

| Инструмент | Версия | Где взять |
|------------|--------|-----------|
| Python | 3.12+ | https://python.org |
| Node.js + npx | 18+ | https://nodejs.org |
| Telegram Bot Token | — | https://t.me/BotFather |
| Groq API Key | — | https://console.groq.com |

### Опциональные

| Инструмент | Нужен для |
|------------|-----------|
| PostgreSQL 16 | Сохранение истории сообщений |
| Redis | Реальный rate limiting (без него — fakeredis) |
| Ollama | Приватный режим, RAG, бенчмарк |
| Tavily API Key | Веб-поиск |
| Docker + Docker Compose | Запуск всего стека одной командой |

---

## Быстрый старт

```bash
# 1. Клонировать репозиторий
git clone <repo-url>
cd TelegramAIBot

# 2. Виртуальное окружение
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # Linux / macOS

# 3. Зависимости
pip install -r requirements.txt

# 4. Конфигурация
cp .env.example .env
# Откройте .env и заполните TELEGRAM_TOKEN и GROQ_API_KEY

# 5. Запуск
python main.py
```

Бот готов к работе. PostgreSQL и Redis не обязательны — без них бот работает с in-memory хранилищами.

---

## Полная установка

### Шаг 1 — Получить токены

**Telegram:**
1. Откройте @BotFather в Telegram
2. `/newbot` → введите имя и username
3. Скопируйте токен вида `1234567890:AAF...`

**Groq:**
1. Зарегистрируйтесь на https://console.groq.com
2. API Keys → Create new key
3. Скопируйте ключ вида `gsk_...`

### Шаг 2 — Установить зависимости

```bash
pip install -r requirements.txt
```

Убедитесь что Node.js установлен (нужен для MCP filesystem сервера):

```bash
node --version   # должно быть v18+
npx --version
```

### Шаг 3 — Настроить .env

```bash
cp .env.example .env
```

Минимальная конфигурация (только обязательные поля):

```dotenv
TELEGRAM_TOKEN=ваш_токен
GROQ_API_KEY=gsk_ваш_ключ
```

Остальные настройки — опциональны, бот работает без них.

### Шаг 4 — PostgreSQL (опционально)

Без PostgreSQL история сообщений не сохраняется между перезапусками.

```bash
# Установить PostgreSQL и создать базу:
createdb chat-bot

# Добавить в .env:
DB_USER=postgres
DB_PASSWORD=ваш_пароль
DB_HOST=localhost
DB_PORT=5432
DB_NAME=chat-bot
```

Таблицы создаются автоматически при первом запуске.

### Шаг 5 — Ollama (опционально)

Нужен для команд `/private`, `/ask`, `/rag_index`, `/benchmark`.

```bash
# Скачать и установить Ollama:
# https://ollama.ai/download

# Запустить сервер:
ollama serve

# Скачать модели (в отдельном терминале):
ollama pull llama3.2:3b          # основная модель (~2 GB)
ollama pull llama3.1:8b          # function calling (~5 GB)
ollama pull nomic-embed-text     # эмбеддинги для RAG (~274 MB)
```

### Шаг 6 — Запустить бота

```bash
python main.py
```

Вывод при успешном старте:

```
{"event": "bot_started", "level": "info", ...}
```

---

## Переменные окружения

Полный список в `.env.example`. Ключевые:

| Переменная | Обязательна | Описание |
|-----------|-------------|----------|
| `TELEGRAM_TOKEN` | ✅ | Токен бота от BotFather |
| `GROQ_API_KEY` | ✅ | Ключ Groq API |
| `GROQ_MODEL` | — | Модель по умолчанию (def: `llama-3.1-8b-instant`) |
| `DB_USER` / `DB_PASSWORD` / `DB_NAME` | — | PostgreSQL (без них — без сохранения) |
| `DB_HOST` / `DB_PORT` | — | Host/port PostgreSQL (def: localhost:5432) |
| `REDIS_HOST` / `REDIS_PORT` | — | Redis для rate limiting (def: fakeredis) |
| `TAVILY_API_KEY` | — | Веб-поиск. Ключ: https://app.tavily.com |
| `MCP_PG_ROLE` | — | Роль MCP postgres-сервера: `student`/`teacher`/`admin` (def: `teacher`) |
| `MCP_BEARER_TOKEN` | — | Токен для HTTP/SSE MCP сервера |
| `WEBHOOK_HOST` | — | HTTPS URL для webhook-режима (без него — polling) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | Jaeger endpoint (def: `http://localhost:4317`) |

---

## Команды бота

### Основные

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие |
| `/help` | Список команд |

Также поддерживается отправка **текста**, **голосовых сообщений** и **фотографий** без команд.

### MCP (Блок 2)

| Команда | Описание |
|---------|----------|
| `/files [путь]` | Показать содержимое директории `data/` через MCP filesystem |
| `/mcp` | Список всех инструментов от 3 MCP серверов |
| `/mcp_call <tool> [json]` | Вызвать конкретный MCP инструмент напрямую |

Примеры:
```
/files
/mcp
/mcp_call pg__query_users {"limit": 5}
/mcp_call api__get_api_status
/mcp_call fs__list_directory {"path": "/allowed/dir"}
```

### Ollama / RAG (Блок 3)

| Команда | Описание |
|---------|----------|
| `/private` | Переключить чат в приватный режим (Ollama) или обратно |
| `/ask <вопрос>` | RAG-поиск по файлам в `data/` + ответ с источниками |
| `/rag_index` | Проиндексировать файлы в `data/` (нужен Ollama) |
| `/benchmark` | Сравнить Groq vs Ollama на 20 вопросах, скачать Excel |
| `/model list` | Список установленных моделей Ollama |
| `/model pull <name>` | Скачать модель с показом прогресса |
| `/model delete <name>` | Удалить модель |

### Инструменты LLM (автоматически)

LLM сам вызывает нужные инструменты без явных команд:

| Инструмент | Триггер |
|-----------|---------|
| Время и дата | «который час», «какая дата» |
| Погода | «погода в Алматы», «weather in London» |
| Калькулятор | «посчитай 15% от 3400» |
| Системные ресурсы | «загрузка процессора», «сколько памяти» |
| Веб-поиск | «найди», «что нового», «последние новости» (нужен `TAVILY_API_KEY`) |

---

## Запуск через Docker

Запускает весь стек: бот + Redis + PostgreSQL + Ollama + Jaeger + Prometheus + Grafana.

```bash
# 1. Настроить окружение
cp .env.example .env
# Заполнить TELEGRAM_TOKEN и GROQ_API_KEY в .env

# 2. Поднять всё одной командой
docker compose up -d

# 3. Проверить статусы
docker compose ps

# 4. Логи бота
docker compose logs bot -f
```

После запуска доступны:

| Сервис | URL |
|--------|-----|
| Jaeger (трейсы) | http://localhost:16686 |
| Grafana (дашборды) | http://localhost:3000 (admin / пароль из `GRAFANA_PASSWORD`) |
| Prometheus (метрики) | http://localhost:9090 |
| Ollama API | http://localhost:11434 |
| MCP SSE сервер | http://localhost:8001/health |

Остановить:
```bash
docker compose down
# С удалением данных:
docker compose down -v
```

---

## Тесты

```bash
# Все тесты (быстрые)
pytest tests/ --ignore=tests/test_property_based.py -v

# Включая property-based (Hypothesis, ~30 сек)
pytest tests/ -v

# С покрытием
pytest tests/ --cov=services --cov=handlers --cov-report=term-missing

# Только конкретный блок
pytest tests/test_mcp_servers.py -v       # MCP (24 теста)
pytest tests/test_ollama_block.py -v      # Ollama (16 тестов)
pytest tests/test_e2e_scenarios.py -v     # E2E сценарии (16 тестов)
pytest tests/test_property_based.py -v   # Hypothesis (9 тестов)
```

Итого: **115 тестов, все зелёные**.

---

## Структура проекта

```
TelegramAIBot/
├── main.py                        # Точка входа (polling-режим)
├── webhook_server.py              # Альтернативный старт (webhook-режим)
│
├── config/
│   ├── settings.py                # Pydantic Settings (.env → типизированный объект)
│   └── database.py                # PostgreSQL + SQLAlchemy
│
├── handlers/
│   ├── messages.py                # /start, /help, текст, голос, фото
│   ├── mcp_handlers.py            # /files, /mcp, /mcp_call
│   └── ollama_handlers.py         # /private, /ask, /benchmark, /model
│
├── services/
│   ├── llm_router.py              # Выбор модели + fallback + streaming
│   ├── summary_manager.py         # История чата + авто-суммаризация
│   ├── rate_limiter.py            # Token Bucket (per-user / per-chat / global)
│   ├── tools.py                   # AI-инструменты (время, погода, calc, OS)
│   ├── tts_service.py             # Text-to-Speech (edge-tts, ru/kk/en)
│   ├── mcp_client.py              # Клиент к MCP filesystem серверу
│   ├── mcp_aggregator.py          # Агрегатор 3 MCP серверов
│   ├── ollama_service.py          # Ollama: chat, streaming, tools, pull
│   ├── rag_service.py             # RAG: embed → store → retrieve → answer
│   ├── benchmark_service.py       # Groq vs Ollama бенчмарк + Excel
│   ├── search_service.py          # Tavily веб-поиск + Redis кеш
│   └── llm_judge.py               # LLM-as-a-judge: оценка качества ответов
│
├── mcp_servers/
│   ├── postgres_server.py         # FastMCP: query_users, get_user_stats, export_to_csv
│   │                              #   + роли (student/teacher/admin)
│   │                              #   + resources (шаблоны)
│   │                              #   + prompts (analyze_code, explain_topic...)
│   ├── custom_api_server.py       # Вспомогательный API сервер для агрегатора
│   └── sse_server.py              # HTTP/SSE транспорт + Bearer авторизация
│
├── utils/
│   └── logging_setup.py           # structlog JSON + OpenTelemetry → Jaeger
│
├── tests/
│   ├── conftest.py                # Фиктивные переменные для тестов
│   ├── test_llm_router.py         # Тесты роутера (7 тестов)
│   ├── test_rate_limiter.py       # Тесты rate limiter (8 тестов)
│   ├── test_tools.py              # Тесты инструментов (15 тестов)
│   ├── test_tts_service.py        # Тесты TTS (9 тестов)
│   ├── test_mcp_servers.py        # MCP блок (24 теста)
│   ├── test_ollama_block.py       # Ollama блок (16 тестов)
│   ├── test_block4_integrations.py # Поиск + webhook (10 тестов)
│   ├── test_e2e_scenarios.py      # E2E сценарии (16 тестов)
│   └── test_property_based.py    # Hypothesis (9 тестов)
│
├── data/                          # Директория для MCP filesystem + RAG индекс
├── monitoring/
│   └── prometheus.yml             # Конфиг Prometheus
│
├── docs/                          # Документация по каждому блоку
│   ├── block2_mcp_servers.md
│   ├── block3_ollama.md
│   ├── block4_integrations.md
│   ├── block5_testing.md
│   └── block6_devops.md
│
├── .github/workflows/ci.yml       # CI/CD pipeline (6 этапов)
├── Dockerfile                     # Multi-stage, non-root user
├── docker-compose.yml             # 7 сервисов (bot + infra)
├── .dockerignore
├── .env.example                   # Шаблон конфигурации
├── requirements.txt
└── pytest.ini
```

---

## Дополнительные режимы запуска

### Webhook вместо polling

Нужен публичный HTTPS-адрес (ngrok для разработки, Let's Encrypt для production).

```bash
# Шаг 1: запустить ngrok
ngrok http 8443

# Шаг 2: добавить в .env
WEBHOOK_HOST=https://xxxx.ngrok.io
WEBHOOK_SECRET=any-secret-string

# Шаг 3: запустить webhook-сервер
python webhook_server.py
```

### MCP SSE сервер отдельно

```bash
MCP_BEARER_TOKEN=mysecret python mcp_servers/sse_server.py

# Проверка:
curl http://localhost:8001/health
curl -H "Authorization: Bearer mysecret" http://localhost:8001/sse
```

### PostgreSQL MCP сервер вручную

```bash
# Роль admin — доступны все 3 инструмента
MCP_ROLE=admin python mcp_servers/postgres_server.py

# Роль student — только query_users
MCP_ROLE=student python mcp_servers/postgres_server.py
```

### LLM-as-a-judge (оценка качества)

```python
from services.llm_judge import LLMJudge
from groq import AsyncGroq
import asyncio

judge = LLMJudge(AsyncGroq(api_key="gsk_..."))
report = asyncio.run(judge.evaluate())
print(f"Passed: {report.passed}, Score: {report.overall_mean}/10")
```

---

## Получить API ключи

| Сервис | URL | Тариф |
|--------|-----|-------|
| Groq | https://console.groq.com | Бесплатно (лимиты по RPM/TPM) |
| Tavily (поиск) | https://app.tavily.com | Бесплатно до 1000 запросов/мес |
| Telegram Bot | https://t.me/BotFather | Бесплатно |

---

## Ручное тестирование в Telegram

Откройте своего бота и проверьте каждый блок по шагам. Никакого кода — только руки и Telegram.

---

### Блок 0–1: Базовый бот

**Текстовый чат с AI:**
1. Напишите боту: `Привет, как дела?`
2. Бот должен ответить осмысленным текстом (не ошибкой).

**Инструменты LLM (вызываются автоматически):**
1. Напишите: `который час?` → бот должен ответить текущим временем
2. Напишите: `погода в Алматы` → бот ответит погодой (инструмент get_weather)
3. Напишите: `посчитай 15% от 3400` → бот выполнит вычисление
4. Напишите: `загрузка процессора` → бот покажет статистику системы

**Голосовые сообщения:**
1. Отправьте голосовое сообщение с любой фразой на русском
2. Бот должен расшифровать текст и ответить на него

**Фото / изображение:**
1. Отправьте любую фотографию
2. Бот должен описать что на ней изображено

**История чата:**
1. Напишите: `Меня зовут Алибек`
2. Затем: `Как меня зовут?`
3. Бот должен вспомнить имя (история хранится в сессии)

---

### Блок 2: MCP серверы

**Filesystem MCP:**
1. Напишите `/files`
2. Бот покажет содержимое папки `data/` через MCP filesystem сервер
3. Убедитесь что список файлов отображается, а не ошибка

**Список всех MCP инструментов:**
1. Напишите `/mcp`
2. Должен появиться список с инструментами с префиксами `fs__`, `pg__`, `api__`
3. Убедитесь что в списке есть минимум 5–6 инструментов

**Прямой вызов MCP инструмента:**
1. Напишите `/mcp_call api__get_api_status`
2. Бот должен вернуть JSON-ответ от кастомного API сервера
3. Попробуйте: `/mcp_call pg__query_users {"limit": 3}` — должен вернуть список пользователей (mock-данные)

---

### Блок 3: Ollama (нужен запущенный Ollama)

> Перед тестом убедитесь что `ollama serve` запущен и есть модель `llama3.2:3b`.

**Приватный режим (локальная LLM):**
1. Напишите `/private`
2. Бот ответит что приватный режим **включён**
3. Напишите любой текст — бот должен отвечать через Ollama, а не Groq
4. Напишите `/private` снова — режим выключится

**RAG — индексация и поиск:**
1. Создайте файл `data/test.txt` с любым текстом, например: `Казахстан — страна в Центральной Азии. Столица — Астана.`
2. Напишите `/rag_index` — бот проиндексирует файлы (займёт несколько секунд)
3. Напишите `/ask Какая столица Казахстана?`
4. Бот должен ответить **«Астана»** и указать источник: `test.txt`

**Управление моделями:**
1. Напишите `/model list`
2. Должен появиться список скачанных моделей Ollama

**Бенчмарк:**
1. Напишите `/benchmark`
2. Бот запустит 20 вопросов к Groq и Ollama (займёт 1–3 минуты)
3. В конце пришлёт файл `benchmark_results.xlsx` — скачайте и откройте

---

### Блок 4: Интеграции

**Веб-поиск (нужен `TAVILY_API_KEY` в .env):**
1. Напишите: `найди последние новости про ИИ`
2. Бот выполнит поиск через Tavily и ответит с актуальной информацией
3. Второй раз напишите то же самое — ответ должен появиться быстрее (Redis кеш)

**Проверка без Tavily:**
1. Если ключа нет — просто спросите что-то актуальное
2. Бот ответит из своих знаний без поиска (без ошибки)

---

### Блок 5: Качество ответов (LLM-as-a-Judge)

Это внутренняя проверка, но увидеть результат можно так:

1. В терминале (не в Telegram) запустите:
   ```bash
   python -c "
   import asyncio
   from groq import AsyncGroq
   from services.llm_judge import LLMJudge
   import os
   judge = LLMJudge(AsyncGroq(api_key=os.environ['GROQ_API_KEY']))
   report = asyncio.run(judge.evaluate())
   print(f'Passed: {report.passed}, Score: {report.overall_mean:.1f}/10')
   "
   ```
2. Должен вывести `Passed: True, Score: X.X/10` где X.X ≥ 7.0

---

### Блок 6: DevOps / Логирование

**Логи в JSON:**
1. Запустите бота и напишите ему любое сообщение
2. В терминале должны появляться строки вида:
   ```json
   {"event": "processing_message", "level": "info", "timestamp": "...", "request_id": "abc123"}
   ```

**Docker стек:**
1. Выполните `docker compose up -d`
2. Откройте http://localhost:16686 — Jaeger UI (трейсы запросов)
3. Откройте http://localhost:3000 — Grafana (логин: admin, пароль из `GRAFANA_PASSWORD`)
4. Напишите боту сообщение
5. В Jaeger найдите сервис `telegram-ai-bot` → должны появиться трейсы с вашим запросом

---

### Чеклист: всё работает

| Проверка | Команда / действие | Ожидаемый результат |
|----------|-------------------|---------------------|
| Базовый чат | Написать привет | Осмысленный ответ от AI |
| Инструменты | `который час?` | Текущее время |
| Голос | Отправить войс | Расшифровка + ответ |
| Фото | Отправить фото | Описание изображения |
| MCP список | `/mcp` | Список с префиксами fs__, pg__, api__ |
| MCP вызов | `/mcp_call api__get_api_status` | JSON-ответ |
| Приватный режим | `/private` | «Приватный режим включён» |
| RAG | `/rag_index` → `/ask ...` | Ответ с источником файла |
| Веб-поиск | `найди новости про ИИ` | Актуальный ответ с источниками |
| Бенчмарк | `/benchmark` | Excel-файл через 1–3 мин |
| Docker | `docker compose ps` | Все сервисы `healthy` |
