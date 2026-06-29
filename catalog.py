import json
import os
import re
from pathlib import Path

from state import Addon, MSFS_VERSIONS, community_key
from targets import (
    addon_search_tokens,
    cycle_name_matches_addon,
    folder_name_matches_addon_signature,
    infer_package_name,
    is_a346_addon,
    is_ifly_737max8_addon,
    is_pmdg_737_addon,
    is_sim_base_navdata_addon,
    path_matches_addon_signature,
    sim_base_navdata_required_subfolders,
    text_matches_addon_signature,
)
from utils import detect_airac, version_at_least

CYCLE_JSON_SCAN_CACHE: dict[tuple[str, ...], list[Path]] = {}


def _expand(raw: str) -> str:
    return os.path.normpath(os.path.expandvars(raw))


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
    if package == "css-core":
        return True
    return False


def effective_navdata_subpath(addon: Addon) -> str:
    if addon.navdata_subpath:
        return addon.navdata_subpath
    if addon.package_name.strip().lower() == "css-core":
        return r"Data\NavData\Inactive"
    return ""


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


def _normalized_path_parts(path: Path) -> list[str]:
    return [_norm_token(part) for part in path.parts if _norm_token(part)]


def _norm_token(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


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


def read_cycle_json(json_path: Path) -> str:
    try:
        import json

        payload = json.loads(json_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return "UNKNOWN"
    return read_cycle_from_payload(payload)


def read_cycle_from_payload(payload) -> str:
    from archive import read_cycle_from_payload as _read_cycle_from_payload

    return _read_cycle_from_payload(payload)


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


def addon_uses_community_2024(addon) -> bool:
    pkg = str(getattr(addon, "package_name", "") or "").strip().lower()
    name = str(getattr(addon, "name", "") or "").strip().lower()
    if pkg.startswith("css-") or name.startswith("css "):
        return False
    return True


def community_base_candidates(state: dict | None, simulator: str, platform: str, addon=None) -> list[str]:
    bases = [community_base(state if isinstance(state, dict) else {}, simulator, platform)]
    if simulator == "MSFS 2024" and (addon is None or addon_uses_community_2024(addon)):
        c24 = community_2024_base(state, platform)
        if c24:
            bases.append(c24)
    return _normalize_path_list(bases)


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


def community_2024_base(state: dict | None, platform: str) -> str:
    if not isinstance(state, dict):
        return ""
    raw = state.get("community_2024_paths", {})
    if not isinstance(raw, dict):
        return ""
    return _expand(str(raw.get(platform, "")).strip()) if str(raw.get(platform, "")).strip() else ""


def wasm_base_candidates(simulator: str, platform: str, state: dict | None = None) -> list[str]:
    defaults = default_wasm_scan_bases(simulator, platform)
    custom = custom_wasm_scan_paths(state, simulator, platform)
    return _normalize_path_list([*custom, *defaults])


def custom_wasm_scan_paths(state: dict | None, simulator: str, platform: str) -> list[str]:
    if not isinstance(state, dict):
        return []
    raw_map = state.get("wasm_scan_paths", {})
    if not isinstance(raw_map, dict):
        return []
    return _normalize_path_list(raw_map.get(community_key(simulator, platform), []))


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


def cycle_json_scan_bases(simulator: str, platform: str, state: dict | None = None) -> list[str]:
    defaults = default_wasm_scan_bases(simulator, platform)
    custom = custom_wasm_scan_paths(state, simulator, platform)
    return _normalize_path_list([*custom, *defaults])


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


def read_a346_builtin_cycle(addon: Addon, state: dict | None = None) -> tuple[str, str] | None:
    if not is_a346_addon(addon):
        return None

    package_name = infer_package_name(addon)
    candidates: list[Path] = []
    seen: set[str] = set()
    for base in community_base_candidates(state, addon.simulator, addon.platform, addon):
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


# Aerosoft A346 in MSFS 2024 moved its navdata out of Community and into the
# WASM\MSFS2024 tree starting with package_version 1.0.3. Earlier builds (<=
# 1.0.2) keep the data under Community/aerosoft-aircraft-a346-pro. We decide per
# install by reading package_version from the Community manifest.json.
A346_WASM2024_MIN_VERSION = "1.0.3"


def read_a346_community_version(addon: Addon, state: dict | None = None) -> str:
    """Read ``package_version`` from the A346 manifest.json under Community.

    The manifest always ships inside the Community package folder, so this is a
    reliable signal even after the navdata itself moves to WASM. Returns "" when
    the package folder or manifest is absent.
    """
    if not is_a346_addon(addon):
        return ""
    package_name = infer_package_name(addon)
    if not package_name:
        return ""
    for base in community_base_candidates(state, addon.simulator, addon.platform, addon):
        if not base:
            continue
        version = read_plugin_version_from_dir(Path(base) / package_name)
        if version:
            return version
    return ""


def a346_should_redirect_to_wasm2024(addon: Addon, state: dict | None = None) -> bool:
    """True when this A346 install should target WASM2024 instead of Community.

    Only applies to MSFS 2024 and only when the Community manifest reports
    package_version >= 1.0.3.
    """
    if not is_a346_addon(addon) or addon.simulator != "MSFS 2024":
        return False
    return version_at_least(read_a346_community_version(addon, state), A346_WASM2024_MIN_VERSION)


def resolve_a346_wasm2024_target(addon: Addon, state: dict | None = None) -> Path | None:
    """Resolve the A346 navdata target under WASM\\MSFS2024 (same folder name).

    Returns the existing ``WASM2024/<package>[/<navdata_subpath>]`` path (or a
    nested cycle dir within it) when present; otherwise returns the prospective
    path under the first WASM2024 base so a fresh install can create it. Returns
    None when no WASM2024 base is configured.
    """
    package_name = infer_package_name(addon)
    if not package_name:
        return None
    bases = [
        base
        for base in wasm_base_candidates(addon.simulator, addon.platform, state)
        if "msfs2024" in base.replace("\\", "/").lower()
    ]
    if not bases:
        return None
    prospective: Path | None = None
    for base in bases:
        candidate = Path(base) / package_name
        if addon.navdata_subpath:
            candidate = candidate / addon.navdata_subpath
        if prospective is None:
            prospective = candidate
        if candidate.exists():
            nested = find_nested_cycle_dir(candidate, addon)
            return nested if nested is not None else candidate
    return prospective


def is_external_folder_addon(addon: Addon) -> bool:
    """True for catalog packages that install into a fixed external folder.

    These come from Navigraph ``external`` strategy packages (FSiPanel, HiFi,
    TFM, TDS GTNXi, ...). Their target lives outside Community and is carried
    verbatim in ``addon.target_path`` (an expandvars path), so it is resolved
    directly rather than via folder-signature scanning.
    """
    tp = str(getattr(addon, "target_path", "") or "").strip()
    if not tp:
        return False
    # Fenix / FSLabs have their own dedicated resolvers; don't double-handle.
    if is_fenix_addon(addon) or is_fslabs_addon(addon):
        return False
    return ("%" in tp) or os.path.isabs(_expand(tp))


def resolve_external_folder_target(addon: Addon) -> Path | None:
    p = Path(_expand(addon.target_path))
    return p if p.exists() and p.is_dir() else None


def is_community_plugin_addon(addon: Addon) -> bool:
    """True for whole-folder Navigraph packages installed fresh into Community.

    These (Academy, Charts, SimBrief, Avionics plugins) carry no cycle.json and
    are dropped into ``Community/<package_name>`` as a single folder.
    """
    return str(getattr(addon, "install_mode", "") or "").strip() == "community_plugin"


def community_plugin_install_target(addon: Addon, state: dict | None = None) -> Path | None:
    """Where a community-plugin addon should be installed (even if not present yet).

    Returns ``Community/<package_name>`` for the addon's simulator/platform.
    Prefers an existing folder; otherwise returns the path under the first
    available Community base so a fresh install can create it.
    """
    pkg = infer_package_name(addon)
    if not pkg:
        return None
    bases = community_base_candidates(state, addon.simulator, addon.platform, addon)
    if not bases:
        return None
    for base in bases:
        candidate = Path(base) / pkg
        if candidate.exists():
            return candidate
    return Path(bases[0]) / pkg


def read_plugin_version_from_dir(folder: Path | None) -> str:
    """Read ``package_version`` from an installed plugin folder's manifest.json."""
    if folder is None:
        return ""
    try:
        manifest = folder / "manifest.json"
        if not manifest.exists():
            return ""
        payload = json.loads(manifest.read_text(encoding="utf-8", errors="ignore"))
        if isinstance(payload, dict):
            return str(payload.get("package_version", "")).strip()
    except Exception:
        return ""
    return ""


def resolve_target_dir(addon: Addon, state: dict | None = None) -> Path | None:
    if is_sim_base_navdata_addon(addon):
        if state is None:
            return None
        for base in community_base_candidates(state, addon.simulator, addon.platform, addon):
            p = Path(base)
            if p.exists() and p.is_dir():
                return p
        return None
    if is_fenix_addon(addon):
        p = Path(fenix_navdata_path())
        if p.exists():
            return p
    if is_fslabs_addon(addon):
        p = Path(fslabs_navdata_path())
        if p.exists():
            return p

    if is_external_folder_addon(addon):
        return resolve_external_folder_target(addon)

    if is_community_plugin_addon(addon):
        # Whole-folder Community plugin: target is Community/<package_name>.
        # Return it only if already installed; a fresh install resolves the
        # destination via community_plugin_install_target instead.
        target = community_plugin_install_target(addon, state)
        if target is not None and target.exists() and target.is_dir():
            return target
        return None

    if a346_should_redirect_to_wasm2024(addon, state):
        # A346 >= 1.0.3 keeps its navdata under WASM\MSFS2024, not Community.
        wasm2024 = resolve_a346_wasm2024_target(addon, state)
        if wasm2024 is not None:
            return wasm2024

    if state is not None and addon_prefers_community(addon):
        for base in community_base_candidates(state, addon.simulator, addon.platform, addon):
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
        for base in community_base_candidates(state, addon.simulator, addon.platform, addon):
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


def addon_status(addon: Addon, api_cycle: str, state: dict | None = None) -> tuple[str, str, str, str]:
    if is_community_plugin_addon(addon):
        # Whole-folder plugin: no AIRAC. Installed => UP TO DATE, else NOT
        # INSTALLED. Report the package_version (if any) in the installed slot.
        target = community_plugin_install_target(addon, state)
        if target is not None and target.exists() and target.is_dir():
            version = read_plugin_version_from_dir(target) or "INSTALLED"
            return "UP TO DATE", version, api_cycle, str(target)
        return "NOT INSTALLED", "NONE", api_cycle, str(target) if target is not None else ""
    if is_sim_base_navdata_addon(addon):
        target = resolve_target_dir(addon, state)
        if target and target.exists():
            required = sim_base_navdata_required_subfolders(addon)
            if required and all((target / sub).exists() for sub in required):
                return "UP TO DATE", "INSTALLED", api_cycle, str(target)
            return "NOT INSTALLED", "NONE", api_cycle, str(target)
        return "NOT INSTALLED", "NONE", api_cycle, ""
    if is_external_folder_addon(addon):
        # Third-party host folders (FSiPanel, HiFi Active Sky, TFM, TDS GTNXi):
        # we can only update data into an EXISTING external folder — we never
        # create it. If the folder is absent the host app isn't installed, so
        # report NOT INSTALLED (red) rather than offering a phantom target.
        target = resolve_external_folder_target(addon)
        if target is None:
            return "NOT INSTALLED", "NONE", api_cycle, ""
        installed = read_cycle_from_dir(target)
        if api_cycle in ("NONE", "UNKNOWN"):
            status = "API UNAVAILABLE"
        elif installed == api_cycle:
            status = "UP TO DATE"
        else:
            status = "UPDATE READY"
        return status, installed, api_cycle, str(target)
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


def clear_cycle_json_scan_cache() -> None:
    CYCLE_JSON_SCAN_CACHE.clear()


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
