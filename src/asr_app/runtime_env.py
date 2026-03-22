from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


APP_NAME = "TEASR"
PACKAGE_DIR = Path(__file__).resolve().parent
SOURCE_ROOT = PACKAGE_DIR.parent
PROJECT_ROOT_PATH = SOURCE_ROOT.parent


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            return Path(meipass).resolve()
        return Path(sys.executable).resolve().parent
    return PROJECT_ROOT_PATH


def application_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return PROJECT_ROOT_PATH


def package_root() -> Path:
    if is_frozen():
        return bundle_root() / "asr_app"
    return PACKAGE_DIR


def package_resource(*relative_parts: str) -> Path:
    return package_root().joinpath(*relative_parts)


def asset_path(filename: str) -> Path:
    candidates = [
        bundle_root() / filename,
        application_root() / filename,
        PROJECT_ROOT_PATH / filename,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def user_data_root() -> Path:
    if not is_frozen():
        return PROJECT_ROOT_PATH

    local_appdata = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
    if local_appdata:
        return Path(local_appdata).resolve() / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def runtime_root() -> Path:
    if is_frozen():
        return user_data_root() / "runtime"
    return PROJECT_ROOT_PATH / "runtime"


def runtime_file(*relative_parts: str) -> Path:
    return runtime_root().joinpath(*relative_parts)


PACKAGE_DIR_STR = str(PACKAGE_DIR)
PROJECT_ROOT = str(application_root())
RUNTIME_DIR = str(runtime_root())
LOG_PATH = str(runtime_file("asr_runtime.log"))


def ensure_runtime_dir() -> str:
    runtime_root().mkdir(parents=True, exist_ok=True)
    return RUNTIME_DIR


def _env_candidates() -> list[Path]:
    if is_frozen():
        return [
            application_root() / ".env",
            user_data_root() / ".env",
        ]
    return [PROJECT_ROOT_PATH / ".env"]


@lru_cache(maxsize=1)
def load_project_env() -> str:
    loaded = ""
    for env_path in _env_candidates():
        if not env_path.exists():
            continue
        load_dotenv(env_path, override=True)
        loaded = str(env_path)
    return loaded


ensure_runtime_dir()
