import signal
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from .app.controller import AppController
from .i18n import detect_system_lang, set_lang
from .caret_locator import enable_per_monitor_dpi_awareness
from .services.settings_service import SettingsService
from .single_instance import SingleInstanceCoordinator
from .ui.qml_window import MainWindow
from .windows_identity import APP_DISPLAY_NAME, APP_USER_MODEL_ID, configure_process_identity, configure_window_identity


def _build_light_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f3efe8"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#1f1f1f"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#fbfaf7"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f3efe8"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#fbfaf7"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#1f1f1f"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#1f1f1f"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#fbfaf7"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#1f1f1f"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#d8c7b3"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#1f1f1f"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#7a756d"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#7a756d"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#7a756d"))
    return palette


def build_application(start_minimized: bool = False):
    enable_per_monitor_dpi_awareness()
    configure_process_identity()

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("TEASR")
    app.setOrganizationName("TEASR")
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setPalette(_build_light_palette())

    instance = SingleInstanceCoordinator(APP_USER_MODEL_ID, APP_DISPLAY_NAME)
    if not instance.acquire():
        return app, None, None

    settings_service = SettingsService()
    settings = settings_service.load()
    set_lang(settings.get("language", "") or detect_system_lang())
    controller = AppController(settings_service)
    window = MainWindow(controller, start_minimized=start_minimized)
    configure_window_identity(window)
    controller.start()

    app.aboutToQuit.connect(instance.close)

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal_timer = QTimer()
    signal_timer.start(200)
    signal_timer.timeout.connect(lambda: None)
    app._signal_timer = signal_timer
    app._single_instance = instance
    app._asr_controller = controller
    app._asr_window = window
    return app, controller, window


def main(start_minimized: bool = False):
    app, _controller, window = build_application(start_minimized=start_minimized)
    if window is None:
        return 0
    if not start_minimized:
        window.show_main_window()
    return app.exec()
