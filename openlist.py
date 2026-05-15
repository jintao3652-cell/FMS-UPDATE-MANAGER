import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from state import APP_NAME, APP_VERSION, Addon
from targets import infer_package_name

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


def normalize_backup_power_login_url(raw_url: str) -> str:
    text = str(raw_url or "").strip()
    if not text:
        return BACKUP_POWER_LOGIN_URL
    if text.startswith("http://") or text.startswith("https://"):
        if "/api/auth/login" in text:
            return text
        return text.rstrip("/") + "/api/auth/login"
    return f"http://{text.strip('/').strip()}/api/auth/login"


def normalize_backup_power_download_dir(raw_path: str) -> str:
    text = str(raw_path or "").strip()
    if not text:
        return ""
    return str(Path(os.path.expandvars(text)).expanduser())


def backup_power_login_request(api_url: str, username: str, password: str) -> dict:
    payload = {
        "username": username,
        "password": password,
        "client": APP_NAME,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
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
    return {"status": status, "token": token, "message": message or "登录成功", "raw": raw}


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
        detail = str((data.get("detail") if isinstance(data, dict) else "") or (data.get("message") if isinstance(data, dict) else "") or raw or str(exc)).strip()
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
    return {"status": status, "user": user if isinstance(user, dict) else {}, "raw": raw}


def openlist_login_request() -> str:
    global OPENLIST_TOKEN_CACHE
    payload = {"username": OPENLIST_USERNAME, "password": OPENLIST_PASSWORD, "otp_code": ""}
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
    payload = {"path": path, "page": 1, "per_page": 500, "refresh": False}
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
    hints = ("token", "authorization", "unauthorized", "invalidated", "missing authorization")
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

    def is_excluded_name(name_norm: str) -> bool:
        if package == "inibuilds-aircraft-a340" and addon.simulator == "MSFS 2024":
            return any(token in name_norm for token in ("a340600", "a346"))
        return False

    def find_by_rules(rules: list[tuple[str, ...]]) -> dict | None:
        for rule in rules:
            candidates: list[tuple[dict, str, str]] = []
            for tup in file_items:
                if is_excluded_name(tup[2]):
                    continue
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
    elif package == "inibuilds-aircraft-a340" and addon.simulator == "MSFS 2024":
        hard_rules = [("inibuilds", "a343"), ("inibuilds", "a340", "300"), ("inibuilds", "a340")]
    elif package in {"inibuilds-aircraft-a340", "inibuilds-aircraft-a350"}:
        hard_rules = [("inibuilds",)]
    elif package == "aerosoft-aircraft-a346-pro":
        hard_rules = [("toliss", "dfdv2"), ("toliss",)]

    hard_match = find_by_rules(hard_rules)
    if hard_match is not None:
        return hard_match

    hints = list(OPENLIST_ARCHIVE_NAME_HINTS.get(package, ()))
    if not hints:
        hints = [p for p in infer_package_name(addon).split("-") if len(p) >= 3]
    hints_norm = [_norm_token(h) for h in hints if _norm_token(h)]

    best_item: dict | None = None
    best_score = -1
    tie = False
    for item, name, name_norm in file_items:
        if is_excluded_name(name_norm):
            continue
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
        headers={"Accept": "*/*", "User-Agent": "FMS-Update-Manager-Flet", "Connection": "close"},
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
