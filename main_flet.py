import json
import io
import os
import re
import asyncio
import base64
import ctypes
import sys
import subprocess
import shutil
import struct
import time
import webbrowser
import zipfile
import tempfile
import tarfile
import xml.etree.ElementTree as ET
from queue import Empty, SimpleQueue
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, cast
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

import flet as ft

import archive as archive_mod
import catalog as catalog_mod
import maintenance as maintenance_mod
import network as network_mod
import openlist as openlist_mod
import state as state_mod
import targets as targets_mod
import utils as utils_mod

from archive import (
    COMMON_ARCHIVE_SUFFIXES,
    _archive_kind,
    _detect_embedded_archive_in_sfx_exe,
    _extract_with_system_tar_command,
    extract_archive_cycle_json_to_temp,
    extract_archive_to_temp,
    extract_airac_from_value,
    extract_zip_payload_to_target,
    copy_payload_dir_to_target,
    cleanup_temp_dir,
    inspect_extracted_cycle_payload,
    inspect_sim_base_payload,
    inspect_zip_cycle_payload,
    is_supported_archive_file,
    load_cycle_json_payload,
    normalize_zip_member,
    prepare_archive_payload,
    read_cycle_from_payload,
    read_cycle_json,
    read_cycle_json_name,
)
from openlist import (
    BACKUP_POWER_LOGIN_URL,
    BACKUP_POWER_ME_URL,
    BACKUP_POWER_NAVDATA_DOWNLOAD_URL,
    BACKUP_POWER_SERVER_BASE,
    OPENLIST_BASE_URL,
    OPENLIST_GET_URL,
    OPENLIST_LIST_URL,
    OPENLIST_LOGIN_URL,
    OPENLIST_ROOT_PATH,
    OPENLIST_TOKEN_CACHE,
    OPENLIST_USERNAME,
    OPENLIST_PASSWORD,
    download_openlist_archive_for_addon,
    find_openlist_cycle_folder,
    find_openlist_cycle_msfs_folder,
    get_openlist_token,
    is_openlist_token_error,
    list_openlist_cycle_msfs_items,
    normalize_backup_power_download_dir,
    normalize_backup_power_login_url,
    openlist_cycle_msfs_path,
    openlist_cycle_path,
    openlist_get_file_meta_auto_request,
    openlist_get_file_meta_request,
    openlist_list_dir_auto_request,
    openlist_list_dir_request,
    openlist_login_request,
    select_openlist_archive_for_addon,
    backup_power_login_request,
    backup_power_me_request,
    backup_power_cycle_subscription_get,
    backup_power_cycle_subscription_put,
    backup_power_cycle_check_now,
    OPENLIST_ARCHIVE_NAME_HINTS,
)
from state import (
    APP_EXECUTABLE_NAME,
    APP_NAME,
    APP_VERSION,
    BACKUP_DIR,
    CACHE_CLEANUP_DAY_OPTIONS,
    DEFAULT_ADDON_FAMILIES,
    DEFAULT_BATCH_DOWNLOAD_WORKERS,
    DEFAULT_CACHE_CLEANUP_DAYS,
    DEFAULT_SIM_PLATFORM_VARIANTS,
    Addon,
    LOCAL_DIR,
    MSFS_VERSIONS,
    PLATFORMS,
    ROAMING_DIR,
    STATE_FILE,
    THEME_DARK,
    THEME_LIGHT,
    community_key,
    default_addons,
    load_state,
    normalize_batch_download_workers,
    normalize_cache_cleanup_days,
    save_state,
    to_addon,
    _addon_from_dict,
    enabled_simulators,
    INSTALLER_PACKAGE_NAME,
    INSTALLER_EXECUTABLE_NAME,
    INSTALLER_COMMANDLINE_HINTS,
    BATCH_DOWNLOAD_WORKER_OPTIONS,
)
from network import (
    GITHUB_API_TOKEN,
    GITHUB_RELEASE_LATEST_API,
    GITHUB_RELEASE_LIST_API,
    GITHUB_RELEASE_REPO,
    GITHUB_TAG_LIST_API,
    fetch_current_cycle,
    fetch_latest_github_release,
    fetch_latest_github_release_atom,
    github_api_json,
    normalize_github_repo,
)
from targets import (
    addon_search_tokens,
    cycle_name_is_generic_for_addon,
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
from catalog import (
    addon_key,
    addon_key as catalog_addon_key,
    addon_prefers_community,
    custom_wasm_scan_paths,
    cycle_json_scan_bases,
    default_community_base,
    read_cycle_from_dir,
    wasm_base_candidates,
    is_valid_community_path,
    is_valid_community2024_path,
    clear_cycle_json_scan_cache,
    addon_status,
    addon_status as catalog_addon_status,
    auto_detect_cycle_json_target,
    community_base_candidates,
    compute_filtered_addon_entries,
    compute_filtered_addon_entries as catalog_compute_filtered_addon_entries,
    default_wasm_scan_bases,
    fixed_relative_path,
    find_nested_cycle_dir,
    fslabs_navdata_path,
    is_fenix_addon,
    is_fslabs_addon,
    matches_filter,
    read_a346_builtin_cycle,
    resolve_target_dir,
    resolve_target_dir as catalog_resolve_target_dir,
    resolve_wasm_target_by_folder_name,
    resolve_wasm_target_by_folder_name as catalog_resolve_wasm_target_by_folder_name,
    status_badge_style,
    status_dot_color,
    CYCLE_JSON_SCAN_CACHE,
    _normalize_path_list,
)
from utils import (
    CYCLES_API_URL,
    LEGACY_LOG_FILE,
    LOG_DIR,
    append_log_file,
    current_log_file,
    decrypt_secret,
    detect_airac,
    encrypt_secret,
    format_version_display,
    fs,
    get_colors,
    human_datetime,
    human_time,
    parse_iso_utc,
    read_log_lines,
    _ensure_installer_not_running,
    acquire_singleton_lock,
    _is_newer_version,
    is_destroyed_session_error,
    is_button_busy,
    open_external_url,
    invoke_callback,
    find_latest_backup_for_addon as _utils_find_latest_backup_for_addon,
    FONT_SCALE,
)
from maintenance import (
    cleanup_backup_power_download_cache,
    cleanup_stale_cache_entries,
    default_backup_power_download_dir,
    default_batch_download_cache_dir,
    ensure_backup_power_download_dir,
    normalize_cache_cleanup_days,
    normalize_cache_root_dir,
    resolve_cache_root_dir,
    resolve_existing_backup_power_download_dir,
)

from crash_report import install_crash_handlers, list_recent_crash_logs, report_exception
from i18n import tr as _

ft.context.disable_auto_update()

TASKBAR_ICON_FILE = Path(__file__).resolve().parent / "assets" / "travel_airplane.ico"
APP_WINDOW_LOGO_FILE = Path(__file__).resolve().parent / "assets" / "logo_telegram.ico"
EXTRACTED_DIR = LOCAL_DIR / "extracted"


def main(  # pylint: disable=too-many-function-args,unexpected-keyword-arg,no-member
    page: ft.Page,
    fast_reload: bool = False,
    cached_cycle: dict | None = None,
):
    ft.context.disable_auto_update()
    for d in (ROAMING_DIR, LOG_DIR, LOCAL_DIR, EXTRACTED_DIR, BACKUP_DIR):
        d.mkdir(parents=True, exist_ok=True)

    state = load_state()
    state.setdefault("crash_upload_enabled", False)
    locale_first_run = "locale" not in state
    state.setdefault("locale", "zh")
    from i18n import set_locale as _set_locale
    _set_locale(state.get("locale") or "zh")
    install_crash_handlers(state_getter=lambda: state)
    if not isinstance(state.get("addons"), list) or not state.get("addons"):
        state["addons"] = default_addons()
        save_state(state)
    simulator = str(state.get("simulator", MSFS_VERSIONS[0]))
    platform = str(state.get("platform", PLATFORMS[0]))
    theme_name = str(state.get("theme", THEME_LIGHT))
    filter_value = "All"
    search_text = ""
    current_cycle_info: dict | None = cached_cycle
    selected_addon_key: str | None = None
    last_rendered_entries: list[tuple[Addon, str, str, str, str, str]] = []
    rebuild_generation = 0
    streamer_mode = bool(state.get("streamer_mode", False))

    addon_items = state.get("addons", []) if isinstance(state.get("addons"), list) else []
    migrated = False
    existing_addons = {
        (
            str(item.get("name", "")).strip(),
            str(item.get("simulator", "")).strip(),
            str(item.get("platform", "")).strip(),
        )
        for item in addon_items
        if isinstance(item, dict)
    }
    for default_item in default_addons():
        key = (
            str(default_item.get("name", "")).strip(),
            str(default_item.get("simulator", "")).strip(),
            str(default_item.get("platform", "")).strip(),
        )
        if key not in existing_addons:
            addon_items.append(default_item)
            existing_addons.add(key)
            migrated = True
    expected_packages = {
        "pmdg 737-600": "pmdg-aircraft-736",
        "pmdg 737-700": "pmdg-aircraft-737",
        "pmdg 737-800": "pmdg-aircraft-738",
        "pmdg 737-900": "pmdg-aircraft-739",
        "pmdg 777-300er": "pmdg-aircraft-77w",
        "pmdg 777f": "pmdg-aircraft-77f",
        "pmdg 777-200er": "pmdg-aircraft-77er",
        "pmdg 777-200lr": "pmdg-aircraft-77l",
    }
    for item in addon_items:
        if not isinstance(item, dict):
            continue
        addon_obj = _addon_from_dict(item)
        name = str(item.get("name", "")).strip().lower()
        package = str(item.get("package_name", "")).strip().lower()
        target = str(item.get("target_path", "")).strip().lower().replace("\\", "/")
        expected_package = expected_packages.get(name)
        if (
            str(item.get("simulator", "")).strip() == "MSFS 2024"
            and package == "inibuilds-aircraft-a340"
            and ("a340-600" in name or "a346" in name)
        ):
            item["name"] = "iniBuilds A340-300"
            item["description"] = "iniBuilds A340 family"
            item["navdata_subpath"] = r"work\NavigationData"
            migrated = True
        if expected_package and package != expected_package:
            item["package_name"] = expected_package
            migrated = True
        if (
            package == "ifly-aircraft-737max8"
            and str(item.get("simulator", "")).strip() == "MSFS 2024"
            and str(item.get("navdata_subpath", "")).strip().lower().replace("/", "\\") != r"work\navdata\permanent"
        ):
            item["navdata_subpath"] = r"work\navdata\Permanent"
            migrated = True
        if (package == "justflight-aircraft-rj" or "rj professional" in name) and "aerosoft-crj" in target:
            item["target_path"] = ""
            migrated = True
        if is_ifly_737max8_addon(addon_obj):
            if "pmdg-aircraft-73" in target or "pmdg 737" in target:
                item["target_path"] = ""
                migrated = True
    deduped_addons: list[dict] = []
    seen_addon_keys: set[tuple[str, str, str]] = set()
    for item in addon_items:
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("name", "")).strip(),
            str(item.get("simulator", "")).strip(),
            str(item.get("platform", "")).strip(),
        )
        if key in seen_addon_keys:
            migrated = True
            continue
        seen_addon_keys.add(key)
        deduped_addons.append(item)
    addon_items = deduped_addons
    if migrated:
        state["addons"] = addon_items
        save_state(state)
    addons_all = [a for a in (to_addon(item) for item in addon_items) if a is not None]
    default_catalog_signatures: set[tuple[str, str, str, str]] = {
        (
            str(item.get("name", "")).strip(),
            str(item.get("simulator", "")).strip(),
            str(item.get("platform", "")).strip(),
            str(item.get("package_name", "")).strip().lower(),
        )
        for item in default_addons()
        if isinstance(item, dict)
    }
    colors = get_colors(theme_name)

    from state import PORTABLE_MODE
    portable_suffix = " | 便携模式 / Portable" if PORTABLE_MODE else ""
    page.title = f"FMS UPDATE MANAGER  | 本软件正在测试中，有问题请联系 qq=168329908 | 当前版本 {format_version_display(APP_VERSION)}{portable_suffix}"
    page.theme_mode = ft.ThemeMode.DARK if theme_name == THEME_DARK else ft.ThemeMode.LIGHT
    page.bgcolor = colors["root_bg"]
    page.padding = 12
    try:
        page.window.width = 1400
        page.window.height = 750
        page.window.min_width = 1100
        page.window.min_height = 700
    except Exception:
        setattr(page, "window_width", 1400)
        setattr(page, "window_height", 750)
        setattr(page, "window_min_width", 1100)
        setattr(page, "window_min_height", 700)
    try:
        if TASKBAR_ICON_FILE.exists():
            page.window.icon = str(TASKBAR_ICON_FILE)
    except Exception:
        pass

    airac_id_text = ft.Text("----", size=fs(34), weight=ft.FontWeight.BOLD, color=colors["cycle_big"])
    airac_effective_text = ft.Text(_("本期数据生效日期：--"), size=fs(12), color=colors["text_sub"])
    airac_next_text = ft.Text(_("本期数据将于--月--日到期"), size=fs(12), color=colors["text_sub"])

    left_list = ft.ListView(expand=True, spacing=6)
    right_cards_list = ft.Column(expand=True, spacing=10)
    log_list = ft.ListView(height=52, spacing=2, auto_scroll=True)
    log_overlay_list = ft.ListView(expand=True, spacing=6, auto_scroll=True)
    log_overlay_title = ft.Text(_("活动日志"), size=fs(24), weight=ft.FontWeight.BOLD, color=colors["text_title"])
    log_overlay_container = ft.Container(visible=False)
    custom_modal_title = ft.Text("", size=fs(22), weight=ft.FontWeight.BOLD, color=colors["text_title"])
    custom_modal_body = ft.Column(tight=True, spacing=10, scroll=ft.ScrollMode.AUTO)
    custom_modal_panel = ft.Container()
    custom_modal_container = ft.Container(visible=False)
    install_overlay_lines: list[str] = []
    install_overlay_list = ft.ListView(expand=True, spacing=6, auto_scroll=True)
    install_overlay_scroll_pending = False
    install_overlay_last_update_ts = 0.0
    install_overlay_update_interval = 0.25
    install_overlay_title_text = _("安装状态")
    install_overlay_title = ft.Text(install_overlay_title_text, size=fs(24), weight=ft.FontWeight.BOLD, color=colors["text_title"])
    install_overlay_container = ft.Container(visible=False)
    install_progress_bar = ft.ProgressBar(value=0.0, bar_height=6, color="#1a73e8")
    install_progress_label = ft.Text("", size=fs(12), color=colors["text_sub"])
    install_progress_row = ft.Container(visible=False, content=ft.Column(spacing=4, controls=[install_progress_label, install_progress_bar]))
    install_progress_last_update_ts = 0.0
    _install_progress_re = re.compile(r"^\s*(\d{1,3})%(?:\s+(.*))?$")
    pending_force_install_action: Callable[[], None] | None = None
    pending_force_install_cancel: Callable[[], None] | None = None
    install_force_button: ft.Button | None = None
    scroll_top_button = ft.Container(visible=True)
    zip_update_picker: ft.FilePicker | None = None
    op_dialog: ft.AlertDialog | None = None
    op_dialog_suppressed = False
    op_dialog_title = ft.Text("", size=fs(18), weight=ft.FontWeight.BOLD)
    op_dialog_status = ft.Text("", size=fs(13), selectable=True)
    op_dialog_detail = ft.Text("", size=fs(12), color=colors["text_sub"], selectable=True)
    op_overlay_container = ft.Container(visible=False)
    op_hide_button = ft.TextButton(_("返回"))
    backup_power_login_valid = False
    one_click_install_filter_button: ft.Button | None = None
    backup_power_login_button: ft.Button | None = None
    cycle_picker_container: ft.Container | None = None
    cycle_picker_label: ft.Text | None = None
    cycle_picker_latest_badge: ft.Container | None = None
    cycle_picker_button: ft.PopupMenuButton | None = None
    cycle_dropdown_options_cache: list[str] = []
    cycle_dropdown_value: str = ""
    startup_update_check_skip = False
    startup_update_release_url = ""
    startup_update_overlay_container = ft.Container(visible=False)
    startup_update_title = ft.Text(_("启动检查更新"), size=fs(22), weight=ft.FontWeight.BOLD, color=colors["text_title"])
    startup_update_status = ft.Text(_("准备检查 GitHub Releases..."), size=fs(14), color=colors["text_sub"])
    startup_update_detail = ft.Text("", size=fs(12), color=colors["text_meta"], selectable=True)
    startup_update_countdown = ft.Text("", size=fs(12), color=colors["text_meta"])
    startup_update_skip_btn: ft.Button | None = None
    startup_update_download_btn: ft.Button | None = None
    startup_update_continue_btn: ft.Button | None = None


    active_sims = enabled_simulators(state)
    if simulator not in active_sims:
        simulator = active_sims[0]
    if platform not in PLATFORMS:
        platform = PLATFORMS[0]
    if theme_name not in (THEME_LIGHT, THEME_DARK):
        theme_name = THEME_LIGHT

    def ensure_initial_locale() -> bool:
        if not locale_first_run:
            return True

        from i18n import available_locales as _avail
        lang_labels = {"zh": "简体中文", "en": "English"}
        selected = {"code": str(state.get("locale") or "zh")}

        def make_pick(code: str):
            def _pick(_e) -> None:
                selected["code"] = code
                _set_locale(code)
                state["locale"] = code
                save_state(state)
                page.clean()
                main(page, fast_reload=True, cached_cycle=cached_cycle)
            return _pick

        buttons: list[ft.Control] = []
        for code in _avail():
            label = lang_labels.get(code, code)
            buttons.append(
                ft.Button(
                    label,
                    on_click=make_pick(code),
                    width=240,
                    bgcolor="#1a73e8" if code == selected["code"] else None,
                    color="#ffffff" if code == selected["code"] else None,
                )
            )

        page.clean()
        page.add(
            ft.Container(
                expand=True,
                alignment=ft.Alignment(0, 0),
                content=ft.Container(
                    width=520,
                    border_radius=18,
                    bgcolor=colors["panel_bg"],
                    padding=28,
                    content=ft.Column(
                        tight=True,
                        spacing=18,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text("选择语言 / Select Language", size=fs(22), weight=ft.FontWeight.BOLD, color=colors["text_title"]),
                            ft.Text("该选项可稍后在“设置”中修改。\nYou can change this later in Settings.", size=fs(12), color=colors["text_sub"]),
                            ft.Column(spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER, controls=buttons),
                        ],
                    ),
                ),
            )
        )
        return False

    if not ensure_initial_locale():
        return

    def ensure_required_community_paths() -> bool:
        key20 = community_key("MSFS 2020", platform)
        key24 = community_key("MSFS 2024", platform)
        key24_extra = platform
        cur20 = str(state.get("community_paths", {}).get(key20, "")).strip()
        cur24 = str(state.get("community_paths", {}).get(key24, "")).strip()
        cur24_extra = str(state.get("community_2024_paths", {}).get(key24_extra, "")).strip()
        has20 = bool(state.get("enabled_simulators", {}).get("MSFS 2020", True))
        has24 = bool(state.get("enabled_simulators", {}).get("MSFS 2024", True))

        ready20 = (not has20) or is_valid_community_path(cur20)
        ready24 = (not has24) or (is_valid_community_path(cur24) and is_valid_community2024_path(cur24_extra))
        if state.get("community_setup_done", False) and (has20 or has24) and ready20 and ready24:
            return True

        has20_check = ft.Checkbox(label=_("我有 MSFS 2020"), value=has20)
        has24_check = ft.Checkbox(label=_("我有 MSFS 2024"), value=has24)
        fs20_field = ft.TextField(
            label="FS20 Community",
            value=cur20 or default_community_base("MSFS 2020", platform),
            expand=True,
        )
        fs24_field = ft.TextField(
            label="FS24 Community",
            value=cur24 or default_community_base("MSFS 2024", platform),
            expand=True,
        )
        fs24_extra_field = ft.TextField(
            label="FS24 Community2024",
            value=cur24_extra,
            hint_text=r"例如 ...\Packages\Community2024",
            expand=True,
        )
        setup_error_text = ft.Text("", size=fs(12), color="#b83d4b")
        browse20_btn = ft.Button(_("浏览"))
        browse24_btn = ft.Button(_("浏览"))
        browse24_extra_btn = ft.Button(_("浏览"))

        for ctrl in list(page.services):
            if isinstance(ctrl, ft.FilePicker) and getattr(ctrl, "data", None) in {"community_picker_20", "community_picker_24", "community_picker_24_extra"}:
                try:
                    page.services.remove(ctrl)
                except ValueError:
                    pass
        picker20 = ft.FilePicker()
        picker20.data = "community_picker_20"
        picker24 = ft.FilePicker()
        picker24.data = "community_picker_24"
        picker24_extra = ft.FilePicker()
        picker24_extra.data = "community_picker_24_extra"
        page.services.extend([picker20, picker24, picker24_extra])

        def browse_fs20(_e) -> None:
            async def runner() -> None:
                try:
                    path = await picker20.get_directory_path(dialog_title=_("选择 FS20 Community"))
                    if path:
                        fs20_field.value = path
                        page.update()
                except Exception as exc:
                    setup_error_text.value = _("选择目录失败: {exc}", exc=exc)
                    page.update()

            page.run_task(runner)

        def browse_fs24(_e) -> None:
            async def runner() -> None:
                try:
                    path = await picker24.get_directory_path(dialog_title=_("选择 FS24 Community"))
                    if path:
                        fs24_field.value = path
                        page.update()
                except Exception as exc:
                    setup_error_text.value = _("选择目录失败: {exc}", exc=exc)
                    page.update()

            page.run_task(runner)

        def browse_fs24_extra(_e) -> None:
            async def runner() -> None:
                try:
                    path = await picker24_extra.get_directory_path(dialog_title=_("选择 FS24 Community2024"))
                    if path:
                        fs24_extra_field.value = path
                        page.update()
                except Exception as exc:
                    setup_error_text.value = _("选择目录失败: {exc}", exc=exc)
                    page.update()

            page.run_task(runner)

        browse20_btn.on_click = browse_fs20
        browse24_btn.on_click = browse_fs24
        browse24_extra_btn.on_click = browse_fs24_extra

        def refresh_setup_field_status() -> None:
            fs20_field.disabled = not bool(has20_check.value)
            browse20_btn.disabled = not bool(has20_check.value)
            fs24_field.disabled = not bool(has24_check.value)
            browse24_btn.disabled = not bool(has24_check.value)
            fs24_extra_field.disabled = not bool(has24_check.value)
            browse24_extra_btn.disabled = not bool(has24_check.value)
            page.update()

        def on_sim_check_change(_e) -> None:
            refresh_setup_field_status()

        has20_check.on_change = on_sim_check_change
        has24_check.on_change = on_sim_check_change

        def save_community_paths(_e) -> None:
            p20 = fs20_field.value.strip()
            p24 = fs24_field.value.strip()
            p24_extra = fs24_extra_field.value.strip()
            has20_selected = bool(has20_check.value)
            has24_selected = bool(has24_check.value)
            if not has20_selected and not has24_selected:
                setup_error_text.value = _("至少需要选择一个模拟器（MSFS 2020 或 MSFS 2024）。")
                page.update()
                return
            if has20_selected and not is_valid_community_path(p20):
                setup_error_text.value = _("MSFS 2020 已启用，请填写有效的 FS20 Community 路径（目录名需为 Community）。")
                page.update()
                return
            if has24_selected and not is_valid_community_path(p24):
                setup_error_text.value = _("MSFS 2024 已启用，请填写有效的 FS24 Community 路径（目录名需为 Community）。")
                page.update()
                return
            if has24_selected and not is_valid_community2024_path(p24_extra):
                setup_error_text.value = _("MSFS 2024 已启用，请填写有效的 FS24 Community2024 路径（目录名需为 Community2024 或 Community）。")
                page.update()
                return
            setup_error_text.value = ""
            state.setdefault("community_paths", {})[key20] = p20
            state.setdefault("community_paths", {})[key24] = p24
            state.setdefault("community_2024_paths", {})[key24_extra] = p24_extra
            state.setdefault("enabled_simulators", {})["MSFS 2020"] = has20_selected
            state.setdefault("enabled_simulators", {})["MSFS 2024"] = has24_selected
            current_sim = str(state.get("simulator", simulator))
            enabled_now = enabled_simulators(state)
            state["simulator"] = current_sim if current_sim in enabled_now else enabled_now[0]
            state["community_setup_done"] = True
            save_state(state)
            page.clean()
            main(page, fast_reload=True, cached_cycle=cached_cycle)

        page.clean()
        page.add(
            ft.Container(
                expand=True,
                alignment=ft.Alignment(0, 0),
                content=ft.Container(
                    width=760,
                    border_radius=18,
                    bgcolor=colors["panel_bg"],
                    padding=24,
                    content=ft.Column(
                        tight=True,
                        spacing=16,
                        controls=[
                            ft.Text(_("首次设置 Community 路径"), size=fs(26), weight=ft.FontWeight.BOLD, color=colors["text_title"]),
                            ft.Text(
                                _("当前平台: {platform}\n请先选择你拥有的模拟器，再填写对应路径。", platform=platform),
                                size=fs(13),
                                color=colors["text_sub"],
                            ),
                            ft.Row(spacing=16, controls=[has20_check, has24_check]),
                            ft.Row(
                                spacing=10,
                                controls=[
                                    fs20_field,
                                    browse20_btn,
                                ],
                            ),
                            ft.Row(
                                spacing=10,
                                controls=[
                                    fs24_field,
                                    browse24_btn,
                                ],
                            ),
                            ft.Row(
                                spacing=10,
                                controls=[
                                    fs24_extra_field,
                                    browse24_extra_btn,
                                ],
                            ),
                            ft.Text(
                                _("要求：目录必须真实存在；FS20/FS24 路径末级需为 Community，FS24 Community2024 路径末级需为 Community2024 或 Community。"),
                                size=fs(12),
                                color=colors["text_meta"],
                            ),
                            setup_error_text,
                            ft.Row(
                                alignment=ft.MainAxisAlignment.END,
                                controls=[
                                    ft.Button(
                                        _("保存并继续"),
                                        on_click=save_community_paths,
                                        bgcolor="#1a73e8",
                                        color="#ffffff",
                                    )
                                ],
                            ),
                        ],
                    ),
                ),
            )
        )
        refresh_setup_field_status()
        return False

    if not ensure_required_community_paths():
        return

    sim_buttons: dict[str, ft.Button] = {}
    platform_buttons: dict[str, ft.Button] = {}
    theme_buttons: dict[str, ft.Button] = {}

    filter_chips = {
        "All": ft.Button("All"),
        "Installed": ft.Button("Installed"),
        "Update Available": ft.Button("Update Available"),
        "Not Installed": ft.Button("Not Installed"),
    }

    def build_top_action_button(text: str, on_click, icon=None, bgcolor=None, color=None) -> ft.Button:
        return ft.Button(
            text,
            icon=icon,
            on_click=on_click,
            bgcolor=bgcolor if bgcolor is not None else colors["panel_bg"],
            color=color if color is not None else colors["text_meta"],
            height=30,
            style=ft.ButtonStyle(
                padding=ft.Padding.symmetric(horizontal=10, vertical=0),
                shape=ft.RoundedRectangleBorder(radius=14),
            ),
        )

    def build_segment_button(text: str, on_click) -> ft.Button:
        return ft.Button(
            text.upper(),
            height=24,
            color=colors["switch_unsel_fg"],
            bgcolor=colors["switch_unsel_bg"],
            style=ft.ButtonStyle(
                padding=ft.Padding.symmetric(horizontal=10, vertical=0),
                shape=ft.RoundedRectangleBorder(radius=12),
            ),
            on_click=lambda _e: on_click(),
        )

    sim_segment_row = ft.Row(spacing=4)
    for option in active_sims:
        sim_buttons[option] = build_segment_button(option, lambda v=option: set_sim(v))
        sim_segment_row.controls.append(sim_buttons[option])

    platform_segment_row = ft.Row(spacing=4)
    for option in PLATFORMS:
        platform_buttons[option] = build_segment_button(option, lambda v=option: set_platform(v))
        platform_segment_row.controls.append(platform_buttons[option])

    theme_segment_row = ft.Row(spacing=4)
    theme_labels = {THEME_LIGHT: _("白色"), THEME_DARK: _("黑色")}
    for option in (THEME_LIGHT, THEME_DARK):
        theme_buttons[option] = build_segment_button(theme_labels[option], lambda v=option: set_theme(v))
        theme_segment_row.controls.append(theme_buttons[option])

    page_session_destroyed = False

    def safe_page_update(*controls: ft.Control) -> bool:
        nonlocal page_session_destroyed
        if page_session_destroyed:
            return False
        try:
            if controls:
                page.update(*controls)
            else:
                page.update()
            return True
        except RuntimeError as exc:
            if is_destroyed_session_error(exc):
                page_session_destroyed = True
                return False
            raise
        except Exception:
            return False

    def try_control_update(control: ft.Control | None) -> bool:
        if control is None:
            return False
        try:
            control.update()
            return True
        except RuntimeError as exc:
            if is_destroyed_session_error(exc):
                return False
            return False
        except Exception:
            return False

    def update_controls(*controls: ft.Control | None) -> None:
        active_controls = [control for control in controls if control is not None]
        if active_controls and safe_page_update(*active_controls):
            return
        safe_page_update()

    def set_button_busy(button: ft.Button | None, busy: bool, busy_text: str | None = None) -> None:
        if button is None:
            return
        try:
            if busy:
                setattr(button, "_busy_active", True)
                if not hasattr(button, "_busy_original_content"):
                    setattr(button, "_busy_original_content", button.content)
                if busy_text is not None:
                    button.content = busy_text
            else:
                setattr(button, "_busy_active", False)
                if hasattr(button, "_busy_original_content"):
                    button.content = cast(Any, getattr(button, "_busy_original_content"))
            update_controls(button)
        except RuntimeError as exc:
            if "Frozen controls cannot be updated" in str(exc):
                log("Skipped busy-state update for frozen button control.")
                return
            raise

    def log(msg: str) -> None:
        line = f"[{human_time()}] {msg}"
        sev = _log_severity(line)
        pal = LOG_SEVERITY_PALETTE[sev]
        log_list.controls.append(ft.Text(line, size=fs(11), color=pal["fg"]))
        if len(log_list.controls) > 300:
            log_list.controls = log_list.controls[-300:]
        append_log_file(f"[{human_datetime()}] {msg}")
        if log_overlay_container.visible:
            refresh_log_overlay()
            update_controls(log_overlay_container)
            return
        update_controls(log_list)

    def try_page_open(control: ft.Control) -> bool:
        open_fn = getattr(page, "open", None)
        if callable(open_fn):
            try:
                open_fn(control)
                if getattr(control, "open", False):
                    return True
            except Exception:
                pass
        try:
            if "dialog" in dir(page):
                setattr(page, "dialog", control)
                setattr(control, "open", True)
                return safe_page_update()
        except Exception:
            pass
        try:
            overlay = getattr(page, "overlay", None)
            if overlay is not None:
                if control not in overlay:
                    overlay.append(control)
                setattr(control, "open", True)
                return safe_page_update()
        except Exception:
            pass
        return False

    def try_page_close(control: ft.Control) -> bool:
        close_fn = getattr(page, "close", None)
        if callable(close_fn):
            try:
                close_fn(control)
                if not getattr(control, "open", False):
                    return True
            except Exception:
                pass
        try:
            if "dialog" in dir(page):
                current_dialog = getattr(page, "dialog", None)
                if current_dialog is control:
                    setattr(control, "open", False)
                    try:
                        setattr(page, "dialog", None)
                    except Exception:
                        pass
                    return safe_page_update()
        except Exception:
            pass
        try:
            overlay = getattr(page, "overlay", None)
            if overlay is not None:
                if control in overlay:
                    overlay.remove(control)
                else:
                    setattr(control, "open", False)
                return safe_page_update()
        except Exception:
            pass
        try:
            setattr(control, "open", False)
            return safe_page_update()
        except Exception:
            pass
        return False

    def dismiss_dialog(dialog: ft.Control | None) -> None:
        if dialog is None:
            return
        if try_page_close(dialog):
            return
        try:
            if getattr(page, "dialog", None) is dialog:
                setattr(page, "dialog", None)
        except Exception:
            pass
        try:
            overlay = getattr(page, "overlay", None)
            if overlay is not None and dialog in overlay:
                overlay.remove(dialog)
        except Exception:
            pass
        try:
            setattr(dialog, "open", False)
        except Exception:
            pass
        update_controls(dialog)

    def close_custom_modal(_e=None) -> None:
        custom_modal_container.visible = False
        custom_modal_title.value = ""
        custom_modal_body.controls = []
        update_controls(custom_modal_container)

    def open_custom_modal(title: str, controls: list[ft.Control], *, width: int = 820, body_height: int | None = None) -> None:
        custom_modal_title.value = title
        custom_modal_body.controls = controls
        custom_modal_body.height = body_height
        custom_modal_panel.width = width
        custom_modal_container.visible = True
        update_controls(custom_modal_container)

    def snack(msg: str) -> None:
        log(msg)
        try:
            if not try_page_open(ft.SnackBar(ft.Text(msg), duration=1800)):
                raise AttributeError("page.open unavailable")
        except Exception:
            snack_bar = ft.SnackBar(ft.Text(msg), duration=1800)
            setattr(page, "snack_bar", snack_bar)
            setattr(snack_bar, "open", True)
            safe_page_update()

    def expand_window_for_update_notice() -> None:
        try:
            page.window.width = max(1360, int(getattr(page.window, "width", 1260) or 1260))
            page.window.height = max(780, int(getattr(page.window, "height", 700) or 700))
            page.window.min_width = max(1200, int(getattr(page.window, "min_width", 1100) or 1100))
            page.window.min_height = max(740, int(getattr(page.window, "min_height", 700) or 700))
        except Exception:
            setattr(page, "window_width", 1360)
            setattr(page, "window_height", 780)
            setattr(page, "window_min_width", 1200)
            setattr(page, "window_min_height", 740)
        safe_page_update()

    def close_startup_update_overlay() -> None:
        startup_update_overlay_container.visible = False
        update_controls(startup_update_overlay_container)

    def set_startup_update_overlay(
        status_text: str,
        detail_text: str = "",
        *,
        countdown_text: str = "",
        show_skip: bool = False,
        show_download: bool = False,
        show_continue: bool = False,
    ) -> None:
        startup_update_status.value = status_text
        startup_update_detail.value = detail_text
        startup_update_countdown.value = countdown_text
        if startup_update_skip_btn is not None:
            startup_update_skip_btn.visible = show_skip
            startup_update_skip_btn.disabled = False
        if startup_update_download_btn is not None:
            startup_update_download_btn.visible = show_download
            startup_update_download_btn.disabled = not bool(startup_update_release_url)
        if startup_update_continue_btn is not None:
            startup_update_continue_btn.visible = show_continue
            startup_update_continue_btn.disabled = False
        startup_update_overlay_container.visible = True
        update_controls(startup_update_overlay_container)

    def on_startup_update_skip(_e=None) -> None:
        nonlocal startup_update_check_skip
        startup_update_check_skip = True
        close_startup_update_overlay()
        log(_("启动更新检查: 用户点击跳过。"))

    def on_startup_update_download(_e=None) -> None:
        nonlocal startup_update_check_skip
        if startup_update_release_url:
            open_external_url(startup_update_release_url)
        startup_update_check_skip = True
        close_startup_update_overlay()
        log(_("启动更新检查: 打开发布页 {startup_update_release_url}", startup_update_release_url=startup_update_release_url))

    def on_startup_update_continue(_e=None) -> None:
        nonlocal startup_update_check_skip
        startup_update_check_skip = True
        close_startup_update_overlay()
        log(_("启动更新检查: 用户继续进入主界面。"))

    async def run_startup_update_check() -> None:
        nonlocal startup_update_check_skip, startup_update_release_url
        startup_update_check_skip = False
        repo = normalize_github_repo(GITHUB_RELEASE_REPO)
        startup_update_release_url = f"https://github.com/{repo}/releases/latest"
        set_startup_update_overlay(
            _("正在检查更新..."),
            _("正在访问 GitHub Releases: {repo}", repo=repo),
            show_skip=False,
            show_download=False,
            show_continue=False,
        )

        check_task = asyncio.create_task(asyncio.to_thread(fetch_latest_github_release, repo))
        while not check_task.done():
            await asyncio.sleep(0.12)

        try:
            release = check_task.result()
        except Exception as exc:
            log(_("GitHub 更新检查失败: {exc}", exc=exc))
            expand_window_for_update_notice()
            failure_message = _("与 GitHub 通信失败，已允许继续使用。")
            for remain in range(3, 0, -1):
                set_startup_update_overlay(
                    _("更新检查失败"),
                    failure_message,
                    countdown_text=_("{remain} 秒后自动进入主界面", remain=remain),
                    show_skip=False,
                    show_download=False,
                    show_continue=False,
                )
                await asyncio.sleep(1)
            close_startup_update_overlay()
            return

        latest_tag = str(release.get("tag_name", "")).strip()
        latest_name = str(release.get("name", "")).strip()
        startup_update_release_url = str(release.get("html_url", "")).strip() or startup_update_release_url
        current_version_label = format_version_display(APP_VERSION)
        latest_version_label = format_version_display(latest_tag or latest_name)
        newest = _is_newer_version(latest_tag or latest_name, APP_VERSION)

        if newest:
            from state import PORTABLE_MODE as _PORTABLE
            has_manifest = False
            try:
                for asset in release.get("assets", []) or []:
                    aname = str(asset.get("name", "")).strip().lower()
                    if aname == "manifest.json":
                        has_manifest = True
                        break
            except Exception:
                has_manifest = False

            if _PORTABLE and has_manifest:
                await _incremental_update_flow(
                    release=release,
                    current=current_version_label,
                    latest=latest_version_label,
                    release_url=startup_update_release_url,
                )
                return

            msi_url = ""
            try:
                for asset in release.get("assets", []) or []:
                    name = str(asset.get("name", "")).strip().lower()
                    if name.endswith(".msi"):
                        msi_url = str(asset.get("browser_download_url", "")).strip()
                        if msi_url:
                            break
            except Exception:
                msi_url = ""

            await _force_update_flow(
                current=current_version_label,
                latest=latest_version_label,
                release_url=startup_update_release_url,
                msi_url=msi_url,
            )
            return

        set_startup_update_overlay(
            _("已是最新版本。"),
            _("当前版本: {current_version_label}", current_version_label=current_version_label),
            countdown_text=_("即将进入主界面..."),
            show_skip=False,
            show_download=False,
            show_continue=False,
        )
        await asyncio.sleep(0.8)
        close_startup_update_overlay()

    async def _incremental_update_flow(release: dict, current: str, latest: str, release_url: str) -> None:
        from incremental_update import (
            IncrementalUpdateError,
            prepare_incremental_update,
            spawn_updater,
        )
        from state import PORTABLE_ROOT
        expand_window_for_update_notice()
        install_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else (PORTABLE_ROOT or Path.cwd())

        progress_state = {"phase": "manifest", "done": 0, "total": None}

        def render_progress() -> None:
            phase = progress_state["phase"]
            done = progress_state["done"]
            total = progress_state["total"]
            if phase == "manifest":
                line = _("校验更新清单...")
            elif phase == "download":
                if total:
                    pct = int(done * 100 / max(total, 1))
                    line = _("下载更新包: {pct}% ({done_mb:.1f}/{total_mb:.1f} MB)", pct=pct, done_mb=done / 1048576, total_mb=total / 1048576)
                else:
                    line = _("下载更新包: {done_mb:.1f} MB", done_mb=done / 1048576)
            elif phase == "extract":
                line = _("应用变更: {done}/{total}", done=done, total=total or "?")
            else:
                line = phase
            set_startup_update_overlay(
                _("正在增量更新到 {latest}", latest=latest),
                line,
                show_skip=False,
                show_download=False,
                show_continue=False,
            )

        def on_progress(phase: str, done: int, total: int | None) -> None:
            progress_state["phase"] = phase
            progress_state["done"] = done
            progress_state["total"] = total
            try:
                page.run_task(_progress_render_task)
            except Exception:
                pass

        async def _progress_render_task() -> None:
            render_progress()

        render_progress()

        def _do_prepare() -> tuple[Path, Path]:
            return prepare_incremental_update(release, install_dir, on_progress=on_progress)

        try:
            staging, updater_exe = await asyncio.to_thread(_do_prepare)
        except IncrementalUpdateError as exc:
            log(_("增量更新失败：{exc}，回退到 MSI 流程", exc=exc))
            msi_url = ""
            for asset in release.get("assets", []) or []:
                name = str(asset.get("name", "")).strip().lower()
                if name.endswith(".msi"):
                    msi_url = str(asset.get("browser_download_url", "")).strip()
                    if msi_url:
                        break
            await _force_update_flow(current=current, latest=latest, release_url=release_url, msi_url=msi_url)
            return
        except Exception as exc:
            log(_("增量更新异常：{exc}", exc=exc))
            set_startup_update_overlay(
                _("增量更新失败"),
                _("错误: {exc}\n将回退到完整安装包流程。", exc=exc),
                show_skip=False,
                show_download=False,
                show_continue=False,
            )
            await asyncio.sleep(2)
            msi_url = ""
            for asset in release.get("assets", []) or []:
                name = str(asset.get("name", "")).strip().lower()
                if name.endswith(".msi"):
                    msi_url = str(asset.get("browser_download_url", "")).strip()
                    if msi_url:
                        break
            await _force_update_flow(current=current, latest=latest, release_url=release_url, msi_url=msi_url)
            return

        set_startup_update_overlay(
            _("更新已就绪，正在重启..."),
            _("应用程序将自动重启完成更新。"),
            show_skip=False,
            show_download=False,
            show_continue=False,
        )
        await asyncio.sleep(1)
        try:
            spawn_updater(updater_exe, install_dir, staging)
        except Exception as exc:
            log(_("启动 updater 失败：{exc}", exc=exc))
            return
        # Exit current process so updater can replace files.
        try:
            page.window.close()
        except Exception:
            pass
        os._exit(0)

    async def _force_update_flow(current: str, latest: str, release_url: str, msi_url: str) -> None:
        expand_window_for_update_notice()
        detail = (
            f"当前版本: {current}\n"
            f"最新版本: {latest}\n"
            "为保证导航数据正确加载，必须升级后才能继续使用。\n"
            f"发布页: {release_url}"
        )
        set_startup_update_overlay(
            _("发现新版本，需升级后才能使用。"),
            detail,
            show_skip=False,
            show_download=False,
            show_continue=False,
        )

        if not msi_url:
            log(_("未在 release 中找到 MSI 资产，无法自动升级；用户需手动下载: {release_url}", release_url=release_url))
            set_startup_update_overlay(
                _("未找到自动升级包"),
                detail + _("\n\n未在 Release 中找到 .msi 安装包，请到发布页手动下载安装。"),
                show_skip=False,
                show_download=True,
                show_continue=False,
            )
            while True:
                await asyncio.sleep(1)
            return

        from urllib.request import urlopen as _urlopen, Request as _Request
        from urllib.error import HTTPError as _HTTPError
        try:
            tmp_dir = Path(tempfile.gettempdir()) / "fms-update"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            msi_path = tmp_dir / Path(msi_url).name
            part_path = tmp_dir / (msi_path.name + ".part")
            set_startup_update_overlay(
                _("正在下载更新包..."),
                detail + _("\n\n下载到: {msi_path}", msi_path=msi_path),
                show_skip=False,
                show_download=False,
                show_continue=False,
            )

            def _download():
                resume_from = part_path.stat().st_size if part_path.exists() and part_path.is_file() else 0
                headers = {"User-Agent": "FMS-Update-Manager-Flet", "Accept": "*/*"}
                if resume_from > 0:
                    headers["Range"] = f"bytes={resume_from}-"
                req = _Request(msi_url, headers=headers, method="GET")
                try:
                    resp = _urlopen(req, timeout=120)
                except _HTTPError as exc:
                    if exc.code == 416 and resume_from > 0:
                        part_path.unlink(missing_ok=True)
                        resume_from = 0
                        req = _Request(msi_url, headers={"User-Agent": "FMS-Update-Manager-Flet", "Accept": "*/*"}, method="GET")
                        resp = _urlopen(req, timeout=120)
                    else:
                        raise
                with resp:
                    status_code = int(getattr(resp, "status", 200) or 200)
                    if resume_from > 0 and status_code != 206:
                        part_path.unlink(missing_ok=True)
                        resume_from = 0
                    mode = "ab" if resume_from > 0 else "wb"
                    with open(part_path, mode) as f:
                        while True:
                            chunk = resp.read(64 * 1024)
                            if not chunk:
                                break
                            f.write(chunk)
                if msi_path.exists():
                    msi_path.unlink(missing_ok=True)
                part_path.replace(msi_path)

            await asyncio.to_thread(_download)
        except Exception as exc:
            log(_("下载 MSI 失败: {exc}", exc=exc))
            set_startup_update_overlay(
                _("更新包下载失败"),
                detail + _("\n\n下载异常: {exc}\n请到发布页手动下载安装。", exc=exc),
                show_skip=False,
                show_download=True,
                show_continue=False,
            )
            while True:
                await asyncio.sleep(1)
            return

        set_startup_update_overlay(
            _("正在校验更新包签名..."),
            detail + _("\n\n正在校验 Authenticode 数字签名。"),
            show_skip=False,
            show_download=False,
            show_continue=False,
        )

        def _verify_msi_signature(msi_file: Path) -> tuple[bool, str]:
            """Verify Authenticode signature AND pin to a known-good certificate.

            Pinning is done via the env var FMS_TRUSTED_CERT_THUMBPRINTS (comma-
            separated SHA1 thumbprints, hex, case-insensitive, no spaces).
            If the env var is empty or unset we fall back to the previous
            behavior (signature must merely be Valid). Pinning is what stops
            an attacker who can sign with *any* trusted cert from impersonating
            a release.
            """
            allowed_raw = os.environ.get("FMS_TRUSTED_CERT_THUMBPRINTS", "").strip()
            allowed = {p.strip().upper().replace(":", "").replace(" ", "")
                       for p in allowed_raw.split(",") if p.strip()}
            ps = (
                "$ErrorActionPreference='Stop';"
                f"$s=Get-AuthenticodeSignature -FilePath '{msi_file}';"
                "$tp=$null;"
                "if ($s.SignerCertificate){$tp=$s.SignerCertificate.Thumbprint};"
                "Write-Host (\"STATUS=\" + $s.Status);"
                "Write-Host (\"THUMBPRINT=\" + $tp);"
                "if ($s.Status -eq 'Valid'){exit 0}else{exit 1}"
            )
            try:
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                    capture_output=True, text=True, timeout=30,
                )
            except Exception as exc:
                return False, f"verify exception: {exc}"
            out = (res.stdout or "") + (res.stderr or "")
            status_line = ""
            thumb = ""
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("STATUS="):
                    status_line = line.split("=", 1)[1].strip()
                elif line.startswith("THUMBPRINT="):
                    thumb = line.split("=", 1)[1].strip().upper().replace(":", "").replace(" ", "")
            if res.returncode != 0 or status_line != "Valid":
                return False, f"signature status={status_line or 'unknown'}"
            if allowed:
                if not thumb:
                    return False, "could not read signer thumbprint"
                if thumb not in allowed:
                    return False, f"signer thumbprint not in whitelist: {thumb}"
                return True, f"thumbprint matched: {thumb[:8]}…"
            return True, f"valid (unpinned, thumbprint={thumb[:8] or 'n/a'})"

        ok, msg = await asyncio.to_thread(_verify_msi_signature, msi_path)
        if not ok:
            log(_("MSI 签名校验失败: {msg}", msg=msg))
            set_startup_update_overlay(
                _("更新包签名校验失败"),
                detail + _("\n\n校验信息: {msg}\n为安全起见已停止安装，请到发布页手动下载并核对签名。", msg=msg),
                show_skip=False,
                show_download=True,
                show_continue=False,
            )
            try:
                msi_path.unlink(missing_ok=True)
            except Exception:
                pass
            while True:
                await asyncio.sleep(1)
            return
        log(_("MSI 签名校验通过: {msg}", msg=msg))

        set_startup_update_overlay(
            _("正在启动安装程序..."),
            detail + _("\n\n安装程序已启动，本程序即将退出。"),
            show_skip=False,
            show_download=False,
            show_continue=False,
        )
        try:
            subprocess.Popen(["msiexec", "/i", str(msi_path)], shell=False)
        except Exception as exc:
            log(_("启动 msiexec 失败: {exc}", exc=exc))
            try:
                os.startfile(str(msi_path))
            except Exception as exc2:
                log(_("os.startfile 失败: {exc2}", exc2=exc2))
        await asyncio.sleep(1.5)
        try:
            page.window.close()
        except Exception:
            try:
                os._exit(0)
            except Exception:
                pass
        while True:
            await asyncio.sleep(1)

    def show_operation_dialog(title: str, status: str, detail: str = "") -> None:
        nonlocal op_dialog, op_dialog_suppressed
        op_dialog_title.value = title
        op_dialog_status.value = status
        op_dialog_detail.value = detail or _("请稍候，任务正在执行中。")

        def hide_click(_e=None) -> None:
            nonlocal op_dialog_suppressed
            op_dialog_suppressed = True
            log(_("处理中弹窗: 点击返回"))
            op_overlay_container.visible = False
            update_controls(op_overlay_container)
            snack(_("已返回主界面，任务仍在后台执行。"))

        if op_dialog_suppressed:
            return
        op_hide_button.on_click = hide_click
        op_overlay_container.visible = True
        update_controls(op_overlay_container)

    def update_operation_dialog(status: str, detail: str = "") -> None:
        if op_dialog_suppressed:
            return
        if not op_overlay_container.visible:
            show_operation_dialog(_("处理中"), status, detail)
            return
        op_dialog_status.value = status
        if detail:
            op_dialog_detail.value = detail
        update_controls(op_overlay_container)

    def close_operation_dialog(reset_suppressed: bool = True) -> None:
        nonlocal op_dialog, op_dialog_suppressed
        if reset_suppressed:
            op_dialog_suppressed = False
        op_overlay_container.visible = False
        update_controls(op_overlay_container)

    def reset_operation_dialog_suppression() -> None:
        nonlocal op_dialog_suppressed
        op_dialog_suppressed = False

    def show_info_dialog(title: str, message: str) -> None:
        def close_dialog(_e=None):
            close_custom_modal()

        try:
            if install_overlay_container.visible:
                close_install_overlay()
        except Exception:
            pass
        try:
            close_operation_dialog()
        except Exception:
            pass

        open_custom_modal(
            title,
            [
                ft.Text(message, selectable=True),
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    controls=[ft.Button("OK", bgcolor="#1a73e8", color="#ffffff", on_click=close_dialog)],
                ),
            ],
            width=760,
        )

    def show_confirm_dialog(title: str, message: str, on_yes, on_no=None) -> None:
        dlg: ft.AlertDialog | None = None

        def close_dialog(_e=None) -> None:
            dismiss_dialog(dlg)

        def yes_click(_e) -> None:
            close_dialog()
            try:
                on_yes()
            except Exception as exc:
                snack(_("确认操作失败: {exc}", exc=exc))

        def no_click(_e) -> None:
            close_dialog()
            if on_no is not None:
                try:
                    on_no()
                except Exception:
                    pass

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Text(message, selectable=True),
            actions=[
                ft.TextButton(_("取消"), on_click=no_click),
                ft.TextButton(_("继续"), on_click=yes_click),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        try:
            try:
                if not try_page_open(dlg):
                    raise AttributeError("page.open unavailable")
            except Exception:
                setattr(page, "dialog", dlg)
                setattr(dlg, "open", True)
                page.update()
        except Exception:
            setattr(page, "dialog", dlg)
            setattr(dlg, "open", True)
            page.update()

    def find_addon_by_key(key: str) -> Addon | None:
        for addon in addons_all:
            if addon_key(addon) == key:
                return addon
        return None

    def is_default_catalog_addon(addon: Addon) -> bool:
        signature = (
            addon.name.strip(),
            addon.simulator.strip(),
            addon.platform.strip(),
            addon.package_name.strip().lower(),
        )
        return signature in default_catalog_signatures

    def persist_addon_target_path(addon: Addon, target_dir: Path) -> None:
        addon.target_path = str(target_dir)
        updated = False
        package_name = addon.package_name.strip().lower()
        for item in state.get("addons", []) if isinstance(state.get("addons"), list) else []:
            if not isinstance(item, dict):
                continue
            item_name = str(item.get("name", "")).strip()
            item_sim = str(item.get("simulator", "")).strip()
            item_platform = str(item.get("platform", "")).strip()
            item_package = str(item.get("package_name", "")).strip().lower()
            if (
                item_name == addon.name.strip()
                and item_sim == addon.simulator.strip()
                and item_platform == addon.platform.strip()
                and item_package == package_name
            ):
                item["target_path"] = str(target_dir)
                updated = True
                break
        if updated:
            save_state(state)

    async def prompt_manual_addon_target_path(addon: Addon) -> Path | None:
        loop = asyncio.get_running_loop()
        result_future: asyncio.Future[Path | None] = loop.create_future()
        picker_tag = "manual_addon_target_picker"

        for ctrl in list(page.services):
            if isinstance(ctrl, ft.FilePicker) and getattr(ctrl, "data", None) == picker_tag:
                try:
                    page.services.remove(ctrl)
                except ValueError:
                    pass
        picker = ft.FilePicker()
        picker.data = picker_tag
        page.services.append(picker)

        def finish_result(value: Path | None) -> None:
            if not result_future.done():
                result_future.set_result(value)
            try:
                page.services.remove(picker)
            except ValueError:
                pass

        async def pick_dir_async() -> None:
            try:
                picked_path = await picker.get_directory_path(dialog_title=f"选择 {addon.name} 导航数据目录")
            except Exception as exc:
                snack(_("打开目录选择窗口失败: {exc}", exc=exc))
                finish_result(None)
                return
            if not picked_path:
                finish_result(None)
                return
            target_dir = Path(str(picked_path).strip())
            if not target_dir.exists() or not target_dir.is_dir():
                snack(_("目录不存在或不可用: {target_dir}", target_dir=target_dir))
                finish_result(None)
                return
            persist_addon_target_path(addon, target_dir)
            snack(f"已保存 {addon.name} 的安装目录: {target_dir}")
            finish_result(target_dir)

        def choose_now() -> None:
            page.run_task(pick_dir_async)

        def cancel_choose() -> None:
            finish_result(None)

        show_confirm_dialog(
            _("未检测到安装目录"),
            (
                f"{addon.name} 未检测到可用导航数据目录。\n"
                "请点击“继续”手动选择已安装机模的导航数据目录。"
            ),
            on_yes=choose_now,
            on_no=cancel_choose,
        )
        return await result_future

    def selected_install_cycle_for_addon(addon: Addon, fallback_cycle: str) -> str:
        fallback = detect_airac(fallback_cycle)
        install_cycles = state.get("addon_install_cycles", {})
        if not isinstance(install_cycles, dict):
            return fallback
        chosen_raw = str(install_cycles.get(addon_key(addon), "")).strip()
        chosen_cycle = detect_airac(chosen_raw)
        return chosen_cycle if chosen_cycle not in {"", "UNKNOWN"} else fallback

    def perform_archive_update_install(
        addon: Addon,
        target: Path,
        archive_path: Path,
        archive_name: str,
        archive_airac: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> dict:
        if progress_callback is not None:
            progress_callback(f"开始安装: {addon.name}")
        extracted_root: Path | None = None
        if is_sim_base_navdata_addon(addon):
            try:
                required = sim_base_navdata_required_subfolders(addon)
                if not required:
                    raise ValueError(_("机型未配置必需的导航数据子目录列表"))
                if progress_callback is not None:
                    progress_callback(_("正在解压压缩包..."))
                extracted_root = extract_archive_to_temp(archive_path, progress_callback=progress_callback)
                if progress_callback is not None:
                    progress_callback(_("正在校验压缩包结构..."))
                payload_info = inspect_sim_base_payload(extracted_root, required)
                if not payload_info:
                    raise ValueError(
                        f"压缩包结构无效：顶层未找到必需目录 {', '.join(required)}"
                    )
                payload_dir = Path(str(payload_info.get("payload_dir", "")).strip())
                install_base = target
                if not install_base.exists() or not install_base.is_dir():
                    raise ValueError(_("Community 目录不可用: {install_base}", install_base=install_base))

                backup_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                safe_name = addon.name.replace("/", "_").replace("\\", "_")
                addon_backup_root = BACKUP_DIR / safe_name
                addon_backup_root.mkdir(parents=True, exist_ok=True)
                backup_path = addon_backup_root / backup_stamp
                backed_up = False
                copied_files = 0
                for sub in required:
                    src = payload_dir / sub
                    if not src.exists():
                        for entry in payload_dir.iterdir():
                            if entry.is_dir() and entry.name.lower() == sub.lower():
                                src = entry
                                break
                    if not src.exists() or not src.is_dir():
                        raise ValueError(_("压缩包缺少子目录: {sub}", sub=sub))
                    dest = install_base / sub
                    if dest.exists():
                        if progress_callback is not None:
                            progress_callback(_("备份旧 {sub}...", sub=sub))
                        backup_path.mkdir(parents=True, exist_ok=True)
                        shutil.copytree(dest, backup_path / sub, dirs_exist_ok=True)
                        backed_up = True
                        shutil.rmtree(dest, ignore_errors=True)
                    if progress_callback is not None:
                        progress_callback(_("安装 {sub}...", sub=sub))
                    shutil.copytree(src, dest)
                    copied_files += sum(1 for _ in dest.rglob("*") if _.is_file())

                if progress_callback is not None:
                    progress_callback(f"安装完成: {addon.name}")
                return {
                    "backup_path": str(backup_path) if backed_up else "",
                    "airac": detect_airac(archive_name) or "UNKNOWN",
                    "install_base": str(install_base),
                    "install_root": str(install_base),
                    "extracted_files": copied_files,
                    "archive_name": archive_name,
                    "extracted_root": str(extracted_root) if extracted_root else "",
                }
            except Exception:
                if extracted_root is not None:
                    cleanup_temp_dir(extracted_root)
                raise
        try:
            archive_kind = _archive_kind(archive_path)
            payload_airac = "UNKNOWN"
            payload_prefix = ""
            payload_dir: Path | None = None
            if archive_kind == "zip":
                if progress_callback is not None:
                    progress_callback(_("正在分析 ZIP 安装载荷..."))
                archive_payload = inspect_zip_cycle_payload(archive_path)
                if not archive_payload:
                    raise ValueError(_("压缩包中未找到可用 cycle.json，无法安装"))
                payload_prefix = str(archive_payload.get("payload_prefix", "")).strip()
                payload_airac = detect_airac(str(archive_payload.get("airac", "UNKNOWN")))
            else:
                if progress_callback is not None:
                    progress_callback(_("正在解压压缩包主体文件..."))
                extracted_root = extract_archive_to_temp(archive_path, progress_callback=progress_callback)
                if progress_callback is not None:
                    progress_callback(_("正在定位安装载荷..."))
                archive_payload = inspect_extracted_cycle_payload(extracted_root)
                if not archive_payload:
                    raise ValueError(_("压缩包中未找到可用 cycle.json，无法安装"))
                payload_dir = Path(str(archive_payload.get("payload_dir", "")).strip())
                if not payload_dir.exists() or not payload_dir.is_dir():
                    raise ValueError(_("无效安装载荷目录: {payload_dir}", payload_dir=payload_dir))
                payload_airac = detect_airac(str(archive_payload.get("airac", "UNKNOWN")))

            install_base = target
            if is_a346_addon(addon) and re.fullmatch(r"cycle[_-]?[0-9]{4}", target.name, re.IGNORECASE):
                install_base = target.parent
            if install_base.exists() and not install_base.is_dir():
                raise ValueError(f"Target path is not a folder: {install_base}")

            backup_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            safe_name = addon.name.replace("/", "_").replace("\\", "_")
            backup_path: Path | None = None
            if install_base.exists():
                if progress_callback is not None:
                    progress_callback(_("备份现有导航数据..."))
                addon_backup_root = BACKUP_DIR / safe_name
                addon_backup_root.mkdir(parents=True, exist_ok=True)
                backup_path = addon_backup_root / backup_stamp
                shutil.copytree(install_base, backup_path, dirs_exist_ok=True)

                if progress_callback is not None:
                    progress_callback(_("清理旧文件..."))
                for child in install_base.iterdir():
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink(missing_ok=True)
            else:
                install_base.mkdir(parents=True, exist_ok=True)
                if progress_callback is not None:
                    progress_callback(_("创建安装目录..."))

            effective_airac = archive_airac if archive_airac != "UNKNOWN" else payload_airac
            if progress_callback is not None:
                progress_callback(_("复制新导航数据文件..."))
            if archive_kind == "zip":
                extracted_files, install_root = extract_zip_payload_to_target(
                    addon=addon,
                    zip_path=archive_path,
                    install_base=install_base,
                    payload_prefix=payload_prefix,
                    airac=effective_airac,
                )
            else:
                if payload_dir is None:
                    raise ValueError(_("安装载荷目录无效。"))
                extracted_files, install_root = copy_payload_dir_to_target(
                    addon=addon,
                    payload_dir=payload_dir,
                    install_base=install_base,
                    airac=effective_airac,
                )
            if extracted_files <= 0:
                raise ValueError("No files were extracted from archive payload.")

            airac = effective_airac
            if airac == "UNKNOWN":
                airac = read_cycle_from_dir(install_base)
            (install_base / "airac.txt").write_text(f"AIRAC {airac}\n", encoding="utf-8")
            if progress_callback is not None:
                progress_callback(_("安装完成: AIRAC {airac}", airac=airac))
            return {
                "backup_path": str(backup_path) if backup_path else "",
                "airac": airac,
                "install_base": str(install_base),
                "install_root": str(install_root),
                "extracted_files": extracted_files,
                "archive_name": archive_name,
                "extracted_root": str(extracted_root),
            }
        except Exception:
            if extracted_root is not None:
                cleanup_temp_dir(extracted_root)
            raise

    def start_archive_update(
        addon: Addon,
        target: Path,
        archive_path: Path,
        archive_name: str,
        archive_airac: str,
        *,
        show_result_dialog: bool = True,
        run_in_background: bool = True,
    ) -> asyncio.Task[bool] | None:
        async def runner() -> bool:
            install_temp_root: Path | None = None
            try:
                open_install_overlay(title=f"安装状态 - {addon.name}", reset=False)
                log(f"{addon.name}: begin install from archive '{archive_name}'")
                append_install_overlay_line(f"开始安装机型: {addon.name}")
                append_install_overlay_line(_("来源压缩包: {archive_name}", archive_name=archive_name))
                result = await run_blocking_with_feedback(
                    perform_archive_update_install,
                    addon,
                    target,
                    archive_path,
                    archive_name,
                    archive_airac,
                    message=f"正在更新 {addon.name}",
                    pulse_interval=0.25,
                    progress_callback=append_install_overlay_line,
                    provide_progress_callback=True,
                    show_page_loading=False,
                )
                install_temp_root_raw = str(result.get("extracted_root", "")).strip()
                if install_temp_root_raw:
                    install_temp_root = Path(install_temp_root_raw)
                if result.get("backup_path"):
                    log(f"{addon.name}: backup created at {result['backup_path']}")
                    append_install_overlay_line(f"已备份旧数据: {result['backup_path']}")
                else:
                    log(f"{addon.name}: no existing data, install performed without backup")
                    append_install_overlay_line(_("未检测到旧数据，已执行全新安装"))
                log(
                    f"{addon.name}: updated to AIRAC {result['airac']} "
                    f"({result['extracted_files']} file(s) installed) from {result['archive_name']}"
                )
                archive_cycle_msg = (
                    _("导航数据更新成功，当前安装的 AIRAC 周期: {archive_airac}（来自压缩包 cycle.json）", archive_airac=archive_airac)
                    if archive_airac != "UNKNOWN"
                    else f"导航数据更新成功，但 cycle.json 未提供 AIRAC，当前周期: {result['airac']}"
                )
                is_base_navdata = addon.package_name.strip().lower() in {
                    "navigraph-msfs2020-base",
                    "navigraph-msfs2024-base",
                }
                if is_base_navdata:
                    archive_cycle_msg = _("安装完成")
                append_install_overlay_line(archive_cycle_msg)
                if show_result_dialog:
                    if is_base_navdata:
                        snack(f"{addon.name} 安装完成")
                    else:
                        snack(f"{addon.name} 更新完成: AIRAC {result['airac']}")
                if show_result_dialog:
                    if is_base_navdata:
                        show_info_dialog(
                            _("安装完成"),
                            f"{addon.name} 安装完成。\n安装文件数: {result['extracted_files']}",
                        )
                    else:
                        show_info_dialog(
                            _("更新完成"),
                            (
                                f"{addon.name} 已更新到 AIRAC {result['airac']}。\n"
                                f"安装文件数: {result['extracted_files']}\n"
                                f"来源压缩包: {result['archive_name']}\n"
                                f"{archive_cycle_msg}"
                            ),
                        )
                return True
            except Exception as exc:
                append_install_overlay_line(_("安装失败: {exc}", exc=exc))
                if show_result_dialog:
                    snack(f"{addon.name} 更新失败: {exc}")
                if show_result_dialog:
                    show_info_dialog(_("更新失败"), f"{addon.name} 更新失败。\n\n错误详情：{exc}")
                return False
            finally:
                await asyncio.to_thread(cleanup_backup_power_download_cache, state)
                if install_temp_root is not None:
                    await asyncio.to_thread(cleanup_temp_dir, install_temp_root)
                await rebuild_lists_async(show_loading=False)

        if run_in_background:
            page.run_task(runner)
            return None
        return asyncio.create_task(runner())

    async def on_archive_update_pick_result(
        selected_files,
        addon: Addon,
        target: Path,
        *,
        show_result_dialog: bool = True,
        allow_force_prompt: bool = True,
        wait_for_completion: bool = False,
        reset_overlay: bool = True,
    ) -> bool:
        if selected_files is None:
            log(f"{addon.name}: archive selection canceled")
            return False

        files = selected_files
        if hasattr(selected_files, "files"):
            files = getattr(selected_files, "files")
        if asyncio.iscoroutine(files):
            files = await files
        if not files:
            log(f"{addon.name}: archive selection canceled")
            return False

        selected_file = files[0]
        file_path = getattr(selected_file, "path", None)
        if not file_path:
            snack(_("未获取到压缩包路径"))
            return False
        archive_path = Path(file_path)
        if not archive_path.exists():
            snack(_("压缩包不存在: {archive_path}", archive_path=archive_path))
            return False
        if not is_supported_archive_file(archive_path):
            snack(f"不支持的压缩格式: {archive_path.name}")
            return False

        open_install_overlay(title=f"安装状态 - {addon.name}", reset=reset_overlay)
        append_install_overlay_line(f"已选择压缩包: {archive_path.name}")
        log(f"{addon.name}: selected archive {archive_path.name}")
        if not target.exists():
            log(f"{addon.name}: target does not exist yet, it will be created during install: {target}")
            append_install_overlay_line(_("目标目录不存在，将自动创建: {target}", target=target))
        else:
            append_install_overlay_line(_("目标目录: {target}", target=target))

        try:
            if is_sim_base_navdata_addon(addon):
                append_install_overlay_line(_("机型为 MSFS 导航数据库，跳过 cycle.json 校验"))
                archive_airac = detect_airac(archive_path.name) or "UNKNOWN"
                await rebuild_lists_async(show_loading=False)
                ok_task = start_archive_update(
                    addon,
                    target,
                    archive_path,
                    archive_path.name,
                    archive_airac,
                    show_result_dialog=show_result_dialog,
                    run_in_background=False,
                )
                if ok_task is not None:
                    return await ok_task
                return False
            log(f"{addon.name}: parsing archive payload from {archive_path.name}")
            append_install_overlay_line(_("正在提取 cycle.json 并校验..."))
            archive_payload = await run_blocking_with_feedback(
                prepare_archive_payload,
                archive_path,
                message=_("正在提取并校验 cycle.json"),
                pulse_interval=0.25,
                progress_callback=append_install_overlay_line,
                provide_progress_callback=True,
                show_page_loading=False,
            )
        except Exception as exc:
            append_install_overlay_line(_("cycle 校验失败: {exc}", exc=exc))
            snack(_("cycle 校验失败: {exc}", exc=exc))
            if show_result_dialog:
                show_info_dialog(
                    _("校验失败"),
                    f"{addon.name} cycle.json 校验失败。\n\n压缩包: {archive_path.name}\n错误详情：{exc}",
                )
            await rebuild_lists_async(show_loading=False)
            return False
        if not archive_payload:
            append_install_overlay_line(_("压缩包中未找到可用 cycle.json，无法安装"))
            snack(f"压缩包中未找到可用 cycle.json: {archive_path.name}")
            if show_result_dialog:
                show_info_dialog(
                    _("压缩包无效"),
                    f"{archive_path.name} 中未找到可用 cycle.json，无法继续安装。",
                )
            await rebuild_lists_async(show_loading=False)
            return False
        await rebuild_lists_async(show_loading=False)

        probe_root_raw = str(archive_payload.get("probe_root", "")).strip()
        probe_root = Path(probe_root_raw) if probe_root_raw else None
        payload_prefix = str(archive_payload.get("payload_prefix", "")).strip()
        archive_airac = str(archive_payload.get("airac", "UNKNOWN"))
        cycle_name = str(archive_payload.get("cycle_name", "")).strip()
        log(
            f"{addon.name}: archive parsed, cycle_name='{cycle_name or '<empty>'}', "
            f"airac={archive_airac}, payload_prefix='{payload_prefix or '<root>'}'"
        )
        append_install_overlay_line(
            f"压缩包校验完成: 机型名称 '{cycle_name or _("空")}'，AIRAC {archive_airac}"
        )
        if probe_root is not None:
            await asyncio.to_thread(cleanup_temp_dir, probe_root)

        async def continue_install_async() -> bool:
            log(f"{addon.name}: archive validation passed, installing...")
            append_install_overlay_line(_("压缩包校验通过，开始解压并安装..."))
            clear_force_install_prompt(refresh=False)
            task = start_archive_update(
                addon=addon,
                target=target,
                archive_path=archive_path,
                archive_name=archive_path.name,
                archive_airac=archive_airac,
                show_result_dialog=show_result_dialog,
                run_in_background=not wait_for_completion,
            )
            if wait_for_completion and task is not None:
                return bool(await task)
            return True

        def continue_install() -> None:
            page.run_task(continue_install_async)

        def cancel_install(reason: str) -> None:
            log(f"{addon.name}: update canceled by user ({reason})")
            append_install_overlay_line(_("用户取消安装（{reason}）", reason=reason))

        if is_sim_base_navdata_addon(addon):
            return await continue_install_async()

        cycle_name_norm = cycle_name.strip().lower()
        if not cycle_name_norm:
            if not allow_force_prompt:
                log(f"{addon.name}: cycle.json name empty, skipped in batch mode")
                append_install_overlay_line(_("cycle.json 的 name 为空，批量模式下已跳过"))
                return False
            log(f"{addon.name}: cycle.json name is empty, waiting for user confirmation")
            set_force_install_prompt(
                _("cycle.json 的 name 字段为空，无法校验机型匹配"),
                on_force=continue_install,
                on_cancel=lambda: cancel_install(_("cycle.json name 为空")),
            )
            snack(_("cycle.json 的 name 为空，请点击“强制安装”继续。"))
            return False
        if not cycle_name_matches_addon(addon, cycle_name):
            if not allow_force_prompt:
                log(f"{addon.name}: cycle name mismatch in batch mode (archive='{cycle_name}')")
                append_install_overlay_line(_("机型名称不匹配，批量模式下已跳过: {cycle_name}", cycle_name=cycle_name))
                return False
            log(
                f"{addon.name}: cycle name mismatch detected (archive='{cycle_name}', addon='{addon.name}'), "
                "waiting for user confirmation"
            )
            append_install_overlay_line(
                f"检测到非本机型导航数据（压缩包: {cycle_name}，当前机型: {addon.name}），等待用户确认"
            )
            set_force_install_prompt(
                f"机型名称不匹配（压缩包: {cycle_name}，当前机型: {addon.name}）",
                on_force=continue_install,
                on_cancel=lambda: cancel_install(_("机型名称不匹配: {cycle_name}", cycle_name=cycle_name)),
            )
            snack(_("检测到机型名称不匹配，请点击“强制安装”继续。"))
            return False
        return await continue_install_async()

    async def on_update_navdata_click(
        addon_key_value: str,
        trigger_button: ft.Button | None = None,
        *,
        bulk_mode: bool = False,
        forced_cycle_id: str | None = None,
        show_result_dialog: bool = True,
        reset_overlay: bool = True,
        wait_for_install: bool = False,
        local_only: bool = False,
    ) -> bool:
        try:
            addon = find_addon_by_key(addon_key_value)
            if addon is None:
                snack(_("未找到对应机型。"))
                return False
            if bulk_mode and not is_default_catalog_addon(addon):
                append_install_overlay_line(f"{addon.name}: 跳过（手动添加机型需手动选包）")
                return False
            target = resolve_target_dir(addon, state)
            inferred_from_wasm = False
            if target is None:
                target = resolve_wasm_target_by_folder_name(addon, state)
                inferred_from_wasm = target is not None
                if target is None and not bulk_mode and not is_default_catalog_addon(addon):
                    target = await prompt_manual_addon_target_path(addon)
                    if target is None:
                        snack(_("未选择路径，已取消本次更新。"))
                        return False
                    log(f"{addon.name}: using user-selected target {target}")
                if target is None:
                    message = _("未检测到已安装数据。请先确认 WASM 下存在对应机型文件夹名称。")
                    if bulk_mode:
                        append_install_overlay_line(f"{addon.name}: {message}")
                    else:
                        snack(message)
                    return False
                if inferred_from_wasm:
                    log(f"{addon.name}: no installed navdata found, using WASM inferred target {target}")
            log(f"{addon.name}: update requested, target={target}")
            if target.exists() and not target.is_dir():
                message = _("目标路径不是文件夹: {target}", target=target)
                if bulk_mode:
                    append_install_overlay_line(f"{addon.name}: {message}")
                else:
                    snack(message)
                return False
            if not target.exists() and not target.parent.exists():
                message = f"目标父目录不存在: {target.parent}"
                if bulk_mode:
                    append_install_overlay_line(f"{addon.name}: {message}")
                else:
                    snack(message)
                return False
            token = str(state.get("backup_power_token", "")).strip()
            can_auto_download = False
            if not local_only and token and is_default_catalog_addon(addon):
                can_auto_download = await refresh_backup_power_login_validity(notify_invalid=False)
                if not can_auto_download:
                    log(f"{addon.name}: DATA token invalid, falling back to local archive picker")
                    if bulk_mode:
                        append_install_overlay_line(f"{addon.name}: 跳过（登录失效，批量模式不允许手动选包）")
                        return False
            if can_auto_download and is_default_catalog_addon(addon):
                cycle_id = detect_airac(str(forced_cycle_id or ""))
                if cycle_id in {"", "UNKNOWN"} and current_cycle_info and current_cycle_info.get("cycle_id"):
                    cycle_id = detect_airac(str(current_cycle_info.get("cycle_id", "")))
                if cycle_id in {"", "UNKNOWN"}:
                    cycle_info = await asyncio.to_thread(fetch_current_cycle)
                    if cycle_info and cycle_info.get("cycle_id"):
                        cycle_id = detect_airac(str(cycle_info.get("cycle_id", "")))
                if cycle_id in {"", "UNKNOWN"}:
                    message = _("未获取到有效 AIRAC 期数，无法自动下载。")
                    if bulk_mode:
                        append_install_overlay_line(f"{addon.name}: {message}")
                    else:
                        snack(message)
                    return False
                download_dir = ensure_backup_power_download_dir(str(default_backup_power_download_dir(state)), create=True)
                try:
                    if bulk_mode:
                        if not install_overlay_container.visible:
                            open_install_overlay(title=f"安装状态 - {addon.name}", reset=reset_overlay)
                    else:
                        open_install_overlay(title=f"安装状态 - {addon.name}", reset=reset_overlay)
                    append_install_overlay_line(_("自动模式: 期数 {cycle_id}", cycle_id=cycle_id))
                    saved_token_for_hash = str(state.get("backup_power_token", "")).strip()
                    expected_hash = ""
                    if saved_token_for_hash:
                        try:
                            from openlist import fetch_archive_expected_hash, list_openlist_cycle_msfs_items, select_openlist_archive_for_addon as _select_for_hash
                            items_for_hash = list_openlist_cycle_msfs_items(cycle_id)
                            chosen_for_hash = _select_for_hash(addon, cycle_id, items_for_hash)
                            if chosen_for_hash is not None:
                                guess_name = str(chosen_for_hash.get("name", "")).strip()
                                if guess_name:
                                    expected_hash = fetch_archive_expected_hash(saved_token_for_hash, cycle_id, guess_name)
                        except Exception as exc:
                            log(_("获取预期哈希失败（将跳过校验）: {exc}", exc=exc))
                    result = await run_blocking_with_feedback(
                        download_openlist_archive_for_addon,
                        addon,
                        cycle_id,
                        download_dir,
                        message=f"正在下载 {addon.name}",
                        pulse_interval=0.25,
                        progress_callback=append_install_overlay_line,
                        provide_progress_callback=True,
                        show_page_loading=False,
                        expected_sha256=expected_hash,
                    )
                    archive_path = Path(str(result.get("archive_path", "")).strip())
                    if not archive_path.exists():
                        raise ValueError(_("自动下载后未找到压缩包: {archive_path}", archive_path=archive_path))
                    log(f"{addon.name}: OpenList auto archive selected {archive_path}")
                    append_install_overlay_line(f"已自动下载压缩包: {archive_path.name}")
                    picked = [type("PickedFile", (), {"path": str(archive_path)})()]
                    return await on_archive_update_pick_result(
                        picked,
                        addon,
                        target,
                        show_result_dialog=show_result_dialog,
                        allow_force_prompt=not bulk_mode,
                        wait_for_completion=wait_for_install,
                        reset_overlay=False,
                    )
                except Exception as exc:
                    if bulk_mode:
                        log(f"{addon.name}: OpenList auto download failed in batch mode ({exc})")
                        append_install_overlay_line(f"{addon.name}: 自动下载失败: {exc}")
                        return False
                    log(f"{addon.name}: OpenList auto download failed, fallback to manual picker ({exc})")
                    snack(_("自动下载失败: {exc}", exc=exc))
                    append_install_overlay_line(f"{addon.name}: 自动下载失败 - {exc}")
                    return False
            snack(_("当前未登录或机型不支持自动下载，无法更新。"))
            return False
        finally:
            set_button_busy(trigger_button, False)

    def make_update_click_handler(addon_key_value: str, *, local_only: bool = False):
        def _handler(e) -> None:
            button = e.control if isinstance(getattr(e, "control", None), ft.Button) else None
            if is_button_busy(button):
                snack(_("任务正在处理中，请稍候。"))
                return
            reset_operation_dialog_suppression()
            set_button_busy(button, True, _("处理中..."))
            chosen_cycle = (cycle_dropdown_value or "").strip() if (backup_power_login_valid and not local_only) else ""

            async def _runner():
                try:
                    if chosen_cycle:
                        ok = await confirm_non_latest_cycle(chosen_cycle)
                        if not ok:
                            snack(_("已取消本次安装。"))
                            set_button_busy(button, False)
                            return
                    await on_update_navdata_click(addon_key_value, button, forced_cycle_id=chosen_cycle or None, local_only=local_only)
                finally:
                    pass

            page.run_task(_runner)

        return _handler

    for ctrl in list(page.services):
        if isinstance(ctrl, ft.FilePicker) and getattr(ctrl, "data", None) == "zip_update_picker":
            try:
                page.services.remove(ctrl)
            except ValueError:
                pass
    zip_update_picker = ft.FilePicker()
    zip_update_picker.data = "zip_update_picker"
    page.services.append(zip_update_picker)

    def _log_severity(line: str) -> str:
        s = line.lower()
        if any(k in s for k in ("失败", "错误", "error", "failed", "fatal", "exception", "traceback")):
            return "error"
        if any(k in s for k in ("警告", "warn", "skipped", "超时", "timeout", "已取消", "取消安装")):
            return "warn"
        if any(k in s for k in ("成功", "完成", "已安装", "ok", "success", "已恢复")):
            return "success"
        if any(k in s for k in ("解压", "下载", "正在", "开始", "校验", "应用变更", "备份")):
            return "info"
        return "default"

    LOG_SEVERITY_PALETTE = {
        "error":   {"fg": "#ff6b6b", "bg": "#3a1f24"},
        "warn":    {"fg": "#f5b942", "bg": "#3a2f1a"},
        "success": {"fg": "#5ad17a", "bg": "#1f3324"},
        "info":    {"fg": "#7cb7ff", "bg": "#1c2a3d"},
        "default": {"fg": colors["log_fg"], "bg": colors["panel_soft_bg"]},
    }

    def _styled_log_row(line: str, *, size: int) -> ft.Container:
        sev = _log_severity(line)
        pal = LOG_SEVERITY_PALETTE[sev]
        return ft.Container(
            border_radius=10,
            bgcolor=pal["bg"],
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            content=ft.Text(line, size=size, color=pal["fg"], selectable=True),
        )

    def refresh_log_overlay() -> None:
        lines = read_log_lines(limit=400)
        log_count = len(lines)
        if not lines:
            lines = [_("暂无当日日志")]
        today_text = datetime.now().strftime("%Y-%m-%d")
        log_overlay_title.value = _("活动日志（{today_text}）({log_count})", today_text=today_text, log_count=log_count)
        log_overlay_list.controls = [_styled_log_row(line, size=fs(12)) for line in lines]

    def close_log_overlay(_e=None) -> None:
        log_overlay_container.visible = False
        update_controls(log_overlay_container)

    def open_log_overlay() -> None:
        refresh_log_overlay()
        log_overlay_container.visible = True
        update_controls(log_overlay_container)

    def refresh_install_overlay() -> None:
        lines = install_overlay_lines[-240:] if install_overlay_lines else [_("暂无安装日志")]
        install_overlay_title.value = f"{install_overlay_title_text} ({len(lines)})"
        install_overlay_list.controls = [_styled_log_row(line, size=fs(12)) for line in lines]

    def refresh_install_overlay_if_needed(force: bool = False) -> None:
        nonlocal install_overlay_last_update_ts
        now = time.monotonic()
        if not force and now - install_overlay_last_update_ts < install_overlay_update_interval:
            return
        install_overlay_last_update_ts = now
        refresh_install_overlay()
        if install_overlay_container.visible:
            page.update()
            schedule_install_overlay_scroll_to_bottom()

    def schedule_install_overlay_scroll_to_bottom() -> None:
        nonlocal install_overlay_scroll_pending
        if install_overlay_scroll_pending:
            return
        install_overlay_scroll_pending = True

        async def runner() -> None:
            nonlocal install_overlay_scroll_pending
            try:
                await asyncio.sleep(0)
                await install_overlay_list.scroll_to(offset=-1, duration=0)
                page.update()
            except Exception:
                pass
            finally:
                install_overlay_scroll_pending = False

        page.run_task(runner)

    def append_install_overlay_line(message: str, *, with_timestamp: bool = True, refresh: bool = True) -> None:
        text = message.strip()
        if not text:
            return
        nonlocal install_progress_last_update_ts
        m = _install_progress_re.match(text)
        if m:
            try:
                pct = max(0, min(100, int(m.group(1))))
            except Exception:
                pct = None
            if pct is not None:
                tail = (m.group(2) or "").strip()
                install_progress_bar.value = pct / 100.0
                install_progress_label.value = _("解压进度: {pct}%{extra}", pct=pct, extra=f"  {tail}" if tail else "")
                install_progress_row.visible = pct < 100
                if pct >= 100:
                    install_progress_bar.value = 0.0
                    install_progress_label.value = ""
                now_ts = time.monotonic()
                if install_overlay_container.visible and (pct >= 100 or now_ts - install_progress_last_update_ts >= 0.1):
                    install_progress_last_update_ts = now_ts
                    page.update()
                return
        line = f"[{human_time()}] {text}" if with_timestamp else text
        install_overlay_lines.append(line)
        if len(install_overlay_lines) > 1200:
            install_overlay_lines[:] = install_overlay_lines[-1200:]
        if refresh:
            refresh_install_overlay_if_needed(force=False)

    def clear_force_install_prompt(*, refresh: bool = True) -> None:
        nonlocal pending_force_install_action, pending_force_install_cancel
        pending_force_install_action = None
        pending_force_install_cancel = None
        if install_force_button is not None:
            install_force_button.visible = False
            install_force_button.disabled = True
        if refresh and install_overlay_container.visible:
            page.update()

    def set_force_install_prompt(
        reason: str,
        on_force: Callable[[], None],
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        nonlocal pending_force_install_action, pending_force_install_cancel
        pending_force_install_action = on_force
        pending_force_install_cancel = on_cancel
        if install_force_button is not None:
            install_force_button.visible = True
            install_force_button.disabled = False
        append_install_overlay_line(_("{reason}。如确认无误，请点击右上角“强制安装”继续。", reason=reason))
        if install_overlay_container.visible:
            page.update()
            schedule_install_overlay_scroll_to_bottom()

    def run_pending_force_install(_e=None) -> None:
        action = pending_force_install_action
        if not callable(action):
            snack(_("当前没有待确认的强制安装任务。"))
            return
        clear_force_install_prompt(refresh=False)
        try:
            append_install_overlay_line(_("用户点击“强制安装”，继续执行安装。"))
            invoke_callback(action)
        except Exception as exc:
            snack(_("强制安装执行失败: {exc}", exc=exc))
            append_install_overlay_line(_("强制安装执行失败: {exc}", exc=exc))
        finally:
            if install_overlay_container.visible:
                page.update()

    def cancel_pending_force_install(reason: str | None = None) -> None:
        cancel_cb = pending_force_install_cancel
        clear_force_install_prompt(refresh=False)
        if reason:
            append_install_overlay_line(reason)
        if callable(cancel_cb):
            try:
                invoke_callback(cancel_cb)
            except Exception:
                pass
        if install_overlay_container.visible:
            page.update()

    def open_install_overlay(title: str = _("安装状态"), reset: bool = False) -> None:
        nonlocal install_overlay_title_text
        if reset:
            install_overlay_lines.clear()
            install_progress_bar.value = 0.0
            install_progress_label.value = ""
            install_progress_row.visible = False
            clear_force_install_prompt(refresh=False)
        install_overlay_title_text = title
        refresh_install_overlay_if_needed(force=True)
        install_overlay_container.visible = True
        page.update()
        schedule_install_overlay_scroll_to_bottom()

    def close_install_overlay(_e=None) -> None:
        if pending_force_install_action is not None:
            cancel_pending_force_install(_("用户关闭安装状态窗口，已取消待确认安装。"))
        install_overlay_container.visible = False
        page.update()

    def clear_install_overlay(_e=None) -> None:
        install_overlay_lines.clear()
        refresh_install_overlay_if_needed(force=True)
        page.update()

    def on_scroll_top_click(_e) -> None:
        async def scroll_top() -> None:
            try:
                await right_scroll_col.scroll_to(offset=0, duration=260)
                page.update()
            except Exception as exc:
                log(f"Scroll top failed: {exc}")

        page.run_task(scroll_top)

    def focus_explorer_window(title_hint: str | None = None) -> None:
        try:
            user32 = ctypes.windll.user32
            title_hint_l = (title_hint or "").lower()
            target_hwnd = ctypes.c_void_p()
            enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

            def cb(hwnd, _lparam):
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.lower()
                class_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, class_buf, 256)
                if class_buf.value in ("CabinetWClass", "ExploreWClass"):
                    if not title_hint_l or title_hint_l in title:
                        target_hwnd.value = hwnd
                        return False
                return True

            user32.EnumWindows(enum_proc(cb), 0)
            if target_hwnd.value:
                user32.ShowWindow(target_hwnd.value, 9)
                user32.SetForegroundWindow(target_hwnd.value)
        except Exception:
            pass

    def masked_path_text(path_text: str) -> str:
        if not path_text:
            return "Target path not set"
        if streamer_mode:
            return _("路径已隐藏")
        return path_text

    def open_folder(path_text: str) -> None:
        if not path_text:
            snack(_("目标路径未设置"))
            return
        p = Path(path_text)
        if p.exists():
            subprocess.Popen(["explorer.exe", str(p)], shell=False)
            focus_explorer_window(p.name)
            log(f"Opened folder: {p}")
            return
        if p.parent.exists():
            subprocess.Popen(["explorer.exe", str(p.parent)], shell=False)
            focus_explorer_window(p.parent.name)
            snack(f"目标文件夹不存在，已打开上级目录: {p.parent}")
            return
        snack(_("路径不存在: {path_text}", path_text=path_text))

    def restore_addon_backup(addon: Addon, target: Path) -> None:
        latest_backup = _utils_find_latest_backup_for_addon(addon, BACKUP_DIR)
        if latest_backup is None:
            snack(f"{addon.name}: 未找到可恢复的备份")
            return
        if target.exists() and not target.is_dir():
            snack(f"{addon.name}: 目标路径不是文件夹")
            return
        try:
            if not target.exists():
                target.mkdir(parents=True, exist_ok=True)
            for child in target.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink(missing_ok=True)
            for item in latest_backup.iterdir():
                dest = target / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)
            snack(f"{addon.name}: 已恢复上次安装的文件")
            log(f"{addon.name}: restored backup from {latest_backup}")
        except Exception as exc:
            snack(f"{addon.name}: 恢复失败: {exc}")

    def refresh_cycle() -> None:
        nonlocal current_cycle_info
        try:
            info = fetch_current_cycle()
            current_cycle_info = info
            if info:
                cycle_id = str(info["cycle_id"])
                start_text = info["start"].astimezone().strftime("%Y-%m-%d")
                end_text = info["end"].astimezone().strftime("%Y-%m-%d")
                days_left = max(0, (info["end"] - datetime.now(timezone.utc)).days)
                airac_id_text.value = cycle_id
                airac_effective_text.value = _("本期数据生效日期：{start_text}", start_text=start_text)
                end_text_mmdd = info["end"].astimezone().strftime(_("%m月%d日"))
                airac_next_text.value = _("本期数据将于{end_text_mmdd}到期（还有{days_left}天）", end_text_mmdd=end_text_mmdd, days_left=days_left)
                log(f"AIRAC current cycle fetched: {cycle_id} (effective {start_text}, end {end_text})")
            else:
                airac_id_text.value = "--"
                airac_effective_text.value = _("本期数据生效日期：--")
                airac_next_text.value = _("本期数据将于--月--日到期")
            update_controls(airac_id_text, airac_effective_text, airac_next_text)
        except Exception as exc:
            current_cycle_info = None
            airac_id_text.value = "--"
            airac_effective_text.value = _("本期数据生效日期：--")
            airac_next_text.value = _("本期数据将于--月--日到期")
            update_controls(airac_id_text, airac_effective_text, airac_next_text)
            snack(_("刷新周期失败: {exc}", exc=exc))

    def visible_addons() -> list[Addon]:
        current_sim = simulator
        current_platform = platform
        items = [a for a in addons_all if a.simulator == current_sim and a.platform == current_platform]
        q = search_text.strip().lower()
        if not q:
            return items
        return [
            a
            for a in items
            if q in a.name.lower()
            or q in a.description.lower()
            or q in infer_package_name(a).lower()
        ]

    def rescan_sources() -> tuple[int, int]:
        source_dir = Path(str(state.get("source_dir", ""))).expanduser()
        if not source_dir.exists():
            source_dir = Path(__file__).resolve().parent
        zips = [p for p in source_dir.iterdir() if p.is_file() and is_supported_archive_file(p)]
        extracted = [p for p in EXTRACTED_DIR.iterdir() if p.is_dir()] if EXTRACTED_DIR.exists() else []
        clear_cycle_json_scan_cache()
        return len(zips), len(extracted)

    def rebuild_lists(
        scroll_to_key: str | None = None,
        precomputed_entries: list[tuple[Addon, str, str, str, str, str]] | None = None,
    ) -> None:
        nonlocal filter_value, selected_addon_key, last_rendered_entries
        api_cycle = "NONE"
        if current_cycle_info and current_cycle_info.get("cycle_id"):
            api_cycle = str(current_cycle_info["cycle_id"])

        left_rows: list[ft.Control] = []
        cards: list[ft.Control] = []
        entries = list(precomputed_entries) if precomputed_entries is not None else compute_filtered_addon_entries(
            addons_all=addons_all,
            simulator=simulator,
            platform=platform,
            search_text=search_text,
            filter_value=filter_value,
            api_cycle=api_cycle,
            state=state,
        )
        last_rendered_entries = entries
        scroll_token_by_addon: dict[str, ft.ScrollKey] = {}

        # Keep selection valid when profile/filter changes.
        if selected_addon_key and not any(k == selected_addon_key for _a, k, _s, _i, _api, _t in entries):
            selected_addon_key = None

        def on_left_addon_click(key: str) -> None:
            nonlocal selected_addon_key
            selected_addon_key = key
            rebuild_lists(scroll_to_key=key, precomputed_entries=last_rendered_entries)

        for addon, key, status, installed, api, target in entries:
            is_selected = key == selected_addon_key
            left_rows.append(
                ft.Container(
                    border_radius=12,
                    bgcolor=colors["list_sel_bg"] if is_selected else colors["list_bg"],
                    border=ft.Border.all(3 if is_selected else 1, "#1a73e8" if is_selected else "#2f3c52"),
                    shadow=(
                        ft.BoxShadow(blur_radius=12, spread_radius=2, color="#1a73e840")
                        if is_selected
                        else None
                    ),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                    on_click=lambda _e, k=key: on_left_addon_click(k),
                    content=ft.Row(
                        controls=[
                            ft.Text("●", color=status_dot_color(status), size=fs(12)),
                            ft.Text(
                                addon.name,
                                size=fs(13),
                                weight=ft.FontWeight.W_700 if is_selected else ft.FontWeight.W_600,
                                color=colors["list_sel_fg"] if is_selected else colors["list_fg"],
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            )

        for idx, (addon, key, status, installed, api, target) in enumerate(entries):
            marker = f"card-{idx}"
            scroll_token = ft.ScrollKey(marker)
            scroll_token_by_addon[key] = scroll_token
            badge_bg, badge_fg = status_badge_style(status)
            is_selected = key == selected_addon_key
            cards.append(
                ft.Container(
                    key=scroll_token,
                    border_radius=16,
                    bgcolor=colors["card_bg"],
                    border=ft.Border.all(3 if is_selected else 1, "#1a73e8" if is_selected else "#2f3c52"),
                    shadow=(
                        ft.BoxShadow(blur_radius=12, spread_radius=2, color="#1a73e840")
                        if is_selected
                        else None
                    ),
                    padding=12,
                    content=ft.Column(
                        spacing=6,
                        controls=[
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.Column(
                                        spacing=2,
                                        controls=[
                                            ft.Text(addon.name, size=fs(18), weight=ft.FontWeight.BOLD, color=colors["card_title"]),
                                            ft.Text(addon.description, size=fs(12), color=colors["card_sub"]),
                                        ],
                                    ),
                                    ft.Container(
                                        bgcolor=badge_bg,
                                        border_radius=999,
                                        padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                                        content=ft.Text(status, size=fs(11), weight=ft.FontWeight.W_700, color=badge_fg),
                                    ),
                                ],
                            ),
                            ft.Text(
                                _("已安装") if addon.package_name.strip().lower() in {"navigraph-msfs2020-base", "navigraph-msfs2024-base"}
                                else _("已安装: {installed}    API: {api}", installed=installed, api=api),
                                size=fs(12), color=colors["card_meta"]),
                            ft.Text(
                                _("未检测到 cycle.json / cycle_info.txt\n建议点击「打开目录」检查文件夹结构"),
                                size=fs(11),
                                color="#c99600",
                                italic=True,
                            ) if status == "UPDATE READY" and installed == "UNKNOWN" else ft.Container(),
                            ft.Text(masked_path_text(target), size=fs(12), color=colors["text_path"]),
                            ft.Row(
                                spacing=6,
                                controls=[
                                    ft.Button(
                                        _("更新导航数据"),
                                        icon=ft.Icons.UPLOAD_FILE,
                                        bgcolor="#1a73e8",
                                        color="#ffffff",
                                        height=30,
                                        style=ft.ButtonStyle(
                                            padding=ft.Padding.symmetric(horizontal=10, vertical=0),
                                        ),
                                        on_click=make_update_click_handler(key),
                                    ),
                                    ft.Button(
                                        _("从本地安装"),
                                        icon=ft.Icons.FOLDER_ZIP,
                                        bgcolor=colors["panel_soft_bg"],
                                        color=colors["text_title"],
                                        height=30,
                                        style=ft.ButtonStyle(
                                            padding=ft.Padding.symmetric(horizontal=10, vertical=0),
                                        ),
                                        on_click=make_update_click_handler(key, local_only=True),
                                        visible=backup_power_login_valid,
                                    ),
                                    ft.Button(
                                        _("打开目录"),
                                        icon=ft.Icons.FOLDER_OPEN,
                                        bgcolor=colors["panel_bg"],
                                        color=colors["text_meta"],
                                        height=30,
                                        style=ft.ButtonStyle(
                                            padding=ft.Padding.symmetric(horizontal=10, vertical=0),
                                        ),
                                        on_click=lambda _e, p=target: open_folder(p),
                                    ),
                                    ft.Button(
                                        _("恢复上次安装的文件"),
                                        icon=ft.Icons.RESTORE,
                                        bgcolor="#b83d4b",
                                        color="#ffffff",
                                        height=30,
                                        style=ft.ButtonStyle(
                                            padding=ft.Padding.symmetric(horizontal=10, vertical=0),
                                        ),
                                        on_click=lambda _e, a=addon, p=target: restore_addon_backup(a, Path(p) if not isinstance(p, Path) else p),
                                    ),
                                ],
                            ),
                        ],
                    ),
                )
            )

        if not left_rows:
            left_rows = [ft.Text("No addons", size=fs(12), color=colors["text_sub"])]
        if not cards:
            cards = [
                ft.Container(
                    border_radius=16,
                    bgcolor=colors["card_bg"],
                    border=ft.Border.all(1, "#2f3c52"),
                    padding=24,
                    content=ft.Column(
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.INBOX_OUTLINED, size=58, color=colors["text_sub"]),
                            ft.Text(_("暂无该过滤条件的机型"), size=fs(16), weight=ft.FontWeight.W_700, color=colors["text_meta"]),
                            ft.Button(
                                _("重置筛选"),
                                icon=ft.Icons.RESTART_ALT,
                                on_click=lambda _e: on_filter_change("All"),
                                bgcolor=colors["panel_bg"],
                                color=colors["text_meta"],
                            ),
                        ],
                    ),
                )
            ]

        left_list.controls = left_rows
        right_cards_list.controls = cards
        update_controls(left_list, right_cards_list)
        if scroll_to_key:
            async def safe_scroll() -> None:
                await asyncio.sleep(0.08)
                try:
                    token = scroll_token_by_addon.get(scroll_to_key)
                    if token is not None:
                        await right_scroll_col.scroll_to(scroll_key=token, duration=220)
                        update_controls(right_scroll_col)
                        return
                    target_idx = next((i for i, (_addon, key, *_rest) in enumerate(entries) if key == scroll_to_key), None)
                    if target_idx is not None:
                        await right_scroll_col.scroll_to(offset=max(0, target_idx * 230), duration=220)
                        update_controls(right_scroll_col)
                except Exception as exc:
                    log(f"Scroll jump failed: {exc}")

            page.run_task(safe_scroll)

    async def refresh_cycle_async(notify_fail: bool = True) -> None:
        nonlocal current_cycle_info
        try:
            info = await asyncio.to_thread(fetch_current_cycle)
            current_cycle_info = info
            if info:
                cycle_id = str(info["cycle_id"])
                start_text = info["start"].astimezone().strftime("%Y-%m-%d")
                end_text = info["end"].astimezone().strftime("%Y-%m-%d")
                days_left = max(0, (info["end"] - datetime.now(timezone.utc)).days)
                airac_id_text.value = cycle_id
                airac_effective_text.value = _("本期数据生效日期：{start_text}", start_text=start_text)
                end_text_mmdd = info["end"].astimezone().strftime(_("%m月%d日"))
                airac_next_text.value = _("本期数据将于{end_text_mmdd}到期（还有{days_left}天）", end_text_mmdd=end_text_mmdd, days_left=days_left)
                log(f"AIRAC current cycle fetched: {cycle_id} (effective {start_text}, end {end_text})")
            else:
                airac_id_text.value = "--"
                airac_effective_text.value = _("本期数据生效日期：--")
                airac_next_text.value = _("本期数据将于--月--日到期")
            update_controls(airac_id_text, airac_effective_text, airac_next_text)
        except Exception as exc:
            current_cycle_info = None
            airac_id_text.value = "--"
            airac_effective_text.value = _("本期数据生效日期：--")
            airac_next_text.value = _("本期数据将于--月--日到期")
            update_controls(airac_id_text, airac_effective_text, airac_next_text)
            if notify_fail:
                snack(_("刷新周期失败: {exc}", exc=exc))
            else:
                log(_("刷新周期失败: {exc}", exc=exc))
        finally:
            cid = ""
            if isinstance(current_cycle_info, dict):
                cid = str(current_cycle_info.get("cycle_id", "")).strip()
            if not cid or cid in {"--", "UNKNOWN"}:
                page.run_task(_auto_retry_refresh_cycle)

    _auto_retry_attempts = {"n": 0}
    _AUTO_RETRY_MAX = 3
    _AUTO_RETRY_DELAYS = (3, 8, 20)

    async def _auto_retry_refresh_cycle() -> None:
        attempt = _auto_retry_attempts["n"]
        if attempt >= _AUTO_RETRY_MAX:
            return
        _auto_retry_attempts["n"] = attempt + 1
        delay = _AUTO_RETRY_DELAYS[min(attempt, len(_AUTO_RETRY_DELAYS) - 1)]
        log(_("AIRAC 当前为空，{delay}s 后自动重试（{n}/{max}）", delay=delay, n=attempt + 1, max=_AUTO_RETRY_MAX))
        try:
            await asyncio.sleep(delay)
            await refresh_cycle_async(notify_fail=False)
            cid = ""
            if isinstance(current_cycle_info, dict):
                cid = str(current_cycle_info.get("cycle_id", "")).strip()
            if cid and cid not in {"--", "UNKNOWN"}:
                _auto_retry_attempts["n"] = 0
        except Exception as exc:
            log(_("AIRAC 自动重试失败：{exc}", exc=exc))

    def show_loading_state(message: str) -> None:
        left_list.controls = [ft.Text(message, size=fs(12), color=colors["text_sub"])]
        right_cards_list.controls = [
            ft.Container(
                border_radius=16,
                bgcolor=colors["card_bg"],
                border=ft.Border.all(1, "#2f3c52"),
                padding=24,
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.ProgressRing(width=28, height=28, stroke_width=3),
                        ft.Text(message, size=fs(16), weight=ft.FontWeight.W_700, color=colors["text_meta"]),
                    ],
                ),
            )
        ]
        page.update()

    async def run_blocking_with_feedback(
        func: Callable[..., Any],
        *args,
        message: str,
        pulse_interval: float = 1.0,
        progress_callback: Callable[[str], None] | None = None,
        provide_progress_callback: bool = False,
        show_page_loading: bool = False,
        show_operation_dialog_ui: bool = True,
        **kwargs: Any,
    ) -> Any:
        if show_page_loading:
            show_loading_state(message)
        if show_operation_dialog_ui:
            show_operation_dialog(_("处理中"), message, _("已耗时 0s"))
        progress_queue: SimpleQueue[str] = SimpleQueue()

        def worker_progress(line: str) -> None:
            text = str(line).strip()
            if text:
                progress_queue.put(text)

        def flush_progress_queue() -> None:
            if progress_callback is None:
                while True:
                    try:
                        progress_queue.get_nowait()
                    except Empty:
                        break
                return
            batch_lines: list[str] = []
            while True:
                try:
                    line = progress_queue.get_nowait()
                except Empty:
                    break
                batch_lines.append(line)
            if not batch_lines:
                return
            if progress_callback is append_install_overlay_line:
                for line in batch_lines:
                    append_install_overlay_line(line, refresh=False)
                refresh_install_overlay_if_needed(force=True)
                return
            for line in batch_lines:
                progress_callback(line)

        if provide_progress_callback:
            task = asyncio.create_task(asyncio.to_thread(func, *args, worker_progress, **kwargs))
        else:
            task = asyncio.create_task(asyncio.to_thread(func, *args, **kwargs))
        start_ts = asyncio.get_running_loop().time()
        dot_count = 0
        try:
            while not task.done():
                await asyncio.sleep(pulse_interval)
                flush_progress_queue()
                if task.done():
                    break
                dot_count = (dot_count + 1) % 4
                elapsed = int(asyncio.get_running_loop().time() - start_ts)
                dots = "." * dot_count
                step_msg = f"{message}{dots} ({elapsed}s)"
                if show_page_loading and not op_dialog_suppressed:
                    show_loading_state(step_msg)
                if show_operation_dialog_ui:
                    update_operation_dialog(step_msg, _("已耗时 {elapsed}s", elapsed=elapsed))
            result = await task
            flush_progress_queue()
            return result
        finally:
            flush_progress_queue()
            if show_operation_dialog_ui:
                close_operation_dialog(reset_suppressed=False)

    async def rebuild_lists_async(scroll_to_key: str | None = None, show_loading: bool = False) -> None:
        nonlocal rebuild_generation
        rebuild_generation += 1
        generation = rebuild_generation
        if show_loading:
            show_loading_state(_("正在扫描机型状态..."))
        api_cycle = "NONE"
        if current_cycle_info and current_cycle_info.get("cycle_id"):
            api_cycle = str(current_cycle_info["cycle_id"])
        entries = await asyncio.to_thread(
            catalog_compute_filtered_addon_entries,
            addons_all,
            simulator,
            platform,
            search_text,
            filter_value,
            api_cycle,
            state,
        )
        if generation != rebuild_generation:
            return
        rebuild_lists(scroll_to_key=scroll_to_key, precomputed_entries=entries)

    def trigger_rebuild(scroll_to_key: str | None = None, show_loading: bool = False) -> None:
        async def runner() -> None:
            await rebuild_lists_async(scroll_to_key=scroll_to_key, show_loading=show_loading)

        page.run_task(runner)

    async def rescan_and_rebuild_async(show_loading: bool = False, notify_done: bool = False) -> None:
        try:
            if show_loading:
                show_loading_state(_("正在重新扫描资源..."))
            zip_count, extracted_count = await asyncio.to_thread(rescan_sources)
            log(f"Rescanned source: {zip_count} zip(s), {extracted_count} extracted package(s).")
            await rebuild_lists_async(show_loading=False)
            if notify_done:
                snack(_("已重新扫描并刷新机型列表。"))
        except Exception as exc:
            snack(_("重新扫描失败: {exc}", exc=exc))

    def on_refresh_click(e):
        button = e.control if isinstance(getattr(e, "control", None), ft.Button) else None
        if is_button_busy(button):
            snack(_("刷新任务正在进行中，请稍候。"))
            return
        reset_operation_dialog_suppression()
        set_button_busy(button, True, _("刷新中..."))

        async def runner() -> None:
            try:
                airac_id_text.value = "..."
                airac_effective_text.value = _("本期数据生效日期：刷新中...")
                airac_next_text.value = _("本期数据将于--月--日到期")
                update_controls(airac_id_text, airac_effective_text, airac_next_text, button)
                await refresh_cycle_async()
                await rebuild_lists_async(show_loading=False)
            finally:
                set_button_busy(button, False)

        page.run_task(runner)

    def on_rescan_click(e):
        button = e.control if isinstance(getattr(e, "control", None), ft.Button) else None
        if is_button_busy(button):
            snack(_("扫描任务正在进行中，请稍候。"))
            return
        reset_operation_dialog_suppression()
        set_button_busy(button, True, _("扫描中..."))

        async def runner() -> None:
            try:
                await rescan_and_rebuild_async(show_loading=True, notify_done=True)
            finally:
                set_button_busy(button, False)

        page.run_task(runner)

    def on_settings_click(_e):
        try:
            key20 = community_key("MSFS 2020", platform)
            key24 = community_key("MSFS 2024", platform)
            key24_extra = platform
            has20 = bool(state.get("enabled_simulators", {}).get("MSFS 2020", True))
            has24 = bool(state.get("enabled_simulators", {}).get("MSFS 2024", True))
            has20_check = ft.Checkbox(label=_("我有 MSFS 2020"), value=has20)
            has24_check = ft.Checkbox(label=_("我有 MSFS 2024"), value=has24)
            fs20_field = ft.TextField(
                label="FS20 Community",
                value=str(state.get("community_paths", {}).get(key20, "")).strip() or default_community_base("MSFS 2020", platform),
                expand=True,
            )
            fs24_field = ft.TextField(
                label="FS24 Community",
                value=str(state.get("community_paths", {}).get(key24, "")).strip() or default_community_base("MSFS 2024", platform),
                expand=True,
            )
            fs24_extra_field = ft.TextField(
                label="FS24 Community2024",
                value=str(state.get("community_2024_paths", {}).get(key24_extra, "")).strip(),
                hint_text=r"例如 ...\Packages\Community2024",
                expand=True,
            )
            current_workers = normalize_batch_download_workers(
                state.get("batch_download_workers", DEFAULT_BATCH_DOWNLOAD_WORKERS)
            )
            workers_dd = ft.Dropdown(
                label=_("一键安装下载线程数"),
                value=str(current_workers),
                options=[ft.dropdown.Option(str(v)) for v in BATCH_DOWNLOAD_WORKER_OPTIONS],
                width=220,
            )
            default_cache_root_display = str(resolve_cache_root_dir(None, create=False))
            configured_cache_root = normalize_cache_root_dir(str(state.get("cache_root_dir", "")).strip())
            cache_root_field = ft.TextField(
                label=_("缓存目录（可选）"),
                value=configured_cache_root or default_cache_root_display,
                hint_text=r"留空使用默认内部目录",
                expand=True,
            )
            cache_cleanup_days = normalize_cache_cleanup_days(
                state.get("cache_cleanup_days", DEFAULT_CACHE_CLEANUP_DAYS)
            )
            cache_cleanup_days_dd = ft.Dropdown(
                label=_("缓存自动清理周期（天）"),
                value=str(cache_cleanup_days),
                options=[ft.dropdown.Option(str(v)) for v in CACHE_CLEANUP_DAY_OPTIONS],
                width=220,
            )
            crash_upload_check = ft.Checkbox(
                label=_("发生崩溃时自动上传报告（匿名）"),
                value=bool(state.get("crash_upload_enabled", False)),
            )
            language_dd = ft.Dropdown(
                label=_("界面语言 / Language"),
                value=str(state.get("locale", "zh") or "zh"),
                options=[
                    ft.dropdown.Option("zh", "中文"),
                    ft.dropdown.Option("en", "English"),
                ],
                width=220,
            )
            cycle_subscribe_check = ft.Checkbox(
                label=_("新 AIRAC 期数上架时邮件通知我"),
                value=bool(state.get("cycle_subscribe_enabled", False)),
            )
            err = ft.Text("", size=fs(12), color="#b83d4b")
            current_version_text = ft.Text(
                f"当前版本: {format_version_display(APP_VERSION)}",
                size=fs(12),
                color=colors["text_sub"],
                selectable=True,
            )
            update_check_status = ft.Text(
                _("更新状态: 未检查"),
                size=fs(12),
                color=colors["text_meta"],
                selectable=True,
            )

            def _make_sim_dot(running: bool) -> ft.Container:
                return ft.Container(
                    width=10, height=10, border_radius=5,
                    bgcolor="#2ecc71" if running else "#e74c3c",
                )
            try:
                import simconnect_status as _scs
                _scs_initial = _scs.latest_status()
            except Exception:
                _scs_initial = None
            sim_2020_dot = _make_sim_dot(bool(getattr(_scs_initial, "running_2020", False)))
            sim_2024_dot = _make_sim_dot(bool(getattr(_scs_initial, "running_2024", False)))
            sim_2020_text = ft.Text(
                "MSFS 2020：" + (_("运行中") if getattr(_scs_initial, "running_2020", False) else _("未运行")),
                size=fs(12), color=colors["text_sub"],
            )
            sim_2024_text = ft.Text(
                "MSFS 2024：" + (_("运行中") if getattr(_scs_initial, "running_2024", False) else _("未运行")),
                size=fs(12), color=colors["text_sub"],
            )
            sim_status_row = ft.Row(spacing=16, controls=[
                ft.Row(spacing=6, controls=[sim_2020_dot, sim_2020_text]),
                ft.Row(spacing=6, controls=[sim_2024_dot, sim_2024_text]),
            ])

            async def _settings_sim_status_loop() -> None:
                while True:
                    try:
                        import simconnect_status as _scs2
                        st = _scs2.latest_status()
                        sim_2020_dot.bgcolor = "#2ecc71" if st.running_2020 else "#e74c3c"
                        sim_2024_dot.bgcolor = "#2ecc71" if st.running_2024 else "#e74c3c"
                        sim_2020_text.value = "MSFS 2020：" + (_("运行中") if st.running_2020 else _("未运行"))
                        sim_2024_text.value = "MSFS 2024：" + (_("运行中") if st.running_2024 else _("未运行"))
                        try:
                            update_controls(sim_2020_dot, sim_2024_dot, sim_2020_text, sim_2024_text)
                        except Exception:
                            pass
                    except Exception:
                        pass
                    await asyncio.sleep(2.0)

            try:
                page.run_task(_settings_sim_status_loop)
            except Exception:
                pass

            check_update_btn = ft.Button(_("检查更新"))
            open_release_btn = ft.TextButton(_("打开发布页"), visible=False)
            latest_release_url = f"https://github.com/{normalize_github_repo(GITHUB_RELEASE_REPO)}/releases"
            dlg: ft.Control | None = None
            browse20_btn = ft.Button(_("浏览"))
            browse24_btn = ft.Button(_("浏览"))
            browse24_extra_btn = ft.Button(_("浏览"))
            browse_cache_btn = ft.Button(_("修改"))

            for ctrl in list(page.services):
                if isinstance(ctrl, ft.FilePicker) and getattr(ctrl, "data", None) in {
                    "settings_comm_picker_20",
                    "settings_comm_picker_24",
                    "settings_comm_picker_24_extra",
                    "settings_cache_picker",
                }:
                    try:
                        page.services.remove(ctrl)
                    except ValueError:
                        pass
            picker20 = ft.FilePicker()
            picker20.data = "settings_comm_picker_20"
            picker24 = ft.FilePicker()
            picker24.data = "settings_comm_picker_24"
            picker24_extra = ft.FilePicker()
            picker24_extra.data = "settings_comm_picker_24_extra"
            picker_cache = ft.FilePicker()
            picker_cache.data = "settings_cache_picker"
            page.services.extend([picker20, picker24, picker24_extra, picker_cache])

            def close_dialog(_evt=None) -> None:
                close_custom_modal()

            def open_release_page(_evt=None) -> None:
                if latest_release_url:
                    open_external_url(latest_release_url)

            async def run_manual_update_check() -> None:
                nonlocal latest_release_url
                repo = normalize_github_repo(GITHUB_RELEASE_REPO)
                update_check_status.value = _("更新状态: 正在检查 ({repo})...", repo=repo)
                open_release_btn.visible = False
                if not try_control_update(dlg):
                    page.update()
                try:
                    release = await asyncio.to_thread(fetch_latest_github_release, repo)
                except Exception as exc:
                    latest_release_url = f"https://github.com/{repo}/releases"
                    update_check_status.value = (
                        _("更新状态: 与github通信失败，请手动检查更新或更换网络后重试。")
                    )
                    log(_("设置页检查更新失败: {exc}", exc=exc))
                    open_release_btn.visible = True
                    if not try_control_update(dlg):
                        page.update()
                    return

                latest_tag = str(release.get("tag_name", "")).strip()
                latest_name = str(release.get("name", "")).strip()
                latest_display = format_version_display(latest_tag or latest_name)
                latest_release_url = str(release.get("html_url", "")).strip() or f"https://github.com/{repo}/releases"
                is_new = _is_newer_version(latest_display, APP_VERSION)
                if is_new:
                    update_check_status.value = (
                        f"更新状态: 发现新版本 {latest_display}（当前 {format_version_display(APP_VERSION)}）"
                    )
                else:
                    update_check_status.value = (
                        f"更新状态: 已是最新版本（当前 {format_version_display(APP_VERSION)}，远端 {latest_display}）"
                    )
                open_release_btn.visible = True
                if not try_control_update(dlg):
                    page.update()

            def check_update_click(_evt=None) -> None:
                if is_button_busy(check_update_btn):
                    return
                set_button_busy(check_update_btn, True, _("检查中..."))

                async def runner() -> None:
                    try:
                        await run_manual_update_check()
                    finally:
                        set_button_busy(check_update_btn, False)

                page.run_task(runner)

            def browse_fs20(_evt) -> None:
                async def runner() -> None:
                    try:
                        path = await picker20.get_directory_path(dialog_title=_("选择 FS20 Community"))
                        if path:
                            fs20_field.value = path
                            page.update()
                    except Exception as exc:
                        err.value = _("选择目录失败: {exc}", exc=exc)
                        page.update()

                page.run_task(runner)

            def browse_fs24(_evt) -> None:
                async def runner() -> None:
                    try:
                        path = await picker24.get_directory_path(dialog_title=_("选择 FS24 Community"))
                        if path:
                            fs24_field.value = path
                            page.update()
                    except Exception as exc:
                        err.value = _("选择目录失败: {exc}", exc=exc)
                        page.update()

                page.run_task(runner)

            def browse_fs24_extra(_evt) -> None:
                async def runner() -> None:
                    try:
                        path = await picker24_extra.get_directory_path(dialog_title=_("选择 FS24 Community2024"))
                        if path:
                            fs24_extra_field.value = path
                            page.update()
                    except Exception as exc:
                        err.value = _("选择目录失败: {exc}", exc=exc)
                        page.update()

                page.run_task(runner)

            def browse_cache_dir(_evt) -> None:
                async def runner() -> None:
                    try:
                        path = await picker_cache.get_directory_path(dialog_title=_("选择缓存目录"))
                        if path:
                            cache_root_field.value = path
                            page.update()
                    except Exception as exc:
                        err.value = _("选择目录失败: {exc}", exc=exc)
                        page.update()

                page.run_task(runner)

            browse20_btn.on_click = browse_fs20
            browse24_btn.on_click = browse_fs24
            browse24_extra_btn.on_click = browse_fs24_extra
            browse_cache_btn.on_click = browse_cache_dir
            check_update_btn.on_click = check_update_click
            open_release_btn.on_click = open_release_page

            def refresh_field_status() -> None:
                fs20_field.disabled = not bool(has20_check.value)
                browse20_btn.disabled = not bool(has20_check.value)
                fs24_field.disabled = not bool(has24_check.value)
                browse24_btn.disabled = not bool(has24_check.value)
                fs24_extra_field.disabled = not bool(has24_check.value)
                browse24_extra_btn.disabled = not bool(has24_check.value)
                page.update()

            def on_sim_check_change(_evt) -> None:
                refresh_field_status()

            has20_check.on_change = on_sim_check_change
            has24_check.on_change = on_sim_check_change

            def save_click(_evt) -> None:
                p20 = fs20_field.value.strip()
                p24 = fs24_field.value.strip()
                p24_extra = fs24_extra_field.value.strip()
                workers = normalize_batch_download_workers(workers_dd.value)
                cache_root_raw = cache_root_field.value.strip()
                cache_root_normalized = normalize_cache_root_dir(cache_root_raw)
                default_cache_root_normalized = normalize_cache_root_dir(default_cache_root_display)
                cache_root_to_save = (
                    ""
                    if cache_root_normalized == default_cache_root_normalized
                    else cache_root_normalized
                )
                cleanup_days = normalize_cache_cleanup_days(cache_cleanup_days_dd.value)
                has20_selected = bool(has20_check.value)
                has24_selected = bool(has24_check.value)
                if not has20_selected and not has24_selected:
                    err.value = _("至少需要选择一个模拟器（MSFS 2020 或 MSFS 2024）。")
                    page.update()
                    return
                if has20_selected and not is_valid_community_path(p20):
                    err.value = _("MSFS 2020 已启用，请填写有效的 FS20 Community 路径（目录名需为 Community）。")
                    page.update()
                    return
                if has24_selected and not is_valid_community_path(p24):
                    err.value = _("MSFS 2024 已启用，请填写有效的 FS24 Community 路径（目录名需为 Community）。")
                    page.update()
                    return
                if has24_selected and not is_valid_community2024_path(p24_extra):
                    err.value = _("MSFS 2024 已启用，请填写有效的 FS24 Community2024 路径（目录名需为 Community2024 或 Community）。")
                    page.update()
                    return
                effective_cache_root = cache_root_to_save or default_cache_root_normalized
                if effective_cache_root:
                    cache_root_path = Path(effective_cache_root)
                    if cache_root_path.exists() and not cache_root_path.is_dir():
                        err.value = _("缓存目录路径无效：该路径存在但不是目录。")
                        page.update()
                        return
                    try:
                        cache_root_path.mkdir(parents=True, exist_ok=True)
                    except Exception as exc:
                        err.value = _("创建缓存目录失败: {exc}", exc=exc)
                        page.update()
                        return
                state.setdefault("community_paths", {})[key20] = p20
                state.setdefault("community_paths", {})[key24] = p24
                state.setdefault("community_2024_paths", {})[key24_extra] = p24_extra
                state.setdefault("enabled_simulators", {})["MSFS 2020"] = has20_selected
                state.setdefault("enabled_simulators", {})["MSFS 2024"] = has24_selected
                state["batch_download_workers"] = workers
                state["cache_root_dir"] = cache_root_to_save
                state["cache_cleanup_days"] = cleanup_days
                state["crash_upload_enabled"] = bool(crash_upload_check.value)
                new_locale = str(language_dd.value or "zh").strip().lower() or "zh"
                locale_changed = new_locale != str(state.get("locale", "zh") or "zh")
                state["locale"] = new_locale
                if locale_changed:
                    from i18n import set_locale as _set_locale
                    _set_locale(new_locale)
                new_subscribe_enabled = bool(cycle_subscribe_check.value)
                old_subscribe_enabled = bool(state.get("cycle_subscribe_enabled", False))
                state["cycle_subscribe_enabled"] = new_subscribe_enabled
                if new_subscribe_enabled != old_subscribe_enabled:
                    saved_token = str(state.get("backup_power_token", "")).strip()
                    if saved_token:
                        try:
                            backup_power_cycle_subscription_put(saved_token, new_subscribe_enabled)
                        except Exception as exc:
                            log(_("同步期数订阅状态失败：{exc}", exc=exc))
                            snack(_("订阅设置保存失败: {exc}", exc=exc))
                nonlocal simulator
                enabled_now = enabled_simulators(state)
                if simulator not in enabled_now:
                    simulator = enabled_now[0]
                    state["simulator"] = simulator
                state["community_setup_done"] = True
                save_state(state)
                clear_cycle_json_scan_cache()
                close_dialog()
                snack(_("设置已保存"))
                page.clean()
                main(page, fast_reload=True, cached_cycle=current_cycle_info)

            dlg = custom_modal_container
            open_custom_modal(
                _("设置"),
                [
                    ft.Text(_("当前平台: {platform}", platform=platform), size=fs(12), color=colors["text_sub"]),
                    ft.Row(spacing=10, controls=[current_version_text, check_update_btn, open_release_btn]),
                    update_check_status,
                    sim_status_row,
                    ft.Row(spacing=16, controls=[has20_check, has24_check]),
                    ft.Row(spacing=8, controls=[fs20_field, browse20_btn]),
                    ft.Row(spacing=8, controls=[fs24_field, browse24_btn]),
                    ft.Row(spacing=8, controls=[fs24_extra_field, browse24_extra_btn]),
                    ft.Row(spacing=8, controls=[workers_dd]),
                    ft.Row(spacing=8, controls=[cache_root_field, browse_cache_btn]),
                    ft.Row(spacing=8, controls=[cache_cleanup_days_dd]),
                    ft.Text(_("默认缓存目录: {default_cache_root_display}", default_cache_root_display=default_cache_root_display), size=fs(12), color=colors["text_meta"]),
                    ft.Text(_("目录必须存在；FS20/FS24 目录名需为 Community，FS24 Community2024 路径目录名需为 Community2024。"), size=fs(12), color=colors["text_meta"]),
                    ft.Text(_("一键安装会并发下载，线程越大下载越快，但网络压力更高。"), size=fs(12), color=colors["text_meta"]),
                    ft.Text(_("缓存目录留空时使用默认内部目录；程序会按“缓存自动清理周期时间”清理过期缓存。"), size=fs(12), color=colors["text_meta"]),
                    ft.Container(height=4),
                    crash_upload_check,
                    ft.Text(_("仅上传异常堆栈与版本信息，不包含路径或账号。"), size=fs(12), color=colors["text_meta"]),
                    cycle_subscribe_check,
                    ft.Text(_("登录账户后才会生效；订阅后由后台检测新期并发送邮件。"), size=fs(12), color=colors["text_meta"]),
                    ft.Container(height=4),
                    language_dd,
                    ft.Container(height=4),
                    ft.Row(spacing=8, controls=[
                        ft.Text(_("期数选择器风格："), size=fs(12), color=colors["text_sub"]),
                        ft.TextButton(
                            _("更改…"),
                            on_click=lambda _e: show_cycle_picker_style_wizard(force=True),
                        ),
                    ], visible=backup_power_login_valid),
                    err,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton(_("取消"), on_click=close_dialog),
                            ft.Button(_("保存"), bgcolor="#1a73e8", color="#ffffff", on_click=save_click),
                        ],
                    ),
                ],
                width=780,
                body_height=560,
            )
            refresh_field_status()
        except Exception as exc:
            snack(_("打开设置失败: {exc}", exc=exc))

    def on_add_addon_click(_e):
        try:
            name_field = ft.TextField(label=_("机型名称"), hint_text=_("例如 PMDG 777-200LR"))
            desc_field = ft.TextField(label=_("描述"), hint_text=_("显示在卡片副标题"))
            cycle_dir_field = ft.TextField(
                label=_("cycle.json 所在目录"),
                hint_text=r"例如 ...\pmdg-aircraft-77l\work\NavigationData",
                expand=True,
            )
            browse_cycle_dir_btn = ft.Button(_("浏览"))
            sim_dd = ft.Dropdown(
                label=_("模拟器"),
                value=simulator,
                options=[ft.dropdown.Option(v) for v in active_sims],
            )
            plat_dd = ft.Dropdown(
                label=_("平台"),
                value=platform,
                options=[ft.dropdown.Option(v) for v in PLATFORMS],
            )
            err = ft.Text("", size=fs(12), color="#b83d4b")
            dlg: ft.Control | None = None

            for ctrl in list(page.services):
                if isinstance(ctrl, ft.FilePicker) and getattr(ctrl, "data", None) == "add_addon_cycle_dir_picker":
                    try:
                        page.services.remove(ctrl)
                    except ValueError:
                        pass
            cycle_dir_picker = ft.FilePicker()
            cycle_dir_picker.data = "add_addon_cycle_dir_picker"
            page.services.append(cycle_dir_picker)

            def close_dialog(_evt=None) -> None:
                close_custom_modal()

            def browse_cycle_dir(_evt) -> None:
                async def runner() -> None:
                    try:
                        path = await cycle_dir_picker.get_directory_path(dialog_title=_("选择 cycle.json 所在目录"))
                        if path:
                            cycle_dir_field.value = path
                            page.update()
                    except Exception as exc:
                        err.value = _("选择目录失败: {exc}", exc=exc)
                        page.update()

                page.run_task(runner)

            browse_cycle_dir_btn.on_click = browse_cycle_dir

            def save_click(_evt) -> None:
                name = name_field.value.strip()
                if not name:
                    err.value = _("机型名称不能为空。")
                    page.update()
                    return
                sim_value = str(sim_dd.value or "").strip()
                plat_value = str(plat_dd.value or "").strip()
                if sim_value not in MSFS_VERSIONS or plat_value not in PLATFORMS:
                    err.value = _("请选择有效的模拟器与平台。")
                    page.update()
                    return
                cycle_dir_text = cycle_dir_field.value.strip()
                if not cycle_dir_text:
                    err.value = _("请选择 cycle.json 所在目录。")
                    page.update()
                    return
                cycle_dir = Path(cycle_dir_text)
                if not cycle_dir.exists() or not cycle_dir.is_dir():
                    err.value = _("所选目录不存在或不可用。")
                    page.update()
                    return
                if not (cycle_dir / "cycle.json").exists():
                    err.value = _("所选目录下未找到 cycle.json，请选择正确目录。")
                    page.update()
                    return

                pkg = ""
                path_parts_lower = [part.lower() for part in cycle_dir.parts]
                if "packages" in path_parts_lower:
                    idx = path_parts_lower.index("packages")
                    if idx + 1 < len(cycle_dir.parts):
                        pkg = cycle_dir.parts[idx + 1].lower()
                if not pkg:
                    pkg = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

                new_addon = Addon(
                    name=name,
                    description=desc_field.value.strip() or name,
                    simulator=sim_value,
                    platform=plat_value,
                    target_path=str(cycle_dir),
                    package_name=pkg,
                    navdata_subpath="",
                )
                if any(addon_key(existing) == addon_key(new_addon) for existing in addons_all):
                    err.value = _("该机型（同模拟器/平台/package）已存在。")
                    page.update()
                    return
                state.setdefault("addons", []).append(
                    {
                        "name": new_addon.name,
                        "description": new_addon.description,
                        "simulator": new_addon.simulator,
                        "platform": new_addon.platform,
                        "target_path": new_addon.target_path,
                        "package_name": new_addon.package_name,
                        "navdata_subpath": new_addon.navdata_subpath,
                    }
                )
                addons_all.append(new_addon)
                save_state(state)
                close_dialog()
                snack(f"已添加机型: {new_addon.name}")
                trigger_rebuild(scroll_to_key=addon_key(new_addon), show_loading=False)

            dlg = custom_modal_container
            open_custom_modal(
                _("添加机型"),
                [
                    name_field,
                    desc_field,
                    ft.Row(spacing=8, controls=[sim_dd, plat_dd]),
                    ft.Row(spacing=8, controls=[cycle_dir_field, browse_cycle_dir_btn]),
                    ft.Text(_("请直接选择包含 cycle.json 的目录。"), size=fs(11), color=colors["text_meta"]),
                    err,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton(_("取消"), on_click=close_dialog),
                            ft.Button(_("保存"), bgcolor="#1a73e8", color="#ffffff", on_click=save_click),
                        ],
                    ),
                ],
                width=780,
            )
        except Exception as exc:
            snack(_("打开添加机型失败: {exc}", exc=exc))

    def on_backup_power_click(_e):
        try:
            user_field = ft.TextField(
                label=_("账号"),
                value=str(state.get("backup_power_username", "")).strip(),
                expand=True,
            )
            pass_field = ft.TextField(
                label=_("密码"),
                value=decrypt_secret(str(state.get("backup_power_password_enc", ""))),
                password=True,
                can_reveal_password=True,
                expand=True,
            )
            result_text = ft.Text("", size=fs(12), color=colors["text_sub"], selectable=True)
            err_text = ft.Text("", size=fs(12), color="#b83d4b")
            input_notice_text = ft.Text("", size=fs(11), color=colors["text_meta"])
            dlg: ft.Control | None = None
            login_inflight = False
            login_btn: ft.Button
            save_btn: ft.TextButton

            def keep_ascii_printable(text: str) -> str:
                return "".join(ch for ch in str(text or "") if 32 <= ord(ch) <= 126)

            def apply_english_only(field: ft.TextField, field_name: str) -> None:
                original = str(field.value or "")
                filtered = keep_ascii_printable(original)
                if original == filtered:
                    return
                field.value = filtered
                input_notice_text.value = _("{field_name}仅支持英文字符，已自动过滤非英文输入。", field_name=field_name)
                if not try_control_update(dlg):
                    page.update()

            def on_user_change(_evt=None) -> None:
                apply_english_only(user_field, _("账号"))

            def on_pass_change(_evt=None) -> None:
                apply_english_only(pass_field, _("密码"))

            user_field.on_change = on_user_change
            pass_field.on_change = on_pass_change

            def set_auth_dialog_busy(busy: bool) -> None:
                login_btn.disabled = busy
                login_btn.content = _("登录中...") if busy else _("登录")
                save_btn.disabled = busy
                if not try_control_update(dlg):
                    page.update()

            def close_dialog(_evt=None) -> None:
                close_custom_modal()

            def save_backup_power_settings() -> Path:
                user = user_field.value.strip()
                if not user:
                    raise ValueError(_("请填写账号。"))
                download_dir_path = ensure_backup_power_download_dir(str(default_backup_power_download_dir(state)), create=True)
                state["backup_power_download_dir"] = str(download_dir_path)
                state["backup_power_api_url"] = BACKUP_POWER_LOGIN_URL
                state["backup_power_username"] = user
                save_state(state)
                return download_dir_path

            def save_only(_evt) -> None:
                if login_inflight:
                    err_text.value = _("登录请求进行中，请稍候。")
                    if not try_control_update(dlg):
                        page.update()
                    return
                try:
                    save_backup_power_settings()
                except Exception as exc:
                    err_text.value = str(exc)
                    if not try_control_update(dlg):
                        page.update()
                    return
                err_text.value = ""
                result_text.value = _("配置已保存。")
                if not try_control_update(dlg):
                    page.update()

            def clear_saved_backup_power_token() -> None:
                state["backup_power_token"] = ""
                state["backup_power_refresh_token"] = ""
                save_state(state)
                set_backup_power_login_valid(False)

            async def try_reuse_saved_token(show_busy: bool, close_on_success: bool) -> bool:
                nonlocal login_inflight
                saved_token = str(state.get("backup_power_token", "")).strip()
                saved_user = str(state.get("backup_power_username", "")).strip()
                current_user = user_field.value.strip()
                if not saved_token:
                    set_backup_power_login_valid(False)
                    return False
                if current_user and saved_user and current_user != saved_user:
                    return False
                if show_busy:
                    login_inflight = True
                    set_auth_dialog_busy(True)
                err_text.value = ""
                result_text.value = _("正在检查已保存的 DATA Token...")
                if not try_control_update(dlg):
                    page.update()
                try:
                    result = await run_blocking_with_feedback(
                        backup_power_me_request,
                        saved_token,
                        message=_("正在校验已保存的 DATA Token"),
                        pulse_interval=0.8,
                        show_page_loading=False,
                        show_operation_dialog_ui=False,
                    )
                    token_len = len(saved_token)
                    result_text.value = (
                        "已复用有效的 DATA Token\n"
                        f"HTTP: {result.get('status', 200)}\n"
                        f"Token 长度: {token_len}\n"
                        f"登录时间: {state.get('backup_power_last_login_at', '--') or '--'}"
                    )
                    snack(_("已检测到有效 DATA Token，无需重新登录"))
                    set_backup_power_login_valid(True)
                    if not try_control_update(dlg):
                        page.update()
                    if close_on_success:
                        close_dialog()
                    return True
                except Exception as exc:
                    detail = str(exc).strip()
                    invalid_hints = ("invalid token", "token", "authorization", "unauthorized", "missing authorization")
                    if any(hint in detail.lower() for hint in invalid_hints):
                        clear_saved_backup_power_token()
                        result_text.value = ""
                        err_text.value = _("已保存的 DATA Token 已失效，请重新登录。")
                    else:
                        result_text.value = ""
                        err_text.value = _("校验 DATA Token 失败: {exc}", exc=exc)
                    set_backup_power_login_valid(False)
                    if not try_control_update(dlg):
                        page.update()
                    return False
                finally:
                    if show_busy:
                        login_inflight = False
                        set_auth_dialog_busy(False)

            def do_login(_evt) -> None:
                nonlocal login_inflight
                if login_inflight:
                    err_text.value = _("登录请求进行中，请稍候。")
                    if not try_control_update(dlg):
                        page.update()
                    return

                api = BACKUP_POWER_LOGIN_URL
                user = user_field.value.strip()
                pwd = pass_field.value
                async def runner() -> None:
                    nonlocal login_inflight
                    reused = await try_reuse_saved_token(show_busy=True, close_on_success=True)
                    if reused:
                        return
                    if not user:
                        err_text.value = _("请填写账号。")
                        if not try_control_update(dlg):
                            page.update()
                        return
                    if not pwd:
                        err_text.value = _("请填写密码。")
                        if not try_control_update(dlg):
                            page.update()
                        return
                    try:
                        save_backup_power_settings()
                    except Exception as exc:
                        err_text.value = str(exc)
                        if not try_control_update(dlg):
                            page.update()
                        return

                    login_inflight = True
                    set_auth_dialog_busy(True)
                    # Ensure no stale global progress dialog blocks this auth dialog.
                    close_operation_dialog()
                    err_text.value = ""
                    result_text.value = _("正在登录...")
                    if not try_control_update(dlg):
                        page.update()

                    try:
                        result = await run_blocking_with_feedback(
                            backup_power_login_request,
                            api,
                            user,
                            pwd,
                            message=_("正在登录"),
                            pulse_interval=0.8,
                            show_page_loading=False,
                            show_operation_dialog_ui=False,
                        )
                        state["backup_power_api_url"] = BACKUP_POWER_LOGIN_URL
                        state["backup_power_username"] = user
                        state["backup_power_password_enc"] = encrypt_secret(pwd)
                        state["backup_power_token"] = str(result.get("token", "")).strip()
                        state["backup_power_refresh_token"] = str(result.get("refresh_token", "")).strip()
                        state["backup_power_last_login_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        save_state(state)
                        set_backup_power_login_valid(True)
                        token_len = len(state["backup_power_token"])
                        result_text.value = (
                            f"登录成功\n"
                            f"HTTP: {result.get('status', 200)}\n"
                            f"消息: {result.get('message', 'OK')}\n"
                            f"Token 长度: {token_len}\n"
                            f"登录时间: {state['backup_power_last_login_at']}"
                        )
                        snack(_("账号登录成功"))
                        if not try_control_update(dlg):
                            page.update()
                        close_dialog()
                    except Exception as exc:
                        result_text.value = ""
                        err_text.value = _("登录失败: {exc}", exc=exc)
                        set_backup_power_login_valid(False)
                        if not try_control_update(dlg):
                            page.update()
                    finally:
                        login_inflight = False
                        set_auth_dialog_busy(False)

                try:
                    page.run_task(runner)
                except Exception as exc:
                    login_inflight = False
                    set_auth_dialog_busy(False)
                    err_text.value = _("启动登录失败: {exc}", exc=exc)
                    if not try_control_update(dlg):
                        page.update()

            token_mask = str(state.get("backup_power_token", "")).strip()
            if token_mask:
                token_mask = f"{token_mask[:4]}...{token_mask[-4:]}" if len(token_mask) > 10 else "***"
            else:
                token_mask = _("未登录")
            last_login = str(state.get("backup_power_last_login_at", "")).strip() or "--"
            save_btn = ft.TextButton(_("保存配置"), on_click=save_only)
            login_btn = ft.Button(_("登录"), bgcolor="#1a73e8", color="#ffffff", on_click=do_login)

            dlg = custom_modal_container
            open_custom_modal(
                _("登录系统"),
                [
                    ft.Text(_("账号登录"), size=fs(14), weight=ft.FontWeight.W_700, color=colors["text_title"]),
                    ft.Row(spacing=8, controls=[user_field, pass_field]),
                    ft.Text(_("账号和密码仅支持英文字符（ASCII）。"), size=fs(11), color=colors["text_sub"]),
                    input_notice_text,
                    
                    ft.Text(_("当前 Token: {token_mask}    上次登录: {last_login}", token_mask=token_mask, last_login=last_login), size=fs(11), color=colors["text_sub"]),
                    err_text,
                    result_text,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton(_("关闭"), on_click=close_dialog),
                            save_btn,
                            login_btn,
                        ],
                    ),
                ],
                width=820,
            )
            if str(state.get("backup_power_token", "")).strip():
                page.run_task(try_reuse_saved_token, False, True)
        except Exception as exc:
            snack(_("登录失败: {exc}", exc=exc))

    def on_wasm_paths_click(_e):
        try:
            key = community_key(simulator, platform)
            custom_paths = custom_wasm_scan_paths(state, simulator, platform)
            default_bases = wasm_base_candidates(simulator, platform, None)
            default_scan_bases = cycle_json_scan_bases(simulator, platform, None)
            custom_field = ft.TextField(
                label=_("自定义扫描目录（每行一个，优先于默认路径）"),
                multiline=True,
                min_lines=5,
                max_lines=8,
                value="\n".join(custom_paths),
            )
            err = ft.Text("", size=fs(12), color="#b83d4b")
            dlg: ft.Control | None = None

            for ctrl in list(page.services):
                if isinstance(ctrl, ft.FilePicker) and getattr(ctrl, "data", None) == "wasm_scan_picker":
                    try:
                        page.services.remove(ctrl)
                    except ValueError:
                        pass
            picker = ft.FilePicker()
            picker.data = "wasm_scan_picker"
            page.services.append(picker)

            def close_dialog(_evt=None) -> None:
                close_custom_modal()

            def browse_dir(_evt) -> None:
                async def runner() -> None:
                    try:
                        path = await picker.get_directory_path(dialog_title=_("选择自定义 WASM 扫描目录"))
                        if not path:
                            return
                        line = path.strip()
                        lines = [x.strip() for x in custom_field.value.splitlines() if x.strip()]
                        if line not in lines:
                            lines.append(line)
                            custom_field.value = "\n".join(lines)
                            page.update()
                    except Exception as exc:
                        err.value = _("选择目录失败: {exc}", exc=exc)
                        page.update()

                page.run_task(runner)

            def save_click(_evt) -> None:
                raw_lines = [line.strip() for line in custom_field.value.splitlines() if line.strip()]
                normalized = _normalize_path_list(raw_lines)
                invalid = [p for p in normalized if not Path(p).exists() or not Path(p).is_dir()]
                if invalid:
                    err.value = f"以下目录不存在或不可用: {invalid[0]}"
                    page.update()
                    return
                state.setdefault("wasm_scan_paths", {})[key] = normalized
                save_state(state)
                clear_cycle_json_scan_cache()
                close_dialog()
                snack(_("WASM 路径已保存: {simulator} / {platform}", simulator=simulator, platform=platform))
                trigger_rebuild(show_loading=True)

            def clear_click(_evt) -> None:
                state.setdefault("wasm_scan_paths", {}).pop(key, None)
                save_state(state)
                clear_cycle_json_scan_cache()
                custom_field.value = ""
                err.value = ""
                page.update()
                snack(_("已清空自定义 WASM 路径: {simulator} / {platform}", simulator=simulator, platform=platform))
                trigger_rebuild(show_loading=True)

            dlg = custom_modal_container
            open_custom_modal(
                _("WASM 路径"),
                [
                    ft.Text(_("当前配置: {simulator} / {platform}", simulator=simulator, platform=platform), size=fs(12), color=colors["text_sub"]),
                    custom_field,
                    ft.Row(spacing=8, controls=[ft.Button(_("浏览并添加"), on_click=browse_dir)]),
                    ft.Text(_("默认 WASM 候选路径:"), size=fs(12), color=colors["text_meta"]),
                    ft.Text("\n".join(f"- {line}" for line in default_bases), size=fs(11), selectable=True),
                    ft.Text(_("默认 cycle.json 扫描根路径:"), size=fs(12), color=colors["text_meta"]),
                    ft.Text("\n".join(f"- {line}" for line in default_scan_bases), size=fs(11), selectable=True),
                    err,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton(_("清空自定义"), on_click=clear_click),
                            ft.TextButton(_("取消"), on_click=close_dialog),
                            ft.Button(_("保存"), bgcolor="#1a73e8", color="#ffffff", on_click=save_click),
                        ],
                    ),
                ],
                width=860,
            )
        except Exception as exc:
            snack(_("读取 WASM 路径失败: {exc}", exc=exc))

    def on_log_click(_e):
        try:
            snack(_("打开日志"))
            open_log_overlay()
        except Exception as exc:
            snack(_("打开日志失败: {exc}", exc=exc))

    def on_install_status_click(_e):
        try:
            open_install_overlay()
        except Exception as exc:
            snack(_("打开安装状态失败: {exc}", exc=exc))

    def set_backup_power_login_valid(valid: bool) -> None:
        nonlocal backup_power_login_valid
        was_valid = backup_power_login_valid
        backup_power_login_valid = bool(valid)
        if one_click_install_filter_button is not None:
            one_click_install_filter_button.visible = backup_power_login_valid
            one_click_install_filter_button.disabled = not backup_power_login_valid
            update_controls(one_click_install_filter_button)
        if backup_power_login_button is not None:
            backup_power_login_button.visible = not backup_power_login_valid
            backup_power_login_button.disabled = backup_power_login_valid
            update_controls(backup_power_login_button)
        if cycle_picker_button is not None:
            cycle_picker_button.visible = backup_power_login_valid
            cycle_picker_button.disabled = not backup_power_login_valid
            update_controls(cycle_picker_button)
        if backup_power_login_valid and not was_valid:
            page.run_task(refresh_cycle_dropdown_options)

    def render_cycle_picker_trigger() -> None:
        if cycle_picker_container is None:
            return
        style = str(state.get("cycle_picker_style", "") or "capsule").strip()
        if style not in {"capsule", "icon", "long", "flat"}:
            style = "capsule"
        cur = cycle_dropdown_value or "--"
        is_latest = bool(cycle_dropdown_options_cache) and cur == cycle_dropdown_options_cache[0]
        is_dark = theme_name == THEME_DARK
        pill_bg = "#243247" if is_dark else "#ffffff"
        pill_border = "#3a4d6e" if is_dark else "#dadce0"
        pill_text = "#eef4ff" if is_dark else "#1a1f2e"
        pill_sub = "#9bb2cf" if is_dark else "#5f6368"
        pill_accent = "#8ab4ff" if is_dark else "#1a73e8"

        if style == "capsule":
            cycle_picker_container.bgcolor = pill_bg
            cycle_picker_container.border = ft.Border.all(1, pill_border)
            cycle_picker_container.border_radius = 999
            cycle_picker_container.padding = ft.Padding.symmetric(horizontal=14, vertical=6)
            latest_badge = ft.Container(
                bgcolor="#1958c4",
                border_radius=999,
                padding=ft.Padding.symmetric(horizontal=6, vertical=1),
                content=ft.Text(_("最新"), size=9, weight=ft.FontWeight.W_700, color="#ffffff"),
                visible=is_latest,
            )
            cycle_picker_container.content = ft.Row(spacing=8, tight=True, controls=[
                ft.Icon(ft.Icons.CALENDAR_MONTH, size=14, color=pill_accent),
                ft.Text(_("期数 · {cur}", cur=cur), size=12, weight=ft.FontWeight.W_600, color=pill_text),
                latest_badge,
                ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=16, color=pill_sub),
            ])
        elif style == "icon":
            cycle_picker_container.bgcolor = pill_bg
            cycle_picker_container.border = ft.Border.all(1, pill_border)
            cycle_picker_container.border_radius = 10
            cycle_picker_container.padding = ft.Padding.symmetric(horizontal=10, vertical=5)
            cycle_picker_container.content = ft.Row(spacing=6, tight=True, controls=[
                ft.Icon(ft.Icons.EVENT_NOTE, size=16, color=pill_accent),
                ft.Text(cur, size=11, color=pill_text),
                ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=pill_sub),
            ])
        elif style == "long":
            cycle_picker_container.bgcolor = pill_bg
            cycle_picker_container.border = ft.Border.all(1, pill_border)
            cycle_picker_container.border_radius = 10
            cycle_picker_container.padding = ft.Padding.symmetric(horizontal=12, vertical=6)
            label_text = f"导航周期  ▾  {cur}{_("（最新）") if is_latest else ''}"
            cycle_picker_container.content = ft.Text(label_text, size=12, weight=ft.FontWeight.W_600, color=pill_text)
        else:  # flat
            cycle_picker_container.bgcolor = pill_bg
            cycle_picker_container.border = ft.Border.all(1, pill_border)
            cycle_picker_container.border_radius = 8
            cycle_picker_container.padding = ft.Padding.symmetric(horizontal=12, vertical=4)
            cycle_picker_container.content = ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Column(spacing=0, tight=True, controls=[
                        ft.Text(_("期数"), size=10, color=pill_sub),
                        ft.Text(f"{cur}{_("（最新）") if is_latest else ''}", size=12, color=pill_text),
                    ]),
                    ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=16, color=pill_sub),
                ],
            )
        if cycle_picker_button is not None:
            try:
                if cycle_picker_button.page is not None:
                    update_controls(cycle_picker_button)
            except RuntimeError:
                pass

    def rebuild_cycle_picker_items() -> None:
        if cycle_picker_button is None:
            return
        latest = cycle_dropdown_options_cache[0] if cycle_dropdown_options_cache else ""

        def make_item(c: str) -> ft.PopupMenuItem:
            is_current = c == cycle_dropdown_value
            is_latest = c == latest
            is_dark = theme_name == THEME_DARK
            item_text_color = "#ffffff" if is_dark else "#000000"
            row_controls: list[ft.Control] = [
                ft.Icon(
                    ft.Icons.CHECK if is_current else ft.Icons.RADIO_BUTTON_UNCHECKED,
                    size=14,
                    color="#8ab4ff" if is_current else ("#9bb2cf" if is_dark else "#9aa6b8"),
                ),
                ft.Text(c, size=13,
                        weight=ft.FontWeight.W_700 if is_current else ft.FontWeight.W_500,
                        color=item_text_color),
            ]
            if is_latest:
                row_controls.append(
                    ft.Container(
                        bgcolor="#1958c4",
                        border_radius=999,
                        padding=ft.Padding.symmetric(horizontal=6, vertical=1),
                        content=ft.Text(_("最新"), size=9, weight=ft.FontWeight.W_700, color="#ffffff"),
                    )
                )
            return ft.PopupMenuItem(
                content=ft.Container(
                    padding=ft.Padding.symmetric(horizontal=4, vertical=4),
                    content=ft.Row(spacing=8, tight=True, controls=row_controls),
                ),
                on_click=lambda _e, cc=c: pick_cycle(cc),
            )

        cycle_picker_button.items = [make_item(c) for c in cycle_dropdown_options_cache]
        try:
            if cycle_picker_button.page is not None:
                update_controls(cycle_picker_button)
        except RuntimeError:
            pass

    def pick_cycle(c: str) -> None:
        nonlocal cycle_dropdown_value
        cycle_dropdown_value = str(c or "").strip()
        state["selected_install_cycle"] = cycle_dropdown_value
        save_state(state)
        render_cycle_picker_trigger()
        rebuild_cycle_picker_items()

    def show_cycle_picker_style_wizard(force: bool = False) -> None:
        if not force and str(state.get("cycle_picker_style", "")).strip() in {"capsule", "icon", "long", "flat"}:
            return

        overlay_holder = {"container": None}

        def close():
            container = overlay_holder.get("container")
            if container is not None:
                try:
                    if container in page.overlay:
                        page.overlay.remove(container)
                except Exception:
                    pass
                try:
                    container.visible = False
                except Exception:
                    pass
            try:
                page.update()
            except Exception:
                pass

        def pick(style: str):
            state["cycle_picker_style"] = style
            save_state(state)
            try:
                render_cycle_picker_trigger()
            except Exception:
                pass
            try:
                rebuild_cycle_picker_items()
            except Exception:
                pass
            close()

        sample_cur = "2502"

        def make_sample(style: str) -> ft.Control:
            if style == "capsule":
                return ft.Container(
                    bgcolor="#0f2444", border=ft.Border.all(1, "#21324c"), border_radius=999,
                    padding=ft.Padding.symmetric(horizontal=14, vertical=6),
                    content=ft.Row(spacing=8, tight=True, controls=[
                        ft.Icon(ft.Icons.CALENDAR_MONTH, size=14, color="#7fb3ff"),
                        ft.Text(_("期数 · {sample_cur}", sample_cur=sample_cur), size=12, weight=ft.FontWeight.W_600, color="#cdd9ef"),
                        ft.Container(bgcolor="#1958c4", border_radius=999,
                                     padding=ft.Padding.symmetric(horizontal=6, vertical=1),
                                     content=ft.Text(_("最新"), size=9, weight=ft.FontWeight.W_700, color="#ffffff")),
                        ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=16, color="#8ea3c7"),
                    ]),
                )
            if style == "icon":
                return ft.Container(
                    bgcolor="#0f2444", border=ft.Border.all(1, "#21324c"), border_radius=10,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=5),
                    content=ft.Row(spacing=6, tight=True, controls=[
                        ft.Icon(ft.Icons.EVENT_NOTE, size=16, color="#7fb3ff"),
                        ft.Text(sample_cur, size=11, color="#cdd9ef"),
                        ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color="#8ea3c7"),
                    ]),
                )
            if style == "long":
                return ft.Container(
                    bgcolor="#1958c4", border=ft.Border.all(1, "#2a5ca0"), border_radius=10,
                    padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                    content=ft.Text(_("导航周期  ▾  {sample_cur}（最新）", sample_cur=sample_cur), size=12, weight=ft.FontWeight.W_600, color="#ffffff"),
                )
            return ft.Container(
                bgcolor="#0f2444", border=ft.Border.all(1, "#21324c"), border_radius=8,
                padding=ft.Padding.symmetric(horizontal=12, vertical=4),
                content=ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[
                    ft.Column(spacing=0, tight=True, controls=[
                        ft.Text(_("期数"), size=10, color="#8ea3c7"),
                        ft.Text(_("{sample_cur}（最新）", sample_cur=sample_cur), size=12, color="#cdd9ef"),
                    ]),
                    ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=16, color="#8ea3c7"),
                ]),
            )

        def card(title: str, desc: str, style: str) -> ft.Control:
            return ft.OutlinedButton(
                on_click=lambda _e, s=style: pick(s),
                style=ft.ButtonStyle(
                    bgcolor=colors["card_bg"],
                    side=ft.BorderSide(1, "#21324c"),
                    shape=ft.RoundedRectangleBorder(radius=14),
                    padding=ft.Padding.symmetric(horizontal=14, vertical=14),
                ),
                content=ft.Column(spacing=10, tight=True, controls=[
                    ft.Text(title, size=14, weight=ft.FontWeight.BOLD, color=colors["text_title"]),
                    ft.Text(desc, size=11, color=colors["text_meta"]),
                    ft.Row(controls=[make_sample(style)]),
                ]),
            )

        panel = ft.Container(
            width=760,
            bgcolor=colors["panel_bg"],
            border=ft.Border.all(1, "#2f3c52"),
            border_radius=22,
            padding=20,
            content=ft.Column(spacing=14, tight=True, controls=[
                ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[
                    ft.Text(_("选择期数选择器风格"), size=18, weight=ft.FontWeight.BOLD, color=colors["text_title"]),
                    ft.IconButton(icon=ft.Icons.CLOSE, on_click=lambda _e: close()),
                ]),
                ft.Text(_("点击下面任一卡片，将作为顶部期数选择控件的样式（可随时在设置里更改）。"),
                        size=12, color=colors["text_sub"]),
                ft.Row(spacing=12, controls=[
                    card(_("胶囊（推荐）"), _("圆角胶囊 + 日历图标 + 最新徽章。"), "capsule"),
                    card(_("紧凑图标"), _("最省空间，图标 + 期号。"), "icon"),
                ]),
                ft.Row(spacing=12, controls=[
                    card(_("醒目蓝按钮"), _("突出选择动作。"), "long"),
                    card(_("扁平表单风"), _("上方有「期数」小标签。"), "flat"),
                ]),
                ft.Row(alignment=ft.MainAxisAlignment.END, controls=[
                    ft.TextButton(_("稍后再选"), on_click=lambda _e: pick("capsule")),
                ]),
            ]),
        )

        overlay = ft.Container(
            expand=True,
            bgcolor="#000000c0",
            alignment=ft.Alignment.CENTER,
            content=panel,
            left=0, top=0, right=0, bottom=0,
        )
        overlay_holder["container"] = overlay
        try:
            page.overlay.append(overlay)
            page.update()
        except Exception as exc:
            log(_("打开风格向导失败：{exc}", exc=exc))

    async def refresh_cycle_dropdown_options() -> None:
        nonlocal cycle_dropdown_options_cache, cycle_dropdown_value
        if cycle_picker_button is None:
            return
        try:
            items = await asyncio.to_thread(openlist_list_dir_auto_request, OPENLIST_ROOT_PATH)
        except Exception as exc:
            log(_("获取 OpenList 期数列表失败: {exc}", exc=exc))
            return
        cycle_dirs: list[str] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            if not bool(item.get("is_dir")):
                continue
            name = str(item.get("name", "")).strip()
            if not name or not re.fullmatch(r"\d{4}", name):
                continue
            cycle_dirs.append(name)

        async def has_msfs(cycle_id: str) -> bool:
            try:
                sub = await asyncio.to_thread(openlist_list_dir_auto_request, openlist_cycle_path(cycle_id))
            except Exception:
                return False
            for it in sub or []:
                if not isinstance(it, dict):
                    continue
                if bool(it.get("is_dir")) and str(it.get("name", "")).strip().lower() == "msfs":
                    return True
            return False

        checks = await asyncio.gather(*[has_msfs(c) for c in cycle_dirs], return_exceptions=True)
        with_msfs = [c for c, ok in zip(cycle_dirs, checks) if ok is True]
        with_msfs.sort(reverse=True)
        cycle_dropdown_options_cache = with_msfs
        saved = str(state.get("selected_install_cycle", "")).strip()
        if saved in with_msfs:
            cycle_dropdown_value = saved
        elif with_msfs:
            cycle_dropdown_value = with_msfs[0]
        else:
            cycle_dropdown_value = ""
        render_cycle_picker_trigger()
        rebuild_cycle_picker_items()

    async def confirm_non_latest_cycle(target_cycle: str) -> bool:
        target_cycle = (target_cycle or "").strip()
        if not target_cycle:
            return True
        latest = cycle_dropdown_options_cache[0] if cycle_dropdown_options_cache else ""
        if not latest or target_cycle == latest:
            return True
        result_future: asyncio.Future[bool] = asyncio.get_event_loop().create_future()

        def _yes():
            if not result_future.done():
                result_future.set_result(True)

        def _no():
            if not result_future.done():
                result_future.set_result(False)

        show_confirm_dialog(
            _("确认安装非最新期数"),
            _("当前选择的期数为 {target_cycle}，并非最新期数 {latest}。\n确定要继续安装非最新期数的导航数据吗？", target_cycle=target_cycle, latest=latest),
            on_yes=_yes,
            on_no=_no,
        )
        return await result_future

    async def refresh_backup_power_login_validity(notify_invalid: bool = False) -> bool:
        token = str(state.get("backup_power_token", "")).strip()
        if not token:
            set_backup_power_login_valid(False)
            return False
        try:
            await asyncio.to_thread(backup_power_me_request, token)
            set_backup_power_login_valid(True)
            return True
        except Exception as exc:
            log(_("DATA token 校验失败: {exc}", exc=exc))
            set_backup_power_login_valid(False)
            if notify_invalid:
                snack(_("登录状态已失效，请重新登录。"))
            return False

    def on_one_click_install_click(e):
        button = e.control if isinstance(getattr(e, "control", None), ft.Button) else None
        if is_button_busy(button):
            open_install_overlay(title=install_overlay_title_text or _("安装状态"), reset=False)
            snack(_("一键安装仍在后台执行，已打开安装状态。"))
            return
        reset_operation_dialog_suppression()
        set_button_busy(button, True, _("执行中..."))

        async def runner() -> None:
            try:
                login_ok = await refresh_backup_power_login_validity(notify_invalid=True)
                if not login_ok:
                    snack(_("登录已失效，一键安装不可用，请重新登录或使用「从本地安装」。"))
                    return
                scoped_addons = [a for a in addons_all if a.simulator == simulator and a.platform == platform]
                if not scoped_addons:
                    snack(_("当前模拟器/平台没有可更新的机型。"))
                    return

                fallback_cycle = ""
                chosen_cycle = (cycle_dropdown_value or "").strip()
                if chosen_cycle:
                    fallback_cycle = detect_airac(chosen_cycle)
                if fallback_cycle in {"", "UNKNOWN"} and current_cycle_info and current_cycle_info.get("cycle_id"):
                    fallback_cycle = detect_airac(str(current_cycle_info.get("cycle_id", "")))
                if fallback_cycle in {"", "UNKNOWN"}:
                    cycle_info = await asyncio.to_thread(fetch_current_cycle)
                    if cycle_info and cycle_info.get("cycle_id"):
                        fallback_cycle = detect_airac(str(cycle_info.get("cycle_id", "")))
                if fallback_cycle in {"", "UNKNOWN"}:
                    snack(_("未获取到有效 AIRAC 期数，无法执行一键安装。"))
                    return

                if chosen_cycle and detect_airac(chosen_cycle) == fallback_cycle:
                    ok = await confirm_non_latest_cycle(fallback_cycle)
                    if not ok:
                        append_install_overlay_line(_("已取消一键安装。"))
                        snack(_("已取消一键安装。"))
                        return

                open_install_overlay(title=_("安装状态 - 一键安装 {simulator} / {platform}", simulator=simulator, platform=platform), reset=True)
                append_install_overlay_line(_("一键安装开始: {simulator} / {platform}", simulator=simulator, platform=platform))
                append_install_overlay_line(_("默认期数: {fallback_cycle}", fallback_cycle=fallback_cycle))

                total = len(scoped_addons)
                success_count = 0
                failed_count = 0
                uninstalled_count = 0
                up_to_date_skip_count = 0
                skipped_count = 0
                cloud_no_data_addons: list[str] = []
                cloud_no_data_seen: set[str] = set()

                install_jobs: list[tuple[Addon, Path, str, int]] = []
                for idx, addon in enumerate(scoped_addons, start=1):
                    if not is_default_catalog_addon(addon):
                        skipped_count += 1
                        append_install_overlay_line(f"[{idx}/{total}] {addon.name}: 跳过（手动添加机型需手动选包）")
                        continue
                    target = resolve_target_dir(addon, state)
                    if target is None:
                        target = resolve_wasm_target_by_folder_name(addon, state)
                    if target is None:
                        uninstalled_count += 1
                        append_install_overlay_line(f"[{idx}/{total}] {addon.name}: 未安装（跳过）")
                        continue
                    if target.exists() and not target.is_dir():
                        failed_count += 1
                        append_install_overlay_line(f"[{idx}/{total}] {addon.name}: 失败（目标路径不是目录）")
                        continue
                    if (not target.exists()) and (not target.parent.exists()):
                        failed_count += 1
                        append_install_overlay_line(f"[{idx}/{total}] {addon.name}: 失败（目标父目录不存在）")
                        continue
                    installed_cycle = detect_airac(read_cycle_from_dir(target))
                    if installed_cycle == fallback_cycle:
                        up_to_date_skip_count += 1
                        append_install_overlay_line(
                            f"[{idx}/{total}] {addon.name}: 已是最新周期 {installed_cycle}（跳过下载）"
                        )
                        continue
                    addon_cycle = selected_install_cycle_for_addon(addon, fallback_cycle)
                    install_jobs.append((addon, target, addon_cycle, idx))

                if not install_jobs:
                    summary = (
                        f"一键安装结束: 总计{total}，成功0，失败{failed_count}，未安装{uninstalled_count}，"
                        f"最新已安装{up_to_date_skip_count}，云盘无数据0，跳过{skipped_count}"
                    )
                    if uninstalled_count > 0:
                        append_install_overlay_line(_("未安装: {uninstalled_count}", uninstalled_count=uninstalled_count))
                    if up_to_date_skip_count > 0:
                        append_install_overlay_line(_("已是最新（跳过下载）: {up_to_date_skip_count}", up_to_date_skip_count=up_to_date_skip_count))
                    append_install_overlay_line(summary)
                    snack(summary)
                    return

                append_install_overlay_line(f"待下载队列: {len(install_jobs)} 个机型")
                for queue_idx, (addon, _target, addon_cycle, _source_idx) in enumerate(install_jobs, start=1):
                    append_install_overlay_line(f"[排队 {queue_idx}/{len(install_jobs)}] {addon.name}（期数 {addon_cycle}）")

                max_download_workers = normalize_batch_download_workers(
                    state.get("batch_download_workers", DEFAULT_BATCH_DOWNLOAD_WORKERS)
                )
                append_install_overlay_line(_("进入并发下载阶段（线程数: {max_download_workers}）", max_download_workers=max_download_workers))
                batch_download_root = default_batch_download_cache_dir(state)
                await asyncio.to_thread(batch_download_root.mkdir, parents=True, exist_ok=True)

                sem = asyncio.Semaphore(max_download_workers)

                def is_openlist_no_data_error(err_text: str) -> bool:
                    text = str(err_text or "").strip().lower()
                    if not text:
                        return False
                    hints = (
                        _("未找到与机型匹配的 openlist 压缩包"),
                        _("openlist 未找到期数目录"),
                        _("openlist 未找到 msfs 目录"),
                        _("openlist 未返回可用下载链接"),
                        _("目录读取失败 (404"),
                        _("文件信息读取失败 (404"),
                        "not found",
                    )
                    return any(h in text for h in hints)

                async def download_job(
                    addon: Addon,
                    target: Path,
                    cycle_id: str,
                    idx: int,
                ) -> tuple[Addon, Path, Path | None, str | None, str | None]:
                    safe_key = re.sub(r"[^a-zA-Z0-9._-]+", "_", addon_key(addon))
                    addon_download_dir = batch_download_root / safe_key
                    await asyncio.to_thread(addon_download_dir.mkdir, parents=True, exist_ok=True)
                    async with sem:
                        append_install_overlay_line(f"[{idx}/{total}] {addon.name}: 开始下载（期数 {cycle_id}）")
                        try:
                            result = await asyncio.to_thread(
                                download_openlist_archive_for_addon,
                                addon,
                                cycle_id,
                                addon_download_dir,
                                None,
                            )
                            archive_path = Path(str(result.get("archive_path", "")).strip())
                            if not archive_path.exists():
                                raise ValueError(_("下载结果文件不存在: {archive_path}", archive_path=archive_path))
                            append_install_overlay_line(f"[{idx}/{total}] {addon.name}: 下载完成 -> {archive_path.name}")
                            return addon, target, archive_path, None, None
                        except Exception as exc:
                            err = str(exc)
                            if is_openlist_no_data_error(err):
                                append_install_overlay_line(f"[{idx}/{total}] {addon.name}: 云盘中无数据")
                                return addon, target, None, err, "no_data"
                            append_install_overlay_line(f"[{idx}/{total}] {addon.name}: 下载失败 -> {err}")
                            return addon, target, None, err, "error"

                download_results = await asyncio.gather(
                    *[
                        download_job(addon, target, cycle_id, idx)
                        for addon, target, cycle_id, idx in install_jobs
                    ]
                )

                append_install_overlay_line(_("进入安装阶段（按顺序执行）"))
                for addon, target, archive_path, download_error, download_kind in download_results:
                    if download_error or archive_path is None:
                        if download_kind == "no_data":
                            if addon.name not in cloud_no_data_seen:
                                cloud_no_data_seen.add(addon.name)
                                cloud_no_data_addons.append(addon.name)
                            continue
                        failed_count += 1
                        continue
                    picked = [type("PickedFile", (), {"path": str(archive_path)})()]
                    ok = await on_archive_update_pick_result(
                        picked,
                        addon,
                        target,
                        show_result_dialog=False,
                        allow_force_prompt=False,
                        wait_for_completion=True,
                        reset_overlay=False,
                    )
                    if ok:
                        success_count += 1
                    else:
                        failed_count += 1

                summary = (
                    f"一键安装完成: 总计{total}，成功{success_count}，失败{failed_count}，未安装{uninstalled_count}，"
                    f"最新已安装{up_to_date_skip_count}，云盘无数据{len(cloud_no_data_addons)}，跳过{skipped_count}"
                )
                if uninstalled_count > 0:
                    append_install_overlay_line(_("未安装: {uninstalled_count}", uninstalled_count=uninstalled_count))
                if up_to_date_skip_count > 0:
                    append_install_overlay_line(_("已是最新（跳过下载）: {up_to_date_skip_count}", up_to_date_skip_count=up_to_date_skip_count))
                if cloud_no_data_addons:
                    append_install_overlay_line(f"云盘中无数据: {', '.join(cloud_no_data_addons)}")
                append_install_overlay_line(summary)
                snack(summary)
            except Exception as exc:
                append_install_overlay_line(_("一键安装异常: {exc}", exc=exc))
                snack(_("一键安装失败: {exc}", exc=exc))
            finally:
                try:
                    await asyncio.to_thread(shutil.rmtree, default_batch_download_cache_dir(state), True)
                except Exception:
                    pass
                set_button_busy(button, False)

        page.run_task(runner)

    def on_open_log_folder_click(_e):
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            open_folder(str(LOG_DIR))
        except Exception as exc:
            snack(_("打开日志文件夹失败: {exc}", exc=exc))

    def on_streamer_mode_click(_e):
        nonlocal streamer_mode
        streamer_mode = not streamer_mode
        state["streamer_mode"] = streamer_mode
        save_state(state)
        refresh_streamer_button()
        rebuild_lists(precomputed_entries=last_rendered_entries)

    def refresh_segment_visuals() -> None:
        for key, btn in sim_buttons.items():
            selected = key == simulator
            btn.bgcolor = "#7a47e8" if selected else colors["switch_unsel_bg"]
            btn.color = "#ffffff" if selected else colors["switch_unsel_fg"]
        for key, btn in platform_buttons.items():
            selected = key == platform
            btn.bgcolor = "#0f7ca8" if selected else colors["switch_unsel_bg"]
            btn.color = "#ffffff" if selected else colors["switch_unsel_fg"]
        for key, btn in theme_buttons.items():
            selected = key == theme_name
            btn.bgcolor = colors["filter_active_bg"] if selected else colors["switch_unsel_bg"]
            btn.color = colors["filter_active_fg"] if selected else colors["switch_unsel_fg"]

    streamer_button = build_top_action_button(_("显示路径") if streamer_mode else _("隐藏路径"), on_click=on_streamer_mode_click)
    msfs_status_badge = ft.Container(
        content=ft.Text(_("MSFS 未运行"), size=fs(11), color=colors["text_meta"], weight=ft.FontWeight.W_600),
        bgcolor=colors["panel_soft_bg"],
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        border_radius=12,
        tooltip=_("MSFS 在线状态（SimConnect / 进程探测）"),
    )

    def refresh_msfs_status_badge() -> None:
        try:
            import simconnect_status as _scs
            st = _scs.latest_status()
        except Exception:
            return
        label = st.headline()
        if st.connected:
            bg = colors["filter_active_bg"]
            fg = colors["filter_active_fg"]
        elif st.running:
            bg = "#7a47e8"
            fg = "#ffffff"
        else:
            bg = colors["panel_soft_bg"]
            fg = colors["text_meta"]
        msfs_status_badge.bgcolor = bg
        try:
            msfs_status_badge.content.value = label
            msfs_status_badge.content.color = fg
        except Exception:
            pass
        try:
            update_controls(msfs_status_badge)
        except Exception:
            pass
    backup_power_login_button = build_top_action_button(
        _("登录下载系统"),
        on_click=on_backup_power_click,
        icon=ft.Icons.AUTO_AWESOME,
        bgcolor=colors["filter_active_bg"],
        color=colors["filter_active_fg"],
    )
    one_click_install_filter_button = ft.Button(
        _("一键安装"),
        on_click=on_one_click_install_click,
        visible=False,
        height=30,
        bgcolor=colors["panel_soft_bg"],
        color=colors["text_meta"],
        style=ft.ButtonStyle(
            padding=ft.Padding.symmetric(horizontal=12, vertical=0),
            shape=ft.RoundedRectangleBorder(radius=14),
            text_style=ft.TextStyle(weight=ft.FontWeight.W_600),
        ),
    )
    cycle_picker_container = ft.Container(ink=True)
    cycle_picker_button = ft.PopupMenuButton(
        items=[],
        content=cycle_picker_container,
        visible=False,
        disabled=True,
    )
    render_cycle_picker_trigger()

    def refresh_streamer_button() -> None:
        setattr(streamer_button, "text", _("显示路径") if streamer_mode else _("隐藏路径"))
        if streamer_mode:
            streamer_button.bgcolor = colors["filter_active_bg"]
            streamer_button.color = colors["filter_active_fg"]
        else:
            streamer_button.bgcolor = colors["panel_bg"]
            streamer_button.color = colors["text_meta"]
        try:
            update_controls(streamer_button)
        except Exception:
            pass

    def set_sim(value: str) -> None:
        nonlocal simulator
        if value not in active_sims or value == simulator:
            return
        simulator = value
        state["simulator"] = simulator
        save_state(state)
        refresh_segment_visuals()
        trigger_rebuild(show_loading=True)

    def set_platform(value: str) -> None:
        nonlocal platform
        if value not in PLATFORMS or value == platform:
            return
        platform = value
        state["platform"] = platform
        save_state(state)
        refresh_segment_visuals()
        trigger_rebuild(show_loading=True)

    def on_filter_change(target_filter: str, rebuild: bool = True):
        nonlocal filter_value
        filter_value = target_filter
        for k, btn in filter_chips.items():
            if k == target_filter:
                btn.bgcolor = colors["filter_active_bg"]
                btn.color = colors["filter_active_fg"]
                btn.style = ft.ButtonStyle(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=0),
                    shape=ft.RoundedRectangleBorder(radius=14),
                    text_style=ft.TextStyle(weight=ft.FontWeight.W_700),
                )
            else:
                btn.bgcolor = colors["filter_bg"]
                btn.color = colors["filter_fg"]
                btn.style = ft.ButtonStyle(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=0),
                    shape=ft.RoundedRectangleBorder(radius=14),
                    text_style=ft.TextStyle(weight=ft.FontWeight.W_500),
                )
        if rebuild:
            trigger_rebuild(show_loading=True)

    def on_search_change(e: ft.Event[ft.TextField]) -> None:
        nonlocal search_text
        search_text = str(getattr(e.control, "value", "") or "")
        trigger_rebuild(show_loading=False)

    def set_theme(value: str) -> None:
        nonlocal theme_name
        if value not in (THEME_LIGHT, THEME_DARK) or value == theme_name:
            return
        theme_name = value
        state["theme"] = theme_name
        save_state(state)
        # Fast hot-reload: rebuild visual tree but reuse already fetched cycle data
        # and skip startup scans/network calls.
        last_cycle = current_cycle_info
        page.clean()
        main(page, fast_reload=True, cached_cycle=last_cycle)

    for key, btn in filter_chips.items():
        btn.on_click = lambda _e, k=key: on_filter_change(k)
        btn.bgcolor = colors["filter_bg"]
        btn.color = colors["filter_fg"]
        btn.height = 30
        btn.style = ft.ButtonStyle(
            padding=ft.Padding.symmetric(horizontal=12, vertical=0),
            shape=ft.RoundedRectangleBorder(radius=14),
        )

    airac_card = ft.Container(
        width=float("inf"),
        border_radius=20,
        bgcolor=colors["panel_bg"],
        padding=12,
        content=ft.Column(
            spacing=6,
            controls=[
                ft.Text(_("当前 AIRAC"), size=fs(14), weight=ft.FontWeight.W_600, color=colors["text_sub"]),
                airac_id_text,
                airac_effective_text,
                airac_next_text,
            ],
        ),
    )

    installed_card = ft.Container(
        expand=True,
        border_radius=20,
        bgcolor=colors["panel_bg"],
        padding=10,
        content=ft.Column(
            expand=True,
            spacing=8,
            controls=[
                ft.Text(_("已安装机型"), size=fs(14), weight=ft.FontWeight.W_600, color=colors["text_sub"]),
                left_list,
            ],
        ),
    )

    left = ft.Container(
        width=330,
        border_radius=20,
        bgcolor=colors["sidebar_bg"],
        padding=10,
        content=ft.Column(
            expand=True,
            controls=[
                airac_card,
                ft.Container(height=12),
                installed_card,
            ],
        ),
    )

    right_scroll_col = ft.Column(
        expand=True,
        spacing=6,
        scroll=ft.ScrollMode.AUTO,
        auto_scroll=False,
        controls=cast(list[ft.Control], [
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=cast(list[ft.Control], [
                        ft.Row(
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Image(
                                    src=str(APP_WINDOW_LOGO_FILE),
                                    width=34,
                                    height=34,
                                    fit=ft.BoxFit.CONTAIN,
                                ) if APP_WINDOW_LOGO_FILE.exists() else ft.Container(width=0, height=0),
                                ft.Column(
                                    spacing=1,
                                    controls=[
                                        ft.Text(_("AIRAC 周期管理器"), size=fs(26), weight=ft.FontWeight.BOLD, color=colors["text_title"]),
                                        ft.Text(_("为你的 MSFS 插件机型更新导航数据库"), size=fs(12), color=colors["text_sub"]),
                                    ],
                                ),
                                ft.Container(
                                    margin=ft.Margin.only(left=18),
                                    padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                                    border_radius=8,
                                    border=ft.Border.all(1, colors["text_meta"]),
                                    opacity=0.55,
                                    content=ft.Text(
                                        "本软件为免费软件，如您通过购买获得该软件，"
                                        "请联系 QQ: 168329908，提供您购买的渠道以及卖家详情。",
                                        size=fs(15),
                                        color=colors["text_meta"],
                                        selectable=True,
                                        max_lines=4,
                                    ),
                                    width=320,
                                ),
                            ],
                        ),
                        ft.Row(
                            spacing=6,
                            alignment=ft.MainAxisAlignment.END,
                            controls=[
                                ft.Column(
                                    spacing=4,
                                    horizontal_alignment=ft.CrossAxisAlignment.END,
                                    controls=[
                                        ft.Container(
                                            bgcolor=colors["switch_shell_bg"],
                                            border_radius=18,
                                            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                                            content=sim_segment_row,
                                        ),
                                        ft.Container(
                                            bgcolor=colors["switch_shell_bg"],
                                            border_radius=18,
                                            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                                            content=platform_segment_row,
                                        ),
                                        ft.Container(
                                            bgcolor=colors["switch_shell_bg"],
                                            border_radius=18,
                                            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                                            content=theme_segment_row,
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ]),
                ),
                ft.Container(
                    bgcolor=colors["panel_bg"],
                    border_radius=16,
                    padding=6,
                    content=ft.Row(
                        expand=True,
                        spacing=6,
                        controls=[
                            ft.Row(
                                spacing=6,
                                wrap=True,
                                controls=[
                                    backup_power_login_button,
                                    msfs_status_badge,
                                    build_top_action_button(_("设置"), on_click=on_settings_click),
                                    build_top_action_button(_("添加机型"), on_click=on_add_addon_click),
                                    build_top_action_button(_("重新扫描"), on_click=on_rescan_click),
                                    build_top_action_button(_("WASM 路径"), on_click=on_wasm_paths_click),
                                    build_top_action_button("LOG", on_click=on_log_click),
                                    build_top_action_button(_("安装状态"), on_click=on_install_status_click),
                                ],
                            ),
                            ft.Container(expand=True),
                            streamer_button,
                            build_top_action_button(
                                _("刷新周期"),
                                on_click=on_refresh_click,
                                icon=ft.Icons.REFRESH,
                            ),
                        ],
                    ),
                ),
                ft.TextField(
                    hint_text=_("搜索机型..."),
                    dense=True,
                    height=36,
                    border_radius=10,
                    content_padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                    on_change=on_search_change,
                ),
                ft.Row(spacing=6, wrap=True, controls=[*list(filter_chips.values()), one_click_install_filter_button, cycle_picker_button]),
                ft.Container(
                    expand=False,
                    border_radius=16,
                    bgcolor=colors["panel_bg"],
                    border=ft.Border.all(1, "#2f3c52"),
                    padding=12,
                    content=right_cards_list,
                ),
        ]),
    )

    right = ft.Container(
        expand=True,
        border_radius=20,
        bgcolor=colors["main_bg"],
        padding=12,
        content=right_scroll_col,
    )

    log_overlay_container.content = ft.Container(
        expand=True,
        bgcolor="#0c1220",
        alignment=ft.Alignment(0, 0),
        content=ft.Container(
            width=980,
            height=620,
            border_radius=22,
            bgcolor=colors["panel_bg"],
            border=ft.Border.all(1, "#2f3c52"),
            padding=16,
            content=ft.Column(
                expand=True,
                spacing=12,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column(
                                spacing=2,
                                controls=[
                                    log_overlay_title,
                                ],
                            ),
                            ft.Row(
                                spacing=8,
                                controls=[
                                    ft.Button(
                                        _("刷新"),
                                        icon=ft.Icons.REFRESH,
                                        bgcolor=colors["panel_soft_bg"],
                                        color=colors["text_meta"],
                                        on_click=lambda _e: (refresh_log_overlay(), update_controls(log_overlay_container)),
                                    ),
                                    ft.Button(
                                        _("打开日志文件夹"),
                                        icon=ft.Icons.FOLDER_OPEN,
                                        bgcolor=colors["panel_soft_bg"],
                                        color=colors["text_meta"],
                                        on_click=on_open_log_folder_click,
                                    ),
                                    ft.Button(
                                        _("关闭"),
                                        icon=ft.Icons.CLOSE,
                                        bgcolor="#b83d4b",
                                        color="#ffffff",
                                        on_click=close_log_overlay,
                                    ),
                                ],
                            ),
                        ],
                    ),
                    ft.Container(
                        expand=True,
                        border_radius=16,
                        bgcolor=colors["log_bg"],
                        padding=12,
                        content=log_overlay_list,
                    ),
                ],
            ),
        ),
    )

    custom_modal_panel.content = ft.Container(
        border_radius=22,
        bgcolor=colors["panel_bg"],
        border=ft.Border.all(1, "#2f3c52"),
        padding=16,
        content=ft.Column(
            tight=True,
            spacing=12,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        custom_modal_title,
                        ft.Button(
                            _("关闭"),
                            icon=ft.Icons.CLOSE,
                            bgcolor="#b83d4b",
                            color="#ffffff",
                            on_click=close_custom_modal,
                        ),
                    ],
                ),
                ft.Container(
                    content=custom_modal_body,
                ),
            ],
        ),
    )

    custom_modal_container.content = ft.Container(
        expand=True,
        bgcolor="#0c1220",
        alignment=ft.Alignment(0, 0),
        content=custom_modal_panel,
    )

    op_overlay_container.content = ft.Container(
        expand=True,
        bgcolor="#0c122088",
        alignment=ft.Alignment(0, 0),
        content=ft.Container(
            width=420,
            border_radius=20,
            bgcolor=colors["panel_bg"],
            border=ft.Border.all(1, "#2f3c52"),
            padding=16,
            content=ft.Column(
                tight=True,
                spacing=12,
                controls=[
                    op_dialog_title,
                    ft.Row(
                        spacing=10,
                        controls=[
                            ft.ProgressRing(width=24, height=24, stroke_width=3),
                            ft.Text(_("处理中"), size=fs(14), weight=ft.FontWeight.W_600),
                        ],
                    ),
                    op_dialog_status,
                    op_dialog_detail,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[op_hide_button],
                    ),
                ],
            ),
        ),
    )

    startup_update_skip_btn = ft.Button(
        _("跳过"),
        icon=ft.Icons.SKIP_NEXT,
        bgcolor=colors["panel_soft_bg"],
        color=colors["text_meta"],
        on_click=on_startup_update_skip,
        visible=False,
    )
    startup_update_download_btn = ft.Button(
        _("前往更新"),
        icon=ft.Icons.SYSTEM_UPDATE_ALT,
        bgcolor="#1a73e8",
        color="#ffffff",
        on_click=on_startup_update_download,
        visible=False,
    )
    startup_update_continue_btn = ft.Button(
        _("继续进入"),
        icon=ft.Icons.ARROW_FORWARD,
        bgcolor=colors["panel_soft_bg"],
        color=colors["text_meta"],
        on_click=on_startup_update_continue,
        visible=False,
    )

    startup_update_overlay_container.content = ft.Container(
        expand=True,
        bgcolor="#0c1220d8",
        alignment=ft.Alignment(0, 0),
        content=ft.Container(
            width=860,
            border_radius=22,
            bgcolor=colors["panel_bg"],
            border=ft.Border.all(1, "#2f3c52"),
            padding=18,
            content=ft.Column(
                tight=True,
                spacing=12,
                controls=[
                    startup_update_title,
                    startup_update_status,
                    startup_update_detail,
                    startup_update_countdown,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        spacing=8,
                        controls=[
                            startup_update_skip_btn,
                            startup_update_download_btn,
                            startup_update_continue_btn,
                        ],
                    ),
                ],
            ),
        ),
    )

    install_force_button = ft.Button(
        _("强制安装"),
        icon=ft.Icons.WARNING_AMBER_ROUNDED,
        bgcolor="#c67a00",
        color="#ffffff",
        visible=False,
        disabled=True,
        on_click=run_pending_force_install,
    )

    install_overlay_container.content = ft.Container(
        expand=True,
        bgcolor="#0c1220",
        alignment=ft.Alignment(0, 0),
        content=ft.Container(
            width=980,
            height=620,
            border_radius=22,
            bgcolor=colors["panel_bg"],
            border=ft.Border.all(1, "#2f3c52"),
            padding=16,
            content=ft.Column(
                expand=True,
                spacing=12,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column(
                                spacing=2,
                                controls=[
                                    install_overlay_title,
                                ],
                            ),
                            ft.Row(
                                spacing=8,
                                controls=[
                                    install_force_button,
                                    ft.Button(
                                        _("清空"),
                                        icon=ft.Icons.CLEAR_ALL,
                                        bgcolor=colors["panel_soft_bg"],
                                        color=colors["text_meta"],
                                        on_click=clear_install_overlay,
                                    ),
                                    ft.Button(
                                        _("关闭"),
                                        icon=ft.Icons.CLOSE,
                                        bgcolor="#b83d4b",
                                        color="#ffffff",
                                        on_click=close_install_overlay,
                                    ),
                                ],
                            ),
                        ],
                    ),
                    ft.Container(
                        expand=True,
                        border_radius=16,
                        bgcolor=colors["log_bg"],
                        padding=12,
                        content=install_overlay_list,
                    ),
                    install_progress_row,
                ],
            ),
        ),
    )

    scroll_top_button.content = ft.Container(
        width=52,
        height=52,
        border_radius=999,
        bgcolor="#ffffff",
        opacity=0.72,
        ink=True,
        on_click=on_scroll_top_click,
        shadow=ft.BoxShadow(blur_radius=18, spread_radius=1, color="#00000022"),
        content=ft.Icon(ft.Icons.KEYBOARD_ARROW_UP, color=colors["text_title"], size=28),
    )

    root_row = ft.Row(expand=True, controls=[left, right])
    page.add(
        ft.Stack(
            expand=True,
            controls=[
                root_row,
                ft.Container(
                    right=24,
                    bottom=24,
                    content=scroll_top_button,
                ),
                custom_modal_container,
                log_overlay_container,
                install_overlay_container,
                op_overlay_container,
                startup_update_overlay_container,
            ],
        )
    )

    refresh_streamer_button()
    refresh_segment_visuals()
    try:
        import simconnect_status as _scs
        _scs.start_status_worker(interval=2.5)
    except Exception:
        pass

    async def _msfs_status_loop() -> None:
        while True:
            try:
                refresh_msfs_status_badge()
            except Exception:
                pass
            await asyncio.sleep(2.5)

    try:
        page.run_task(_msfs_status_loop)
    except Exception:
        pass
    on_filter_change("All", rebuild=False)
    set_backup_power_login_valid(False)
    if not fast_reload:
        log("FMS UPDATE MANAGER  started.")
        airac_id_text.value = "..."
        airac_effective_text.value = _("本期数据生效日期：加载中...")
        airac_next_text.value = _("本期数据将于--月--日到期")
        show_loading_state(_("正在初始化..."))

        async def bootstrap() -> None:
            try:
                try:
                    cleanup_result = await asyncio.wait_for(
                        asyncio.to_thread(cleanup_stale_cache_entries, state),
                        timeout=20,
                    )
                    if cleanup_result.get("ran"):
                        save_state(state)
                        removed = int(cleanup_result.get("removed", 0))
                        days = int(cleanup_result.get("days", DEFAULT_CACHE_CLEANUP_DAYS))
                        log(_("缓存定期清理完成：清理周期 {days} 天，删除 {removed} 项过期缓存。", days=days, removed=removed))
                except TimeoutError:
                    log(_("缓存清理超时，已跳过。"))
                except Exception as exc:
                    log(_("缓存清理失败：{exc}", exc=exc))

                try:
                    await asyncio.wait_for(run_startup_update_check(), timeout=30)
                except TimeoutError:
                    log(_("启动更新检查超时，已跳过。"))
                except Exception as exc:
                    log(_("启动更新检查失败：{exc}", exc=exc))

                try:
                    from incremental_update import write_heartbeat as _wh
                    from state import PORTABLE_ROOT as _PR
                    if _PR is not None:
                        _install_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else _PR
                        _wh(_install_dir)
                except Exception as exc:
                    log(_("写入更新心跳失败：{exc}", exc=exc))

                try:
                    await asyncio.wait_for(refresh_backup_power_login_validity(notify_invalid=False), timeout=15)
                except TimeoutError:
                    log(_("DATA Token 校验超时，已跳过。"))

                if state.get("cycle_subscribe_enabled") and str(state.get("backup_power_token", "")).strip():
                    async def _trigger_cycle_check():
                        try:
                            await asyncio.to_thread(
                                backup_power_cycle_check_now,
                                str(state.get("backup_power_token", "")).strip(),
                            )
                        except Exception as exc:
                            log(_("AIRAC 订阅启动检查失败：{exc}", exc=exc))
                    try:
                        await asyncio.wait_for(_trigger_cycle_check(), timeout=10)
                    except TimeoutError:
                        log(_("AIRAC 订阅启动检查超时，已跳过。"))

                try:
                    show_cycle_picker_style_wizard(force=False)
                except Exception as exc:
                    log(_("期数选择器风格向导失败：{exc}", exc=exc))

                try:
                    await asyncio.wait_for(refresh_cycle_async(notify_fail=False), timeout=20)
                except TimeoutError:
                    log(_("AIRAC 刷新超时，已跳过。"))
                except Exception as exc:
                    log(_("AIRAC 刷新失败：{exc}", exc=exc))

                try:
                    await asyncio.wait_for(
                        rescan_and_rebuild_async(show_loading=False, notify_done=False),
                        timeout=120,
                    )
                except TimeoutError:
                    log(_("资源扫描超时，已跳过。"))
                except Exception as exc:
                    log(_("资源扫描失败：{exc}", exc=exc))
            finally:
                try:
                    await rebuild_lists_async(show_loading=False)
                except Exception as exc:
                    log(_("启动收尾刷新失败：{exc}", exc=exc))

        page.run_task(bootstrap)
    else:
        trigger_rebuild(show_loading=True)
        page.run_task(refresh_backup_power_login_validity, False)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--updater":
        from incremental_update import run_updater_mode
        sys.exit(run_updater_mode(sys.argv[1:]))
    if not acquire_singleton_lock():
        try:
            from utils import _show_windows_message_box
            _show_windows_message_box("FMS UPDATE MANAGER", _("已检测到另一个实例正在运行。"))
        except Exception:
            pass
        sys.exit(0)
    if _ensure_installer_not_running():
        ft.run(main)
