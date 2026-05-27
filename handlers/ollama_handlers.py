"""
Ollama-related bot handlers (Tasks 13-17)

Commands:
  /private        — toggle private (Ollama) mode (Task 13)
  /ask <question> — RAG search + LLM answer (Task 14)
  /benchmark      — Groq vs Ollama benchmark, exports Excel (Task 15)
  /model list     — list installed Ollama models (Task 17)
  /model pull <n> — pull a model with live progress (Task 17)
  /model delete <n>— remove a model (Task 17)

Function calling via Ollama is exercised internally in handle_private_text.
"""

import asyncio
import logging
import time
from io import BytesIO

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile
from groq import AsyncGroq

from config.settings import config
from services.ollama_service import OllamaService, ollama_service
from services.rag_service import RAGService

router = Router()
log = logging.getLogger("bot.ollama")

# ── Per-chat private mode state ───────────────────────────────────────────────
_private_chats: set[int] = set()

groq_client = AsyncGroq(api_key=config.GROQ_API_KEY.get_secret_value())
rag = RAGService(ollama=ollama_service, embed_model="nomic-embed-text")
rag.load_index()  # load persisted index if exists

# ── /private ─────────────────────────────────────────────────────────────────

@router.message(Command("private"))
async def handle_private_toggle(message: types.Message):
    """Toggle private (Ollama) mode for this chat."""
    chat_id = message.chat.id
    available = await ollama_service.is_available()

    if chat_id in _private_chats:
        _private_chats.discard(chat_id)
        await message.answer(
            "☁️ <b>Облачный режим</b> активирован.\n"
            "Сообщения обрабатываются через Groq API.",
            parse_mode="HTML",
        )
    else:
        if not available:
            await message.answer(
                "❌ <b>Ollama недоступна</b>\n"
                "Установите Ollama: <code>https://ollama.ai</code>\n"
                "Затем запустите: <code>ollama run llama3.2:3b</code>",
                parse_mode="HTML",
            )
            return
        models = await ollama_service.list_models()
        _private_chats.add(chat_id)
        await message.answer(
            "🔒 <b>Приватный режим</b> активирован.\n"
            "Сообщения обрабатываются <b>локально</b> через Ollama.\n"
            f"Доступные модели: {', '.join(models) or 'нет'}",
            parse_mode="HTML",
        )

# ── /ask <question> — RAG ─────────────────────────────────────────────────────

@router.message(Command("ask"))
async def handle_ask(message: types.Message):
    question = (message.text or "").replace("/ask", "", 1).strip()
    if not question:
        await message.answer("Использование: <code>/ask ваш вопрос</code>", parse_mode="HTML")
        return

    status = await message.answer("🔍 Ищу в базе знаний...")
    result = await rag.ask(question, groq_client=groq_client)

    sources_text = ""
    if result["sources"]:
        sources_text = "\n\n📚 <b>Источники:</b> " + ", ".join(f"<code>{s}</code>" for s in result["sources"])

    await status.edit_text(
        f"❓ <b>{question}</b>\n\n{result['answer']}{sources_text}",
        parse_mode="HTML",
    )


@router.message(Command("rag_index"))
async def handle_rag_index(message: types.Message):
    """Index the data/ directory."""
    available = await ollama_service.is_available()
    if not available:
        await message.answer("❌ Ollama недоступна для генерации эмбеддингов.")
        return
    status = await message.answer("📚 Индексирую data/ ...")
    from pathlib import Path
    data_dir = Path(__file__).parent.parent / "data"
    count = await rag.index_directory(data_dir)
    rag.save_index()
    await status.edit_text(f"✅ Проиндексировано {count} документов в data/")

# ── /benchmark ────────────────────────────────────────────────────────────────

@router.message(Command("benchmark"))
async def handle_benchmark(message: types.Message):
    status = await message.answer("⏱️ Запускаю бенчмарк (20 вопросов)...\nЭто займёт ~2 минуты.")

    from services.benchmark_service import BenchmarkService, BENCHMARK_QUESTIONS
    bench = BenchmarkService(groq_client=groq_client, ollama=ollama_service)

    question_count = [0]

    async def progress(i, total, question):
        question_count[0] = i
        if i % 5 == 0 or i == total:
            try:
                await status.edit_text(
                    f"⏱️ Бенчмарк: {i}/{total} вопросов...",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    try:
        data = await bench.run(progress_callback=progress)
        excel_bytes = bench.to_excel(data)

        groq_s = data["groq"]["stats"]
        ollama_s = data["ollama"]["stats"]
        ollama_available = bool(ollama_s.get("count", 0))

        summary = (
            f"📊 <b>Benchmark Results</b>\n\n"
            f"<b>Groq ({data['groq_model']}):</b>\n"
            f"  p50: {groq_s['p50_latency']}s | p95: {groq_s['p95_latency']}s | "
            f"p99: {groq_s['p99_latency']}s\n"
            f"  Avg tokens/sec: {groq_s['mean_tps']}\n\n"
        )
        if ollama_available:
            summary += (
                f"<b>Ollama ({data['ollama_model']}):</b>\n"
                f"  p50: {ollama_s['p50_latency']}s | p95: {ollama_s['p95_latency']}s | "
                f"p99: {ollama_s['p99_latency']}s\n"
                f"  Avg tokens/sec: {ollama_s['mean_tps']}\n"
            )
        else:
            summary += "ℹ️ Ollama недоступна — сравнение не проводилось.\n"

        await status.edit_text(summary, parse_mode="HTML")

        file = BufferedInputFile(excel_bytes, filename="benchmark_results.xlsx")
        await message.answer_document(file, caption="📎 Детальный отчёт в Excel")

    except Exception as e:
        log.error("Benchmark error: %s", e)
        await status.edit_text(f"❌ Ошибка бенчмарка: <code>{e}</code>", parse_mode="HTML")

# ── /model list / pull / delete ───────────────────────────────────────────────

@router.message(Command("model"))
async def handle_model(message: types.Message):
    parts = (message.text or "").split(None, 2)
    if len(parts) < 2:
        await message.answer(
            "📦 <b>Управление моделями Ollama:</b>\n"
            "/model list — список установленных моделей\n"
            "/model pull &lt;name&gt; — скачать модель\n"
            "/model delete &lt;name&gt; — удалить модель",
            parse_mode="HTML",
        )
        return

    subcmd = parts[1].lower()

    if subcmd == "list":
        available = await ollama_service.is_available()
        if not available:
            await message.answer("❌ Ollama недоступна.")
            return
        models = await ollama_service.list_models()
        if models:
            await message.answer(
                "📦 <b>Установленные модели:</b>\n" + "\n".join(f"• <code>{m}</code>" for m in models),
                parse_mode="HTML",
            )
        else:
            await message.answer("📭 Нет установленных моделей Ollama.")

    elif subcmd == "pull":
        if len(parts) < 3:
            await message.answer("Использование: <code>/model pull llama3.2:3b</code>", parse_mode="HTML")
            return
        model_name = parts[2].strip()
        await _pull_model(message, model_name)

    elif subcmd == "delete":
        if len(parts) < 3:
            await message.answer("Использование: <code>/model delete llama3.2:3b</code>", parse_mode="HTML")
            return
        model_name = parts[2].strip()
        ok = await ollama_service.delete_model(model_name)
        if ok:
            await message.answer(f"🗑️ Модель <code>{model_name}</code> удалена.", parse_mode="HTML")
        else:
            await message.answer(f"❌ Не удалось удалить <code>{model_name}</code>.", parse_mode="HTML")

    else:
        await message.answer("Неизвестная команда. Доступно: list, pull, delete")


async def _pull_model(message: types.Message, model_name: str):
    available = await ollama_service.is_available()
    if not available:
        await message.answer("❌ Ollama недоступна. Запустите: <code>ollama serve</code>", parse_mode="HTML")
        return

    status = await message.answer(f"⬇️ Загружаю <code>{model_name}</code>...", parse_mode="HTML")
    last_edit = time.monotonic()

    async def on_progress(update: dict):
        nonlocal last_edit
        now = time.monotonic()
        if now - last_edit < 5.0:
            return
        last_edit = now
        pct = update.get("percent")
        stat = update.get("status", "")
        text = f"⬇️ <b>{model_name}</b>: {stat}"
        if pct is not None:
            text += f" ({pct}%)"
        try:
            await status.edit_text(text, parse_mode="HTML")
        except Exception:
            pass

    try:
        async for update in ollama_service.pull_model(model_name, progress_callback=on_progress):
            if update.get("status") == "complete":
                await status.edit_text(
                    f"✅ Модель <code>{model_name}</code> загружена!\n"
                    "Используйте /private для переключения в приватный режим.",
                    parse_mode="HTML",
                )
                return
            elif update.get("status") == "error":
                reason = update.get("reason", "unknown")
                detail = update.get("detail", "")
                if reason == "insufficient_disk":
                    msg = f"❌ Недостаточно места на диске для <code>{model_name}</code>"
                elif reason == "network_error":
                    msg = f"❌ Ошибка сети при загрузке <code>{model_name}</code>"
                else:
                    msg = f"❌ Ошибка загрузки: <code>{detail[:200]}</code>"
                await status.edit_text(msg, parse_mode="HTML")
                return
    except asyncio.CancelledError:
        await status.edit_text(f"⚠️ Загрузка <code>{model_name}</code> отменена.", parse_mode="HTML")
    except Exception as e:
        log.error("pull_model error: %s", e)
        await status.edit_text(f"❌ Ошибка: <code>{e}</code>", parse_mode="HTML")


# ── Private mode text handler ─────────────────────────────────────────────────
# NOTE: This router must be included BEFORE messages_router in main.py
# so that private-mode messages are intercepted here.

@router.message(F.text & F.func(lambda m: m.chat.id in _private_chats))
async def handle_private_text(message: types.Message):
    """Handle text messages in private (Ollama) mode (Tasks 13, 16)."""
    chat_id = message.chat.id
    available = await ollama_service.is_available()

    if not available:
        _private_chats.discard(chat_id)
        await message.answer(
            "⚠️ Ollama недоступна. Переключаюсь в облачный режим.\n"
            "Используйте /private для повторного переключения.",
        )
        return

    from services.tools import AI_TOOLS, FUNCTIONS_MAP
    import json

    sent = await message.answer("🔒 <i>Обрабатываю локально...</i>", parse_mode="HTML")

    # Try function calling first (Task 16)
    try:
        result = await ollama_service.chat_with_tools(
            messages=[{"role": "user", "content": message.text}],
            tools=AI_TOOLS,
            model="llama3.1:8b",
        )

        if result["tool_calls"]:
            tool_results = []
            for tc in result["tool_calls"]:
                fn = FUNCTIONS_MAP.get(tc["name"])
                if fn:
                    res = await fn(**tc["arguments"])
                    tool_results.append(f"[{tc['name']}]: {res}")
                if result["parse_errors"]:
                    log.warning("Tool parse errors: %s", result["parse_errors"])

            # Second pass with tool results
            followup = await ollama_service.chat(
                messages=[
                    {"role": "user", "content": message.text},
                    {"role": "tool", "content": "\n".join(tool_results)},
                ],
                model="llama3.1:8b",
            )
            ai_text = followup if isinstance(followup, str) else ""
        else:
            ai_text = result["content"]

    except Exception:
        # Fallback to simple chat without tools
        try:
            ai_text = await ollama_service.chat(
                messages=[{"role": "user", "content": message.text}],
            )
        except Exception as e2:
            ai_text = f"❌ Ошибка Ollama: {e2}"

    mode_indicator = "🔒 <i>[Локально · Ollama]</i>\n\n"
    await sent.edit_text(mode_indicator + ai_text, parse_mode="HTML")
