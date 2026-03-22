from __future__ import annotations

import base64
import io

from openai import OpenAI

from ....i18n import t
from ..base import AsrCredentials, AsrProvider, AsrProviderError, RealtimeSession


class OpenAIProvider(AsrProvider):
    def __init__(self, credentials: AsrCredentials) -> None:
        self._credentials = credentials

    def transcribe_non_stream(self, audio_base64: str, model_name: str) -> str:
        base_url = self._credentials.base_url or "https://api.openai.com/v1"
        client = OpenAI(api_key=self._credentials.api_key, base_url=base_url, timeout=30)
        wav_bytes = base64.b64decode(audio_base64)
        audio_file = io.BytesIO(wav_bytes)
        audio_file.name = "audio.wav"
        try:
            transcript = client.audio.transcriptions.create(model=model_name, file=audio_file)
        except Exception as exc:
            raise AsrProviderError(f"OpenAI ASR request failed: {exc}") from exc
        return transcript.text or ""

    def create_realtime_session(self, model_name: str) -> RealtimeSession:
        raise AsrProviderError(t("error.openai_realtime_not_supported"))
