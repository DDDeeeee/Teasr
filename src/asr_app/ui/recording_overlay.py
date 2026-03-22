"""QML-based recording indicator overlay.

Drop-in replacement for the old QWidget RecordingIndicator.
Exposes the same signal interface (sig_show / sig_hide / sig_audio_level)
so that controller.py and audio_recorder.py need no changes.
"""

from __future__ import annotations

import ctypes

from PyQt6.QtCore import QObject, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtQml import QQmlApplicationEngine

from ..runtime_env import package_resource

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080

_user32 = ctypes.windll.user32
_GetWindowLong = _user32.GetWindowLongW
_SetWindowLong = _user32.SetWindowLongW


class _OverlayBridge(QObject):
    """Thin Python object exposed to QML as ``overlayBridge``."""

    audioLevelChanged = pyqtSignal()
    activeChanged = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._audio_level: float = 0.0
        self._active: bool = False

    @pyqtProperty(float, notify=audioLevelChanged)
    def audioLevel(self) -> float:
        return self._audio_level

    @audioLevel.setter  # type: ignore[attr-defined]
    def audioLevel(self, value: float) -> None:
        if self._audio_level == value:
            return
        self._audio_level = value
        self.audioLevelChanged.emit()

    @pyqtProperty(bool, notify=activeChanged)
    def active(self) -> bool:
        return self._active

    @active.setter  # type: ignore[attr-defined]
    def active(self, value: bool) -> None:
        if self._active == value:
            return
        self._active = value
        self.activeChanged.emit()


class RecordingOverlay(QObject):
    """QML recording indicator with the same signal API as the old QWidget version."""

    sig_show = pyqtSignal()
    sig_hide = pyqtSignal()
    sig_audio_level = pyqtSignal(list)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._bridge = _OverlayBridge(self)
        self._engine = QQmlApplicationEngine(self)
        self._engine.rootContext().setContextProperty("overlayBridge", self._bridge)

        qml_path = package_resource("ui", "qml", "overlays", "RecordingOverlay.qml")
        self._engine.load(QUrl.fromLocalFile(str(qml_path)))

        self._window: QObject | None = None
        roots = self._engine.rootObjects()
        if roots:
            self._window = roots[0]
        self._no_activate_applied = False

        self.sig_show.connect(self._on_show)
        self.sig_hide.connect(self._on_hide)
        self.sig_audio_level.connect(self._on_audio_level)

    @pyqtSlot()
    def _on_show(self) -> None:
        self._bridge.audioLevel = 0.0
        self._bridge.active = True
        if not self._no_activate_applied:
            self._apply_no_activate()

    @pyqtSlot()
    def _on_hide(self) -> None:
        self._bridge.audioLevel = 0.0
        self._bridge.active = False

    @pyqtSlot(list)
    def _on_audio_level(self, values: list) -> None:
        if not values:
            return
        try:
            level = max(0.0, float(values[0]))
        except (TypeError, ValueError):
            return
        self._bridge.audioLevel = level

    def _apply_no_activate(self) -> None:
        """Set WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW on the overlay HWND."""
        if self._window is None:
            return
        try:
            from PyQt6.QtGui import QWindow

            if isinstance(self._window, QWindow):
                hwnd = int(self._window.winId())
            else:
                hwnd = 0
            if not hwnd:
                return
            ex = _GetWindowLong(hwnd, GWL_EXSTYLE)
            _SetWindowLong(hwnd, GWL_EXSTYLE, ex | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
            self._no_activate_applied = True
        except Exception:
            pass

    def hide(self) -> None:
        """Immediate hide without fade, used by controller cleanup."""
        self._bridge.active = False
        if self._window is not None:
            self._window.setProperty("visible", False)

    def deleteLater(self) -> None:
        if self._window is not None:
            self._window.setProperty("visible", False)
        self._engine.deleteLater()
        super().deleteLater()
