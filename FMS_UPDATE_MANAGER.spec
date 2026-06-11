# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

datas = [('assets', 'assets'), ('navigraph_catalog_2605.json', '.')]
datas += collect_data_files('flet')
try:
    datas += collect_data_files('SimConnect')
except Exception:
    pass

# 把 Flet 桌面客户端（Flutter 编译产物）直接打进包里。
# 否则首次运行时 flet_desktop 会尝试从 GitHub Releases 下载 flet-windows.zip，
# 在网络受限/被墙的环境下会以 WinError 10060 超时崩溃。
# 构建机（GitHub Actions, 美区）能正常访问 GitHub，这里在打包阶段把客户端
# 下载/解压到缓存，再整目录塞进 flet_bin/flet 下；运行时通过 FLET_VIEW_PATH 指向它。
import flet_desktop  # noqa: E402

_client_dir = Path(flet_desktop.ensure_client_cached())  # ~/.flet/client/flet-desktop-full-<ver>
_client_flet = _client_dir / 'flet'  # 内含 flet.exe + 所有 DLL + data/
if not (_client_flet / 'flet.exe').is_file():
    raise SystemExit(f'Flet 桌面客户端未找到: {_client_flet}')
for _root, _dirs, _files in os.walk(_client_flet):
    for _f in _files:
        _abs = Path(_root) / _f
        _rel = _abs.relative_to(_client_flet)
        # 目标路径放在包内 flet_bin/flet/<相对路径目录> 下
        datas.append((str(_abs), str(Path('flet_bin') / 'flet' / _rel.parent)))

a = Analysis(
    ['main_flet.py'],
    pathex=[],
    binaries=[('7z.exe', '.'), ('7z.dll', '.'), ('SimConnect.dll', '.')],
    datas=datas,
    hiddenimports=['psutil', 'SimConnect', 'simconnect_status'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FMS_UPDATE_MANAGER',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\travel_airplane.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FMS_UPDATE_MANAGER',
)
