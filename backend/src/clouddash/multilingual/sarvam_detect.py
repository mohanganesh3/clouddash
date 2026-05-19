"""Sarvam-powered language detection + greeting generation.

Detects if the first message is in an Indian language (Hindi, Tamil, Telugu,
Bengali, Marathi, Kannada, Gujarati, Malayalam, Punjabi) and generates a
greeting in that language before switching to English for the actual support flow.

This is a demo moment — show that CloudDash is India-aware.
Uses sarvam-30b for detection (fast, low cost).
"""
from __future__ import annotations

from pydantic import BaseModel

from clouddash.models import LanguageDetection


_SUPPORTED_INDIAN_LANGS = {
    "hi": "Hindi",
    "ta": "Tamil",
    "te": "Telugu",
    "bn": "Bengali",
    "mr": "Marathi",
    "kn": "Kannada",
    "gu": "Gujarati",
    "ml": "Malayalam",
    "pa": "Punjabi",
}

_GREETINGS = {
    "hi": "नमस्ते! मैं CloudDash सपोर्ट हूँ। मैं आपकी मदद कर सकता हूँ। Please tell me your issue in English so I can assist you better.",
    "ta": "வணக்கம்! நான் CloudDash support. உங்கள் பிரச்சனையை English-ல் சொல்லுங்கள்.",
    "te": "నమస్కారం! CloudDash support ఇక్కడ ఉంది. దయచేసి మీ సమస్యను English లో చెప్పండి.",
    "bn": "নমস্কার! আমি CloudDash সাপোর্ট। আপনার সমস্যাটি English এ বলুন।",
    "mr": "नमस्कार! मी CloudDash सपोर्ट आहे। कृपया तुमची समस्या English मध्ये सांगा.",
    "kn": "ನಮಸ್ಕಾರ! CloudDash support ಇಲ್ಲಿದೆ. ದಯವಿಟ್ಟು English ನಲ್ಲಿ ನಿಮ್ಮ ಸಮಸ್ಯೆ ತಿಳಿಸಿ.",
    "gu": "નમસ્તે! CloudDash support અહીં છે. Please English માં તમારી સમસ્યા જણાવો.",
    "ml": "നമസ്കാരം! CloudDash support ഇവിടെ ഉണ്ട്. ദയവായി English-ൽ പ്രശ്നം പറയൂ.",
    "pa": "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ! CloudDash support ਇੱਥੇ ਹੈ। ਕਿਰਪਾ ਕਰਕੇ English ਵਿੱਚ ਆਪਣੀ ਸਮੱਸਿਆ ਦੱਸੋ।",
}


class _LangOutput(BaseModel):
    language_code: str  # ISO 639-1
    confidence: float


async def detect_language(text: str) -> LanguageDetection:
    """Detect language of user input. Uses sarvam-30b for accuracy on Indian scripts."""
    from clouddash.providers.sarvam import build_sarvam
    from clouddash.settings import get_settings

    cfg = get_settings()
    if not cfg.sarvam_api_key:
        return LanguageDetection(detected_language="en", is_indian_language=False)

    llm = build_sarvam(cfg.sarvam_fast_model, temperature=0.0).with_structured_output(_LangOutput)
    prompt = (
        f"Detect the language of this text. Return the ISO 639-1 code (e.g. 'en', 'hi', 'ta').\n\n"
        f"Text: {text[:200]}"
    )
    try:
        out: _LangOutput = await llm.ainvoke(prompt)
        lang = out.language_code.lower().strip()[:2]
    except Exception:
        lang = "en"

    is_indian = lang in _SUPPORTED_INDIAN_LANGS
    greeting = _GREETINGS.get(lang, "") if is_indian else ""

    return LanguageDetection(
        detected_language=lang,
        is_indian_language=is_indian,
        greeting=greeting,
    )
