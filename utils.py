import ctypes
import json
import os
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import unquote
from urllib.request import Request, urlopen

from state import APP_NAME, APP_VERSION, BACKUP_DIR, LOCAL_DIR, ROAMING_DIR

CYCLES_API_URL = "https://fmsdata.api.navigraph.com/v3/cycles"
LOG_DIR = ROAMING_DIR / "logs"
LEGACY_LOG_FILE = ROAMING_DIR / "app.log"


def human_time() -> str:
    return datetime.now().strftime("%H:%M:%S")


def human_datetime() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _startup_subprocess_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "ignore",
        "check": False,
    }
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return kwargs


def _show_windows_message_box(title: str, message: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
    except Exception:
        pass


def _query_windows_processes() -> list[dict[str, Any]]:
    if os.name != "nt":
        return []
    script = r"""
$ErrorActionPreference = 'Stop'
$procs = Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match '^(?i)(msiexec\.exe|FMS_UPDATE_MANAGER_Installer\.exe)$' } |
    Select-Object ProcessId, Name, CommandLine
if ($null -eq $procs) {
    '[]'
} else {
    $procs | ConvertTo-Json -Compress
}
"""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            **_startup_subprocess_kwargs(),
        )
        payload = (result.stdout or "").strip()
        if result.returncode != 0 or not payload:
            return []
        parsed = json.loads(payload)
        if isinstance(parsed, dict):
            parsed = [parsed]
        return [item for item in parsed if isinstance(item, dict)]
    except Exception:
        return []


def _is_our_installer_running() -> bool:
    from state import APP_EXECUTABLE_NAME, INSTALLER_COMMANDLINE_HINTS, INSTALLER_EXECUTABLE_NAME

    current_pid = os.getpid()
    for proc in _query_windows_processes():
        try:
            pid = int(proc.get("ProcessId", 0) or 0)
        except Exception:
            pid = 0
        if pid == current_pid:
            continue
        name = str(proc.get("Name", "")).strip().lower()
        command_line = str(proc.get("CommandLine", "")).strip().lower()
        if name == INSTALLER_EXECUTABLE_NAME.lower():
            return True
        if name == "msiexec.exe" and any(hint in command_line for hint in INSTALLER_COMMANDLINE_HINTS):
            return True
    return False


def _ensure_installer_not_running() -> bool:
    from state import APP_NAME, INSTALLER_COMMANDLINE_HINTS

    if not _is_our_installer_running():
        return True
    _show_windows_message_box(
        APP_NAME,
        "检测到安装程序正在运行。\n\n"
        "安装程序与软件不能同时运行，请二选一：\n"
        "1. 先完成安装，再启动软件；\n"
        "2. 或先关闭安装程序，再打开软件。",
    )
    return False


def fs(size: int) -> int:
    return max(8, int(round(size * 0.9)))


def get_colors(theme_name: str) -> dict[str, str]:
    from state import THEME_DARK

    if theme_name == THEME_DARK:
        return {
            "root_bg": "#141a24",
            "sidebar_bg": "#1a2332",
            "main_bg": "#1b2431",
            "panel_bg": "#243247",
            "panel_soft_bg": "#2c3b53",
            "text_title": "#f3f7ff",
            "text_sub": "#97abc7",
            "text_meta": "#9bb2cf",
            "text_path": "#b5c4da",
            "cycle_big": "#8ab4ff",
            "list_bg": "#223149",
            "list_fg": "#e2ebf8",
            "list_sel_bg": "#31486b",
            "list_sel_fg": "#ffffff",
            "canvas_bg": "#1b2431",
            "log_bg": "#1f2b3c",
            "log_fg": "#d9e5f8",
            "switch_shell_bg": "#2d3b51",
            "switch_unsel_bg": "#2d3b51",
            "switch_unsel_fg": "#a8bad4",
            "switch_unsel_fg_active": "#c3d3ea",
            "filter_bg": "#314564",
            "filter_fg": "#d6e3f5",
            "filter_active_bg": "#1a73e8",
            "filter_active_fg": "#ffffff",
            "card_bg": "#243247",
            "card_title": "#eef4ff",
            "card_sub": "#9db2d0",
            "card_meta": "#b8c8dd",
        }
    return {
        "root_bg": "#dce2ea",
        "sidebar_bg": "#cfd8e3",
        "main_bg": "#dce2ea",
        "panel_bg": "#e8edf4",
        "panel_soft_bg": "#eef3f9",
        "text_title": "#14263f",
        "text_sub": "#5c6e8b",
        "text_meta": "#324b73",
        "text_path": "#314766",
        "cycle_big": "#183c74",
        "list_bg": "#e8edf4",
        "list_fg": "#13233b",
        "list_sel_bg": "#cad7ea",
        "list_sel_fg": "#13233b",
        "canvas_bg": "#dce2ea",
        "log_bg": "#eef3f9",
        "log_fg": "#2b3e5f",
        "switch_shell_bg": "#e5ebf3",
        "switch_unsel_bg": "#e5ebf3",
        "switch_unsel_fg": "#6d7fa0",
        "switch_unsel_fg_active": "#4f6286",
        "filter_bg": "#d7e2f1",
        "filter_fg": "#274768",
        "filter_active_bg": "#1a73e8",
        "filter_active_fg": "#ffffff",
        "card_bg": "#f1f5fa",
        "card_title": "#12243f",
        "card_sub": "#5a6f91",
        "card_meta": "#354f73",
    }


def detect_airac(text: str) -> str:
    if not text:
        return "UNKNOWN"
    match = re.search(r"([0-9]{4})", str(text))
    return match.group(1) if match else "UNKNOWN"


def parse_iso_utc(raw: str) -> datetime:
    normalized = raw.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except Exception:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _parse_version_numbers(raw: str) -> tuple[int, ...]:
    text = str(raw or "").strip()
    if not text:
        return ()
    text = text.lstrip("vV")
    nums = re.findall(r"\d+", text)
    if not nums:
        return ()
    try:
        return tuple(int(item) for item in nums)
    except Exception:
        return ()


def _is_newer_version(latest: str, current: str) -> bool:
    latest_parts = _parse_version_numbers(latest)
    current_parts = _parse_version_numbers(current)
    if not latest_parts or not current_parts:
        return False
    width = max(len(latest_parts), len(current_parts))
    left = latest_parts + (0,) * (width - len(latest_parts))
    right = current_parts + (0,) * (width - len(current_parts))
    return left > right


def format_version_display(raw: str) -> str:
    parts = _parse_version_numbers(raw)
    if parts:
        normalized = parts[:3] + (0,) * max(0, 3 - len(parts[:3]))
        return ".".join(str(item) for item in normalized)
    text = str(raw or "").strip().lstrip("vV")
    return text or "未知版本"


def current_log_file() -> Path:
    return LOG_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.log"


def append_log_file(line: str) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with current_log_file().open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def read_log_lines(limit: int = 400) -> list[str]:
    if limit <= 0:
        return []
    try:
        parsed_lines: list[str] = []
        current_file = current_log_file()
        use_current_file = current_file.exists()
        if use_current_file:
            lines = current_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        elif LEGACY_LOG_FILE.exists():
            lines = LEGACY_LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
        else:
            return []
        today = datetime.now().strftime("%Y-%m-%d")
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            dated_match = re.match(r"^\[(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})\]\s?(.*)$", line)
            if dated_match:
                if use_current_file or dated_match.group(1) == today:
                    msg = dated_match.group(3)
                    parsed_lines.append(f"[{dated_match.group(2)}] {msg}")
                continue
            legacy_match = re.match(r"^\[(\d{2}:\d{2}:\d{2})\]\s?(.*)$", line)
            if legacy_match:
                parsed_lines.append(line)
        return parsed_lines[-limit:]
    except Exception:
        return []

