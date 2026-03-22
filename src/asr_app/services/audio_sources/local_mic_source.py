from __future__ import annotations

import numpy as np
import sounddevice as sd

from ...i18n import t
from .base import AudioInputSource, AudioInputSourceError


class LocalMicSource(AudioInputSource):
    def __init__(self, sample_rate: int = 16000, input_device: int | None = None) -> None:
        super().__init__()
        self.sample_rate = sample_rate
        self.input_device = input_device
        self._stream: sd.InputStream | None = None
        self._active = False
        self._last_error = ""

    def start(self) -> None:
        if self._active:
            return
        try:
            self._stream = sd.InputStream(samplerate=self.sample_rate, channels=1, callback=self._callback, dtype="float32", device=self.input_device, blocksize=512)
            self._stream.start()
            self._active = True
            self._last_error = ""
        except Exception as exc:
            self._stream = None
            self._active = False
            self._last_error = str(exc)
            raise AudioInputSourceError(t("error.local_mic_start_failed", error=exc)) from exc

    def stop(self) -> None:
        self._active = False
        stream = self._stream
        self._stream = None
        if stream is None:
            return
        try:
            stream.stop()
        finally:
            stream.close()

    def is_ready(self) -> bool:
        return True

    def status_snapshot(self) -> dict:
        return {"source_type": "local_mic", "ready": True, "active": self._active, "input_device": self.input_device, "last_error": self._last_error}

    def _callback(self, indata, _frames, _time_info, status) -> None:
        if status:
            self._last_error = str(status)
        if not self._active:
            return
        pcm = np.clip(indata[:, 0], -1.0, 1.0)
        pcm_int16 = (pcm * 32767.0).astype(np.int16)
        self._emit_frame(pcm_int16.tobytes())
