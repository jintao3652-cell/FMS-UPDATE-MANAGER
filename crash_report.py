"""Crash capture + optional upload to backend.

- Hooks `sys.excepthook` and `asyncio` exception handlers.
- Writes a `crash_*.log` file under `%APPDATA%/.../logs/` for every fault.
- If the user opted in (state["crash_upload_enabled"]), POSTs the report to
  `<BACKUP_POWER_SERVER_BASE>/api/crash` in a background thread.
"""

import asyncio
import json
import platform
import sys
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from openlist import BACKUP_POWER_SERVER_BASE
from state import APP_NAME, APP_VERSION
from utils import LOG_DIR

CRASH_ENDPOINT = f"{BACKUP_POWER_SERVER_BASE}/api/crash"
_state_provider = None  # set by install_crash_handlers(state_getter=...)
_install_id_cache: str | None = None


def _install_id() -> str:
    """Stable per-machine pseudo-id (no PII)."""
    global _install_id_cache
    if _install_id_cache is not None:
        return _install_id_cache
    try:
        marker = LOG_DIR / ".install_id"
        if marker.exists():
            _install_id_cache = marker.read_text(encoding="utf-8").strip()
        else:
            import uuid
            _install_id_cache = uuid.uuid4().hex
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(_install_id_cache, encoding="utf-8")
    except Exception:
        _install_id_cache = "unknown"
    return _install_id_cache


def _build_report(kind: str, exc: BaseException | None, tb_text: str | None = None, extra: dict | None = None) -> dict:
    if tb_text is None and exc is not None:
        tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "app": APP_NAME,
        "version": APP_VERSION,
        "install_id": _install_id(),
        "kind": kind,
        "exc_type": type(exc).__name__ if exc is not None else "",
        "exc_msg": _redact(str(exc)) if exc is not None else "",
        "traceback": _redact(tb_text or ""),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "extra": _redact_obj(extra or {}),
    }


_REDACT_PATTERNS = [
    (__import__("re").compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", __import__("re").IGNORECASE), r"\1<redacted>"),
    (__import__("re").compile(r"(Authorization\s*[:=]\s*['\"]?Bearer\s+)[A-Za-z0-9._\-]+", __import__("re").IGNORECASE), r"\1<redacted>"),
    (__import__("re").compile(r"((?:password|passwd|pwd|token|refresh_token|secret|api[_-]?key)\s*['\"]?\s*[:=]\s*['\"]?)([^\s'\"&,;}\)]{4,})", __import__("re").IGNORECASE), r"\1<redacted>"),
    (__import__("re").compile(r"((?:[?&])(?:password|passwd|pwd|token|refresh_token|secret|api[_-]?key|email_code)=)([^&\s]+)", __import__("re").IGNORECASE), r"\1<redacted>"),
    (__import__("re").compile(r"\b([A-Za-z0-9_\-]{20,})\.([A-Za-z0-9_\-]{10,})\.([A-Za-z0-9_\-]{20,})\b"), r"<redacted-jwt>"),
]


def _redact(text: str) -> str:
    out = text or ""
    for pat, repl in _REDACT_PATTERNS:
        try:
            out = pat.sub(repl, out)
        except Exception:
            pass
    return out


def _redact_obj(obj):
    if isinstance(obj, dict):
        return {k: ("<redacted>" if str(k).lower() in {"password", "passwd", "pwd", "token", "refresh_token", "secret", "api_key", "apikey", "email_code"} else _redact_obj(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_obj(v) for v in obj]
    if isinstance(obj, str):
        return _redact(obj)
    return obj


def _write_local_crash_log(report: dict) -> Path | None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = LOG_DIR / f"crash_{stamp}.log"
        body = (
            f"=== {report['ts']} ===\n"
            f"app: {report['app']} v{report['version']}\n"
            f"install_id: {report['install_id']}\n"
            f"platform: {report['platform']} / python {report['python']}\n"
            f"kind: {report['kind']}\n"
            f"exc: {report['exc_type']}: {report['exc_msg']}\n"
            f"extra: {json.dumps(report['extra'], ensure_ascii=False)}\n"
            f"--- traceback ---\n{report['traceback']}\n"
        )
        path.write_text(body, encoding="utf-8")
        return path
    except Exception:
        return None


def _should_upload() -> bool:
    if _state_provider is None:
        return False
    try:
        state = _state_provider() or {}
        return bool(state.get("crash_upload_enabled", False))
    except Exception:
        return False


def _upload(report: dict) -> None:
    try:
        body = json.dumps(report, ensure_ascii=False).encode("utf-8")
        req = Request(
            CRASH_ENDPOINT,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": f"{APP_NAME}/{APP_VERSION}"},
            method="POST",
        )
        with urlopen(req, timeout=8) as resp:
            int(getattr(resp, "status", 200) or 200)
    except (HTTPError, URLError, OSError):
        pass
    except Exception:
        pass


def report_exception(exc: BaseException, *, kind: str = "manual", extra: dict | None = None) -> Path | None:
    report = _build_report(kind, exc, extra=extra)
    path = _write_local_crash_log(report)
    if _should_upload():
        threading.Thread(target=_upload, args=(report,), daemon=True).start()
    return path


def _excepthook(exc_type, exc, tb) -> None:
    if exc_type is KeyboardInterrupt:
        sys.__excepthook__(exc_type, exc, tb)
        return
    try:
        tb_text = "".join(traceback.format_exception(exc_type, exc, tb))
        report = _build_report("excepthook", exc, tb_text=tb_text)
        _write_local_crash_log(report)
        if _should_upload():
            threading.Thread(target=_upload, args=(report,), daemon=True).start()
    finally:
        sys.__excepthook__(exc_type, exc, tb)


def _asyncio_exc_handler(loop, context) -> None:
    exc = context.get("exception")
    msg = context.get("message", "")
    if exc is None:
        report = _build_report("asyncio", None, tb_text=f"asyncio: {msg}\ncontext keys: {list(context.keys())}")
    else:
        report = _build_report("asyncio", exc, extra={"message": msg})
    _write_local_crash_log(report)
    if _should_upload():
        threading.Thread(target=_upload, args=(report,), daemon=True).start()
    loop.default_exception_handler(context)


def install_crash_handlers(state_getter: Any = None) -> None:
    """Install global handlers. `state_getter` is a zero-arg callable returning
    the live state dict (used to read crash_upload_enabled at fire time)."""
    global _state_provider
    if state_getter is not None:
        _state_provider = state_getter
    sys.excepthook = _excepthook
    try:
        loop = asyncio.get_event_loop()
        loop.set_exception_handler(_asyncio_exc_handler)
    except RuntimeError:
        pass


def list_recent_crash_logs(limit: int = 20) -> list[Path]:
    try:
        files = sorted(LOG_DIR.glob("crash_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        return files[:limit]
    except Exception:
        return []
