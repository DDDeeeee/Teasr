from PyQt6.QtCore import QSettings

from ..config import AppConfig, apply_config_to_env
from ..runtime_logging import configure_logging

HOTKEY_MODE_HOLD = "hold"
HOTKEY_MODE_TOGGLE = "toggle"


class SettingsService:
    ORGANIZATION = "TEASR"
    APPLICATION = "TEASR"

    def __init__(self):
        self._settings = QSettings(self.ORGANIZATION, self.APPLICATION)

    def defaults(self) -> dict:
        return AppConfig.from_env().to_dict()

    def load(self) -> dict:
        defaults = self.defaults()
        stored = {key: self._settings.value(key, defaults[key]) for key in defaults}
        return AppConfig.from_mapping(stored).to_dict()

    def save(self, updates: dict) -> dict:
        current = AppConfig.from_mapping(self.load())
        merged = AppConfig.from_mapping(current.to_dict() | updates)
        data = merged.to_dict()
        for key, value in data.items():
            self._settings.setValue(key, value)
        self._settings.sync()
        self.apply_runtime(data)
        return data

    def apply_runtime(self, settings: dict) -> None:
        config = AppConfig.from_mapping(settings)
        apply_config_to_env(config)
        configure_logging(config.log_level)
