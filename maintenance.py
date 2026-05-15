import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from state import BACKUP_DIR, DEFAULT_BATCH_DOWNLOAD_WORKERS, DEFAULT_CACHE_CLEANUP_DAYS, LOCAL_DIR


def resolve_cache_root_dir(state: dict[str, Any] | None = None, *, create: bool = False) -> Path:
    configured = ""
    if isinstance(state, dict):
        configured = normalize_cache_root_dir(str(state.get("cache_root_dir", "")))
    root = Path(configured) if configured else BACKUP_DIR
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def normalize_cache_root_dir(raw_path: str) -> str:
    import os

    text = str(raw_path or "").strip()
    if not text:
        return ""
    return str(Path(os.path.expandvars(text)).expanduser())


def default_backup_power_download_dir(state: dict[str, Any] | None = None) -> Path:
    return resolve_cache_root_dir(state, create=False) / "_openlist_cache"


def default_batch_download_cache_dir(state: dict[str, Any] | None = None) -> Path:
    return resolve_cache_root_dir(state, create=False) / "_openlist_batch_cache"


def resolve_existing_backup_power_download_dir(state: dict[str, Any]) -> Path | None:
    configured = normalize_cache_root_dir(str(state.get("backup_power_download_dir", "")))
    if configured:
        candidate = Path(configured)
        if candidate.exists() and candidate.is_dir():
            return candidate
    default_dir = default_backup_power_download_dir(state)
    if default_dir.exists() and default_dir.is_dir():
        return default_dir
    return None


def ensure_backup_power_download_dir(raw_path: str, *, create: bool = True) -> Path:
    normalized = normalize_cache_root_dir(raw_path)
    if not normalized:
        raise ValueError("请先指定 OpenList 下载目录。")
    target = Path(normalized)
    if create:
        target.mkdir(parents=True, exist_ok=True)
    if not target.exists() or not target.is_dir():
        raise ValueError("OpenList 下载目录不存在或不可用。")
    return target


def cleanup_backup_power_download_cache(state: dict[str, Any] | None = None) -> None:
    cache_dir = default_backup_power_download_dir(state)
    if not cache_dir.exists():
        return
    shutil.rmtree(cache_dir, ignore_errors=True)


def normalize_cache_cleanup_days(raw_value: Any) -> int:
    try:
        value = int(str(raw_value).strip())
    except Exception:
        return DEFAULT_CACHE_CLEANUP_DAYS
    if value in (1, 3, 7, 14, 30):
        return value
    if value <= 1:
        return 1
    if value >= 30:
        return 30
    return DEFAULT_CACHE_CLEANUP_DAYS


def _parse_cleanup_timestamp(raw_value: Any) -> datetime | None:
    text = str(raw_value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _remove_if_older_than(path: Path, cutoff_ts: float) -> bool:
    try:
        mtime = path.stat().st_mtime
    except Exception:
        return False
    if mtime >= cutoff_ts:
        return False
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def cleanup_stale_cache_entries(state: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    days = normalize_cache_cleanup_days(state.get("cache_cleanup_days", DEFAULT_CACHE_CLEANUP_DAYS))
    state["cache_cleanup_days"] = days
    now = datetime.now()
    last_cleanup = _parse_cleanup_timestamp(state.get("cache_last_cleanup_at", ""))
    if not force and last_cleanup is not None and now - last_cleanup < timedelta(days=days):
        return {"ran": False, "days": days, "removed": 0}
    cutoff_ts = (now - timedelta(days=days)).timestamp()
    removed_count = 0
    scan_targets = [default_backup_power_download_dir(state), default_batch_download_cache_dir(state)]
    for base in scan_targets:
        if not base.exists():
            continue
        for child in list(base.iterdir()):
            if _remove_if_older_than(child, cutoff_ts):
                removed_count += 1
        try:
            has_entries = any(base.iterdir())
        except Exception:
            has_entries = True
        if not has_entries:
            _remove_if_older_than(base, cutoff_ts)
    for pattern in ("fms_archive_*", "fms_cycle_probe_*"):
        for path in LOCAL_DIR.glob(pattern):
            if _remove_if_older_than(path, cutoff_ts):
                removed_count += 1
    state["cache_last_cleanup_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
    return {"ran": True, "days": days, "removed": removed_count}

