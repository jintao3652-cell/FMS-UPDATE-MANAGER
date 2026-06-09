import json
import os
import sys
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


def _exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _portable_root() -> Path | None:
    base = _exe_dir()
    if (base / "portable.flag").exists():
        return base / "data"
    return None


PORTABLE_ROOT = _portable_root()
PORTABLE_MODE = PORTABLE_ROOT is not None
if PORTABLE_ROOT is not None:
    ROAMING_DIR = PORTABLE_ROOT / "roaming"
    LOCAL_DIR = PORTABLE_ROOT / "local"
STATE_FILE = ROAMING_DIR / "state.json"
BACKUP_DIR = LOCAL_DIR / "backups"
APP_VERSION = os.getenv("FMS_APP_VERSION", "1.1.2").strip() or "1.1.0"
MSFS_VERSIONS = ["MSFS 2024", "MSFS 2020"]
PLATFORMS = ["Xbox/MS Store", "Steam"]
THEME_LIGHT = "Light Mode"
THEME_DARK = "Dark Mode"
DEFAULT_BATCH_DOWNLOAD_WORKERS = 4
DEFAULT_CACHE_CLEANUP_DAYS = 7
CACHE_CLEANUP_DAY_OPTIONS = (1, 3, 7, 14, 30)
BATCH_DOWNLOAD_WORKER_OPTIONS = (1, 2, 4, 8)
BACKUP_POWER_LOGIN_URL = "http://fms.cnrpg.top:17306/api/auth/login"
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
    ("CSS 737CL", "CSS 737 Classic series", "css-core", r"Data\NavData\Inactive"),
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
    # "" = navdata/aircraft (default flow); "community_plugin" = whole-folder
    # Navigraph package installed fresh into Community (no cycle.json).
    install_mode: str = ""


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
    if value in BATCH_DOWNLOAD_WORKER_OPTIONS:
        return value
    if value <= min(BATCH_DOWNLOAD_WORKER_OPTIONS):
        return min(BATCH_DOWNLOAD_WORKER_OPTIONS)
    if value >= max(BATCH_DOWNLOAD_WORKER_OPTIONS):
        return max(BATCH_DOWNLOAD_WORKER_OPTIONS)
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
    for sim, package in (
        ("MSFS 2020", "navigraph-msfs2020-base"),
        ("MSFS 2024", "navigraph-msfs2024-base"),
    ):
        label = f"{sim} Navigation Data"
        desc = f"Navigraph base navdata for {sim}"
        for plat in ("Steam", "Xbox/MS Store"):
            addons.append(
                {
                    "name": label,
                    "description": desc,
                    "simulator": sim,
                    "platform": plat,
                    "target_path": "",
                    "package_name": package,
                    "navdata_subpath": "",
                }
            )

    # Augment the hand-tuned families above with any packages from the bundled
    # Navigraph catalog that aren't already covered. This is data-driven: adding
    # a package to navigraph_catalog_2605.json surfaces it here automatically,
    # without new hardcoded matching rules (the generic token matcher handles it).
    try:
        import navigraph_catalog

        catalog_packages = navigraph_catalog.load_bundled_catalog()
        addons.extend(navigraph_catalog.missing_addons_from_catalog(catalog_packages, addons))
    except Exception:
        # Catalog augmentation is best-effort; never break the core addon list.
        pass

    return addons


def to_addon(item: dict) -> Addon | None:
    if not isinstance(item, dict):
        return None
    try:
        package_name = str(item.get("package_name", "")).strip()
        navdata_subpath = str(item.get("navdata_subpath", "")).strip()
        if package_name.lower() == "css-core" and not navdata_subpath:
            navdata_subpath = r"Data\NavData\Inactive"
        return Addon(
            name=str(item.get("name", "")).strip(),
            description=str(item.get("description", "")).strip(),
            simulator=str(item.get("simulator", "")).strip(),
            platform=str(item.get("platform", "")).strip(),
            target_path=str(item.get("target_path", "")).strip(),
            package_name=package_name,
            navdata_subpath=navdata_subpath,
            install_mode=str(item.get("install_mode", "")).strip(),
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
            "backup_power_api_url": BACKUP_POWER_LOGIN_URL,
            "backup_power_username": "",
            "backup_power_token": "",
            "backup_power_refresh_token": "",
            "backup_power_last_login_at": "",
            "backup_power_download_dir": "",
            "cache_root_dir": "",
            "cache_cleanup_days": DEFAULT_CACHE_CLEANUP_DAYS,
            "cache_last_cleanup_at": "",
            "addon_install_cycles": {},
            "batch_download_workers": DEFAULT_BATCH_DOWNLOAD_WORKERS,
        }
    try:
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8", errors="ignore"))
        except (json.JSONDecodeError, ValueError):
            bak = STATE_FILE.with_suffix(STATE_FILE.suffix + ".bak")
            if bak.exists():
                state = json.loads(bak.read_text(encoding="utf-8", errors="ignore"))
            else:
                raise
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
        from openlist import normalize_backup_power_login_url, normalize_backup_power_download_dir
        from maintenance import normalize_cache_root_dir
        state["backup_power_api_url"] = normalize_backup_power_login_url(state.get("backup_power_api_url", BACKUP_POWER_LOGIN_URL))
        state.setdefault("backup_power_username", "")
        state.setdefault("backup_power_token", "")
        state.setdefault("backup_power_refresh_token", "")
        state.setdefault("crash_upload_enabled", False)
        state.setdefault("cycle_subscribe_enabled", False)
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
            "backup_power_refresh_token": "",
            "backup_power_last_login_at": "",
            "backup_power_download_dir": "",
            "cache_root_dir": "",
            "cache_cleanup_days": DEFAULT_CACHE_CLEANUP_DAYS,
            "cache_last_cleanup_at": "",
            "addon_install_cycles": {},
            "batch_download_workers": DEFAULT_BATCH_DOWNLOAD_WORKERS,
        }


_save_state_lock = __import__("threading").Lock()


def save_state(state: dict) -> None:
    """Atomic state.json writer.
    Steps:
      1. Serialize JSON to bytes.
      2. Write to a sibling .tmp in the same directory (atomic os.replace requires same fs).
      3. fsync the tmp file.
      4. os.replace tmp -> STATE_FILE (atomic on Win/POSIX).
      5. Keep a .bak of the previous good copy so we can recover from a partial run.
    Errors are swallowed (matches previous behavior) — we never let a save failure crash the UI thread.
    """
    try:
        payload = json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8")
    except Exception:
        return
    with _save_state_lock:
        try:
            ROAMING_DIR.mkdir(parents=True, exist_ok=True)
            if STATE_FILE.exists():
                try:
                    bak = STATE_FILE.with_suffix(STATE_FILE.suffix + ".bak")
                    bak.write_bytes(STATE_FILE.read_bytes())
                except Exception:
                    pass
            tmp = STATE_FILE.with_suffix(STATE_FILE.suffix + ".tmp")
            with open(tmp, "wb") as fh:
                fh.write(payload)
                try:
                    fh.flush()
                    os.fsync(fh.fileno())
                except Exception:
                    pass
            os.replace(tmp, STATE_FILE)
        except Exception:
            pass


def _addon_from_dict(item: dict) -> Addon:
    package_name = str(item.get("package_name", "")).strip()
    navdata_subpath = str(item.get("navdata_subpath", "")).strip()
    if package_name.lower() == "css-core" and not navdata_subpath:
        navdata_subpath = r"Data\NavData\Inactive"
    return Addon(
        name=str(item.get("name", "")).strip(),
        description=str(item.get("description", "")).strip(),
        simulator=str(item.get("simulator", "")).strip(),
        platform=str(item.get("platform", "")).strip(),
        target_path=str(item.get("target_path", "")).strip(),
        package_name=package_name,
        navdata_subpath=navdata_subpath,
        install_mode=str(item.get("install_mode", "")).strip(),
    )


def enabled_simulators(state: dict | None) -> list[str]:
    if not isinstance(state, dict):
        return list(MSFS_VERSIONS)
    raw = state.get("enabled_simulators", {})
    if not isinstance(raw, dict):
        return list(MSFS_VERSIONS)
    sims = [sim for sim in MSFS_VERSIONS if bool(raw.get(sim, True))]
    return sims if sims else list(MSFS_VERSIONS)
