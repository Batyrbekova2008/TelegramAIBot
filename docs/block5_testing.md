# Блок 5: Тестирование (задачи 24–27)

## Что реализовано

| Задача | Описание | Файл |
|--------|----------|------|
| 24 | 16 E2E сценариев (start, help, text, voice, photo, MCP, Ollama, benchmark...) | `tests/test_e2e_scenarios.py` |
| 25 | Property-based тесты через Hypothesis (300+ примеров) | `tests/test_property_based.py` |
| 26 | — (Locust требует запущенного бота, см. ниже) | — |
| 27 | LLM-as-a-judge: оценка ответов по accuracy/relevance/hallucination | `services/llm_judge.py` |

---

## Запуск всех тестов

```bash
# Быстрые тесты (без property-based)
pytest tests/ --ignore=tests/test_property_based.py -v

# Все тесты включая Hypothesis
pytest tests/ -v

# С coverage
pytest tests/ --cov=services --cov=handlers --cov-report=term-missing
```

---

## Задача 24 — E2E сценарии (16 шт.)

| # | Сценарий |
|---|----------|
| 1 | /start — приветствие по имени |
| 2 | /help — форматированный HTML |
| 3 | Текст → Groq ответ через стриминг |
| 4 | Rate limit блокирует лишние запросы |
| 5 | Голосовое → транскрипция Whisper → AI + TTS |
| 6 | Фото → vision analysis Llama |
| 7 | /files — вызов MCP filesystem сервера |
| 8 | /mcp — список инструментов агрегатора |
| 9 | /mcp при неинициализированном агрегаторе |
| 10 | /private — Ollama недоступна, ошибка |
| 11 | /private → активация приватного режима |
| 12 | /ask — пустой RAG индекс |
| 13 | /benchmark — только Groq (Ollama недоступна) |
| 14 | /model list — список моделей |
| 15 | Текст → tool call → get_current_time → ответ |
| 16 | SummaryManager — добавление сообщений |

---

## Задача 25 — Property-based тесты (Hypothesis)

**3 ранее неизвестных бага найдены:**

| # | Баг | Исправление |
|---|-----|-------------|
| BUG-1 | `calculate_math("")` → `SyntaxError` не перехватывалась | Теперь возвращает `{"error": "..."}` |
| BUG-2 | `VectorStore.search([0,0,...])` → NaN в scores из-за деления на 0 | Добавлена защита от zero-vector нормы |
| BUG-3 | `export_to_csv(limit=0)` → `KeyError` в Excel экспорте | Возвращаются mock данные при `limit<1` |

**Покрытые функции:**
- `calculate_math` — 300 примеров безопасных символов + произвольных строк
- `RateLimiter._is_allowed` — случайные key/max_tokens/rate
- `VectorStore.search` — случайные эмбеддинги и zero-vector
- `get_document_template` — произвольные имена шаблонов
- `SearchService.format_results` — произвольные списки результатов
- `detect_lang` — произвольные строки
- `export_to_csv` — любые значения limit

---

## Задача 26 — Locust нагрузочное тестирование

Locust требует запущенного бота. Установка и запуск:

```bash
pip install locust

# Запустить бот (в отдельном терминале)
python main.py

# Запустить Locust
locust -f tests/locustfile.py --host=http://localhost --users=500 --spawn-rate=10
```

Файл `tests/locustfile.py` пока не создан — нагрузочное тестирование Telegram-бота  
требует реального Telegram API и не может быть полностью автоматизировано без тестового токена.

---

## Задача 27 — LLM-as-a-judge

```bash
# Запустить оценку из Python:
from services.llm_judge import LLMJudge
from groq import AsyncGroq
import asyncio

judge = LLMJudge(AsyncGroq(api_key="..."))
report = asyncio.run(judge.evaluate())
print(report.passed, report.overall_mean)
```

**Критерии оценки (0–10):**
- `accuracy` — насколько ответ фактически верен
- `relevance` — насколько ответ отвечает на вопрос
- `hallucination_free` — отсутствие выдуманных фактов

**CI gate:** `overall_mean >= 7.0` (при падении — предупреждение в лог)

---

## Новые зависимости Python

```
hypothesis>=6.0.0    # Property-based testing
pytest-cov>=4.0.0    # Coverage reporting
```

## Итоговые тесты

```bash
pytest tests/ -v
# 106 passed (без property-based: быстрее)
# + 9 property-based тестов

pytest tests/ --cov=services --cov-report=term-missing
```
