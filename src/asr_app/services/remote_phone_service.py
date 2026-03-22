from __future__ import annotations

import asyncio
import json
import logging
import secrets
import ssl

LOGGER = logging.getLogger('asr')
import threading
import uuid
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from websockets.exceptions import ConnectionClosed
from websockets.server import WebSocketServerProtocol, serve

from ..i18n import get_lang, remote_web_translations, t
from ..transport import (
    FRAME_MS,
    PROTOCOL_VERSION,
    TARGET_CHANNELS,
    TARGET_SAMPLE_RATE,
    PhoneSession,
    build_control_message,
    current_timestamp_ms,
    ensure_self_signed_cert,
    parse_audio_packet,
)

HEARTBEAT_INTERVAL_MS = 5_000
HEARTBEAT_TIMEOUT_MS = 30_000
AUDIO_FRAME_TIMEOUT_MS = 4_000
START_CAPTURE_TIMEOUT_MS = 5_000
STOP_ACK_TIMEOUT_MS = 1_500
CONTROL_RECONNECT_GRACE_MS = 8_000
WEBSOCKET_CLOSE_TIMEOUT_S = 1.0
ACCESS_TOKEN_LENGTH = 6
ACCESS_TOKEN_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
WEBSOCKET_UNAUTHORIZED_CODE = 1008
PROTECTED_HTTP_PATHS = {'/', '/index.html', '/runtime-config', '/runtime-config.js'}


class QuietStaticHandler(SimpleHTTPRequestHandler):
    runtime_config: dict = {}
    access_token: str = ""

    def __init__(
        self,
        *args,
        directory: str | None = None,
        runtime_config: dict | None = None,
        access_token: str | None = None,
        **kwargs,
    ) -> None:
        if runtime_config is not None:
            self.runtime_config = runtime_config
        if access_token is not None:
            self.access_token = access_token
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        request_path = parsed.path or "/"
        request_token = parse_qs(parsed.query).get("token", [""])[0]

        if request_path in PROTECTED_HTTP_PATHS and request_token != self.access_token:
            self._send_unauthorized()
            return

        self.path = request_path

        if request_path == "/runtime-config":
            payload = json.dumps(self.runtime_config)
            encoded = payload.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded)
            return
        if request_path == "/runtime-config.js":
            payload = "window.ASR_REMOTE_PHONE_CONFIG = " + json.dumps(self.runtime_config) + ";\n"
            encoded = payload.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded)
            return
        super().do_GET()

    def _send_unauthorized(self) -> None:
        encoded = b"Unauthorized"
        self.send_response(401)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:
        return


class RemotePhoneService:
    def __init__(
        self,
        *,
        bind_host: str,
        public_host: str,
        http_port: int,
        control_port: int,
        audio_port: int,
        web_root: Path,
        runtime_root: Path,
    ) -> None:
        self.bind_host = bind_host
        self.public_host = public_host
        self.http_port = http_port
        self.control_port = control_port
        self.audio_port = audio_port
        self.web_root = web_root
        self.runtime_root = runtime_root
        self.cert_dir = runtime_root / "certs"

        self._control_server = None
        self._audio_server = None
        self._http_server: ThreadingHTTPServer | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()
        self._teardown_lock = asyncio.Lock()
        self._frame_handler = None
        self._capture_started = asyncio.Event()
        self._capture_finished = asyncio.Event()
        self._running = False
        self._cert_path: Path | None = None
        self._key_path: Path | None = None
        self._last_service_error = ""
        self.access_token = self._generate_access_token()

        self.session: PhoneSession | None = None
        self.control_ws: WebSocketServerProtocol | None = None
        self.audio_ws: WebSocketServerProtocol | None = None

    async def start(self) -> None:
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self._cert_path, self._key_path = ensure_self_signed_cert(self.cert_dir, self.public_host)
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(certfile=self._cert_path, keyfile=self._key_path)

        self._start_https_server(ssl_context)
        self._control_server = await serve(self._handle_control_ws, self.bind_host, self.control_port, ssl=ssl_context)
        self._audio_server = await serve(self._handle_audio_ws, self.bind_host, self.audio_port, ssl=ssl_context)
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._running = True
        self._last_service_error = ""
        self._log_info("remote_phone_service_started", url=self.phone_page_url())

    async def wait_closed(self) -> None:
        await self._shutdown_event.wait()

    async def shutdown(self) -> None:
        if self._shutdown_event.is_set() and not self._running:
            return
        self._shutdown_event.set()
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            await asyncio.gather(self._heartbeat_task, return_exceptions=True)
            self._heartbeat_task = None
        await self._teardown_session("service_shutdown", send_disconnect=True)
        if self._control_server is not None:
            self._control_server.close()
            await self._control_server.wait_closed()
            self._control_server = None
        if self._audio_server is not None:
            self._audio_server.close()
            await self._audio_server.wait_closed()
            self._audio_server = None
        if self._http_server is not None:
            await asyncio.to_thread(self._stop_https_server)
        self._running = False
        self._log_info("remote_phone_service_stopped")

    def set_frame_handler(self, handler) -> None:
        self._frame_handler = handler

    async def start_capture(self) -> None:
        if not self.session or not self.control_ws:
            raise RuntimeError(t("error.remote_phone_not_connected"))
        if self.session.state != "PHONE_READY":
            raise RuntimeError(t("error.remote_phone_not_ready"))

        capture_id = f"cap_{uuid.uuid4().hex[:8]}"
        now = current_timestamp_ms()
        self.session.active_capture_id = capture_id
        self.session.active_capture_started_ts = now
        self.session.stop_requested_ts = None
        self.session.stop_acknowledged_ts = None
        self.session.last_audio_frame_ts = None
        self.session.audio_packet_count = 0
        self.session.last_error = None
        self.session.state = "STARTING"
        self._capture_started.clear()
        self._capture_finished.clear()
        self._log_info("capture_start_requested", session_id=self.session.session_id, capture_id=capture_id)

        try:
            await self.control_ws.send(
                build_control_message("start_capture", self.session.session_id, {"capture_id": capture_id})
            )
        except ConnectionClosed as exc:
            await self._detach_control_ws("control_channel_closed", close_socket=False)
            raise RuntimeError(t("error.remote_control_disconnected")) from exc

        try:
            await asyncio.wait_for(self._capture_started.wait(), timeout=START_CAPTURE_TIMEOUT_MS / 1000)
        except TimeoutError as exc:
            if self.session:
                self.session.last_error = "capture_start_timeout"
            await self._close_audio_ws()
            self._finalize_active_capture("capture_start_timeout")
            raise RuntimeError(t("error.remote_capture_start_timeout")) from exc

        if not self.session or self.session.state not in {"STARTING", "RECORDING"}:
            raise RuntimeError(t("error.remote_capture_interrupted"))

    async def stop_capture(self) -> None:
        if not self.session or not self.session.active_capture_id:
            return
        if self.session.state not in {"STARTING", "RECORDING", "STOPPING"}:
            return

        capture_id = self.session.active_capture_id
        self.session.state = "STOPPING"
        self.session.stop_requested_ts = current_timestamp_ms()
        self.session.stop_acknowledged_ts = None
        self._capture_finished.clear()
        self._log_info("capture_stop_requested", session_id=self.session.session_id, capture_id=capture_id)

        if self.control_ws is not None:
            try:
                await self.control_ws.send(
                    build_control_message("stop_capture", self.session.session_id, {"capture_id": capture_id})
                )
            except ConnectionClosed:
                await self._detach_control_ws("control_channel_closed", close_socket=False)

        try:
            await asyncio.wait_for(self._capture_finished.wait(), timeout=(STOP_ACK_TIMEOUT_MS + 1000) / 1000)
        except TimeoutError:
            if self.session:
                self.session.last_error = "capture_stop_timeout"
            await self._close_audio_ws()
            self._finalize_active_capture("capture_stop_timeout")

    async def status_snapshot(self) -> dict:
        return self.status_snapshot_sync()

    def status_snapshot_sync(self) -> dict:
        session_snapshot = self.session.snapshot() if self.session else {}
        state = session_snapshot.get("state", "PHONE_OFFLINE")
        return {
            "service_running": self._running,
            "state": state,
            "connected": bool(self.session and self.control_ws),
            "ready": state == "PHONE_READY",
            "url": self.phone_page_url(),
            "bind_host": self.bind_host,
            "public_host": self.public_host,
            "http_port": self.http_port,
            "control_port": self.control_port,
            "audio_port": self.audio_port,
            "cert_path": str(self._cert_path) if self._cert_path else "",
            "cert_status": "ready" if self._cert_path and self._key_path else "missing",
            "last_service_error": self._last_service_error,
            **session_snapshot,
        }
    def phone_page_url(self) -> str:
        query = urlencode({"token": self.access_token})
        return f"https://{self.public_host}:{self.http_port}/?{query}"

    def _start_https_server(self, ssl_context: ssl.SSLContext) -> None:
        runtime_config = {
            "controlPort": self.control_port,
            "audioPort": self.audio_port,
            "publicHost": self.public_host,
            "language": get_lang(),
            "translations": remote_web_translations(),
        }
        handler = partial(
            QuietStaticHandler,
            directory=str(self.web_root),
            runtime_config=runtime_config,
            access_token=self.access_token,
        )
        self._http_server = ThreadingHTTPServer((self.bind_host, self.http_port), handler)
        self._http_server.socket = ssl_context.wrap_socket(self._http_server.socket, server_side=True)
        thread = threading.Thread(target=self._http_server.serve_forever, daemon=True)
        thread.start()

    def _stop_https_server(self) -> None:
        server = self._http_server
        if server is None:
            return
        self._http_server = None
        server.shutdown()
        server.server_close()

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL_MS / 1000)
            except asyncio.CancelledError:
                return

            if not self.session:
                continue

            now = current_timestamp_ms()
            if self._reconnect_grace_expired(now):
                self.session.last_error = "control_reconnect_timeout"
                self._log_warning("control_reconnect_grace_expired", session_id=self.session.session_id)
                await self._teardown_session("control_reconnect_timeout")
                continue

            if self._control_timed_out(now):
                self.session.last_error = "control_timeout"
                self._log_warning("control_timeout", session_id=self.session.session_id)
                await self._detach_control_ws("control_timeout", close_socket=True)
                continue

            if self._stop_ack_timed_out(now):
                self.session.last_error = "stop_ack_timeout"
                await self._close_audio_ws()
                self._finalize_active_capture("stop_ack_timeout")
                continue

            if self._audio_timed_out(now):
                self.session.last_error = "audio_timeout"
                await self._close_audio_ws()
                self._log_warning("audio_timeout", session_id=self.session.session_id)
                self._finalize_active_capture("audio_timeout")
                continue

            if self.control_ws is None:
                continue

            try:
                self.session.last_ping_ts = now
                await self.control_ws.send(
                    build_control_message("ping", self.session.session_id, {"nonce": str(uuid.uuid4())})
                )
            except ConnectionClosed:
                self._log_warning("control_ping_failed", session_id=self.session.session_id)
                await self._detach_control_ws("control_channel_closed", close_socket=False)

    def _control_timed_out(self, now: int) -> bool:
        if not self.session or not self.control_ws or self.session.last_pong_ts is None:
            return False
        return now - self.session.last_pong_ts > HEARTBEAT_TIMEOUT_MS

    def _reconnect_grace_expired(self, now: int) -> bool:
        if not self.session or self.control_ws is not None:
            return False
        if self.session.reconnect_deadline_ts is None:
            return False
        return now > self.session.reconnect_deadline_ts

    def _stop_ack_timed_out(self, now: int) -> bool:
        if not self.session or self.session.state != "STOPPING" or not self.session.active_capture_id:
            return False
        if self.session.stop_acknowledged_ts is not None or self.session.stop_requested_ts is None:
            return False
        return now - self.session.stop_requested_ts > STOP_ACK_TIMEOUT_MS

    def _audio_timed_out(self, now: int) -> bool:
        if not self.session or self.session.state not in {"STARTING", "RECORDING", "STOPPING"}:
            return False
        if not self.session.active_capture_id:
            return False
        reference_ts = self.session.last_audio_frame_ts or self.session.active_capture_started_ts
        if reference_ts is None:
            return False
        return now - reference_ts > AUDIO_FRAME_TIMEOUT_MS

    async def _handle_control_ws(self, websocket: WebSocketServerProtocol) -> None:
        query = parse_qs(urlparse(websocket.path).query)
        token = query.get("token", [""])[0]
        if token != self.access_token:
            await self._close_websocket_quickly(websocket, code=WEBSOCKET_UNAUTHORIZED_CODE, reason="invalid token")
            return

        client_id = query.get("client_id", [None])[0] or f"client_{uuid.uuid4().hex[:8]}"
        now = current_timestamp_ms()
        previous_ws: WebSocketServerProtocol | None = None

        if self.session is not None and self.control_ws is None and self._reconnect_grace_expired(now):
            await self._teardown_session("stale_session_replaced")

        if self.session is None:
            session_id = f"sess_{uuid.uuid4().hex[:8]}"
            self.session = PhoneSession(
                session_id=session_id,
                client_id=client_id,
                last_ping_ts=now,
                last_pong_ts=now,
            )
            resumed = False
            self._log_info("control_connected", session_id=session_id, client_id=client_id, resumed=resumed)
        elif self.session.client_id == client_id:
            resumed = True
            previous_ws = self.control_ws
            self._log_info(
                "control_reconnected",
                session_id=self.session.session_id,
                client_id=client_id,
                resumed=resumed,
            )
        else:
            self._log_warning(
                "control_session_conflict",
                current_session_id=self.session.session_id,
                current_client_id=self.session.client_id,
                incoming_client_id=client_id,
            )
            await websocket.send(
                json.dumps(
                    {
                        "type": "error",
                        "session_id": "",
                        "ts": 0,
                        "payload": {"code": "session_conflict", "message": "only one phone is supported"},
                    }
                )
            )
            await self._close_websocket_quickly(websocket)
            return

        assert self.session is not None
        self.control_ws = websocket
        self.session.client_id = client_id
        self.session.last_ping_ts = now
        self.session.last_pong_ts = now
        self.session.last_control_disconnect_ts = None
        self.session.reconnect_deadline_ts = None
        if self.session.state == "PHONE_RECONNECTING":
            self.session.state = self._ready_state(connected=True)

        if previous_ws is not None and previous_ws is not websocket:
            await self._close_websocket_quickly(previous_ws)

        await websocket.send(
            build_control_message(
                "hello",
                self.session.session_id,
                {
                    "server_name": "asr-assistant",
                    "protocol_version": PROTOCOL_VERSION,
                    "audio_format": {
                        "sample_rate": TARGET_SAMPLE_RATE,
                        "channels": TARGET_CHANNELS,
                        "sample_format": "pcm_s16le",
                        "frame_ms": FRAME_MS,
                    },
                    "audio_port": self.audio_port,
                    "resumed": resumed,
                },
            )
        )

        try:
            async for raw_message in websocket:
                if isinstance(raw_message, bytes):
                    continue
                await self._handle_control_message(raw_message)
        except ConnectionClosed:
            self._log_info("control_socket_closed", session_id=self.session.session_id if self.session else "")
        finally:
            await self._detach_control_ws("control_channel_closed", websocket=websocket, close_socket=False)

    async def _handle_control_message(self, raw_message: str) -> None:
        if not self.session:
            return
        try:
            message = json.loads(raw_message)
        except json.JSONDecodeError:
            return

        message_type = message.get("type")
        payload = message.get("payload", {})
        capture_id = payload.get("capture_id")

        if message_type == "ready":
            self.session.state = "PHONE_READY"
            self.session.device_name = payload.get("device_name")
            self.session.browser = payload.get("browser")
            self.session.platform = payload.get("platform")
            self.session.last_error = None
            self._log_info(
                "phone_ready",
                session_id=self.session.session_id,
                device_name=self.session.device_name or "",
                browser=self.session.browser or "",
            )
            return

        if message_type == "capturing" and capture_id == self.session.active_capture_id:
            self.session.state = "STARTING"
            self.session.last_error = None
            self._log_info("capture_acknowledged", session_id=self.session.session_id, capture_id=capture_id)
            return

        if message_type == "stopped" and capture_id == self.session.active_capture_id:
            self.session.stop_acknowledged_ts = current_timestamp_ms()
            if self.audio_ws is None:
                self._finalize_active_capture("phone_stop_ack")
            return

        if message_type == "pong":
            self.session.last_pong_ts = current_timestamp_ms()
            return

        if message_type == "error":
            self.session.last_error = payload.get("code") or payload.get("message") or "remote_error"
            self.session.state = "ERROR"
            self._log_warning(
                "phone_reported_error",
                session_id=self.session.session_id,
                error=self.session.last_error or "",
            )
            if self.session.active_capture_id:
                await self._close_audio_ws()
                self._finalize_active_capture("phone_error")

    async def _handle_audio_ws(self, websocket: WebSocketServerProtocol) -> None:
        if not self.session:
            await self._close_websocket_quickly(websocket)
            return

        query = parse_qs(urlparse(websocket.path).query)
        token = query.get("token", [""])[0]
        if token != self.access_token:
            await self._close_websocket_quickly(websocket, code=WEBSOCKET_UNAUTHORIZED_CODE, reason="invalid token")
            return

        session_id = query.get("session_id", [None])[0]
        if session_id != self.session.session_id:
            await self._close_websocket_quickly(websocket)
            return

        if self.audio_ws and self.audio_ws is not websocket:
            await self._close_websocket_quickly(self.audio_ws)

        self.audio_ws = websocket
        self.session.audio_bound = True
        self._log_info("audio_socket_bound", session_id=self.session.session_id)

        try:
            async for raw_packet in websocket:
                if not isinstance(raw_packet, bytes):
                    continue
                try:
                    self._handle_audio_packet(raw_packet)
                except Exception as exc:
                    if self.session:
                        self.session.last_error = f"audio_packet_invalid: {exc}"
                    self._log_warning(
                        "audio_packet_invalid",
                        session_id=self.session.session_id if self.session else "",
                        error=str(exc),
                    )
                    break
        except ConnectionClosed:
            self._log_info("audio_socket_closed", session_id=self.session.session_id if self.session else "")
        finally:
            if self.audio_ws is websocket:
                self.audio_ws = None
            if self.session:
                self.session.audio_bound = False
                if self.session.active_capture_id:
                    if self.session.state == "STOPPING" and self.session.stop_acknowledged_ts is not None:
                        self._finalize_active_capture("audio_channel_closed")
                    elif self.session.state in {"STARTING", "RECORDING"}:
                        self.session.last_error = "audio_channel_closed"
                        self._finalize_active_capture("audio_channel_closed")

    def _handle_audio_packet(self, raw_packet: bytes) -> None:
        if not self.session or not self.session.active_capture_id:
            return

        packet = parse_audio_packet(raw_packet)
        if packet.capture_id != self.session.active_capture_id:
            return

        self.session.last_audio_frame_ts = current_timestamp_ms()
        self.session.audio_packet_count += 1
        if self.session.audio_packet_count == 1:
            self._log_info(
                "audio_first_packet",
                session_id=self.session.session_id,
                capture_id=packet.capture_id,
                payload_len=len(packet.pcm_payload),
            )
        if self._frame_handler is not None:
            self._frame_handler(packet.pcm_payload)

        if self.session.state == "STARTING":
            self.session.state = "RECORDING"
            self._capture_started.set()

    async def _close_audio_ws(self) -> None:
        websocket = self.audio_ws
        if websocket is None:
            return
        self.audio_ws = None
        await self._close_websocket_quickly(websocket)

    async def _close_websocket_quickly(
        self,
        websocket: WebSocketServerProtocol | None,
        *,
        code: int = 1000,
        reason: str = "",
    ) -> None:
        if websocket is None:
            return
        try:
            await asyncio.wait_for(websocket.close(code=code, reason=reason), timeout=WEBSOCKET_CLOSE_TIMEOUT_S)
        except Exception:
            pass

    def _finalize_active_capture(self, reason: str) -> None:
        if not self.session or not self.session.active_capture_id:
            return

        self._log_info(
            "capture_finalized",
            session_id=self.session.session_id,
            capture_id=self.session.active_capture_id,
            reason=reason,
            control_connected=bool(self.control_ws),
        )
        self.session.active_capture_id = None
        self.session.active_capture_started_ts = None
        self.session.stop_requested_ts = None
        self.session.stop_acknowledged_ts = None
        self.session.last_audio_frame_ts = None
        self.session.audio_packet_count = 0
        self.session.audio_bound = False
        self.session.state = self._ready_state(connected=bool(self.control_ws))
        if reason and not self.session.last_error and reason not in {"phone_stop_ack", "audio_channel_closed"}:
            self.session.last_error = reason
        self._capture_finished.set()

    async def _detach_control_ws(
        self,
        reason: str,
        *,
        websocket: WebSocketServerProtocol | None = None,
        close_socket: bool,
    ) -> None:
        async with self._teardown_lock:
            if self.session is None:
                return
            control_ws = self.control_ws
            if websocket is not None and control_ws is not websocket:
                return

            self.control_ws = None
            now = current_timestamp_ms()
            self.session.last_control_disconnect_ts = now
            self.session.reconnect_deadline_ts = now + CONTROL_RECONNECT_GRACE_MS
            if self.session.active_capture_id:
                await self._close_audio_ws()
                self._finalize_active_capture(reason)
            else:
                self.session.state = "PHONE_RECONNECTING"
            if reason and not self.session.last_error:
                self.session.last_error = reason
            self._log_warning(
                "control_detached",
                session_id=self.session.session_id,
                reason=reason,
                reconnect_deadline_ts=self.session.reconnect_deadline_ts,
            )
            if close_socket and control_ws is not None:
                await self._close_websocket_quickly(control_ws)

    async def _teardown_session(
        self,
        reason: str,
        *,
        send_disconnect: bool = False,
        close_control: bool = True,
    ) -> None:
        async with self._teardown_lock:
            session = self.session
            control_ws = self.control_ws
            audio_ws = self.audio_ws
            self.control_ws = None
            self.audio_ws = None

            if send_disconnect and session and control_ws:
                try:
                    await control_ws.send(
                        build_control_message("disconnect", session.session_id, {"reason": reason})
                    )
                except Exception:
                    pass

            if audio_ws:
                await self._close_websocket_quickly(audio_ws)

            if close_control and control_ws:
                await self._close_websocket_quickly(control_ws)

            self._capture_started.set()
            self._capture_finished.set()
            self._log_warning("session_torn_down", reason=reason, session_id=session.session_id if session else "")
            self.session = None

    def _ready_state(self, *, connected: bool) -> str:
        if self.session is None:
            return "PHONE_OFFLINE"
        if connected:
            return "PHONE_READY" if self.session.device_name else "PHONE_CONNECTED"
        return "PHONE_RECONNECTING" if self.session.device_name else "PHONE_OFFLINE"

    def _log_info(self, event: str, **fields) -> None:
        return

    def _log_warning(self, event: str, **fields) -> None:
        return

    def _log_debug(self, event: str, **fields) -> None:
        return

    @staticmethod
    def _format_fields(fields: dict) -> str:
        return " ".join(f"{key}={value}" for key, value in fields.items() if value not in {None, ""})

    @staticmethod
    def _generate_access_token() -> str:
        return "".join(secrets.choice(ACCESS_TOKEN_ALPHABET) for _ in range(ACCESS_TOKEN_LENGTH))



