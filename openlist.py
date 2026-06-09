import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from state import APP_NAME, APP_VERSION, Addon
from targets import addon_search_tokens, infer_package_name

BACKUP_POWER_SERVER_BASE = "http://fms.cnrpg.top:17306"
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
    "aerosoft-aircraft-a346-pro": ("toliss", "dfdv2", "as346", "a346", "aerosofta346", "aerosoft"),
    "navigraph-msfs2020-base": ("msfs2020",),
    "navigraph-msfs2024-base": ("msfs2024",),
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


def _is_winsock_access_error(exc: BaseException) -> bool:
    """Detect Windows WinError 10013 (WSAEACCES) — the OS denied the socket.

    This usually happens when Windows picks an ephemeral source port that falls
    inside a Hyper-V/WSL/Docker reserved range, or when a firewall blocks it.
    Retrying opens a new connection which typically lands on a different
    (allowed) source port, so it is worth a few attempts.
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, OSError) and getattr(cur, "winerror", None) == 10013:
            return True
        text = str(cur).lower()
        if ("winerror 10013" in text) or ("10013" in text and "套接字" in str(cur)):
            return True
        reason = getattr(cur, "reason", None)
        nxt = reason if isinstance(reason, BaseException) else (cur.__cause__ or cur.__context__)
        cur = nxt if isinstance(nxt, BaseException) else None
    return False


def _urlopen_with_retry(req: "Request", timeout: float, attempts: int = 4):
    """urlopen wrapper that retries on transient WinError 10013 socket errors."""
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            return urlopen(req, timeout=timeout)
        except (URLError, OSError) as exc:
            if _is_winsock_access_error(exc) and attempt < attempts - 1:
                last_exc = exc
                time.sleep(0.4 * (attempt + 1))
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise URLError("urlopen failed without raising")


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
            with _urlopen_with_retry(req, timeout=6) as resp:
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
                if "invalid credentials" in lowered or "invalid credential" in lowered or not detail:
                    detail = "账号或密码错误"
                raise ValueError(detail) from exc
            raise ValueError(detail or f"请求失败 ({exc.code})") from exc
        except URLError as exc:
            if attempt < 1:
                time.sleep(0.6 * (attempt + 1))
                continue
            if _is_winsock_access_error(exc):
                raise ValueError("无法连接服务器：本机网络访问被系统或安全软件拦截（WinError 10013），请检查防火墙/代理设置后重试。") from exc
            raise ValueError(f"网络连接失败: {exc}") from exc

    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {"raw": raw}
    if not isinstance(data, dict):
        data = {"raw": raw}

    ok_flag = data.get("success")
    token = str(data.get("token", "")).strip()
    refresh_token = str(data.get("refresh_token", "")).strip()
    refresh_expires_in = int(data.get("refresh_expires_in") or 0)
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
        "refresh_token": refresh_token,
        "refresh_expires_in": refresh_expires_in,
        "message": message or "登录成功",
        "raw": raw,
    }


def backup_power_refresh_request(api_url: str, refresh_token: str) -> dict:
    """Exchange a refresh token for a fresh access token.

    `api_url` should be the canonical login URL (e.g. http://.../api/auth/login).
    We swap the path to /api/auth/refresh for the actual call.
    """
    rt = str(refresh_token or "").strip()
    if not rt:
        raise ValueError("缺少 refresh_token。")
    try:
        from urllib.parse import urlsplit, urlunsplit
        u = urlsplit(api_url)
        target = urlunsplit((u.scheme, u.netloc, "/api/auth/refresh", "", ""))
    except Exception:
        target = api_url.rsplit("/api/auth/", 1)[0].rstrip("/") + "/api/auth/refresh"
    body = json.dumps({"refresh_token": rt}, ensure_ascii=False).encode("utf-8")
    req = Request(
        target,
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
        with _urlopen_with_retry(req, timeout=6) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            status_code = int(getattr(resp, "status", 200) or 200)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        try:
            detail_payload = json.loads(raw)
            detail = str(detail_payload.get("detail") or detail_payload.get("message") or raw).strip()
        except Exception:
            detail = raw.strip() or str(exc)
        raise ValueError(f"refresh 失败 ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise ValueError(f"refresh 网络错误: {exc}") from exc
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}
    new_token = str(data.get("token", "")).strip()
    if not new_token:
        raise ValueError("refresh 接口未返回新 token")
    return {"status": status_code, "token": new_token, "raw": raw}


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
        with _urlopen_with_retry(req, timeout=6) as resp:
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
        if _is_winsock_access_error(exc):
            raise ValueError("无法连接服务器：本机网络访问被系统或安全软件拦截（WinError 10013），请检查防火墙/代理设置后重试。") from exc
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

    def is_excluded_name(name_norm: str) -> bool:
        if package == "inibuilds-aircraft-a340" and addon.simulator == "MSFS 2024":
            return any(token in name_norm for token in ("a340600", "a346"))
        if package == "navigraph-msfs2020-base":
            return "msfs2024" in name_norm
        if package == "navigraph-msfs2024-base":
            return "msfs2020" in name_norm
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
    elif package == "inibuilds-aircraft-a340" and addon.simulator == "MSFS 2024":
        hard_rules = [("inibuilds", "a343"), ("inibuilds", "a340", "300"), ("inibuilds", "a340")]
    elif package in {"inibuilds-aircraft-a340", "inibuilds-aircraft-a350"}:
        hard_rules = [("inibuilds",)]
    elif package == "aerosoft-aircraft-a346-pro":
        hard_rules = [
            ("toliss", "dfdv2"),
            ("toliss",),
            ("as346",),
            ("aerosoft", "a346"),
            ("aerosoft", "a340"),
            ("a346",),
        ]
    elif package == "navigraph-msfs2020-base":
        hard_rules = [("msfs2020", "navdata"), ("msfs2020",)]
    elif package == "navigraph-msfs2024-base":
        hard_rules = [("msfs2024", "navdata"), ("msfs2024",)]

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
    expected_sha256: str = "",
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
    part_file = download_dir / (file_name + ".part")

    if local_file.exists() and local_file.is_file():
        local_file.unlink(missing_ok=True)

    resume_from = part_file.stat().st_size if part_file.exists() and part_file.is_file() else 0
    if progress_callback is not None:
        if resume_from > 0:
            progress_callback(f"检测到 .part 缓存，从 {resume_from} 字节断点续传: {file_name}")
        else:
            progress_callback(f"正在下载: {file_name}")

    headers = {
        "Accept": "*/*",
        "User-Agent": "FMS-Update-Manager-Flet",
        "Connection": "close",
    }
    if resume_from > 0:
        headers["Range"] = f"bytes={resume_from}-"

    req = Request(raw_url, headers=headers, method="GET")
    total_size = 0
    try:
        with urlopen(req, timeout=60) as resp:
            status_code = int(getattr(resp, "status", 200) or 200)
            if resume_from > 0 and status_code != 206:
                if progress_callback is not None:
                    progress_callback(f"服务器未返回 206，放弃续传，从头下载: {file_name}")
                part_file.unlink(missing_ok=True)
                resume_from = 0
            mode = "ab" if resume_from > 0 else "wb"
            with part_file.open(mode) as fh:
                if resume_from > 0:
                    total_size = resume_from
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    fh.write(chunk)
                    total_size += len(chunk)
    except HTTPError as exc:
        if exc.code == 416 and resume_from > 0:
            if progress_callback is not None:
                progress_callback(f"断点位置无效（416），从头下载: {file_name}")
            part_file.unlink(missing_ok=True)
            return download_openlist_archive_for_addon(addon, cycle_id, download_dir, progress_callback)
        raise
    if total_size <= 0:
        part_file.unlink(missing_ok=True)
        raise ValueError(f"下载失败或文件为空: {file_name}")

    expected_hash = str(expected_sha256 or (meta or {}).get("expected_sha256", "")).lower().strip()
    if expected_hash:
        import hashlib as _hashlib
        if progress_callback is not None:
            progress_callback(f"正在校验文件哈希: {file_name}")
        h = _hashlib.sha256()
        with part_file.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        got = h.hexdigest()
        if got != expected_hash:
            part_file.unlink(missing_ok=True)
            raise ValueError(
                f"下载文件 SHA256 校验失败: {file_name}\n  expected={expected_hash}\n  got={got}"
            )
        if progress_callback is not None:
            progress_callback(f"哈希校验通过: {file_name}")

    part_file.replace(local_file)
    if progress_callback is not None:
        progress_callback(f"下载完成: {file_name} ({total_size} bytes)")
    return {
        "archive_path": str(local_file),
        "archive_name": file_name,
        "cycle_id": cycle_text,
        "bytes": total_size,
        "remote_path": remote_path,
        "raw_url": raw_url,
        "sha256_verified": bool(expected_hash),
    }


def fetch_archive_expected_hash(token: str, cycle_id: str, archive_name: str) -> str:
    """Ask backup_auth for the expected SHA-256 of an archive. Returns '' if
    backend has no entry (and the caller should treat the download as
    unverified — log it but still install)."""
    token_text = str(token or "").strip()
    if not token_text:
        return ""
    from urllib.parse import urlencode
    url = (
        BACKUP_POWER_SERVER_BASE
        + "/api/navdata/archive_hash?"
        + urlencode({"cycle": cycle_id, "archive": archive_name})
    )
    req = Request(
        url,
        headers={"Authorization": f"Bearer {token_text}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError):
        return ""
    try:
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        return ""
    return str(data.get("sha256", "")).lower().strip()


def backup_power_cycle_subscription_get(token: str) -> dict:
    """GET /api/me/cycle_subscription"""
    token_text = str(token or "").strip()
    if not token_text:
        raise ValueError("缺少 token。")
    url = BACKUP_POWER_SERVER_BASE + "/api/me/cycle_subscription"
    req = Request(url, headers={"Authorization": f"Bearer {token_text}", "Accept": "application/json"}, method="GET")
    try:
        with urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError) as exc:
        raise ValueError(f"读取订阅状态失败: {exc}") from exc
    try:
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def backup_power_cycle_subscription_put(token: str, enabled: bool) -> dict:
    token_text = str(token or "").strip()
    if not token_text:
        raise ValueError("缺少 token。")
    url = BACKUP_POWER_SERVER_BASE + "/api/me/cycle_subscription"
    body = json.dumps({"enabled": bool(enabled)}).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {token_text}", "Content-Type": "application/json", "Accept": "application/json"},
        method="PUT",
    )
    try:
        with urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        try:
            d = json.loads(raw)
            detail = str(d.get("detail") or raw)
        except Exception:
            detail = raw or str(exc)
        raise ValueError(f"保存订阅失败 ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise ValueError(f"网络错误: {exc}") from exc
    try:
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def backup_power_cycle_check_now(token: str) -> dict:
    """POST /api/me/cycle_check_now — client-pull trigger."""
    token_text = str(token or "").strip()
    if not token_text:
        raise ValueError("缺少 token。")
    url = BACKUP_POWER_SERVER_BASE + "/api/me/cycle_check_now"
    req = Request(
        url,
        data=b"{}",
        headers={"Authorization": f"Bearer {token_text}", "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError) as exc:
        return {"success": False, "error": str(exc)}
    try:
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}
