import tempfile
import os
import edge_tts

VOICES = {
    "ru": "ru-RU-SvetlanaNeural",
    "kk": "kk-KZ-AigulNeural",
    "en": "en-US-JennyNeural",
}

_KK_CHARS = set("әғқңөұүһіӘҒҚҢӨҰҮҺІ")

def detect_lang(text: str) -> str:
    kk_count = sum(1 for c in text if c in _KK_CHARS)
    return "kk" if kk_count >= 2 else "ru"

async def text_to_speech(text: str, lang: str | None = None) -> str:
    if lang is None:
        lang = detect_lang(text)
    voice = VOICES.get(lang, VOICES["ru"])
    communicate = edge_tts.Communicate(text, voice)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name
    await communicate.save(tmp_path)
    return tmp_path
