from __future__ import annotations

import numpy as np

from ...i18n import t
from ..remote_phone_runtime import RemotePhoneRuntime
from .base import AudioInputSource, AudioInputSourceError


class RemotePhoneSource(AudioInputSource):
    def __init__(self, runtime: RemotePhoneRuntime, gain: float = 1.0) -> None:
        super().__init__()
        self.runtime = runtime
        self.gain = max(0.0, float(gain))
        self._active = False

    def start(self) -> None:
        if self._active:
            return
        self.runtime.set_frame_handler(self._handle_frame)
        try:
            self.runtime.start_capture()
            self._active = True
        except Exception as exc:
            self.runtime.set_frame_handler(None)
            raise AudioInputSourceError(t("error.remote_phone_source_not_ready", error=exc)) from exc

    def stop(self) -> None:
        try:
            self.runtime.stop_capture()
        finally:
            self.runtime.set_frame_handler(None)
            self._active = False

    def is_ready(self) -> bool:
        return bool(self.runtime.status_snapshot().get("ready"))

    def status_snapshot(self) -> dict:
        snapshot = self.runtime.status_snapshot()
        snapshot["source_type"] = "remote_phone"
        snapshot["active"] = self._active
        snapshot["input_gain"] = self.gain
        return snapshot

    def _handle_frame(self, pcm_bytes: bytes) -> None:
        self._emit_frame(self._apply_gain(pcm_bytes))

    def _apply_gain(self, pcm_bytes: bytes) -> bytes:
        if not pcm_bytes or self.gain == 1.0:
            return pcm_bytes
        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
        adjusted = np.clip(samples * self.gain, -32768, 32767).astype(np.int16)
        return adjusted.tobytes()
