import json
from datetime import timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import unquote
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from state import APP_NAME, APP_VERSION
from targets import infer_package_name
from utils import CYCLES_API_URL, detect_airac, parse_iso_utc

GITHUB_RELEASE_REPO = "jintao3652-cell/FMS-UPDATE-MANAGER"
GITHUB_RELEASE_LATEST_API = "https://api.github.com/repos/{repo}/releases/latest"
GITHUB_RELEASE_LIST_API = "https://api.github.com/repos/{repo}/releases?per_page=1"
GITHUB_TAG_LIST_API = "https://api.github.com/repos/{repo}/tags?per_page=1"
GITHUB_API_TOKEN = ""


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
    return {"tag_name": tag_name, "name": title or tag_name, "html_url": link or f"https://github.com/{normalized_repo}/releases", "_repo": normalized_repo}


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
    tags_url = GITHUB_TAG_LIST_API.format(repo=normalized_repo)
    status, payload = github_api_json(tags_url)
    if status == 200 and isinstance(payload, list) and payload:
        first = payload[0] if isinstance(payload[0], dict) else {}
        tag_name = str(first.get("name", "")).strip() if isinstance(first, dict) else ""
        if tag_name:
            return {"tag_name": tag_name, "name": tag_name, "html_url": f"https://github.com/{normalized_repo}/tags", "_repo": normalized_repo}
    atom_error = ""
    try:
        return fetch_latest_github_release_atom(normalized_repo)
    except Exception as exc:
        atom_error = str(exc)
    message = payload.get("message", "github api unavailable") if isinstance(payload, dict) else "github api unavailable"
    if atom_error:
        raise ValueError(f"github releases not available for {normalized_repo}: {message}; atom fallback failed: {atom_error}")
    raise ValueError(f"github releases not available for {normalized_repo}: {message}")


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
    current_rows.sort(key=lambda r: parse_iso_utc(str(r.get("cycle_start_date", "1970-01-01T00:00:00Z"))), reverse=True)
    current = current_rows[0]
    cycle_id = detect_airac(str(current.get("cycle_id", "UNKNOWN")))
    start_dt = parse_iso_utc(str(current.get("cycle_start_date", "1970-01-01T00:00:00Z")))
    end_dt = start_dt + timedelta(days=28)
    return {"cycle_id": cycle_id, "start": start_dt, "end": end_dt}

