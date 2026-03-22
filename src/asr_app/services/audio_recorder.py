from __future__ import annotations

import base64
import ctypes
import io
import threading
import time
import wave

import keyboard
import numpy as np

from .. import runtime_core as core
from ..caret_locator import get_caret_position
from ..config import AppConfig
from ..i18n import LOG_TAG_ASR, LOG_TAG_DONE, LOG_TAG_FINAL, LOG_TAG_REC, LOG_TAG_RETRY, LOG_TAG_RESULT, LOG_TAG_WARN, t
from ..modes import MODE_NON_STREAM_POLISH, MODE_REALTIME, MODE_REALTIME_POLISH
from ..polish_parser import describe_stream_issue
from ..text_polisher import TextPolisherError, request_polished_text, stream_polished_text
from .audio_sources import AudioInputSource, LocalMicSource
from .asr.base import AsrProvider


class AudioRecorder:
    def __init__(
        self,
        sample_rate: int = 16000,
        mode: str = "1",
        config: AppConfig | None = None,
        input_device: int | None = None,
        input_source: AudioInputSource | None = None,
        asr_provider: AsrProvider | None = None,
    ) -> None:
        self.recording = False
        self.audio_data: list[bytes] = []
        self.sample_rate = sample_rate
        self.caps_state_before = None
        self._suppress_until = 0.0
        self._press_time = 0.0
        self.mode = mode
        self.config = config or AppConfig.from_env()
        self.input_device = input_device
        self.input_source = input_source or LocalMicSource(sample_rate=sample_rate, input_device=input_device)
        self._asr_provider = asr_provider
        self._realtime = None
        self._indicator_pending_rms = 0.0
        self._indicator_last_emit_at = 0.0
        self._indicator_emit_interval = 0.05
        self.input_source.set_frame_handler(self._handle_audio_frame)

    def _get_provider(self) -> AsrProvider:
        if self._asr_provider is not None:
            return self._asr_provider
        from .asr import create_provider
        from .asr.base import AsrCredentials
        return create_provider("aliyun", AsrCredentials(api_key=self.config.resolved_asr_api_key()))

    def _is_realtime_mode(self) -> bool:
        return self.mode in {MODE_REALTIME, MODE_REALTIME_POLISH}

    def _is_non_realtime_polish_mode(self) -> bool:
        return self.mode == MODE_NON_STREAM_POLISH

    def _is_polish_mode(self) -> bool:
        return self.mode == MODE_REALTIME_POLISH

    def _handle_audio_frame(self, pcm_bytes: bytes) -> None:
        if not self.recording or not pcm_bytes:
            return
        if self._is_realtime_mode() and self._realtime is not None:
            self._realtime.send_audio(pcm_bytes)
            return
        self.audio_data.append(pcm_bytes)
        indicator = core.recording_indicator
        if indicator is None:
            return
        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if not samples.size:
            return
        rms = float(np.sqrt(np.mean(samples**2)))
        self._indicator_pending_rms = max(self._indicator_pending_rms, rms)
        self._flush_indicator_level()

    def start_recording(self) -> None:
        if self.recording or time.time() < self._suppress_until:
            return
        if not self.input_source.is_ready():
            raise RuntimeError(t("error.audio_input_not_ready"))

        vk_capital = 0x14
        self.caps_state_before = ctypes.windll.user32.GetKeyState(vk_capital) & 0x0001
        self._press_time = time.time()
        self.recording = True
        self.audio_data = []
        self._reset_indicator_meter()
        core.log(f"\n{LOG_TAG_REC} {t('log.recording')}")

        try:
            self._prepare_output_surface()
            self.input_source.set_frame_handler(self._handle_audio_frame)
            self.input_source.start()
        except Exception as exc:
            self.recording = False
            self._cleanup_failed_start()
            core.logger.exception("Failed to start recording")
            raise RuntimeError(t("error.recording_start_failed", error=exc)) from exc

    def stop_and_transcribe(self) -> None:
        if not self.recording:
            return
        self.recording = False
        self._hide_indicator()
        self._stop_input_source()

        if self._is_realtime_mode():
            self._stop_realtime()
            return

        if not self.audio_data:
            core.log(f"{LOG_TAG_WARN} {t('log.empty_recording')}")
            return

        audio_base64 = self._encode_wav_base64(b"".join(self.audio_data))
        core.log(f"{LOG_TAG_ASR} {t('log.transcribing')}")
        full_text = self._transcribe_with_retries(audio_base64)

        if self._is_non_realtime_polish_mode():
            self._input_polished_text(full_text, t("mode.non_stream_polish"))
            return
        self._input_text(full_text)

    def stop_and_transcribe_with_toggle(self) -> None:
        hold_duration = time.time() - self._press_time if self._press_time else 0.0
        if hold_duration < 0.3:
            self.recording = False
            self._stop_input_source()
            self._cleanup_realtime_after_cancel()
            self._hide_osd()
            self._hide_indicator()
            core.log(f"{LOG_TAG_WARN} {t('log.short_press_caps', duration=hold_duration)}")
            return
        self.stop_and_transcribe()
        self._restore_caps_lock_state()

    def cancel_recording(self, *, restore_caps_lock: bool = False) -> None:
        self.recording = False
        self.audio_data = []
        self._press_time = 0.0
        self._stop_input_source()
        self._cleanup_realtime_after_cancel()
        self._hide_osd()
        self._hide_indicator()
        self._reset_indicator_meter()
        if restore_caps_lock:
            self._restore_caps_lock_state()
        else:
            self.caps_state_before = None

    def _prepare_output_surface(self) -> None:
        if self._is_realtime_mode():
            caret = get_caret_position()
            if core.osd_bubble is not None:
                core.osd_bubble.sig_show.emit(caret.x, caret.y, caret.height, caret.source)
            self._realtime = self._get_provider().create_realtime_session(self.config.asr_realtime_model)
            self._realtime.start()
            return
        if core.recording_indicator is not None:
            core.recording_indicator.sig_show.emit()

    def _cleanup_failed_start(self) -> None:
        self._cleanup_realtime_after_cancel()
        self._hide_osd()
        self._hide_indicator()
        self._reset_indicator_meter()

    def _transcribe_with_retries(self, audio_base64: str) -> str:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return self._get_provider().transcribe_non_stream(audio_base64, self.config.asr_non_stream_model)
            except Exception as exc:
                if attempt >= max_retries - 1:
                    core.logger.exception("Transcribe failed")
                    raise
                wait_seconds = attempt + 1
                core.log(f"{LOG_TAG_RETRY} {t('log.retry_request', attempt=attempt + 1, wait_seconds=wait_seconds, error=exc)}")
                time.sleep(wait_seconds)
        return ""

    def _reset_indicator_meter(self) -> None:
        self._indicator_pending_rms = 0.0
        self._indicator_last_emit_at = 0.0

    def _flush_indicator_level(self, force: bool = False) -> None:
        indicator = core.recording_indicator
        if indicator is None:
            self._reset_indicator_meter()
            return
        now = time.monotonic()
        if not force and now - self._indicator_last_emit_at < self._indicator_emit_interval:
            return
        level = self._indicator_pending_rms
        self._indicator_pending_rms = 0.0
        self._indicator_last_emit_at = now
        indicator.sig_audio_level.emit([level])

    def _encode_wav_base64(self, pcm_bytes: bytes) -> str:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(pcm_bytes)
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    def _stop_input_source(self) -> None:
        try:
            self.input_source.stop()
        except Exception:
            core.logger.exception("Failed to stop input source")

    def _stop_realtime(self) -> None:
        if self._realtime is None:
            return
        print("", flush=True)
        realtime = self._realtime
        self._realtime = None
        try:
            if self._is_polish_mode():
                self._stop_realtime_with_polish(realtime)
            else:
                self._stop_realtime_plain(realtime)
        finally:
            threading.Thread(target=self._cleanup_realtime, args=(realtime,), daemon=True).start()

    def _stop_realtime_plain(self, realtime) -> None:
        self._hide_osd()
        full_text = realtime.finish_and_get_text()
        self._input_text(full_text)

    def _stop_realtime_with_polish(self, realtime) -> None:
        full_text = realtime.finish_and_get_text()
        if not full_text:
            self._hide_osd()
            core.log(f"{LOG_TAG_WARN} {t('log.realtime_empty')}")
            return
        if core.osd_bubble is not None:
            core.osd_bubble.sig_set_phase.emit("polishing")
        self._input_polished_text(full_text, t("mode.realtime_polish"), before_first_chunk=self._hide_osd)

    def _cleanup_realtime(self, realtime) -> None:
        try:
            realtime.close()
        except Exception:
            core.logger.exception("Realtime cleanup failed")

    def _cleanup_realtime_after_cancel(self) -> None:
        if self._realtime is None:
            return
        try:
            self._realtime.close()
        except Exception:
            core.logger.exception("Failed to close realtime session during cleanup")
        finally:
            self._realtime = None

    def _hide_osd(self) -> None:
        if core.osd_bubble is not None:
            core.osd_bubble.sig_hide.emit()

    def _hide_indicator(self) -> None:
        self._indicator_pending_rms = 0.0
        self._indicator_last_emit_at = 0.0
        if core.recording_indicator is not None:
            core.recording_indicator.sig_audio_level.emit([0.0])
            core.recording_indicator.sig_hide.emit()

    def _restore_caps_lock_state(self) -> None:
        vk_capital = 0x14
        try:
            caps_state_after = ctypes.windll.user32.GetKeyState(vk_capital) & 0x0001
        except Exception:
            core.logger.exception("Failed to read Caps Lock state")
            self.caps_state_before = None
            return
        if self.caps_state_before is not None and caps_state_after != self.caps_state_before:
            try:
                self._suppress_until = time.time() + 0.5
                ctypes.windll.user32.keybd_event(vk_capital, 0x3A, 0, 0)
                ctypes.windll.user32.keybd_event(vk_capital, 0x3A, 2, 0)
            except Exception:
                core.logger.exception("Failed to restore Caps Lock state")
        self.caps_state_before = None

    def _input_polished_text(self, full_text: str, context_label: str, before_first_chunk=None) -> None:
        if not full_text:
            core.log(f"{LOG_TAG_WARN} {t('log.no_text_detected')}")
            return

        core.log(f"{LOG_TAG_RESULT} {context_label} | {t('log.original_text', text=full_text)}")
        target_hwnd = core.get_foreground_window()
        typed_text_parts: list[str] = []
        released_before_output = False
        injection_cancelled = False

        def release_before_output() -> None:
            nonlocal released_before_output
            if not released_before_output and before_first_chunk is not None:
                before_first_chunk()
                released_before_output = True

        def append_suffix_if_safe(final_text: str | None, reason: str) -> bool:
            current_text = "".join(typed_text_parts)
            release_before_output()
            if not core.is_same_foreground_window(target_hwnd):
                core.log(f"{LOG_TAG_WARN} {t('log.focus_switched_cancel_autocomplete')}")
                return False
            if not final_text:
                if current_text:
                    core.log(f"{LOG_TAG_FINAL} {t('log.final_text', text=current_text)}")
                    core.log(f"{LOG_TAG_DONE} {t('log.text_inserted')}")
                else:
                    core.log(f"{LOG_TAG_WARN} {t('log.no_text_detected')}")
                return True
            if not current_text:
                self._write_text(final_text)
                typed_text_parts.append(final_text)
                core.log(f"{LOG_TAG_WARN} {t('log.direct_fill_due_reason', reason=reason)}")
                core.log(f"{LOG_TAG_FINAL} {t('log.final_text', text=final_text)}")
                core.log(f"{LOG_TAG_DONE} {t('log.text_inserted')}")
                return True
            if final_text.startswith(current_text):
                suffix = final_text[len(current_text):]
                if suffix:
                    self._write_text(suffix)
                    typed_text_parts.append(suffix)
                    core.log(f"{LOG_TAG_WARN} {t('log.fill_suffix_due_reason', reason=reason)}")
                core.log(f"{LOG_TAG_FINAL} {t('log.final_text', text=final_text)}")
                core.log(f"{LOG_TAG_DONE} {t('log.text_inserted')}")
                return True
            core.log(f"{LOG_TAG_WARN} {t('log.safe_fill_mismatch')}")
            return False

        def handle_stream_chunk(chunk: str) -> None:
            nonlocal injection_cancelled
            if not chunk or injection_cancelled:
                return
            if not core.is_same_foreground_window(target_hwnd):
                injection_cancelled = True
                return
            release_before_output()
            self._write_text(chunk)
            typed_text_parts.append(chunk)

        stream_result = None
        stream_error = None
        try:
            stream_result = stream_polished_text(
                full_text,
                self.config.resolved_text_polish_api_key(),
                on_chunk=handle_stream_chunk,
                model_name=self.config.text_polish_model,
                base_url=self.config.resolved_text_polish_base_url(),
                target_key=self.config.polish_output_key,
                optimization_level=self.config.optimization_level,
                custom_prompt=self.config.custom_polish_prompt,
            )
        except TextPolisherError as exc:
            stream_error = str(exc)
            core.logger.exception("Polish stream failed")

        if stream_result is not None:
            if stream_result.first_chunk_latency_ms is not None:
                core.log(f"{LOG_TAG_RESULT} {t('log.first_chunk_latency', latency=stream_result.first_chunk_latency_ms)}")
            core.log(
                f"{LOG_TAG_RESULT} {t('log.stream_parse_status', length=len(stream_result.text), target_started=stream_result.target_started, target_completed=stream_result.target_completed, json_completed=stream_result.json_completed, resolved_length=len(stream_result.resolved_text or ''))}"
            )

        if injection_cancelled:
            release_before_output()
            core.log(f"{LOG_TAG_WARN} {t('log.focus_switched_cancel_stream_injection')}")
            return

        if stream_result is not None and stream_result.resolved_text is not None:
            append_suffix_if_safe(stream_result.resolved_text, "stream_monitor")
            return

        fallback_reason = t('polish.stream_request_failed') if stream_error else describe_stream_issue(stream_result)
        core.log(f"{LOG_TAG_WARN} {t('log.stream_invalid_fallback', reason=fallback_reason)}")
        if stream_error:
            core.log(f"{LOG_TAG_WARN} {t('log.stream_request_error', error=stream_error)}")

        try:
            replacement_text = request_polished_text(
                full_text,
                self.config.resolved_text_polish_api_key(),
                model_name=self.config.text_polish_model,
                base_url=self.config.resolved_text_polish_base_url(),
                target_key=self.config.polish_output_key,
                optimization_level=self.config.optimization_level,
                custom_prompt=self.config.custom_polish_prompt,
            )
        except TextPolisherError as exc:
            replacement_text = full_text if not typed_text_parts else None
            core.log(f"{LOG_TAG_WARN} {t('log.non_stream_fallback_failed', error=exc)}")

        append_suffix_if_safe(replacement_text, "fallback")

    def _write_text(self, text: str) -> None:
        try:
            keyboard.write(text)
        except Exception as exc:
            core.log(f"{LOG_TAG_WARN} {t('log.keyboard_write_failed', error=exc)}")
            core.send_unicode_text(text)

    def _input_text(self, full_text: str) -> None:
        if not full_text:
            core.log(f"{LOG_TAG_WARN} {t('log.no_text_detected')}")
            return
        core.log(f"{LOG_TAG_RESULT} {t('log.result_text', text=full_text)}")
        self._write_text(full_text)
        core.log(f"{LOG_TAG_DONE} {t('log.text_inserted')}")
