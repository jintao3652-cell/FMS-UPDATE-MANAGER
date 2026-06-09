"""OpenList client for admin_panel cycle monitor (#14).

Token cached in-process for ~110 minutes (OpenList tokens are 2h).
"""

import re
import threading
import time
from typing import Any

import httpx

from .config import settings

_token_cache: dict[str, Any] = {"token": "", "fetched_at": 0.0}
_token_lock = threading.Lock()
_TOKEN_TTL = 110 * 60  # ~2h, refresh a bit early


def _login() -> str:
    payload = {
        "username": settings.openlist_username,
        "password": settings.openlist_password,
        "otp_code": "",
    }
    with httpx.Client(timeout=15) as cli:
        r = cli.post(f"{settings.openlist_base_url}/api/auth/login", json=payload)
    r.raise_for_status()
    data = r.json()
    token = ""
    if isinstance(data, dict):
        token = str((data.get("data") or {}).get("token") or data.get("token") or "").strip()
    if not token:
        raise RuntimeError(f"openlist login: no token in response: {data!r}")
    return token


def _get_token(force: bool = False) -> str:
    with _token_lock:
        now = time.time()
        if not force and _token_cache["token"] and now - _token_cache["fetched_at"] < _TOKEN_TTL:
            return _token_cache["token"]
        token = _login()
        _token_cache["token"] = token
        _token_cache["fetched_at"] = now
        return token


def _list_dir(path: str) -> list[dict]:
    body = {"path": path or "/", "password": "", "page": 1, "per_page": 0, "refresh": False}
    for attempt in range(2):
        token = _get_token(force=(attempt == 1))
        try:
            with httpx.Client(timeout=20) as cli:
                r = cli.post(
                    f"{settings.openlist_base_url}/api/fs/list",
                    json=body,
                    headers={"Authorization": token},
                )
        except httpx.HTTPError as exc:
            if attempt == 1:
                raise
            continue
        if r.status_code in (401, 403):
            continue
        r.raise_for_status()
        data = r.json()
        content = ((data or {}).get("data") or {}).get("content") or []
        return [c for c in content if isinstance(c, dict)]
    return []


def list_cycles() -> list[dict]:
    """Return cycles available at OpenList root (folders whose name matches AIRAC YYMM)."""
    items = _list_dir(settings.openlist_root_path)
    cycles = []
    for it in items:
        name = str(it.get("name", "")).strip()
        if not it.get("is_dir"):
            continue
        if not re.fullmatch(r"\d{4}", name):
            continue
        cycles.append({
            "cycle_id": name,
            "modified": str(it.get("modified", "")),
            "size": int(it.get("size") or 0),
        })
    cycles.sort(key=lambda c: c["cycle_id"], reverse=True)
    return cycles


def list_msfs_packages(cycle_id: str) -> list[dict]:
    """List archive files under /<cycle>/MSFS/."""
    cycle = str(cycle_id or "").strip()
    if not re.fullmatch(r"\d{4}", cycle):
        raise ValueError("invalid cycle id")
    items = _list_dir(f"/{cycle}/MSFS")
    files = []
    for it in items:
        if it.get("is_dir"):
            continue
        files.append({
            "name": str(it.get("name", "")),
            "size": int(it.get("size") or 0),
            "modified": str(it.get("modified", "")),
        })
    files.sort(key=lambda f: f["name"].lower())
    return files
