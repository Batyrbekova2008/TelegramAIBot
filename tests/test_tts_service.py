import pytest
from services.tts_service import detect_lang, VOICES


# ── detect_lang ───────────────────────────────────────────────────────────────

def test_detect_lang_pure_russian():
    assert detect_lang("Привет, как дела?") == "ru"


def test_detect_lang_pure_kazakh_chars():
    # "Сәлем" contains 'ә' which is a Kazakh char
    assert detect_lang("Сәлем, қалайсыз?") == "kk"


def test_detect_lang_one_kazakh_char_stays_ru():
    # Only 1 Kazakh char → below threshold of 2
    assert detect_lang("Сәлем world") == "ru"


def test_detect_lang_exactly_two_kazakh_chars():
    # Exactly 2 Kazakh-specific chars → kk
    text = "аәa"  # 'ә' = 1, plus we need one more: 'ғ'
    text = "аәғ"
    assert detect_lang(text) == "kk"


def test_detect_lang_empty_string():
    assert detect_lang("") == "ru"


def test_detect_lang_english():
    assert detect_lang("Hello, how are you?") == "ru"


def test_detect_lang_numbers_only():
    assert detect_lang("1234567890") == "ru"


# ── VOICES lookup ─────────────────────────────────────────────────────────────

def test_voices_has_all_languages():
    assert "ru" in VOICES
    assert "kk" in VOICES
    assert "en" in VOICES


def test_voices_not_empty():
    for voice in VOICES.values():
        assert isinstance(voice, str) and voice
