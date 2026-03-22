import logging
import os

from .runtime_env import LOG_PATH, ensure_runtime_dir, load_project_env


LOGGER_NAME = "asr"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"


def _resolve_level(level_name: str | None) -> int:
    candidate = (level_name or os.getenv("ASR_LOG_LEVEL", "INFO")).upper()
    return getattr(logging, candidate, logging.INFO)


def _build_file_handler() -> logging.Handler:
    ensure_runtime_dir()
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    return handler


def configure_logging(level_name: str | None = None) -> logging.Logger:
    load_project_env()
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(_resolve_level(level_name))
    logger.propagate = False
    if not logger.handlers:
        logger.addHandler(_build_file_handler())
    else:
        for handler in logger.handlers:
            handler.setLevel(logging.NOTSET)
    return logger


logger = configure_logging()
