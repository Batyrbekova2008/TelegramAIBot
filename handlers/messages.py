from aiogram import Router, types, F
from aiogram.filters import Command
from services.llm_router import llm_router
from services.summary_manager import summary_manager
from services.tools import AI_TOOLS, FUNCTIONS_MAP
from config.settings import config
from groq import AsyncGroq
import json
import tempfile
import os

router = Router()
groq_client = AsyncGroq(api_key=config.GROQ_API_KEY.get_secret_value())

@router.message(Command("start"))
async def handle_start(message: types.Message):
    await message.answer(
        "👋 <b>Сәлем! Мен AI көмекшіңізбін.</b>\n\n"
        "Мәтін немесе дауыстық хабарлама жіберіңіз!",
        parse_mode="HTML"
    )

@router.message(F.voice | F.audio)
async def handle_voice(message: types.Message):
    try:
        # Дауыстық файлды жүктеп алу
        if message.voice:
            file = await message.bot.get_file(message.voice.file_id)
        else:
            file = await message.bot.get_file(message.audio.file_id)

        # Файлды уақытша сақтау
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name

        await message.bot.download_file(file.file_path, destination=tmp_path)

        # Groq Whisper арқылы мәтінге айналдыру
        with open(tmp_path, "rb") as audio_file:
            transcription = await groq_client.audio.transcriptions.create(
                file=("audio.ogg", audio_file),
                model="whisper-large-v3",
                language="kk"
            )

        os.unlink(tmp_path)
        user_text = transcription.text

        if not user_text.strip():
            await message.answer("❌ Дауыстық хабарламаны түсіне алмадым. Қайтадан байқаңыз.")
            return

        await message.answer(f"🎙️ <b>Сіз айттыңыз:</b> {user_text}", parse_mode="HTML")

        # Мәтін ретінде AI-ға жіберу
        chat_id = message.chat.id
        await summary_manager.add_message(chat_id, "user", user_text)
        history = await summary_manager.get_history(chat_id)

        response, _ = await llm_router.send_chat_completion(
            messages=history,
            tools=AI_TOOLS
        )

        msg = response.choices[0].message

        if msg.tool_calls:
            tool_results = []
            for tc in msg.tool_calls:
                fn = FUNCTIONS_MAP.get(tc.function.name)
                if fn:
                    raw_args = tc.function.arguments
                    args = json.loads(raw_args) if raw_args else {}
                    result = await fn(**args)
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result
                    })

            history.append({
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments or "{}"
                        }
                    }
                    for tc in msg.tool_calls
                ]
            })
            history.extend(tool_results)

            final_response, _ = await llm_router.send_chat_completion(messages=history)
            ai_text = final_response.choices[0].message.content
        else:
            ai_text = msg.content

        await summary_manager.add_message(chat_id, "assistant", ai_text)
        await message.answer(ai_text, parse_mode="HTML")

    except Exception as e:
        print(f"Дауыстық қате: {e}")
        await message.answer("❌ Дауыстық хабарламаны өңдеу кезінде қате кетті.")

@router.message()
async def handle_text(message: types.Message):
    try:
        chat_id = message.chat.id
        if not message.text:
            return

        await summary_manager.add_message(chat_id, "user", message.text)
        history = await summary_manager.get_history(chat_id)

        response, _ = await llm_router.send_chat_completion(
            messages=history,
            tools=AI_TOOLS
        )

        msg = response.choices[0].message

        if msg.tool_calls:
            tool_results = []
            for tc in msg.tool_calls:
                fn = FUNCTIONS_MAP.get(tc.function.name)
                if fn:
                    raw_args = tc.function.arguments
                    args = json.loads(raw_args) if raw_args else {}
                    result = await fn(**args)
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result
                    })

            history.append({
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments or "{}"
                        }
                    }
                    for tc in msg.tool_calls
                ]
            })
            history.extend(tool_results)

            final_response, _ = await llm_router.send_chat_completion(messages=history)
            ai_text = final_response.choices[0].message.content
        else:
            ai_text = msg.content

        await summary_manager.add_message(chat_id, "assistant", ai_text)
        await message.answer(ai_text, parse_mode="HTML")

    except Exception as e:
        print(f"Қате: {e}")
        await message.answer("❌ Қате кетті. Қайтадан байқап көріңіз.")