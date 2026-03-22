from __future__ import annotations

import asyncio
import base64
import threading
from typing import Any

import aiohttp

from .... import runtime_core as core
from ....i18n import LOG_TAG_RT, t
from ..base import AsrCredentials, AsrProvider, AsrProviderError, RealtimeSession
from ._doubao_protocol import build_audio_request, build_auth_headers, build_full_client_request, parse_response, read_wav_audio_data, split_audio_segments

SAUC_NOSTREAM_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream"
SAUC_REALTIME_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel"
SAUC_RESOURCE_ID = "volc.bigasr.sauc.duration"
SEGMENT_DURATION_MS = 200


class DoubaoProvider(AsrProvider):
    def __init__(self, credentials: AsrCredentials) -> None:
        self._credentials = credentials

    def transcribe_non_stream(self, audio_base64: str, model_name: str) -> str:
        wav_bytes = base64.b64decode(audio_base64)
        try:
            return asyncio.run(self._transcribe_ws(wav_bytes, model_name))
        except AsrProviderError:
            raise
        except Exception as exc:
            raise AsrProviderError(f"Doubao ASR request failed: {exc}") from exc

    async def _transcribe_ws(self, wav_bytes: bytes, model_name: str) -> str:
        channels, sample_width, sample_rate, pcm_data = read_wav_audio_data(wav_bytes)
        segment_size = channels * sample_width * sample_rate * SEGMENT_DURATION_MS // 1000
        segments = split_audio_segments(pcm_data, segment_size)
        headers = build_auth_headers(self._credentials.app_key, self._credentials.api_key, SAUC_RESOURCE_ID)
        url = self._credentials.base_url or SAUC_NOSTREAM_URL

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url, headers=headers) as ws:
                seq = 1
                await ws.send_bytes(build_full_client_request(seq, model_name, sample_rate))
                seq += 1
                init_msg = await ws.receive()
                if init_msg.type != aiohttp.WSMsgType.BINARY:
                    raise AsrProviderError(f"Unexpected initial message type: {init_msg.type}")
                init_resp = parse_response(init_msg.data)
                if init_resp.code != 0:
                    raise AsrProviderError(f"Doubao init error code={init_resp.code}: {init_resp.payload_msg}")

                for index, segment in enumerate(segments):
                    is_last = index == len(segments) - 1
                    await ws.send_bytes(build_audio_request(seq, segment, is_last=is_last))
                    if not is_last:
                        seq += 1
                        await asyncio.sleep(SEGMENT_DURATION_MS / 1000)

                final_text_parts: list[str] = []
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.BINARY:
                        resp = parse_response(msg.data)
                        if resp.code != 0:
                            raise AsrProviderError(f"Doubao error code={resp.code}: {resp.payload_msg}")
                        if resp.payload_msg:
                            text = self._extract_text(resp.payload_msg)
                            if text:
                                final_text_parts.append(text)
                        if resp.is_last_package:
                            break
                    elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                        break
                return "".join(final_text_parts)

    def create_realtime_session(self, model_name: str) -> RealtimeSession:
        return DoubaoRealtimeSession(self._credentials, model_name)

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        result = payload.get("result", {})
        text = result.get("text", "")
        if text:
            return text
        utterances = result.get("utterances", [])
        parts = [item.get("text", "") for item in utterances if item.get("definite", False)]
        return "".join(parts)


class DoubaoRealtimeSession(RealtimeSession):
    def __init__(self, credentials: AsrCredentials, model_name: str) -> None:
        self._credentials = credentials
        self._model_name = model_name
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._seq = 1
        self._completed_texts: list[str] = []
        self._connected = threading.Event()
        self._finished = threading.Event()
        self._audio_queue: asyncio.Queue[bytes | None] | None = None

    def start(self) -> None:
        self._completed_texts = []
        self._connected.clear()
        self._finished.clear()
        self._seq = 1
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        if not self._connected.wait(timeout=8):
            raise AsrProviderError("Doubao WebSocket connection timed out")

    def send_audio(self, pcm_bytes: bytes) -> None:
        if self._audio_queue is not None and self._loop is not None:
            self._loop.call_soon_threadsafe(self._audio_queue.put_nowait, pcm_bytes)

    def finish_and_get_text(self) -> str:
        if self._audio_queue is not None and self._loop is not None:
            self._loop.call_soon_threadsafe(self._audio_queue.put_nowait, None)
        self._finished.wait(timeout=5)
        return "".join(self._completed_texts)

    def close(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._loop = None
        self._thread = None

    def _run_loop(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._session_task())
        except Exception:
            core.logger.exception("Doubao realtime session error")
        finally:
            self._finished.set()

    async def _session_task(self) -> None:
        self._audio_queue = asyncio.Queue()
        headers = build_auth_headers(self._credentials.app_key, self._credentials.api_key, SAUC_RESOURCE_ID)
        url = self._credentials.base_url or SAUC_REALTIME_URL
        self._session = aiohttp.ClientSession()
        try:
            self._ws = await self._session.ws_connect(url, headers=headers)
            core.log(f"{LOG_TAG_RT} {t('log.doubao_ws_connected')}")
            await self._ws.send_bytes(build_full_client_request(self._seq, self._model_name))
            self._seq += 1
            init_msg = await self._ws.receive()
            if init_msg.type == aiohttp.WSMsgType.BINARY:
                init_resp = parse_response(init_msg.data)
                if init_resp.code != 0:
                    raise AsrProviderError(f"Doubao init error: {init_resp.payload_msg}")
            self._connected.set()
            sender = asyncio.create_task(self._send_loop())
            receiver = asyncio.create_task(self._recv_loop())
            await asyncio.gather(sender, receiver)
        except Exception:
            core.logger.exception("Doubao realtime session task failed")
        finally:
            self._connected.set()
            self._finished.set()
            if self._ws is not None and not self._ws.closed:
                await self._ws.close()
            if self._session is not None and not self._session.closed:
                await self._session.close()

    async def _send_loop(self) -> None:
        assert self._audio_queue is not None and self._ws is not None
        while True:
            chunk = await self._audio_queue.get()
            if chunk is None:
                await self._ws.send_bytes(build_audio_request(self._seq, b"", is_last=True))
                break
            await self._ws.send_bytes(build_audio_request(self._seq, chunk, is_last=False))
            self._seq += 1

    async def _recv_loop(self) -> None:
        assert self._ws is not None
        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.BINARY:
                resp = parse_response(msg.data)
                if resp.code != 0:
                    core.log(f"{LOG_TAG_RT} {t('log.doubao_error', code=resp.code, message=resp.payload_msg)}")
                    break
                if resp.payload_msg:
                    text = self._extract_text(resp.payload_msg)
                    if text:
                        core.log(f"{LOG_TAG_RT} {t('log.realtime_confirmed_text', text=text)}")
                        self._completed_texts.append(text)
                        if core.osd_bubble is not None:
                            core.osd_bubble.sig_update_completed.emit(text)
                    stash = self._extract_stash(resp.payload_msg)
                    if stash:
                        if core.osd_bubble is not None:
                            core.osd_bubble.sig_update_stash.emit(stash)
                    print(f"\r[RT] {stash}", end="", flush=True)
                if resp.is_last_package:
                    core.log(f"{LOG_TAG_RT} {t('log.doubao_session_finished')}")
                    break
            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                core.log(f"{LOG_TAG_RT} {t('log.doubao_ws_closed')}")
                break

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        result = payload.get("result", {})
        utterances = result.get("utterances", [])
        parts = [item.get("text", "") for item in utterances if item.get("definite", False)]
        return "".join(parts)

    @staticmethod
    def _extract_stash(payload: dict[str, Any]) -> str:
        result = payload.get("result", {})
        utterances = result.get("utterances", [])
        parts = [item.get("text", "") for item in utterances if not item.get("definite", False)]
        return "".join(parts)
