"""Локалізація інтерфейсу: locales/<код>.json; бракує ключа → українська → сам ключ."""
import json
import os

from .paths import resource_path

LANGUAGES = {"uk": "Українська", "en": "English"}
FALLBACK = "uk"

_strings: dict = {}
_fallback: dict = {}
_lang = FALLBACK
_loaded = False


def _read(lang: str) -> dict:
    try:
        with open(resource_path(os.path.join("locales", f"{lang}.json")), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load(lang: str) -> None:
    global _strings, _fallback, _lang, _loaded
    _loaded = True
    _lang = lang if lang in LANGUAGES else FALLBACK
    _strings = _read(_lang)
    _fallback = _strings if _lang == FALLBACK else _read(FALLBACK)


def current() -> str:
    return _lang


def _ensure() -> None:
    if not _loaded:
        try:
            from . import settings
            lang = settings.get().lang
        except Exception:
            lang = FALLBACK
        load(lang)


def tr(key: str, **fmt) -> str:
    _ensure()
    text = _strings.get(key) or _fallback.get(key) or key
    if fmt:
        try:
            return text.format(**fmt)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def has(key: str) -> bool:
    _ensure()
    return key in _strings or key in _fallback
