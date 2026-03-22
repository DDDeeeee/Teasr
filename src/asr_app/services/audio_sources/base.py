from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable


AudioFrameHandler = Callable[[bytes], None]


class AudioInputSourceError(RuntimeError):
    pass


class AudioInputSource(ABC):
    def __init__(self) -> None:
        self._frame_handler: AudioFrameHandler | None = None

    def set_frame_handler(self, handler: AudioFrameHandler | None) -> None:
        self._frame_handler = handler

    def _emit_frame(self, pcm_bytes: bytes) -> None:
        if pcm_bytes and self._frame_handler is not None:
            self._frame_handler(pcm_bytes)

    @abstractmethod
    def start(self) -> None:
        pass

    @abstractmethod
    def stop(self) -> None:
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        pass

    @abstractmethod
    def status_snapshot(self) -> dict:
        pass
