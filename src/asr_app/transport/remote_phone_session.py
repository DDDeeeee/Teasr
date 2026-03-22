from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PhoneSession:
    session_id: str
    client_id: str
    state: str = "PHONE_CONNECTED"
    device_name: str | None = None
    browser: str | None = None
    platform: str | None = None
    active_capture_id: str | None = None
    active_capture_started_ts: int | None = None
    stop_requested_ts: int | None = None
    stop_acknowledged_ts: int | None = None
    audio_bound: bool = False
    last_error: str | None = None
    last_ping_ts: int | None = None
    last_pong_ts: int | None = None
    last_audio_frame_ts: int | None = None
    last_control_disconnect_ts: int | None = None
    reconnect_deadline_ts: int | None = None
    audio_packet_count: int = 0

    def snapshot(self) -> dict:
        return {
            "session_id": self.session_id,
            "client_id": self.client_id,
            "state": self.state,
            "device_name": self.device_name,
            "browser": self.browser,
            "platform": self.platform,
            "active_capture_id": self.active_capture_id,
            "active_capture_started_ts": self.active_capture_started_ts,
            "stop_requested_ts": self.stop_requested_ts,
            "stop_acknowledged_ts": self.stop_acknowledged_ts,
            "audio_bound": self.audio_bound,
            "last_error": self.last_error,
            "last_ping_ts": self.last_ping_ts,
            "last_pong_ts": self.last_pong_ts,
            "last_audio_frame_ts": self.last_audio_frame_ts,
            "last_control_disconnect_ts": self.last_control_disconnect_ts,
            "reconnect_deadline_ts": self.reconnect_deadline_ts,
            "audio_packet_count": self.audio_packet_count,
        }
