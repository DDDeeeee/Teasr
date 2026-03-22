from __future__ import annotations

import base64
import threading

import dashscope
from dashscope.audio.qwen_omni import MultiModality, OmniRealtimeCallback, OmniRealtimeConversation
from dashscope.audio.qwen_omni.omni_realtime import TranscriptionParams

from .... import runtime_core as core
from ....i18n import LOG_TAG_RT, t
from ..base import AsrCredentials, AsrProvider, AsrProviderError, RealtimeSession


class AliyunProvider(AsrProvider):
    def __init__(self, credentials: AsrCredentials) -> None:
        self._credentials = credentials

    def transcribe_non_stream(self, audio_base64: str, model_name: str) -> str:
        messages = [{"role": "user", "content": [{"audio": f"data:audio/wav;base64,{audio_base64}"}]}]
        try:
            response = dashscope.MultiModalConversation.call(
                api_key=self._credentials.api_key,
                model=model_name,
                messages=messages,
                result_format="message",
                asr_options={"enable_itn": True},
            )
        except Exception as exc:
            raise AsrProviderError(f"Aliyun ASR request failed: {exc}") from exc

        try:
            content = response["output"]["choices"][0]["message"]["content"]
            for item in content:
                if "text" in item:
                    return item["text"]
        except (KeyError, IndexError, TypeError):
            pass
        return ""

    def create_realtime_session(self, model_name: str) -> RealtimeSession:
        return AliyunRealtimeSession(self._credentials, model_name)


class AliyunRealtimeSession(RealtimeSession):
    def __init__(self, credentials: AsrCredentials, model_name: str) -> None:
        self._credentials = credentials
        self._model_name = model_name
        self._conversation = None
        self._completed_texts: list[str] = []
        self._finished = threading.Event()
        self._connected = threading.Event()

    def start(self) -> None:
        self._completed_texts = []
        self._finished.clear()
        self._connected.clear()

        dashscope.api_key = self._credentials.api_key
        callback = _AliyunRealtimeCallback(self)
        self._conversation = OmniRealtimeConversation(
            model=self._model_name,
            url="wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
            callback=callback,
        )
        callback.conversation = self._conversation

        self._conversation.connect()
        if not self._connected.wait(timeout=5):
            raise AsrProviderError("Aliyun WebSocket connection timed out")

        self._conversation.update_session(
            output_modalities=[MultiModality.TEXT],
            enable_input_audio_transcription=True,
            transcription_params=TranscriptionParams(
                language="zh",
                sample_rate=16000,
                input_audio_format="pcm",
            ),
        )

    def send_audio(self, pcm_bytes: bytes) -> None:
        if self._conversation is None:
            return
        audio_b64 = base64.b64encode(pcm_bytes).decode("ascii")
        self._conversation.append_audio(audio_b64)

    def finish_and_get_text(self) -> str:
        if self._conversation is None:
            return ""
        try:
            self._conversation.end_session()
            self._finished.wait(timeout=3)
        except Exception:
            core.logger.exception("Aliyun end_session failed")
        return "".join(self._completed_texts)

    def close(self) -> None:
        if self._conversation is None:
            return
        try:
            self._conversation.close()
        except Exception:
            core.logger.exception("Aliyun close conversation failed")
        finally:
            self._conversation = None

    def _on_connected(self) -> None:
        self._connected.set()

    def _on_completed(self, transcript: str) -> None:
        self._completed_texts.append(transcript)
        if core.osd_bubble is not None:
            core.osd_bubble.sig_update_completed.emit(transcript)

    def _on_session_finished(self) -> None:
        self._finished.set()

    def _on_closed(self) -> None:
        self._finished.set()


class _AliyunRealtimeCallback(OmniRealtimeCallback):
    def __init__(self, session: AliyunRealtimeSession) -> None:
        self._session = session
        self.conversation = None

    def on_open(self) -> None:
        core.log(f"{LOG_TAG_RT} {t('log.realtime_ws_connected')}")
        self._session._on_connected()

    def on_close(self, code, msg) -> None:
        core.log(f"{LOG_TAG_RT} {t('log.realtime_ws_closed', code=code)}")
        self._session._on_closed()

    def on_event(self, response) -> None:
        try:
            event_type = response.get("type", "")
            if event_type == "session.created":
                core.log(f"{LOG_TAG_RT} {t('log.realtime_session_created', session_id=response['session']['id'])}")
            elif event_type == "session.finished":
                core.log(f"{LOG_TAG_RT} {t('log.realtime_session_finished')}")
                self._session._on_session_finished()
            elif event_type == "conversation.item.input_audio_transcription.completed":
                transcript = response.get("transcript", "")
                if transcript:
                    core.log(f"{LOG_TAG_RT} {t('log.realtime_confirmed_text', text=transcript)}")
                    self._session._on_completed(transcript)
            elif event_type == "conversation.item.input_audio_transcription.text":
                stash = response.get("stash", "")
                if stash:
                    if core.osd_bubble is not None:
                        core.osd_bubble.sig_update_stash.emit(stash)
                    print(f"\r[RT] {stash}", end="", flush=True)
            elif event_type == "input_audio_buffer.speech_started":
                core.log(f"{LOG_TAG_RT} {t('log.realtime_speech_started')}")
            elif event_type == "input_audio_buffer.speech_stopped":
                core.log(f"{LOG_TAG_RT} {t('log.realtime_speech_stopped')}")
        except Exception as exc:
            core.log(f"{LOG_TAG_RT} {t('log.realtime_callback_error', error=exc)}")
            core.logger.exception("Aliyun realtime callback error")
