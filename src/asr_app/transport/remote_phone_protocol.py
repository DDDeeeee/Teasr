from __future__ import annotations

import json
import struct
from dataclasses import dataclass


PROTOCOL_VERSION = 1
TARGET_SAMPLE_RATE = 16_000
TARGET_CHANNELS = 1
FRAME_MS = 40
FRAME_SIZE = TARGET_SAMPLE_RATE * FRAME_MS // 1000
AUDIO_MAGIC = b"RMIC"
AUDIO_HEADER_STRUCT = struct.Struct("!4sBBHIBIQ")
AUDIO_BASE_HEADER_SIZE = AUDIO_HEADER_STRUCT.size


def current_timestamp_ms() -> int:
    from time import time

    return int(time() * 1000)


def build_control_message(message_type: str, session_id: str, payload: dict) -> str:
    return json.dumps(
        {
            "type": message_type,
            "session_id": session_id,
            "ts": current_timestamp_ms(),
            "payload": payload,
        },
        ensure_ascii=True,
    )


@dataclass(slots=True)
class AudioPacket:
    capture_id: str
    frame_seq: int
    timestamp_ms: int
    pcm_payload: bytes


def parse_audio_packet(packet: bytes) -> AudioPacket:
    if len(packet) < AUDIO_BASE_HEADER_SIZE:
        raise ValueError("audio packet too short")

    magic, version, _flags, header_len, payload_len, capture_id_len, frame_seq, timestamp_ms = (
        AUDIO_HEADER_STRUCT.unpack(packet[:AUDIO_BASE_HEADER_SIZE])
    )
    if magic != AUDIO_MAGIC:
        raise ValueError("invalid packet magic")
    if version != PROTOCOL_VERSION:
        raise ValueError("unsupported protocol version")
    if header_len != AUDIO_BASE_HEADER_SIZE + capture_id_len:
        raise ValueError("invalid packet header length")
    if len(packet) != header_len + payload_len:
        raise ValueError("invalid packet payload length")

    capture_start = AUDIO_BASE_HEADER_SIZE
    capture_end = capture_start + capture_id_len
    return AudioPacket(
        capture_id=packet[capture_start:capture_end].decode("utf-8"),
        frame_seq=frame_seq,
        timestamp_ms=timestamp_ms,
        pcm_payload=packet[capture_end:],
    )
