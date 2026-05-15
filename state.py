import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
STATE_FILE = ROAMING_DIR / "state.json"
BACKUP_DIR = LOCAL_DIR / "backups"
APP_VERSION = os.getenv("FMS_APP_VERSION", "1.0.5").strip() or "1.0.5"
MSFS_VERSIONS = ["MSFS 2024", "MSFS 2020"]
PLATFORMS = ["Xbox/MS Store", "Steam"]
THEME_LIGHT = "Light Mode"
THEME_DARK = "Dark Mode"
DEFAULT_BATCH_DOWNLOAD_WORKERS = 4
DEFAULT_CACHE_CLEANUP_DAYS = 7
CACHE_CLEANUP_DAY_OPTIONS = (1, 3, 7, 14, 30)
DEFAULT_SIM_PLATFORM_VARIANTS = [
    ("MSFS 2020", "Steam"),
    ("MSFS 2020", "Xbox/MS Store"),
    ("MSFS 2024", "Steam"),
    ("MSFS 2024", "Xbox/MS Store"),
]
DEFAULT_ADDON_FAMILIES = [
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


def community_key(simulator: str, platform: str) -> str:
    return f"{simulator}|{platform}"


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


def normalize_batch_download_workers(raw_value: Any) -> int:
    try:
        value = int(str(raw_value).strip())
    except Exception:
        return DEFAULT_BATCH_DOWNLOAD_WORKERS
    if value in (1, 2, 4, 8):
        return value
    if value <= 1:
        return 1
    if value >= 8:
        return 8
    return DEFAULT_BATCH_DOWNLOAD_WORKERS


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
    addons.extend(
        [
            {
                "name": "iniBuilds A340-300",
                "description": "iniBuilds A340 family",
                "simulator": "MSFS 2024",
                "platform": "Steam",
                "target_path": "",
                "package_name": "inibuilds-aircraft-a340",
                "navdata_subpath": r"work\NavigationData",
            },
            {
                "name": "iniBuilds A340-300",
                "description": "iniBuilds A340 family",
                "simulator": "MSFS 2024",
                "platform": "Xbox/MS Store",
                "target_path": "",
                "package_name": "inibuilds-aircraft-a340",
                "navdata_subpath": r"work\NavigationData",
            },
            {
                "name": "iniBuilds A350",
                "description": "iniBuilds A350 family",
                "simulator": "MSFS 2024",
                "platform": "Steam",
                "target_path": "",
                "package_name": "inibuilds-aircraft-a350",
                "navdata_subpath": r"work\NavigationData",
            },
            {
                "name": "iniBuilds A350",
                "description": "iniBuilds A350 family",
                "simulator": "MSFS 2020",
                "platform": "Steam",
                "target_path": "",
                "package_name": "inibuilds-aircraft-a350",
                "navdata_subpath": r"work\NavigationData",
            },
            {
                "name": "iniBuilds A350",
                "description": "iniBuilds A350 family",
                "simulator": "MSFS 2020",
                "platform": "Xbox/MS Store",
                "target_path": "",
                "package_name": "inibuilds-aircraft-a350",
                "navdata_subpath": r"work\NavigationData",
            },
            {
                "name": "iniBuilds A350",
                "description": "iniBuilds A350 family",
                "simulator": "MSFS 2024",
                "platform": "Xbox/MS Store",
                "target_path": "",
                "package_name": "inibuilds-aircraft-a350",
                "navdata_subpath": r"work\NavigationData",
            },
            {
                "name": "Aerosoft A340-600 Pro",
                "description": "Aerosoft Airbus A340-600 Pro",
                "simulator": "MSFS 2024",
                "platform": "Steam",
                "target_path": "",
                "package_name": "aerosoft-aircraft-a346-pro",
                "navdata_subpath": r"work\FMSData",
            },
            {
                "name": "Aerosoft A340-600 Pro",
                "description": "Aerosoft Airbus A340-600 Pro",
                "simulator": "MSFS 2024",
                "platform": "Xbox/MS Store",
                "target_path": "",
                "package_name": "aerosoft-aircraft-a346-pro",
                "navdata_subpath": r"work\FMSData",
            },
            {
                "name": "Aerosoft A340-600 Pro",
                "description": "Aerosoft Airbus A340-600 Pro",
                "simulator": "MSFS 2020",
                "platform": "Steam",
                "target_path": "",
                "package_name": "aerosoft-aircraft-a346-pro",
                "navdata_subpath": r"work\FMSData",
            },
            {
                "name": "Aerosoft A340-600 Pro",
                "description": "Aerosoft Airbus A340-600 Pro",
                "simulator": "MSFS 2020",
                "platform": "Xbox/MS Store",
                "target_path": "",
                "package_name": "aerosoft-aircraft-a346-pro",
                "navdata_subpath": r"work\FMSData",
            },
        ]
    )
    return addons


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
            "backup_power_api_url": "http://fms.cnrpg.top:3090/api/auth/login",
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
        state.setdefault("backup_power_api_url", "")
        state.setdefault("backup_power_username", "")
        state.setdefault("backup_power_token", "")
        state.setdefault("backup_power_last_login_at", "")
        state.setdefault("backup_power_download_dir", "")
        state.setdefault("cache_root_dir", "")
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
            "backup_power_api_url": "http://fms.cnrpg.top:3090/api/auth/login",
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


def save_state(state: dict) -> None:
    try:
        ROAMING_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
