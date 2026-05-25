"""Lightweight MSFS status probe used by the top bar.

Two sources are consulted; whichever resolves first wins:

1. Process detection (always available, no extra deps) — checks for
   ``FlightSimulator.exe`` (MSFS 2020) and ``FlightSimulator2024.exe``
   (MSFS 2024) via :mod:`psutil` when available, falling back to
   ``tasklist`` on Windows.
2. SimConnect — when the optional ``SimConnect`` package is installed,
   we try to open a session and read ``TITLE`` / ``SIM ON GROUND`` /
   ``CAMERA STATE`` so we can tell "in menu" from "in cockpit".

The probe runs in a background thread and pushes results into a small
queue; the UI polls :func:`latest_status`.  All errors are swallowed —
the worst case is that we report ``not_running``.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Optional


MSFS_2020_PROC = "FlightSimulator.exe"
MSFS_2024_PROC = "FlightSimulator2024.exe"


@dataclass
class SimStatus:
    running: bool = False
    sim_label: str = ""           # "MSFS 2020" / "MSFS 2024" / ""
    running_2020: bool = False
    running_2024: bool = False
    connected: bool = False        # SimConnect session is open
    aircraft_title: str = ""       # from SimConnect TITLE
    on_ground: Optional[bool] = None
    camera_state: Optional[int] = None
    last_error: str = ""
    updated_at: float = field(default_factory=time.time)

    def headline(self) -> str:
        """Short user-facing label for the top-bar badge."""
        if not self.running:
            return "MSFS 未运行"
        base = self.sim_label or "MSFS 运行中"
        if self.connected and self.aircraft_title:
            return f"{base} · {self.aircraft_title}"
        if self.connected:
            return f"{base} · 已连接"
        return base


_lock = threading.Lock()
_status = SimStatus()
_stop_event: Optional[threading.Event] = None
_worker: Optional[threading.Thread] = None


def latest_status() -> SimStatus:
    with _lock:
        return replace(_status)


def _set_status(new: SimStatus) -> None:
    global _status
    new.updated_at = time.time()
    with _lock:
        _status = new


def _resolve_simconnect_dll_path() -> str:
    candidates = []
    try:
        base_frozen = getattr(sys, "_MEIPASS", "")
        if base_frozen:
            candidates.append(os.path.join(base_frozen, "SimConnect.dll"))
    except Exception:
        pass
    try:
        exe_dir = os.path.dirname(sys.executable or "")
        if exe_dir:
            candidates.append(os.path.join(exe_dir, "SimConnect.dll"))
    except Exception:
        pass
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(here, "SimConnect.dll"))
    except Exception:
        pass
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return ""


def _probe_sim_via_simconnect() -> tuple[bool, bool, str, str]:
    """Open a SimConnect session and identify which sim is running.

    Returns (running_2020, running_2024, app_name, error).
    """
    try:
        from SimConnect import SimConnect  # type: ignore
    except Exception as exc:
        return False, False, "", f"simconnect import failed: {exc}"
    dll_path = _resolve_simconnect_dll_path()
    sm = None
    try:
        sm = SimConnect(auto_connect=False, dll_path=dll_path) if dll_path else SimConnect(auto_connect=False)
        try:
            sm.connect()
        except Exception:
            pass
        app_name = ""
        ver_major = 0
        for attr in ("ApplicationName", "_application_name", "szApplicationName"):
            value = getattr(sm, attr, "")
            if isinstance(value, (bytes, bytearray)):
                value = value.decode("utf-8", errors="ignore")
            value = str(value or "").strip("\x00 ").strip()
            if value:
                app_name = value
                break
        for attr in ("ApplicationVersionMajor", "_application_version_major", "dwApplicationVersionMajor"):
            try:
                v = int(getattr(sm, attr, 0) or 0)
            except Exception:
                v = 0
            if v:
                ver_major = v
                break
        if not app_name and not ver_major and not getattr(sm, "ok", False) and not getattr(sm, "running", False):
            return False, False, "", "simconnect not connected"
        name_lower = app_name.lower()
        is_2024 = ver_major >= 12 or "2024" in name_lower
        is_2020 = (not is_2024) and (
            ver_major in (10, 11) or "kittyhawk" in name_lower or "2020" in name_lower or bool(app_name)
        )
        return is_2020, is_2024, app_name, ""
    except Exception as exc:
        return False, False, "", f"simconnect open failed: {exc}"
    finally:
        if sm is not None:
            try:
                sm.exit()
            except Exception:
                pass


def _detect_running_sims() -> tuple[bool, bool]:
    """Return (running_2020, running_2024). Prefer SimConnect handshake; fall
    back to process scanning if SimConnect lib is unavailable."""
    r20, r24, _name, err = _probe_sim_via_simconnect()
    if r20 or r24:
        return r20, r24
    if not err.startswith("simconnect import failed"):
        return False, False
    names: set[str] = set()
    try:
        import psutil  # type: ignore
        names = {p.info["name"] for p in psutil.process_iter(["name"]) if p.info.get("name")}
    except Exception:
        names = set()
    if not names and os.name == "nt":
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", "IMAGENAME eq FlightSimulator*.exe", "/FO", "CSV", "/NH"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                stderr=subprocess.DEVNULL,
                timeout=4,
            ).decode("utf-8", errors="ignore")
            lower = out.lower()
            if MSFS_2020_PROC.lower() in lower:
                names.add(MSFS_2020_PROC)
            if MSFS_2024_PROC.lower() in lower:
                names.add(MSFS_2024_PROC)
        except Exception:
            pass
    return (MSFS_2020_PROC in names, MSFS_2024_PROC in names)


def _detect_running_sim() -> str:
    r20, r24 = _detect_running_sims()
    if r24:
        return "MSFS 2024"
    if r20:
        return "MSFS 2020"
    return ""


def _probe_simconnect(current: SimStatus) -> SimStatus:
    """Open a SimConnect session and read TITLE / SIM ON GROUND / CAMERA STATE.

    Returns a copy of ``current`` with the extra fields filled in (or the
    same object if SimConnect is unreachable). Never raises.
    """
    try:
        from SimConnect import SimConnect, AircraftRequests  # type: ignore
    except Exception as exc:
        return replace(current, last_error=f"simconnect import failed: {exc}")

    sm = None
    try:
        sm = SimConnect()
        ar = AircraftRequests(sm, _time=200)
        title_raw = ar.get("TITLE")
        on_ground_raw = ar.get("SIM_ON_GROUND")
        camera_raw = ar.get("CAMERA_STATE")
        title = ""
        if isinstance(title_raw, (bytes, bytearray)):
            title = title_raw.decode("utf-8", errors="ignore").strip("\x00 ").strip()
        elif title_raw is not None:
            title = str(title_raw).strip("\x00 ").strip()
        on_ground: Optional[bool] = None
        if on_ground_raw is not None:
            try:
                on_ground = bool(int(on_ground_raw))
            except Exception:
                on_ground = None
        camera_state: Optional[int] = None
        if camera_raw is not None:
            try:
                camera_state = int(camera_raw)
            except Exception:
                camera_state = None
        return replace(
            current,
            connected=True,
            aircraft_title=title,
            on_ground=on_ground,
            camera_state=camera_state,
            last_error="",
        )
    except Exception as exc:
        return replace(current, connected=False, last_error=f"simconnect probe failed: {exc}")
    finally:
        if sm is not None:
            try:
                sm.exit()
            except Exception:
                pass


def _worker_loop(stop_event: threading.Event, interval: float) -> None:
    while not stop_event.is_set():
        r20, r24 = _detect_running_sims()
        sim_label = "MSFS 2024" if r24 else ("MSFS 2020" if r20 else "")
        running = r20 or r24
        new = SimStatus(running=running, sim_label=sim_label, running_2020=r20, running_2024=r24)
        if running:
            new = _probe_simconnect(new)
        _set_status(new)
        stop_event.wait(interval if running else max(interval, 5.0))


def start_status_worker(interval: float = 2.5) -> None:
    """Idempotently spawn the background poller."""
    global _stop_event, _worker
    if _worker is not None and _worker.is_alive():
        return
    _stop_event = threading.Event()
    _worker = threading.Thread(
        target=_worker_loop,
        args=(_stop_event, interval),
        name="msfs-status-probe",
        daemon=True,
    )
    _worker.start()
