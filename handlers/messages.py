import os
import json
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

router = Router()
groq_client = AsyncGroq(api_key=config.GROQ_API_KEY.get_secret_value())

# ─── /start ────────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def handle_start(message: types.Message):
    await message.answer(
        "👋 <b>Сәлем! Мен AI көмекшіңізбін.</b>\n\n"
        "Мәтін, дауыстық хабарлама немесе суret жіберіңіз!",
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

# ─── Text ──────────────────────────────────────────────────────────────────────

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
        response, _ = await llm_router.send_chat_completion(messages=history, tools=AI_TOOLS)
        msg = response.choices[0].message

        if msg.tool_calls:
            ai_text = await _process_tool_calls(msg, history)
        else:
            ai_text = msg.content

        await summary_manager.add_message(chat_id, "assistant", ai_text)
        await save_message(user_id, chat_id, "assistant", "text", ai_text)

        await message.answer(ai_text, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Text error: {e}")
        await message.answer("❌ Қате кетті. Қайтадан байқап көріңіз.")

# ─── Helpers ───────────────────────────────────────────────────────────────────

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
