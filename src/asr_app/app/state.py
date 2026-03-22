from dataclasses import asdict, dataclass

from ..config import asr_provider_labels, input_source_labels, optimization_level_labels, DEFAULT_OPTIMIZATION_LEVEL
from ..i18n import t
from ..modes import MODE_NON_STREAM, MODE_NON_STREAM_POLISH, MODE_REALTIME, MODE_REALTIME_POLISH
from ..runtime_env import LOG_PATH


def mode_labels() -> dict[str, str]:
    return {
        MODE_NON_STREAM: t("mode.non_stream"),
        MODE_NON_STREAM_POLISH: t("mode.non_stream_polish"),
        MODE_REALTIME: t("mode.realtime"),
        MODE_REALTIME_POLISH: t("mode.realtime_polish"),
    }


def mode_descriptions() -> dict[str, str]:
    return {
        MODE_NON_STREAM: t("mode_desc.non_stream"),
        MODE_NON_STREAM_POLISH: t("mode_desc.non_stream_polish"),
        MODE_REALTIME: t("mode_desc.realtime"),
        MODE_REALTIME_POLISH: t("mode_desc.realtime_polish"),
    }


def hotkey_mode_labels() -> dict[str, str]:
    return {
        "hold": t("hotkey_mode.hold"),
        "toggle": t("hotkey_mode.toggle"),
    }


def status_labels() -> dict[str, str]:
    return {
        "idle": t("status.idle"),
        "recording": t("status.recording"),
        "transcribing": t("status.transcribing"),
        "realtime_streaming": t("status.realtime_streaming"),
        "polishing": t("status.polishing"),
        "injecting": t("status.injecting"),
        "completed": t("status.completed"),
        "failed": t("status.failed"),
    }


def remote_phone_state_labels() -> dict[str, str]:
    return {
        "PHONE_OFFLINE": t("remote_state.PHONE_OFFLINE"),
        "PHONE_CONNECTED": t("remote_state.PHONE_CONNECTED"),
        "PHONE_RECONNECTING": t("remote_state.PHONE_RECONNECTING"),
        "PHONE_READY": t("remote_state.PHONE_READY"),
        "STARTING": t("remote_state.STARTING"),
        "RECORDING": t("remote_state.RECORDING"),
        "STOPPING": t("remote_state.STOPPING"),
        "ERROR": t("remote_state.ERROR"),
    }


def _resolve_active_model(mode: str, non_stream_model: str, realtime_model: str, polish_model: str) -> tuple[str, str]:
    is_realtime = mode in {MODE_REALTIME, MODE_REALTIME_POLISH}
    use_polish = mode in {MODE_NON_STREAM_POLISH, MODE_REALTIME_POLISH}
    main_model = realtime_model if is_realtime else non_stream_model
    labels = mode_labels()
    details = [labels.get(mode, mode)]
    if use_polish:
        details.append(t("label.polish_model", model=polish_model or "-"))
    return main_model or "-", " | ".join(details)


@dataclass
class AppState:
    current_mode: str = MODE_NON_STREAM
    asr_provider: str = "aliyun"
    app_status: str = "idle"
    recording: bool = False
    hotkeys_registered: bool = False
    is_admin: bool = False
    osd_ready: bool = False
    tray_enabled: bool = True
    asr_api_key_configured: bool = False
    text_polish_api_key_configured: bool = False
    input_source_type: str = "local_mic"
    input_device_name: str = ""
    asr_base_url: str = ""
    text_polish_base_url: str = ""
    asr_non_stream_model: str = ""
    asr_realtime_model: str = ""
    text_polish_model: str = ""
    polish_output_key: str = "text"
    optimization_level: str = DEFAULT_OPTIMIZATION_LEVEL
    last_error: str = ""
    last_warning: str = ""
    last_result_preview: str = ""
    log_path: str = LOG_PATH
    startup_minimized: bool = False
    hotkey_mode: str = "hold"
    primary_hotkey: str = "caps lock"
    secondary_hotkey: str = "f8"
    remote_phone_service_running: bool = False
    remote_phone_state: str = "PHONE_OFFLINE"
    remote_phone_ready: bool = False
    remote_phone_url: str = ""
    remote_phone_device_name: str = ""
    remote_phone_browser: str = ""
    remote_phone_platform: str = ""
    remote_phone_last_error: str = ""
    remote_phone_session_id: str = ""
    remote_phone_connected: bool = False
    remote_phone_cert_status: str = "missing"

    def to_dict(self) -> dict:
        data = asdict(self)
        active_model_name, active_model_detail = _resolve_active_model(
            self.current_mode,
            self.asr_non_stream_model,
            self.asr_realtime_model,
            self.text_polish_model,
        )
        data["mode_label"] = mode_labels().get(self.current_mode, self.current_mode)
        data["mode_description"] = mode_descriptions().get(self.current_mode, "")
        data["asr_provider_label"] = asr_provider_labels().get(self.asr_provider, self.asr_provider)
        data["status_label"] = status_labels().get(self.app_status, self.app_status)
        data["hotkey_mode_label"] = hotkey_mode_labels().get(self.hotkey_mode, self.hotkey_mode)
        data["optimization_level_label"] = optimization_level_labels().get(self.optimization_level, self.optimization_level)
        data["active_model_name"] = active_model_name
        data["active_model_detail"] = active_model_detail
        data["input_source_label"] = input_source_labels().get(self.input_source_type, self.input_source_type)
        data["remote_phone_state_label"] = remote_phone_state_labels().get(self.remote_phone_state, self.remote_phone_state)
        return data
