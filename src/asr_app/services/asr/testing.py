from __future__ import annotations

import base64
import io
import wave

from ...i18n import t
from .base import AsrCredentials, AsrProviderError
from .factory import create_provider


def generate_silent_wav(duration_s: float = 0.5, sample_rate: int = 16000) -> str:
    num_samples = int(sample_rate * duration_s)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * num_samples)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_non_stream_asr(provider_name: str, credentials: AsrCredentials, model_name: str) -> tuple[bool, str]:
    try:
        provider = create_provider(provider_name, credentials)
        wav_b64 = generate_silent_wav()
        result = provider.transcribe_non_stream(wav_b64, model_name)
        return True, t("test.response_content", text=result)
    except AsrProviderError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, str(exc)


def test_text_polish(api_key: str, base_url: str, model_name: str) -> tuple[bool, str]:
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url, timeout=15)
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "??"}],
            max_tokens=20,
        )
        choices = getattr(response, "choices", None) or []
        if not choices:
            return False, t("polish.error.no_choices")
        text = getattr(getattr(choices[0], "message", None), "content", "") or ""
        return True, t("test.response_content", text=text.strip())
    except Exception as exc:
        return False, str(exc)
