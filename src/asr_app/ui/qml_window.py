from __future__ import annotations

from PyQt6.QtCore import QTimer, Qt, QUrl
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtQuickWidgets import QQuickWidget
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication, QMainWindow, QMenu, QMessageBox, QSystemTrayIcon

from ..app.controller import AppController
from ..i18n import t
from ..runtime_env import asset_path, package_resource
from .bridge import AppBridge


class MainWindow(QMainWindow):
    def __init__(self, controller: AppController, start_minimized: bool = False):
        super().__init__()
        self.controller = controller
        self.bridge = AppBridge(controller)
        self._allow_close = False
        self._tray: QSystemTrayIcon | None = None
        self._tray_menu: QMenu | None = None
        self._mode_menu: QMenu | None = None
        self._mode_actions: dict[str, QAction] = {}
        self._show_action: QAction | None = None
        self._start_action: QAction | None = None
        self._stop_action: QAction | None = None
        self._settings_action: QAction | None = None
        self._diagnostics_action: QAction | None = None
        self._quit_action: QAction | None = None

        self.setWindowTitle("TEASR")
        self.setMinimumSize(900, 620)
        self.resize(980, 680)
        self.setWindowIcon(self._create_app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self._qml_view = QQuickWidget(self)
        self._qml_view.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self._qml_view.setClearColor(QColor("#f3efe8"))
        self._qml_view.rootContext().setContextProperty("appBridge", self.bridge)
        qml_path = package_resource("ui", "qml", "AppRoot.qml")
        self._qml_view.setSource(QUrl.fromLocalFile(str(qml_path)))
        if self._qml_view.status() == QQuickWidget.Status.Error:
            errors = "\n".join(error.toString() for error in self._qml_view.errors())
            raise RuntimeError(f"Failed to load QML UI:\n{errors}")
        self.setCentralWidget(self._qml_view)

        self.controller.notification.connect(self.show_notification)
        self.bridge.translationsChanged.connect(self._rebuild_tray_text)
        self._setup_tray()
        if start_minimized and self.controller.state.tray_enabled:
            QTimer.singleShot(0, self.hide)

    def open_page(self, page_index: int) -> None:
        self.bridge.setCurrentPage(page_index)
        self.show_main_window()

    def show_main_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_application(self) -> None:
        QTimer.singleShot(0, self._perform_quit)

    def _perform_quit(self) -> None:
        self._allow_close = True
        self.controller.shutdown()
        if self._tray is not None:
            self._tray.hide()
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def closeEvent(self, event) -> None:
        if self._allow_close:
            return super().closeEvent(event)
        if not self.controller.state.tray_enabled:
            self._allow_close = True
            self.controller.shutdown()
            if self._tray is not None:
                self._tray.hide()
            app = QApplication.instance()
            if app is not None:
                app.quit()
            return super().closeEvent(event)
        event.ignore()
        self.hide()
        self.bridge.flashMessage(t("toast.minimized_to_tray"))

    def show_notification(self, message: str, level: str) -> None:
        if level == "error":
            QMessageBox.warning(self, "TEASR", message)
        elif self._tray is not None and not self.isVisible():
            self._tray.showMessage("TEASR", message, QSystemTrayIcon.MessageIcon.Information, 2500)

    def _setup_tray(self) -> None:
        self._tray = QSystemTrayIcon(self.windowIcon(), self)
        self._tray.setToolTip("TEASR")
        self.controller.state_changed.connect(self._update_tray_tooltip)

        self._tray_menu = QMenu(self)
        self._show_action = QAction(self)
        self._show_action.triggered.connect(self.show_main_window)
        self._tray_menu.addAction(self._show_action)

        self._tray_menu.addSeparator()
        self._start_action = QAction(self)
        self._start_action.triggered.connect(self.controller.start_recording)
        self._stop_action = QAction(self)
        self._stop_action.triggered.connect(self.controller.stop_recording)
        self._tray_menu.addAction(self._start_action)
        self._tray_menu.addAction(self._stop_action)

        self._mode_menu = self._tray_menu.addMenu("")
        for mode, label in self.controller.mode_options():
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, m=mode: self.controller.set_mode(m))
            self._mode_menu.addAction(action)
            self._mode_actions[mode] = action

        self._tray_menu.addSeparator()
        self._settings_action = QAction(self)
        self._settings_action.triggered.connect(lambda: self.open_page(1))
        self._diagnostics_action = QAction(self)
        self._diagnostics_action.triggered.connect(lambda: self.open_page(2))
        self._tray_menu.addAction(self._settings_action)
        self._tray_menu.addAction(self._diagnostics_action)

        self._tray_menu.addSeparator()
        self._quit_action = QAction(self)
        self._quit_action.triggered.connect(self.quit_application)
        self._tray_menu.addAction(self._quit_action)

        self._tray.setContextMenu(self._tray_menu)
        self._tray.activated.connect(self._tray_activated)
        self._rebuild_tray_text()
        self._tray.show()
        self._update_tray_tooltip(self.controller.state.to_dict())

    def _rebuild_tray_text(self) -> None:
        if self._show_action is not None:
            self._show_action.setText(t("tray.show_main_window"))
        if self._start_action is not None:
            self._start_action.setText(t("tray.start_recording"))
        if self._stop_action is not None:
            self._stop_action.setText(t("tray.stop_transcribing"))
        if self._mode_menu is not None:
            self._mode_menu.setTitle(t("tray.switch_mode"))
        if self._settings_action is not None:
            self._settings_action.setText(t("tray.open_settings"))
        if self._diagnostics_action is not None:
            self._diagnostics_action.setText(t("tray.open_diagnostics"))
        if self._quit_action is not None:
            self._quit_action.setText(t("tray.quit"))
        for mode, action in self._mode_actions.items():
            action.setText(dict(self.controller.mode_options()).get(mode, mode))
        self._update_tray_tooltip(self.controller.state.to_dict())

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show_main_window()

    def _update_tray_tooltip(self, state: dict) -> None:
        if self._tray is None:
            return
        for mode, action in self._mode_actions.items():
            action.setChecked(mode == state.get("current_mode"))
        self._tray.setToolTip(f"TEASR | {state.get('mode_label', '')} | {state.get('status_label', '')}")

    def _create_app_icon(self) -> QIcon:
        svg_path = asset_path("teasr-logo.svg")
        if svg_path.exists():
            renderer = QSvgRenderer(str(svg_path))
            icon = QIcon()
            for size in (16, 24, 32, 48, 64, 96, 128, 256):
                pixmap = QPixmap(size, size)
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                renderer.render(painter)
                painter.end()
                icon.addPixmap(pixmap)
            return icon
        pixmap = QPixmap(96, 96)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QColor("#1e1e24"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(4, 4, 88, 88)
        painter.setPen(QColor("#ffffff"))
        from PyQt6.QtGui import QFont
        painter.setFont(QFont("Segoe UI", 34, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "T")
        painter.end()
        return QIcon(pixmap)
