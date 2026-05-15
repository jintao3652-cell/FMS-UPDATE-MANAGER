import io
import json
import os
import re
import shutil
import subprocess
import struct
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

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
                useful_entries = sum(1 for entry in members if (entry.startswith(prefix) if prefix else True) and Path(entry).name.lower() != "cycle.json")
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
    if any(name.endswith(suffix) for suffix in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz", ".tbz2", ".tar.xz", ".txz")):
        return "tar"
    return ""


def is_supported_archive_file(archive_path: Path) -> bool:
    name = archive_path.name.lower()
    return any(name.endswith(suffix) for suffix in COMMON_ARCHIVE_SUFFIXES)


def _detect_embedded_archive_in_sfx_exe(exe_path: Path) -> tuple[str, int] | None:
    try:
        data = exe_path.read_bytes()
    except Exception:
        return None
    if not data:
        return None
    signatures = [("7z", b"7z\xBC\xAF'\x1C"), ("rar", b"Rar!\x1A\x07\x01\x00"), ("rar", b"Rar!\x1A\x07\x00"), ("zip", b"PK\x03\x04")]
    candidates: list[tuple[int, str]] = []
    for kind, sig in signatures:
        idx = data.find(sig)
        if idx >= 0:
            candidates.append((idx, kind))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0])
    return candidates[0][1], candidates[0][0]


def read_cycle_json_name(json_path: Path) -> str:
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return ""
    if isinstance(payload, dict):
        return str(payload.get("name", "")).strip()
    return ""


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
    match = re.search(r"([0-9]{4})", str(value))
    return match.group(1) if match else "UNKNOWN"


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
        return {"cycle_json_path": str(cycle_json_path), "payload_dir": str(payload_dir), "cycle_name": cycle_name, "airac": airac}
    except Exception:
        return None


def _extract_with_system_tar_command(archive_path: Path, temp_dir: Path) -> None:
    exe = shutil.which("tar")
    if not exe:
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        candidate = system_root / "System32" / "tar.exe"
        if candidate.exists() and candidate.is_file():
            exe = str(candidate)
    if not exe:
        raise ValueError("system tar.exe not found.")
    result = subprocess.run([exe, "-xf", str(archive_path), "-C", str(temp_dir)], capture_output=True, text=True)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"system tar extract failed ({result.returncode}): {err}")


def extract_archive_cycle_json_to_temp(archive_path: Path, progress_callback: Callable[[str], None] | None = None) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="fms_cycle_probe_"))
    try:
        if progress_callback is not None:
            progress_callback(f"检测到压缩格式: {_archive_kind(archive_path)}")
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(temp_dir)
        return temp_dir
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def extract_archive_to_temp(archive_path: Path, progress_callback: Callable[[str], None] | None = None) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="fms_archive_"))
    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(temp_dir)
        return temp_dir
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def prepare_archive_payload(archive_path: Path, progress_callback: Callable[[str], None] | None = None) -> dict | None:
    kind = _archive_kind(archive_path)
    if kind == "zip":
        payload = inspect_zip_cycle_payload(archive_path)
        if payload:
            payload["probe_root"] = ""
            payload["payload_prefix"] = str(payload.get("payload_prefix", "")).strip()
        return payload
    probe_root = extract_archive_cycle_json_to_temp(archive_path, progress_callback=progress_callback)
    payload = inspect_extracted_cycle_payload(probe_root)
    if not payload:
        shutil.rmtree(probe_root, ignore_errors=True)
        return None
    payload["probe_root"] = str(probe_root)
    payload["payload_prefix"] = ""
    return payload
