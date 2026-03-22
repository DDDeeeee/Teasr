from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QDesktopServices, QGuiApplication

from ...app.controller import AppController
from ...config import asr_provider_labels
from ...i18n import available_languages, get_lang, qml_translations, t
from ...runtime_env import LOG_PATH
from ..hotkeys import build_hotkey_from_key_event, format_hotkey_label
from ..qr_code import build_styled_qr_data_url
from ..view_data import DIAGNOSTIC_KEYS, LOG_LEVEL_OPTIONS, diagnostic_label


class AppBridge(QObject):
    stateChanged = pyqtSignal()
    connectionSettingsChanged = pyqtSignal()
    behaviorSettingsChanged = pyqtSignal()
    diagnosticsEntriesChanged = pyqtSignal()
    logTextChanged = pyqtSignal()
    deviceOptionsChanged = pyqtSignal()
    currentPageChanged = pyqtSignal()
    apiKeyVisibleChanged = pyqtSignal()
    textPolishApiKeyVisibleChanged = pyqtSignal()
    toastMessageChanged = pyqtSignal()
    toastLevelChanged = pyqtSignal()
    translationsChanged = pyqtSignal()
    optionsChanged = pyqtSignal()

    def __init__(self, controller: AppController):
        super().__init__()
        self.controller = controller
        self._state: dict = {}
        self._connection_settings: dict = {}
        self._behavior_settings: dict = {}
        self._diagnostics_entries: list[dict] = []
        self._log_text = controller.recent_logs_text()
        self._device_options: list[dict] = []
        self._cached_remote_phone_url = ""
        self._cached_remote_phone_qr_source = ""
        self._diagnostics_snapshot: dict[str, str] = {}
        self._current_page = 0
        self._api_key_visible = False
        self._text_polish_api_key_visible = False
        self._toast_message = ""
        self._toast_level = "info"
        self._translations = qml_translations()
        self._pending_language = ""
        self._language_timer = QTimer(self)
        self._language_timer.setSingleShot(True)
        self._language_timer.timeout.connect(self._apply_language_change)
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self.clearToast)

        self.controller.state_changed.connect(self._on_state_changed)
        self.controller.logs_changed.connect(self._on_logs_changed)
        self.controller.devices_changed.connect(self._on_devices_changed)
        self.controller.notification.connect(self._on_notification)

        self._reload_forms()
        self._on_devices_changed(self.controller.audio_devices)
        self._on_state_changed(self.controller.state.to_dict())
        self._rebuild_diagnostics(force=True)

    @pyqtProperty("QVariantMap", notify=stateChanged)
    def state(self) -> dict:
        return self._state

    @pyqtProperty("QVariantMap", notify=connectionSettingsChanged)
    def connectionSettings(self) -> dict:
        return self._connection_settings

    @pyqtProperty("QVariantMap", notify=behaviorSettingsChanged)
    def behaviorSettings(self) -> dict:
        return self._behavior_settings

    @pyqtProperty("QVariantList", notify=diagnosticsEntriesChanged)
    def diagnosticsEntries(self) -> list[dict]:
        return self._diagnostics_entries

    @pyqtProperty(str, notify=logTextChanged)
    def logText(self) -> str:
        return self._log_text

    @pyqtProperty("QVariantList", notify=deviceOptionsChanged)
    def deviceOptions(self) -> list[dict]:
        return self._device_options

    @pyqtProperty("QVariantMap", notify=translationsChanged)
    def translations(self) -> dict:
        return self._translations

    @pyqtProperty(str, notify=translationsChanged)
    def currentLanguage(self) -> str:
        return get_lang()

    @pyqtProperty("QVariantList", notify=optionsChanged)
    def modeOptions(self) -> list[dict]:
        return self._normalize_options(self.controller.mode_options())

    @pyqtProperty("QVariantList", notify=optionsChanged)
    def asrProviderOptions(self) -> list[dict]:
        labels = asr_provider_labels()
        return [{"value": key, "label": value} for key, value in labels.items()]

    @pyqtProperty("QVariantList", notify=optionsChanged)
    def hotkeyModeOptions(self) -> list[dict]:
        return self._normalize_options(self.controller.hotkey_mode_options())

    @pyqtProperty("QVariantList", notify=optionsChanged)
    def optimizationOptions(self) -> list[dict]:
        return self._normalize_options(self.controller.optimization_level_options())

    @pyqtProperty("QVariantList", notify=optionsChanged)
    def inputSourceOptions(self) -> list[dict]:
        return self._normalize_options(self.controller.input_source_options())

    @pyqtProperty("QVariantList", notify=optionsChanged)
    def logLevelOptions(self) -> list[dict]:
        return [{"value": item, "label": item} for item in LOG_LEVEL_OPTIONS]

    @pyqtProperty("QVariantList", notify=optionsChanged)
    def runtimeNotes(self) -> list[str]:
        return [t("note.1"), t("note.2"), t("note.3"), t("note.4")]

    @pyqtProperty("QVariantList", notify=optionsChanged)
    def languageOptions(self) -> list[dict]:
        return [{"value": value, "label": label} for value, label in available_languages()]

    @pyqtProperty(int, notify=currentPageChanged)
    def currentPage(self) -> int:
        return self._current_page

    @pyqtProperty(bool, notify=apiKeyVisibleChanged)
    def apiKeyVisible(self) -> bool:
        return self._api_key_visible

    @pyqtProperty(bool, notify=textPolishApiKeyVisibleChanged)
    def textPolishApiKeyVisible(self) -> bool:
        return self._text_polish_api_key_visible

    @pyqtProperty(str, notify=toastMessageChanged)
    def toastMessage(self) -> str:
        return self._toast_message

    @pyqtProperty(str, notify=toastLevelChanged)
    def toastLevel(self) -> str:
        return self._toast_level

    @pyqtSlot(int)
    def setCurrentPage(self, page_index: int) -> None:
        normalized = max(0, min(int(page_index), 2))
        if normalized == self._current_page:
            return
        self._current_page = normalized
        self.currentPageChanged.emit()
        if normalized == 2:
            self._rebuild_diagnostics()

    @pyqtSlot(str)
    def setMode(self, mode: str) -> None:
        self.controller.set_mode(mode)

    @pyqtSlot(str)
    def setHotkeyMode(self, mode: str) -> None:
        self.controller.set_hotkey_mode(mode)

    @pyqtSlot(str)
    def setOptimizationLevel(self, level: str) -> None:
        self.controller.set_optimization_level(level)

    @pyqtSlot(str)
    def setInputSourceType(self, input_source_type: str) -> None:
        self.controller.set_input_source_type(input_source_type)

    @pyqtSlot(str)
    def setLanguage(self, lang: str) -> None:
        self._pending_language = str(lang or "").strip()
        self._language_timer.start(0)

    @pyqtSlot()
    def startRecording(self) -> None:
        self.controller.start_recording()

    @pyqtSlot()
    def stopRecording(self) -> None:
        self.controller.stop_recording()

    @pyqtSlot()
    def refreshAudioDevices(self) -> None:
        self.controller.refresh_audio_devices(emit=True)
        self.flashMessage(t("toast.device_list_refreshed"))

    @pyqtSlot()
    def restartRemotePhoneService(self) -> None:
        self.controller.restart_remote_phone_service()

    @pyqtSlot()
    def copyRemotePhoneUrl(self) -> None:
        url = str(self._state.get("remote_phone_url") or "").strip()
        if not url:
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(url)
        self.flashMessage(t("toast.phone_url_copied"))

    @pyqtSlot()
    def openLogFolder(self) -> None:
        folder = Path(os.path.dirname(LOG_PATH))
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    @pyqtSlot()
    def toggleApiKeyVisibility(self) -> None:
        self._api_key_visible = not self._api_key_visible
        self.apiKeyVisibleChanged.emit()

    @pyqtSlot()
    def toggleTextPolishApiKeyVisibility(self) -> None:
        self._text_polish_api_key_visible = not self._text_polish_api_key_visible
        self.textPolishApiKeyVisibleChanged.emit()

    @pyqtSlot()
    def testAsrNonStream(self) -> None:
        self.controller.test_asr_non_stream()
        self.flashMessage(t("toast.testing_non_stream"), "info", 5000)

    @pyqtSlot()
    def testTextPolish(self) -> None:
        self.controller.test_text_polish()
        self.flashMessage(t("toast.testing_text_polish"), "info", 5000)

    @pyqtSlot("QVariantMap")
    def saveConnectionSettings(self, form: dict) -> None:
        updates = {
            "asr_provider": str(form.get("asr_provider", "aliyun")).strip() or "aliyun",
            "asr_api_key": str(form.get("asr_api_key", "")).strip(),
            "asr_app_key": str(form.get("asr_app_key", "")).strip(),
            "asr_base_url": str(form.get("asr_base_url", "")).strip(),
            "asr_non_stream_model": str(form.get("asr_non_stream_model", "")).strip(),
            "asr_realtime_model": str(form.get("asr_realtime_model", "")).strip(),
            "text_polish_api_key": str(form.get("text_polish_api_key", "")).strip(),
            "text_polish_base_url": str(form.get("text_polish_base_url", "")).strip(),
            "text_polish_model": str(form.get("text_polish_model", "")).strip(),
            "primary_hotkey": str(form.get("primary_hotkey", "")).strip(),
            "secondary_hotkey": str(form.get("secondary_hotkey", "")).strip(),
            "log_level": str(form.get("log_level", "INFO")).strip() or "INFO",
            "language": str(form.get("language", self.controller.settings.get("language", ""))).strip(),
        }
        self.controller.save_settings(updates)
        self._reload_forms()
        self.flashMessage(t("toast.connection_saved"))

    @pyqtSlot("QVariantMap")
    def saveBehaviorSettings(self, form: dict) -> None:
        gain_value = form.get("remote_phone_input_gain", "0.75")
        try:
            gain = float(gain_value)
        except (TypeError, ValueError):
            gain = float(self.controller.settings.get("remote_phone_input_gain", 0.75))

        updates = {
            "audio_input_device": str(form.get("audio_input_device", "")),
            "remote_phone_input_gain": max(0.0, min(gain, 4.0)),
            "enable_tray": bool(form.get("enable_tray", True)),
            "start_minimized": bool(form.get("start_minimized", False)),
            "custom_polish_prompt": str(form.get("custom_polish_prompt", "")),
        }
        self.controller.save_settings(updates)
        self._reload_forms()
        self.flashMessage(t("toast.behavior_saved"))

    @pyqtSlot(int, str, int, result=str)
    def buildHotkeyFromEvent(self, key: int, text: str, modifiers: int) -> str:
        return build_hotkey_from_key_event(int(key), text, int(modifiers))

    @pyqtSlot(str, result=str)
    def formatHotkeyLabel(self, hotkey: str) -> str:
        return format_hotkey_label(hotkey)

    @pyqtSlot()
    def clearToast(self) -> None:
        if not self._toast_message:
            return
        self._toast_message = ""
        self.toastMessageChanged.emit()

    def flashMessage(self, message: str, level: str = "info", timeout_ms: int = 2800) -> None:
        self._show_toast(message, level, timeout_ms)

    def _apply_language_change(self) -> None:
        lang = self._pending_language
        self._pending_language = ""
        self.controller.set_language(lang)
        self._reload_forms()
        self._rebuild_translations()
        self._on_devices_changed(self.controller.audio_devices)
        self._on_state_changed(self.controller.state.to_dict())
        self._rebuild_diagnostics(force=True)
        self.optionsChanged.emit()

    def _rebuild_translations(self) -> None:
        self._translations = qml_translations()
        self.translationsChanged.emit()

    def _on_state_changed(self, state: dict) -> None:
        mapped = dict(state)
        remote_phone_url = str(mapped.get("remote_phone_url") or "")
        if remote_phone_url != self._cached_remote_phone_url:
            self._cached_remote_phone_url = remote_phone_url
            self._cached_remote_phone_qr_source = build_styled_qr_data_url(remote_phone_url, 156)
        mapped["remote_phone_qr_source"] = self._cached_remote_phone_qr_source

        if mapped != self._state:
            self._state = mapped
            self.stateChanged.emit()

        if self._current_page == 2:
            self._rebuild_diagnostics()

    def _on_logs_changed(self, text: str) -> None:
        self._log_text = text
        self.logTextChanged.emit()

    def _on_devices_changed(self, devices: list) -> None:
        self._device_options = [{"value": "", "label": t("device.system_default")}]
        for item in devices:
            self._device_options.append({"value": str(item["id"]), "label": str(item["label"])})
        self.deviceOptionsChanged.emit()

    def _on_notification(self, message: str, level: str) -> None:
        self._show_toast(message or "", level or "info", 2800)

    def _reload_forms(self) -> None:
        settings = self.controller.settings
        self._connection_settings = {
            "asr_provider": settings.get("asr_provider", "aliyun"),
            "asr_api_key": settings.get("asr_api_key") or settings.get("api_key", ""),
            "asr_app_key": settings.get("asr_app_key", ""),
            "asr_base_url": settings.get("asr_base_url") or settings.get("base_url", ""),
            "asr_non_stream_model": settings.get("asr_non_stream_model", ""),
            "asr_realtime_model": settings.get("asr_realtime_model", ""),
            "text_polish_api_key": settings.get("text_polish_api_key") or settings.get("api_key", ""),
            "text_polish_base_url": settings.get("text_polish_base_url") or settings.get("base_url", ""),
            "text_polish_model": settings.get("text_polish_model", ""),
            "primary_hotkey": settings.get("primary_hotkey", ""),
            "secondary_hotkey": settings.get("secondary_hotkey", ""),
            "log_level": settings.get("log_level", "INFO"),
            "language": settings.get("language", ""),
        }
        self._behavior_settings = {
            "audio_input_device": str(settings.get("audio_input_device", "")),
            "remote_phone_input_gain": f"{float(settings.get('remote_phone_input_gain', 0.75)):.2f}",
            "enable_tray": bool(settings.get("enable_tray", True)),
            "start_minimized": bool(settings.get("start_minimized", False)),
            "custom_polish_prompt": str(settings.get("custom_polish_prompt", "")),
        }
        self.connectionSettingsChanged.emit()
        self.behaviorSettingsChanged.emit()

    def _rebuild_diagnostics(self, force: bool = False) -> None:
        snapshot = {key: str(value) for key, value in self.controller.diagnostics_snapshot().items()}
        if not force and snapshot == self._diagnostics_snapshot:
            return
        self._diagnostics_snapshot = snapshot
        self._diagnostics_entries = [
            {"id": key, "label": diagnostic_label(key), "value": snapshot.get(key, "-")}
            for key in DIAGNOSTIC_KEYS
        ]
        self.diagnosticsEntriesChanged.emit()

    def _show_toast(self, message: str, level: str, timeout_ms: int) -> None:
        self._toast_level = level or "info"
        self._toast_message = message or ""
        self.toastLevelChanged.emit()
        self.toastMessageChanged.emit()
        if self._toast_message:
            self._toast_timer.start(timeout_ms)
        else:
            self._toast_timer.stop()

    @staticmethod
    def _normalize_options(items: list[tuple[str, str]]) -> list[dict]:
        return [{"value": str(value), "label": str(label)} for value, label in items]
