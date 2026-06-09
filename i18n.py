"""Lightweight i18n for FMS UPDATE MANAGER.

Usage:
    from i18n import tr, set_locale, _
    label.text = _("设置")

Translation files live in ``i18n/<code>.json`` next to this module. Keys are the
original Chinese source strings; missing keys fall back to the key itself so the
app stays usable even if a language file is incomplete.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_BASE = Path(__file__).resolve().parent / "i18n"
_AVAILABLE = ("zh", "en")
_DEFAULT = "zh"

_cache: dict[str, dict[str, str]] = {}
_current = _DEFAULT


def available_locales() -> tuple[str, ...]:
    return _AVAILABLE


def _load(code: str) -> dict[str, str]:
    if code in _cache:
        return _cache[code]
    path = _BASE / f"{code}.json"
    data: dict[str, str] = {}
    try:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = {str(k): str(v) for k, v in raw.items()}
    except Exception:
        data = {}
    _cache[code] = data
    return data


def set_locale(code: str) -> None:
    global _current
    code = (code or "").strip().lower()
    if code not in _AVAILABLE:
        code = _DEFAULT
    _current = code
    _load(code)


def current_locale() -> str:
    return _current


def tr(key: str, **fmt: Any) -> str:
    if not isinstance(key, str):
        return str(key)
    table = _load(_current)
    text = table.get(key, key)
    if fmt:
        try:
            return text.format(**fmt)
        except Exception:
            return text
    return text


_ = tr
