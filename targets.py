import json
import os
import re
from pathlib import Path
from state import Addon


def _expand(raw: str) -> str:
    return os.path.normpath(os.path.expandvars(raw))


def _norm_token(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def _normalized_path_parts(path: Path) -> list[str]:
    return [_norm_token(part) for part in path.parts if _norm_token(part)]


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
    tokens.extend(
        [
            p
            for p in normalized_name.split()
            if len(p) >= 3 and p not in {"the", "and", "for", "family", "series", "professional"}
        ]
    )
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


def is_pmdg_737_addon(addon: Addon) -> bool:
    package = addon.package_name.strip().lower()
    name = addon.name.strip().lower()
    return package.startswith("pmdg-aircraft-73") or "pmdg 737" in name


def is_ifly_737max8_addon(addon: Addon) -> bool:
    package = addon.package_name.strip().lower()
    name = addon.name.strip().lower()
    if package == "ifly-aircraft-737max8":
        return True
    return "ifly" in name and ("737max8" in name or "737 max" in name or "max8" in name)


def is_inibuilds_msfs2024_a340_addon(addon: Addon) -> bool:
    return addon.simulator == "MSFS 2024" and addon.package_name.strip().lower() == "inibuilds-aircraft-a340"


def _is_a343_text(hay: str, compact: str) -> bool:
    return "a340-300" in hay or "a340300" in compact or "a343" in compact


def _is_a346_text(hay: str, compact: str) -> bool:
    return "a340-600" in hay or "a340600" in compact or "a346" in compact


def _is_inibuilds_a340_text(hay: str, compact: str) -> bool:
    return "a340" in compact or _is_a343_text(hay, compact)


def text_matches_addon_signature(addon: Addon, text: str) -> bool:
    hay = text.strip().lower()
    if not hay:
        return False
    tokens = addon_search_tokens(addon)
    strong_tokens = [token for token in tokens if any(ch.isdigit() for ch in token) or "-" in token]
    if strong_tokens:
        return any(token in hay for token in strong_tokens)
    return any(token in hay for token in tokens)


def cycle_name_matches_addon(addon: Addon, cycle_name: str) -> bool:
    hay = cycle_name.strip().lower()
    compact = re.sub(r"[^a-z0-9]+", "", hay)
    name = addon.name.strip().lower()
    package = addon.package_name.strip().lower()
    if not hay:
        return False
    if is_ifly_737max8_addon(addon):
        return "ifly" in hay and ("737-max8" in hay or "737max8" in compact or "max8" in compact)
    if is_pmdg_737_addon(addon):
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
        if is_inibuilds_msfs2024_a340_addon(addon):
            if "dfd" in hay:
                return not _is_a346_text(hay, compact)
            return _is_inibuilds_a340_text(hay, compact) and not _is_a346_text(hay, compact)
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
        if "toliss" in compact:
            return True
        return "a340-600" in hay or "a346" in compact
    return text_matches_addon_signature(addon, cycle_name)


def cycle_name_is_generic_for_addon(addon: Addon, cycle_name: str) -> bool:
    hay = cycle_name.strip().lower()
    compact = re.sub(r"[^a-z0-9]+", "", hay)
    name = addon.name.strip().lower()
    package = addon.package_name.strip().lower()
    if not hay:
        return False
    if is_ifly_737max8_addon(addon):
        if "ifly" not in hay:
            return False
        return not any(token in compact for token in ("737max8", "max8", "b738m", "b38m"))
    if is_pmdg_737_addon(addon):
        if "pmdg" not in hay:
            return False
        specific_tokens = ("736", "737600", "737700", "738", "737800", "739", "737900")
        return not any(token in compact for token in specific_tokens)
    if package.startswith("pmdg-aircraft-77") or "pmdg 777" in name:
        if "pmdg" not in hay:
            return False
        specific_tokens = ("77l", "777200lr", "200lr", "77er", "777200er", "200er", "77f", "777f", "freighter", "77w", "777300er", "300er")
        return not any(token in compact for token in specific_tokens)
    return False


def folder_name_matches_addon_signature(addon: Addon, candidate_dir: Path) -> bool:
    parts = _normalized_path_parts(candidate_dir)
    if not parts:
        return False
    package = addon.package_name.strip().lower()

    def part_has(token: str) -> bool:
        token_norm = _norm_token(token)
        return bool(token_norm) and any(token_norm in part for part in parts)

    if is_ifly_737max8_addon(addon):
        if part_has("pmdg") or part_has("pmdg-aircraft-73"):
            return False
        return part_has("ifly") and (part_has("ifly-aircraft-737max8") or part_has("737max8") or part_has("max8") or part_has("b738m") or part_has("b38m"))

    if is_pmdg_737_addon(addon):
        if part_has("ifly") or part_has("ifly-aircraft-737max8"):
            return False
        expected_package = infer_package_name(addon)
        if expected_package and part_has(expected_package):
            return True
        if package == "pmdg-aircraft-736":
            return part_has("736") or part_has("737600")
        if package == "pmdg-aircraft-737":
            return part_has("737") or part_has("737700")
        if package == "pmdg-aircraft-738":
            return part_has("738") or part_has("737800")
        if package == "pmdg-aircraft-739":
            return part_has("739") or part_has("737900")
        return part_has("pmdg") and any(part_has(token) for token in ("736", "737", "738", "739"))

    if package == "inibuilds-aircraft-a340" and is_inibuilds_msfs2024_a340_addon(addon):
        return part_has("inibuilds") and part_has("a340") and not (part_has("a340-600") or part_has("a346"))

    expected = infer_package_name(addon)
    if expected and part_has(expected):
        return True
    if package == "fnx-aircraft-320":
        return part_has("fenix")
    if package == "fslabs-aircraft-a321":
        return part_has("fslabs")
    if package == "tfdidesign-aircraft-md11":
        return part_has("tfdi") or part_has("md11")
    if package == "fycyc-aircraft-c919x":
        return part_has("fycyc") or part_has("c919")
    if package == "justflight-aircraft-rj":
        return part_has("justflight") and part_has("rj")
    if package == "aerosoft-aircraft-a346-pro":
        return part_has("aerosoft") or part_has("a346") or part_has("toliss")
    if package == "inibuilds-aircraft-a340":
        return part_has("inibuilds") and part_has("a340")
    if package == "inibuilds-aircraft-a350":
        return part_has("inibuilds") and part_has("a350")
    if package == "ifly-aircraft-737max8":
        return part_has("ifly") and (part_has("737max8") or part_has("max8") or part_has("b738m"))
    if package == "aerosoft-crj":
        return part_has("aerosoft") and part_has("crj")
    return text_matches_addon_signature(addon, "/".join(parts))


def path_matches_addon_signature(addon: Addon, candidate_dir: Path, cycle_json_path: Path | None = None) -> bool:
    if not folder_name_matches_addon_signature(addon, candidate_dir):
        return False
    if cycle_json_path is not None:
        cycle_name = read_cycle_json_name(cycle_json_path)
        if cycle_name:
            if cycle_name_matches_addon(addon, cycle_name):
                return True
            if cycle_name_is_generic_for_addon(addon, cycle_name):
                return True
            return False
        return not addon.package_name.strip().lower().startswith("pmdg-aircraft-")
    return True


def read_cycle_json_name(json_path: Path) -> str:
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return ""
    if isinstance(payload, dict):
        return str(payload.get("name", "")).strip()
    return ""
