from __future__ import annotations

import ctypes
from ctypes import wintypes

from .runtime_logging import logger


osd_bubble = None
recording_indicator = None
_log_listeners: list = []


def add_log_listener(callback) -> None:
    if callback not in _log_listeners:
        _log_listeners.append(callback)


def remove_log_listener(callback) -> None:
    if callback in _log_listeners:
        _log_listeners.remove(callback)


def log(message: str) -> None:
    print(message, flush=True)
    logger.info(message)
    for callback in list(_log_listeners):
        try:
            callback(message)
        except Exception:
            logger.exception("Log listener failed")


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT)]


def send_unicode_text(text: str) -> None:
    if not text:
        return

    input_keyboard = 1
    keyeventf_unicode = 0x0004
    keyeventf_keyup = 0x0002

    input_array = INPUT * (len(text) * 2)
    inputs = input_array()

    for index, char in enumerate(text):
        codepoint = ord(char)
        inputs[index * 2] = INPUT(
            type=input_keyboard,
            ki=KEYBDINPUT(
                wVk=0,
                wScan=codepoint,
                dwFlags=keyeventf_unicode,
                time=0,
                dwExtraInfo=None,
            ),
        )
        inputs[index * 2 + 1] = INPUT(
            type=input_keyboard,
            ki=KEYBDINPUT(
                wVk=0,
                wScan=codepoint,
                dwFlags=keyeventf_unicode | keyeventf_keyup,
                time=0,
                dwExtraInfo=None,
            ),
        )

    ctypes.windll.user32.SendInput(len(inputs), ctypes.byref(inputs), ctypes.sizeof(INPUT))


def get_foreground_window() -> int:
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
    except Exception:
        logger.exception("GetForegroundWindow failed")
        return 0
    return int(hwnd or 0)


def is_same_foreground_window(hwnd: int) -> bool:
    if not hwnd:
        return True
    return get_foreground_window() == hwnd


def transcribe_non_stream(audio_base64: str, api_key: str, model_name: str) -> str:
    """Deprecated: use AsrProvider instead. Kept for legacy CLI compatibility."""
    from .services.asr import create_provider
    from .services.asr.base import AsrCredentials

    provider = create_provider("aliyun", AsrCredentials(api_key=api_key))
    return provider.transcribe_non_stream(audio_base64, model_name)


class RealtimeTranscriber:
    """Deprecated: use AsrProvider.create_realtime_session() instead."""

    def __init__(self, api_key: str, model_name: str):
        from .services.asr import create_provider
        from .services.asr.base import AsrCredentials

        provider = create_provider("aliyun", AsrCredentials(api_key=api_key))
        self._session = provider.create_realtime_session(model_name)

    def start(self) -> None:
        self._session.start()

    def send_audio(self, pcm_bytes: bytes) -> None:
        self._session.send_audio(pcm_bytes)

    def finish_and_get_text(self) -> str:
        return self._session.finish_and_get_text()

    def close(self) -> None:
        self._session.close()
