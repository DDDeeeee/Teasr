"""Doubao (豆包) SAUC binary protocol helpers.

Adapted from sample/sauc_python/sauc_websocket_demo.py for production use.
"""

from __future__ import annotations

import gzip
import json
import struct
import uuid
from dataclasses import dataclass, field
from typing import Any


class ProtocolVersion:
    V1 = 0b0001


class MessageType:
    CLIENT_FULL_REQUEST = 0b0001
    CLIENT_AUDIO_ONLY_REQUEST = 0b0010
    SERVER_FULL_RESPONSE = 0b1001
    SERVER_ERROR_RESPONSE = 0b1111


class MessageTypeSpecificFlags:
    NO_SEQUENCE = 0b0000
    POS_SEQUENCE = 0b0001
    NEG_SEQUENCE = 0b0010
    NEG_WITH_SEQUENCE = 0b0011


class SerializationType:
    NO_SERIALIZATION = 0b0000
    JSON = 0b0001


class CompressionType:
    GZIP = 0b0001


def gzip_compress(data: bytes) -> bytes:
    return gzip.compress(data)


def gzip_decompress(data: bytes) -> bytes:
    return gzip.decompress(data)


def build_auth_headers(app_key: str, access_key: str, resource_id: str) -> dict[str, str]:
    return {
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": str(uuid.uuid4()),
        "X-Api-Access-Key": access_key,
        "X-Api-App-Key": app_key,
    }


def build_header_bytes(
    message_type: int = MessageType.CLIENT_FULL_REQUEST,
    flags: int = MessageTypeSpecificFlags.POS_SEQUENCE,
    serialization: int = SerializationType.JSON,
    compression: int = CompressionType.GZIP,
) -> bytes:
    header = bytearray()
    header.append((ProtocolVersion.V1 << 4) | 1)
    header.append((message_type << 4) | flags)
    header.append((serialization << 4) | compression)
    header.append(0x00)
    return bytes(header)


def build_full_client_request(seq: int, model_name: str, sample_rate: int = 16000) -> bytes:
    header = build_header_bytes(
        message_type=MessageType.CLIENT_FULL_REQUEST,
        flags=MessageTypeSpecificFlags.POS_SEQUENCE,
    )
    payload = {
        "user": {"uid": "asr_app_user"},
        "audio": {
            "format": "wav",
            "codec": "raw",
            "rate": sample_rate,
            "bits": 16,
            "channel": 1,
        },
        "request": {
            "model_name": model_name,
            "enable_itn": True,
            "enable_punc": True,
            "enable_ddc": True,
            "show_utterances": True,
        },
    }
    compressed = gzip_compress(json.dumps(payload).encode("utf-8"))
    request = bytearray()
    request.extend(header)
    request.extend(struct.pack(">i", seq))
    request.extend(struct.pack(">I", len(compressed)))
    request.extend(compressed)
    return bytes(request)


def build_audio_request(seq: int, audio_segment: bytes, is_last: bool = False) -> bytes:
    if is_last:
        flags = MessageTypeSpecificFlags.NEG_WITH_SEQUENCE
        wire_seq = -seq
    else:
        flags = MessageTypeSpecificFlags.POS_SEQUENCE
        wire_seq = seq

    header = build_header_bytes(
        message_type=MessageType.CLIENT_AUDIO_ONLY_REQUEST,
        flags=flags,
    )
    compressed = gzip_compress(audio_segment)
    request = bytearray()
    request.extend(header)
    request.extend(struct.pack(">i", wire_seq))
    request.extend(struct.pack(">I", len(compressed)))
    request.extend(compressed)
    return bytes(request)


@dataclass(slots=True)
class DoubaoResponse:
    code: int = 0
    event: int = 0
    is_last_package: bool = False
    payload_sequence: int = 0
    payload_size: int = 0
    payload_msg: dict[str, Any] | None = None


def parse_response(msg: bytes) -> DoubaoResponse:
    resp = DoubaoResponse()
    header_size = msg[0] & 0x0F
    message_type = msg[1] >> 4
    message_type_specific_flags = msg[1] & 0x0F
    serialization_method = msg[2] >> 4
    message_compression = msg[2] & 0x0F

    payload = msg[header_size * 4:]

    if message_type_specific_flags & 0x01:
        resp.payload_sequence = struct.unpack(">i", payload[:4])[0]
        payload = payload[4:]
    if message_type_specific_flags & 0x02:
        resp.is_last_package = True
    if message_type_specific_flags & 0x04:
        resp.event = struct.unpack(">i", payload[:4])[0]
        payload = payload[4:]

    if message_type == MessageType.SERVER_FULL_RESPONSE:
        resp.payload_size = struct.unpack(">I", payload[:4])[0]
        payload = payload[4:]
    elif message_type == MessageType.SERVER_ERROR_RESPONSE:
        resp.code = struct.unpack(">i", payload[:4])[0]
        resp.payload_size = struct.unpack(">I", payload[4:8])[0]
        payload = payload[8:]

    if not payload:
        return resp

    if message_compression == CompressionType.GZIP:
        try:
            payload = gzip_decompress(payload)
        except Exception:
            return resp

    if serialization_method == SerializationType.JSON:
        try:
            resp.payload_msg = json.loads(payload.decode("utf-8"))
        except Exception:
            pass

    return resp


def split_audio_segments(data: bytes, segment_size: int) -> list[bytes]:
    if segment_size <= 0:
        return []
    return [data[i : i + segment_size] for i in range(0, len(data), segment_size)]


def read_wav_audio_data(wav_bytes: bytes) -> tuple[int, int, int, bytes]:
    """Parse WAV and return (channels, sample_width, sample_rate, pcm_data)."""
    if len(wav_bytes) < 44 or wav_bytes[:4] != b"RIFF" or wav_bytes[8:12] != b"WAVE":
        raise ValueError("Invalid WAV data")

    num_channels = struct.unpack("<H", wav_bytes[22:24])[0]
    sample_rate = struct.unpack("<I", wav_bytes[24:28])[0]
    bits_per_sample = struct.unpack("<H", wav_bytes[34:36])[0]
    sample_width = bits_per_sample // 8

    pos = 36
    while pos < len(wav_bytes) - 8:
        subchunk_id = wav_bytes[pos : pos + 4]
        subchunk_size = struct.unpack("<I", wav_bytes[pos + 4 : pos + 8])[0]
        if subchunk_id == b"data":
            pcm_data = wav_bytes[pos + 8 : pos + 8 + subchunk_size]
            return num_channels, sample_width, sample_rate, pcm_data
        pos += 8 + subchunk_size

    raise ValueError("WAV data chunk not found")
