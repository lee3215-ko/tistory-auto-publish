# PyInstaller spec — TistoryPoster onedir 배포
import os

import certifi
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
ICON_FILE = os.path.join(SPEC_DIR, "assets", "app_icon.ico")

datas = [(ICON_FILE, "assets")] if os.path.isfile(ICON_FILE) else []
datas += [(certifi.where(), "certifi")]
datas += collect_data_files("playwright")

hiddenimports = [
    "certifi",
    "openai",
    "playwright",
    "playwright.sync_api",
]
hiddenimports += collect_submodules("playwright")
hiddenimports += collect_submodules("openai")
hiddenimports = list(dict.fromkeys(hiddenimports))

a = Analysis(
    ["run_gui.py"],
    pathex=[SPEC_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["flask"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TistoryPoster",
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
    icon=ICON_FILE if os.path.isfile(ICON_FILE) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="TistoryPoster",
)
