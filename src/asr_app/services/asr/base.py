from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class AsrProviderError(RuntimeError):
    """Raised when an ASR provider operation fails."""


@dataclass(frozen=True, slots=True)
class AsrCredentials:
    """Immutable credentials bundle for ASR providers.

    - ``api_key``: OpenAI / Aliyun API key, or Doubao *access_key*.
    - ``app_key``: Doubao-only *app_key* (empty for other providers).
    - ``base_url``: Optional endpoint override.
    """

    api_key: str = ""
    app_key: str = ""
    base_url: str = ""


class RealtimeSession(ABC):
    """Abstract realtime ASR session.

    The interface mirrors the existing ``RealtimeTranscriber`` contract so that
    ``AudioRecorder`` requires minimal changes.
    """

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def send_audio(self, pcm_bytes: bytes) -> None: ...

    @abstractmethod
    def finish_and_get_text(self) -> str: ...

    @abstractmethod
    def close(self) -> None: ...


class AsrProvider(ABC):
    """Abstract ASR provider with non-realtime and realtime capabilities."""

    @abstractmethod
    def transcribe_non_stream(self, audio_base64: str, model_name: str) -> str:
        """Transcribe a base64-encoded WAV file. Returns recognised text."""
        ...

    @abstractmethod
    def create_realtime_session(self, model_name: str) -> RealtimeSession:
        """Create a new realtime transcription session."""
        ...
