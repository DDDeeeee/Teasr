import os
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from .i18n import t
from .modes import MODE_NON_STREAM
from .runtime_env import load_project_env


DEFAULT_ASR_PROVIDER = "aliyun"
DEFAULT_LANGUAGE = ""
DEFAULT_ASR_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_TEXT_POLISH_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_BASE_URL = DEFAULT_TEXT_POLISH_BASE_URL
DEFAULT_NON_STREAM_MODEL = "qwen3-asr-flash"
DEFAULT_REALTIME_MODEL = "qwen3-asr-flash-realtime"
DEFAULT_TEXT_POLISH_MODEL = "qwen3.5-flash"
DEFAULT_TEXT_POLISH_OUTPUT_KEY = "text"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_HOTKEY_MODE = "hold"
DEFAULT_PRIMARY_HOTKEY = "caps lock"
DEFAULT_SECONDARY_HOTKEY = "f8"
DEFAULT_OPTIMIZATION_LEVEL = "normal"
DEFAULT_CUSTOM_POLISH_PROMPT = ""
DEFAULT_INPUT_SOURCE_TYPE = "local_mic"
DEFAULT_REMOTE_PHONE_ENABLED = True
DEFAULT_REMOTE_PHONE_HOST = ""
DEFAULT_REMOTE_PHONE_HTTP_PORT = 8764
DEFAULT_REMOTE_PHONE_CONTROL_PORT = 8765
DEFAULT_REMOTE_PHONE_AUDIO_PORT = 8766
DEFAULT_REMOTE_PHONE_AUTO_START = False
DEFAULT_REMOTE_PHONE_INPUT_GAIN = 0.75


def asr_provider_labels() -> dict[str, str]:
    return {
        "openai": "OpenAI",
        "aliyun": t("provider.aliyun"),
        "doubao": t("provider.doubao"),
    }


def input_source_labels() -> dict[str, str]:
    return {
        "local_mic": t("input_source.local_mic"),
        "remote_phone": t("input_source.remote_phone"),
    }


def optimization_level_labels() -> dict[str, str]:
    return {
        "light": t("optimization.light"),
        DEFAULT_OPTIMIZATION_LEVEL: t("optimization.normal"),
        "deep": t("optimization.deep"),
        "professional": t("optimization.professional"),
        "custom": t("optimization.custom"),
    }


CONFIG_KEYS = (
    "language",
    "asr_provider",
    "asr_api_key",
    "asr_app_key",
    "asr_base_url",
    "asr_non_stream_model",
    "asr_realtime_model",
    "text_polish_api_key",
    "text_polish_base_url",
    "text_polish_model",
    "polish_output_key",
    "default_mode",
    "input_source_type",
    "audio_input_device",
    "enable_tray",
    "start_minimized",
    "log_level",
    "hotkey_mode",
    "primary_hotkey",
    "secondary_hotkey",
    "optimization_level",
    "custom_polish_prompt",
    "remote_phone_enabled",
    "remote_phone_host",
    "remote_phone_http_port",
    "remote_phone_control_port",
    "remote_phone_audio_port",
    "remote_phone_auto_start",
    "remote_phone_input_gain",
)


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _coerce_str(value: Any, default: str) -> str:
    if value is None:
        return default
    return str(value).strip()


def _coerce_int(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class AppConfig:
    language: str = DEFAULT_LANGUAGE
    asr_provider: str = DEFAULT_ASR_PROVIDER
    asr_api_key: str = ""
    asr_app_key: str = ""
    asr_base_url: str = ""
    asr_non_stream_model: str = DEFAULT_NON_STREAM_MODEL
    asr_realtime_model: str = DEFAULT_REALTIME_MODEL
    text_polish_api_key: str = ""
    text_polish_base_url: str = ""
    text_polish_model: str = DEFAULT_TEXT_POLISH_MODEL
    polish_output_key: str = DEFAULT_TEXT_POLISH_OUTPUT_KEY
    default_mode: str = MODE_NON_STREAM
    input_source_type: str = DEFAULT_INPUT_SOURCE_TYPE
    audio_input_device: str = ""
    enable_tray: bool = True
    start_minimized: bool = False
    log_level: str = DEFAULT_LOG_LEVEL
    hotkey_mode: str = DEFAULT_HOTKEY_MODE
    primary_hotkey: str = DEFAULT_PRIMARY_HOTKEY
    secondary_hotkey: str = DEFAULT_SECONDARY_HOTKEY
    optimization_level: str = DEFAULT_OPTIMIZATION_LEVEL
    custom_polish_prompt: str = DEFAULT_CUSTOM_POLISH_PROMPT
    remote_phone_enabled: bool = DEFAULT_REMOTE_PHONE_ENABLED
    remote_phone_host: str = DEFAULT_REMOTE_PHONE_HOST
    remote_phone_http_port: int = DEFAULT_REMOTE_PHONE_HTTP_PORT
    remote_phone_control_port: int = DEFAULT_REMOTE_PHONE_CONTROL_PORT
    remote_phone_audio_port: int = DEFAULT_REMOTE_PHONE_AUDIO_PORT
    remote_phone_auto_start: bool = DEFAULT_REMOTE_PHONE_AUTO_START
    remote_phone_input_gain: float = DEFAULT_REMOTE_PHONE_INPUT_GAIN

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_project_env()
        legacy_api_key = os.getenv("API_KEY", "")
        legacy_base_url = os.getenv("BASE_URL") or os.getenv("DASHSCOPE_COMPATIBLE_BASE_URL", "")
        return cls(
            language=os.getenv("ASR_LANGUAGE", DEFAULT_LANGUAGE),
            asr_provider=os.getenv("ASR_PROVIDER", DEFAULT_ASR_PROVIDER),
            asr_api_key=os.getenv("ASR_API_KEY", legacy_api_key),
            asr_app_key=os.getenv("ASR_APP_KEY", ""),
            asr_base_url=os.getenv("ASR_BASE_URL", legacy_base_url),
            asr_non_stream_model=os.getenv("ASR_NON_STREAM_MODEL", DEFAULT_NON_STREAM_MODEL),
            asr_realtime_model=os.getenv("ASR_REALTIME_MODEL", DEFAULT_REALTIME_MODEL),
            text_polish_api_key=os.getenv("TEXT_POLISH_API_KEY", legacy_api_key),
            text_polish_base_url=os.getenv("TEXT_POLISH_BASE_URL", legacy_base_url),
            text_polish_model=os.getenv("ASR_TEXT_POLISH_MODEL", DEFAULT_TEXT_POLISH_MODEL),
            polish_output_key=os.getenv("TEXT_POLISH_OUTPUT_KEY", DEFAULT_TEXT_POLISH_OUTPUT_KEY),
            default_mode=os.getenv("ASR_DEFAULT_MODE", MODE_NON_STREAM),
            input_source_type=os.getenv("ASR_INPUT_SOURCE_TYPE", DEFAULT_INPUT_SOURCE_TYPE),
            log_level=os.getenv("ASR_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper(),
            hotkey_mode=os.getenv("ASR_HOTKEY_MODE", DEFAULT_HOTKEY_MODE),
            primary_hotkey=os.getenv("ASR_PRIMARY_HOTKEY", DEFAULT_PRIMARY_HOTKEY),
            secondary_hotkey=os.getenv("ASR_SECONDARY_HOTKEY", DEFAULT_SECONDARY_HOTKEY),
            optimization_level=os.getenv("ASR_OPTIMIZATION_LEVEL", DEFAULT_OPTIMIZATION_LEVEL),
            custom_polish_prompt=os.getenv("ASR_CUSTOM_POLISH_PROMPT", DEFAULT_CUSTOM_POLISH_PROMPT),
            remote_phone_enabled=_coerce_bool(os.getenv("ASR_REMOTE_PHONE_ENABLED"), DEFAULT_REMOTE_PHONE_ENABLED),
            remote_phone_host=os.getenv("ASR_REMOTE_PHONE_HOST", DEFAULT_REMOTE_PHONE_HOST),
            remote_phone_http_port=_coerce_int(os.getenv("ASR_REMOTE_PHONE_HTTP_PORT"), DEFAULT_REMOTE_PHONE_HTTP_PORT),
            remote_phone_control_port=_coerce_int(os.getenv("ASR_REMOTE_PHONE_CONTROL_PORT"), DEFAULT_REMOTE_PHONE_CONTROL_PORT),
            remote_phone_audio_port=_coerce_int(os.getenv("ASR_REMOTE_PHONE_AUDIO_PORT"), DEFAULT_REMOTE_PHONE_AUDIO_PORT),
            remote_phone_auto_start=_coerce_bool(os.getenv("ASR_REMOTE_PHONE_AUTO_START"), DEFAULT_REMOTE_PHONE_AUTO_START),
            remote_phone_input_gain=_coerce_float(os.getenv("ASR_REMOTE_PHONE_INPUT_GAIN"), DEFAULT_REMOTE_PHONE_INPUT_GAIN),
        )

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | None = None) -> "AppConfig":
        base = cls.from_env()
        if not values:
            return base
        legacy_api_key = values.get("api_key")
        legacy_base_url = values.get("base_url")
        return cls(
            language=_coerce_str(values.get("language"), base.language),
            asr_provider=_coerce_str(values.get("asr_provider"), base.asr_provider) or DEFAULT_ASR_PROVIDER,
            asr_api_key=_coerce_str(values.get("asr_api_key", legacy_api_key), base.asr_api_key),
            asr_app_key=_coerce_str(values.get("asr_app_key"), base.asr_app_key),
            asr_base_url=_coerce_str(values.get("asr_base_url", legacy_base_url), base.asr_base_url),
            asr_non_stream_model=_coerce_str(values.get("asr_non_stream_model"), base.asr_non_stream_model) or DEFAULT_NON_STREAM_MODEL,
            asr_realtime_model=_coerce_str(values.get("asr_realtime_model"), base.asr_realtime_model) or DEFAULT_REALTIME_MODEL,
            text_polish_api_key=_coerce_str(values.get("text_polish_api_key", legacy_api_key), base.text_polish_api_key),
            text_polish_base_url=_coerce_str(values.get("text_polish_base_url", legacy_base_url), base.text_polish_base_url),
            text_polish_model=_coerce_str(values.get("text_polish_model"), base.text_polish_model) or DEFAULT_TEXT_POLISH_MODEL,
            polish_output_key=_coerce_str(values.get("polish_output_key"), base.polish_output_key) or DEFAULT_TEXT_POLISH_OUTPUT_KEY,
            default_mode=_coerce_str(values.get("default_mode"), base.default_mode) or MODE_NON_STREAM,
            input_source_type=_coerce_str(values.get("input_source_type"), base.input_source_type) or DEFAULT_INPUT_SOURCE_TYPE,
            audio_input_device=_coerce_str(values.get("audio_input_device"), base.audio_input_device),
            enable_tray=_coerce_bool(values.get("enable_tray"), base.enable_tray),
            start_minimized=_coerce_bool(values.get("start_minimized"), base.start_minimized),
            log_level=_coerce_str(values.get("log_level"), base.log_level).upper() or DEFAULT_LOG_LEVEL,
            hotkey_mode=_coerce_str(values.get("hotkey_mode"), base.hotkey_mode) or DEFAULT_HOTKEY_MODE,
            primary_hotkey=_coerce_str(values.get("primary_hotkey"), base.primary_hotkey) or DEFAULT_PRIMARY_HOTKEY,
            secondary_hotkey=_coerce_str(values.get("secondary_hotkey"), base.secondary_hotkey) or DEFAULT_SECONDARY_HOTKEY,
            optimization_level=_coerce_str(values.get("optimization_level"), base.optimization_level) or DEFAULT_OPTIMIZATION_LEVEL,
            custom_polish_prompt=_coerce_str(values.get("custom_polish_prompt"), base.custom_polish_prompt) or DEFAULT_CUSTOM_POLISH_PROMPT,
            remote_phone_enabled=_coerce_bool(values.get("remote_phone_enabled"), base.remote_phone_enabled),
            remote_phone_host=_coerce_str(values.get("remote_phone_host"), base.remote_phone_host),
            remote_phone_http_port=_coerce_int(values.get("remote_phone_http_port"), base.remote_phone_http_port),
            remote_phone_control_port=_coerce_int(values.get("remote_phone_control_port"), base.remote_phone_control_port),
            remote_phone_audio_port=_coerce_int(values.get("remote_phone_audio_port"), base.remote_phone_audio_port),
            remote_phone_auto_start=_coerce_bool(values.get("remote_phone_auto_start"), base.remote_phone_auto_start),
            remote_phone_input_gain=_coerce_float(values.get("remote_phone_input_gain"), base.remote_phone_input_gain),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def api_key(self) -> str:
        return self.asr_api_key

    @property
    def base_url(self) -> str:
        return self.asr_base_url

    def resolved_asr_api_key(self) -> str:
        return self.asr_api_key

    def resolved_asr_base_url(self) -> str:
        return self.asr_base_url or DEFAULT_ASR_BASE_URL

    def resolved_text_polish_api_key(self) -> str:
        return self.text_polish_api_key or self.asr_api_key

    def resolved_text_polish_base_url(self) -> str:
        return self.text_polish_base_url or self.asr_base_url or DEFAULT_TEXT_POLISH_BASE_URL


def apply_config_to_env(config: AppConfig) -> None:
    os.environ["ASR_PROVIDER"] = config.asr_provider
    os.environ["ASR_LANGUAGE"] = config.language

    if config.asr_api_key:
        os.environ["ASR_API_KEY"] = config.asr_api_key
        os.environ["API_KEY"] = config.asr_api_key
    else:
        os.environ.pop("ASR_API_KEY", None)
        os.environ.pop("API_KEY", None)

    if config.asr_app_key:
        os.environ["ASR_APP_KEY"] = config.asr_app_key
    else:
        os.environ.pop("ASR_APP_KEY", None)

    if config.asr_base_url:
        os.environ["ASR_BASE_URL"] = config.asr_base_url
        os.environ["BASE_URL"] = config.asr_base_url
        os.environ["DASHSCOPE_COMPATIBLE_BASE_URL"] = config.asr_base_url
    else:
        os.environ.pop("ASR_BASE_URL", None)
        os.environ.pop("BASE_URL", None)
        os.environ.pop("DASHSCOPE_COMPATIBLE_BASE_URL", None)

    if config.text_polish_api_key:
        os.environ["TEXT_POLISH_API_KEY"] = config.text_polish_api_key
    else:
        os.environ.pop("TEXT_POLISH_API_KEY", None)

    if config.text_polish_base_url:
        os.environ["TEXT_POLISH_BASE_URL"] = config.text_polish_base_url
    else:
        os.environ.pop("TEXT_POLISH_BASE_URL", None)

    os.environ["ASR_NON_STREAM_MODEL"] = config.asr_non_stream_model
    os.environ["ASR_REALTIME_MODEL"] = config.asr_realtime_model
    os.environ["ASR_TEXT_POLISH_MODEL"] = config.text_polish_model
    os.environ["TEXT_POLISH_OUTPUT_KEY"] = config.polish_output_key
    os.environ["ASR_DEFAULT_MODE"] = config.default_mode
    os.environ["ASR_INPUT_SOURCE_TYPE"] = config.input_source_type
    os.environ["ASR_LOG_LEVEL"] = config.log_level
    os.environ["ASR_HOTKEY_MODE"] = config.hotkey_mode
    os.environ["ASR_PRIMARY_HOTKEY"] = config.primary_hotkey
    os.environ["ASR_SECONDARY_HOTKEY"] = config.secondary_hotkey
    os.environ["ASR_OPTIMIZATION_LEVEL"] = config.optimization_level
    os.environ["ASR_CUSTOM_POLISH_PROMPT"] = config.custom_polish_prompt
    os.environ["ASR_REMOTE_PHONE_ENABLED"] = "1" if config.remote_phone_enabled else "0"
    os.environ["ASR_REMOTE_PHONE_HOST"] = config.remote_phone_host
    os.environ["ASR_REMOTE_PHONE_HTTP_PORT"] = str(config.remote_phone_http_port)
    os.environ["ASR_REMOTE_PHONE_CONTROL_PORT"] = str(config.remote_phone_control_port)
    os.environ["ASR_REMOTE_PHONE_AUDIO_PORT"] = str(config.remote_phone_audio_port)
    os.environ["ASR_REMOTE_PHONE_AUTO_START"] = "1" if config.remote_phone_auto_start else "0"
    os.environ["ASR_REMOTE_PHONE_INPUT_GAIN"] = str(config.remote_phone_input_gain)
