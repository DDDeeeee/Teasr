import ctypes
import sys


_ERROR_ALREADY_EXISTS = 183
_kernel32 = ctypes.windll.kernel32 if sys.platform == "win32" else None
_user32 = ctypes.windll.user32 if sys.platform == "win32" else None
class SingleInstanceCoordinator:
    def __init__(self, mutex_name: str, window_title: str):
        self.mutex_name = self._normalize_mutex_name(mutex_name)
        self.window_title = window_title
        self._handle = None

    def acquire(self) -> bool:
        if sys.platform != "win32":
            return True

        self._handle = _kernel32.CreateMutexW(None, False, self.mutex_name)
        if not self._handle:
            raise OSError("CreateMutexW failed")

        if _kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
            self.activate_existing_window()
            self.close()
            return False
        return True

    def close(self) -> None:
        if self._handle:
            _kernel32.CloseHandle(self._handle)
            self._handle = None

    def activate_existing_window(self) -> None:
        if sys.platform != "win32":
            return

        return

    @staticmethod
    def _normalize_mutex_name(mutex_name: str) -> str:
        chars = []
        for ch in mutex_name:
            if ch.isalnum():
                chars.append(ch)
            else:
                chars.append("_")
        return "Local\\" + "".join(chars)
