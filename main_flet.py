import json
import io
import os
import re
import asyncio
import base64
import ctypes
import sys
import subprocess
import shutil
import struct
import time
import webbrowser
import zipfile
import tempfile
import tarfile
import xml.etree.ElementTree as ET
from queue import Empty, SimpleQueue
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, cast
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

import flet as ft

ft.context.disable_auto_update()

APP_NAME = "FMS UPDATE MANAGER"
APP_EXECUTABLE_NAME = "FMS_UPDATE_MANAGER.exe"
INSTALLER_PACKAGE_NAME = "FMS_UPDATE_MANAGER_Installer.msi"
INSTALLER_EXECUTABLE_NAME = "FMS_UPDATE_MANAGER_Installer.exe"
INSTALLER_COMMANDLINE_HINTS = (
    INSTALLER_PACKAGE_NAME.lower(),
    INSTALLER_EXECUTABLE_NAME.lower(),
    "fms_update_manager_installer",
    "fms update manager installer",
)
ROAMING_DIR = Path(os.path.expandvars(r"%APPDATA%")) / APP_NAME
LOCAL_DIR = Path(os.path.expandvars(r"%LOCALAPPDATA%")) / APP_NAME
TASKBAR_ICON_FILE = Path(__file__).resolve().parent / "assets" / "travel_airplane.ico"
APP_WINDOW_LOGO_FILE = Path(__file__).resolve().parent / "assets" / "logo_telegram.ico"
STATE_FILE = ROAMING_DIR / "state.json"
LEGACY_LOG_FILE = ROAMING_DIR / "app.log"
LOG_DIR = ROAMING_DIR / "logs"
EXTRACTED_DIR = LOCAL_DIR / "extracted"
BACKUP_DIR = LOCAL_DIR / "backups"
CYCLES_API_URL = "https://fmsdata.api.navigraph.com/v3/cycles"
BACKUP_POWER_SERVER_BASE = "http://data.cnrpg.top:17306"
BACKUP_POWER_LOGIN_URL = f"{BACKUP_POWER_SERVER_BASE}/api/auth/login"
BACKUP_POWER_NAVDATA_DOWNLOAD_URL = f"{BACKUP_POWER_SERVER_BASE}/api/navdata/download"
BACKUP_POWER_ME_URL = f"{BACKUP_POWER_SERVER_BASE}/api/me"
OPENLIST_BASE_URL = "http://main.cnrpg.top:5245"
OPENLIST_LOGIN_URL = f"{OPENLIST_BASE_URL}/api/auth/login"
OPENLIST_LIST_URL = f"{OPENLIST_BASE_URL}/api/fs/list"
OPENLIST_GET_URL = f"{OPENLIST_BASE_URL}/api/fs/get"
OPENLIST_ROOT_PATH = "/"
OPENLIST_USERNAME = "navdata"
OPENLIST_PASSWORD = "navdata"
OPENLIST_TOKEN_CACHE = ""
APP_VERSION = os.getenv("FMS_APP_VERSION", "1.0.1").strip() or "1.0.1"
GITHUB_RELEASE_REPO = os.getenv("FMS_GITHUB_REPO", "jintao3652-cell/FMS-UPDATE-MANAGER").strip() or "jintao3652-cell/FMS-UPDATE-MANAGER"
GITHUB_RELEASE_LATEST_API = "https://api.github.com/repos/{repo}/releases/latest"
GITHUB_RELEASE_LIST_API = "https://api.github.com/repos/{repo}/releases?per_page=1"
GITHUB_TAG_LIST_API = "https://api.github.com/repos/{repo}/tags?per_page=1"
GITHUB_API_TOKEN = os.getenv("FMS_GITHUB_TOKEN", "").strip()
OPENLIST_ARCHIVE_NAME_HINTS: dict[str, tuple[str, ...]] = {
    "fnx-aircraft-320": ("fenix",),
    "pmdg-aircraft-736": ("pmdg", "wasm", "navdata"),
    "pmdg-aircraft-737": ("pmdg", "wasm", "navdata"),
    "pmdg-aircraft-738": ("pmdg", "wasm", "navdata"),
    "pmdg-aircraft-739": ("pmdg", "wasm", "navdata"),
    "pmdg-aircraft-77w": ("pmdg", "wasm", "navdata"),
    "pmdg-aircraft-77f": ("pmdg", "wasm", "navdata"),
    "pmdg-aircraft-77er": ("pmdg", "wasm", "navdata"),
    "pmdg-aircraft-77l": ("pmdg", "wasm", "navdata"),
    "tfdidesign-aircraft-md11": ("tfdi", "md11"),
    "fslabs-aircraft-a321": ("fslabs",),
    "justflight-aircraft-rj": ("justflight", "rj"),
    "fss-aircraft-e19x": ("fss", "erj"),
    "css-core": ("css",),
    "fycyc-aircraft-c919x": ("c919",),
    "ifly-aircraft-737max8": ("ifly", "max8"),
    "inibuilds-aircraft-a340": ("inibuilds",),
    "inibuilds-aircraft-a350": ("inibuilds",),
    "aerosoft-aircraft-a346-pro": ("toliss", "dfdv2"),
}
COMMON_ARCHIVE_SUFFIXES = (
    ".zip",
    ".7z",
    ".rar",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".tar.bz2",
    ".tbz",
    ".tbz2",
    ".tar.xz",
    ".txz",
    ".exe",
)
BATCH_DOWNLOAD_WORKER_OPTIONS: tuple[int, ...] = (1, 2, 4, 8)
DEFAULT_BATCH_DOWNLOAD_WORKERS = 4
CACHE_CLEANUP_DAY_OPTIONS: tuple[int, ...] = (1, 3, 7, 14, 30)
DEFAULT_CACHE_CLEANUP_DAYS = 7
MSFS_VERSIONS = ["MSFS 2024", "MSFS 2020"]
PLATFORMS = ["Xbox/MS Store", "Steam"]
THEME_LIGHT = "Light Mode"
THEME_DARK = "Dark Mode"
FONT_SCALE = 0.9
CYCLE_JSON_SCAN_CACHE: dict[tuple[str, ...], list[Path]] = {}
DEFAULT_SIM_PLATFORM_VARIANTS: list[tuple[str, str]] = [
    ("MSFS 2020", "Steam"),
    ("MSFS 2020", "Xbox/MS Store"),
    ("MSFS 2024", "Steam"),
    ("MSFS 2024", "Xbox/MS Store"),
]
DEFAULT_ADDON_FAMILIES: list[tuple[str, str, str, str]] = [
    ("Fenix A320", "Fenix A320 series", "fnx-aircraft-320", ""),
    ("PMDG 737-600", "PMDG 737 family", "pmdg-aircraft-736", ""),
    ("PMDG 737-700", "PMDG 737 family", "pmdg-aircraft-737", ""),
    ("PMDG 737-800", "PMDG 737 family", "pmdg-aircraft-738", ""),
    ("PMDG 737-900", "PMDG 737 family", "pmdg-aircraft-739", ""),
    ("PMDG 777-300ER", "PMDG 777 family", "pmdg-aircraft-77w", ""),
    ("PMDG 777F", "PMDG 777 family", "pmdg-aircraft-77f", ""),
    ("PMDG 777-200ER", "PMDG 777 family", "pmdg-aircraft-77er", ""),
    ("PMDG 777-200LR", "PMDG 777 family", "pmdg-aircraft-77l", ""),
    ("TFDi MD-11", "TFDi MD-11", "tfdidesign-aircraft-md11", ""),
    ("Flight Sim Labs 321", "Flight Sim Labs A321", "fslabs-aircraft-a321", ""),
    ("RJ Professional", "Just Flight RJ Professional", "justflight-aircraft-rj", ""),
    ("FSS ERJ", "FSS ERJ series", "fss-aircraft-e19x", ""),
    ("CSS 737CL", "CSS 737 Classic series", "css-core", ""),
    ("FYCYC C919", "FYCYC C919", "fycyc-aircraft-c919x", ""),
    ("iFly 737 MAX8", "iFly 737 MAX series", "ifly-aircraft-737max8", r"Data\navdata\Permanent"),
]


@dataclass
class Addon:
    name: str
    description: str
    simulator: str
    platform: str
    target_path: str = ""
    package_name: str = ""
    navdata_subpath: str = ""


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
    return max(8, int(round(size * FONT_SCALE)))


def get_colors(theme_name: str) -> dict[str, str]:
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


def normalize_github_repo(raw_repo: str) -> str:
    repo = str(raw_repo or "").strip().strip("/")
    parts = [part.strip() for part in repo.split("/") if part.strip()]
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return GITHUB_RELEASE_REPO


def github_api_json(url: str) -> tuple[int, Any]:
    headers = {
        "User-Agent": f"{APP_NAME}/{APP_VERSION}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_API_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_API_TOKEN}"
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=8) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
            return status, payload
    except HTTPError as exc:
        status = int(getattr(exc, "code", 0) or 0)
        try:
            payload = json.loads(exc.read().decode("utf-8", errors="ignore"))
        except Exception:
            payload = {"message": str(exc)}
        return status, payload
    except URLError as exc:
        reason = getattr(exc, "reason", None)
        return 0, {"message": str(reason or exc)}
    except TimeoutError as exc:
        return 0, {"message": str(exc)}
    except Exception as exc:
        return 0, {"message": str(exc)}


def fetch_latest_github_release_atom(repo: str) -> dict:
    normalized_repo = normalize_github_repo(repo)
    atom_url = f"https://github.com/{normalized_repo}/releases.atom"
    req = Request(
        atom_url,
        headers={
            "User-Agent": f"{APP_NAME}/{APP_VERSION}",
            "Accept": "application/atom+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(req, timeout=8) as resp:
        xml_text = resp.read().decode("utf-8", errors="ignore")
    root = ET.fromstring(xml_text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", ns)
    if entry is None:
        raise ValueError("github releases atom empty")

    title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
    link = ""
    for link_node in entry.findall("atom:link", ns):
        href = str(link_node.attrib.get("href", "")).strip()
        rel = str(link_node.attrib.get("rel", "alternate")).strip().lower()
        if href and rel in {"alternate", ""}:
            link = href
            break
    if not link:
        source_id = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
        if source_id.startswith("tag:github.com,2008:https://github.com/"):
            link = source_id.replace("tag:github.com,2008:", "", 1)

    tag_name = ""
    if "/releases/tag/" in link:
        tag_name = unquote(link.rsplit("/releases/tag/", 1)[-1].split("?", 1)[0].strip())
    if not tag_name:
        tag_name = title
    if not tag_name:
        raise ValueError("github releases atom has no tag")

    return {
        "tag_name": tag_name,
        "name": title or tag_name,
        "html_url": link or f"https://github.com/{normalized_repo}/releases",
        "_repo": normalized_repo,
    }


def fetch_latest_github_release(repo: str) -> dict:
    normalized_repo = normalize_github_repo(repo)
    latest_url = GITHUB_RELEASE_LATEST_API.format(repo=normalized_repo)
    status, payload = github_api_json(latest_url)
    if status == 200 and isinstance(payload, dict):
        payload.setdefault("tag_name", "")
        payload.setdefault("name", "")
        payload.setdefault("html_url", f"https://github.com/{normalized_repo}/releases/latest")
        payload["_repo"] = normalized_repo
        return payload

    # Some repositories have no published release. Fallback to release list.
    release_list_url = GITHUB_RELEASE_LIST_API.format(repo=normalized_repo)
    status, payload = github_api_json(release_list_url)
    if status == 200 and isinstance(payload, list) and payload:
        first = payload[0] if isinstance(payload[0], dict) else {}
        if isinstance(first, dict):
            first.setdefault("tag_name", "")
            first.setdefault("name", "")
            first.setdefault("html_url", f"https://github.com/{normalized_repo}/releases")
            first["_repo"] = normalized_repo
            return first

    # Final fallback: use latest tag as update source.
    tags_url = GITHUB_TAG_LIST_API.format(repo=normalized_repo)
    status, payload = github_api_json(tags_url)
    if status == 200 and isinstance(payload, list) and payload:
        first = payload[0] if isinstance(payload[0], dict) else {}
        tag_name = str(first.get("name", "")).strip() if isinstance(first, dict) else ""
        if tag_name:
            return {
                "tag_name": tag_name,
                "name": tag_name,
                "html_url": f"https://github.com/{normalized_repo}/tags",
                "_repo": normalized_repo,
            }

    # GitHub API may hit shared-IP rate limits. Fallback to public Atom feed.
    atom_error = ""
    try:
        return fetch_latest_github_release_atom(normalized_repo)
    except Exception as exc:
        atom_error = str(exc)

    message = payload.get("message", "github api unavailable") if isinstance(payload, dict) else "github api unavailable"
    if atom_error:
        raise ValueError(
            f"github releases not available for {normalized_repo}: {message}; atom fallback failed: {atom_error}"
        )
    raise ValueError(f"github releases not available for {normalized_repo}: {message}")


def load_cycle_json_payload(json_path: Path):
    try:
        return json.loads(json_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None


def extract_airac_from_value(value) -> str:
    if value is None:
        return "UNKNOWN"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    return detect_airac(str(value))


def read_cycle_from_payload(payload) -> str:
    if payload is None:
        return "UNKNOWN"
    if isinstance(payload, dict):
        for key in ("cycle_id", "cycle", "airac", "current_airac", "id"):
            cycle = extract_airac_from_value(payload.get(key))
            if cycle != "UNKNOWN":
                return cycle
        for value in payload.values():
            cycle = extract_airac_from_value(value)
            if cycle != "UNKNOWN":
                return cycle
    elif isinstance(payload, list):
        for item in payload:
            cycle = extract_airac_from_value(item)
            if cycle != "UNKNOWN":
                return cycle
    return "UNKNOWN"


def read_cycle_json(json_path: Path) -> str:
    payload = load_cycle_json_payload(json_path)
    return read_cycle_from_payload(payload)


def read_cycle_json_name(json_path: Path) -> str:
    payload = load_cycle_json_payload(json_path)
    if isinstance(payload, dict):
        return str(payload.get("name", "")).strip()
    return ""


def is_a346_addon(addon: Addon) -> bool:
    package_name = addon.package_name.strip().lower()
    addon_name = addon.name.strip().lower()
    return package_name == "aerosoft-aircraft-a346-pro" or "a340-600" in addon_name


def normalize_zip_member(member_name: str) -> str:
    return member_name.replace("\\", "/").lstrip("/").strip()


def inspect_zip_cycle_payload(zip_path: Path) -> dict | None:
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            members: list[str] = []
            for info in zip_ref.infolist():
                if info.is_dir():
                    continue
                member = normalize_zip_member(info.filename)
                if member:
                    members.append(member)

            cycle_json_members = [m for m in members if Path(m).name.lower() == "cycle.json"]
            if not cycle_json_members:
                return None

            scored: list[tuple[int, int, str, str]] = []
            for member in cycle_json_members:
                parent = member.rsplit("/", 1)[0] if "/" in member else ""
                prefix = f"{parent}/" if parent else ""
                useful_entries = sum(
                    1
                    for entry in members
                    if (entry.startswith(prefix) if prefix else True) and Path(entry).name.lower() != "cycle.json"
                )
                depth = parent.count("/") + (1 if parent else 0)
                scored.append((useful_entries, -depth, member, parent))
            scored.sort(reverse=True)
            cycle_json_member = scored[0][2]
            payload_prefix = scored[0][3]

            payload = None
            try:
                payload = json.loads(zip_ref.read(cycle_json_member).decode("utf-8", errors="ignore"))
            except Exception:
                payload = None

            cycle_name = str(payload.get("name", "")).strip() if isinstance(payload, dict) else ""
            airac = read_cycle_from_payload(payload)
            return {
                "cycle_json_member": cycle_json_member,
                "payload_prefix": payload_prefix,
                "cycle_name": cycle_name,
                "airac": airac,
            }
    except (OSError, zipfile.BadZipFile):
        return None


def extract_zip_payload_to_target(
    addon: Addon,
    zip_path: Path,
    install_base: Path,
    payload_prefix: str,
    airac: str,
) -> tuple[int, Path]:
    normalized_prefix = normalize_zip_member(payload_prefix).rstrip("/")
    prefix_with_sep = f"{normalized_prefix}/" if normalized_prefix else ""

    if is_a346_addon(addon):
        if airac == "UNKNOWN":
            raise ValueError("A346 package cycle is missing in cycle.json.")
        install_root = install_base / f"cycle_{airac}"
    else:
        install_root = install_base
    install_root.mkdir(parents=True, exist_ok=True)

    extracted_files = 0
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        for info in zip_ref.infolist():
            if info.is_dir():
                continue
            member = normalize_zip_member(info.filename)
            if not member:
                continue
            if prefix_with_sep:
                if not member.startswith(prefix_with_sep):
                    continue
                relative_name = member[len(prefix_with_sep) :]
            else:
                relative_name = member
            if not relative_name:
                continue
            relative_path = Path(relative_name)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                continue

            dst = install_root / relative_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            with zip_ref.open(info, "r") as src, dst.open("wb") as out:
                shutil.copyfileobj(src, out)
            extracted_files += 1
    return extracted_files, install_root


def is_supported_archive_file(archive_path: Path) -> bool:
    name = archive_path.name.lower()
    return any(name.endswith(suffix) for suffix in COMMON_ARCHIVE_SUFFIXES)


def _archive_kind(archive_path: Path) -> str:
    name = archive_path.name.lower()
    if name.endswith(".zip"):
        return "zip"
    if name.endswith(".exe"):
        return "sfx_exe"
    if name.endswith(".7z"):
        return "7z"
    if name.endswith(".rar"):
        return "rar"
    if any(
        name.endswith(suffix)
        for suffix in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz", ".tbz2", ".tar.xz", ".txz")
    ):
        return "tar"
    return ""


def _resolve_tool_path(candidates: list[str], extra_paths: list[Path] | None = None) -> str | None:
    for name in candidates:
        found = shutil.which(name)
        if found:
            return found
    if extra_paths:
        for p in extra_paths:
            if p.exists() and p.is_file():
                return str(p)
    return None


def _runtime_tool_dirs() -> list[Path]:
    dirs: list[Path] = [Path.cwd(), LOCAL_DIR]
    try:
        base_dir = Path(__file__).resolve().parent
        dirs.append(base_dir)
        dirs.append(base_dir / "tools")
    except Exception:
        pass
    if getattr(sys, "frozen", False):
        try:
            exe_dir = Path(sys.executable).resolve().parent
            dirs.append(exe_dir)
            dirs.append(exe_dir / "tools")
        except Exception:
            pass
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        try:
            mp = Path(str(meipass))
            dirs.append(mp)
            dirs.append(mp / "tools")
        except Exception:
            pass
    dedup: list[Path] = []
    seen: set[str] = set()
    for d in dirs:
        key = str(d).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        dedup.append(d)
    return dedup


def _runtime_executable_paths(file_names: list[str]) -> list[Path]:
    paths: list[Path] = []
    for d in _runtime_tool_dirs():
        for n in file_names:
            paths.append(d / n)
    return paths


def _find_7z_executable() -> str | None:
    pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    pf86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    runtime_paths = _runtime_executable_paths(["7zz.exe", "7z.exe", "7za.exe", "7zr.exe"])
    return _resolve_tool_path(
        candidates=["7zz", "7z", "7za", "7zr", "7zz.exe", "7z.exe", "7za.exe", "7zr.exe"],
        extra_paths=[
            pf / "7-Zip" / "7zz.exe",
            pf / "7-Zip" / "7z.exe",
            pf / "7-Zip" / "7za.exe",
            pf / "7-Zip" / "7zr.exe",
            pf86 / "7-Zip" / "7zz.exe",
            pf86 / "7-Zip" / "7z.exe",
            pf86 / "7-Zip" / "7za.exe",
            pf86 / "7-Zip" / "7zr.exe",
        ]
        + runtime_paths,
    )


def _find_rar_capable_7z_executable() -> str | None:
    pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    pf86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    runtime_paths = _runtime_executable_paths(["7zz.exe", "7z.exe"])
    return _resolve_tool_path(
        candidates=["7zz", "7z", "7zz.exe", "7z.exe"],
        extra_paths=[
            pf / "7-Zip" / "7zz.exe",
            pf / "7-Zip" / "7z.exe",
            pf86 / "7-Zip" / "7zz.exe",
            pf86 / "7-Zip" / "7z.exe",
        ]
        + runtime_paths,
    )


def _find_unrar_executable() -> str | None:
    pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    pf86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    runtime_paths = _runtime_executable_paths(["UnRAR.exe", "unrar.exe"])
    return _resolve_tool_path(
        candidates=["unrar", "unrar.exe", "UnRAR.exe"],
        extra_paths=[
            pf / "WinRAR" / "UnRAR.exe",
            pf / "WinRAR" / "unrar.exe",
            pf86 / "WinRAR" / "UnRAR.exe",
            pf86 / "WinRAR" / "unrar.exe",
        ]
        + runtime_paths,
    )


def _friendly_rar_extract_error(rar_errors: list[str]) -> str:
    joined = " | ".join(rar_errors)
    if "7za.exe does not support RAR extraction" in joined:
        return (
            "RAR 解压失败：检测到仅有 7za.exe。"
            "7za 不支持 RAR，请改用 7z.exe/7zz.exe 或 UnRAR.exe。"
        )
    if "Declared dictionary size is not supported" in joined:
        return (
            "RAR 解压失败：当前压缩包使用了较大的字典参数，Windows 系统解压器不支持。"
            "请将 7zz.exe/7z.exe 或 UnRAR.exe 放到程序目录后重试；"
            "也可先手动解压并改用 ZIP。"
        )
    if "No module named 'rarfile'" in joined and (
        "7z/7za not found" in joined or "requires WinRAR UnRAR.exe or 7-Zip" in joined
    ):
        return (
            "RAR 解压失败：当前环境缺少可用解压后端。"
            "建议先安装 Python 库 rarfile；若仍失败，请安装 7-Zip 或 WinRAR，"
            "或将 7z.exe/UnRAR.exe 放到程序目录后重试。"
        )
    return "RAR extraction failed: " + joined


def _pe_overlay_offset(exe_path: Path) -> int:
    try:
        with exe_path.open("rb") as f:
            mz = f.read(2)
            if mz != b"MZ":
                return 0
            f.seek(0x3C)
            raw = f.read(4)
            if len(raw) != 4:
                return 0
            pe_offset = struct.unpack("<I", raw)[0]
            f.seek(pe_offset)
            if f.read(4) != b"PE\x00\x00":
                return 0
            coff = f.read(20)
            if len(coff) != 20:
                return 0
            number_of_sections = struct.unpack("<H", coff[2:4])[0]
            optional_header_size = struct.unpack("<H", coff[16:18])[0]
            section_table_offset = pe_offset + 24 + optional_header_size
            f.seek(section_table_offset)
            max_end = 0
            for _ in range(number_of_sections):
                sh = f.read(40)
                if len(sh) != 40:
                    break
                size_of_raw_data = struct.unpack("<I", sh[16:20])[0]
                ptr_to_raw_data = struct.unpack("<I", sh[20:24])[0]
                section_end = ptr_to_raw_data + size_of_raw_data
                if section_end > max_end:
                    max_end = section_end
            return max(0, max_end)
    except Exception:
        return 0


def _detect_embedded_archive_in_sfx_exe(exe_path: Path) -> tuple[str, int] | None:
    try:
        data = exe_path.read_bytes()
    except Exception:
        return None
    if not data:
        return None

    start = _pe_overlay_offset(exe_path)
    if start <= 0 or start >= len(data):
        start = 0

    signatures: list[tuple[str, bytes]] = [
        ("7z", b"7z\xBC\xAF\x27\x1C"),
        ("rar", b"Rar!\x1A\x07\x01\x00"),
        ("rar", b"Rar!\x1A\x07\x00"),
        ("zip", b"PK\x03\x04"),
    ]

    candidates: list[tuple[int, str]] = []
    for kind, sig in signatures:
        idx = data.find(sig, start)
        if idx >= 0:
            candidates.append((idx, kind))
    if not candidates:
        return None

    candidates.sort(key=lambda t: t[0])
    for idx, kind in candidates:
        if kind == "zip":
            try:
                with zipfile.ZipFile(io.BytesIO(data[idx:]), "r") as zf:
                    if zf.infolist():
                        return kind, idx
            except Exception:
                continue
        else:
            return kind, idx
    return None


def _extract_sfx_exe_overlay_to_temp(
    exe_path: Path,
    temp_dir: Path,
    progress_callback: Callable[[str], None] | None = None,
) -> None:
    detected = _detect_embedded_archive_in_sfx_exe(exe_path)
    if not detected:
        raise ValueError(
            "未在 EXE 中识别到可用压缩数据（ZIP/7z/RAR）。"
            "请确认该文件是导航数据自解压包，或改用原始压缩包。"
        )
    embedded_kind, offset = detected
    if progress_callback is not None:
        progress_callback(f"检测到 EXE 内嵌压缩包格式: {embedded_kind}")
    ext_map = {"zip": ".zip", "7z": ".7z", "rar": ".rar"}
    payload_path = temp_dir / f"_embedded_payload{ext_map.get(embedded_kind, '.bin')}"
    with exe_path.open("rb") as src, payload_path.open("wb") as dst:
        src.seek(offset)
        shutil.copyfileobj(src, dst)

    try:
        if embedded_kind == "zip":
            with zipfile.ZipFile(payload_path, "r") as zf:
                zf.extractall(temp_dir)
        elif embedded_kind == "7z":
            sevenz_errors: list[str] = []
            try:
                _extract_with_7z_command(payload_path, temp_dir, progress_callback=progress_callback)
            except Exception as cmd_exc:
                sevenz_errors.append(f"7z command: {cmd_exc}")
                try:
                    import py7zr  # type: ignore  # pylint: disable=import-error,import-outside-toplevel

                    with py7zr.SevenZipFile(payload_path, "r") as zf:
                        zf.extractall(path=temp_dir)
                except Exception as lib_exc:
                    sevenz_errors.append(f"py7zr: {lib_exc}")
                    try:
                        _extract_with_system_tar_command(payload_path, temp_dir)
                    except Exception as sys_exc:
                        sevenz_errors.append(f"system tar: {sys_exc}")
                        raise RuntimeError("7z extraction failed: " + " | ".join(sevenz_errors)) from sys_exc
        elif embedded_kind == "rar":
            rar_errors: list[str] = []
            try:
                _extract_with_unrar_command(payload_path, temp_dir, progress_callback=progress_callback)
            except Exception as cmd_exc:
                rar_errors.append(f"unrar/7z command: {cmd_exc}")
                try:
                    import rarfile  # type: ignore  # pylint: disable=import-error,import-outside-toplevel

                    with rarfile.RarFile(payload_path) as rf:
                        rf.extractall(path=temp_dir)
                except Exception as lib_exc:
                    rar_errors.append(f"rarfile: {lib_exc}")
                    try:
                        _extract_with_system_tar_command(payload_path, temp_dir)
                    except Exception as sys_exc:
                        rar_errors.append(f"system tar: {sys_exc}")
                        raise RuntimeError(_friendly_rar_extract_error(rar_errors)) from sys_exc
        else:
            raise ValueError(f"Unsupported embedded kind: {embedded_kind}")
    finally:
        try:
            payload_path.unlink(missing_ok=True)
        except Exception:
            pass


def _find_system_tar_executable() -> str | None:
    exe = shutil.which("tar")
    if exe:
        return exe
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    candidate = system_root / "System32" / "tar.exe"
    if candidate.exists() and candidate.is_file():
        return str(candidate)
    return None


def _run_hidden_subprocess(command: list[str]) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "shell": False,
    }
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(command, **kwargs)


def _run_hidden_subprocess_with_live_output(
    command: list[str],
    on_output: Callable[[str], None] | None = None,
) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "shell": False,
        "bufsize": 1,
    }
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    proc = subprocess.Popen(command, **kwargs)
    output_parts: list[str] = []
    pending_chars: list[str] = []

    def flush_pending() -> None:
        if not pending_chars:
            return
        line = "".join(pending_chars).strip()
        pending_chars.clear()
        if line and on_output is not None:
            on_output(line)

    try:
        if proc.stdout is not None:
            while True:
                ch = proc.stdout.read(1)
                if ch == "":
                    if proc.poll() is not None:
                        break
                    continue
                output_parts.append(ch)
                if ch in ("\r", "\n"):
                    flush_pending()
                else:
                    pending_chars.append(ch)
        flush_pending()
    finally:
        returncode = proc.wait()
    return subprocess.CompletedProcess(command, returncode, "".join(output_parts), "")


def _run_7z_with_live_output(
    command: list[str],
    on_output: Callable[[str], None] | None = None,
) -> subprocess.CompletedProcess[str]:
    return _run_hidden_subprocess_with_live_output(command, on_output=on_output)


def _extract_with_system_tar_command(archive_path: Path, temp_dir: Path) -> None:
    exe = _find_system_tar_executable()
    if not exe:
        raise ValueError("system tar.exe not found.")
    result = _run_hidden_subprocess([exe, "-xf", str(archive_path), "-C", str(temp_dir)])
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"system tar extract failed ({result.returncode}): {err}")


def _extract_with_7z_command(
    archive_path: Path,
    temp_dir: Path,
    *,
    require_rar_support: bool = False,
    progress_callback: Callable[[str], None] | None = None,
) -> None:
    exe = _find_rar_capable_7z_executable() if require_rar_support else _find_7z_executable()
    if not exe:
        if require_rar_support:
            raise ValueError("RAR requires 7z.exe/7zz.exe or UnRAR.exe; 7za.exe is not enough.")
        raise ValueError("7z/7za not found. Install py7zr or 7-Zip, or convert archive to ZIP/TAR.")
    if require_rar_support and Path(exe).name.strip().lower() == "7za.exe":
        raise ValueError("7za.exe does not support RAR extraction.")
    if progress_callback is not None:
        progress_callback(f"7z 开始解压: {archive_path.name}")
    result = _run_7z_with_live_output(
        [exe, "x", "-y", "-bsp1", "-bso1", "-bse1", f"-o{temp_dir}", str(archive_path)],
        on_output=progress_callback,
    )
    if result.returncode != 0:
        tail = "\n".join([line for line in result.stdout.splitlines() if line.strip()][-8:])
        detail = f"\n{tail}" if tail else ""
        raise RuntimeError(f"7z extract failed ({result.returncode}).{detail}")
    if progress_callback is not None:
        progress_callback(f"7z 解压完成: {archive_path.name}")


def _extract_with_unrar_command(
    archive_path: Path,
    temp_dir: Path,
    progress_callback: Callable[[str], None] | None = None,
) -> None:
    # Prefer 7z for consistent RAR behavior first.
    try:
        _extract_with_7z_command(
            archive_path,
            temp_dir,
            require_rar_support=True,
            progress_callback=progress_callback,
        )
        return
    except Exception as sevenz_exc:
        sevenz_error = sevenz_exc

    exe = _find_unrar_executable()
    if not exe:
        raise ValueError(
            "RAR extraction requires rarfile backend or external WinRAR UnRAR.exe/7-Zip (7z.exe). "
            "Please install one of them or convert to ZIP/TAR."
        ) from sevenz_error
    if progress_callback is not None:
        progress_callback(f"UnRAR 开始解压: {archive_path.name}")
    result = _run_hidden_subprocess([exe, "x", "-y", "-o+", str(archive_path), str(temp_dir)])
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"unrar extract failed ({result.returncode}): {err}")
    if progress_callback is not None:
        progress_callback(f"UnRAR 解压完成: {archive_path.name}")


def _write_archive_member_to_temp(temp_dir: Path, member_name: str, src_stream: Any) -> bool:
    normalized_name = normalize_zip_member(member_name)
    if not normalized_name:
        return False
    relative_path = Path(normalized_name)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return False
    dst = temp_dir / relative_path
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("wb") as out:
        shutil.copyfileobj(src_stream, out)
    return True


def _extract_cycle_json_only_with_7z_command(
    archive_path: Path,
    temp_dir: Path,
    *,
    require_rar_support: bool = False,
    progress_callback: Callable[[str], None] | None = None,
) -> None:
    exe = _find_rar_capable_7z_executable() if require_rar_support else _find_7z_executable()
    if not exe:
        if require_rar_support:
            raise ValueError("RAR requires 7z.exe/7zz.exe or UnRAR.exe; 7za.exe is not enough.")
        raise ValueError("7z/7za not found. Install py7zr or 7-Zip, or convert archive to ZIP/TAR.")
    if require_rar_support and Path(exe).name.strip().lower() == "7za.exe":
        raise ValueError("7za.exe does not support RAR extraction.")
    if progress_callback is not None:
        progress_callback(f"7z 开始提取 cycle.json: {archive_path.name}")
    result = _run_7z_with_live_output(
        [
            exe,
            "x",
            "-y",
            "-bsp1",
            "-bso1",
            "-bse1",
            f"-o{temp_dir}",
            str(archive_path),
            "-r",
            "-ir!cycle.json",
        ],
        on_output=progress_callback,
    )
    if result.returncode != 0:
        tail = "\n".join([line for line in result.stdout.splitlines() if line.strip()][-8:])
        detail = f"\n{tail}" if tail else ""
        raise RuntimeError(f"7z cycle.json extract failed ({result.returncode}).{detail}")
    if progress_callback is not None:
        progress_callback(f"7z cycle.json 提取完成: {archive_path.name}")


def _extract_cycle_jsons_to_temp_by_kind(
    archive_path: Path,
    temp_dir: Path,
    *,
    kind: str,
    progress_callback: Callable[[str], None] | None = None,
) -> None:
    if kind == "zip":
        if progress_callback is not None:
            progress_callback(f"ZIP 提取 cycle.json: {archive_path.name}")
        with zipfile.ZipFile(archive_path, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                member = normalize_zip_member(info.filename)
                if Path(member).name.lower() != "cycle.json":
                    continue
                with zf.open(info, "r") as src:
                    _write_archive_member_to_temp(temp_dir, member, src)
        return

    if kind == "tar":
        if progress_callback is not None:
            progress_callback(f"TAR 提取 cycle.json: {archive_path.name}")
        with tarfile.open(archive_path, "r:*") as tf:
            for member in tf.getmembers():
                if not member.isfile():
                    continue
                member_name = normalize_zip_member(member.name)
                if Path(member_name).name.lower() != "cycle.json":
                    continue
                src = tf.extractfile(member)
                if src is None:
                    continue
                with src:
                    _write_archive_member_to_temp(temp_dir, member_name, src)
        return

    if kind == "7z":
        sevenz_errors: list[str] = []
        try:
            _extract_cycle_json_only_with_7z_command(
                archive_path,
                temp_dir,
                progress_callback=progress_callback,
            )
            return
        except Exception as cmd_exc:
            sevenz_errors.append(f"7z command: {cmd_exc}")
        try:
            import py7zr  # type: ignore  # pylint: disable=import-error,import-outside-toplevel

            with py7zr.SevenZipFile(archive_path, "r") as zf:
                cycle_targets = [
                    name
                    for name in zf.getnames()
                    if Path(normalize_zip_member(name)).name.lower() == "cycle.json"
                ]
                if cycle_targets:
                    zf.extract(path=temp_dir, targets=cycle_targets)
            return
        except Exception as lib_exc:
            sevenz_errors.append(f"py7zr: {lib_exc}")
            raise RuntimeError("7z cycle.json extraction failed: " + " | ".join(sevenz_errors)) from lib_exc

    if kind == "rar":
        rar_errors: list[str] = []
        try:
            _extract_cycle_json_only_with_7z_command(
                archive_path,
                temp_dir,
                require_rar_support=True,
                progress_callback=progress_callback,
            )
            return
        except Exception as cmd_exc:
            rar_errors.append(f"unrar/7z command: {cmd_exc}")
        try:
            import rarfile  # type: ignore  # pylint: disable=import-error,import-outside-toplevel

            with rarfile.RarFile(archive_path) as rf:
                for info in rf.infolist():
                    if info.isdir():
                        continue
                    member_name = normalize_zip_member(info.filename)
                    if Path(member_name).name.lower() != "cycle.json":
                        continue
                    with rf.open(info) as src:
                        _write_archive_member_to_temp(temp_dir, member_name, src)
            return
        except Exception as lib_exc:
            rar_errors.append(f"rarfile: {lib_exc}")
            raise RuntimeError(_friendly_rar_extract_error(rar_errors)) from lib_exc

    if kind == "sfx_exe":
        detected = _detect_embedded_archive_in_sfx_exe(archive_path)
        if not detected:
            raise ValueError(
                "未在 EXE 中识别到可用压缩数据（ZIP/7z/RAR）。"
                "请确认该文件是导航数据自解压包，或改用原始压缩包。"
            )
        embedded_kind, offset = detected
        if progress_callback is not None:
            progress_callback(f"检测到 EXE 内嵌压缩包格式: {embedded_kind}")
        ext_map = {"zip": ".zip", "7z": ".7z", "rar": ".rar"}
        payload_path = temp_dir / f"_embedded_payload{ext_map.get(embedded_kind, '.bin')}"
        with archive_path.open("rb") as src, payload_path.open("wb") as dst:
            src.seek(offset)
            shutil.copyfileobj(src, dst)
        try:
            _extract_cycle_jsons_to_temp_by_kind(
                payload_path,
                temp_dir,
                kind=embedded_kind,
                progress_callback=progress_callback,
            )
        finally:
            try:
                payload_path.unlink(missing_ok=True)
            except Exception:
                pass
        return

    raise ValueError(f"Unsupported archive format: {archive_path.name}")


def extract_archive_cycle_json_to_temp(
    archive_path: Path,
    progress_callback: Callable[[str], None] | None = None,
) -> Path:
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix="fms_cycle_probe_", dir=str(LOCAL_DIR)))
    kind = _archive_kind(archive_path)
    if not kind:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise ValueError(f"Unsupported archive format: {archive_path.name}")
    try:
        if progress_callback is not None:
            progress_callback(f"检测到压缩格式: {kind}")
        _extract_cycle_jsons_to_temp_by_kind(
            archive_path,
            temp_dir,
            kind=kind,
            progress_callback=progress_callback,
        )
        return temp_dir
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def extract_archive_to_temp(
    archive_path: Path,
    progress_callback: Callable[[str], None] | None = None,
) -> Path:
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix="fms_archive_", dir=str(LOCAL_DIR)))
    kind = _archive_kind(archive_path)
    if not kind:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise ValueError(f"Unsupported archive format: {archive_path.name}")
    if progress_callback is not None:
        progress_callback(f"检测到压缩格式: {kind}")

    try:
        if kind == "zip":
            zip_errors: list[str] = []
            try:
                if progress_callback is not None:
                    progress_callback(f"ZIP 开始解压: {archive_path.name}")
                with zipfile.ZipFile(archive_path, "r") as zf:
                    zf.extractall(temp_dir)
                if progress_callback is not None:
                    progress_callback(f"ZIP 解压完成: {archive_path.name}")
            except Exception as exc:
                zip_errors.append(f"python zipfile: {exc}")
                try:
                    _extract_with_system_tar_command(archive_path, temp_dir)
                except Exception as sys_exc:
                    zip_errors.append(f"system tar: {sys_exc}")
                    raise RuntimeError("ZIP extraction failed: " + " | ".join(zip_errors)) from sys_exc
        elif kind == "tar":
            tar_errors: list[str] = []
            try:
                if progress_callback is not None:
                    progress_callback(f"TAR 开始解压: {archive_path.name}")
                shutil.unpack_archive(str(archive_path), str(temp_dir))
                if progress_callback is not None:
                    progress_callback(f"TAR 解压完成: {archive_path.name}")
            except Exception as exc:
                tar_errors.append(f"python unpack_archive: {exc}")
                try:
                    _extract_with_system_tar_command(archive_path, temp_dir)
                except Exception as sys_exc:
                    tar_errors.append(f"system tar: {sys_exc}")
                    raise RuntimeError("TAR extraction failed: " + " | ".join(tar_errors)) from sys_exc
        elif kind == "7z":
            sevenz_errors: list[str] = []
            try:
                _extract_with_7z_command(archive_path, temp_dir, progress_callback=progress_callback)
            except Exception as cmd_exc:
                sevenz_errors.append(f"7z command: {cmd_exc}")
                try:
                    import py7zr  # type: ignore  # pylint: disable=import-error,import-outside-toplevel

                    with py7zr.SevenZipFile(archive_path, "r") as zf:
                        zf.extractall(path=temp_dir)
                except Exception as lib_exc:
                    sevenz_errors.append(f"py7zr: {lib_exc}")
                    try:
                        _extract_with_system_tar_command(archive_path, temp_dir)
                    except Exception as sys_exc:
                        sevenz_errors.append(f"system tar: {sys_exc}")
                        raise RuntimeError("7z extraction failed: " + " | ".join(sevenz_errors)) from sys_exc
        elif kind == "rar":
            rar_errors: list[str] = []
            try:
                _extract_with_unrar_command(archive_path, temp_dir, progress_callback=progress_callback)
            except Exception as cmd_exc:
                rar_errors.append(f"unrar/7z command: {cmd_exc}")
                try:
                    import rarfile  # type: ignore  # pylint: disable=import-error,import-outside-toplevel

                    with rarfile.RarFile(archive_path) as rf:
                        rf.extractall(path=temp_dir)
                except Exception as lib_exc:
                    rar_errors.append(f"rarfile: {lib_exc}")
                    try:
                        _extract_with_system_tar_command(archive_path, temp_dir)
                    except Exception as sys_exc:
                        rar_errors.append(f"system tar: {sys_exc}")
                        raise RuntimeError(_friendly_rar_extract_error(rar_errors)) from sys_exc
        elif kind == "sfx_exe":
            _extract_sfx_exe_overlay_to_temp(archive_path, temp_dir, progress_callback=progress_callback)
        else:
            raise ValueError(f"Unsupported archive format: {archive_path.name}")
        return temp_dir
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def inspect_extracted_cycle_payload(extracted_root: Path) -> dict | None:
    try:
        candidates: list[tuple[int, int, Path, Path]] = []
        for cycle_json in extracted_root.rglob("cycle.json"):
            parent = cycle_json.parent
            try:
                depth = len(parent.relative_to(extracted_root).parts)
            except ValueError:
                depth = 999
            try:
                entries = list(parent.iterdir())
            except Exception:
                entries = []
            useful_entries = sum(1 for entry in entries if entry.name.lower() != "cycle.json")
            candidates.append((useful_entries, -depth, cycle_json, parent))
        if not candidates:
            return None
        candidates.sort(reverse=True)
        cycle_json_path = candidates[0][2]
        payload_dir = candidates[0][3]
        payload = load_cycle_json_payload(cycle_json_path)
        cycle_name = str(payload.get("name", "")).strip() if isinstance(payload, dict) else ""
        airac = read_cycle_from_payload(payload)
        return {
            "cycle_json_path": str(cycle_json_path),
            "payload_dir": str(payload_dir),
            "cycle_name": cycle_name,
            "airac": airac,
        }
    except Exception:
        return None


def copy_payload_dir_to_target(
    addon: Addon,
    payload_dir: Path,
    install_base: Path,
    airac: str,
) -> tuple[int, Path]:
    if is_a346_addon(addon):
        if airac == "UNKNOWN":
            raise ValueError("A346 package cycle is missing in cycle.json.")
        install_root = install_base / f"cycle_{airac}"
    else:
        install_root = install_base
    install_root.mkdir(parents=True, exist_ok=True)

    copied_files = 0

    def copy_with_count(src, dst, *, follow_symlinks=True):
        nonlocal copied_files
        result = shutil.copy2(src, dst, follow_symlinks=follow_symlinks)
        copied_files += 1
        return result

    for child in payload_dir.iterdir():
        dst = install_root / child.name
        if child.is_dir():
            shutil.copytree(child, dst, dirs_exist_ok=True, copy_function=copy_with_count)
        else:
            copy_with_count(child, dst)
    return copied_files, install_root


def cleanup_temp_dir(path: Path | None) -> None:
    if path is None:
        return
    shutil.rmtree(path, ignore_errors=True)


def prepare_archive_payload(
    archive_path: Path,
    progress_callback: Callable[[str], None] | None = None,
) -> dict | None:
    if progress_callback is not None:
        progress_callback(f"开始解析压缩包: {archive_path.name}")
    kind = _archive_kind(archive_path)
    if kind == "zip":
        if progress_callback is not None:
            progress_callback("检测到压缩格式: zip")
            progress_callback("正在读取 ZIP 内 cycle.json...")
        payload = inspect_zip_cycle_payload(archive_path)
        if not payload:
            if progress_callback is not None:
                progress_callback("未找到有效 cycle.json")
            return None
        payload["probe_root"] = ""
        payload["payload_prefix"] = str(payload.get("payload_prefix", "")).strip()
        if progress_callback is not None:
            progress_callback(
                f"解析成功: AIRAC {payload.get('airac', 'UNKNOWN')}, payload={payload.get('payload_prefix', '')}"
            )
        return payload

    probe_root = extract_archive_cycle_json_to_temp(archive_path, progress_callback=progress_callback)
    if progress_callback is not None:
        progress_callback("正在定位 cycle.json...")
    payload = inspect_extracted_cycle_payload(probe_root)
    if not payload:
        if progress_callback is not None:
            progress_callback("未找到有效 cycle.json")
        cleanup_temp_dir(probe_root)
        return None
    payload_dir = Path(str(payload.get("payload_dir", "")).strip())
    payload_prefix = ""
    if payload_dir:
        try:
            payload_prefix = str(payload_dir.relative_to(probe_root)).replace("\\", "/")
        except Exception:
            payload_prefix = ""
    if progress_callback is not None:
        progress_callback(
            f"解析成功: AIRAC {payload.get('airac', 'UNKNOWN')}, payload={payload.get('payload_dir', '')}"
        )
    payload["probe_root"] = str(probe_root)
    payload["payload_prefix"] = payload_prefix
    return payload


def find_nested_cycle_dir(folder: Path | None, addon: Addon | None = None, max_depth: int = 4) -> Path | None:
    if folder is None or not folder.exists() or not folder.is_dir():
        return None
    try:
        base_depth = len(folder.parts)
        matches: list[tuple[int, int, Path]] = []
        for cycle_json in folder.rglob("cycle.json"):
            candidate = cycle_json.parent
            if len(candidate.parts) - base_depth > max_depth:
                continue
            if addon is not None and not path_matches_addon_signature(addon, candidate, cycle_json):
                continue
            cycle = read_cycle_json(cycle_json)
            if cycle == "UNKNOWN":
                cycle = read_cycle_from_dir(candidate)
            if cycle == "UNKNOWN":
                continue
            score = int(cycle) if cycle.isdigit() else -1
            matches.append((score, -len(candidate.parts), candidate))
        if not matches:
            return None
        matches.sort(reverse=True)
        return matches[0][2]
    except Exception:
        return None


def read_cycle_from_dir(folder: Path | None) -> str:
    if not folder:
        return "UNKNOWN"

    cycle_json = folder / "cycle.json"
    if cycle_json.exists():
        cycle = read_cycle_json(cycle_json)
        if cycle != "UNKNOWN":
            return cycle

    info_txt = folder / "cycle_info.txt"
    if info_txt.exists():
        try:
            cycle = detect_airac(info_txt.read_text(encoding="utf-8", errors="ignore"))
            if cycle != "UNKNOWN":
                return cycle
        except Exception:
            pass

    marker = folder / "airac.txt"
    if marker.exists():
        try:
            cycle = detect_airac(marker.read_text(encoding="utf-8", errors="ignore"))
            if cycle != "UNKNOWN":
                return cycle
        except Exception:
            pass

    cycle_from_name = detect_airac(folder.name)
    if cycle_from_name != "UNKNOWN":
        return cycle_from_name

    child_cycles: list[str] = []
    try:
        for child in folder.iterdir():
            if not child.is_dir():
                continue
            if not re.fullmatch(r"cycle[_-]?[0-9]{4}", child.name, re.IGNORECASE):
                continue
            child_cycle = detect_airac(child.name)
            if child_cycle == "UNKNOWN":
                child_cycle = read_cycle_from_dir(child)
            if child_cycle != "UNKNOWN":
                child_cycles.append(child_cycle)
    except Exception:
        return "UNKNOWN"

    if child_cycles:
        return sorted(child_cycles, key=lambda c: int(c) if c.isdigit() else -1, reverse=True)[0]
    return "UNKNOWN"


def fetch_current_cycle() -> dict | None:
    req = Request(CYCLES_API_URL, headers={"User-Agent": "FMS-Update-Manager-Flet"})
    with urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("value") or payload.get("cycles") or payload.get("data") or []
    else:
        rows = []
    if not isinstance(rows, list):
        return None

    current_rows = [r for r in rows if isinstance(r, dict) and str(r.get("cycle_status", "")).lower() == "current"]
    if not current_rows:
        return None

    current_rows.sort(
        key=lambda r: parse_iso_utc(str(r.get("cycle_start_date", "1970-01-01T00:00:00Z"))),
        reverse=True,
    )
    current = current_rows[0]
    cycle_id = detect_airac(str(current.get("cycle_id", "UNKNOWN")))
    start_dt = parse_iso_utc(str(current.get("cycle_start_date", "1970-01-01T00:00:00Z")))
    # Keep behavior consistent with main.py: AIRAC cycles are treated as 28 days.
    end_dt = start_dt + timedelta(days=28)
    return {
        "cycle_id": cycle_id,
        "start": start_dt,
        "end": end_dt,
    }


def backup_power_login_request(api_url: str, username: str, password: str) -> dict:
    payload = {
        "username": username,
        "password": password,
        "client": APP_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    raw = ""
    status = 0
    for attempt in range(2):
        req = Request(
            api_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "FMS-Update-Manager-Flet",
                "Connection": "close",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=6) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
                status = int(getattr(resp, "status", 200) or 200)
            break
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            if exc.code in {502, 503, 504} and attempt < 1:
                time.sleep(0.6 * (attempt + 1))
                continue
            try:
                detail_payload = json.loads(raw)
                detail = str(detail_payload.get("message") or detail_payload.get("detail") or raw).strip()
            except Exception:
                detail = raw.strip() or str(exc)
            if exc.code == 401:
                lowered = detail.lower()
                if "invalid credentials" in lowered or "invalid credential" in lowered:
                    detail = "账号或密码错误（此处为 DATA 域名登录，不支持 OpenList 账号）"
                elif not detail:
                    detail = "账号或密码错误（此处为 DATA 域名登录）"
                raise ValueError(f"接口返回错误 ({exc.code}): {detail}") from exc
            raise ValueError(f"接口返回错误 ({exc.code}): {detail}") from exc
        except URLError as exc:
            if attempt < 1:
                time.sleep(0.6 * (attempt + 1))
                continue
            raise ValueError(f"无法连接服务器: {exc}") from exc

    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {"raw": raw}
    if not isinstance(data, dict):
        data = {"raw": raw}

    ok_flag = data.get("success")
    token = str(data.get("token", "")).strip()
    message = str(data.get("message") or data.get("detail") or "").strip()
    if status >= 400:
        raise ValueError(f"接口返回错误 ({status}): {message or raw}")
    if ok_flag is False:
        raise ValueError(message or "登录失败")
    if not token and ok_flag is not True:
        raise ValueError(message or "接口未返回 token")
    return {
        "status": status,
        "token": token,
        "message": message or "登录成功",
        "raw": raw,
    }


def backup_power_me_request(token: str) -> dict:
    token_text = str(token or "").strip()
    if not token_text:
        raise ValueError("缺少 DATA Token。")
    req = Request(
        BACKUP_POWER_ME_URL,
        headers={
            "Authorization": f"Bearer {token_text}",
            "Accept": "application/json",
            "User-Agent": "FMS-Update-Manager-Flet",
            "Connection": "close",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=6) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            status = int(getattr(resp, "status", 200) or 200)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        try:
            data = json.loads(raw) if raw.strip() else {}
        except Exception:
            data = {"raw": raw}
        detail = str(
            (data.get("detail") if isinstance(data, dict) else "")
            or (data.get("message") if isinstance(data, dict) else "")
            or raw
            or str(exc)
        ).strip()
        if exc.code == 401:
            raise ValueError(detail or "DATA Token 已失效。") from exc
        raise ValueError(f"校验 DATA Token 失败 ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise ValueError(f"无法连接服务器: {exc}") from exc

    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {"raw": raw}
    if not isinstance(data, dict):
        data = {"raw": raw}
    if status >= 400:
        raise ValueError(str(data.get("detail") or data.get("message") or raw or f"HTTP {status}"))
    if data.get("success") is False:
        raise ValueError(str(data.get("detail") or data.get("message") or "DATA Token 无效"))
    user = data.get("user")
    return {
        "status": status,
        "user": user if isinstance(user, dict) else {},
        "raw": raw,
    }


def openlist_login_request() -> str:
    global OPENLIST_TOKEN_CACHE
    payload = {
        "username": OPENLIST_USERNAME,
        "password": OPENLIST_PASSWORD,
        "otp_code": "",
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        OPENLIST_LOGIN_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "FMS-Update-Manager-Flet",
            "Connection": "close",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            status = int(getattr(resp, "status", 200) or 200)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        try:
            data = json.loads(raw)
            detail = str(data.get("message") or data.get("detail") or raw).strip()
        except Exception:
            detail = raw.strip() or str(exc)
        raise ValueError(f"OpenList 登录失败 ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise ValueError(f"无法连接 OpenList: {exc}") from exc

    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {"raw": raw}
    if not isinstance(data, dict):
        data = {"raw": raw}
    if status >= 400 or int(data.get("code", 200) or 200) >= 400:
        raise ValueError(str(data.get("message") or data.get("detail") or raw or "OpenList 登录失败"))
    token = str(data.get("token") or data.get("data", {}).get("token") or "").strip()
    if not token:
        raise ValueError("OpenList 登录成功但未返回 token。")
    OPENLIST_TOKEN_CACHE = token
    return token


def openlist_list_dir_request(token: str, folder_path: str = OPENLIST_ROOT_PATH) -> list[dict]:
    path = str(folder_path or OPENLIST_ROOT_PATH).strip() or OPENLIST_ROOT_PATH
    if not path.startswith("/"):
        path = "/" + path
    payload = {
        "path": path,
        "page": 1,
        "per_page": 500,
        "refresh": False,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        OPENLIST_LIST_URL,
        data=body,
        headers={
            "Authorization": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "FMS-Update-Manager-Flet",
            "Connection": "close",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            status = int(getattr(resp, "status", 200) or 200)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        try:
            data = json.loads(raw)
            detail = str(data.get("message") or data.get("detail") or raw).strip()
        except Exception:
            detail = raw.strip() or str(exc)
        raise ValueError(f"OpenList 目录读取失败 ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise ValueError(f"无法连接 OpenList: {exc}") from exc

    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {"raw": raw}
    if not isinstance(data, dict):
        data = {"raw": raw}
    if status >= 400 or int(data.get("code", 200) or 200) >= 400:
        raise ValueError(str(data.get("message") or data.get("detail") or raw or "OpenList 目录读取失败"))
    items = data.get("data", {}).get("content", [])
    return items if isinstance(items, list) else []


def is_openlist_token_error(exc: Exception | str) -> bool:
    detail = str(exc or "").strip().lower()
    hints = (
        "token",
        "authorization",
        "unauthorized",
        "invalidated",
        "missing authorization",
    )
    return any(hint in detail for hint in hints)


def get_openlist_token(*, force_refresh: bool = False) -> str:
    global OPENLIST_TOKEN_CACHE
    if OPENLIST_TOKEN_CACHE and not force_refresh:
        return OPENLIST_TOKEN_CACHE
    OPENLIST_TOKEN_CACHE = openlist_login_request()
    return OPENLIST_TOKEN_CACHE


def openlist_list_dir_auto_request(folder_path: str = OPENLIST_ROOT_PATH) -> list[dict]:
    global OPENLIST_TOKEN_CACHE
    token = get_openlist_token(force_refresh=False)
    try:
        return openlist_list_dir_request(token, folder_path)
    except Exception as exc:
        if not is_openlist_token_error(exc):
            raise
        OPENLIST_TOKEN_CACHE = ""
        fresh_token = get_openlist_token(force_refresh=True)
        return openlist_list_dir_request(fresh_token, folder_path)


def openlist_get_file_meta_request(token: str, file_path: str) -> dict:
    path = str(file_path or "").strip()
    if not path:
        raise ValueError("OpenList 文件路径不能为空。")
    if not path.startswith("/"):
        path = "/" + path
    payload = {"path": path, "password": ""}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        OPENLIST_GET_URL,
        data=body,
        headers={
            "Authorization": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "FMS-Update-Manager-Flet",
            "Connection": "close",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            status = int(getattr(resp, "status", 200) or 200)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        try:
            data = json.loads(raw)
            detail = str(data.get("message") or data.get("detail") or raw).strip()
        except Exception:
            detail = raw.strip() or str(exc)
        raise ValueError(f"OpenList 文件信息读取失败 ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise ValueError(f"无法连接 OpenList: {exc}") from exc

    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {"raw": raw}
    if not isinstance(data, dict):
        data = {"raw": raw}
    if status >= 400 or int(data.get("code", 200) or 200) >= 400:
        raise ValueError(str(data.get("message") or data.get("detail") or raw or "OpenList 文件信息读取失败"))
    payload_data = data.get("data", {})
    return payload_data if isinstance(payload_data, dict) else {}


def openlist_get_file_meta_auto_request(file_path: str) -> dict:
    global OPENLIST_TOKEN_CACHE
    token = get_openlist_token(force_refresh=False)
    try:
        return openlist_get_file_meta_request(token, file_path)
    except Exception as exc:
        if not is_openlist_token_error(exc):
            raise
        OPENLIST_TOKEN_CACHE = ""
        fresh_token = get_openlist_token(force_refresh=True)
        return openlist_get_file_meta_request(fresh_token, file_path)


def openlist_cycle_path(cycle_id: str) -> str:
    cycle_text = str(cycle_id or "").strip().strip("/")
    if not cycle_text:
        return OPENLIST_ROOT_PATH
    return "/" + cycle_text


def openlist_cycle_msfs_path(cycle_id: str) -> str:
    cycle_text = str(cycle_id or "").strip().strip("/")
    if not cycle_text:
        return "/MSFS"
    return "/" + cycle_text + "/MSFS"


def find_openlist_cycle_folder(cycle_id: str) -> dict | None:
    cycle_text = str(cycle_id or "").strip()
    if not cycle_text:
        return None
    items = openlist_list_dir_auto_request(OPENLIST_ROOT_PATH)
    for item in items:
        if not isinstance(item, dict):
            continue
        if bool(item.get("is_dir")) and str(item.get("name", "")).strip() == cycle_text:
            return item
    return None


def find_openlist_cycle_msfs_folder(cycle_id: str) -> dict | None:
    cycle_text = str(cycle_id or "").strip()
    if not cycle_text:
        return None
    cycle_folder = find_openlist_cycle_folder(cycle_text)
    if not cycle_folder:
        return None
    items = openlist_list_dir_auto_request(openlist_cycle_path(cycle_text))
    for item in items:
        if not isinstance(item, dict):
            continue
        if bool(item.get("is_dir")) and str(item.get("name", "")).strip().lower() == "msfs":
            return item
    return None


def list_openlist_cycle_msfs_items(cycle_id: str) -> list[dict]:
    cycle_text = str(cycle_id or "").strip()
    if not cycle_text:
        raise ValueError("AIRAC 期数不能为空。")
    if not find_openlist_cycle_folder(cycle_text):
        raise ValueError(f"OpenList 未找到期数目录: {cycle_text}")
    if not find_openlist_cycle_msfs_folder(cycle_text):
        raise ValueError(f"OpenList 未找到 MSFS 目录: {cycle_text}/MSFS")
    return openlist_list_dir_auto_request(openlist_cycle_msfs_path(cycle_text))


def _norm_token(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def select_openlist_archive_for_addon(addon: Addon, cycle_id: str, items: list[dict]) -> dict | None:
    package = addon.package_name.strip().lower()
    addon_name = addon.name.strip().lower()
    cycle_norm = _norm_token(cycle_id)

    file_items: list[tuple[dict, str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if bool(item.get("is_dir")):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        file_items.append((item, name, _norm_token(name)))

    def find_by_rules(rules: list[tuple[str, ...]]) -> dict | None:
        for rule in rules:
            candidates: list[tuple[dict, str, str]] = []
            for tup in file_items:
                if all(token in tup[2] for token in rule):
                    candidates.append(tup)
            if not candidates:
                continue
            if cycle_norm:
                cycle_candidates = [c for c in candidates if cycle_norm in c[2]]
                if cycle_candidates:
                    candidates = cycle_candidates
            candidates.sort(key=lambda c: c[1].lower())
            return candidates[0][0]
        return None

    hard_rules: list[tuple[str, ...]] = []
    if package.startswith("pmdg-aircraft-"):
        # PMDG family uses a universal package naming: PMDG_WASM_NavData_XXXX
        hard_rules = [("pmdg", "wasm", "navdata")]
    elif package == "ifly-aircraft-737max8":
        hard_rules = [("ifly", "b38m"), ("ifly", "wasm"), ("ifly", "navdata")]
    elif package == "fnx-aircraft-320":
        hard_rules = [("fenix", "navdata")]
    elif package == "fslabs-aircraft-a321":
        hard_rules = [("fslabs", "navdata")]
    elif package == "fss-aircraft-e19x":
        hard_rules = [("fss", "erj"), ("fss", "navdata")]
    elif package == "css-core":
        hard_rules = [("css",)]
    elif package == "justflight-aircraft-rj":
        hard_rules = [("justflight", "rj"), ("rj", "wasm")]
    elif package == "tfdidesign-aircraft-md11":
        hard_rules = [("tfdi", "md11")]
    elif package in {"inibuilds-aircraft-a340", "inibuilds-aircraft-a350"}:
        hard_rules = [("inibuilds",)]
    elif package == "aerosoft-aircraft-a346-pro":
        hard_rules = [("toliss", "dfdv2"), ("toliss",)]

    hard_match = find_by_rules(hard_rules)
    if hard_match is not None:
        return hard_match

    hints = list(OPENLIST_ARCHIVE_NAME_HINTS.get(package, ()))
    if not hints:
        hints = [p for p in addon_search_tokens(addon) if len(p) >= 3]
    hints_norm = [_norm_token(h) for h in hints if _norm_token(h)]

    best_item: dict | None = None
    best_score = -1
    tie = False
    for item, name, name_norm in file_items:
        score = 0
        for hint in hints_norm:
            if hint and hint in name_norm:
                score += 10
        if cycle_norm and cycle_norm in name_norm:
            score += 6
        if package.startswith("pmdg-aircraft-73") and "777" in name_norm:
            score -= 30
        if package.startswith("pmdg-aircraft-77") and "737" in name_norm:
            score -= 30
        if package == "inibuilds-aircraft-a340" and "a350" in name_norm:
            score -= 30
        if package == "inibuilds-aircraft-a350" and "a340" in name_norm:
            score -= 30
        if package == "aerosoft-aircraft-a346-pro" and "inibuilds" in name_norm:
            score -= 40
        if "a340" in addon_name and "a350" in name_norm:
            score -= 15
        if "a350" in addon_name and "a340" in name_norm:
            score -= 15
        if score <= 0:
            continue
        if score > best_score:
            best_score = score
            best_item = item
            tie = False
        elif score == best_score:
            tie = True
    if best_score <= 0 or best_item is None or tie:
        return None
    return best_item


def download_openlist_archive_for_addon(
    addon: Addon,
    cycle_id: str,
    download_dir: Path,
    progress_callback: Callable[[str], None] | None = None,
) -> dict:
    cycle_text = str(cycle_id or "").strip()
    if not cycle_text:
        raise ValueError("未指定 AIRAC 期数。")
    if progress_callback is not None:
        progress_callback(f"正在读取 OpenList 目录: /{cycle_text}/MSFS")
    items = list_openlist_cycle_msfs_items(cycle_text)
    chosen = select_openlist_archive_for_addon(addon, cycle_text, items)
    if chosen is None:
        raise ValueError(f"未找到与机型匹配的 OpenList 压缩包: {addon.name} / {cycle_text}")
    file_name = str(chosen.get("name", "")).strip()
    if not file_name:
        raise ValueError("OpenList 返回的压缩包名称为空。")
    remote_path = f"{openlist_cycle_msfs_path(cycle_text).rstrip('/')}/{file_name}"
    if progress_callback is not None:
        progress_callback(f"正在获取下载链接: {file_name}")
    meta = openlist_get_file_meta_auto_request(remote_path)
    raw_url = str(meta.get("raw_url", "")).strip()
    if not raw_url:
        raise ValueError(f"OpenList 未返回可用下载链接: {file_name}")

    download_dir.mkdir(parents=True, exist_ok=True)
    local_file = download_dir / file_name
    if local_file.exists() and local_file.is_file():
        local_file.unlink(missing_ok=True)
    if progress_callback is not None:
        progress_callback(f"正在下载: {file_name}")
    req = Request(
        raw_url,
        headers={
            "Accept": "*/*",
            "User-Agent": "FMS-Update-Manager-Flet",
            "Connection": "close",
        },
        method="GET",
    )
    total_size = 0
    with urlopen(req, timeout=60) as resp:
        with local_file.open("wb") as fh:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                fh.write(chunk)
                total_size += len(chunk)
    if total_size <= 0:
        raise ValueError(f"下载失败或文件为空: {file_name}")
    if progress_callback is not None:
        progress_callback(f"下载完成: {file_name} ({total_size} bytes)")
    return {
        "archive_path": str(local_file),
        "archive_name": file_name,
        "cycle_id": cycle_text,
        "bytes": total_size,
        "remote_path": remote_path,
        "raw_url": raw_url,
    }


def normalize_backup_power_login_url(raw_url: str) -> str:
    text = str(raw_url or "").strip()
    if not text:
        return BACKUP_POWER_LOGIN_URL
    if text.startswith("http://") or text.startswith("https://"):
        if "/api/auth/login" in text:
            return text
        return text.rstrip("/") + "/api/auth/login"
    return f"http://{text.strip('/').strip()}/api/auth/login"


def normalize_cache_root_dir(raw_path: str) -> str:
    text = str(raw_path or "").strip()
    if not text:
        return ""
    return str(Path(os.path.expandvars(text)).expanduser())


def resolve_cache_root_dir(state: dict[str, Any] | None = None, *, create: bool = False) -> Path:
    configured = ""
    if isinstance(state, dict):
        configured = normalize_cache_root_dir(str(state.get("cache_root_dir", "")))
    root = Path(configured) if configured else BACKUP_DIR
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def normalize_backup_power_download_dir(raw_path: str) -> str:
    text = str(raw_path or "").strip()
    if not text:
        return ""
    return str(Path(os.path.expandvars(text)).expanduser())


def default_backup_power_download_dir(state: dict[str, Any] | None = None) -> Path:
    return resolve_cache_root_dir(state, create=False) / "_openlist_cache"


def default_batch_download_cache_dir(state: dict[str, Any] | None = None) -> Path:
    return resolve_cache_root_dir(state, create=False) / "_openlist_batch_cache"


def resolve_existing_backup_power_download_dir(state: dict[str, Any]) -> Path | None:
    configured = normalize_backup_power_download_dir(str(state.get("backup_power_download_dir", "")))
    if configured:
        candidate = Path(configured)
        if candidate.exists() and candidate.is_dir():
            return candidate
    default_dir = default_backup_power_download_dir(state)
    if default_dir.exists() and default_dir.is_dir():
        return default_dir
    return None


def ensure_backup_power_download_dir(raw_path: str, *, create: bool = True) -> Path:
    normalized = normalize_backup_power_download_dir(raw_path)
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
    if value in CACHE_CLEANUP_DAY_OPTIONS:
        return value
    if value <= min(CACHE_CLEANUP_DAY_OPTIONS):
        return min(CACHE_CLEANUP_DAY_OPTIONS)
    if value >= max(CACHE_CLEANUP_DAY_OPTIONS):
        return max(CACHE_CLEANUP_DAY_OPTIONS)
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
    scan_targets = [
        default_backup_power_download_dir(state),
        default_batch_download_cache_dir(state),
    ]
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


def normalize_batch_download_workers(raw_value: Any) -> int:
    try:
        value = int(str(raw_value).strip())
    except Exception:
        return DEFAULT_BATCH_DOWNLOAD_WORKERS
    if value in BATCH_DOWNLOAD_WORKER_OPTIONS:
        return value
    if value <= min(BATCH_DOWNLOAD_WORKER_OPTIONS):
        return min(BATCH_DOWNLOAD_WORKER_OPTIONS)
    if value >= max(BATCH_DOWNLOAD_WORKER_OPTIONS):
        return max(BATCH_DOWNLOAD_WORKER_OPTIONS)
    return DEFAULT_BATCH_DOWNLOAD_WORKERS


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {
            "simulator": MSFS_VERSIONS[0],
            "platform": PLATFORMS[0],
            "theme": THEME_LIGHT,
            "addons": [],
            "community_paths": {f"{sim}|{plat}": "" for sim in MSFS_VERSIONS for plat in PLATFORMS},
            "community_2024_paths": {plat: "" for plat in PLATFORMS},
            "community_setup_done": False,
            "wasm_scan_paths": {},
            "enabled_simulators": {sim: True for sim in MSFS_VERSIONS},
            "backup_power_api_url": BACKUP_POWER_LOGIN_URL,
            "backup_power_username": "",
            "backup_power_token": "",
            "backup_power_last_login_at": "",
            "backup_power_download_dir": "",
            "cache_root_dir": "",
            "cache_cleanup_days": DEFAULT_CACHE_CLEANUP_DAYS,
            "cache_last_cleanup_at": "",
            "addon_install_cycles": {},
            "batch_download_workers": DEFAULT_BATCH_DOWNLOAD_WORKERS,
        }
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8", errors="ignore"))
        if not isinstance(state, dict):
            raise TypeError("state must be dict")
        if not isinstance(state.get("community_paths"), dict):
            state["community_paths"] = {}
        if not isinstance(state.get("community_2024_paths"), dict):
            state["community_2024_paths"] = {}
        if not isinstance(state.get("wasm_scan_paths"), dict):
            state["wasm_scan_paths"] = {}
        if not isinstance(state.get("enabled_simulators"), dict):
            state["enabled_simulators"] = {}
        for sim in MSFS_VERSIONS:
            for plat in PLATFORMS:
                state["community_paths"].setdefault(f"{sim}|{plat}", "")
                state["wasm_scan_paths"].setdefault(f"{sim}|{plat}", [])
        for plat in PLATFORMS:
            state["community_2024_paths"].setdefault(plat, "")
        for sim in MSFS_VERSIONS:
            state["enabled_simulators"][sim] = bool(state["enabled_simulators"].get(sim, True))
        state.setdefault("community_setup_done", False)
        state["backup_power_api_url"] = normalize_backup_power_login_url(state.get("backup_power_api_url", BACKUP_POWER_LOGIN_URL))
        state.setdefault("backup_power_username", "")
        state.setdefault("backup_power_token", "")
        state.setdefault("backup_power_last_login_at", "")
        state["backup_power_download_dir"] = normalize_backup_power_download_dir(state.get("backup_power_download_dir", ""))
        state["cache_root_dir"] = normalize_cache_root_dir(state.get("cache_root_dir", ""))
        state["cache_cleanup_days"] = normalize_cache_cleanup_days(
            state.get("cache_cleanup_days", DEFAULT_CACHE_CLEANUP_DAYS)
        )
        state.setdefault("cache_last_cleanup_at", "")
        if not isinstance(state.get("addon_install_cycles"), dict):
            state["addon_install_cycles"] = {}
        state["batch_download_workers"] = normalize_batch_download_workers(
            state.get("batch_download_workers", DEFAULT_BATCH_DOWNLOAD_WORKERS)
        )
        return state
    except Exception:
        return {
            "simulator": MSFS_VERSIONS[0],
            "platform": PLATFORMS[0],
            "theme": THEME_LIGHT,
            "addons": [],
            "community_paths": {f"{sim}|{plat}": "" for sim in MSFS_VERSIONS for plat in PLATFORMS},
            "community_2024_paths": {plat: "" for plat in PLATFORMS},
            "community_setup_done": False,
            "wasm_scan_paths": {},
            "enabled_simulators": {sim: True for sim in MSFS_VERSIONS},
            "backup_power_api_url": BACKUP_POWER_LOGIN_URL,
            "backup_power_username": "",
            "backup_power_token": "",
            "backup_power_last_login_at": "",
            "backup_power_download_dir": "",
            "cache_root_dir": "",
            "cache_cleanup_days": DEFAULT_CACHE_CLEANUP_DAYS,
            "cache_last_cleanup_at": "",
            "addon_install_cycles": {},
            "batch_download_workers": DEFAULT_BATCH_DOWNLOAD_WORKERS,
        }


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


def default_addons() -> list[dict]:
    addons: list[dict] = []
    for name, description, package_name, navdata_subpath in DEFAULT_ADDON_FAMILIES:
        for simulator, platform in DEFAULT_SIM_PLATFORM_VARIANTS:
            addons.append(
                {
                    "name": name,
                    "description": description,
                    "simulator": simulator,
                    "platform": platform,
                    "target_path": "",
                    "package_name": package_name,
                    "navdata_subpath": navdata_subpath,
                }
            )

    addons.append(
        {
            "name": "iniBuilds A340-300",
            "description": "iniBuilds A340 family",
            "simulator": "MSFS 2024",
            "platform": "Steam",
            "target_path": "",
            "package_name": "inibuilds-aircraft-a340",
            "navdata_subpath": r"work\NavigationData",
        }
    )
    addons.append(
        {
            "name": "iniBuilds A340-300",
            "description": "iniBuilds A340 family",
            "simulator": "MSFS 2024",
            "platform": "Xbox/MS Store",
            "target_path": "",
            "package_name": "inibuilds-aircraft-a340",
            "navdata_subpath": r"work\NavigationData",
        }
    )
    addons.append(
        {
            "name": "iniBuilds A350",
            "description": "iniBuilds A350 family",
            "simulator": "MSFS 2024",
            "platform": "Steam",
            "target_path": "",
            "package_name": "inibuilds-aircraft-a350",
            "navdata_subpath": r"work\NavigationData",
        }
    )
    addons.append(
        {
            "name": "iniBuilds A350",
            "description": "iniBuilds A350 family",
            "simulator": "MSFS 2020",
            "platform": "Steam",
            "target_path": "",
            "package_name": "inibuilds-aircraft-a350",
            "navdata_subpath": r"work\NavigationData",
        }
    )
    addons.append(
        {
            "name": "iniBuilds A350",
            "description": "iniBuilds A350 family",
            "simulator": "MSFS 2020",
            "platform": "Xbox/MS Store",
            "target_path": "",
            "package_name": "inibuilds-aircraft-a350",
            "navdata_subpath": r"work\NavigationData",
        }
    )
    addons.append(
        {
            "name": "iniBuilds A350",
            "description": "iniBuilds A350 family",
            "simulator": "MSFS 2024",
            "platform": "Xbox/MS Store",
            "target_path": "",
            "package_name": "inibuilds-aircraft-a350",
            "navdata_subpath": r"work\NavigationData",
        }
    )
    addons.append(
        {
            "name": "Aerosoft A340-600 Pro",
            "description": "Aerosoft Airbus A340-600 Pro",
            "simulator": "MSFS 2024",
            "platform": "Steam",
            "target_path": "",
            "package_name": "aerosoft-aircraft-a346-pro",
            "navdata_subpath": r"work\FMSData",
        }
    )
    addons.append(
        {
            "name": "Aerosoft A340-600 Pro",
            "description": "Aerosoft Airbus A340-600 Pro",
            "simulator": "MSFS 2024",
            "platform": "Xbox/MS Store",
            "target_path": "",
            "package_name": "aerosoft-aircraft-a346-pro",
            "navdata_subpath": r"work\FMSData",
        }
    )
    addons.append(
        {
            "name": "Aerosoft A340-600 Pro",
            "description": "Aerosoft Airbus A340-600 Pro",
            "simulator": "MSFS 2020",
            "platform": "Steam",
            "target_path": "",
            "package_name": "aerosoft-aircraft-a346-pro",
            "navdata_subpath": r"work\FMSData",
        }
    )
    addons.append(
        {
            "name": "Aerosoft A340-600 Pro",
            "description": "Aerosoft Airbus A340-600 Pro",
            "simulator": "MSFS 2020",
            "platform": "Xbox/MS Store",
            "target_path": "",
            "package_name": "aerosoft-aircraft-a346-pro",
            "navdata_subpath": r"work\FMSData",
        }
    )
    return addons


def save_state(state: dict) -> None:
    try:
        ROAMING_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def to_addon(item: dict) -> Addon | None:
    if not isinstance(item, dict):
        return None
    try:
        return Addon(
            name=str(item.get("name", "")).strip(),
            description=str(item.get("description", "")).strip(),
            simulator=str(item.get("simulator", "")).strip(),
            platform=str(item.get("platform", "")).strip(),
            target_path=str(item.get("target_path", "")).strip(),
            package_name=str(item.get("package_name", "")).strip(),
            navdata_subpath=str(item.get("navdata_subpath", "")).strip(),
        )
    except Exception:
        return None


def _expand(raw: str) -> str:
    return os.path.normpath(os.path.expandvars(raw))


def _normalize_path_list(raw) -> list[str]:
    if isinstance(raw, list):
        values = [str(v).strip() for v in raw]
    elif isinstance(raw, str):
        values = [line.strip() for line in raw.splitlines()]
    else:
        values = []
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not item:
            continue
        normalized = _expand(item)
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized)
    return out


def custom_wasm_scan_paths(state: dict | None, simulator: str, platform: str) -> list[str]:
    if not isinstance(state, dict):
        return []
    raw_map = state.get("wasm_scan_paths", {})
    if not isinstance(raw_map, dict):
        return []
    return _normalize_path_list(raw_map.get(community_key(simulator, platform), []))


def default_wasm_scan_bases(simulator: str, platform: str) -> list[str]:
    if simulator == "MSFS 2024":
        if platform == "Steam":
            root = _expand(r"%APPDATA%\Microsoft Flight Simulator 2024\packages")
            wasm_root = _expand(r"%APPDATA%\Microsoft Flight Simulator 2024\WASM")
        else:
            root = _expand(r"%LOCALAPPDATA%\Packages\Microsoft.Limitless_8wekyb3d8bbwe\LocalState\packages")
            wasm_root = _expand(r"%LOCALAPPDATA%\Packages\Microsoft.Limitless_8wekyb3d8bbwe\LocalState\WASM")
        return _normalize_path_list(
            [
                root,
                os.path.join(root, "WASM", "MSFS2024"),
                os.path.join(wasm_root, "MSFS2024"),
                os.path.join(root, "WASM", "MSFS2020"),
                os.path.join(wasm_root, "MSFS2020"),
            ]
        )
    if platform == "Steam":
        return [_expand(r"%APPDATA%\Microsoft Flight Simulator\packages")]
    return [_expand(r"%LOCALAPPDATA%\Packages\Microsoft.FlightSimulator_8wekyb3d8bbwe\LocalState\packages")]


def cycle_json_scan_bases(simulator: str, platform: str, state: dict | None = None) -> list[str]:
    defaults = default_wasm_scan_bases(simulator, platform)
    custom = custom_wasm_scan_paths(state, simulator, platform)
    return _normalize_path_list([*custom, *defaults])


def get_cycle_json_index(bases: list[str]) -> list[Path]:
    key = tuple(bases)
    cached = CYCLE_JSON_SCAN_CACHE.get(key)
    if cached is not None:
        return cached
    found: list[Path] = []
    for base in bases:
        if not base:
            continue
        p = Path(base)
        if not p.exists():
            continue
        try:
            found.extend(list(p.rglob("cycle.json")))
        except Exception:
            continue
    CYCLE_JSON_SCAN_CACHE[key] = found
    return found


def clear_cycle_json_scan_cache() -> None:
    CYCLE_JSON_SCAN_CACHE.clear()


def community_key(simulator: str, platform: str) -> str:
    return f"{simulator}|{platform}"


def enabled_simulators(state: dict | None) -> list[str]:
    if not isinstance(state, dict):
        return list(MSFS_VERSIONS)
    raw = state.get("enabled_simulators", {})
    if not isinstance(raw, dict):
        return list(MSFS_VERSIONS)
    sims = [sim for sim in MSFS_VERSIONS if bool(raw.get(sim, True))]
    return sims if sims else list(MSFS_VERSIONS)


def community_2024_base(state: dict | None, platform: str) -> str:
    if not isinstance(state, dict):
        return ""
    raw = state.get("community_2024_paths", {})
    if not isinstance(raw, dict):
        return ""
    return _expand(str(raw.get(platform, "")).strip()) if str(raw.get(platform, "")).strip() else ""


def community_base_candidates(state: dict | None, simulator: str, platform: str) -> list[str]:
    bases = [community_base(state if isinstance(state, dict) else {}, simulator, platform)]
    if simulator == "MSFS 2024":
        c24 = community_2024_base(state, platform)
        if c24:
            bases.append(c24)
    return _normalize_path_list(bases)


def is_valid_community_path(path: str) -> bool:
    if not path:
        return False
    p = Path(path)
    return p.exists() and p.is_dir() and p.name.lower() == "community"


def is_valid_community2024_path(path: str) -> bool:
    if not path:
        return False
    p = Path(path)
    return p.exists() and p.is_dir() and p.name.lower() in {"community2024", "community"}


def default_community_base(simulator: str, platform: str) -> str:
    if simulator == "MSFS 2024":
        if platform == "Steam":
            return _expand(r"%APPDATA%\Microsoft Flight Simulator 2024\packages\Community")
        return _expand(r"%LOCALAPPDATA%\Packages\Microsoft.Limitless_8wekyb3d8bbwe\LocalCache\packages\Community")
    if platform == "Steam":
        return _expand(r"%APPDATA%\Microsoft Flight Simulator\packages\Community")
    return _expand(r"%LOCALAPPDATA%\Packages\Microsoft.FlightSimulator_8wekyb3d8bbwe\LocalCache\packages\Community")


def community_base(state: dict, simulator: str, platform: str) -> str:
    custom = str(state.get("community_paths", {}).get(community_key(simulator, platform), "")).strip()
    if custom:
        return _expand(custom)
    return default_community_base(simulator, platform)


def wasm_base_candidates(simulator: str, platform: str, state: dict | None = None) -> list[str]:
    defaults = default_wasm_scan_bases(simulator, platform)
    custom = custom_wasm_scan_paths(state, simulator, platform)
    return _normalize_path_list([*custom, *defaults])


def infer_package_name(addon: Addon) -> str:
    if addon.package_name:
        return addon.package_name
    return re.sub(r"[^a-z0-9]+", "-", addon.name.lower()).strip("-")


def addon_search_tokens(addon: Addon) -> list[str]:
    tokens: list[str] = []
    package_name = addon.package_name.strip().lower()
    if package_name:
        tokens.append(package_name)
        tokens.extend(
            [
                p
                for p in package_name.split("-")
                if len(p) >= 3 and p not in {"aircraft", "design", "professional", "series", "family"}
            ]
        )
    name = addon.name.strip().lower()
    normalized_name = re.sub(r"[^a-z0-9]+", " ", name)
    tokens.extend([p for p in normalized_name.split() if len(p) >= 3 and p not in {"the", "and", "for", "family", "series", "professional"}])
    if "pmdg 777-200lr" in name:
        tokens.extend(["77l", "777"])
    elif "pmdg 777-200er" in name:
        tokens.extend(["77er", "777"])
    elif "pmdg 777f" in name:
        tokens.extend(["77f", "777"])
    elif "pmdg 777-300er" in name:
        tokens.extend(["77w", "777"])
    elif "pmdg 737-600" in name:
        tokens.extend(["736", "737"])
    elif "pmdg 737-700" in name:
        tokens.extend(["737"])
    elif "pmdg 737-800" in name:
        tokens.extend(["738", "737"])
    elif "pmdg 737-900" in name:
        tokens.extend(["739", "737"])
    elif "a340-300" in name or "a343" in name:
        tokens.extend(["a343", "343", "a340-300"])
    elif "a340-600" in name or "a346" in name:
        tokens.extend(["a346", "346", "a340-600"])
    return list(dict.fromkeys(tokens))


def addon_requires_cycle_name_match(addon: Addon) -> bool:
    name = addon.name.strip().lower()
    package = addon.package_name.strip().lower()
    return addon.simulator == "MSFS 2024" and package == "inibuilds-aircraft-a340" and (
        "a340-300" in name or "a343" in name or "a340-600" in name or "a346" in name
    )


def cycle_name_matches_addon(addon: Addon, cycle_name: str) -> bool:
    hay = cycle_name.strip().lower()
    compact = re.sub(r"[^a-z0-9]+", "", hay)
    name = addon.name.strip().lower()
    package = addon.package_name.strip().lower()

    if not hay:
        return False

    if package.startswith("pmdg-aircraft-73") or "pmdg 737" in name:
        if "pmdg" not in hay:
            return False
        if "737-600" in name and ("737-600" in hay or "736" in hay):
            return True
        if "737-700" in name and "737-700" in hay:
            return True
        if "737-800" in name and ("737-800" in hay or "738" in hay):
            return True
        if "737-900" in name and ("737-900" in hay or "739" in hay):
            return True
        if addon.simulator == "MSFS 2024":
            return "737" in hay or compact in {"pmdg", "pmdg737"}
        return False

    if package.startswith("pmdg-aircraft-77") or "pmdg 777" in name:
        if "pmdg" not in hay:
            return False
        if "200lr" in name:
            return "200lr" in compact or "777200lr" in compact or "77l" in compact
        if "200er" in name:
            return "200er" in compact or "777200er" in compact or "77er" in compact
        if "777f" in name:
            return "777f" in compact or ("777" in hay and "freighter" in hay) or "77f" in compact
        if "300er" in compact or "777300er" in compact or "77w" in compact:
            return True
        if addon.simulator == "MSFS 2024":
            return "777" in hay or compact in {"pmdg", "pmdg777"}
        return False

    if package == "fnx-aircraft-320" or name.startswith("fenix"):
        return "fenix" in hay
    if "fslabs" in package or "flight sim labs" in name:
        return ("fslabs" in compact or "flightsimlabs" in compact) and ("a321" in compact or "321" in compact)
    if package == "tfdidesign-aircraft-md11" or "md-11" in name or "md11" in package:
        return "tfdi" in hay and ("md11" in compact or "md-11" in hay)
    if package == "justflight-aircraft-rj" or "rj professional" in name:
        return ("justflight" in compact or "just flight" in hay) and ("rj" in hay or "146" in compact)
    if package == "fss-aircraft-e19x" or "fss erj" in name:
        return "fss" in hay and ("erj" in hay or "e170" in compact or "e175" in compact or "e190" in compact or "e195" in compact)
    if package == "css-core" or "css 737" in name:
        return "css" in hay and "737" in hay
    if package == "fycyc-aircraft-c919x" or "c919" in name:
        return "c919" in hay
    if package == "ifly-aircraft-737max8" or "ifly" in name:
        return "ifly" in hay and ("737-max8" in hay or "737max8" in compact or "max8" in compact)
    if package in {"inibuilds-aircraft-a340", "inibuilds-aircraft-a350"}:
        if "inibuilds" not in hay:
            return False
        if "dfd" in hay:
            return True
        if package == "inibuilds-aircraft-a350" or "a350" in name:
            return "a350" in hay or "350" in compact
        if "a340-300" in name or "a343" in name:
            return "a340-300" in hay or "a343" in compact
        if "a340-600" in name or "a346" in name:
            return "a340-600" in hay or "a346" in compact
        return False
    if package == "aerosoft-aircraft-a346-pro" or "a340-600" in name:
        # Aerosoft A346 packages may use a generic cycle name like "ToLiss" in cycle.json.
        if "toliss" in compact:
            return True
        return "a340-600" in hay or "a346" in compact

    return text_matches_addon_signature(addon, cycle_name)


def text_matches_addon_signature(addon: Addon, text: str) -> bool:
    hay = text.strip().lower()
    if not hay:
        return False
    tokens = addon_search_tokens(addon)
    strong_tokens = [token for token in tokens if any(ch.isdigit() for ch in token) or "-" in token]
    if strong_tokens:
        return any(token in hay for token in strong_tokens)
    return any(token in hay for token in tokens)


def cycle_name_needs_path_disambiguation(addon: Addon, cycle_name: str) -> bool:
    hay = cycle_name.strip().lower()
    compact = re.sub(r"[^a-z0-9]+", "", hay)
    package = addon.package_name.strip().lower()
    name = addon.name.strip().lower()

    if package.startswith("pmdg-aircraft-73") or "pmdg 737" in name:
        if "pmdg" not in hay:
            return False
        specific_tokens = ("736", "737600", "737700", "738", "737800", "739", "737900")
        return not any(token in compact for token in specific_tokens)

    if package.startswith("pmdg-aircraft-77") or "pmdg 777" in name:
        if "pmdg" not in hay:
            return False
        specific_tokens = (
            "77l",
            "777200lr",
            "200lr",
            "77er",
            "777200er",
            "200er",
            "77f",
            "777f",
            "freighter",
            "77w",
            "777300er",
            "300er",
        )
        return not any(token in compact for token in specific_tokens)
    return False


def path_matches_addon_signature(addon: Addon, candidate_dir: Path, cycle_json_path: Path | None = None) -> bool:
    haystack = str(candidate_dir).lower().replace("\\", "/")
    package = addon.package_name.strip().lower()
    name = addon.name.strip().lower()

    # PMDG families must match their package folder signature to avoid
    # accidental cross-match with other 737/777 addons (e.g. iFly MAX8).
    if package.startswith("pmdg-aircraft-73") or "pmdg 737" in name:
        if package and package not in haystack:
            return False
    if package.startswith("pmdg-aircraft-77") or "pmdg 777" in name:
        if package and package not in haystack:
            return False

    # A340 families can share generic tokens like "a340" in path/cycle metadata.
    # Enforce package-level separation to avoid Aerosoft A346 matching iniBuilds A340.
    if package == "aerosoft-aircraft-a346-pro":
        if "inibuilds-aircraft-a340" in haystack:
            return False
        if "aerosoft-aircraft-a346-pro" not in haystack:
            return False
    if package == "inibuilds-aircraft-a340":
        if addon.simulator == "MSFS 2024":
            if (
                "microsoft flight simulator 2024" not in haystack
                and "microsoft.limitless_8wekyb3d8bbwe" not in haystack
                and "/msfs2024/" not in haystack
            ):
                return False
        elif addon.simulator == "MSFS 2020":
            if (
                "microsoft flight simulator 2024" in haystack
                or "microsoft.limitless_8wekyb3d8bbwe" in haystack
                or "/msfs2024/" in haystack
            ):
                return False
        if "aerosoft-aircraft-a346-pro" in haystack:
            return False
        if "inibuilds-aircraft-a350" in haystack:
            return False
        if "inibuilds-aircraft-a340" not in haystack:
            return False
    if package == "inibuilds-aircraft-a350":
        if addon.simulator == "MSFS 2024":
            if (
                "microsoft flight simulator 2024" not in haystack
                and "microsoft.limitless_8wekyb3d8bbwe" not in haystack
                and "/msfs2024/" not in haystack
            ):
                return False
        elif addon.simulator == "MSFS 2020":
            if (
                "microsoft flight simulator 2024" in haystack
                or "microsoft.limitless_8wekyb3d8bbwe" in haystack
                or "/msfs2024/" in haystack
            ):
                return False
        if "aerosoft-aircraft-a346-pro" in haystack:
            return False
        if "inibuilds-aircraft-a340" in haystack:
            return False
        if "inibuilds-aircraft-a350" not in haystack:
            return False

    # Hard guard for known conflicting families (RJ vs CRJ).
    if package == "justflight-aircraft-rj" or "rj professional" in name:
        if "aerosoft-crj" in haystack:
            return False
        if "justflight-aircraft-rj" not in haystack:
            return False
    if package == "aerosoft-crj" or "crj" in name:
        if "justflight-aircraft-rj" in haystack:
            return False

    if cycle_json_path is not None:
        cycle_name = read_cycle_json_name(cycle_json_path)
        if cycle_name:
            if cycle_name_matches_addon(addon, cycle_name):
                if cycle_name_needs_path_disambiguation(addon, cycle_name):
                    return text_matches_addon_signature(addon, str(candidate_dir))
                return True
            if addon_requires_cycle_name_match(addon):
                return False
            # Some addons (e.g. PMDG family) may write a generic cycle name such as "PMDG".
            # In this case, fallback to path-signature matching instead of rejecting directly.
            return text_matches_addon_signature(addon, str(candidate_dir))
        # Some packages ship cycle.json without a stable "name" field.
        # For those, fallback to folder-signature matching.
        if addon_requires_cycle_name_match(addon):
            return False
        return text_matches_addon_signature(addon, str(candidate_dir))
    return text_matches_addon_signature(addon, str(candidate_dir))


def auto_detect_cycle_json_target(addon: Addon, state: dict | None = None) -> Path | None:
    bases = cycle_json_scan_bases(addon.simulator, addon.platform, state)
    indexed = get_cycle_json_index(bases)
    if not indexed:
        return None
    matches: list[tuple[int, int, Path]] = []
    for cycle_json in indexed:
        candidate = cycle_json.parent
        if not path_matches_addon_signature(addon, candidate, cycle_json):
            continue
        cycle = read_cycle_from_dir(candidate)
        score = int(cycle) if cycle.isdigit() else -1
        depth = len(candidate.parts)
        matches.append((score, -depth, candidate))
    if not matches:
        return None
    matches.sort(reverse=True)
    return matches[0][2]


def is_fenix_addon(addon: Addon) -> bool:
    return addon.package_name.strip().lower() == "fnx-aircraft-320" or addon.name.strip().lower().startswith("fenix")


def is_fslabs_addon(addon: Addon) -> bool:
    package_name = addon.package_name.strip().lower()
    addon_name = addon.name.strip().lower()
    return "fslabs" in package_name or addon_name.startswith("flight sim labs")


def fenix_navdata_path() -> str:
    return _expand(r"%ProgramData%\Fenix\Navdata")


def fslabs_navdata_path() -> str:
    home_drive = os.path.expandvars(r"%HOMEDRIVE%")
    home_path = os.path.expandvars(r"%HOMEPATH%")
    if home_drive and home_path and home_path != r"%HOMEPATH%":
        return os.path.normpath(os.path.join(home_drive + home_path, "AppData", "Roaming", "FSLabs_NavData", "NavData"))
    return _expand(r"%USERPROFILE%\AppData\Roaming\FSLabs_NavData\NavData")


def addon_key(addon: Addon) -> str:
    return "|".join(
        [
            addon.simulator,
            addon.platform,
            infer_package_name(addon),
            addon.name,
        ]
    )


def addon_prefers_community(addon: Addon) -> bool:
    package = addon.package_name.strip().lower()
    if package == "ifly-aircraft-737max8":
        # MSFS 2024 iFly package is currently installed under WASM paths in user setups.
        return addon.simulator != "MSFS 2024"
    return False


def fixed_relative_path(addon: Addon) -> str:
    name = addon.name.lower().strip()
    package = addon.package_name.lower().strip()

    fixed_paths = {
        "pmdg 737-600": os.path.join("pmdg-aircraft-736", "Work"),
        "pmdg 737-700": os.path.join("pmdg-aircraft-737", "Work"),
        "pmdg 737-800": os.path.join("pmdg-aircraft-738", "Work"),
        "pmdg 737-900": os.path.join("pmdg-aircraft-739", "Work"),
        "pmdg 777-200er": os.path.join("pmdg-aircraft-77er", "work", "NavigationData"),
        "pmdg 777f": os.path.join("pmdg-aircraft-77f", "work", "NavigationData"),
        "pmdg 777-200lr": os.path.join("pmdg-aircraft-77l", "work", "NavigationData"),
        "pmdg 777-300er": os.path.join("pmdg-aircraft-77w", "work", "NavigationData"),
        "tfdi md-11": os.path.join("tfdidesign-aircraft-md11", "work", "Nav-Primary"),
        "fycyc c919": os.path.join("fycyc-aircraft-c919x", "work", "NavigationData"),
    }
    if name in fixed_paths:
        return fixed_paths[name]
    if package in {
        "pmdg-aircraft-736",
        "pmdg-aircraft-737",
        "pmdg-aircraft-738",
        "pmdg-aircraft-739",
        "pmdg-aircraft-77er",
        "pmdg-aircraft-77f",
        "pmdg-aircraft-77l",
        "pmdg-aircraft-77w",
        "tfdidesign-aircraft-md11",
        "fycyc-aircraft-c919x",
    }:
        package_fixed_paths = {
            "pmdg-aircraft-736": os.path.join("pmdg-aircraft-736", "Work"),
            "pmdg-aircraft-737": os.path.join("pmdg-aircraft-737", "Work"),
            "pmdg-aircraft-738": os.path.join("pmdg-aircraft-738", "Work"),
            "pmdg-aircraft-739": os.path.join("pmdg-aircraft-739", "Work"),
            "pmdg-aircraft-77er": os.path.join("pmdg-aircraft-77er", "work", "NavigationData"),
            "pmdg-aircraft-77f": os.path.join("pmdg-aircraft-77f", "work", "NavigationData"),
            "pmdg-aircraft-77l": os.path.join("pmdg-aircraft-77l", "work", "NavigationData"),
            "pmdg-aircraft-77w": os.path.join("pmdg-aircraft-77w", "work", "NavigationData"),
            "tfdidesign-aircraft-md11": os.path.join("tfdidesign-aircraft-md11", "work", "Nav-Primary"),
            "fycyc-aircraft-c919x": os.path.join("fycyc-aircraft-c919x", "work", "NavigationData"),
        }
        return package_fixed_paths[package]

    # PMDG 737 series
    if "pmdg 737" in name or package.startswith("pmdg-aircraft-73"):
        if package == "pmdg-aircraft-736" or "737-600" in name:
            return os.path.join("pmdg-aircraft-736", "Work")
        if package == "pmdg-aircraft-737" or "737-700" in name:
            return os.path.join("pmdg-aircraft-737", "Work")
        if package == "pmdg-aircraft-738" or "737-800" in name:
            return os.path.join("pmdg-aircraft-738", "Work")
        if package == "pmdg-aircraft-739" or "737-900" in name:
            return os.path.join("pmdg-aircraft-739", "Work")

    # PMDG 777 series
    if "pmdg 777" in name or package.startswith("pmdg-aircraft-77"):
        if "77l" in package or "200lr" in name:
            return os.path.join("pmdg-aircraft-77l", "work", "NavigationData")
        if "77er" in package or "200er" in name:
            return os.path.join("pmdg-aircraft-77er", "work", "NavigationData")
        if "77f" in package or "freighter" in name:
            return os.path.join("pmdg-aircraft-77f", "work", "NavigationData")
        return os.path.join("pmdg-aircraft-77w", "work", "NavigationData")

    # TFDi MD-11
    if "tfdi" in package or "md-11" in name or "md11" in package:
        return os.path.join("tfdidesign-aircraft-md11", "work", "Nav-Primary")

    # FYCYC C919
    if package == "fycyc-aircraft-c919x" or "c919" in name:
        return os.path.join("fycyc-aircraft-c919x", "work", "NavigationData")

    if "fly the maddog x md82-88" in name or "maddog" in name:
        return os.path.join("lsh-maddogx-aircraft", "Work", "Navigraph")

    if "ifly b738m" in name or package == "ifly-aircraft-737max8":
        return os.path.join("ifly-aircraft-737max8", "work", "navdata", "Permanent")

    # Aerosoft A340-600 Pro
    if package == "aerosoft-aircraft-a346-pro" or "a340-600" in name:
        return os.path.join("aerosoft-aircraft-a346-pro", "work", "FMSData")

    # Just Flight RJ Professional
    if "rj professional" in name or package == "justflight-aircraft-rj":
        return os.path.join("justflight-aircraft-rj", "Work", "JustFlight")

    if name == "bae 146" or "bae 146" in name:
        return os.path.join("ustflight-aircraft-rj", "work", "JustFlight")

    if "crj" in name or package == "aerosoft-crj":
        return os.path.join("aerosoft-crj", "work", "Data", "NavData")
    return ""


def resolve_wasm_target_by_folder_name(addon: Addon, state: dict | None = None) -> Path | None:
    if addon_prefers_community(addon):
        return None

    fixed = fixed_relative_path(addon)
    pkg = infer_package_name(addon)

    for base in wasm_base_candidates(addon.simulator, addon.platform, state):
        base_path = Path(base)
        if not base_path.exists() or not base_path.is_dir():
            continue

        if fixed:
            fixed_path = Path(fixed)
            if not fixed_path.parts:
                continue
            package_dir = base_path / fixed_path.parts[0]
            if package_dir.exists() and package_dir.is_dir():
                return base_path / fixed_path
            continue

        package_dir = base_path / pkg
        if package_dir.exists() and package_dir.is_dir():
            target = package_dir
            if addon.navdata_subpath:
                target = target / Path(addon.navdata_subpath)
            return target
    return None


def resolve_target_dir(addon: Addon, state: dict | None = None) -> Path | None:
    if is_fenix_addon(addon):
        p = Path(fenix_navdata_path())
        if p.exists():
            return p
    if is_fslabs_addon(addon):
        p = Path(fslabs_navdata_path())
        if p.exists():
            return p

    if state is not None and addon_prefers_community(addon):
        for base in community_base_candidates(state, addon.simulator, addon.platform):
            community_path = Path(base) / infer_package_name(addon)
            if addon.navdata_subpath:
                community_path = community_path / addon.navdata_subpath
            if community_path.exists():
                cycle_json = community_path / "cycle.json"
                if cycle_json.exists() and path_matches_addon_signature(addon, community_path, cycle_json):
                    nested = find_nested_cycle_dir(community_path, addon)
                    return nested if nested is not None else community_path

    if not addon_prefers_community(addon):
        fixed = fixed_relative_path(addon)
        if fixed:
            for base in wasm_base_candidates(addon.simulator, addon.platform, state):
                p = Path(base) / fixed
                if p.exists():
                    cycle_json = p / "cycle.json"
                    if cycle_json.exists() and not path_matches_addon_signature(addon, p, cycle_json):
                        continue
                    nested = find_nested_cycle_dir(p, addon)
                    return nested if nested is not None else p

    if addon.target_path:
        p = Path(addon.target_path)
        if p.exists():
            cycle_json = p / "cycle.json"
            if path_matches_addon_signature(addon, p, cycle_json if cycle_json.exists() else None):
                nested = find_nested_cycle_dir(p, addon)
                return nested if nested is not None else p

    pkg = infer_package_name(addon)
    for base in wasm_base_candidates(addon.simulator, addon.platform, state):
        p = Path(base) / pkg
        if addon.navdata_subpath:
            p = p / addon.navdata_subpath
        if p.exists():
            cycle_json = p / "cycle.json"
            if path_matches_addon_signature(addon, p, cycle_json if cycle_json.exists() else None):
                nested = find_nested_cycle_dir(p, addon)
                return nested if nested is not None else p

    if state is not None:
        for base in community_base_candidates(state, addon.simulator, addon.platform):
            community_path = Path(base) / infer_package_name(addon)
            if addon.navdata_subpath:
                community_path = community_path / addon.navdata_subpath
            if community_path.exists():
                cycle_json = community_path / "cycle.json"
                if cycle_json.exists() and path_matches_addon_signature(addon, community_path, cycle_json):
                    nested = find_nested_cycle_dir(community_path, addon)
                    return nested if nested is not None else community_path

    scanned = auto_detect_cycle_json_target(addon, state)
    if scanned and scanned.exists():
        nested = find_nested_cycle_dir(scanned, addon)
        return nested if nested is not None else scanned
    return None


def read_a346_builtin_cycle(addon: Addon, state: dict | None = None) -> tuple[str, str] | None:
    if not is_a346_addon(addon):
        return None

    package_name = infer_package_name(addon)
    candidates: list[Path] = []
    seen: set[str] = set()
    for base in community_base_candidates(state, addon.simulator, addon.platform):
        if not base:
            continue
        package_root = Path(base) / package_name
        key = str(package_root).lower()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(package_root)
    if addon.simulator == "MSFS 2024" and addon.platform == "Xbox/MS Store":
        package_root = Path(_expand(r"%APPDATA%\Microsoft Flight Simulator 2024\packages\Community")) / package_name
        key = str(package_root).lower()
        if key not in seen:
            seen.add(key)
            candidates.append(package_root)

    for package_root in candidates:
        default_data = package_root / "data" / "default data"
        if not default_data.exists() or not default_data.is_dir():
            continue

        cycle_candidates: list[str] = []
        for file_path in default_data.glob("ng_jeppesen_fwdfd_*.s3db"):
            cycle = detect_airac(file_path.name)
            if cycle != "UNKNOWN":
                cycle_candidates.append(cycle)

        if cycle_candidates:
            cycle_candidates.sort(key=lambda value: int(value), reverse=True)
            return cycle_candidates[0], str(default_data)
    return None


def addon_status(addon: Addon, api_cycle: str, state: dict | None = None) -> tuple[str, str, str, str]:
    target = resolve_target_dir(addon, state)
    if target and target.exists():
        installed = read_cycle_from_dir(target)
        target_str = str(target)
    else:
        installed = "NONE"
        target_str = addon.target_path or ""
        a346_builtin = read_a346_builtin_cycle(addon, state)
        if a346_builtin is not None:
            installed, target_str = a346_builtin

    if not target_str:
        status = "NOT INSTALLED"
    elif api_cycle in ("NONE", "UNKNOWN"):
        status = "API UNAVAILABLE"
    elif installed == api_cycle:
        status = "UP TO DATE"
    else:
        status = "UPDATE READY"

    return status, installed, api_cycle, target_str


def status_badge_style(status: str) -> tuple[str, str]:
    if status == "UP TO DATE":
        return "#daf5e7", "#1f7a43"
    if status == "NOT INSTALLED":
        return "#f9dde0", "#a53742"
    if status == "API UNAVAILABLE":
        return "#e6e9ef", "#4d607d"
    return "#f8eacb", "#8a6200"


def status_dot_color(status: str) -> str:
    if status == "UP TO DATE":
        return "#1aa35c"
    if status == "NOT INSTALLED":
        return "#d64545"
    return "#c99600"


def matches_filter(status: str, filter_value: str) -> bool:
    if filter_value == "All":
        return True
    if filter_value == "Installed":
        return status in {"UP TO DATE", "UPDATE READY", "API UNAVAILABLE"}
    if filter_value == "Update Available":
        return status == "UPDATE READY"
    if filter_value == "Not Installed":
        return status == "NOT INSTALLED"
    return True


def compute_filtered_addon_entries(
    addons_all: list[Addon],
    simulator: str,
    platform: str,
    search_text: str,
    filter_value: str,
    api_cycle: str,
    state: dict | None = None,
) -> list[tuple[Addon, str, str, str, str, str]]:
    items = [a for a in addons_all if a.simulator == simulator and a.platform == platform]
    q = search_text.strip().lower()
    if q:
        items = [
            a
            for a in items
            if q in a.name.lower()
            or q in a.description.lower()
            or q in infer_package_name(a).lower()
        ]

    entries: list[tuple[Addon, str, str, str, str, str]] = []
    for addon in items:
        status, installed, api, target = addon_status(addon, api_cycle, state)
        if matches_filter(status, filter_value):
            entries.append((addon, addon_key(addon), status, installed, api, target))

    def sort_rank(status: str) -> int:
        if status in {"UP TO DATE", "API UNAVAILABLE"}:
            return 0
        if status == "UPDATE READY":
            return 1
        if status == "NOT INSTALLED":
            return 2
        return 3

    entries.sort(key=lambda e: (sort_rank(e[2]), e[0].name.casefold()))
    return entries


def main(  # pylint: disable=too-many-function-args,unexpected-keyword-arg,no-member
    page: ft.Page,
    fast_reload: bool = False,
    cached_cycle: dict | None = None,
):
    ft.context.disable_auto_update()
    for d in (ROAMING_DIR, LOG_DIR, LOCAL_DIR, EXTRACTED_DIR, BACKUP_DIR):
        d.mkdir(parents=True, exist_ok=True)

    state = load_state()
    if not isinstance(state.get("addons"), list) or not state.get("addons"):
        state["addons"] = default_addons()
        save_state(state)
    simulator = str(state.get("simulator", MSFS_VERSIONS[0]))
    platform = str(state.get("platform", PLATFORMS[0]))
    theme_name = str(state.get("theme", THEME_LIGHT))
    filter_value = "All"
    search_text = ""
    current_cycle_info: dict | None = cached_cycle
    selected_addon_key: str | None = None
    last_rendered_entries: list[tuple[Addon, str, str, str, str, str]] = []
    rebuild_generation = 0
    streamer_mode = bool(state.get("streamer_mode", False))

    addon_items = state.get("addons", []) if isinstance(state.get("addons"), list) else []
    migrated = False
    existing_addons = {
        (
            str(item.get("name", "")).strip(),
            str(item.get("simulator", "")).strip(),
            str(item.get("platform", "")).strip(),
        )
        for item in addon_items
        if isinstance(item, dict)
    }
    for default_item in default_addons():
        key = (
            str(default_item.get("name", "")).strip(),
            str(default_item.get("simulator", "")).strip(),
            str(default_item.get("platform", "")).strip(),
        )
        if key not in existing_addons:
            addon_items.append(default_item)
            existing_addons.add(key)
            migrated = True
    expected_packages = {
        "pmdg 737-600": "pmdg-aircraft-736",
        "pmdg 737-700": "pmdg-aircraft-737",
        "pmdg 737-800": "pmdg-aircraft-738",
        "pmdg 737-900": "pmdg-aircraft-739",
        "pmdg 777-300er": "pmdg-aircraft-77w",
        "pmdg 777f": "pmdg-aircraft-77f",
        "pmdg 777-200er": "pmdg-aircraft-77er",
        "pmdg 777-200lr": "pmdg-aircraft-77l",
    }
    for item in addon_items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip().lower()
        package = str(item.get("package_name", "")).strip().lower()
        target = str(item.get("target_path", "")).strip().lower().replace("\\", "/")
        expected_package = expected_packages.get(name)
        if expected_package and package != expected_package:
            item["package_name"] = expected_package
            migrated = True
        if (
            package == "ifly-aircraft-737max8"
            and str(item.get("simulator", "")).strip() == "MSFS 2024"
            and str(item.get("navdata_subpath", "")).strip().lower().replace("/", "\\") != r"work\navdata\permanent"
        ):
            item["navdata_subpath"] = r"work\navdata\Permanent"
            migrated = True
        if (package == "justflight-aircraft-rj" or "rj professional" in name) and "aerosoft-crj" in target:
            item["target_path"] = ""
            migrated = True
    deduped_addons: list[dict] = []
    seen_addon_keys: set[tuple[str, str, str]] = set()
    for item in addon_items:
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("name", "")).strip(),
            str(item.get("simulator", "")).strip(),
            str(item.get("platform", "")).strip(),
        )
        if key in seen_addon_keys:
            migrated = True
            continue
        seen_addon_keys.add(key)
        deduped_addons.append(item)
    addon_items = deduped_addons
    if migrated:
        state["addons"] = addon_items
        save_state(state)
    addons_all = [a for a in (to_addon(item) for item in addon_items) if a is not None]
    default_catalog_signatures: set[tuple[str, str, str, str]] = {
        (
            str(item.get("name", "")).strip(),
            str(item.get("simulator", "")).strip(),
            str(item.get("platform", "")).strip(),
            str(item.get("package_name", "")).strip().lower(),
        )
        for item in default_addons()
        if isinstance(item, dict)
    }
    colors = get_colors(theme_name)

    page.title = "FMS UPDATE MANAGER  | 本软件正在测试中，有问题请联系 qq=168329908"
    page.theme_mode = ft.ThemeMode.DARK if theme_name == THEME_DARK else ft.ThemeMode.LIGHT
    page.bgcolor = colors["root_bg"]
    page.padding = 12
    try:
        page.window.width = 1260
        page.window.height = 700
        page.window.min_width = 1100
        page.window.min_height = 700
    except Exception:
        setattr(page, "window_width", 1260)
        setattr(page, "window_height", 700)
        setattr(page, "window_min_width", 1100)
        setattr(page, "window_min_height", 700)
    try:
        if TASKBAR_ICON_FILE.exists():
            page.window.icon = str(TASKBAR_ICON_FILE)
    except Exception:
        pass

    airac_id_text = ft.Text("----", size=fs(34), weight=ft.FontWeight.BOLD, color=colors["cycle_big"])
    airac_effective_text = ft.Text("本期数据生效日期：--", size=fs(12), color=colors["text_sub"])
    airac_next_text = ft.Text("本期数据将于--月--日到期", size=fs(12), color=colors["text_sub"])

    left_list = ft.ListView(expand=True, spacing=6)
    right_cards_list = ft.Column(expand=True, spacing=10)
    log_list = ft.ListView(height=52, spacing=2, auto_scroll=True)
    log_overlay_list = ft.ListView(expand=True, spacing=6, auto_scroll=True)
    log_overlay_title = ft.Text("活动日志", size=fs(24), weight=ft.FontWeight.BOLD, color=colors["text_title"])
    log_overlay_container = ft.Container(visible=False)
    custom_modal_title = ft.Text("", size=fs(22), weight=ft.FontWeight.BOLD, color=colors["text_title"])
    custom_modal_body = ft.Column(tight=True, spacing=10)
    custom_modal_panel = ft.Container()
    custom_modal_container = ft.Container(visible=False)
    install_overlay_lines: list[str] = []
    install_overlay_list = ft.ListView(expand=True, spacing=6, auto_scroll=True)
    install_overlay_scroll_pending = False
    install_overlay_last_update_ts = 0.0
    install_overlay_update_interval = 0.25
    install_overlay_title_text = "安装状态"
    install_overlay_title = ft.Text(install_overlay_title_text, size=fs(24), weight=ft.FontWeight.BOLD, color=colors["text_title"])
    install_overlay_container = ft.Container(visible=False)
    pending_force_install_action: Callable[[], None] | None = None
    pending_force_install_cancel: Callable[[], None] | None = None
    install_force_button: ft.Button | None = None
    scroll_top_button = ft.Container(visible=True)
    zip_update_picker: ft.FilePicker | None = None
    op_dialog: ft.AlertDialog | None = None
    op_dialog_suppressed = False
    op_dialog_title = ft.Text("", size=fs(18), weight=ft.FontWeight.BOLD)
    op_dialog_status = ft.Text("", size=fs(13), selectable=True)
    op_dialog_detail = ft.Text("", size=fs(12), color=colors["text_sub"], selectable=True)
    op_overlay_container = ft.Container(visible=False)
    op_hide_button = ft.TextButton("返回")
    backup_power_login_valid = False
    one_click_install_filter_button: ft.Button | None = None
    startup_update_check_skip = False
    startup_update_release_url = ""
    startup_update_overlay_container = ft.Container(visible=False)
    startup_update_title = ft.Text("启动检查更新", size=fs(22), weight=ft.FontWeight.BOLD, color=colors["text_title"])
    startup_update_status = ft.Text("准备检查 GitHub Releases...", size=fs(14), color=colors["text_sub"])
    startup_update_detail = ft.Text("", size=fs(12), color=colors["text_meta"], selectable=True)
    startup_update_countdown = ft.Text("", size=fs(12), color=colors["text_meta"])
    startup_update_skip_btn: ft.Button | None = None
    startup_update_download_btn: ft.Button | None = None
    startup_update_continue_btn: ft.Button | None = None


    active_sims = enabled_simulators(state)
    if simulator not in active_sims:
        simulator = active_sims[0]
    if platform not in PLATFORMS:
        platform = PLATFORMS[0]
    if theme_name not in (THEME_LIGHT, THEME_DARK):
        theme_name = THEME_LIGHT

    def ensure_required_community_paths() -> bool:
        key20 = community_key("MSFS 2020", platform)
        key24 = community_key("MSFS 2024", platform)
        key24_extra = platform
        cur20 = str(state.get("community_paths", {}).get(key20, "")).strip()
        cur24 = str(state.get("community_paths", {}).get(key24, "")).strip()
        cur24_extra = str(state.get("community_2024_paths", {}).get(key24_extra, "")).strip()
        has20 = bool(state.get("enabled_simulators", {}).get("MSFS 2020", True))
        has24 = bool(state.get("enabled_simulators", {}).get("MSFS 2024", True))

        ready20 = (not has20) or is_valid_community_path(cur20)
        ready24 = (not has24) or (is_valid_community_path(cur24) and is_valid_community2024_path(cur24_extra))
        if state.get("community_setup_done", False) and (has20 or has24) and ready20 and ready24:
            return True

        has20_check = ft.Checkbox(label="我有 MSFS 2020", value=has20)
        has24_check = ft.Checkbox(label="我有 MSFS 2024", value=has24)
        fs20_field = ft.TextField(
            label="FS20 Community",
            value=cur20 or default_community_base("MSFS 2020", platform),
            expand=True,
        )
        fs24_field = ft.TextField(
            label="FS24 Community",
            value=cur24 or default_community_base("MSFS 2024", platform),
            expand=True,
        )
        fs24_extra_field = ft.TextField(
            label="FS24 Community2024",
            value=cur24_extra,
            hint_text=r"例如 ...\Packages\Community2024",
            expand=True,
        )
        setup_error_text = ft.Text("", size=fs(12), color="#b83d4b")
        browse20_btn = ft.Button("浏览")
        browse24_btn = ft.Button("浏览")
        browse24_extra_btn = ft.Button("浏览")

        for ctrl in list(page.services):
            if isinstance(ctrl, ft.FilePicker) and getattr(ctrl, "data", None) in {"community_picker_20", "community_picker_24", "community_picker_24_extra"}:
                try:
                    page.services.remove(ctrl)
                except ValueError:
                    pass
        picker20 = ft.FilePicker()
        picker20.data = "community_picker_20"
        picker24 = ft.FilePicker()
        picker24.data = "community_picker_24"
        picker24_extra = ft.FilePicker()
        picker24_extra.data = "community_picker_24_extra"
        page.services.extend([picker20, picker24, picker24_extra])

        def browse_fs20(_e) -> None:
            async def runner() -> None:
                try:
                    path = await picker20.get_directory_path(dialog_title="选择 FS20 Community")
                    if path:
                        fs20_field.value = path
                        page.update()
                except Exception as exc:
                    setup_error_text.value = f"选择目录失败: {exc}"
                    page.update()

            page.run_task(runner)

        def browse_fs24(_e) -> None:
            async def runner() -> None:
                try:
                    path = await picker24.get_directory_path(dialog_title="选择 FS24 Community")
                    if path:
                        fs24_field.value = path
                        page.update()
                except Exception as exc:
                    setup_error_text.value = f"选择目录失败: {exc}"
                    page.update()

            page.run_task(runner)

        def browse_fs24_extra(_e) -> None:
            async def runner() -> None:
                try:
                    path = await picker24_extra.get_directory_path(dialog_title="选择 FS24 Community2024")
                    if path:
                        fs24_extra_field.value = path
                        page.update()
                except Exception as exc:
                    setup_error_text.value = f"选择目录失败: {exc}"
                    page.update()

            page.run_task(runner)

        browse20_btn.on_click = browse_fs20
        browse24_btn.on_click = browse_fs24
        browse24_extra_btn.on_click = browse_fs24_extra

        def refresh_setup_field_status() -> None:
            fs20_field.disabled = not bool(has20_check.value)
            browse20_btn.disabled = not bool(has20_check.value)
            fs24_field.disabled = not bool(has24_check.value)
            browse24_btn.disabled = not bool(has24_check.value)
            fs24_extra_field.disabled = not bool(has24_check.value)
            browse24_extra_btn.disabled = not bool(has24_check.value)
            page.update()

        def on_sim_check_change(_e) -> None:
            refresh_setup_field_status()

        has20_check.on_change = on_sim_check_change
        has24_check.on_change = on_sim_check_change

        def save_community_paths(_e) -> None:
            p20 = fs20_field.value.strip()
            p24 = fs24_field.value.strip()
            p24_extra = fs24_extra_field.value.strip()
            has20_selected = bool(has20_check.value)
            has24_selected = bool(has24_check.value)
            if not has20_selected and not has24_selected:
                setup_error_text.value = "至少需要选择一个模拟器（MSFS 2020 或 MSFS 2024）。"
                page.update()
                return
            if has20_selected and not is_valid_community_path(p20):
                setup_error_text.value = "MSFS 2020 已启用，请填写有效的 FS20 Community 路径（目录名需为 Community）。"
                page.update()
                return
            if has24_selected and not is_valid_community_path(p24):
                setup_error_text.value = "MSFS 2024 已启用，请填写有效的 FS24 Community 路径（目录名需为 Community）。"
                page.update()
                return
            if has24_selected and not is_valid_community2024_path(p24_extra):
                setup_error_text.value = "MSFS 2024 已启用，请填写有效的 FS24 Community2024 路径（目录名需为 Community2024 或 Community）。"
                page.update()
                return
            setup_error_text.value = ""
            state.setdefault("community_paths", {})[key20] = p20
            state.setdefault("community_paths", {})[key24] = p24
            state.setdefault("community_2024_paths", {})[key24_extra] = p24_extra
            state.setdefault("enabled_simulators", {})["MSFS 2020"] = has20_selected
            state.setdefault("enabled_simulators", {})["MSFS 2024"] = has24_selected
            current_sim = str(state.get("simulator", simulator))
            enabled_now = enabled_simulators(state)
            state["simulator"] = current_sim if current_sim in enabled_now else enabled_now[0]
            state["community_setup_done"] = True
            save_state(state)
            page.clean()
            main(page, fast_reload=True, cached_cycle=cached_cycle)

        page.clean()
        page.add(
            ft.Container(
                expand=True,
                alignment=ft.Alignment(0, 0),
                content=ft.Container(
                    width=760,
                    border_radius=18,
                    bgcolor=colors["panel_bg"],
                    padding=24,
                    content=ft.Column(
                        tight=True,
                        spacing=16,
                        controls=[
                            ft.Text("首次设置 Community 路径", size=fs(26), weight=ft.FontWeight.BOLD, color=colors["text_title"]),
                            ft.Text(
                                f"当前平台: {platform}\n请先选择你拥有的模拟器，再填写对应路径。",
                                size=fs(13),
                                color=colors["text_sub"],
                            ),
                            ft.Row(spacing=16, controls=[has20_check, has24_check]),
                            ft.Row(
                                spacing=10,
                                controls=[
                                    fs20_field,
                                    browse20_btn,
                                ],
                            ),
                            ft.Row(
                                spacing=10,
                                controls=[
                                    fs24_field,
                                    browse24_btn,
                                ],
                            ),
                            ft.Row(
                                spacing=10,
                                controls=[
                                    fs24_extra_field,
                                    browse24_extra_btn,
                                ],
                            ),
                            ft.Text(
                                "要求：目录必须真实存在；FS20/FS24 路径末级需为 Community，FS24 Community2024 路径末级需为 Community2024 或 Community。",
                                size=fs(12),
                                color=colors["text_meta"],
                            ),
                            setup_error_text,
                            ft.Row(
                                alignment=ft.MainAxisAlignment.END,
                                controls=[
                                    ft.Button(
                                        "保存并继续",
                                        on_click=save_community_paths,
                                        bgcolor="#1a73e8",
                                        color="#ffffff",
                                    )
                                ],
                            ),
                        ],
                    ),
                ),
            )
        )
        refresh_setup_field_status()
        return False

    if not ensure_required_community_paths():
        return

    sim_buttons: dict[str, ft.Button] = {}
    platform_buttons: dict[str, ft.Button] = {}
    theme_buttons: dict[str, ft.Button] = {}

    filter_chips = {
        "All": ft.Button("All"),
        "Installed": ft.Button("Installed"),
        "Update Available": ft.Button("Update Available"),
        "Not Installed": ft.Button("Not Installed"),
    }

    def build_top_action_button(text: str, on_click, icon=None, bgcolor=None, color=None) -> ft.Button:
        return ft.Button(
            text,
            icon=icon,
            on_click=on_click,
            bgcolor=bgcolor if bgcolor is not None else colors["panel_bg"],
            color=color if color is not None else colors["text_meta"],
            height=30,
            style=ft.ButtonStyle(
                padding=ft.Padding.symmetric(horizontal=10, vertical=0),
                shape=ft.RoundedRectangleBorder(radius=14),
            ),
        )

    def build_segment_button(text: str, on_click) -> ft.Button:
        return ft.Button(
            text.upper(),
            height=24,
            color=colors["switch_unsel_fg"],
            bgcolor=colors["switch_unsel_bg"],
            style=ft.ButtonStyle(
                padding=ft.Padding.symmetric(horizontal=10, vertical=0),
                shape=ft.RoundedRectangleBorder(radius=12),
            ),
            on_click=lambda _e: on_click(),
        )

    sim_segment_row = ft.Row(spacing=4)
    for option in active_sims:
        sim_buttons[option] = build_segment_button(option, lambda v=option: set_sim(v))
        sim_segment_row.controls.append(sim_buttons[option])

    platform_segment_row = ft.Row(spacing=4)
    for option in PLATFORMS:
        platform_buttons[option] = build_segment_button(option, lambda v=option: set_platform(v))
        platform_segment_row.controls.append(platform_buttons[option])

    theme_segment_row = ft.Row(spacing=4)
    theme_labels = {THEME_LIGHT: "Light Mode", THEME_DARK: "Dark Mode"}
    for option in (THEME_LIGHT, THEME_DARK):
        theme_buttons[option] = build_segment_button(theme_labels[option], lambda v=option: set_theme(v))
        theme_segment_row.controls.append(theme_buttons[option])

    def try_control_update(control: ft.Control | None) -> bool:
        if control is None:
            return False
        try:
            control.update()
            return True
        except Exception:
            return False

    def update_controls(*controls: ft.Control | None) -> None:
        active_controls = [control for control in controls if control is not None]
        if active_controls:
            try:
                page.update(*active_controls)
                return
            except Exception:
                pass
        page.update()

    def set_button_busy(button: ft.Button | None, busy: bool, busy_text: str | None = None) -> None:
        if button is None:
            return
        try:
            if busy:
                setattr(button, "_busy_active", True)
                if not hasattr(button, "_busy_original_content"):
                    setattr(button, "_busy_original_content", button.content)
                if busy_text is not None:
                    button.content = busy_text
            else:
                setattr(button, "_busy_active", False)
                if hasattr(button, "_busy_original_content"):
                    button.content = cast(Any, getattr(button, "_busy_original_content"))
            update_controls(button)
        except RuntimeError as exc:
            if "Frozen controls cannot be updated" in str(exc):
                log("Skipped busy-state update for frozen button control.")
                return
            raise

    def is_button_busy(button: ft.Button | None) -> bool:
        if button is None:
            return False
        return bool(getattr(button, "_busy_active", False))

    def log(msg: str) -> None:
        line = f"[{human_time()}] {msg}"
        log_list.controls.append(ft.Text(line, size=fs(11), color=colors["log_fg"]))
        if len(log_list.controls) > 300:
            log_list.controls = log_list.controls[-300:]
        append_log_file(f"[{human_datetime()}] {msg}")
        if log_overlay_container.visible:
            refresh_log_overlay()
            update_controls(log_overlay_container)
            return
        update_controls(log_list)

    def try_page_open(control: ft.Control) -> bool:
        open_fn = getattr(page, "open", None)
        if callable(open_fn):
            try:
                open_fn(control)
                if getattr(control, "open", False):
                    return True
            except Exception:
                pass
        try:
            if "dialog" in dir(page):
                setattr(page, "dialog", control)
                setattr(control, "open", True)
                page.update()
                return True
        except Exception:
            pass
        try:
            overlay = getattr(page, "overlay", None)
            if overlay is not None:
                if control not in overlay:
                    overlay.append(control)
                setattr(control, "open", True)
                page.update()
                return True
        except Exception:
            pass
        return False

    def try_page_close(control: ft.Control) -> bool:
        close_fn = getattr(page, "close", None)
        if callable(close_fn):
            try:
                close_fn(control)
                if not getattr(control, "open", False):
                    return True
            except Exception:
                pass
        try:
            if "dialog" in dir(page):
                current_dialog = getattr(page, "dialog", None)
                if current_dialog is control:
                    setattr(control, "open", False)
                    try:
                        setattr(page, "dialog", None)
                    except Exception:
                        pass
                    page.update()
                    return True
        except Exception:
            pass
        try:
            overlay = getattr(page, "overlay", None)
            if overlay is not None:
                if control in overlay:
                    overlay.remove(control)
                else:
                    setattr(control, "open", False)
                page.update()
                return True
        except Exception:
            pass
        try:
            setattr(control, "open", False)
            page.update()
            return True
        except Exception:
            pass
        return False

    def dismiss_dialog(dialog: ft.Control | None) -> None:
        if dialog is None:
            return
        if try_page_close(dialog):
            return
        try:
            if getattr(page, "dialog", None) is dialog:
                setattr(page, "dialog", None)
        except Exception:
            pass
        try:
            overlay = getattr(page, "overlay", None)
            if overlay is not None and dialog in overlay:
                overlay.remove(dialog)
        except Exception:
            pass
        try:
            setattr(dialog, "open", False)
        except Exception:
            pass
        update_controls(dialog)

    def close_custom_modal(_e=None) -> None:
        custom_modal_container.visible = False
        custom_modal_title.value = ""
        custom_modal_body.controls = []
        update_controls(custom_modal_container)

    def open_custom_modal(title: str, controls: list[ft.Control], *, width: int = 820) -> None:
        custom_modal_title.value = title
        custom_modal_body.controls = controls
        custom_modal_panel.width = width
        custom_modal_container.visible = True
        update_controls(custom_modal_container)

    def snack(msg: str) -> None:
        log(msg)
        try:
            if not try_page_open(ft.SnackBar(ft.Text(msg), duration=1800)):
                raise AttributeError("page.open unavailable")
        except Exception:
            snack_bar = ft.SnackBar(ft.Text(msg), duration=1800)
            setattr(page, "snack_bar", snack_bar)
            setattr(snack_bar, "open", True)
            page.update()

    def expand_window_for_update_notice() -> None:
        try:
            page.window.width = max(1360, int(getattr(page.window, "width", 1260) or 1260))
            page.window.height = max(780, int(getattr(page.window, "height", 700) or 700))
            page.window.min_width = max(1200, int(getattr(page.window, "min_width", 1100) or 1100))
            page.window.min_height = max(740, int(getattr(page.window, "min_height", 700) or 700))
        except Exception:
            setattr(page, "window_width", 1360)
            setattr(page, "window_height", 780)
            setattr(page, "window_min_width", 1200)
            setattr(page, "window_min_height", 740)
        page.update()

    def close_startup_update_overlay() -> None:
        startup_update_overlay_container.visible = False
        update_controls(startup_update_overlay_container)

    def set_startup_update_overlay(
        status_text: str,
        detail_text: str = "",
        *,
        countdown_text: str = "",
        show_skip: bool = False,
        show_download: bool = False,
        show_continue: bool = False,
    ) -> None:
        startup_update_status.value = status_text
        startup_update_detail.value = detail_text
        startup_update_countdown.value = countdown_text
        if startup_update_skip_btn is not None:
            startup_update_skip_btn.visible = show_skip
            startup_update_skip_btn.disabled = False
        if startup_update_download_btn is not None:
            startup_update_download_btn.visible = show_download
            startup_update_download_btn.disabled = not bool(startup_update_release_url)
        if startup_update_continue_btn is not None:
            startup_update_continue_btn.visible = show_continue
            startup_update_continue_btn.disabled = False
        startup_update_overlay_container.visible = True
        update_controls(startup_update_overlay_container)

    def open_external_url(url: str) -> None:
        raw = str(url or "").strip()
        if not raw:
            return
        try:
            webbrowser.open(raw, new=2)
            return
        except Exception:
            pass
        try:
            subprocess.Popen(["explorer.exe", raw], shell=False)
        except Exception:
            pass

    def on_startup_update_skip(_e=None) -> None:
        nonlocal startup_update_check_skip
        startup_update_check_skip = True
        close_startup_update_overlay()
        log("启动更新检查: 用户点击跳过。")

    def on_startup_update_download(_e=None) -> None:
        nonlocal startup_update_check_skip
        if startup_update_release_url:
            open_external_url(startup_update_release_url)
        startup_update_check_skip = True
        close_startup_update_overlay()
        log(f"启动更新检查: 打开发布页 {startup_update_release_url}")

    def on_startup_update_continue(_e=None) -> None:
        nonlocal startup_update_check_skip
        startup_update_check_skip = True
        close_startup_update_overlay()
        log("启动更新检查: 用户继续进入主界面。")

    async def run_startup_update_check() -> None:
        nonlocal startup_update_check_skip, startup_update_release_url
        startup_update_check_skip = False
        repo = normalize_github_repo(GITHUB_RELEASE_REPO)
        startup_update_release_url = f"https://github.com/{repo}/releases/latest"
        set_startup_update_overlay(
            "正在检查更新...",
            f"正在访问 GitHub Releases: {repo}",
            show_skip=True,
            show_download=False,
            show_continue=False,
        )

        check_task = asyncio.create_task(asyncio.to_thread(fetch_latest_github_release, repo))
        while not check_task.done():
            if startup_update_check_skip:
                return
            await asyncio.sleep(0.12)

        if startup_update_check_skip:
            return

        try:
            release = check_task.result()
        except Exception as exc:
            log(f"GitHub 更新检查失败: {exc}")
            expand_window_for_update_notice()
            failure_message = "与github通信失败，请手动检查更新或更换网络后重试。"
            for remain in range(3, 0, -1):
                if startup_update_check_skip:
                    return
                set_startup_update_overlay(
                    "更新检查失败",
                    failure_message,
                    countdown_text=f"{remain} 秒后自动进入主界面",
                    show_skip=False,
                    show_download=False,
                    show_continue=False,
                )
                await asyncio.sleep(1)
            close_startup_update_overlay()
            return

        latest_tag = str(release.get("tag_name", "")).strip()
        latest_name = str(release.get("name", "")).strip()
        startup_update_release_url = str(release.get("html_url", "")).strip() or startup_update_release_url
        current_version_label = format_version_display(APP_VERSION)
        latest_version_label = format_version_display(latest_tag or latest_name)
        newest = _is_newer_version(latest_tag or latest_name, APP_VERSION)

        if newest:
            detail = (
                f"当前版本: {current_version_label}\n"
                f"最新版本: {latest_version_label}\n"
                f"发布页: {startup_update_release_url}"
            )
            for remain in range(8, 0, -1):
                if startup_update_check_skip:
                    return
                set_startup_update_overlay(
                    "发现新版本，可从 GitHub Releases 更新。",
                    detail,
                    countdown_text=f"{remain} 秒后自动进入主界面",
                    show_skip=False,
                    show_download=True,
                    show_continue=True,
                )
                await asyncio.sleep(1)
            close_startup_update_overlay()
            return

        set_startup_update_overlay(
            "已是最新版本。",
            f"当前版本: {current_version_label}",
            countdown_text="即将进入主界面...",
            show_skip=False,
            show_download=False,
            show_continue=False,
        )
        await asyncio.sleep(0.8)
        close_startup_update_overlay()

    def show_operation_dialog(title: str, status: str, detail: str = "") -> None:
        nonlocal op_dialog, op_dialog_suppressed
        op_dialog_title.value = title
        op_dialog_status.value = status
        op_dialog_detail.value = detail or "请稍候，任务正在执行中。"

        def hide_click(_e=None) -> None:
            nonlocal op_dialog_suppressed
            op_dialog_suppressed = True
            log("处理中弹窗: 点击返回")
            op_overlay_container.visible = False
            update_controls(op_overlay_container)
            snack("已返回主界面，任务仍在后台执行。")

        if op_dialog_suppressed:
            return
        op_hide_button.on_click = hide_click
        op_overlay_container.visible = True
        update_controls(op_overlay_container)

    def update_operation_dialog(status: str, detail: str = "") -> None:
        if op_dialog_suppressed:
            return
        if not op_overlay_container.visible:
            show_operation_dialog("处理中", status, detail)
            return
        op_dialog_status.value = status
        if detail:
            op_dialog_detail.value = detail
        update_controls(op_overlay_container)

    def close_operation_dialog(reset_suppressed: bool = True) -> None:
        nonlocal op_dialog, op_dialog_suppressed
        if reset_suppressed:
            op_dialog_suppressed = False
        op_overlay_container.visible = False
        update_controls(op_overlay_container)

    def reset_operation_dialog_suppression() -> None:
        nonlocal op_dialog_suppressed
        op_dialog_suppressed = False

    def show_info_dialog(title: str, message: str) -> None:
        def close_dialog(_e=None):
            close_custom_modal()

        try:
            if install_overlay_container.visible:
                close_install_overlay()
        except Exception:
            pass
        try:
            close_operation_dialog()
        except Exception:
            pass

        open_custom_modal(
            title,
            [
                ft.Text(message, selectable=True),
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    controls=[ft.Button("OK", bgcolor="#1a73e8", color="#ffffff", on_click=close_dialog)],
                ),
            ],
            width=760,
        )

    def show_confirm_dialog(title: str, message: str, on_yes, on_no=None) -> None:
        dlg: ft.AlertDialog | None = None

        def close_dialog(_e=None) -> None:
            dismiss_dialog(dlg)

        def yes_click(_e) -> None:
            close_dialog()
            try:
                on_yes()
            except Exception as exc:
                snack(f"确认操作失败: {exc}")

        def no_click(_e) -> None:
            close_dialog()
            if on_no is not None:
                try:
                    on_no()
                except Exception:
                    pass

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Column(
                tight=True,
                spacing=12,
                controls=[
                    ft.Text(message, selectable=True),
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton("取消", on_click=no_click),
                            ft.TextButton("继续", on_click=yes_click),
                        ],
                    ),
                ],
            ),
        )
        try:
            try:
                if not try_page_open(dlg):
                    raise AttributeError("page.open unavailable")
            except Exception:
                setattr(page, "dialog", dlg)
                setattr(dlg, "open", True)
                page.update()
        except Exception:
            setattr(page, "dialog", dlg)
            setattr(dlg, "open", True)
            page.update()

    def find_addon_by_key(key: str) -> Addon | None:
        for addon in addons_all:
            if addon_key(addon) == key:
                return addon
        return None

    def is_default_catalog_addon(addon: Addon) -> bool:
        signature = (
            addon.name.strip(),
            addon.simulator.strip(),
            addon.platform.strip(),
            addon.package_name.strip().lower(),
        )
        return signature in default_catalog_signatures

    def persist_addon_target_path(addon: Addon, target_dir: Path) -> None:
        addon.target_path = str(target_dir)
        updated = False
        package_name = addon.package_name.strip().lower()
        for item in state.get("addons", []) if isinstance(state.get("addons"), list) else []:
            if not isinstance(item, dict):
                continue
            item_name = str(item.get("name", "")).strip()
            item_sim = str(item.get("simulator", "")).strip()
            item_platform = str(item.get("platform", "")).strip()
            item_package = str(item.get("package_name", "")).strip().lower()
            if (
                item_name == addon.name.strip()
                and item_sim == addon.simulator.strip()
                and item_platform == addon.platform.strip()
                and item_package == package_name
            ):
                item["target_path"] = str(target_dir)
                updated = True
                break
        if updated:
            save_state(state)

    async def prompt_manual_addon_target_path(addon: Addon) -> Path | None:
        loop = asyncio.get_running_loop()
        result_future: asyncio.Future[Path | None] = loop.create_future()
        picker_tag = "manual_addon_target_picker"

        for ctrl in list(page.services):
            if isinstance(ctrl, ft.FilePicker) and getattr(ctrl, "data", None) == picker_tag:
                try:
                    page.services.remove(ctrl)
                except ValueError:
                    pass
        picker = ft.FilePicker()
        picker.data = picker_tag
        page.services.append(picker)

        def finish_result(value: Path | None) -> None:
            if not result_future.done():
                result_future.set_result(value)
            try:
                page.services.remove(picker)
            except ValueError:
                pass

        async def pick_dir_async() -> None:
            try:
                picked_path = await picker.get_directory_path(dialog_title=f"选择 {addon.name} 导航数据目录")
            except Exception as exc:
                snack(f"打开目录选择窗口失败: {exc}")
                finish_result(None)
                return
            if not picked_path:
                finish_result(None)
                return
            target_dir = Path(str(picked_path).strip())
            if not target_dir.exists() or not target_dir.is_dir():
                snack(f"目录不存在或不可用: {target_dir}")
                finish_result(None)
                return
            persist_addon_target_path(addon, target_dir)
            snack(f"已保存 {addon.name} 的安装目录: {target_dir}")
            finish_result(target_dir)

        def choose_now() -> None:
            page.run_task(pick_dir_async)

        def cancel_choose() -> None:
            finish_result(None)

        show_confirm_dialog(
            "未检测到安装目录",
            (
                f"{addon.name} 未检测到可用导航数据目录。\n"
                "请点击“继续”手动选择已安装机模的导航数据目录。"
            ),
            on_yes=choose_now,
            on_no=cancel_choose,
        )
        return await result_future

    def selected_install_cycle_for_addon(addon: Addon, fallback_cycle: str) -> str:
        fallback = detect_airac(fallback_cycle)
        install_cycles = state.get("addon_install_cycles", {})
        if not isinstance(install_cycles, dict):
            return fallback
        chosen_raw = str(install_cycles.get(addon_key(addon), "")).strip()
        chosen_cycle = detect_airac(chosen_raw)
        return chosen_cycle if chosen_cycle not in {"", "UNKNOWN"} else fallback

    def perform_archive_update_install(
        addon: Addon,
        target: Path,
        archive_path: Path,
        archive_name: str,
        archive_airac: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> dict:
        if progress_callback is not None:
            progress_callback(f"开始安装: {addon.name}")
        extracted_root: Path | None = None
        try:
            archive_kind = _archive_kind(archive_path)
            payload_airac = "UNKNOWN"
            payload_prefix = ""
            payload_dir: Path | None = None
            if archive_kind == "zip":
                if progress_callback is not None:
                    progress_callback("正在分析 ZIP 安装载荷...")
                archive_payload = inspect_zip_cycle_payload(archive_path)
                if not archive_payload:
                    raise ValueError("压缩包中未找到可用 cycle.json，无法安装")
                payload_prefix = str(archive_payload.get("payload_prefix", "")).strip()
                payload_airac = detect_airac(str(archive_payload.get("airac", "UNKNOWN")))
            else:
                if progress_callback is not None:
                    progress_callback("正在解压压缩包主体文件...")
                extracted_root = extract_archive_to_temp(archive_path, progress_callback=progress_callback)
                if progress_callback is not None:
                    progress_callback("正在定位安装载荷...")
                archive_payload = inspect_extracted_cycle_payload(extracted_root)
                if not archive_payload:
                    raise ValueError("压缩包中未找到可用 cycle.json，无法安装")
                payload_dir = Path(str(archive_payload.get("payload_dir", "")).strip())
                if not payload_dir.exists() or not payload_dir.is_dir():
                    raise ValueError(f"无效安装载荷目录: {payload_dir}")
                payload_airac = detect_airac(str(archive_payload.get("airac", "UNKNOWN")))

            install_base = target
            if is_a346_addon(addon) and re.fullmatch(r"cycle[_-]?[0-9]{4}", target.name, re.IGNORECASE):
                install_base = target.parent
            if install_base.exists() and not install_base.is_dir():
                raise ValueError(f"Target path is not a folder: {install_base}")

            backup_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            safe_name = addon.name.replace("/", "_").replace("\\", "_")
            backup_path: Path | None = None
            if install_base.exists():
                if progress_callback is not None:
                    progress_callback("备份现有导航数据...")
                addon_backup_root = BACKUP_DIR / safe_name
                addon_backup_root.mkdir(parents=True, exist_ok=True)
                backup_path = addon_backup_root / backup_stamp
                shutil.copytree(install_base, backup_path, dirs_exist_ok=True)

                if progress_callback is not None:
                    progress_callback("清理旧文件...")
                for child in install_base.iterdir():
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink(missing_ok=True)
            else:
                install_base.mkdir(parents=True, exist_ok=True)
                if progress_callback is not None:
                    progress_callback("创建安装目录...")

            effective_airac = archive_airac if archive_airac != "UNKNOWN" else payload_airac
            if progress_callback is not None:
                progress_callback("复制新导航数据文件...")
            if archive_kind == "zip":
                extracted_files, install_root = extract_zip_payload_to_target(
                    addon=addon,
                    zip_path=archive_path,
                    install_base=install_base,
                    payload_prefix=payload_prefix,
                    airac=effective_airac,
                )
            else:
                if payload_dir is None:
                    raise ValueError("安装载荷目录无效。")
                extracted_files, install_root = copy_payload_dir_to_target(
                    addon=addon,
                    payload_dir=payload_dir,
                    install_base=install_base,
                    airac=effective_airac,
                )
            if extracted_files <= 0:
                raise ValueError("No files were extracted from archive payload.")

            airac = effective_airac
            if airac == "UNKNOWN":
                airac = read_cycle_from_dir(install_base)
            (install_base / "airac.txt").write_text(f"AIRAC {airac}\n", encoding="utf-8")
            if progress_callback is not None:
                progress_callback(f"安装完成: AIRAC {airac}")
            return {
                "backup_path": str(backup_path) if backup_path else "",
                "airac": airac,
                "install_base": str(install_base),
                "install_root": str(install_root),
                "extracted_files": extracted_files,
                "archive_name": archive_name,
                "extracted_root": str(extracted_root),
            }
        except Exception:
            if extracted_root is not None:
                cleanup_temp_dir(extracted_root)
            raise

    def start_archive_update(
        addon: Addon,
        target: Path,
        archive_path: Path,
        archive_name: str,
        archive_airac: str,
        *,
        show_result_dialog: bool = True,
        run_in_background: bool = True,
    ) -> asyncio.Task[bool] | None:
        async def runner() -> bool:
            install_temp_root: Path | None = None
            try:
                open_install_overlay(title=f"安装状态 - {addon.name}", reset=False)
                log(f"{addon.name}: begin install from archive '{archive_name}'")
                append_install_overlay_line(f"开始安装机型: {addon.name}")
                append_install_overlay_line(f"来源压缩包: {archive_name}")
                result = await run_blocking_with_feedback(
                    perform_archive_update_install,
                    addon,
                    target,
                    archive_path,
                    archive_name,
                    archive_airac,
                    message=f"正在更新 {addon.name}",
                    pulse_interval=0.25,
                    progress_callback=append_install_overlay_line,
                    provide_progress_callback=True,
                    show_page_loading=False,
                )
                install_temp_root_raw = str(result.get("extracted_root", "")).strip()
                if install_temp_root_raw:
                    install_temp_root = Path(install_temp_root_raw)
                if result.get("backup_path"):
                    log(f"{addon.name}: backup created at {result['backup_path']}")
                    append_install_overlay_line(f"已备份旧数据: {result['backup_path']}")
                else:
                    log(f"{addon.name}: no existing data, install performed without backup")
                    append_install_overlay_line("未检测到旧数据，已执行全新安装")
                log(
                    f"{addon.name}: updated to AIRAC {result['airac']} "
                    f"({result['extracted_files']} file(s) installed) from {result['archive_name']}"
                )
                archive_cycle_msg = (
                    f"导航数据更新成功，当前安装的 AIRAC 周期: {archive_airac}（来自压缩包 cycle.json）"
                    if archive_airac != "UNKNOWN"
                    else f"导航数据更新成功，但 cycle.json 未提供 AIRAC，当前周期: {result['airac']}"
                )
                append_install_overlay_line(archive_cycle_msg)
                if show_result_dialog:
                    snack(f"{addon.name} 更新完成: AIRAC {result['airac']}")
                if show_result_dialog:
                    show_info_dialog(
                        "更新完成",
                        (
                            f"{addon.name} 已更新到 AIRAC {result['airac']}。\n"
                            f"安装文件数: {result['extracted_files']}\n"
                            f"来源压缩包: {result['archive_name']}\n"
                            f"{archive_cycle_msg}"
                        ),
                    )
                return True
            except Exception as exc:
                append_install_overlay_line(f"安装失败: {exc}")
                if show_result_dialog:
                    snack(f"{addon.name} 更新失败: {exc}")
                if show_result_dialog:
                    show_info_dialog("更新失败", f"{addon.name} 更新失败。\n\n错误详情：{exc}")
                return False
            finally:
                await asyncio.to_thread(cleanup_backup_power_download_cache, state)
                if install_temp_root is not None:
                    await asyncio.to_thread(cleanup_temp_dir, install_temp_root)
                await rebuild_lists_async(show_loading=False)

        if run_in_background:
            page.run_task(runner)
            return None
        return asyncio.create_task(runner())

    async def on_archive_update_pick_result(
        selected_files,
        addon: Addon,
        target: Path,
        *,
        show_result_dialog: bool = True,
        allow_force_prompt: bool = True,
        wait_for_completion: bool = False,
        reset_overlay: bool = True,
    ) -> bool:
        if selected_files is None:
            log(f"{addon.name}: archive selection canceled")
            return False

        files = selected_files
        if hasattr(selected_files, "files"):
            files = getattr(selected_files, "files")
        if asyncio.iscoroutine(files):
            files = await files
        if not files:
            log(f"{addon.name}: archive selection canceled")
            return False

        selected_file = files[0]
        file_path = getattr(selected_file, "path", None)
        if not file_path:
            snack("未获取到压缩包路径")
            return False
        archive_path = Path(file_path)
        if not archive_path.exists():
            snack(f"压缩包不存在: {archive_path}")
            return False
        if not is_supported_archive_file(archive_path):
            snack(f"不支持的压缩格式: {archive_path.name}")
            return False

        open_install_overlay(title=f"安装状态 - {addon.name}", reset=reset_overlay)
        append_install_overlay_line(f"已选择压缩包: {archive_path.name}")
        log(f"{addon.name}: selected archive {archive_path.name}")
        if not target.exists():
            log(f"{addon.name}: target does not exist yet, it will be created during install: {target}")
            append_install_overlay_line(f"目标目录不存在，将自动创建: {target}")
        else:
            append_install_overlay_line(f"目标目录: {target}")

        try:
            log(f"{addon.name}: parsing archive payload from {archive_path.name}")
            append_install_overlay_line("正在提取 cycle.json 并校验...")
            archive_payload = await run_blocking_with_feedback(
                prepare_archive_payload,
                archive_path,
                message="正在提取并校验 cycle.json",
                pulse_interval=0.25,
                progress_callback=append_install_overlay_line,
                provide_progress_callback=True,
                show_page_loading=False,
            )
        except Exception as exc:
            append_install_overlay_line(f"cycle 校验失败: {exc}")
            snack(f"cycle 校验失败: {exc}")
            if show_result_dialog:
                show_info_dialog(
                    "校验失败",
                    f"{addon.name} cycle.json 校验失败。\n\n压缩包: {archive_path.name}\n错误详情：{exc}",
                )
            await rebuild_lists_async(show_loading=False)
            return False
        if not archive_payload:
            append_install_overlay_line("压缩包中未找到可用 cycle.json，无法安装")
            snack(f"压缩包中未找到可用 cycle.json: {archive_path.name}")
            if show_result_dialog:
                show_info_dialog(
                    "压缩包无效",
                    f"{archive_path.name} 中未找到可用 cycle.json，无法继续安装。",
                )
            await rebuild_lists_async(show_loading=False)
            return False
        await rebuild_lists_async(show_loading=False)

        probe_root_raw = str(archive_payload.get("probe_root", "")).strip()
        probe_root = Path(probe_root_raw) if probe_root_raw else None
        payload_prefix = str(archive_payload.get("payload_prefix", "")).strip()
        archive_airac = str(archive_payload.get("airac", "UNKNOWN"))
        cycle_name = str(archive_payload.get("cycle_name", "")).strip()
        log(
            f"{addon.name}: archive parsed, cycle_name='{cycle_name or '<empty>'}', "
            f"airac={archive_airac}, payload_prefix='{payload_prefix or '<root>'}'"
        )
        append_install_overlay_line(
            f"压缩包校验完成: 机型名称 '{cycle_name or '空'}'，AIRAC {archive_airac}"
        )
        if probe_root is not None:
            await asyncio.to_thread(cleanup_temp_dir, probe_root)

        async def continue_install_async() -> bool:
            log(f"{addon.name}: archive validation passed, installing...")
            append_install_overlay_line("压缩包校验通过，开始解压并安装...")
            clear_force_install_prompt(refresh=False)
            task = start_archive_update(
                addon=addon,
                target=target,
                archive_path=archive_path,
                archive_name=archive_path.name,
                archive_airac=archive_airac,
                show_result_dialog=show_result_dialog,
                run_in_background=not wait_for_completion,
            )
            if wait_for_completion and task is not None:
                return bool(await task)
            return True

        def continue_install() -> None:
            page.run_task(continue_install_async)

        def cancel_install(reason: str) -> None:
            log(f"{addon.name}: update canceled by user ({reason})")
            append_install_overlay_line(f"用户取消安装（{reason}）")

        cycle_name_norm = cycle_name.strip().lower()
        if not cycle_name_norm:
            if not allow_force_prompt:
                log(f"{addon.name}: cycle.json name empty, skipped in batch mode")
                append_install_overlay_line("cycle.json 的 name 为空，批量模式下已跳过")
                return False
            log(f"{addon.name}: cycle.json name is empty, waiting for user confirmation")
            set_force_install_prompt(
                "cycle.json 的 name 字段为空，无法校验机型匹配",
                on_force=continue_install,
                on_cancel=lambda: cancel_install("cycle.json name 为空"),
            )
            snack("cycle.json 的 name 为空，请点击“强制安装”继续。")
            return False
        if not cycle_name_matches_addon(addon, cycle_name):
            if not allow_force_prompt:
                log(f"{addon.name}: cycle name mismatch in batch mode (archive='{cycle_name}')")
                append_install_overlay_line(f"机型名称不匹配，批量模式下已跳过: {cycle_name}")
                return False
            log(
                f"{addon.name}: cycle name mismatch detected (archive='{cycle_name}', addon='{addon.name}'), "
                "waiting for user confirmation"
            )
            set_force_install_prompt(
                f"机型名称不匹配（压缩包: {cycle_name}，当前机型: {addon.name}）",
                on_force=continue_install,
                on_cancel=lambda: cancel_install(f"机型名称不匹配: {cycle_name}"),
            )
            snack("检测到机型名称不匹配，请点击“强制安装”继续。")
            return False
        return await continue_install_async()

    async def on_update_navdata_click(
        addon_key_value: str,
        trigger_button: ft.Button | None = None,
        *,
        bulk_mode: bool = False,
        forced_cycle_id: str | None = None,
        show_result_dialog: bool = True,
        reset_overlay: bool = True,
        wait_for_install: bool = False,
    ) -> bool:
        try:
            addon = find_addon_by_key(addon_key_value)
            if addon is None:
                snack("未找到对应机型。")
                return False
            if bulk_mode and not is_default_catalog_addon(addon):
                append_install_overlay_line(f"{addon.name}: 跳过（手动添加机型需手动选包）")
                return False
            target = resolve_target_dir(addon, state)
            inferred_from_wasm = False
            if target is None:
                target = resolve_wasm_target_by_folder_name(addon, state)
                inferred_from_wasm = target is not None
                if target is None and not bulk_mode and not is_default_catalog_addon(addon):
                    target = await prompt_manual_addon_target_path(addon)
                    if target is None:
                        snack("未选择路径，已取消本次更新。")
                        return False
                    log(f"{addon.name}: using user-selected target {target}")
                if target is None:
                    message = "未检测到已安装数据。请先确认 WASM 下存在对应机型文件夹名称。"
                    if bulk_mode:
                        append_install_overlay_line(f"{addon.name}: {message}")
                    else:
                        snack(message)
                    return False
                if inferred_from_wasm:
                    log(f"{addon.name}: no installed navdata found, using WASM inferred target {target}")
            log(f"{addon.name}: update requested, target={target}")
            if target.exists() and not target.is_dir():
                message = f"目标路径不是文件夹: {target}"
                if bulk_mode:
                    append_install_overlay_line(f"{addon.name}: {message}")
                else:
                    snack(message)
                return False
            if not target.exists() and not target.parent.exists():
                message = f"目标父目录不存在: {target.parent}"
                if bulk_mode:
                    append_install_overlay_line(f"{addon.name}: {message}")
                else:
                    snack(message)
                return False
            token = str(state.get("backup_power_token", "")).strip()
            can_auto_download = False
            if token and is_default_catalog_addon(addon):
                can_auto_download = await refresh_backup_power_login_validity(notify_invalid=False)
                if not can_auto_download:
                    manual_only_message = "DATA(data.cnrpg.top) 登录状态失效，仅支持手动选择本地压缩包安装。"
                    log(f"{addon.name}: {manual_only_message}")
                    if bulk_mode:
                        append_install_overlay_line(f"{addon.name}: 跳过（登录失效，批量模式不允许手动选包）")
                        return False
                    snack(manual_only_message)
            if can_auto_download and is_default_catalog_addon(addon):
                cycle_id = detect_airac(str(forced_cycle_id or ""))
                if cycle_id in {"", "UNKNOWN"} and current_cycle_info and current_cycle_info.get("cycle_id"):
                    cycle_id = detect_airac(str(current_cycle_info.get("cycle_id", "")))
                if cycle_id in {"", "UNKNOWN"}:
                    cycle_info = await asyncio.to_thread(fetch_current_cycle)
                    if cycle_info and cycle_info.get("cycle_id"):
                        cycle_id = detect_airac(str(cycle_info.get("cycle_id", "")))
                if cycle_id in {"", "UNKNOWN"}:
                    message = "未获取到有效 AIRAC 期数，无法自动下载。"
                    if bulk_mode:
                        append_install_overlay_line(f"{addon.name}: {message}")
                    else:
                        snack(message)
                    return False
                download_dir = ensure_backup_power_download_dir(str(default_backup_power_download_dir(state)), create=True)
                try:
                    if bulk_mode:
                        if not install_overlay_container.visible:
                            open_install_overlay(title=f"安装状态 - {addon.name}", reset=reset_overlay)
                    else:
                        open_install_overlay(title=f"安装状态 - {addon.name}", reset=reset_overlay)
                    append_install_overlay_line(f"自动模式: OpenList /{cycle_id}/MSFS")
                    result = await run_blocking_with_feedback(
                        download_openlist_archive_for_addon,
                        addon,
                        cycle_id,
                        download_dir,
                        message=f"正在从 OpenList 下载 {addon.name}",
                        pulse_interval=0.25,
                        progress_callback=append_install_overlay_line,
                        provide_progress_callback=True,
                        show_page_loading=False,
                    )
                    archive_path = Path(str(result.get("archive_path", "")).strip())
                    if not archive_path.exists():
                        raise ValueError(f"自动下载后未找到压缩包: {archive_path}")
                    log(f"{addon.name}: OpenList auto archive selected {archive_path}")
                    append_install_overlay_line(f"已自动下载压缩包: {archive_path.name}")
                    picked = [type("PickedFile", (), {"path": str(archive_path)})()]
                    return await on_archive_update_pick_result(
                        picked,
                        addon,
                        target,
                        show_result_dialog=show_result_dialog,
                        allow_force_prompt=not bulk_mode,
                        wait_for_completion=wait_for_install,
                        reset_overlay=False,
                    )
                except Exception as exc:
                    if bulk_mode:
                        log(f"{addon.name}: OpenList auto download failed in batch mode ({exc})")
                        append_install_overlay_line(f"{addon.name}: 自动下载失败: {exc}")
                        return False
                    log(f"{addon.name}: OpenList auto download failed, fallback to manual picker ({exc})")
                    snack(f"自动下载失败，已切换手动选包: {exc}")
            if bulk_mode:
                append_install_overlay_line(f"{addon.name}: 跳过（当前模式不允许手动选包）")
                return False
            if zip_update_picker is None:
                snack("压缩包选择器未初始化")
                return False
            try:
                selected_files = await zip_update_picker.pick_files(
                    dialog_title=f"选择 {addon.name} 导航数据压缩包",
                    allow_multiple=False,
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["zip", "7z", "rar", "tar", "gz", "tgz", "bz2", "tbz", "tbz2", "xz", "txz", "exe"],
                )
                return await on_archive_update_pick_result(
                    selected_files,
                    addon,
                    target,
                    show_result_dialog=show_result_dialog,
                    allow_force_prompt=True,
                    wait_for_completion=wait_for_install,
                    reset_overlay=True,
                )
            except Exception as exc:
                snack(f"打开压缩包选择窗口失败: {exc}")
                return False
        finally:
            set_button_busy(trigger_button, False)

    def make_update_click_handler(addon_key_value: str):
        def _handler(e) -> None:
            button = e.control if isinstance(getattr(e, "control", None), ft.Button) else None
            if is_button_busy(button):
                snack("任务正在处理中，请稍候。")
                return
            reset_operation_dialog_suppression()
            set_button_busy(button, True, "处理中...")
            page.run_task(on_update_navdata_click, addon_key_value, button)

        return _handler

    for ctrl in list(page.services):
        if isinstance(ctrl, ft.FilePicker) and getattr(ctrl, "data", None) == "zip_update_picker":
            try:
                page.services.remove(ctrl)
            except ValueError:
                pass
    zip_update_picker = ft.FilePicker()
    zip_update_picker.data = "zip_update_picker"
    page.services.append(zip_update_picker)

    def refresh_log_overlay() -> None:
        lines = read_log_lines(limit=400)
        log_count = len(lines)
        if not lines:
            lines = ["暂无当日日志"]
        today_text = datetime.now().strftime("%Y-%m-%d")
        log_overlay_title.value = f"活动日志（{today_text}）({log_count})"
        log_overlay_list.controls = [
            ft.Container(
                border_radius=10,
                bgcolor=colors["panel_soft_bg"],
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                content=ft.Text(line, size=fs(12), color=colors["log_fg"], selectable=True),
            )
            for line in lines
        ]

    def close_log_overlay(_e=None) -> None:
        log_overlay_container.visible = False
        update_controls(log_overlay_container)

    def open_log_overlay() -> None:
        refresh_log_overlay()
        log_overlay_container.visible = True
        update_controls(log_overlay_container)

    def refresh_install_overlay() -> None:
        lines = install_overlay_lines[-240:] if install_overlay_lines else ["暂无安装日志"]
        install_overlay_title.value = f"{install_overlay_title_text} ({len(lines)})"
        install_overlay_list.controls = [
            ft.Container(
                border_radius=10,
                bgcolor=colors["panel_soft_bg"],
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                content=ft.Text(line, size=fs(12), color=colors["log_fg"], selectable=True),
            )
            for line in lines
        ]

    def refresh_install_overlay_if_needed(force: bool = False) -> None:
        nonlocal install_overlay_last_update_ts
        now = time.monotonic()
        if not force and now - install_overlay_last_update_ts < install_overlay_update_interval:
            return
        install_overlay_last_update_ts = now
        refresh_install_overlay()
        if install_overlay_container.visible:
            page.update()
            schedule_install_overlay_scroll_to_bottom()

    def schedule_install_overlay_scroll_to_bottom() -> None:
        nonlocal install_overlay_scroll_pending
        if install_overlay_scroll_pending:
            return
        install_overlay_scroll_pending = True

        async def runner() -> None:
            nonlocal install_overlay_scroll_pending
            try:
                await asyncio.sleep(0)
                await install_overlay_list.scroll_to(offset=-1, duration=0)
                page.update()
            except Exception:
                pass
            finally:
                install_overlay_scroll_pending = False

        page.run_task(runner)

    def append_install_overlay_line(message: str, *, with_timestamp: bool = True, refresh: bool = True) -> None:
        text = message.strip()
        if not text:
            return
        line = f"[{human_time()}] {text}" if with_timestamp else text
        install_overlay_lines.append(line)
        if len(install_overlay_lines) > 1200:
            install_overlay_lines[:] = install_overlay_lines[-1200:]
        if refresh:
            refresh_install_overlay_if_needed(force=False)

    def clear_force_install_prompt(*, refresh: bool = True) -> None:
        nonlocal pending_force_install_action, pending_force_install_cancel
        pending_force_install_action = None
        pending_force_install_cancel = None
        if install_force_button is not None:
            install_force_button.visible = False
            install_force_button.disabled = True
        if refresh and install_overlay_container.visible:
            page.update()

    def set_force_install_prompt(
        reason: str,
        on_force: Callable[[], None],
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        nonlocal pending_force_install_action, pending_force_install_cancel
        pending_force_install_action = on_force
        pending_force_install_cancel = on_cancel
        if install_force_button is not None:
            install_force_button.visible = True
            install_force_button.disabled = False
        append_install_overlay_line(f"{reason}。如确认无误，请点击右上角“强制安装”继续。")
        if install_overlay_container.visible:
            page.update()
            schedule_install_overlay_scroll_to_bottom()

    def invoke_callback(callback: Callable[[], None]) -> None:
        callback()

    def run_pending_force_install(_e=None) -> None:
        action = pending_force_install_action
        if not callable(action):
            snack("当前没有待确认的强制安装任务。")
            return
        clear_force_install_prompt(refresh=False)
        try:
            append_install_overlay_line("用户点击“强制安装”，继续执行安装。")
            invoke_callback(action)
        except Exception as exc:
            snack(f"强制安装执行失败: {exc}")
            append_install_overlay_line(f"强制安装执行失败: {exc}")
        finally:
            if install_overlay_container.visible:
                page.update()

    def cancel_pending_force_install(reason: str | None = None) -> None:
        cancel_cb = pending_force_install_cancel
        clear_force_install_prompt(refresh=False)
        if reason:
            append_install_overlay_line(reason)
        if callable(cancel_cb):
            try:
                invoke_callback(cancel_cb)
            except Exception:
                pass
        if install_overlay_container.visible:
            page.update()

    def open_install_overlay(title: str = "安装状态", reset: bool = False) -> None:
        nonlocal install_overlay_title_text
        if reset:
            install_overlay_lines.clear()
            clear_force_install_prompt(refresh=False)
        install_overlay_title_text = title
        refresh_install_overlay_if_needed(force=True)
        install_overlay_container.visible = True
        page.update()
        schedule_install_overlay_scroll_to_bottom()

    def close_install_overlay(_e=None) -> None:
        if pending_force_install_action is not None:
            cancel_pending_force_install("用户关闭安装状态窗口，已取消待确认安装。")
        install_overlay_container.visible = False
        page.update()

    def clear_install_overlay(_e=None) -> None:
        install_overlay_lines.clear()
        refresh_install_overlay_if_needed(force=True)
        page.update()

    def on_scroll_top_click(_e) -> None:
        async def scroll_top() -> None:
            try:
                await right_scroll_col.scroll_to(offset=0, duration=260)
                page.update()
            except Exception as exc:
                log(f"Scroll top failed: {exc}")

        page.run_task(scroll_top)

    def focus_explorer_window(title_hint: str | None = None) -> None:
        try:
            user32 = ctypes.windll.user32
            title_hint_l = (title_hint or "").lower()
            target_hwnd = ctypes.c_void_p()
            enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

            def cb(hwnd, _lparam):
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.lower()
                class_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, class_buf, 256)
                if class_buf.value in ("CabinetWClass", "ExploreWClass"):
                    if not title_hint_l or title_hint_l in title:
                        target_hwnd.value = hwnd
                        return False
                return True

            user32.EnumWindows(enum_proc(cb), 0)
            if target_hwnd.value:
                user32.ShowWindow(target_hwnd.value, 9)
                user32.SetForegroundWindow(target_hwnd.value)
        except Exception:
            pass

    def masked_path_text(path_text: str) -> str:
        if not path_text:
            return "Target path not set"
        if streamer_mode:
            return "路径已隐藏（主播模式）"
        return path_text

    def open_folder(path_text: str) -> None:
        if not path_text:
            snack("目标路径未设置")
            return
        p = Path(path_text)
        if p.exists():
            subprocess.Popen(["explorer.exe", str(p)], shell=False)
            focus_explorer_window(p.name)
            log(f"Opened folder: {p}")
            return
        if p.parent.exists():
            subprocess.Popen(["explorer.exe", str(p.parent)], shell=False)
            focus_explorer_window(p.parent.name)
            snack(f"目标文件夹不存在，已打开上级目录: {p.parent}")
            return
        snack(f"路径不存在: {path_text}")

    def refresh_cycle() -> None:
        nonlocal current_cycle_info
        try:
            info = fetch_current_cycle()
            current_cycle_info = info
            if info:
                cycle_id = str(info["cycle_id"])
                start_text = info["start"].astimezone().strftime("%Y-%m-%d")
                end_text = info["end"].astimezone().strftime("%Y-%m-%d")
                days_left = max(0, (info["end"] - datetime.now(timezone.utc)).days)
                airac_id_text.value = cycle_id
                airac_effective_text.value = f"本期数据生效日期：{start_text}"
                end_text_mmdd = info["end"].astimezone().strftime("%m月%d日")
                airac_next_text.value = f"本期数据将于{end_text_mmdd}到期（还有{days_left}天）"
                log(f"AIRAC current cycle fetched: {cycle_id} (effective {start_text}, end {end_text})")
            else:
                airac_id_text.value = "--"
                airac_effective_text.value = "本期数据生效日期：--"
                airac_next_text.value = "本期数据将于--月--日到期"
            update_controls(airac_id_text, airac_effective_text, airac_next_text)
        except Exception as exc:
            current_cycle_info = None
            airac_id_text.value = "--"
            airac_effective_text.value = "本期数据生效日期：--"
            airac_next_text.value = "本期数据将于--月--日到期"
            update_controls(airac_id_text, airac_effective_text, airac_next_text)
            snack(f"刷新周期失败: {exc}")

    def visible_addons() -> list[Addon]:
        current_sim = simulator
        current_platform = platform
        items = [a for a in addons_all if a.simulator == current_sim and a.platform == current_platform]
        q = search_text.strip().lower()
        if not q:
            return items
        return [
            a
            for a in items
            if q in a.name.lower()
            or q in a.description.lower()
            or q in infer_package_name(a).lower()
        ]

    def rescan_sources() -> tuple[int, int]:
        source_dir = Path(str(state.get("source_dir", ""))).expanduser()
        if not source_dir.exists():
            source_dir = Path(__file__).resolve().parent
        zips = list(source_dir.glob("*.zip"))
        extracted = [p for p in EXTRACTED_DIR.iterdir() if p.is_dir()] if EXTRACTED_DIR.exists() else []
        clear_cycle_json_scan_cache()
        return len(zips), len(extracted)

    def rebuild_lists(
        scroll_to_key: str | None = None,
        precomputed_entries: list[tuple[Addon, str, str, str, str, str]] | None = None,
    ) -> None:
        nonlocal filter_value, selected_addon_key, last_rendered_entries
        api_cycle = "NONE"
        if current_cycle_info and current_cycle_info.get("cycle_id"):
            api_cycle = str(current_cycle_info["cycle_id"])

        left_rows: list[ft.Control] = []
        cards: list[ft.Control] = []
        entries = list(precomputed_entries) if precomputed_entries is not None else compute_filtered_addon_entries(
            addons_all=addons_all,
            simulator=simulator,
            platform=platform,
            search_text=search_text,
            filter_value=filter_value,
            api_cycle=api_cycle,
            state=state,
        )
        last_rendered_entries = entries
        scroll_token_by_addon: dict[str, ft.ScrollKey] = {}

        # Keep selection valid when profile/filter changes.
        if selected_addon_key and not any(k == selected_addon_key for _a, k, _s, _i, _api, _t in entries):
            selected_addon_key = None

        def on_left_addon_click(key: str) -> None:
            nonlocal selected_addon_key
            selected_addon_key = key
            rebuild_lists(scroll_to_key=key, precomputed_entries=last_rendered_entries)

        for addon, key, status, installed, api, target in entries:
            is_selected = key == selected_addon_key
            left_rows.append(
                ft.Container(
                    border_radius=12,
                    bgcolor=colors["list_sel_bg"] if is_selected else colors["list_bg"],
                    border=ft.Border.all(3 if is_selected else 1, "#1a73e8" if is_selected else "#2f3c52"),
                    shadow=(
                        ft.BoxShadow(blur_radius=12, spread_radius=2, color="#1a73e840")
                        if is_selected
                        else None
                    ),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                    on_click=lambda _e, k=key: on_left_addon_click(k),
                    content=ft.Row(
                        controls=[
                            ft.Text("●", color=status_dot_color(status), size=fs(12)),
                            ft.Text(
                                addon.name,
                                size=fs(13),
                                weight=ft.FontWeight.W_700 if is_selected else ft.FontWeight.W_600,
                                color=colors["list_sel_fg"] if is_selected else colors["list_fg"],
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            )

        for idx, (addon, key, status, installed, api, target) in enumerate(entries):
            marker = f"card-{idx}"
            scroll_token = ft.ScrollKey(marker)
            scroll_token_by_addon[key] = scroll_token
            badge_bg, badge_fg = status_badge_style(status)
            is_selected = key == selected_addon_key
            cards.append(
                ft.Container(
                    key=scroll_token,
                    border_radius=16,
                    bgcolor=colors["card_bg"],
                    border=ft.Border.all(3 if is_selected else 1, "#1a73e8" if is_selected else "#2f3c52"),
                    shadow=(
                        ft.BoxShadow(blur_radius=12, spread_radius=2, color="#1a73e840")
                        if is_selected
                        else None
                    ),
                    padding=12,
                    content=ft.Column(
                        spacing=6,
                        controls=[
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.Column(
                                        spacing=2,
                                        controls=[
                                            ft.Text(addon.name, size=fs(18), weight=ft.FontWeight.BOLD, color=colors["card_title"]),
                                            ft.Text(addon.description, size=fs(12), color=colors["card_sub"]),
                                        ],
                                    ),
                                    ft.Container(
                                        bgcolor=badge_bg,
                                        border_radius=999,
                                        padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                                        content=ft.Text(status, size=fs(11), weight=ft.FontWeight.W_700, color=badge_fg),
                                    ),
                                ],
                            ),
                            ft.Text(f"已安装: {installed}    API: {api}", size=fs(12), color=colors["card_meta"]),
                            ft.Text(
                                "未检测到 cycle.json / cycle_info.txt\n建议点击「打开目录」检查文件夹结构",
                                size=fs(11),
                                color="#c99600",
                                italic=True,
                            ) if status == "UPDATE READY" and installed == "UNKNOWN" else ft.Container(),
                            ft.Text(masked_path_text(target), size=fs(12), color=colors["text_path"]),
                            ft.Row(
                                spacing=6,
                                controls=[
                                    ft.Button(
                                        "更新导航数据",
                                        icon=ft.Icons.UPLOAD_FILE,
                                        bgcolor="#1a73e8",
                                        color="#ffffff",
                                        height=30,
                                        style=ft.ButtonStyle(
                                            padding=ft.Padding.symmetric(horizontal=10, vertical=0),
                                        ),
                                        on_click=make_update_click_handler(key),
                                    ),
                                    ft.Button(
                                        "打开目录",
                                        icon=ft.Icons.FOLDER_OPEN,
                                        bgcolor=colors["panel_bg"],
                                        color=colors["text_meta"],
                                        height=30,
                                        style=ft.ButtonStyle(
                                            padding=ft.Padding.symmetric(horizontal=10, vertical=0),
                                        ),
                                        on_click=lambda _e, p=target: open_folder(p),
                                    ),
                                    ft.Button(
                                        "恢复",
                                        icon=ft.Icons.RESTORE,
                                        bgcolor="#b83d4b",
                                        color="#ffffff",
                                        height=30,
                                        style=ft.ButtonStyle(
                                            padding=ft.Padding.symmetric(horizontal=10, vertical=0),
                                        ),
                                        on_click=lambda _e, n=addon.name: snack(f"{n}: 备份恢复流程下一步迁移"),
                                    ),
                                ],
                            ),
                        ],
                    ),
                )
            )

        if not left_rows:
            left_rows = [ft.Text("No addons", size=fs(12), color=colors["text_sub"])]
        if not cards:
            cards = [
                ft.Container(
                    border_radius=16,
                    bgcolor=colors["card_bg"],
                    border=ft.Border.all(1, "#2f3c52"),
                    padding=24,
                    content=ft.Column(
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.INBOX_OUTLINED, size=58, color=colors["text_sub"]),
                            ft.Text("暂无该过滤条件的机型", size=fs(16), weight=ft.FontWeight.W_700, color=colors["text_meta"]),
                            ft.Button(
                                "重置筛选",
                                icon=ft.Icons.RESTART_ALT,
                                on_click=lambda _e: on_filter_change("All"),
                                bgcolor=colors["panel_bg"],
                                color=colors["text_meta"],
                            ),
                        ],
                    ),
                )
            ]

        left_list.controls = left_rows
        right_cards_list.controls = cards
        update_controls(left_list, right_cards_list)
        if scroll_to_key:
            async def safe_scroll() -> None:
                await asyncio.sleep(0.08)
                try:
                    token = scroll_token_by_addon.get(scroll_to_key)
                    if token is not None:
                        await right_scroll_col.scroll_to(scroll_key=token, duration=220)
                        update_controls(right_scroll_col)
                        return
                    target_idx = next((i for i, (_addon, key, *_rest) in enumerate(entries) if key == scroll_to_key), None)
                    if target_idx is not None:
                        await right_scroll_col.scroll_to(offset=max(0, target_idx * 230), duration=220)
                        update_controls(right_scroll_col)
                except Exception as exc:
                    log(f"Scroll jump failed: {exc}")

            page.run_task(safe_scroll)

    async def refresh_cycle_async(notify_fail: bool = True) -> None:
        nonlocal current_cycle_info
        try:
            info = await asyncio.to_thread(fetch_current_cycle)
            current_cycle_info = info
            if info:
                cycle_id = str(info["cycle_id"])
                start_text = info["start"].astimezone().strftime("%Y-%m-%d")
                end_text = info["end"].astimezone().strftime("%Y-%m-%d")
                days_left = max(0, (info["end"] - datetime.now(timezone.utc)).days)
                airac_id_text.value = cycle_id
                airac_effective_text.value = f"本期数据生效日期：{start_text}"
                end_text_mmdd = info["end"].astimezone().strftime("%m月%d日")
                airac_next_text.value = f"本期数据将于{end_text_mmdd}到期（还有{days_left}天）"
                log(f"AIRAC current cycle fetched: {cycle_id} (effective {start_text}, end {end_text})")
            else:
                airac_id_text.value = "--"
                airac_effective_text.value = "本期数据生效日期：--"
                airac_next_text.value = "本期数据将于--月--日到期"
            update_controls(airac_id_text, airac_effective_text, airac_next_text)
        except Exception as exc:
            current_cycle_info = None
            airac_id_text.value = "--"
            airac_effective_text.value = "本期数据生效日期：--"
            airac_next_text.value = "本期数据将于--月--日到期"
            update_controls(airac_id_text, airac_effective_text, airac_next_text)
            if notify_fail:
                snack(f"刷新周期失败: {exc}")
            else:
                log(f"刷新周期失败: {exc}")

    def show_loading_state(message: str) -> None:
        left_list.controls = [ft.Text(message, size=fs(12), color=colors["text_sub"])]
        right_cards_list.controls = [
            ft.Container(
                border_radius=16,
                bgcolor=colors["card_bg"],
                border=ft.Border.all(1, "#2f3c52"),
                padding=24,
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.ProgressRing(width=28, height=28, stroke_width=3),
                        ft.Text(message, size=fs(16), weight=ft.FontWeight.W_700, color=colors["text_meta"]),
                    ],
                ),
            )
        ]
        page.update()

    async def run_blocking_with_feedback(
        func: Callable[..., Any],
        *args,
        message: str,
        pulse_interval: float = 1.0,
        progress_callback: Callable[[str], None] | None = None,
        provide_progress_callback: bool = False,
        show_page_loading: bool = False,
        show_operation_dialog_ui: bool = True,
    ) -> Any:
        if show_page_loading:
            show_loading_state(message)
        if show_operation_dialog_ui:
            show_operation_dialog("处理中", message, "已耗时 0s")
        progress_queue: SimpleQueue[str] = SimpleQueue()

        def worker_progress(line: str) -> None:
            text = str(line).strip()
            if text:
                progress_queue.put(text)

        def flush_progress_queue() -> None:
            if progress_callback is None:
                while True:
                    try:
                        progress_queue.get_nowait()
                    except Empty:
                        break
                return
            batch_lines: list[str] = []
            while True:
                try:
                    line = progress_queue.get_nowait()
                except Empty:
                    break
                batch_lines.append(line)
            if not batch_lines:
                return
            if progress_callback is append_install_overlay_line:
                for line in batch_lines:
                    append_install_overlay_line(line, refresh=False)
                refresh_install_overlay_if_needed(force=True)
                return
            for line in batch_lines:
                progress_callback(line)

        if provide_progress_callback:
            task = asyncio.create_task(asyncio.to_thread(func, *args, worker_progress))
        else:
            task = asyncio.create_task(asyncio.to_thread(func, *args))
        start_ts = asyncio.get_running_loop().time()
        dot_count = 0
        try:
            while not task.done():
                await asyncio.sleep(pulse_interval)
                flush_progress_queue()
                if task.done():
                    break
                dot_count = (dot_count + 1) % 4
                elapsed = int(asyncio.get_running_loop().time() - start_ts)
                dots = "." * dot_count
                step_msg = f"{message}{dots} ({elapsed}s)"
                if show_page_loading and not op_dialog_suppressed:
                    show_loading_state(step_msg)
                if show_operation_dialog_ui:
                    update_operation_dialog(step_msg, f"已耗时 {elapsed}s")
            result = await task
            flush_progress_queue()
            return result
        finally:
            flush_progress_queue()
            if show_operation_dialog_ui:
                close_operation_dialog(reset_suppressed=False)

    async def rebuild_lists_async(scroll_to_key: str | None = None, show_loading: bool = False) -> None:
        nonlocal rebuild_generation
        rebuild_generation += 1
        generation = rebuild_generation
        if show_loading:
            show_loading_state("正在扫描机型状态...")
        api_cycle = "NONE"
        if current_cycle_info and current_cycle_info.get("cycle_id"):
            api_cycle = str(current_cycle_info["cycle_id"])
        entries = await asyncio.to_thread(
            compute_filtered_addon_entries,
            addons_all,
            simulator,
            platform,
            search_text,
            filter_value,
            api_cycle,
            state,
        )
        if generation != rebuild_generation:
            return
        rebuild_lists(scroll_to_key=scroll_to_key, precomputed_entries=entries)

    def trigger_rebuild(scroll_to_key: str | None = None, show_loading: bool = False) -> None:
        async def runner() -> None:
            await rebuild_lists_async(scroll_to_key=scroll_to_key, show_loading=show_loading)

        page.run_task(runner)

    async def rescan_and_rebuild_async(show_loading: bool = False, notify_done: bool = False) -> None:
        try:
            if show_loading:
                show_loading_state("正在重新扫描资源...")
            zip_count, extracted_count = await asyncio.to_thread(rescan_sources)
            log(f"Rescanned source: {zip_count} zip(s), {extracted_count} extracted package(s).")
            await rebuild_lists_async(show_loading=False)
            if notify_done:
                snack("已重新扫描并刷新机型列表。")
        except Exception as exc:
            snack(f"重新扫描失败: {exc}")

    def on_refresh_click(e):
        button = e.control if isinstance(getattr(e, "control", None), ft.Button) else None
        if is_button_busy(button):
            snack("刷新任务正在进行中，请稍候。")
            return
        reset_operation_dialog_suppression()
        set_button_busy(button, True, "刷新中...")

        async def runner() -> None:
            try:
                airac_id_text.value = "..."
                airac_effective_text.value = "本期数据生效日期：刷新中..."
                airac_next_text.value = "本期数据将于--月--日到期"
                update_controls(airac_id_text, airac_effective_text, airac_next_text, button)
                await refresh_cycle_async()
                await rebuild_lists_async(show_loading=False)
            finally:
                set_button_busy(button, False)

        page.run_task(runner)

    def on_rescan_click(e):
        button = e.control if isinstance(getattr(e, "control", None), ft.Button) else None
        if is_button_busy(button):
            snack("扫描任务正在进行中，请稍候。")
            return
        reset_operation_dialog_suppression()
        set_button_busy(button, True, "扫描中...")

        async def runner() -> None:
            try:
                await rescan_and_rebuild_async(show_loading=True, notify_done=True)
            finally:
                set_button_busy(button, False)

        page.run_task(runner)

    def on_settings_click(_e):
        try:
            key20 = community_key("MSFS 2020", platform)
            key24 = community_key("MSFS 2024", platform)
            key24_extra = platform
            has20 = bool(state.get("enabled_simulators", {}).get("MSFS 2020", True))
            has24 = bool(state.get("enabled_simulators", {}).get("MSFS 2024", True))
            has20_check = ft.Checkbox(label="我有 MSFS 2020", value=has20)
            has24_check = ft.Checkbox(label="我有 MSFS 2024", value=has24)
            fs20_field = ft.TextField(
                label="FS20 Community",
                value=str(state.get("community_paths", {}).get(key20, "")).strip() or default_community_base("MSFS 2020", platform),
                expand=True,
            )
            fs24_field = ft.TextField(
                label="FS24 Community",
                value=str(state.get("community_paths", {}).get(key24, "")).strip() or default_community_base("MSFS 2024", platform),
                expand=True,
            )
            fs24_extra_field = ft.TextField(
                label="FS24 Community2024",
                value=str(state.get("community_2024_paths", {}).get(key24_extra, "")).strip(),
                hint_text=r"例如 ...\Packages\Community2024",
                expand=True,
            )
            current_workers = normalize_batch_download_workers(
                state.get("batch_download_workers", DEFAULT_BATCH_DOWNLOAD_WORKERS)
            )
            workers_dd = ft.Dropdown(
                label="一键安装下载线程数",
                value=str(current_workers),
                options=[ft.dropdown.Option(str(v)) for v in BATCH_DOWNLOAD_WORKER_OPTIONS],
                width=220,
            )
            default_cache_root_display = str(resolve_cache_root_dir(None, create=False))
            configured_cache_root = normalize_cache_root_dir(str(state.get("cache_root_dir", "")).strip())
            cache_root_field = ft.TextField(
                label="缓存目录（可选）",
                value=configured_cache_root or default_cache_root_display,
                hint_text=r"留空使用默认内部目录",
                expand=True,
            )
            cache_cleanup_days = normalize_cache_cleanup_days(
                state.get("cache_cleanup_days", DEFAULT_CACHE_CLEANUP_DAYS)
            )
            cache_cleanup_days_dd = ft.Dropdown(
                label="缓存自动清理周期（天）",
                value=str(cache_cleanup_days),
                options=[ft.dropdown.Option(str(v)) for v in CACHE_CLEANUP_DAY_OPTIONS],
                width=220,
            )
            err = ft.Text("", size=fs(12), color="#b83d4b")
            current_version_text = ft.Text(
                f"当前版本: {format_version_display(APP_VERSION)}",
                size=fs(12),
                color=colors["text_sub"],
                selectable=True,
            )
            update_check_status = ft.Text(
                "更新状态: 未检查",
                size=fs(12),
                color=colors["text_meta"],
                selectable=True,
            )
            check_update_btn = ft.Button("检查更新")
            open_release_btn = ft.TextButton("打开发布页", visible=False)
            latest_release_url = f"https://github.com/{normalize_github_repo(GITHUB_RELEASE_REPO)}/releases"
            dlg: ft.Control | None = None
            browse20_btn = ft.Button("浏览")
            browse24_btn = ft.Button("浏览")
            browse24_extra_btn = ft.Button("浏览")
            browse_cache_btn = ft.Button("修改")

            for ctrl in list(page.services):
                if isinstance(ctrl, ft.FilePicker) and getattr(ctrl, "data", None) in {
                    "settings_comm_picker_20",
                    "settings_comm_picker_24",
                    "settings_comm_picker_24_extra",
                    "settings_cache_picker",
                }:
                    try:
                        page.services.remove(ctrl)
                    except ValueError:
                        pass
            picker20 = ft.FilePicker()
            picker20.data = "settings_comm_picker_20"
            picker24 = ft.FilePicker()
            picker24.data = "settings_comm_picker_24"
            picker24_extra = ft.FilePicker()
            picker24_extra.data = "settings_comm_picker_24_extra"
            picker_cache = ft.FilePicker()
            picker_cache.data = "settings_cache_picker"
            page.services.extend([picker20, picker24, picker24_extra, picker_cache])

            def close_dialog(_evt=None) -> None:
                close_custom_modal()

            def open_release_page(_evt=None) -> None:
                if latest_release_url:
                    open_external_url(latest_release_url)

            async def run_manual_update_check() -> None:
                nonlocal latest_release_url
                repo = normalize_github_repo(GITHUB_RELEASE_REPO)
                update_check_status.value = f"更新状态: 正在检查 ({repo})..."
                open_release_btn.visible = False
                if not try_control_update(dlg):
                    page.update()
                try:
                    release = await asyncio.to_thread(fetch_latest_github_release, repo)
                except Exception as exc:
                    latest_release_url = f"https://github.com/{repo}/releases"
                    update_check_status.value = (
                        "更新状态: 与github通信失败，请手动检查更新或更换网络后重试。"
                    )
                    log(f"设置页检查更新失败: {exc}")
                    open_release_btn.visible = True
                    if not try_control_update(dlg):
                        page.update()
                    return

                latest_tag = str(release.get("tag_name", "")).strip()
                latest_name = str(release.get("name", "")).strip()
                latest_display = format_version_display(latest_tag or latest_name)
                latest_release_url = str(release.get("html_url", "")).strip() or f"https://github.com/{repo}/releases"
                is_new = _is_newer_version(latest_display, APP_VERSION)
                if is_new:
                    update_check_status.value = (
                        f"更新状态: 发现新版本 {latest_display}（当前 {format_version_display(APP_VERSION)}）"
                    )
                else:
                    update_check_status.value = (
                        f"更新状态: 已是最新版本（当前 {format_version_display(APP_VERSION)}，远端 {latest_display}）"
                    )
                open_release_btn.visible = True
                if not try_control_update(dlg):
                    page.update()

            def check_update_click(_evt=None) -> None:
                if is_button_busy(check_update_btn):
                    return
                set_button_busy(check_update_btn, True, "检查中...")

                async def runner() -> None:
                    try:
                        await run_manual_update_check()
                    finally:
                        set_button_busy(check_update_btn, False)

                page.run_task(runner)

            def browse_fs20(_evt) -> None:
                async def runner() -> None:
                    try:
                        path = await picker20.get_directory_path(dialog_title="选择 FS20 Community")
                        if path:
                            fs20_field.value = path
                            page.update()
                    except Exception as exc:
                        err.value = f"选择目录失败: {exc}"
                        page.update()

                page.run_task(runner)

            def browse_fs24(_evt) -> None:
                async def runner() -> None:
                    try:
                        path = await picker24.get_directory_path(dialog_title="选择 FS24 Community")
                        if path:
                            fs24_field.value = path
                            page.update()
                    except Exception as exc:
                        err.value = f"选择目录失败: {exc}"
                        page.update()

                page.run_task(runner)

            def browse_fs24_extra(_evt) -> None:
                async def runner() -> None:
                    try:
                        path = await picker24_extra.get_directory_path(dialog_title="选择 FS24 Community2024")
                        if path:
                            fs24_extra_field.value = path
                            page.update()
                    except Exception as exc:
                        err.value = f"选择目录失败: {exc}"
                        page.update()

                page.run_task(runner)

            def browse_cache_dir(_evt) -> None:
                async def runner() -> None:
                    try:
                        path = await picker_cache.get_directory_path(dialog_title="选择缓存目录")
                        if path:
                            cache_root_field.value = path
                            page.update()
                    except Exception as exc:
                        err.value = f"选择目录失败: {exc}"
                        page.update()

                page.run_task(runner)

            browse20_btn.on_click = browse_fs20
            browse24_btn.on_click = browse_fs24
            browse24_extra_btn.on_click = browse_fs24_extra
            browse_cache_btn.on_click = browse_cache_dir
            check_update_btn.on_click = check_update_click
            open_release_btn.on_click = open_release_page

            def refresh_field_status() -> None:
                fs20_field.disabled = not bool(has20_check.value)
                browse20_btn.disabled = not bool(has20_check.value)
                fs24_field.disabled = not bool(has24_check.value)
                browse24_btn.disabled = not bool(has24_check.value)
                fs24_extra_field.disabled = not bool(has24_check.value)
                browse24_extra_btn.disabled = not bool(has24_check.value)
                page.update()

            def on_sim_check_change(_evt) -> None:
                refresh_field_status()

            has20_check.on_change = on_sim_check_change
            has24_check.on_change = on_sim_check_change

            def save_click(_evt) -> None:
                p20 = fs20_field.value.strip()
                p24 = fs24_field.value.strip()
                p24_extra = fs24_extra_field.value.strip()
                workers = normalize_batch_download_workers(workers_dd.value)
                cache_root_raw = cache_root_field.value.strip()
                cache_root_normalized = normalize_cache_root_dir(cache_root_raw)
                default_cache_root_normalized = normalize_cache_root_dir(default_cache_root_display)
                cache_root_to_save = (
                    ""
                    if cache_root_normalized == default_cache_root_normalized
                    else cache_root_normalized
                )
                cleanup_days = normalize_cache_cleanup_days(cache_cleanup_days_dd.value)
                has20_selected = bool(has20_check.value)
                has24_selected = bool(has24_check.value)
                if not has20_selected and not has24_selected:
                    err.value = "至少需要选择一个模拟器（MSFS 2020 或 MSFS 2024）。"
                    page.update()
                    return
                if has20_selected and not is_valid_community_path(p20):
                    err.value = "MSFS 2020 已启用，请填写有效的 FS20 Community 路径（目录名需为 Community）。"
                    page.update()
                    return
                if has24_selected and not is_valid_community_path(p24):
                    err.value = "MSFS 2024 已启用，请填写有效的 FS24 Community 路径（目录名需为 Community）。"
                    page.update()
                    return
                if has24_selected and not is_valid_community2024_path(p24_extra):
                    err.value = "MSFS 2024 已启用，请填写有效的 FS24 Community2024 路径（目录名需为 Community2024 或 Community）。"
                    page.update()
                    return
                effective_cache_root = cache_root_to_save or default_cache_root_normalized
                if effective_cache_root:
                    cache_root_path = Path(effective_cache_root)
                    if cache_root_path.exists() and not cache_root_path.is_dir():
                        err.value = "缓存目录路径无效：该路径存在但不是目录。"
                        page.update()
                        return
                    try:
                        cache_root_path.mkdir(parents=True, exist_ok=True)
                    except Exception as exc:
                        err.value = f"创建缓存目录失败: {exc}"
                        page.update()
                        return
                state.setdefault("community_paths", {})[key20] = p20
                state.setdefault("community_paths", {})[key24] = p24
                state.setdefault("community_2024_paths", {})[key24_extra] = p24_extra
                state.setdefault("enabled_simulators", {})["MSFS 2020"] = has20_selected
                state.setdefault("enabled_simulators", {})["MSFS 2024"] = has24_selected
                state["batch_download_workers"] = workers
                state["cache_root_dir"] = cache_root_to_save
                state["cache_cleanup_days"] = cleanup_days
                nonlocal simulator
                enabled_now = enabled_simulators(state)
                if simulator not in enabled_now:
                    simulator = enabled_now[0]
                    state["simulator"] = simulator
                state["community_setup_done"] = True
                save_state(state)
                clear_cycle_json_scan_cache()
                close_dialog()
                snack("设置已保存")
                page.clean()
                main(page, fast_reload=True, cached_cycle=current_cycle_info)

            dlg = custom_modal_container
            open_custom_modal(
                "设置",
                [
                    ft.Text(f"当前平台: {platform}", size=fs(12), color=colors["text_sub"]),
                    ft.Row(spacing=10, controls=[current_version_text, check_update_btn, open_release_btn]),
                    update_check_status,
                    ft.Row(spacing=16, controls=[has20_check, has24_check]),
                    ft.Row(spacing=8, controls=[fs20_field, browse20_btn]),
                    ft.Row(spacing=8, controls=[fs24_field, browse24_btn]),
                    ft.Row(spacing=8, controls=[fs24_extra_field, browse24_extra_btn]),
                    ft.Row(spacing=8, controls=[workers_dd]),
                    ft.Row(spacing=8, controls=[cache_root_field, browse_cache_btn]),
                    ft.Row(spacing=8, controls=[cache_cleanup_days_dd]),
                    ft.Text(f"默认缓存目录: {default_cache_root_display}", size=fs(12), color=colors["text_meta"]),
                    ft.Text("目录必须存在；FS20/FS24 目录名需为 Community，FS24 Community2024 路径目录名需为 Community2024 或 Community。", size=fs(12), color=colors["text_meta"]),
                    ft.Text("一键安装会并发下载，线程越大下载越快，但网络与服务器压力更高。", size=fs(12), color=colors["text_meta"]),
                    ft.Text("缓存目录留空时使用默认内部目录；程序会按“缓存自动清理周期”清理过期缓存。", size=fs(12), color=colors["text_meta"]),
                    err,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton("取消", on_click=close_dialog),
                            ft.Button("保存", bgcolor="#1a73e8", color="#ffffff", on_click=save_click),
                        ],
                    ),
                ],
                width=780,
            )
            refresh_field_status()
        except Exception as exc:
            snack(f"打开设置失败: {exc}")

    def on_add_addon_click(_e):
        try:
            name_field = ft.TextField(label="机型名称", hint_text="例如 PMDG 777-200LR")
            desc_field = ft.TextField(label="描述", hint_text="显示在卡片副标题")
            cycle_dir_field = ft.TextField(
                label="cycle.json 所在目录",
                hint_text=r"例如 ...\pmdg-aircraft-77l\work\NavigationData",
                expand=True,
            )
            browse_cycle_dir_btn = ft.Button("浏览")
            sim_dd = ft.Dropdown(
                label="模拟器",
                value=simulator,
                options=[ft.dropdown.Option(v) for v in active_sims],
            )
            plat_dd = ft.Dropdown(
                label="平台",
                value=platform,
                options=[ft.dropdown.Option(v) for v in PLATFORMS],
            )
            err = ft.Text("", size=fs(12), color="#b83d4b")
            dlg: ft.Control | None = None

            for ctrl in list(page.services):
                if isinstance(ctrl, ft.FilePicker) and getattr(ctrl, "data", None) == "add_addon_cycle_dir_picker":
                    try:
                        page.services.remove(ctrl)
                    except ValueError:
                        pass
            cycle_dir_picker = ft.FilePicker()
            cycle_dir_picker.data = "add_addon_cycle_dir_picker"
            page.services.append(cycle_dir_picker)

            def close_dialog(_evt=None) -> None:
                close_custom_modal()

            def browse_cycle_dir(_evt) -> None:
                async def runner() -> None:
                    try:
                        path = await cycle_dir_picker.get_directory_path(dialog_title="选择 cycle.json 所在目录")
                        if path:
                            cycle_dir_field.value = path
                            page.update()
                    except Exception as exc:
                        err.value = f"选择目录失败: {exc}"
                        page.update()

                page.run_task(runner)

            browse_cycle_dir_btn.on_click = browse_cycle_dir

            def save_click(_evt) -> None:
                name = name_field.value.strip()
                if not name:
                    err.value = "机型名称不能为空。"
                    page.update()
                    return
                sim_value = str(sim_dd.value or "").strip()
                plat_value = str(plat_dd.value or "").strip()
                if sim_value not in MSFS_VERSIONS or plat_value not in PLATFORMS:
                    err.value = "请选择有效的模拟器与平台。"
                    page.update()
                    return
                cycle_dir_text = cycle_dir_field.value.strip()
                if not cycle_dir_text:
                    err.value = "请选择 cycle.json 所在目录。"
                    page.update()
                    return
                cycle_dir = Path(cycle_dir_text)
                if not cycle_dir.exists() or not cycle_dir.is_dir():
                    err.value = "所选目录不存在或不可用。"
                    page.update()
                    return
                if not (cycle_dir / "cycle.json").exists():
                    err.value = "所选目录下未找到 cycle.json，请选择正确目录。"
                    page.update()
                    return

                pkg = ""
                path_parts_lower = [part.lower() for part in cycle_dir.parts]
                if "packages" in path_parts_lower:
                    idx = path_parts_lower.index("packages")
                    if idx + 1 < len(cycle_dir.parts):
                        pkg = cycle_dir.parts[idx + 1].lower()
                if not pkg:
                    pkg = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

                new_addon = Addon(
                    name=name,
                    description=desc_field.value.strip() or name,
                    simulator=sim_value,
                    platform=plat_value,
                    target_path=str(cycle_dir),
                    package_name=pkg,
                    navdata_subpath="",
                )
                if any(addon_key(existing) == addon_key(new_addon) for existing in addons_all):
                    err.value = "该机型（同模拟器/平台/package）已存在。"
                    page.update()
                    return
                state.setdefault("addons", []).append(
                    {
                        "name": new_addon.name,
                        "description": new_addon.description,
                        "simulator": new_addon.simulator,
                        "platform": new_addon.platform,
                        "target_path": new_addon.target_path,
                        "package_name": new_addon.package_name,
                        "navdata_subpath": new_addon.navdata_subpath,
                    }
                )
                addons_all.append(new_addon)
                save_state(state)
                close_dialog()
                snack(f"已添加机型: {new_addon.name}")
                trigger_rebuild(scroll_to_key=addon_key(new_addon), show_loading=False)

            dlg = custom_modal_container
            open_custom_modal(
                "添加机型",
                [
                    name_field,
                    desc_field,
                    ft.Row(spacing=8, controls=[sim_dd, plat_dd]),
                    ft.Row(spacing=8, controls=[cycle_dir_field, browse_cycle_dir_btn]),
                    ft.Text("请直接选择包含 cycle.json 的目录。", size=fs(11), color=colors["text_meta"]),
                    err,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton("取消", on_click=close_dialog),
                            ft.Button("保存", bgcolor="#1a73e8", color="#ffffff", on_click=save_click),
                        ],
                    ),
                ],
                width=780,
            )
        except Exception as exc:
            snack(f"打开添加机型失败: {exc}")

    def on_backup_power_click(_e):
        try:
            user_field = ft.TextField(
                label="账号",
                value=str(state.get("backup_power_username", "")).strip(),
                expand=True,
            )
            pass_field = ft.TextField(
                label="密码",
                password=True,
                can_reveal_password=True,
                expand=True,
            )
            result_text = ft.Text("", size=fs(12), color=colors["text_sub"], selectable=True)
            err_text = ft.Text("", size=fs(12), color="#b83d4b")
            input_notice_text = ft.Text("", size=fs(11), color=colors["text_meta"])
            dlg: ft.Control | None = None
            login_inflight = False
            login_btn: ft.Button
            save_btn: ft.TextButton

            def keep_ascii_printable(text: str) -> str:
                return "".join(ch for ch in str(text or "") if 32 <= ord(ch) <= 126)

            def apply_english_only(field: ft.TextField, field_name: str) -> None:
                original = str(field.value or "")
                filtered = keep_ascii_printable(original)
                if original == filtered:
                    return
                field.value = filtered
                input_notice_text.value = f"{field_name}仅支持英文字符，已自动过滤非英文输入。"
                if not try_control_update(dlg):
                    page.update()

            def on_user_change(_evt=None) -> None:
                apply_english_only(user_field, "账号")

            def on_pass_change(_evt=None) -> None:
                apply_english_only(pass_field, "密码")

            user_field.on_change = on_user_change
            pass_field.on_change = on_pass_change

            def set_auth_dialog_busy(busy: bool) -> None:
                login_btn.disabled = busy
                login_btn.content = "登录中..." if busy else "登录"
                save_btn.disabled = busy
                if not try_control_update(dlg):
                    page.update()

            def close_dialog(_evt=None) -> None:
                close_custom_modal()

            def save_backup_power_settings() -> Path:
                user = user_field.value.strip()
                if not user:
                    raise ValueError("请填写账号。")
                download_dir_path = ensure_backup_power_download_dir(str(default_backup_power_download_dir(state)), create=True)
                state["backup_power_download_dir"] = str(download_dir_path)
                state["backup_power_api_url"] = BACKUP_POWER_LOGIN_URL
                state["backup_power_username"] = user
                save_state(state)
                return download_dir_path

            def save_only(_evt) -> None:
                if login_inflight:
                    err_text.value = "登录请求进行中，请稍候。"
                    if not try_control_update(dlg):
                        page.update()
                    return
                try:
                    save_backup_power_settings()
                except Exception as exc:
                    err_text.value = str(exc)
                    if not try_control_update(dlg):
                        page.update()
                    return
                err_text.value = ""
                result_text.value = "配置已保存。"
                if not try_control_update(dlg):
                    page.update()

            def clear_saved_backup_power_token() -> None:
                state["backup_power_token"] = ""
                save_state(state)
                set_backup_power_login_valid(False)

            async def try_reuse_saved_token(show_busy: bool, close_on_success: bool) -> bool:
                nonlocal login_inflight
                saved_token = str(state.get("backup_power_token", "")).strip()
                saved_user = str(state.get("backup_power_username", "")).strip()
                current_user = user_field.value.strip()
                if not saved_token:
                    set_backup_power_login_valid(False)
                    return False
                if current_user and saved_user and current_user != saved_user:
                    return False
                if show_busy:
                    login_inflight = True
                    set_auth_dialog_busy(True)
                err_text.value = ""
                result_text.value = "正在检查已保存的 DATA Token..."
                if not try_control_update(dlg):
                    page.update()
                try:
                    result = await run_blocking_with_feedback(
                        backup_power_me_request,
                        saved_token,
                        message="正在校验已保存的 DATA Token",
                        pulse_interval=0.8,
                        show_page_loading=False,
                        show_operation_dialog_ui=False,
                    )
                    token_len = len(saved_token)
                    result_text.value = (
                        "已复用有效的 DATA Token\n"
                        f"HTTP: {result.get('status', 200)}\n"
                        f"Token 长度: {token_len}\n"
                        f"登录时间: {state.get('backup_power_last_login_at', '--') or '--'}"
                    )
                    snack("已检测到有效 DATA Token，无需重新登录")
                    set_backup_power_login_valid(True)
                    if not try_control_update(dlg):
                        page.update()
                    if close_on_success:
                        close_dialog()
                    return True
                except Exception as exc:
                    detail = str(exc).strip()
                    invalid_hints = ("invalid token", "token", "authorization", "unauthorized", "missing authorization")
                    if any(hint in detail.lower() for hint in invalid_hints):
                        clear_saved_backup_power_token()
                        result_text.value = ""
                        err_text.value = "已保存的 DATA Token 已失效，请重新登录。"
                    else:
                        result_text.value = ""
                        err_text.value = f"校验 DATA Token 失败: {exc}"
                    set_backup_power_login_valid(False)
                    if not try_control_update(dlg):
                        page.update()
                    return False
                finally:
                    if show_busy:
                        login_inflight = False
                        set_auth_dialog_busy(False)

            def do_login(_evt) -> None:
                nonlocal login_inflight
                if login_inflight:
                    err_text.value = "登录请求进行中，请稍候。"
                    if not try_control_update(dlg):
                        page.update()
                    return

                api = BACKUP_POWER_LOGIN_URL
                user = user_field.value.strip()
                pwd = pass_field.value
                async def runner() -> None:
                    nonlocal login_inflight
                    reused = await try_reuse_saved_token(show_busy=True, close_on_success=True)
                    if reused:
                        return
                    if not user:
                        err_text.value = "请填写账号。"
                        if not try_control_update(dlg):
                            page.update()
                        return
                    if not pwd:
                        err_text.value = "请填写密码。"
                        if not try_control_update(dlg):
                            page.update()
                        return
                    try:
                        save_backup_power_settings()
                    except Exception as exc:
                        err_text.value = str(exc)
                        if not try_control_update(dlg):
                            page.update()
                        return

                    login_inflight = True
                    set_auth_dialog_busy(True)
                    # Ensure no stale global progress dialog blocks this auth dialog.
                    close_operation_dialog()
                    err_text.value = ""
                    result_text.value = "正在登录..."
                    if not try_control_update(dlg):
                        page.update()

                    try:
                        result = await run_blocking_with_feedback(
                            backup_power_login_request,
                            api,
                            user,
                            pwd,
                            message="正在登录后备隐藏能源",
                            pulse_interval=0.8,
                            show_page_loading=False,
                            show_operation_dialog_ui=False,
                        )
                        state["backup_power_api_url"] = BACKUP_POWER_LOGIN_URL
                        state["backup_power_username"] = user
                        state["backup_power_token"] = str(result.get("token", "")).strip()
                        state["backup_power_last_login_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        save_state(state)
                        set_backup_power_login_valid(True)
                        token_len = len(state["backup_power_token"])
                        result_text.value = (
                            f"登录成功\n"
                            f"HTTP: {result.get('status', 200)}\n"
                            f"消息: {result.get('message', 'OK')}\n"
                            f"Token 长度: {token_len}\n"
                            f"登录时间: {state['backup_power_last_login_at']}"
                        )
                        snack("后备隐藏能源登录成功")
                        if not try_control_update(dlg):
                            page.update()
                        close_dialog()
                    except Exception as exc:
                        result_text.value = ""
                        err_text.value = f"登录失败: {exc}"
                        set_backup_power_login_valid(False)
                        if not try_control_update(dlg):
                            page.update()
                    finally:
                        login_inflight = False
                        set_auth_dialog_busy(False)

                try:
                    page.run_task(runner)
                except Exception as exc:
                    login_inflight = False
                    set_auth_dialog_busy(False)
                    err_text.value = f"启动登录失败: {exc}"
                    if not try_control_update(dlg):
                        page.update()

            token_mask = str(state.get("backup_power_token", "")).strip()
            if token_mask:
                token_mask = f"{token_mask[:4]}...{token_mask[-4:]}" if len(token_mask) > 10 else "***"
            else:
                token_mask = "未登录"
            last_login = str(state.get("backup_power_last_login_at", "")).strip() or "--"
            save_btn = ft.TextButton("保存配置", on_click=save_only)
            login_btn = ft.Button("登录", bgcolor="#1a73e8", color="#ffffff", on_click=do_login)

            dlg = custom_modal_container
            open_custom_modal(
                "后备隐藏能源",
                [
                    ft.Text("账号登录", size=fs(14), weight=ft.FontWeight.W_700, color=colors["text_title"]),
                    ft.Row(spacing=8, controls=[user_field, pass_field]),
                    ft.Text("账号和密码仅支持英文字符（ASCII）。", size=fs(11), color=colors["text_sub"]),
                    input_notice_text,
                    ft.Text(
                        "OpenList 会在后台自动登录并自动刷新 Token，无需用户手动登录。当前窗口只用于 DATA 域名登录。",
                        size=fs(11),
                        color=colors["text_sub"],
                    ),
                    ft.Text(
                        "若使用 OpenList 账号（如 admin/navdata）登录此窗口，接口通常会返回 401 invalid credentials。",
                        size=fs(11),
                        color=colors["text_sub"],
                    ),
                    ft.Text(
                        "OpenList 缓存目录可在“设置”中自定义，安装后会自动清理下载缓存。",
                        size=fs(11),
                        color=colors["text_sub"],
                    ),
                    ft.Text(f"当前 Token: {token_mask}    上次登录: {last_login}", size=fs(11), color=colors["text_sub"]),
                    err_text,
                    result_text,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton("关闭", on_click=close_dialog),
                            save_btn,
                            login_btn,
                        ],
                    ),
                ],
                width=820,
            )
            if str(state.get("backup_power_token", "")).strip():
                page.run_task(try_reuse_saved_token, False, True)
        except Exception as exc:
            snack(f"后备隐藏能源失败: {exc}")

    def on_wasm_paths_click(_e):
        try:
            key = community_key(simulator, platform)
            custom_paths = custom_wasm_scan_paths(state, simulator, platform)
            default_bases = wasm_base_candidates(simulator, platform, None)
            default_scan_bases = cycle_json_scan_bases(simulator, platform, None)
            custom_field = ft.TextField(
                label="自定义扫描目录（每行一个，优先于默认路径）",
                multiline=True,
                min_lines=5,
                max_lines=8,
                value="\n".join(custom_paths),
            )
            err = ft.Text("", size=fs(12), color="#b83d4b")
            dlg: ft.Control | None = None

            for ctrl in list(page.services):
                if isinstance(ctrl, ft.FilePicker) and getattr(ctrl, "data", None) == "wasm_scan_picker":
                    try:
                        page.services.remove(ctrl)
                    except ValueError:
                        pass
            picker = ft.FilePicker()
            picker.data = "wasm_scan_picker"
            page.services.append(picker)

            def close_dialog(_evt=None) -> None:
                close_custom_modal()

            def browse_dir(_evt) -> None:
                async def runner() -> None:
                    try:
                        path = await picker.get_directory_path(dialog_title="选择自定义 WASM 扫描目录")
                        if not path:
                            return
                        line = path.strip()
                        lines = [x.strip() for x in custom_field.value.splitlines() if x.strip()]
                        if line not in lines:
                            lines.append(line)
                            custom_field.value = "\n".join(lines)
                            page.update()
                    except Exception as exc:
                        err.value = f"选择目录失败: {exc}"
                        page.update()

                page.run_task(runner)

            def save_click(_evt) -> None:
                raw_lines = [line.strip() for line in custom_field.value.splitlines() if line.strip()]
                normalized = _normalize_path_list(raw_lines)
                invalid = [p for p in normalized if not Path(p).exists() or not Path(p).is_dir()]
                if invalid:
                    err.value = f"以下目录不存在或不可用: {invalid[0]}"
                    page.update()
                    return
                state.setdefault("wasm_scan_paths", {})[key] = normalized
                save_state(state)
                clear_cycle_json_scan_cache()
                close_dialog()
                snack(f"WASM 路径已保存: {simulator} / {platform}")
                trigger_rebuild(show_loading=True)

            def clear_click(_evt) -> None:
                state.setdefault("wasm_scan_paths", {}).pop(key, None)
                save_state(state)
                clear_cycle_json_scan_cache()
                custom_field.value = ""
                err.value = ""
                page.update()
                snack(f"已清空自定义 WASM 路径: {simulator} / {platform}")
                trigger_rebuild(show_loading=True)

            dlg = custom_modal_container
            open_custom_modal(
                "WASM 路径",
                [
                    ft.Text(f"当前配置: {simulator} / {platform}", size=fs(12), color=colors["text_sub"]),
                    custom_field,
                    ft.Row(spacing=8, controls=[ft.Button("浏览并添加", on_click=browse_dir)]),
                    ft.Text("默认 WASM 候选路径:", size=fs(12), color=colors["text_meta"]),
                    ft.Text("\n".join(f"- {line}" for line in default_bases), size=fs(11), selectable=True),
                    ft.Text("默认 cycle.json 扫描根路径:", size=fs(12), color=colors["text_meta"]),
                    ft.Text("\n".join(f"- {line}" for line in default_scan_bases), size=fs(11), selectable=True),
                    err,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton("清空自定义", on_click=clear_click),
                            ft.TextButton("取消", on_click=close_dialog),
                            ft.Button("保存", bgcolor="#1a73e8", color="#ffffff", on_click=save_click),
                        ],
                    ),
                ],
                width=860,
            )
        except Exception as exc:
            snack(f"读取 WASM 路径失败: {exc}")

    def on_log_click(_e):
        try:
            snack("打开日志")
            open_log_overlay()
        except Exception as exc:
            snack(f"打开日志失败: {exc}")

    def on_install_status_click(_e):
        try:
            open_install_overlay()
        except Exception as exc:
            snack(f"打开安装状态失败: {exc}")

    def set_backup_power_login_valid(valid: bool) -> None:
        nonlocal backup_power_login_valid
        backup_power_login_valid = bool(valid)
        if one_click_install_filter_button is None:
            return
        one_click_install_filter_button.visible = backup_power_login_valid
        one_click_install_filter_button.disabled = not backup_power_login_valid
        update_controls(one_click_install_filter_button)

    async def refresh_backup_power_login_validity(notify_invalid: bool = False) -> bool:
        token = str(state.get("backup_power_token", "")).strip()
        if not token:
            set_backup_power_login_valid(False)
            return False
        try:
            await asyncio.to_thread(backup_power_me_request, token)
            set_backup_power_login_valid(True)
            return True
        except Exception as exc:
            log(f"DATA token 校验失败: {exc}")
            set_backup_power_login_valid(False)
            if notify_invalid:
                snack("登录状态已失效，请重新登录后备隐藏能源。")
            return False

    def on_one_click_install_click(e):
        button = e.control if isinstance(getattr(e, "control", None), ft.Button) else None
        if is_button_busy(button):
            open_install_overlay(title=install_overlay_title_text or "安装状态", reset=False)
            snack("一键安装仍在后台执行，已打开安装状态。")
            return
        reset_operation_dialog_suppression()
        set_button_busy(button, True, "执行中...")

        async def runner() -> None:
            try:
                login_ok = await refresh_backup_power_login_validity(notify_invalid=True)
                if not login_ok:
                    snack("DATA(data.cnrpg.top) 登录状态失效时仅支持手动本地压缩包安装；一键安装不可用。")
                    return
                scoped_addons = [a for a in addons_all if a.simulator == simulator and a.platform == platform]
                if not scoped_addons:
                    snack("当前模拟器/平台没有可更新的机型。")
                    return

                fallback_cycle = ""
                if current_cycle_info and current_cycle_info.get("cycle_id"):
                    fallback_cycle = detect_airac(str(current_cycle_info.get("cycle_id", "")))
                if fallback_cycle in {"", "UNKNOWN"}:
                    cycle_info = await asyncio.to_thread(fetch_current_cycle)
                    if cycle_info and cycle_info.get("cycle_id"):
                        fallback_cycle = detect_airac(str(cycle_info.get("cycle_id", "")))
                if fallback_cycle in {"", "UNKNOWN"}:
                    snack("未获取到有效 AIRAC 期数，无法执行一键安装。")
                    return

                open_install_overlay(title=f"安装状态 - 一键安装 {simulator} / {platform}", reset=True)
                append_install_overlay_line(f"一键安装开始: {simulator} / {platform}")
                append_install_overlay_line(f"默认期数: {fallback_cycle}")

                total = len(scoped_addons)
                success_count = 0
                failed_count = 0
                uninstalled_count = 0
                up_to_date_skip_count = 0
                skipped_count = 0
                cloud_no_data_addons: list[str] = []
                cloud_no_data_seen: set[str] = set()

                install_jobs: list[tuple[Addon, Path, str, int]] = []
                for idx, addon in enumerate(scoped_addons, start=1):
                    if not is_default_catalog_addon(addon):
                        skipped_count += 1
                        append_install_overlay_line(f"[{idx}/{total}] {addon.name}: 跳过（手动添加机型需手动选包）")
                        continue
                    target = resolve_target_dir(addon, state)
                    if target is None:
                        target = resolve_wasm_target_by_folder_name(addon, state)
                    if target is None:
                        uninstalled_count += 1
                        append_install_overlay_line(f"[{idx}/{total}] {addon.name}: 未安装（跳过）")
                        continue
                    if target.exists() and not target.is_dir():
                        failed_count += 1
                        append_install_overlay_line(f"[{idx}/{total}] {addon.name}: 失败（目标路径不是目录）")
                        continue
                    if (not target.exists()) and (not target.parent.exists()):
                        failed_count += 1
                        append_install_overlay_line(f"[{idx}/{total}] {addon.name}: 失败（目标父目录不存在）")
                        continue
                    installed_cycle = detect_airac(read_cycle_from_dir(target))
                    if installed_cycle == fallback_cycle:
                        up_to_date_skip_count += 1
                        append_install_overlay_line(
                            f"[{idx}/{total}] {addon.name}: 已是最新周期 {installed_cycle}（跳过下载）"
                        )
                        continue
                    addon_cycle = selected_install_cycle_for_addon(addon, fallback_cycle)
                    install_jobs.append((addon, target, addon_cycle, idx))

                if not install_jobs:
                    summary = (
                        f"一键安装结束: 总计{total}，成功0，失败{failed_count}，未安装{uninstalled_count}，"
                        f"最新已安装{up_to_date_skip_count}，云盘无数据0，跳过{skipped_count}"
                    )
                    if uninstalled_count > 0:
                        append_install_overlay_line(f"未安装: {uninstalled_count}")
                    if up_to_date_skip_count > 0:
                        append_install_overlay_line(f"已是最新（跳过下载）: {up_to_date_skip_count}")
                    append_install_overlay_line(summary)
                    snack(summary)
                    return

                append_install_overlay_line(f"待下载队列: {len(install_jobs)} 个机型")
                for queue_idx, (addon, _target, addon_cycle, _source_idx) in enumerate(install_jobs, start=1):
                    append_install_overlay_line(f"[排队 {queue_idx}/{len(install_jobs)}] {addon.name}（期数 {addon_cycle}）")

                max_download_workers = normalize_batch_download_workers(
                    state.get("batch_download_workers", DEFAULT_BATCH_DOWNLOAD_WORKERS)
                )
                append_install_overlay_line(f"进入并发下载阶段（线程数: {max_download_workers}）")
                batch_download_root = default_batch_download_cache_dir(state)
                await asyncio.to_thread(batch_download_root.mkdir, parents=True, exist_ok=True)

                sem = asyncio.Semaphore(max_download_workers)

                def is_openlist_no_data_error(err_text: str) -> bool:
                    text = str(err_text or "").strip().lower()
                    if not text:
                        return False
                    hints = (
                        "未找到与机型匹配的 openlist 压缩包",
                        "openlist 未找到期数目录",
                        "openlist 未找到 msfs 目录",
                        "openlist 未返回可用下载链接",
                        "目录读取失败 (404",
                        "文件信息读取失败 (404",
                        "not found",
                    )
                    return any(h in text for h in hints)

                async def download_job(
                    addon: Addon,
                    target: Path,
                    cycle_id: str,
                    idx: int,
                ) -> tuple[Addon, Path, Path | None, str | None, str | None]:
                    safe_key = re.sub(r"[^a-zA-Z0-9._-]+", "_", addon_key(addon))
                    addon_download_dir = batch_download_root / safe_key
                    await asyncio.to_thread(addon_download_dir.mkdir, parents=True, exist_ok=True)
                    async with sem:
                        append_install_overlay_line(f"[{idx}/{total}] {addon.name}: 开始下载（期数 {cycle_id}）")
                        try:
                            result = await asyncio.to_thread(
                                download_openlist_archive_for_addon,
                                addon,
                                cycle_id,
                                addon_download_dir,
                                None,
                            )
                            archive_path = Path(str(result.get("archive_path", "")).strip())
                            if not archive_path.exists():
                                raise ValueError(f"下载结果文件不存在: {archive_path}")
                            append_install_overlay_line(f"[{idx}/{total}] {addon.name}: 下载完成 -> {archive_path.name}")
                            return addon, target, archive_path, None, None
                        except Exception as exc:
                            err = str(exc)
                            if is_openlist_no_data_error(err):
                                append_install_overlay_line(f"[{idx}/{total}] {addon.name}: 云盘中无数据")
                                return addon, target, None, err, "no_data"
                            append_install_overlay_line(f"[{idx}/{total}] {addon.name}: 下载失败 -> {err}")
                            return addon, target, None, err, "error"

                download_results = await asyncio.gather(
                    *[
                        download_job(addon, target, cycle_id, idx)
                        for addon, target, cycle_id, idx in install_jobs
                    ]
                )

                append_install_overlay_line("进入安装阶段（按顺序执行）")
                for addon, target, archive_path, download_error, download_kind in download_results:
                    if download_error or archive_path is None:
                        if download_kind == "no_data":
                            if addon.name not in cloud_no_data_seen:
                                cloud_no_data_seen.add(addon.name)
                                cloud_no_data_addons.append(addon.name)
                            continue
                        failed_count += 1
                        continue
                    picked = [type("PickedFile", (), {"path": str(archive_path)})()]
                    ok = await on_archive_update_pick_result(
                        picked,
                        addon,
                        target,
                        show_result_dialog=False,
                        allow_force_prompt=False,
                        wait_for_completion=True,
                        reset_overlay=False,
                    )
                    if ok:
                        success_count += 1
                    else:
                        failed_count += 1

                summary = (
                    f"一键安装完成: 总计{total}，成功{success_count}，失败{failed_count}，未安装{uninstalled_count}，"
                    f"最新已安装{up_to_date_skip_count}，云盘无数据{len(cloud_no_data_addons)}，跳过{skipped_count}"
                )
                if uninstalled_count > 0:
                    append_install_overlay_line(f"未安装: {uninstalled_count}")
                if up_to_date_skip_count > 0:
                    append_install_overlay_line(f"已是最新（跳过下载）: {up_to_date_skip_count}")
                if cloud_no_data_addons:
                    append_install_overlay_line(f"云盘中无数据: {', '.join(cloud_no_data_addons)}")
                append_install_overlay_line(summary)
                snack(summary)
            except Exception as exc:
                append_install_overlay_line(f"一键安装异常: {exc}")
                snack(f"一键安装失败: {exc}")
            finally:
                try:
                    await asyncio.to_thread(shutil.rmtree, default_batch_download_cache_dir(state), True)
                except Exception:
                    pass
                set_button_busy(button, False)

        page.run_task(runner)

    def on_open_log_folder_click(_e):
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            open_folder(str(LOG_DIR))
        except Exception as exc:
            snack(f"打开日志文件夹失败: {exc}")

    def on_streamer_mode_click(_e):
        nonlocal streamer_mode
        streamer_mode = not streamer_mode
        state["streamer_mode"] = streamer_mode
        save_state(state)
        refresh_streamer_button()
        rebuild_lists(precomputed_entries=last_rendered_entries)

    def refresh_segment_visuals() -> None:
        for key, btn in sim_buttons.items():
            selected = key == simulator
            btn.bgcolor = "#7a47e8" if selected else colors["switch_unsel_bg"]
            btn.color = "#ffffff" if selected else colors["switch_unsel_fg"]
        for key, btn in platform_buttons.items():
            selected = key == platform
            btn.bgcolor = "#0f7ca8" if selected else colors["switch_unsel_bg"]
            btn.color = "#ffffff" if selected else colors["switch_unsel_fg"]
        for key, btn in theme_buttons.items():
            selected = key == theme_name
            btn.bgcolor = colors["filter_active_bg"] if selected else colors["switch_unsel_bg"]
            btn.color = colors["filter_active_fg"] if selected else colors["switch_unsel_fg"]

    streamer_button = build_top_action_button("主播模式", on_click=on_streamer_mode_click)
    one_click_install_filter_button = ft.Button(
        "一键安装",
        on_click=on_one_click_install_click,
        visible=False,
        height=30,
        bgcolor=colors["panel_soft_bg"],
        color=colors["text_meta"],
        style=ft.ButtonStyle(
            padding=ft.Padding.symmetric(horizontal=12, vertical=0),
            shape=ft.RoundedRectangleBorder(radius=14),
            text_style=ft.TextStyle(weight=ft.FontWeight.W_600),
        ),
    )

    def refresh_streamer_button() -> None:
        setattr(streamer_button, "text", "关闭主播模式" if streamer_mode else "主播模式")
        if streamer_mode:
            streamer_button.bgcolor = colors["filter_active_bg"]
            streamer_button.color = colors["filter_active_fg"]
        else:
            streamer_button.bgcolor = colors["panel_bg"]
            streamer_button.color = colors["text_meta"]

    def set_sim(value: str) -> None:
        nonlocal simulator
        if value not in active_sims or value == simulator:
            return
        simulator = value
        state["simulator"] = simulator
        save_state(state)
        refresh_segment_visuals()
        trigger_rebuild(show_loading=True)

    def set_platform(value: str) -> None:
        nonlocal platform
        if value not in PLATFORMS or value == platform:
            return
        platform = value
        state["platform"] = platform
        save_state(state)
        refresh_segment_visuals()
        trigger_rebuild(show_loading=True)

    def on_filter_change(target_filter: str, rebuild: bool = True):
        nonlocal filter_value
        filter_value = target_filter
        for k, btn in filter_chips.items():
            if k == target_filter:
                btn.bgcolor = colors["filter_active_bg"]
                btn.color = colors["filter_active_fg"]
                btn.style = ft.ButtonStyle(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=0),
                    shape=ft.RoundedRectangleBorder(radius=14),
                    text_style=ft.TextStyle(weight=ft.FontWeight.W_700),
                )
            else:
                btn.bgcolor = colors["filter_bg"]
                btn.color = colors["filter_fg"]
                btn.style = ft.ButtonStyle(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=0),
                    shape=ft.RoundedRectangleBorder(radius=14),
                    text_style=ft.TextStyle(weight=ft.FontWeight.W_500),
                )
        if rebuild:
            trigger_rebuild(show_loading=True)

    def on_search_change(e: ft.Event[ft.TextField]) -> None:
        nonlocal search_text
        search_text = str(getattr(e.control, "value", "") or "")
        trigger_rebuild(show_loading=False)

    def set_theme(value: str) -> None:
        nonlocal theme_name
        if value not in (THEME_LIGHT, THEME_DARK) or value == theme_name:
            return
        theme_name = value
        state["theme"] = theme_name
        save_state(state)
        # Fast hot-reload: rebuild visual tree but reuse already fetched cycle data
        # and skip startup scans/network calls.
        last_cycle = current_cycle_info
        page.clean()
        main(page, fast_reload=True, cached_cycle=last_cycle)

    for key, btn in filter_chips.items():
        btn.on_click = lambda _e, k=key: on_filter_change(k)
        btn.bgcolor = colors["filter_bg"]
        btn.color = colors["filter_fg"]
        btn.height = 30
        btn.style = ft.ButtonStyle(
            padding=ft.Padding.symmetric(horizontal=12, vertical=0),
            shape=ft.RoundedRectangleBorder(radius=14),
        )

    airac_card = ft.Container(
        width=float("inf"),
        border_radius=20,
        bgcolor=colors["panel_bg"],
        padding=12,
        content=ft.Column(
            spacing=6,
            controls=[
                ft.Text("当前 AIRAC", size=fs(14), weight=ft.FontWeight.W_600, color=colors["text_sub"]),
                airac_id_text,
                airac_effective_text,
                airac_next_text,
            ],
        ),
    )

    installed_card = ft.Container(
        expand=True,
        border_radius=20,
        bgcolor=colors["panel_bg"],
        padding=10,
        content=ft.Column(
            expand=True,
            spacing=8,
            controls=[
                ft.Text("已安装机型", size=fs(14), weight=ft.FontWeight.W_600, color=colors["text_sub"]),
                left_list,
            ],
        ),
    )

    left = ft.Container(
        width=330,
        border_radius=20,
        bgcolor=colors["sidebar_bg"],
        padding=10,
        content=ft.Column(
            expand=True,
            controls=[
                airac_card,
                ft.Container(height=12),
                installed_card,
            ],
        ),
    )

    right_scroll_col = ft.Column(
        expand=True,
        spacing=6,
        scroll=ft.ScrollMode.AUTO,
        auto_scroll=False,
        controls=cast(list[ft.Control], [
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=cast(list[ft.Control], [
                        ft.Row(
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Image(
                                    src=str(APP_WINDOW_LOGO_FILE),
                                    width=34,
                                    height=34,
                                    fit=ft.BoxFit.CONTAIN,
                                ) if APP_WINDOW_LOGO_FILE.exists() else ft.Container(width=0, height=0),
                                ft.Column(
                                    spacing=1,
                                    controls=[
                                        ft.Text("AIRAC 周期管理器", size=fs(26), weight=ft.FontWeight.BOLD, color=colors["text_title"]),
                                        ft.Text("为你的 MSFS 插件机型更新导航数据库", size=fs(12), color=colors["text_sub"]),
                                    ],
                                ),
                            ],
                        ),
                        ft.Row(
                            spacing=6,
                            alignment=ft.MainAxisAlignment.END,
                            controls=[
                                ft.Column(
                                    spacing=4,
                                    horizontal_alignment=ft.CrossAxisAlignment.END,
                                    controls=[
                                        ft.Container(
                                            bgcolor=colors["switch_shell_bg"],
                                            border_radius=18,
                                            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                                            content=sim_segment_row,
                                        ),
                                        ft.Container(
                                            bgcolor=colors["switch_shell_bg"],
                                            border_radius=18,
                                            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                                            content=platform_segment_row,
                                        ),
                                        ft.Container(
                                            bgcolor=colors["switch_shell_bg"],
                                            border_radius=18,
                                            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                                            content=theme_segment_row,
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ]),
                ),
                ft.Container(
                    bgcolor=colors["panel_bg"],
                    border_radius=16,
                    padding=6,
                    content=ft.Row(
                        expand=True,
                        spacing=6,
                        controls=[
                            ft.Row(
                                spacing=6,
                                controls=[
                                    build_top_action_button(
                                        "启动后备隐藏能源",
                                        on_click=on_backup_power_click,
                                        bgcolor=colors["panel_soft_bg"],
                                        color=colors["text_meta"],
                                    ),
                                    build_top_action_button("设置", on_click=on_settings_click),
                                    build_top_action_button("添加机型", on_click=on_add_addon_click),
                                    build_top_action_button("重新扫描", on_click=on_rescan_click),
                                    build_top_action_button("WASM 路径", on_click=on_wasm_paths_click),
                                    build_top_action_button("LOG", on_click=on_log_click),
                                    build_top_action_button("安装状态", on_click=on_install_status_click),
                                ],
                            ),
                            ft.Container(expand=True),
                            streamer_button,
                            build_top_action_button(
                                "刷新周期",
                                on_click=on_refresh_click,
                                icon=ft.Icons.REFRESH,
                            ),
                        ],
                    ),
                ),
                ft.TextField(
                    hint_text="搜索机型...",
                    dense=True,
                    height=36,
                    border_radius=10,
                    content_padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                    on_change=on_search_change,
                ),
                ft.Row(spacing=6, wrap=True, controls=[*list(filter_chips.values()), one_click_install_filter_button]),
                ft.Container(
                    expand=False,
                    border_radius=16,
                    bgcolor=colors["panel_bg"],
                    border=ft.Border.all(1, "#2f3c52"),
                    padding=12,
                    content=right_cards_list,
                ),
        ]),
    )

    right = ft.Container(
        expand=True,
        border_radius=20,
        bgcolor=colors["main_bg"],
        padding=12,
        content=right_scroll_col,
    )

    log_overlay_container.content = ft.Container(
        expand=True,
        bgcolor="#0c1220",
        alignment=ft.Alignment(0, 0),
        content=ft.Container(
            width=980,
            height=620,
            border_radius=22,
            bgcolor=colors["panel_bg"],
            border=ft.Border.all(1, "#2f3c52"),
            padding=16,
            content=ft.Column(
                expand=True,
                spacing=12,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column(
                                spacing=2,
                                controls=[
                                    log_overlay_title,
                                ],
                            ),
                            ft.Row(
                                spacing=8,
                                controls=[
                                    ft.Button(
                                        "刷新",
                                        icon=ft.Icons.REFRESH,
                                        bgcolor=colors["panel_soft_bg"],
                                        color=colors["text_meta"],
                                        on_click=lambda _e: (refresh_log_overlay(), update_controls(log_overlay_container)),
                                    ),
                                    ft.Button(
                                        "打开日志文件夹",
                                        icon=ft.Icons.FOLDER_OPEN,
                                        bgcolor=colors["panel_soft_bg"],
                                        color=colors["text_meta"],
                                        on_click=on_open_log_folder_click,
                                    ),
                                    ft.Button(
                                        "关闭",
                                        icon=ft.Icons.CLOSE,
                                        bgcolor="#b83d4b",
                                        color="#ffffff",
                                        on_click=close_log_overlay,
                                    ),
                                ],
                            ),
                        ],
                    ),
                    ft.Container(
                        expand=True,
                        border_radius=16,
                        bgcolor=colors["log_bg"],
                        padding=12,
                        content=log_overlay_list,
                    ),
                ],
            ),
        ),
    )

    custom_modal_panel.content = ft.Container(
        border_radius=22,
        bgcolor=colors["panel_bg"],
        border=ft.Border.all(1, "#2f3c52"),
        padding=16,
        content=ft.Column(
            tight=True,
            spacing=12,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        custom_modal_title,
                        ft.Button(
                            "关闭",
                            icon=ft.Icons.CLOSE,
                            bgcolor="#b83d4b",
                            color="#ffffff",
                            on_click=close_custom_modal,
                        ),
                    ],
                ),
                custom_modal_body,
            ],
        ),
    )

    custom_modal_container.content = ft.Container(
        expand=True,
        bgcolor="#0c1220",
        alignment=ft.Alignment(0, 0),
        content=custom_modal_panel,
    )

    op_overlay_container.content = ft.Container(
        expand=True,
        bgcolor="#0c122088",
        alignment=ft.Alignment(0, 0),
        content=ft.Container(
            width=420,
            border_radius=20,
            bgcolor=colors["panel_bg"],
            border=ft.Border.all(1, "#2f3c52"),
            padding=16,
            content=ft.Column(
                tight=True,
                spacing=12,
                controls=[
                    op_dialog_title,
                    ft.Row(
                        spacing=10,
                        controls=[
                            ft.ProgressRing(width=24, height=24, stroke_width=3),
                            ft.Text("处理中", size=fs(14), weight=ft.FontWeight.W_600),
                        ],
                    ),
                    op_dialog_status,
                    op_dialog_detail,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[op_hide_button],
                    ),
                ],
            ),
        ),
    )

    startup_update_skip_btn = ft.Button(
        "跳过",
        icon=ft.Icons.SKIP_NEXT,
        bgcolor=colors["panel_soft_bg"],
        color=colors["text_meta"],
        on_click=on_startup_update_skip,
        visible=False,
    )
    startup_update_download_btn = ft.Button(
        "前往更新",
        icon=ft.Icons.SYSTEM_UPDATE_ALT,
        bgcolor="#1a73e8",
        color="#ffffff",
        on_click=on_startup_update_download,
        visible=False,
    )
    startup_update_continue_btn = ft.Button(
        "继续进入",
        icon=ft.Icons.ARROW_FORWARD,
        bgcolor=colors["panel_soft_bg"],
        color=colors["text_meta"],
        on_click=on_startup_update_continue,
        visible=False,
    )

    startup_update_overlay_container.content = ft.Container(
        expand=True,
        bgcolor="#0c1220d8",
        alignment=ft.Alignment(0, 0),
        content=ft.Container(
            width=860,
            border_radius=22,
            bgcolor=colors["panel_bg"],
            border=ft.Border.all(1, "#2f3c52"),
            padding=18,
            content=ft.Column(
                tight=True,
                spacing=12,
                controls=[
                    startup_update_title,
                    startup_update_status,
                    startup_update_detail,
                    startup_update_countdown,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        spacing=8,
                        controls=[
                            startup_update_skip_btn,
                            startup_update_download_btn,
                            startup_update_continue_btn,
                        ],
                    ),
                ],
            ),
        ),
    )

    install_force_button = ft.Button(
        "强制安装",
        icon=ft.Icons.WARNING_AMBER_ROUNDED,
        bgcolor="#c67a00",
        color="#ffffff",
        visible=False,
        disabled=True,
        on_click=run_pending_force_install,
    )

    install_overlay_container.content = ft.Container(
        expand=True,
        bgcolor="#0c1220",
        alignment=ft.Alignment(0, 0),
        content=ft.Container(
            width=980,
            height=620,
            border_radius=22,
            bgcolor=colors["panel_bg"],
            border=ft.Border.all(1, "#2f3c52"),
            padding=16,
            content=ft.Column(
                expand=True,
                spacing=12,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column(
                                spacing=2,
                                controls=[
                                    install_overlay_title,
                                ],
                            ),
                            ft.Row(
                                spacing=8,
                                controls=[
                                    install_force_button,
                                    ft.Button(
                                        "清空",
                                        icon=ft.Icons.CLEAR_ALL,
                                        bgcolor=colors["panel_soft_bg"],
                                        color=colors["text_meta"],
                                        on_click=clear_install_overlay,
                                    ),
                                    ft.Button(
                                        "关闭",
                                        icon=ft.Icons.CLOSE,
                                        bgcolor="#b83d4b",
                                        color="#ffffff",
                                        on_click=close_install_overlay,
                                    ),
                                ],
                            ),
                        ],
                    ),
                    ft.Container(
                        expand=True,
                        border_radius=16,
                        bgcolor=colors["log_bg"],
                        padding=12,
                        content=install_overlay_list,
                    ),
                ],
            ),
        ),
    )

    scroll_top_button.content = ft.Container(
        width=52,
        height=52,
        border_radius=999,
        bgcolor="#ffffff",
        opacity=0.72,
        ink=True,
        on_click=on_scroll_top_click,
        shadow=ft.BoxShadow(blur_radius=18, spread_radius=1, color="#00000022"),
        content=ft.Icon(ft.Icons.KEYBOARD_ARROW_UP, color=colors["text_title"], size=28),
    )

    root_row = ft.Row(expand=True, controls=[left, right])
    page.add(
        ft.Stack(
            expand=True,
            controls=[
                root_row,
                ft.Container(
                    right=24,
                    bottom=24,
                    content=scroll_top_button,
                ),
                custom_modal_container,
                log_overlay_container,
                install_overlay_container,
                op_overlay_container,
                startup_update_overlay_container,
            ],
        )
    )

    refresh_streamer_button()
    refresh_segment_visuals()
    on_filter_change("All", rebuild=False)
    set_backup_power_login_valid(False)
    if not fast_reload:
        log("FMS UPDATE MANAGER  started.")
        airac_id_text.value = "..."
        airac_effective_text.value = "本期数据生效日期：加载中..."
        airac_next_text.value = "本期数据将于--月--日到期"
        show_loading_state("正在初始化...")

        async def bootstrap() -> None:
            cleanup_result = await asyncio.to_thread(cleanup_stale_cache_entries, state)
            if cleanup_result.get("ran"):
                save_state(state)
                removed = int(cleanup_result.get("removed", 0))
                days = int(cleanup_result.get("days", DEFAULT_CACHE_CLEANUP_DAYS))
                log(f"缓存定期清理完成：清理周期 {days} 天，删除 {removed} 项过期缓存。")
            await run_startup_update_check()
            await refresh_backup_power_login_validity(notify_invalid=False)
            await refresh_cycle_async(notify_fail=False)
            await rescan_and_rebuild_async(show_loading=False, notify_done=False)

        page.run_task(bootstrap)
    else:
        trigger_rebuild(show_loading=True)
        page.run_task(refresh_backup_power_login_validity, False)


if __name__ == "__main__":
    if _ensure_installer_not_running():
        ft.run(main)
