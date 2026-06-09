import io
import json
import os
import re
import shutil
import subprocess
import struct
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

from state import Addon, LOCAL_DIR
from targets import is_a346_addon
from utils import detect_airac

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
    if any(
        name.endswith(suffix)
        for suffix in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz", ".tbz2", ".tar.xz", ".txz")
    ):
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


def read_cycle_json_name(json_path: Path) -> str:
    payload = load_cycle_json_payload(json_path)
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


def inspect_sim_base_payload(extracted_root: Path, required_subfolders: tuple[str, ...]) -> dict | None:
    """Locate a directory inside extracted_root that contains ALL required top-level subfolders.

    Returns {payload_dir, required} or None if no such directory exists.
    """
    if not required_subfolders:
        return None
    required_lower = tuple(s.lower() for s in required_subfolders)
    candidates: list[tuple[int, Path]] = []
    try:
        all_dirs = [extracted_root] + [p for p in extracted_root.rglob("*") if p.is_dir()]
    except Exception:
        all_dirs = [extracted_root]
    for d in all_dirs:
        try:
            names = {entry.name.lower(): entry for entry in d.iterdir() if entry.is_dir()}
        except Exception:
            continue
        if all(req in names for req in required_lower):
            try:
                depth = len(d.relative_to(extracted_root).parts)
            except ValueError:
                depth = 999
            candidates.append((depth, d))
    if not candidates:
        return None
    candidates.sort()
    payload_dir = candidates[0][1]
    return {"payload_dir": str(payload_dir), "required": list(required_subfolders)}



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


def _extract_with_system_tar_command(archive_path: Path, temp_dir: Path) -> None:
    exe = _find_system_tar_executable()
    if not exe:
        raise ValueError("system tar.exe not found.")
    result = _run_hidden_subprocess([exe, "-xf", str(archive_path), "-C", str(temp_dir)])
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"system tar extract failed ({result.returncode}): {err}")


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


def copy_payload_dir_to_target(
    addon: Addon,
    payload_dir: Path,
    install_base: Path,
    airac: str,
) -> tuple[int, Path]:
    """Stage the new payload to a sibling temp dir, swap atomically.

    Goal: if anything goes wrong mid-copy, the user's existing target dir is
    untouched. Old behavior wrote files in-place which could leave a half-
    overlaid Community/<addon>/ directory.

    Algorithm:
      1. Compute install_root (per-cycle dir for A346, else install_base).
      2. Build a sibling staging dir <install_root>.installing.tmp.
      3. If install_root exists, copy its current contents into the staging
         dir first (so files we don't overwrite remain).
      4. Copy payload on top of staging dir.
      5. Atomically rename old install_root -> <install_root>.replaced.tmp,
         then rename staging dir -> install_root.
      6. Delete .replaced.tmp.
    Any exception in 1-4 cleans up staging dir and leaves install_root intact.
    """
    if is_a346_addon(addon):
        if airac == "UNKNOWN":
            raise ValueError("A346 package cycle is missing in cycle.json.")
        install_root = install_base / f"cycle_{airac}"
    else:
        install_root = install_base
    install_root.parent.mkdir(parents=True, exist_ok=True)

    staging = install_root.parent / (install_root.name + ".installing.tmp")
    replaced = install_root.parent / (install_root.name + ".replaced.tmp")
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    if replaced.exists():
        shutil.rmtree(replaced, ignore_errors=True)

    copied_files = 0

    def copy_with_count(src, dst, *, follow_symlinks=True):
        nonlocal copied_files
        result = shutil.copy2(src, dst, follow_symlinks=follow_symlinks)
        copied_files += 1
        return result

    try:
        if install_root.exists() and install_root.is_dir():
            shutil.copytree(install_root, staging, dirs_exist_ok=True)
        else:
            staging.mkdir(parents=True, exist_ok=True)

        for child in payload_dir.iterdir():
            dst = staging / child.name
            if child.is_dir():
                shutil.copytree(child, dst, dirs_exist_ok=True, copy_function=copy_with_count)
            else:
                copy_with_count(child, dst)

        if install_root.exists():
            os.replace(install_root, replaced)
        os.replace(staging, install_root)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if replaced.exists() and not install_root.exists():
            try:
                os.replace(replaced, install_root)
            except Exception:
                pass
        raise
    finally:
        if replaced.exists():
            shutil.rmtree(replaced, ignore_errors=True)

    return copied_files, install_root


def cleanup_temp_dir(path: Path | None) -> None:
    if path is None:
        return
    shutil.rmtree(path, ignore_errors=True)
