"""Minimal OpenList client used by the AIRAC cycle subscription cron.

Mirrors deploy/admin_panel/app/openlist_client.py but lives in backup_auth so
the SMTP worker / cron in backup_auth can poll OpenList directly without going
through admin_panel.
"""

import os
import re
import threading
import time
from typing import Any

import httpx

OPENLIST_BASE_URL = os.getenv("APP_OPENLIST_BASE_URL", "http://main.cnrpg.top:5245").strip().rstrip("/")
OPENLIST_USERNAME = os.getenv("APP_OPENLIST_USERNAME", "navdata").strip()
OPENLIST_PASSWORD = os.getenv("APP_OPENLIST_PASSWORD", "navdata").strip()
OPENLIST_ROOT_PATH = os.getenv("APP_OPENLIST_ROOT_PATH", "/").strip() or "/"

_token_cache: dict[str, Any] = {"token": "", "fetched_at": 0.0}
_token_lock = threading.Lock()
_TOKEN_TTL = 110 * 60


def _login() -> str:
    with httpx.Client(timeout=15) as cli:
        r = cli.post(
            f"{OPENLIST_BASE_URL}/api/auth/login",
            json={"username": OPENLIST_USERNAME, "password": OPENLIST_PASSWORD, "otp_code": ""},
        )
    r.raise_for_status()
    data = r.json()
    token = ""
    if isinstance(data, dict):
        token = str((data.get("data") or {}).get("token") or data.get("token") or "").strip()
    if not token:
        raise RuntimeError(f"openlist login: no token: {data!r}")
    return token


def _get_token(force: bool = False) -> str:
    with _token_lock:
        now = time.time()
        if not force and _token_cache["token"] and now - _token_cache["fetched_at"] < _TOKEN_TTL:
            return _token_cache["token"]
        _token_cache["token"] = _login()
        _token_cache["fetched_at"] = now
        return _token_cache["token"]


def _list_dir(path: str) -> list[dict]:
    body = {"path": path or "/", "password": "", "page": 1, "per_page": 0, "refresh": False}
    for attempt in range(2):
        token = _get_token(force=(attempt == 1))
        with httpx.Client(timeout=20) as cli:
            r = cli.post(
                f"{OPENLIST_BASE_URL}/api/fs/list",
                json=body,
                headers={"Authorization": token},
            )
        if r.status_code in (401, 403):
            continue
        r.raise_for_status()
        data = r.json()
        content = ((data or {}).get("data") or {}).get("content") or []
        return [c for c in content if isinstance(c, dict)]
    return []


def latest_cycle() -> str:
    """Return the highest-numbered AIRAC cycle folder name, or '' if none."""
    try:
        items = _list_dir(OPENLIST_ROOT_PATH)
    except Exception:
        return ""
    names = []
    for it in items:
        if not it.get("is_dir"):
            continue
        n = str(it.get("name", "")).strip()
        if re.fullmatch(r"\d{4}", n):
            names.append(n)
    if not names:
        return ""
    names.sort(reverse=True)
    return names[0]
