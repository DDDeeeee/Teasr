from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes
from dataclasses import dataclass
from typing import Optional


logger = logging.getLogger("asr")

_user32 = ctypes.windll.user32
_shcore = getattr(ctypes.windll, "shcore", None)

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

MONITOR_DEFAULTTONEAREST = 2
MDT_EFFECTIVE_DPI = 0
PROCESS_PER_MONITOR_DPI_AWARE = 2
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)

MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL,
    wintypes.HANDLE,
    wintypes.HDC,
    ctypes.POINTER(wintypes.RECT),
    wintypes.LPARAM,
)


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


_user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(GUITHREADINFO)]
_user32.GetGUIThreadInfo.restype = wintypes.BOOL
_user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
_user32.ClientToScreen.restype = wintypes.BOOL
_user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
_user32.GetCursorPos.restype = wintypes.BOOL
if hasattr(_user32, "SetProcessDpiAwarenessContext"):
    _user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    _user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
_user32.EnumDisplayMonitors.argtypes = [
    wintypes.HDC,
    ctypes.POINTER(wintypes.RECT),
    MONITORENUMPROC,
    wintypes.LPARAM,
]
_user32.EnumDisplayMonitors.restype = wintypes.BOOL
_user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
_user32.MonitorFromPoint.restype = wintypes.HANDLE
_user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFOEXW)]
_user32.GetMonitorInfoW.restype = wintypes.BOOL

if _shcore is not None:
    _shcore.SetProcessDpiAwareness.argtypes = [ctypes.c_int]
    _shcore.SetProcessDpiAwareness.restype = ctypes.c_long
    _shcore.GetDpiForMonitor.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_uint),
    ]
    _shcore.GetDpiForMonitor.restype = ctypes.c_long


@dataclass(frozen=True)
class CaretPosition:
    x: int
    y: int
    height: int
    source: str
    note: str = ""


@dataclass(frozen=True)
class MonitorDescriptor:
    device_name: str
    monitor_rect: tuple[int, int, int, int]
    work_rect: tuple[int, int, int, int]
    scale: float


def enable_per_monitor_dpi_awareness() -> None:
    try:
        result = _user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        if result:
            logger.info("[OSD] enabled per-monitor DPI awareness (PMv2)")
            return
    except Exception:
        logger.debug("SetProcessDpiAwarenessContext failed", exc_info=True)

    if _shcore is None:
        return

    try:
        hr = _shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)
        if hr == 0:
            logger.info("[OSD] enabled per-monitor DPI awareness (shcore)")
    except Exception:
        logger.debug("SetProcessDpiAwareness failed", exc_info=True)


def _rect_tuple(rect: wintypes.RECT) -> tuple[int, int, int, int]:
    return rect.left, rect.top, rect.right, rect.bottom


def _safe_note(note: str) -> str:
    return note if note else "-"


def _log_caret(position: CaretPosition) -> CaretPosition:
    logger.info(
        "[OSD] caret source=%s x=%d y=%d height=%d note=%s",
        position.source,
        position.x,
        position.y,
        position.height,
        _safe_note(position.note),
    )
    return position


def _get_monitor_scale(hmonitor) -> float:
    if _shcore is None:
        return 1.0

    dpi_x = ctypes.c_uint()
    dpi_y = ctypes.c_uint()
    hr = _shcore.GetDpiForMonitor(hmonitor, MDT_EFFECTIVE_DPI, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
    if hr != 0 or dpi_x.value == 0:
        return 1.0
    return max(dpi_x.value / 96.0, 1.0)


def get_monitor_descriptor(x: int, y: int) -> Optional[MonitorDescriptor]:
    point = wintypes.POINT(x, y)
    hmonitor = _user32.MonitorFromPoint(point, MONITOR_DEFAULTTONEAREST)
    if not hmonitor:
        return None
    return _descriptor_from_handle(hmonitor)


def _descriptor_from_handle(hmonitor) -> Optional[MonitorDescriptor]:
    if not hmonitor:
        return None

    info = MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(MONITORINFOEXW)
    if not _user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
        return None

    return MonitorDescriptor(
        device_name=str(info.szDevice),
        monitor_rect=_rect_tuple(info.rcMonitor),
        work_rect=_rect_tuple(info.rcWork),
        scale=_get_monitor_scale(hmonitor),
    )


def _enumerate_monitors() -> list[MonitorDescriptor]:
    monitors = []

    @MONITORENUMPROC
    def callback(hmonitor, _hdc, _rect, _lparam):
        descriptor = _descriptor_from_handle(hmonitor)
        if descriptor is not None:
            monitors.append(descriptor)
        return True

    _user32.EnumDisplayMonitors(None, None, callback, 0)
    return monitors


def _monitor_sort_key(monitor: MonitorDescriptor) -> tuple[int, int, int, int]:
    left, top, right, bottom = monitor.monitor_rect
    return left, top, right - left, bottom - top


def _screen_sort_key(screen) -> tuple[int, int, int, int]:
    geometry = screen.geometry()
    return geometry.left(), geometry.top(), geometry.width(), geometry.height()


def _match_qt_screen_for_monitor(monitor: MonitorDescriptor):
    from PyQt6.QtGui import QGuiApplication

    screens = QGuiApplication.screens()
    if not screens:
        return None

    device_name = monitor.device_name.lower()
    for candidate in screens:
        if candidate.name().lower() == device_name:
            return candidate

    monitors = _enumerate_monitors()
    if len(monitors) == len(screens):
        sorted_monitors = sorted(monitors, key=_monitor_sort_key)
        sorted_screens = sorted(screens, key=_screen_sort_key)
        for index, candidate_monitor in enumerate(sorted_monitors):
            if candidate_monitor.monitor_rect == monitor.monitor_rect:
                return sorted_screens[index]

    return None


def physical_to_logical_qt_point(x: int, y: int):
    from PyQt6.QtGui import QGuiApplication

    monitor = get_monitor_descriptor(x, y)
    screen = _match_qt_screen_for_monitor(monitor) if monitor is not None else None

    if screen is None:
        screen = QGuiApplication.primaryScreen()

    if screen is None:
        return x, y, None, 1.0

    if monitor is None:
        scale = max(float(screen.devicePixelRatio()), 1.0)
        return round(x / scale), round(y / scale), screen, scale

    geometry = screen.geometry()
    logical_x = geometry.left() + round((x - monitor.monitor_rect[0]) / monitor.scale)
    logical_y = geometry.top() + round((y - monitor.monitor_rect[1]) / monitor.scale)
    return logical_x, logical_y, screen, monitor.scale


def _get_caret_by_gui_thread_info(thread_id: int) -> Optional[CaretPosition]:
    gui = GUITHREADINFO()
    gui.cbSize = ctypes.sizeof(GUITHREADINFO)
    if not _user32.GetGUIThreadInfo(thread_id, ctypes.byref(gui)):
        return None
    if not gui.hwndCaret:
        return None

    width = max(gui.rcCaret.right - gui.rcCaret.left, 0)
    point = wintypes.POINT(gui.rcCaret.left + width // 2, gui.rcCaret.bottom)
    if not _user32.ClientToScreen(gui.hwndCaret, ctypes.byref(point)):
        return None

    height = max(gui.rcCaret.bottom - gui.rcCaret.top, 0)
    return CaretPosition(point.x, point.y, height, "win32_gui_thread_info")


def _describe_focused_element(focused) -> str:
    parts = []
    for attr in ("CurrentClassName", "CurrentLocalizedControlType", "CurrentFrameworkId"):
        try:
            value = getattr(focused, attr)
        except Exception:
            value = None
        if value:
            parts.append(str(value))
    return " | ".join(parts)


def _query_pattern(element, pattern_id, interface):
    try:
        pattern = element.GetCurrentPattern(pattern_id)
    except Exception:
        return None
    if pattern is None:
        return None
    try:
        return pattern.QueryInterface(interface)
    except Exception:
        return None


def _range_to_position(text_range, source: str, note: str) -> Optional[CaretPosition]:
    try:
        rectangles = list(text_range.GetBoundingRectangles())
    except Exception:
        return None

    if len(rectangles) < 4:
        return None

    best_rect = None
    best_area = None
    for index in range(0, len(rectangles), 4):
        chunk = rectangles[index:index + 4]
        if len(chunk) < 4:
            continue
        left, top, width, height = chunk
        if width < 0 or height <= 0:
            continue
        area = max(width, 1.0) * height
        if best_area is None or area < best_area:
            best_area = area
            best_rect = chunk

    if best_rect is None:
        return None

    left, top, width, height = best_rect
    x = round(left + (width / 2.0 if width > 0 else 0.0))
    y = round(top + height)
    return CaretPosition(x, y, round(height), source, note)


def _get_caret_by_uia() -> Optional[CaretPosition]:
    try:
        import comtypes
        import comtypes.client
    except ImportError:
        logger.debug("UIA caret detection skipped because comtypes is unavailable")
        return None

    initialized = False
    try:
        comtypes.CoInitialize()
        initialized = True
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient

        automation = comtypes.client.CreateObject(
            UIAutomationClient.CUIAutomation,
            interface=UIAutomationClient.IUIAutomation,
        )
        focused = automation.GetFocusedElement()
        if focused is None:
            return None

        note = _describe_focused_element(focused)

        text_pattern2 = _query_pattern(
            focused,
            UIAutomationClient.UIA_TextPattern2Id,
            UIAutomationClient.IUIAutomationTextPattern2,
        )
        if text_pattern2 is not None:
            is_active, text_range = text_pattern2.GetCaretRange()
            if text_range is not None:
                position = _range_to_position(
                    text_range,
                    "uia_textpattern2_caret",
                    f"active={bool(is_active)}; {note}".strip(),
                )
                if position is not None:
                    return position

        text_pattern = _query_pattern(
            focused,
            UIAutomationClient.UIA_TextPatternId,
            UIAutomationClient.IUIAutomationTextPattern,
        )
        if text_pattern is None:
            return None

        selection = text_pattern.GetSelection()
        if selection is None or selection.Length <= 0:
            return None

        text_range = selection.GetElement(0)
        if text_range is None:
            return None

        return _range_to_position(text_range, "uia_textpattern_selection", note)
    except Exception:
        logger.debug("UIA caret detection failed", exc_info=True)
        return None
    finally:
        if initialized:
            try:
                comtypes.CoUninitialize()
            except Exception:
                logger.debug("UIA CoUninitialize failed", exc_info=True)


def _get_caret_by_cursor() -> Optional[CaretPosition]:
    point = wintypes.POINT()
    if not _user32.GetCursorPos(ctypes.byref(point)):
        return None
    return CaretPosition(point.x, point.y, 0, "cursor_fallback")


def _get_virtual_screen_fallback() -> CaretPosition:
    left = _user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    top = _user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    width = _user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    height = _user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    x = left + width // 2
    y = top + max(height - 150, 0)
    return CaretPosition(x, y, 0, "virtual_screen_fallback", "no caret source available")


def get_caret_position() -> CaretPosition:
    try:
        hwnd_foreground = _user32.GetForegroundWindow()
        process_id = wintypes.DWORD()
        thread_id = _user32.GetWindowThreadProcessId(hwnd_foreground, ctypes.byref(process_id))

        if thread_id:
            position = _get_caret_by_gui_thread_info(thread_id)
            if position is not None:
                return _log_caret(position)

        position = _get_caret_by_uia()
        if position is not None:
            return _log_caret(position)

        position = _get_caret_by_cursor()
        if position is not None:
            return _log_caret(position)
    except Exception:
        logger.exception("get_caret_position failed")

    return _log_caret(_get_virtual_screen_fallback())
