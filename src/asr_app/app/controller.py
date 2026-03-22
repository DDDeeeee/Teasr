from __future__ import annotations

import ctypes
import threading
from collections import deque
from collections.abc import Callable

import keyboard
import sounddevice as sd
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .. import runtime_core as core
from ..config import AppConfig, asr_provider_labels, input_source_labels, optimization_level_labels
from ..modes import MODE_NON_STREAM, MODE_REALTIME, MODE_REALTIME_POLISH
from ..services.audio_recorder import AudioRecorder
from ..services.audio_sources import LocalMicSource, RemotePhoneSource
from ..services.remote_phone_runtime import RemotePhoneRuntime
from ..services.settings_service import HOTKEY_MODE_HOLD, HOTKEY_MODE_TOGGLE, SettingsService
from ..i18n import (
    get_lang,
    set_lang,
    LOG_TAG_DONE,
    LOG_TAG_ERR,
    LOG_TAG_FINAL,
    LOG_TAG_GUI,
    LOG_TAG_REC,
    LOG_TAG_RESULT,
    LOG_TAG_TEST,
    LOG_TAG_WARN,
    t,
)
from ..ui.view_data import DIAGNOSTIC_KEYS
from .state import AppState, hotkey_mode_labels, mode_labels


class AppController(QObject):
    state_changed = pyqtSignal(dict)
    logs_changed = pyqtSignal(str)
    notification = pyqtSignal(str, str)
    devices_changed = pyqtSignal(list)

    def __init__(self, settings_service: SettingsService):
        super().__init__()
        self.settings_service = settings_service
        self.settings = self.settings_service.load()
        self.settings_service.apply_runtime(self.settings)

        self.state = AppState(
            current_mode=self.settings.get("default_mode", MODE_NON_STREAM),
            tray_enabled=bool(self.settings.get("enable_tray", True)),
            startup_minimized=bool(self.settings.get("start_minimized", False)),
            asr_api_key_configured=bool(self.settings.get("asr_api_key") or self.settings.get("api_key", "")),
            text_polish_api_key_configured=bool(self.settings.get("text_polish_api_key") or self.settings.get("api_key", "")),
            input_source_type=self.settings.get("input_source_type", "local_mic"),
            asr_base_url=self.settings.get("asr_base_url") or self.settings.get("base_url", ""),
            text_polish_base_url=self.settings.get("text_polish_base_url") or self.settings.get("base_url", ""),
            asr_non_stream_model=self.settings.get("asr_non_stream_model", ""),
            asr_realtime_model=self.settings.get("asr_realtime_model", ""),
            text_polish_model=self.settings.get("text_polish_model", ""),
            polish_output_key=self.settings.get("polish_output_key", "text"),
            hotkey_mode=self.settings.get("hotkey_mode", HOTKEY_MODE_HOLD),
            primary_hotkey=self.settings.get("primary_hotkey", "caps lock"),
            secondary_hotkey=self.settings.get("secondary_hotkey", "f8"),
            optimization_level=self.settings.get("optimization_level", "normal"),
        )
        self._state_lock = threading.Lock()
        self._log_lines = deque(maxlen=240)
        self._audio_devices: list[dict] = []
        self._hotkey_hooks: list[Callable[[], None]] = []
        self._toggle_pressed_hotkeys: set[str] = set()
        self._stop_in_progress = False
        self._bubble = None
        self._indicator = None
        self._recorder: AudioRecorder | None = None
        self._log_listener_attached = False
        self._remote_phone_runtime = RemotePhoneRuntime(self.config)
        self._remote_status_timer = QTimer(self)
        self._remote_status_timer.setInterval(1000)
        self._remote_status_timer.timeout.connect(self._refresh_remote_phone_status)
        self._remote_status_polling_enabled = False

        self._attach_log_listener()
        self.refresh_audio_devices(emit=False)
        self._sync_runtime_flags()
        self._sync_remote_phone_runtime()
        self._rebuild_recorder()
        self._refresh_remote_phone_status()
        self._emit_state()

    @property
    def config(self) -> AppConfig:
        return AppConfig.from_mapping(self.settings)

    @property
    def asr_api_key(self) -> str:
        return self.config.resolved_asr_api_key()

    @property
    def text_polish_api_key(self) -> str:
        return self.config.resolved_text_polish_api_key()

    @property
    def audio_devices(self) -> list[dict]:
        return list(self._audio_devices)

    def start(self) -> None:
        self._ensure_hotkeys_registered()
        self._ensure_osd_for_mode()
        self._sync_remote_phone_runtime()
        self._emit_state()

    def shutdown(self) -> None:
        self._remote_status_timer.stop()
        self._unregister_hotkeys()
        self._force_release_keyboard_hooks()

        if self._recorder is not None:
            try:
                self._recorder.cancel_recording(restore_caps_lock=True)
            except Exception:
                core.logger.exception("Failed to cleanup recorder during shutdown")

        self._destroy_osd()
        self._destroy_indicator()

        try:
            self._remote_phone_runtime.stop_service()
        except Exception:
            core.logger.exception("Failed to stop remote phone runtime during shutdown")

        if self._log_listener_attached:
            core.remove_log_listener(self._handle_log_message)
            self._log_listener_attached = False

    def mode_options(self) -> list[tuple[str, str]]:
        return list(mode_labels().items())

    def hotkey_mode_options(self) -> list[tuple[str, str]]:
        return list(hotkey_mode_labels().items())

    def optimization_level_options(self) -> list[tuple[str, str]]:
        return list(optimization_level_labels().items())

    def input_source_options(self) -> list[tuple[str, str]]:
        return list(input_source_labels().items())

    def set_language(self, lang: str) -> None:
        previous_lang = get_lang()
        set_lang(lang)
        effective_changed = get_lang() != previous_lang
        self.settings = self.settings_service.save({"language": lang})
        if self._bubble is not None and hasattr(self._bubble, "refresh_language"):
            self._bubble.refresh_language()
        # Keep language switching as a UI-only action. Restarting the remote phone
        # service synchronously from the GUI thread has been unstable, and it is
        # unnecessary when the effective language did not actually change
        # (for example, Follow System -> Chinese on a Chinese system).
        if effective_changed and self._remote_phone_runtime.is_service_running():
            core.log(f"{LOG_TAG_GUI} Language changed; the phone page will update after the next service reconnect")
        self.refresh_audio_devices(emit=True)
        self._refresh_remote_phone_status()
        self._emit_state()


    def set_mode(self, mode: str) -> None:
        if not mode or mode == self.state.current_mode:
            return
        if self._is_recording_locked(t("notify.recording_locked_mode")):
            return
        self.settings = self.settings_service.save({"default_mode": mode})
        self._sync_runtime_flags()
        self._rebuild_recorder()
        self._ensure_osd_for_mode()
        self._emit_state()
        core.log(f"{LOG_TAG_GUI} {t('log.mode_switched', value=mode_labels().get(mode, mode))}")

    def set_hotkey_mode(self, mode: str) -> None:
        if not mode or mode == self.state.hotkey_mode:
            return
        if self._is_recording_locked(t("notify.recording_locked_hotkey_mode")):
            return
        self.settings = self.settings_service.save({"hotkey_mode": mode})
        self._sync_runtime_flags()
        self._ensure_hotkeys_registered(force=True)
        self._emit_state()
        core.log(f"{LOG_TAG_GUI} {t('log.hotkey_mode_switched', value=hotkey_mode_labels().get(mode, mode))}")

    def set_optimization_level(self, level: str) -> None:
        if not level or level == self.state.optimization_level:
            return
        self.settings = self.settings_service.save({"optimization_level": level})
        self._sync_runtime_flags()
        self._rebuild_recorder()
        self._emit_state()
        core.log(f"{LOG_TAG_GUI} {t('log.optimization_switched', value=optimization_level_labels().get(level, level))}")

    def set_input_source_type(self, input_source_type: str) -> None:
        if not input_source_type or input_source_type == self.state.input_source_type:
            return
        if self._is_recording_locked(t("notify.recording_locked_input_source")):
            return
        self.settings = self.settings_service.save({"input_source_type": input_source_type})
        self._sync_runtime_flags()
        self._sync_remote_phone_runtime()
        self._rebuild_recorder()
        self._refresh_remote_phone_status()
        self._emit_state()
        core.log(f"{LOG_TAG_GUI} {t('log.input_source_switched', value=input_source_labels().get(input_source_type, input_source_type))}")

    def refresh_audio_devices(self, emit: bool = True) -> list[dict]:
        devices: list[dict] = []
        try:
            hostapis = sd.query_hostapis()
            for index, item in enumerate(sd.query_devices()):
                if item.get("max_input_channels", 0) <= 0:
                    continue
                hostapi_index = int(item.get("hostapi", -1))
                hostapi_name = str(hostapis[hostapi_index]["name"]) if 0 <= hostapi_index < len(hostapis) else "Unknown"
                label = f"{item['name']} ({hostapi_name})"
                devices.append({"id": str(index), "label": label})
        except Exception as exc:
            core.logger.exception("Failed to query audio devices")
            self.notification.emit(t("notify.read_audio_devices_failed", error=exc), "warning")

        self._audio_devices = devices
        selected = str(self.settings.get("audio_input_device", ""))
        selected_label = t("device.system_default")
        for item in devices:
            if item["id"] == selected:
                selected_label = item["label"]
                break
        self.state.input_device_name = selected_label

        if emit:
            self.devices_changed.emit(devices)
            self._emit_state()
        return devices

    def save_settings(self, updates: dict) -> dict:
        if self._is_recording_locked(t("notify.recording_locked_save_settings")):
            return self.settings

        merged = dict(self.settings)
        merged.update(updates)
        hotkeys = self._normalized_hotkeys_from_mapping(merged)
        if not hotkeys:
            self.notification.emit(t("notify.need_one_hotkey"), "error")
            return self.settings

        try:
            for hotkey in hotkeys:
                keyboard.parse_hotkey_combinations(hotkey)
        except Exception as exc:
            self.notification.emit(t("notify.invalid_hotkey_format", error=exc), "error")
            return self.settings

        self.settings = self.settings_service.save(updates)
        self._sync_runtime_flags()
        self._sync_remote_phone_runtime()
        self._rebuild_recorder()
        self._ensure_osd_for_mode()
        self._ensure_hotkeys_registered(force=True)
        self.refresh_audio_devices(emit=True)
        self._refresh_remote_phone_status()
        self._emit_state()
        self.notification.emit(t("notify.settings_saved"), "info")
        return self.settings

    def restart_remote_phone_service(self) -> None:
        if self.state.input_source_type != "remote_phone":
            self.notification.emit(t("notify.remote_mic_not_selected"), "warning")
            return
        try:
            self._remote_phone_runtime.config = self.config
            self._remote_phone_runtime.restart_service()
            self._set_remote_status_polling(True)
            self._refresh_remote_phone_status()
            self.notification.emit(t("notify.remote_mic_restarted"), "info")
        except Exception as exc:
            core.logger.exception("Failed to restart remote phone service")
            self.notification.emit(t("notify.remote_mic_restart_failed", error=exc), "error")
            self._set_state(remote_phone_last_error=str(exc), last_error=str(exc))

    def start_recording(self) -> None:
        if self._stop_in_progress:
            return
        config = self.config
        if config.asr_provider == "doubao":
            if not config.asr_app_key or not config.asr_api_key:
                self._set_state(app_status="failed", last_error="Missing Doubao credentials", asr_api_key_configured=False)
                self.notification.emit(t("notify.configure_doubao_credentials"), "error")
                return
        elif not self.asr_api_key:
            self._set_state(app_status="failed", last_error="Missing ASR API Key", asr_api_key_configured=False)
            self.notification.emit(t("notify.configure_asr_api_key"), "error")
            return
        if self._recorder is not None and self._recorder.recording:
            return

        self._ensure_osd_for_mode()
        if self._recorder is None:
            self._rebuild_recorder()

        if self.state.input_source_type == "remote_phone":
            self._start_remote_phone_service_if_needed(force=True)
            self._refresh_remote_phone_status()
            if not self.state.remote_phone_ready:
                self.notification.emit(t("notify.remote_mic_not_ready"), "warning")
                return

        try:
            assert self._recorder is not None
            self._recorder.start_recording()
        except Exception as exc:
            core.logger.exception("Start recording failed")
            self.notification.emit(t("notify.start_recording_failed", error=exc), "error")
            self._set_state(app_status="failed", last_error=str(exc), recording=False)
            return

        status = "realtime_streaming" if self.state.current_mode in {MODE_REALTIME, MODE_REALTIME_POLISH} else "recording"
        self._set_state(app_status=status, recording=True, last_error="")

    def stop_recording(self) -> None:
        if self._stop_in_progress or self._recorder is None or not self._recorder.recording:
            return
        status = "polishing" if self.state.current_mode == MODE_REALTIME_POLISH else "transcribing"
        self._run_stop_job(self._recorder.stop_and_transcribe, status, t("notify.stop_recording_error"))

    def toggle_recording(self) -> None:
        if self._recorder is not None and self._recorder.recording:
            self.stop_recording()
        else:
            self.start_recording()

    def handle_hotkey_press(self) -> None:
        try:
            self.start_recording()
        except Exception as exc:
            core.logger.exception("Hotkey press handling failed")
            self.notification.emit(t("notify.hotkey_start_failed", error=exc), "error")
            self._set_state(app_status="failed", recording=False, last_error=str(exc))

    def handle_hotkey_release(self) -> None:
        if self._stop_in_progress or self._recorder is None or not self._recorder.recording:
            return
        status = "polishing" if self.state.current_mode == MODE_REALTIME_POLISH else "transcribing"
        self._run_stop_job(self._recorder.stop_and_transcribe_with_toggle, status, t("notify.stop_hotkey_recording_error"))

    def diagnostics_snapshot(self) -> dict:
        return {
            "asr_provider": asr_provider_labels().get(self.state.asr_provider, self.state.asr_provider),
            "admin_rights": t("common.yes") if self.state.is_admin else t("common.no"),
            "hotkey_registered": t("common.registered") if self.state.hotkeys_registered else t("common.not_registered"),
            "hotkey_mode": hotkey_mode_labels().get(self.state.hotkey_mode, self.state.hotkey_mode),
            "primary_hotkey": self.state.primary_hotkey or t("common.not_configured"),
            "secondary_hotkey": self.state.secondary_hotkey or t("common.not_configured"),
            "osd_status": t("common.ready") if self.state.osd_ready else t("common.disabled"),
            "current_mode": mode_labels().get(self.state.current_mode, self.state.current_mode),
            "current_input_source": input_source_labels().get(self.state.input_source_type, self.state.input_source_type),
            "current_input_device": self.state.input_device_name,
            "phone_service": t("common.running") if self.state.remote_phone_service_running else t("common.not_started"),
            "phone_connection": self.state.to_dict().get("remote_phone_state_label", self.state.remote_phone_state),
            "phone_url": self.state.remote_phone_url or "-",
            "phone_device": self.state.remote_phone_device_name or "-",
            "phone_gain": f"{self.config.remote_phone_input_gain:.2f}x",
            "remote_session_id": self.state.remote_phone_session_id or "-",
            "remote_cert": self.state.remote_phone_cert_status or t("common.missing"),
            "log_path": self.state.log_path,
            "asr_base_url": self.state.asr_base_url or t("common.default"),
            "text_polish_base_url": self.state.text_polish_base_url or t("common.default"),
            "non_stream_model": self.state.asr_non_stream_model,
            "realtime_model": self.state.asr_realtime_model,
            "polish_model": self.state.text_polish_model,
            "polish_output_key": self.state.polish_output_key,
            "asr_api_key": self._mask_secret(self.asr_api_key),
            "text_polish_api_key": self._mask_secret(self.text_polish_api_key),
            "recent_warning": self.state.last_warning or t("common.none"),
            "recent_error": self.state.last_error or t("common.none"),
            "recent_remote_error": self.state.remote_phone_last_error or t("common.none"),
        }

    def recent_logs_text(self) -> str:
        return "\n".join(self._log_lines)

    def test_asr_non_stream(self) -> None:
        config = self.config
        from ..services.asr.base import AsrCredentials
        credentials = AsrCredentials(
            api_key=config.resolved_asr_api_key(),
            app_key=config.asr_app_key,
            base_url=config.resolved_asr_base_url(),
        )
        provider_name = config.asr_provider
        model_name = config.asr_non_stream_model

        def _worker() -> None:
            from ..services.asr.testing import test_non_stream_asr
            core.log(f"{LOG_TAG_TEST} {t('log.testing_non_stream')}")
            success, detail = test_non_stream_asr(provider_name, credentials, model_name)
            if success:
                core.log(f"{LOG_TAG_TEST} {t('log.testing_non_stream_passed', detail=detail)}")
                self.notification.emit(t("notify.non_stream_test_passed"), "info")
            else:
                core.log(f"{LOG_TAG_TEST} {t('log.testing_non_stream_failed', detail=detail)}")
                self.notification.emit(t("notify.non_stream_test_failed", detail=detail), "error")

        threading.Thread(target=_worker, daemon=True).start()

    def test_text_polish(self) -> None:
        config = self.config

        def _worker() -> None:
            from ..services.asr.testing import test_text_polish
            core.log(f"{LOG_TAG_TEST} {t('log.testing_text_polish')}")
            success, detail = test_text_polish(
                config.resolved_text_polish_api_key(),
                config.resolved_text_polish_base_url(),
                config.text_polish_model,
            )
            if success:
                core.log(f"{LOG_TAG_TEST} {t('log.testing_text_polish_passed', detail=detail)}")
                self.notification.emit(t("notify.text_polish_test_passed"), "info")
            else:
                core.log(f"{LOG_TAG_TEST} {t('log.testing_text_polish_failed', detail=detail)}")
                self.notification.emit(t("notify.text_polish_test_failed", detail=detail), "error")

        threading.Thread(target=_worker, daemon=True).start()

    def _attach_log_listener(self) -> None:
        if self._log_listener_attached:
            return
        core.add_log_listener(self._handle_log_message)
        self._log_listener_attached = True

    def _is_recording_locked(self, message: str) -> bool:
        if self._recorder is None or not self._recorder.recording:
            return False
        self.notification.emit(message, "warning")
        return True

    def _run_stop_job(self, job: Callable[[], None], status: str, error_prefix: str) -> None:
        self._stop_in_progress = True
        self._set_state(app_status=status, recording=False)

        def _worker() -> None:
            try:
                job()
                self._set_state(app_status="completed", recording=False)
            except Exception as exc:
                core.logger.exception("Stop recording failed")
                self.notification.emit(f"{error_prefix}: {exc}", "error")
                self._set_state(app_status="failed", recording=False, last_error=str(exc))
            finally:
                self._stop_in_progress = False
                self._refresh_remote_phone_status()

        threading.Thread(target=_worker, daemon=True).start()

    def _sync_runtime_flags(self) -> None:
        config = self.config
        self._remote_phone_runtime.config = config
        self.state.current_mode = config.default_mode
        self.state.asr_provider = config.asr_provider
        self.state.asr_api_key_configured = bool(config.asr_api_key)
        self.state.text_polish_api_key_configured = bool(config.text_polish_api_key or config.asr_api_key)
        self.state.asr_base_url = config.asr_base_url
        self.state.text_polish_base_url = config.text_polish_base_url
        self.state.asr_non_stream_model = config.asr_non_stream_model
        self.state.asr_realtime_model = config.asr_realtime_model
        self.state.text_polish_model = config.text_polish_model
        self.state.polish_output_key = config.polish_output_key
        self.state.tray_enabled = bool(config.enable_tray)
        self.state.startup_minimized = bool(config.start_minimized)
        self.state.hotkey_mode = config.hotkey_mode
        self.state.primary_hotkey = config.primary_hotkey
        self.state.secondary_hotkey = config.secondary_hotkey
        self.state.optimization_level = config.optimization_level
        self.state.input_source_type = config.input_source_type
        try:
            self.state.is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            self.state.is_admin = False
            core.logger.exception("Admin check failed in GUI controller")

    def _sync_remote_phone_runtime(self) -> None:
        should_run_remote = self.state.input_source_type == "remote_phone" and bool(self.config.remote_phone_enabled)
        if should_run_remote:
            self._start_remote_phone_service_if_needed(force=True)
            self._set_remote_status_polling(True)
            return

        self._set_remote_status_polling(False)
        self._set_state(
            remote_phone_service_running=False,
            remote_phone_state="PHONE_OFFLINE",
            remote_phone_ready=False,
            remote_phone_device_name="",
            remote_phone_browser="",
            remote_phone_platform="",
            remote_phone_last_error="",
            remote_phone_session_id="",
            remote_phone_connected=False,
            remote_phone_cert_status="missing",
        )

        def _stop_in_background() -> None:
            try:
                self._remote_phone_runtime.stop_service()
            except Exception:
                core.logger.exception("Failed to stop remote phone runtime during input source switch")

        threading.Thread(target=_stop_in_background, daemon=True).start()

    def _set_remote_status_polling(self, enabled: bool) -> None:
        if enabled == self._remote_status_polling_enabled:
            return
        self._remote_status_polling_enabled = enabled
        if enabled:
            self._remote_status_timer.start()
        else:
            self._remote_status_timer.stop()

    def _start_remote_phone_service_if_needed(self, force: bool = False) -> None:
        config = self.config
        should_start = bool(config.remote_phone_enabled and (force or config.input_source_type == "remote_phone"))
        if not should_start:
            return
        try:
            self._remote_phone_runtime.config = config
            self._remote_phone_runtime.start_service()
        except Exception as exc:
            core.logger.exception("Failed to start remote phone runtime")
            self._set_state(remote_phone_last_error=str(exc), last_error=str(exc))

    def _refresh_remote_phone_status(self) -> None:
        snapshot = self._remote_phone_runtime.status_snapshot()
        self._set_state(
            remote_phone_service_running=bool(snapshot.get("service_running")),
            remote_phone_state=str(snapshot.get("state", "PHONE_OFFLINE")),
            remote_phone_ready=bool(snapshot.get("ready")),
            remote_phone_url=str(snapshot.get("url", "")),
            remote_phone_device_name=str(snapshot.get("device_name") or ""),
            remote_phone_browser=str(snapshot.get("browser") or ""),
            remote_phone_platform=str(snapshot.get("platform") or ""),
            remote_phone_last_error=str(snapshot.get("last_error") or snapshot.get("last_service_error") or ""),
            remote_phone_session_id=str(snapshot.get("session_id") or ""),
            remote_phone_connected=bool(snapshot.get("connected")),
            remote_phone_cert_status=str(snapshot.get("cert_status") or "missing"),
        )

    def _rebuild_recorder(self) -> None:
        if self._recorder is not None and self._recorder.recording:
            return

        from ..services.asr import create_provider
        from ..services.asr.base import AsrCredentials

        config = self.config
        device_value = str(self.settings.get("audio_input_device", ""))
        device = int(device_value) if device_value.isdigit() else None

        credentials = AsrCredentials(
            api_key=config.resolved_asr_api_key(),
            app_key=config.asr_app_key,
            base_url=config.resolved_asr_base_url(),
        )
        provider = create_provider(config.asr_provider, credentials)

        if config.input_source_type == "remote_phone":
            source = RemotePhoneSource(self._remote_phone_runtime, gain=config.remote_phone_input_gain)
        else:
            source = LocalMicSource(sample_rate=16000, input_device=device)

        self._recorder = AudioRecorder(
            mode=self.state.current_mode,
            config=config,
            input_device=device,
            input_source=source,
            asr_provider=provider,
        )

    def _ensure_osd_for_mode(self) -> None:
        if self.state.current_mode in {MODE_REALTIME, MODE_REALTIME_POLISH}:
            if self._bubble is None:
                from ..osd_widget import OsdBubble

                self._bubble = OsdBubble()
                core.osd_bubble = self._bubble
                core.log(f"{LOG_TAG_GUI} {t('log.osd_initialized')}")
            self.state.osd_ready = True
            self._destroy_indicator()
            return

        self._destroy_osd()
        self._ensure_indicator()

    def _ensure_indicator(self) -> None:
        if self._indicator is not None:
            return
        from ..ui.recording_overlay import RecordingOverlay

        self._indicator = RecordingOverlay()
        core.recording_indicator = self._indicator
        core.log(f"{LOG_TAG_GUI} {t('log.indicator_initialized')}")

    def _destroy_indicator(self) -> None:
        if self._indicator is not None:
            try:
                self._indicator.hide()
                self._indicator.deleteLater()
            except Exception:
                core.logger.exception("Failed to destroy recording indicator")
        self._indicator = None
        core.recording_indicator = None

    def _destroy_osd(self) -> None:
        if self._bubble is not None:
            try:
                self._bubble.hide()
                self._bubble.deleteLater()
            except Exception:
                core.logger.exception("Failed to destroy OSD bubble")
        self._bubble = None
        core.osd_bubble = None
        self.state.osd_ready = False

    def _ensure_hotkeys_registered(self, force: bool = False) -> None:
        if force:
            self._unregister_hotkeys()
        elif self._hotkey_hooks:
            self.state.hotkeys_registered = True
            return

        hotkeys = self._configured_hotkeys()
        if not hotkeys:
            self.state.hotkeys_registered = False
            self.notification.emit(t("notify.invalid_hotkey"), "warning")
            return

        try:
            if self.state.hotkey_mode == HOTKEY_MODE_TOGGLE:
                for hotkey in hotkeys:
                    keyboard.parse_hotkey_combinations(hotkey)
                    remover = keyboard.hook_key(hotkey, self._make_toggle_callback(hotkey))
                    self._hotkey_hooks.append(self._normalize_hotkey_remover(remover, is_hotkey=False))
            else:
                for hotkey in hotkeys:
                    remover = keyboard.hook_key(hotkey, self._make_hold_callback())
                    self._hotkey_hooks.append(self._normalize_hotkey_remover(remover, is_hotkey=False))

            self.state.hotkeys_registered = bool(self._hotkey_hooks)
            core.log(
                f"{LOG_TAG_GUI} {t('log.hotkeys_registered', hotkeys=', '.join(hotkeys), mode=hotkey_mode_labels().get(self.state.hotkey_mode, self.state.hotkey_mode))}"
            )
        except Exception as exc:
            self._unregister_hotkeys()
            self.state.hotkeys_registered = False
            core.logger.exception("Hotkey register failed in GUI controller")
            self.notification.emit(t("notify.register_hotkey_failed", error=exc), "error")

    def _configured_hotkeys(self) -> list[str]:
        return self._normalized_hotkeys_from_mapping(
            {
                "primary_hotkey": self.state.primary_hotkey,
                "secondary_hotkey": self.state.secondary_hotkey,
            }
        )

    @staticmethod
    def _normalized_hotkeys_from_mapping(values: dict) -> list[str]:
        hotkeys: list[str] = []
        for raw in (values.get("primary_hotkey", ""), values.get("secondary_hotkey", "")):
            hotkey = str(raw or "").strip()
            if hotkey and hotkey not in hotkeys:
                hotkeys.append(hotkey)
        return hotkeys

    def _unregister_hotkeys(self) -> None:
        for remover in self._hotkey_hooks:
            try:
                remover()
            except KeyError:
                continue
            except Exception:
                core.logger.exception("Failed to remove keyboard hotkey")
        self._hotkey_hooks = []
        self._toggle_pressed_hotkeys.clear()
        self._force_release_keyboard_hooks()
        self.state.hotkeys_registered = False

    @staticmethod
    def _force_release_keyboard_hooks() -> None:
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            core.logger.exception("Failed to clear keyboard hotkeys")
        try:
            keyboard.unhook_all()
        except Exception:
            core.logger.exception("Failed to clear keyboard hooks")

    @staticmethod
    def _normalize_hotkey_remover(remover, *, is_hotkey: bool):
        if callable(remover):
            return remover

        def _remove() -> None:
            if is_hotkey:
                keyboard.remove_hotkey(remover)
            else:
                keyboard.unhook(remover)

        return _remove

    def _make_toggle_callback(self, hotkey: str):
        def _callback(event) -> None:
            if event.event_type == keyboard.KEY_DOWN:
                if hotkey in self._toggle_pressed_hotkeys:
                    return
                self._toggle_pressed_hotkeys.add(hotkey)
                self.toggle_recording()
            elif event.event_type == keyboard.KEY_UP:
                self._toggle_pressed_hotkeys.discard(hotkey)

        return _callback

    def _make_hold_callback(self):
        def _callback(event) -> None:
            if event.event_type == keyboard.KEY_DOWN:
                self.handle_hotkey_press()
            elif event.event_type == keyboard.KEY_UP:
                self.handle_hotkey_release()

        return _callback

    def _handle_log_message(self, message: str) -> None:
        self._log_lines.append(message)
        self.logs_changed.emit(self.recent_logs_text())

        if LOG_TAG_ERR in message:
            self._set_state(app_status="failed", last_error=message)
        elif LOG_TAG_WARN in message:
            self._set_state(last_warning=message)
        elif LOG_TAG_FINAL in message or LOG_TAG_RESULT in message:
            preview = message.split(":", 1)[-1].strip()
            self._set_state(last_result_preview=preview)
        elif LOG_TAG_REC in message:
            status = "realtime_streaming" if self.state.current_mode in {MODE_REALTIME, MODE_REALTIME_POLISH} else "recording"
            self._set_state(app_status=status, recording=True)
        elif LOG_TAG_DONE in message:
            self._set_state(app_status="completed", recording=False)

    def _set_state(self, **updates) -> None:
        changed = False
        with self._state_lock:
            for key, value in updates.items():
                if not hasattr(self.state, key):
                    continue
                if getattr(self.state, key) == value:
                    continue
                setattr(self.state, key, value)
                changed = True
        if changed:
            self._emit_state()

    def _emit_state(self) -> None:
        self.state_changed.emit(self.state.to_dict())

    @staticmethod
    def _mask_secret(value: str) -> str:
        if not value:
            return t("common.not_configured")
        if len(value) <= 8:
            return "*" * len(value)
        return f"{value[:4]}***{value[-4:]}"
