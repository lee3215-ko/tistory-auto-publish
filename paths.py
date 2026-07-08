"""??寃쎈줈쨌踰꾩쟾쨌?곗씠???붾젆?곕━."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "TistoryPoster"
APP_VERSION = "2.0.5"
EXE_NAME = "TistoryPoster.exe"
UPDATE_VERSION_URL = (
    "https://raw.githubusercontent.com/lee3215-ko/tistory-auto-publish/main/version.json"
)
RELEASE_ASSET = "TistoryPoster.zip"
DATA_FILES = ("accounts.txt",)


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def get_app_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_data_dir() -> Path:
    data_dir = get_app_dir() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def data_path(filename: str) -> Path:
    return get_data_dir() / filename


def accounts_path() -> Path:
    return data_path("accounts.txt")


def migrate_legacy_data() -> None:
    app_dir = get_app_dir()
    data_dir = get_data_dir()
    for name in DATA_FILES:
        legacy = app_dir / name
        target = data_dir / name
        if legacy.is_file() and not target.is_file():
            shutil.copy2(legacy, target)


def get_resource_path(*parts: str) -> Path:
    if is_frozen():
        base = Path(getattr(sys, "_MEIPASS", str(get_app_dir())))
    else:
        base = get_app_dir()
    return base.joinpath(*parts)


def get_icon_path() -> Path | None:
    ico = get_resource_path("assets", "app_icon.ico")
    return ico if ico.is_file() else None


def is_admin_mode() -> bool:
    return os.getenv("TISTORY_POSTER_ADMIN", "").strip() == "1"


def init_runtime_paths() -> None:
    os.chdir(get_app_dir())
    migrate_legacy_data()






