# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"

hiddenimports = [
    "PyQt6.QtQuickWidgets",
    "PyQt6.QtSvg",
]
hiddenimports += collect_submodules("PyQt6.QtQml")

datas = [
    (str(ROOT / "src" / "asr_app" / "ui" / "qml"), "asr_app/ui/qml"),
    (str(ROOT / "src" / "asr_app" / "web" / "remote_phone"), "asr_app/web/remote_phone"),
    (str(ROOT / "teasr-logo.svg"), "."),
    (str(ROOT / "TEASR.ico"), "."),
    (str(ROOT / ".env.example"), "."),
]

a = Analysis(
    [str(ROOT / "scripts" / "launch_asr_gui.pyw")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name="TEASR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "TEASR.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="TEASR",
)

