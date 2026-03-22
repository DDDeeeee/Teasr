from ..i18n import t


INSIGHT_LABELS = [
    ("asr_api_key", "asr_api_key_configured"),
    ("text_polish_api_key", "text_polish_api_key_configured"),
    ("hotkey_mode", "hotkey_mode"),
    ("primary_hotkey", "primary_hotkey"),
    ("secondary_hotkey", "secondary_hotkey"),
    ("polish_model", "text_polish_model"),
    ("polish_output_key", "polish_output_key"),
    ("asr_base_url", "asr_base_url"),
    ("text_polish_base_url", "text_polish_base_url"),
]

DIAGNOSTIC_KEYS = [
    "asr_provider",
    "admin_rights",
    "hotkey_registered",
    "hotkey_mode",
    "primary_hotkey",
    "secondary_hotkey",
    "osd_status",
    "current_mode",
    "current_input_source",
    "current_input_device",
    "phone_service",
    "phone_connection",
    "phone_url",
    "phone_device",
    "phone_gain",
    "remote_session_id",
    "remote_cert",
    "log_path",
    "asr_base_url",
    "text_polish_base_url",
    "non_stream_model",
    "realtime_model",
    "polish_model",
    "polish_output_key",
    "asr_api_key",
    "text_polish_api_key",
    "recent_warning",
    "recent_error",
    "recent_remote_error",
]

LOG_LEVEL_OPTIONS = ["DEBUG", "INFO", "WARNING", "ERROR"]


def diagnostic_label(key: str) -> str:
    return t(f"diag.{key}")
