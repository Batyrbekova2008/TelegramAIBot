# Блок 3: Ollama интеграция (задачи 13–17)

## Что реализовано

| Задача | Описание | Файл |
|--------|----------|------|
| 13 | `/private` — переключение на локальный Ollama, визуальный индикатор | `handlers/ollama_handlers.py` |
| 14 | RAG-пайплайн: эмбеддинги Ollama, in-memory векторный store, `/ask` | `services/rag_service.py` |
| 15 | `/benchmark` — 20 вопросов на Groq + Ollama, p50/p95/p99, Excel-отчёт | `services/benchmark_service.py` |
| 16 | Function calling через Ollama (llama3.1:8b), лог parse errors | `services/ollama_service.py` |
| 17 | `/model pull/list/delete` — динамическая загрузка + обработка ошибок | `handlers/ollama_handlers.py` |

---

## Установка Ollama

> **Без Ollama бот продолжает работать** — все команды возвращают понятное сообщение об ошибке.

1. Скачайте Ollama: https://ollama.ai/download
2. Запустите сервер:
   ```bash
   ollama serve
   ```
3. Скачайте модели:
   ```bash
   ollama pull llama3.2:3b          # легкая (2.0 GB)
   ollama pull llama3.1:8b          # function calling (4.7 GB)
   ollama pull nomic-embed-text     # эмбеддинги для RAG (274 MB)
   ```

---

## Новые зависимости Python

```
ollama>=0.3.0     # Ollama Python SDK
numpy>=1.26.0     # Векторные вычисления для RAG (cosine similarity)
openpyxl>=3.1.0   # Экспорт benchmark в Excel
```

## Переменные .env

Дополнительных переменных не требуется. Ollama ищется на `http://localhost:11434`.  
Если Ollama запущена на другом хосте, можно переопределить (в коде):
```python
from services.ollama_service import OllamaService
svc = OllamaService(host="http://remote-host:11434")
```

---

## Команды бота

| Команда | Описание |
|---------|----------|
| `/private` | Переключить чат в приватный (Ollama) режим или обратно |
| `/ask <вопрос>` | RAG-поиск по `data/` + ответ Groq с контекстом |
| `/rag_index` | Проиндексировать файлы в `data/` (требует Ollama) |
| `/benchmark` | Запустить 20 вопросов на Groq и Ollama, скачать Excel |
| `/model list` | Список установленных моделей Ollama |
| `/model pull <name>` | Скачать модель (обновление каждые 5 сек) |
| `/model delete <name>` | Удалить модель |

---

## Архитектура RAG (задача 14)

```
/ask "что такое рекурсия?"
   │
   ├─► OllamaService.embed(question)           # nomic-embed-text → float[768]
   │
   ├─► VectorStore.search(embedding, top_k=5)  # cosine similarity (numpy)
   │       └── Returns: [(doc, score), ...]
   │
   └─► Groq llama-3.1-8b-instant               # финальный ответ с контекстом
           prompt = "Контекст:\n{top5_docs}\n\nВопрос: ..."
```

Индекс сохраняется в `data/rag_index.json` и восстанавливается при рестарте бота.

---

## Benchmark (задача 15)

Метрики:
- **Latency**: p50, p95, p99 (в секундах)
- **Tokens/sec**: среднее значение по 20 вопросам
- **Errors**: количество неуспешных запросов

Excel-отчёт содержит:
- Лист **Summary** — сравнение Groq vs Ollama
- Лист **Groq Results** — детальные результаты по каждому вопросу
- Лист **Ollama Results** — то же для Ollama

---

## Функции (задача 16)

Function calling в Ollama работает для моделей с поддержкой tools:
- `llama3.1:8b` — официальная поддержка tools
- `qwen2.5:7b` — альтернатива

Parse errors (когда модель генерирует некорректный JSON для аргументов) логируются в `bot.log`.

---

## Тесты

```bash
pytest tests/test_ollama_block.py -v
# 16 passed
```
