import os
import json
import time
import base64
import tempfile
import logging
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
from groq import AsyncGroq
from config.settings import config
from config.database import save_message
from services.llm_router import llm_router
from services.summary_manager import summary_manager
from services.tools import AI_TOOLS, FUNCTIONS_MAP
from services.tts_service import text_to_speech
from services.rate_limiter import rate_limiter

from services.search_service import SearchService, SearchAwareHandler

router = Router()
groq_client = AsyncGroq(api_key=config.GROQ_API_KEY.get_secret_value())
action_logger = logging.getLogger("bot.actions")

_search_svc = SearchService(api_key=config.TAVILY_API_KEY or None)
_search_handler = SearchAwareHandler(groq_client, _search_svc)

# ─── /start ────────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def handle_start(message: types.Message):
    await message.answer(
        "👋 <b>Сәлем! Мен AI көмекшіңізбін.</b>\n\n"
        "Мәтін, дауыстық хабарлама немесе суret жіберіңіз!",
        parse_mode="HTML"
    )

# ─── /help ─────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def handle_help(message: types.Message):
    await message.answer(
        "🤖 <b>Қолжетімді командалар:</b>\n\n"
        "/start — Ботты қосу\n"
        "/help — Осы анықтама\n\n"
        "<b>Не жіберуге болады:</b>\n"
        "✉️ Мәтін — AI жауабы\n"
        "🎙️ Дауыс — транскрипция + AI жауабы\n"
        "🖼️ Сурет — визуалды талдау\n\n"
        "<b>Ақылды функциялар:</b>\n"
        "🕐 Уақыт · 🌤️ Ауа райы · 🧮 Калькулятор · 💻 Жүйе ресурстары",
        parse_mode="HTML"
    )

# ─── Photo ─────────────────────────────────────────────────────────────────────

@router.message(F.photo)
async def handle_photo(message: types.Message):
    if not await rate_limiter.check_limits(message.from_user.id, message.chat.id):
        await message.answer("⏳ Тым көп сұраныс. Бір минуттан кейін қайталаңыз.")
        return
    try:
        await message.answer("🔍 Суретті талдауда...")

        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
        await message.bot.download_file(file.file_path, destination=tmp_path)

        with open(tmp_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
        os.unlink(tmp_path)

        prompt = (
            message.caption
            or "Суретте не бар? Толық сипатта. Егер тапсырма немесе мәтін болса — шеш/жаз."
        )

        response = await groq_client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    ],
                }
            ],
        )

        ai_text = response.choices[0].message.content

        user_id = message.from_user.id
        chat_id = message.chat.id
        await save_message(user_id, chat_id, "user", "image", prompt)
        await save_message(user_id, chat_id, "assistant", "image", ai_text)

        action_logger.info(
            "user_id=%s username=%s type=image response_len=%d",
            user_id, message.from_user.username or "", len(ai_text)
        )
        await message.answer(ai_text, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Photo error: {e}")
        await message.answer("❌ Суретті өңдеу кезінде қате кетті.")

# ─── Voice ─────────────────────────────────────────────────────────────────────

@router.message(F.voice | F.audio)
async def handle_voice(message: types.Message):
    if not await rate_limiter.check_limits(message.from_user.id, message.chat.id):
        await message.answer("⏳ Тым көп сұраныс. Бір минуттан кейін қайталаңыз.")
        return
    tts_path = None
    tmp_path = None
    try:
        if message.voice:
            file = await message.bot.get_file(message.voice.file_id)
        else:
            file = await message.bot.get_file(message.audio.file_id)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        await message.bot.download_file(file.file_path, destination=tmp_path)

        with open(tmp_path, "rb") as audio_file:
            transcription = await groq_client.audio.transcriptions.create(
                file=("audio.ogg", audio_file),
                model="whisper-large-v3",
            )
        os.unlink(tmp_path)
        tmp_path = None

        user_text = transcription.text.strip()
        if not user_text:
            await message.answer("❌ Дауыстық хабарламаны түсіне алмадым.")
            return

        await message.answer(f"🎙️ <b>Сіз айттыңыз:</b> {user_text}", parse_mode="HTML")

        chat_id = message.chat.id
        user_id = message.from_user.id
        await summary_manager.add_message(chat_id, "user", user_text)
        await save_message(user_id, chat_id, "user", "voice", user_text)

        history = await summary_manager.get_history(chat_id)
        response, _ = await llm_router.send_chat_completion(messages=history, tools=AI_TOOLS)
        msg = response.choices[0].message

        if msg.tool_calls:
            ai_text = await _process_tool_calls(msg, history)
        else:
            ai_text = msg.content

        await summary_manager.add_message(chat_id, "assistant", ai_text)
        await save_message(user_id, chat_id, "assistant", "voice", ai_text)

        action_logger.info(
            "user_id=%s username=%s type=voice text=%r response_len=%d",
            user_id, message.from_user.username or "", user_text[:100], len(ai_text)
        )

        # Respond with voice
        try:
            tts_path = await text_to_speech(ai_text)
            voice_file = FSInputFile(tts_path)
            await message.answer_voice(voice_file)
        except Exception as tts_err:
            logging.warning(f"TTS failed, falling back to text: {tts_err}")
            await message.answer(ai_text, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Voice error: {e}")
        await message.answer("❌ Дауыстық хабарламаны өңдеу кезінде қате кетті.")
    finally:
        for path in (tmp_path, tts_path):
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except Exception:
                    pass

# ─── Text (streaming with debounce) ───────────────────────────────────────────

_STREAM_DEBOUNCE = 1.5  # seconds between Telegram edits

@router.message()
async def handle_text(message: types.Message):
    if not message.text:
        return
    if not await rate_limiter.check_limits(message.from_user.id, message.chat.id):
        await message.answer("⏳ Тым көп сұраныс. Бір минуттан кейін қайталаңыз.")
        return
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id

        await summary_manager.add_message(chat_id, "user", message.text)
        await save_message(user_id, chat_id, "user", "text", message.text)

        history = await summary_manager.get_history(chat_id)

        sent_msg = await message.answer("⏳")
        accumulated = ""
        last_edit_time = time.monotonic()
        tool_calls_raw = None

        async for event_type, data, _model in llm_router.stream_chat_completion(
            messages=history, tools=AI_TOOLS
        ):
            if event_type == "text":
                accumulated += data
                now = time.monotonic()
                if now - last_edit_time >= _STREAM_DEBOUNCE and accumulated.strip():
                    try:
                        await sent_msg.edit_text(accumulated, parse_mode="HTML")
                        last_edit_time = now
                    except Exception:
                        pass
            elif event_type == "tool_calls":
                tool_calls_raw = data
            # "done" — final full_text already equals accumulated

        if tool_calls_raw:
            ai_text = await _process_tool_calls_raw(tool_calls_raw, history, sent_msg)
        else:
            ai_text = accumulated
            if ai_text.strip():
                try:
                    await sent_msg.edit_text(ai_text, parse_mode="HTML")
                except Exception:
                    pass

        await summary_manager.add_message(chat_id, "assistant", ai_text)
        await save_message(user_id, chat_id, "assistant", "text", ai_text)

        action_logger.info(
            "user_id=%s username=%s type=text text=%r response_len=%d",
            user_id, message.from_user.username or "", message.text[:100], len(ai_text)
        )

    except Exception as e:
        logging.error(f"Text error: {e}")
        await message.answer("❌ Қате кетті. Қайтадан байқап көріңіз.")

# ─── Helpers ───────────────────────────────────────────────────────────────────

async def _process_tool_calls_raw(tool_calls_raw: dict, history: list, sent_msg) -> str:
    """Process tool calls assembled from streaming chunks."""
    tc_list = [
        {
            "id": tc["id"],
            "type": "function",
            "function": {"name": tc["name"], "arguments": tc["args"]},
        }
        for _, tc in sorted(tool_calls_raw.items())
    ]
    history.append({"role": "assistant", "tool_calls": tc_list})

    tool_results = []
    for tc in tc_list:
        fn = FUNCTIONS_MAP.get(tc["function"]["name"])
        if fn:
            args = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
            result = await fn(**args)
            tool_results.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })
    history.extend(tool_results)

    final_response, _ = await llm_router.send_chat_completion(messages=history)
    ai_text = final_response.choices[0].message.content
    try:
        await sent_msg.edit_text(ai_text, parse_mode="HTML")
    except Exception:
        pass
    return ai_text


async def _process_tool_calls(msg, history: list) -> str:
    tool_results = []
    for tc in msg.tool_calls:
        fn = FUNCTIONS_MAP.get(tc.function.name)
        if fn:
            args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            result = await fn(**args)
            tool_results.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    history.append({
        "role": "assistant",
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"},
            }
            for tc in msg.tool_calls
        ],
    })
    history.extend(tool_results)

    final_response, _ = await llm_router.send_chat_completion(messages=history)
    return final_response.choices[0].message.content
