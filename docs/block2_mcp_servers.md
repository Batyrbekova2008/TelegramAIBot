# Блок 2: MCP-серверы (задачи 7–12)

## Что реализовано

| Задача | Описание | Файл |
|--------|----------|------|
| 7  | Клиент к `@modelcontextprotocol/server-filesystem`, команда `/files` | `services/mcp_client.py`, `handlers/mcp_handlers.py` |
| 8  | MCP-сервер для PostgreSQL (query_users, get_user_stats, export_to_csv) | `mcp_servers/postgres_server.py` |
| 9  | Роли (student / teacher / admin) через `MCP_ROLE` env, ошибка при нарушении | `mcp_servers/postgres_server.py` |
| 10 | Агрегатор 3 серверов (fs__, pg__, api__) с маршрутизацией | `services/mcp_aggregator.py`, `mcp_servers/custom_api_server.py` |
| 11 | Resources (шаблоны документов) и Prompts в postgres_server | `mcp_servers/postgres_server.py` |
| 12 | HTTP/SSE транспорт с Bearer-токен авторизацией | `mcp_servers/sse_server.py` |

---

## Новые зависимости Python

Добавлены в `requirements.txt`:

```
mcp>=1.0.0        # MCP Python SDK (клиент + сервер)
uvicorn>=0.20.0   # ASGI сервер для HTTP/SSE транспорта
starlette>=0.30.0 # HTTP middleware для Bearer-авторизации
```

Установка:
```bash
pip install -r requirements.txt
```

## Системные зависимости

- **Node.js 18+** + **npx** — нужны для запуска `@modelcontextprotocol/server-filesystem`  
  Проверка: `node --version && npx --version`  
  Скачать: https://nodejs.org/

---

## Переменные .env

Добавить в `.env` (или `.env.local`):

```dotenv
# MCP — роль пользователя для PostgreSQL сервера
# Значения: student | teacher | admin
MCP_PG_ROLE=teacher

# MCP SSE сервер (Task 12) — Bearer токен
MCP_BEARER_TOKEN=changeme

# Порт SSE сервера (по умолчанию 8001)
MCP_SSE_PORT=8001
```

---

## Команды бота

| Команда | Описание |
|---------|----------|
| `/files [path]` | Показать содержимое директории `data/` через MCP filesystem |
| `/mcp` | Список всех доступных инструментов от 3 серверов |
| `/mcp_call <tool> [json_args]` | Вызвать конкретный MCP инструмент |

Примеры:
```
/files
/mcp
/mcp_call pg__query_users {"limit": 5}
/mcp_call api__get_api_status
```

---

## Запуск MCP серверов вручную

### PostgreSQL сервер (stdio, Task 8/9/11)
```bash
MCP_ROLE=admin python mcp_servers/postgres_server.py
```

### HTTP/SSE сервер (Task 12)
```bash
MCP_BEARER_TOKEN=mysecret MCP_SSE_PORT=8001 python mcp_servers/sse_server.py
```

Проверка SSE авторизации:
```bash
# Без токена — 401
curl http://localhost:8001/sse

# С токеном — SSE stream
curl -H "Authorization: Bearer mysecret" http://localhost:8001/sse

# Healthcheck
curl http://localhost:8001/health
```

---

## Архитектура

```
Bot (aiogram)
  │
  ├── /files ──────────────────────► FilesystemMCPClient
  │                                       │
  │                                       └──stdio──► npx @modelcontextprotocol/server-filesystem
  │                                                        (serves data/ directory)
  │
  ├── /mcp, /mcp_call ─────────────► MCPAggregator
  │                                       │
  │                                       ├── fs__ ──stdio──► @modelcontextprotocol/server-filesystem
  │                                       ├── pg__ ──stdio──► mcp_servers/postgres_server.py
  │                                       └── api__ ─stdio──► mcp_servers/custom_api_server.py
  │
  └── (optional) SSE client ────────► mcp_servers/sse_server.py  (HTTP:8001)
```

### Роли (Task 9)

| Роль | query_users | get_user_stats | export_to_csv |
|------|:-----------:|:--------------:|:-------------:|
| student | ✅ | ❌ | ❌ |
| teacher | ✅ | ✅ | ❌ |
| admin   | ✅ | ✅ | ✅ |

Нарушение вызывает `PermissionError` (JSON-RPC -32603).

### Resources (Task 11)

| URI | Описание |
|-----|----------|
| `template://document/essay` | Шаблон эссе |
| `template://document/report` | Шаблон отчёта |
| `template://document/summary` | Шаблон конспекта |
| `db://users/list` | Список пользователей (live) |

### Prompts (Task 11)

| Имя | Аргументы | Описание |
|-----|-----------|----------|
| `analyze_code` | `code`, `language` | Анализ кода |
| `explain_topic` | `topic`, `level` | Объяснение темы |
| `summarize_dialog` | `dialog` | Суммаризация диалога |

---

## Тесты

```bash
pytest tests/test_mcp_servers.py -v
# 24 passed
```
