"""Incremental updater for FMS UPDATE MANAGER.

This module has two entry points:

1. ``run_updater_mode(args)`` — invoked when the main exe is launched with
   ``--updater <install_dir> <staging_dir>``. The currently running process is
   a *copy* of the main exe placed in %TEMP% (so it can replace files in the
   real install directory). It waits for the original main process to exit,
   replaces files according to the manifest, starts the new main exe, watches
   for a heartbeat, and rolls back on failure.

2. ``check_and_apply_incremental_update(...)`` — invoked from the running main
   UI to download a manifest, diff against local files, fetch the release zip,
   stage changed files, then re-launch a copy of itself in updater mode.

Only enabled in portable mode (``state.PORTABLE_MODE``); MSI installs continue
to use the existing MSI MajorUpgrade flow.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from update_keys import (
    HEARTBEAT_TIMEOUT_SEC,
    MANIFEST_FILENAME,
    MANIFEST_SIG_FILENAME,
    PUBLIC_KEY_HEX,
    RELEASE_ZIP_FILENAME,
    UPDATER_BACKUP_DIRNAME,
    UPDATER_HEARTBEAT_FILENAME,
    UPDATER_LOG_FILENAME,
    UPDATER_STAGING_DIRNAME,
)

CHUNK = 1 << 20
HEARTBEAT_GRACE_SEC = 5


def _log_path(install_dir: Path) -> Path:
    return install_dir / UPDATER_LOG_FILENAME


def _ulog(install_dir: Path, msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
    try:
        with _log_path(install_dir).open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Signature verification (pure-python Ed25519 to avoid runtime cryptography dep)
# ---------------------------------------------------------------------------
# Compact RFC8032 Ed25519 verify.

_p = (1 << 255) - 19
_L = (1 << 252) + 27742317777372353535851937790883648493


def _modp_inv(x: int) -> int:
    return pow(x, _p - 2, _p)


_d = -121665 * _modp_inv(121666) % _p
_modp_sqrt_m1 = pow(2, (_p - 1) // 4, _p)


def _sha512(b: bytes) -> bytes:
    return hashlib.sha512(b).digest()


def _point_compress(P):
    zinv = _modp_inv(P[2])
    x = P[0] * zinv % _p
    y = P[1] * zinv % _p
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _recover_x(y: int, sign: int) -> int | None:
    if y >= _p:
        return None
    x2 = (y * y - 1) * _modp_inv(_d * y * y + 1)
    if x2 == 0:
        if sign:
            return None
        return 0
    x = pow(x2, (_p + 3) // 8, _p)
    if (x * x - x2) % _p != 0:
        x = x * _modp_sqrt_m1 % _p
    if (x * x - x2) % _p != 0:
        return None
    if (x & 1) != sign:
        x = _p - x
    return x


_g_y = 4 * _modp_inv(5) % _p
_g_x = _recover_x(_g_y, 0)
_G = (_g_x, _g_y, 1, _g_x * _g_y % _p)


def _point_add(P, Q):
    A = (P[1] - P[0]) * (Q[1] - Q[0]) % _p
    B = (P[1] + P[0]) * (Q[1] + Q[0]) % _p
    C = 2 * P[3] * Q[3] * _d % _p
    D = 2 * P[2] * Q[2] % _p
    E = B - A
    F = D - C
    G = D + C
    H = B + A
    return (E * F, G * H, F * G, E * H)


def _point_mul(s: int, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _point_add(Q, P)
        P = _point_add(P, P)
        s >>= 1
    return Q


def _point_equal(P, Q) -> bool:
    if (P[0] * Q[2] - Q[0] * P[2]) % _p != 0:
        return False
    if (P[1] * Q[2] - Q[1] * P[2]) % _p != 0:
        return False
    return True


def _point_decompress(s: bytes):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = (y >> 255) & 1
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _p)


def _verify_ed25519(public_key: bytes, message: bytes, signature: bytes) -> bool:
    if len(public_key) != 32 or len(signature) != 64:
        return False
    A = _point_decompress(public_key)
    if A is None:
        return False
    Rs = signature[:32]
    R = _point_decompress(Rs)
    if R is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False
    h = int.from_bytes(_sha512(Rs + public_key + message), "little") % _L
    sB = _point_mul(s, _G)
    hA = _point_mul(h, A)
    return _point_equal(sB, _point_add(R, hA))


# ---------------------------------------------------------------------------
# manifest helpers
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            buf = fh.read(CHUNK)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def _http_get(url: str, *, timeout: float = 30.0) -> bytes:
    headers = {"User-Agent": "FMS-Update-Manager-Incremental", "Accept": "*/*"}
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _http_download(url: str, dest: Path, *, timeout: float = 120.0,
                   on_progress: Callable[[int, int | None], None] | None = None) -> None:
    headers = {"User-Agent": "FMS-Update-Manager-Incremental", "Accept": "*/*"}
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout) as resp:
        total_raw = resp.headers.get("Content-Length")
        total = int(total_raw) if (total_raw or "").isdigit() else None
        downloaded = 0
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as fh:
            while True:
                buf = resp.read(CHUNK)
                if not buf:
                    break
                fh.write(buf)
                downloaded += len(buf)
                if on_progress is not None:
                    try:
                        on_progress(downloaded, total)
                    except Exception:
                        pass


def _verify_manifest(manifest_bytes: bytes, signature: bytes) -> bool:
    try:
        pub = bytes.fromhex(PUBLIC_KEY_HEX)
    except Exception:
        return False
    return _verify_ed25519(pub, manifest_bytes, signature)


# ---------------------------------------------------------------------------
# Asset URL discovery from a GitHub release dict
# ---------------------------------------------------------------------------

def _find_asset(release: dict, name: str) -> str:
    for asset in release.get("assets", []) or []:
        if not isinstance(asset, dict):
            continue
        if str(asset.get("name", "")).strip().lower() == name.lower():
            url = str(asset.get("browser_download_url", "")).strip()
            if url:
                return url
    return ""


# ---------------------------------------------------------------------------
# Client side: prepare update + spawn updater copy
# ---------------------------------------------------------------------------

class IncrementalUpdateError(RuntimeError):
    pass


def prepare_incremental_update(
    release: dict,
    install_dir: Path,
    *,
    on_progress: Callable[[str, int, int | None], None] | None = None,
) -> tuple[Path, Path]:
    """Download manifest, verify, diff, fetch zip, stage files.

    Returns (staging_dir, updater_exe_copy_path).
    """
    install_dir = install_dir.resolve()
    manifest_url = _find_asset(release, MANIFEST_FILENAME)
    sig_url = _find_asset(release, MANIFEST_SIG_FILENAME)
    zip_url = _find_asset(release, RELEASE_ZIP_FILENAME)
    if not (manifest_url and sig_url and zip_url):
        raise IncrementalUpdateError(
            f"release missing required assets ({MANIFEST_FILENAME} / {MANIFEST_SIG_FILENAME} / {RELEASE_ZIP_FILENAME})"
        )

    if on_progress:
        on_progress("manifest", 0, None)
    manifest_bytes = _http_get(manifest_url)
    sig_bytes = _http_get(sig_url)
    if not _verify_manifest(manifest_bytes, sig_bytes):
        raise IncrementalUpdateError("manifest signature verification failed")

    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except Exception as exc:
        raise IncrementalUpdateError(f"manifest is not valid JSON: {exc}") from exc

    files = manifest.get("files") or []
    if not isinstance(files, list) or not files:
        raise IncrementalUpdateError("manifest has no files")

    # diff: which files differ vs install_dir
    needed: list[dict] = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        rel = str(entry.get("path", "")).strip()
        sha = str(entry.get("sha256", "")).strip().lower()
        if not rel or not sha:
            continue
        local = install_dir / rel
        if local.exists() and local.is_file():
            try:
                if _sha256_file(local) == sha:
                    continue
            except Exception:
                pass
        needed.append({"path": rel, "sha256": sha, "size": int(entry.get("size", 0) or 0)})

    staging = install_dir / UPDATER_STAGING_DIRNAME
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "manifest.json").write_bytes(manifest_bytes)
    (staging / "manifest.json.sig").write_bytes(sig_bytes)

    if not needed:
        # Nothing to do; still spawn updater so heartbeat / version stamp run.
        return staging, _copy_self_to_temp()

    # Download the release zip; extract only the changed files into staging/.
    zip_path = staging / "_release.zip"

    def _zip_progress(done: int, total: int | None) -> None:
        if on_progress:
            on_progress("download", done, total)

    _http_download(zip_url, zip_path, on_progress=_zip_progress)

    if on_progress:
        on_progress("extract", 0, len(needed))
    needed_set = {entry["path"].replace("\\", "/") for entry in needed}
    extracted = 0
    with zipfile.ZipFile(zip_path) as zf:
        members = {info.filename.replace("\\", "/"): info for info in zf.infolist() if not info.is_dir()}
        # release.zip is built from dist root; entries should match manifest paths directly.
        for rel in needed_set:
            info = members.get(rel)
            if info is None:
                # Some zips may include a top-level dir; try fuzzy match
                tail_match = None
                for k in members:
                    if k.endswith("/" + rel):
                        tail_match = k
                        break
                if tail_match is None:
                    raise IncrementalUpdateError(f"file not found in release.zip: {rel}")
                info = members[tail_match]
            target = staging / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=CHUNK)
            extracted += 1
            if on_progress:
                on_progress("extract", extracted, len(needed))

    try:
        zip_path.unlink()
    except Exception:
        pass

    # Verify staged files match expected hashes
    for entry in needed:
        rel = entry["path"]
        actual = _sha256_file(staging / rel)
        if actual != entry["sha256"]:
            raise IncrementalUpdateError(f"hash mismatch after staging: {rel}")

    return staging, _copy_self_to_temp()


def _copy_self_to_temp() -> Path:
    src = Path(sys.executable).resolve()
    tmp = Path(tempfile.mkdtemp(prefix="fms_updater_"))
    dst = tmp / src.name
    shutil.copy2(src, dst)
    return dst


def spawn_updater(updater_exe: Path, install_dir: Path, staging: Path) -> None:
    cmd = [str(updater_exe), "--updater", str(install_dir), str(staging), str(os.getpid())]
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(cmd, close_fds=True, creationflags=creationflags)


# ---------------------------------------------------------------------------
# Updater mode: run inside the temp-copy exe
# ---------------------------------------------------------------------------

def _wait_pid_exit(pid: int, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.5)
    return False


def _pid_alive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
            if not ok:
                return False
            return code.value == STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    except Exception:
        return False


def _backup_and_apply(install_dir: Path, staging: Path, manifest: dict) -> Path:
    backup_dir = install_dir / UPDATER_BACKUP_DIRNAME
    if backup_dir.exists():
        shutil.rmtree(backup_dir, ignore_errors=True)
    backup_dir.mkdir(parents=True, exist_ok=True)

    files = manifest.get("files") or []
    staged_paths: list[str] = []
    for entry in files:
        rel = str(entry.get("path", "")).strip()
        if not rel:
            continue
        staged = staging / rel
        if not staged.exists():
            continue
        staged_paths.append(rel)

    # Backup originals (only those we'll overwrite)
    for rel in staged_paths:
        target = install_dir / rel
        if target.exists() and target.is_file():
            bk = backup_dir / rel
            bk.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, bk)

    # Apply
    for rel in staged_paths:
        src = staging / rel
        dst = install_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            if dst.exists():
                dst.unlink()
        except PermissionError:
            tmp = dst.with_suffix(dst.suffix + ".old")
            try:
                tmp.unlink()
            except Exception:
                pass
            os.replace(dst, tmp)
        shutil.copy2(src, dst)

    return backup_dir


def _rollback(install_dir: Path, backup_dir: Path) -> None:
    if not backup_dir.exists():
        return
    for src in backup_dir.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(backup_dir).as_posix()
        dst = install_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            if dst.exists():
                dst.unlink()
        except Exception:
            pass
        shutil.copy2(src, dst)


def _wait_heartbeat(install_dir: Path, deadline_ts: float) -> bool:
    hb = install_dir / UPDATER_HEARTBEAT_FILENAME
    while time.time() < deadline_ts:
        if hb.exists():
            try:
                content = hb.read_text(encoding="utf-8", errors="ignore").strip()
                if content:
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    return False


def run_updater_mode(argv: list[str]) -> int:
    # argv: ["--updater", install_dir, staging_dir, parent_pid]
    if len(argv) < 4:
        return 2
    install_dir = Path(argv[1]).resolve()
    staging = Path(argv[2]).resolve()
    try:
        parent_pid = int(argv[3])
    except Exception:
        parent_pid = 0

    _ulog(install_dir, f"updater started; install={install_dir} staging={staging} parent_pid={parent_pid}")

    if parent_pid > 0:
        if not _wait_pid_exit(parent_pid, timeout=60.0):
            _ulog(install_dir, "parent process did not exit in 60s; aborting")
            return 3

    # Read & re-verify staged manifest
    manifest_path = staging / "manifest.json"
    sig_path = staging / "manifest.json.sig"
    try:
        manifest_bytes = manifest_path.read_bytes()
        sig_bytes = sig_path.read_bytes()
    except Exception as exc:
        _ulog(install_dir, f"failed to read staged manifest: {exc}")
        return 4
    if not _verify_manifest(manifest_bytes, sig_bytes):
        _ulog(install_dir, "staged manifest signature verification FAILED; aborting")
        return 5
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except Exception as exc:
        _ulog(install_dir, f"manifest parse error: {exc}")
        return 6

    # Clear any previous heartbeat
    hb = install_dir / UPDATER_HEARTBEAT_FILENAME
    try:
        if hb.exists():
            hb.unlink()
    except Exception:
        pass

    try:
        backup_dir = _backup_and_apply(install_dir, staging, manifest)
        _ulog(install_dir, f"applied {len(manifest.get('files') or [])} entries; backup at {backup_dir}")
    except Exception as exc:
        _ulog(install_dir, f"apply failed: {exc}; attempting rollback")
        _rollback(install_dir, install_dir / UPDATER_BACKUP_DIRNAME)
        return 7

    # Launch new main exe
    main_exe = install_dir / Path(sys.executable).name
    if not main_exe.exists():
        # frozen exe name may differ; try common names
        candidates = [
            "FMS_UPDATE_MANAGER.exe",
            "FMS_UPDATE_MANAGER_beta.exe",
        ]
        for cand in candidates:
            p = install_dir / cand
            if p.exists():
                main_exe = p
                break

    try:
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen([str(main_exe)], cwd=str(install_dir), creationflags=creationflags, close_fds=True)
        _ulog(install_dir, f"launched {main_exe}")
    except Exception as exc:
        _ulog(install_dir, f"launch failed: {exc}; rolling back")
        _rollback(install_dir, install_dir / UPDATER_BACKUP_DIRNAME)
        return 8

    deadline = time.time() + HEARTBEAT_TIMEOUT_SEC + HEARTBEAT_GRACE_SEC
    if not _wait_heartbeat(install_dir, deadline):
        _ulog(install_dir, "heartbeat timeout; rolling back")
        _rollback(install_dir, install_dir / UPDATER_BACKUP_DIRNAME)
        # Re-launch the (now-rolled-back) main exe
        try:
            subprocess.Popen([str(main_exe)], cwd=str(install_dir), close_fds=True)
        except Exception:
            pass
        return 9

    _ulog(install_dir, "heartbeat ok; cleanup")
    # Cleanup: staging + backup
    try:
        shutil.rmtree(install_dir / UPDATER_BACKUP_DIRNAME, ignore_errors=True)
    except Exception:
        pass
    try:
        shutil.rmtree(staging, ignore_errors=True)
    except Exception:
        pass
    return 0


def write_heartbeat(install_dir: Path) -> None:
    """Called by the main app on successful startup to signal the updater."""
    try:
        hb = install_dir / UPDATER_HEARTBEAT_FILENAME
        hb.write_text(f"{int(time.time())}\n", encoding="utf-8")
    except Exception:
        pass
