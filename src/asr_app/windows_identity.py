import ctypes
import logging
import subprocess
import sys
from pathlib import Path

from .runtime_env import application_root, asset_path, is_frozen

APP_USER_MODEL_ID = "TEASR.TEASR"
APP_DISPLAY_NAME = "TEASR"
_ICON_FILE_NAME = "TEASR.ico"
_GUI_LAUNCHER_NAME = "launch_asr_gui.pyw"

logger = logging.getLogger(__name__)


def configure_process_identity() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        logger.exception("Failed to set process AppUserModelID")


def configure_window_identity(window) -> None:
    if sys.platform != "win32":
        return

    try:
        from win32com.propsys import propsys, pscon
    except ModuleNotFoundError:
        return

    try:
        hwnd = int(window.winId())
        store = propsys.SHGetPropertyStoreForWindow(hwnd, propsys.IID_IPropertyStore)
        store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(APP_USER_MODEL_ID))

        relaunch_command = build_relaunch_command()
        if relaunch_command:
            store.SetValue(
                pscon.PKEY_AppUserModel_RelaunchCommand,
                propsys.PROPVARIANTType(relaunch_command),
            )

        store.SetValue(
            pscon.PKEY_AppUserModel_RelaunchDisplayNameResource,
            propsys.PROPVARIANTType(APP_DISPLAY_NAME),
        )

        icon_resource = build_icon_resource()
        if icon_resource:
            store.SetValue(
                pscon.PKEY_AppUserModel_RelaunchIconResource,
                propsys.PROPVARIANTType(icon_resource),
            )

        store.Commit()
    except Exception:
        logger.exception("Failed to set window taskbar identity")


def build_relaunch_command() -> str:
    if is_frozen():
        return subprocess.list2cmdline([str(Path(sys.executable).resolve())])

    pythonw = _resolve_pythonw_path()
    launcher = _root_dir() / "scripts" / _GUI_LAUNCHER_NAME
    if not pythonw or not launcher.exists():
        return ""
    return subprocess.list2cmdline([str(pythonw), str(launcher)])


def build_icon_resource() -> str:
    if is_frozen():
        return f'{Path(sys.executable).resolve()},0'

    icon_path = asset_path(_ICON_FILE_NAME)
    if not icon_path.exists():
        return ""
    return f"{icon_path},0"


def _resolve_pythonw_path() -> Path | None:
    candidates = [
        _root_dir() / "venv" / "Scripts" / "pythonw.exe",
        Path(sys.executable).with_name("pythonw.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _root_dir() -> Path:
    return application_root()
