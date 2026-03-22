from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future, TimeoutError as FutureTimeoutError

from ..config import AppConfig
from ..i18n import t
from ..runtime_env import package_resource, runtime_root
from ..transport import detect_local_ip
from .remote_phone_service import RemotePhoneService


class RemotePhoneRuntime:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._service: RemotePhoneService | None = None
        self._startup_event = threading.Event()
        self._startup_error: Exception | None = None
        self._pending_frame_handler = None
        self._public_host = self._resolve_public_host()
        self._status_lock = threading.Lock()
        self._status_cache = self._build_stopped_snapshot(last_service_error="")

    def start_service(self, timeout: float = 8.0) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._public_host = self._resolve_public_host()
        self._update_status_cache(self._build_stopped_snapshot(last_service_error=""))
        self._startup_event.clear()
        self._startup_error = None
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()
        if not self._startup_event.wait(timeout=timeout):
            raise TimeoutError(t("error.remote_phone_service_start_timeout"))
        if self._startup_error is not None:
            raise RuntimeError(t("error.remote_phone_service_start_failed", error=self._startup_error)) from self._startup_error

    def stop_service(self, timeout: float = 8.0) -> None:
        loop = self._loop
        service = self._service
        if not loop or not service:
            self._update_status_cache(self._build_stopped_snapshot(last_service_error=""))
            return
        future = asyncio.run_coroutine_threadsafe(service.shutdown(), loop)
        try:
            future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            raise TimeoutError(t("error.remote_phone_service_stop_timeout")) from exc
        finally:
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=timeout)
        self._loop = None
        self._thread = None
        self._service = None
        self._update_status_cache(self._build_stopped_snapshot(last_service_error=""))

    def restart_service(self) -> None:
        self.stop_service()
        self.start_service()

    def start_capture(self) -> None:
        self._require_service()
        self._submit(self._service.start_capture()).result()

    def stop_capture(self) -> None:
        if not self._service or not self._loop:
            return
        self._submit(self._service.stop_capture()).result()

    def set_frame_handler(self, handler) -> None:
        self._pending_frame_handler = handler
        if not self._service or not self._loop:
            return
        self._loop.call_soon_threadsafe(self._service.set_frame_handler, handler)

    def status_snapshot(self) -> dict:
        service = self._service
        if service is not None:
            snapshot = service.status_snapshot_sync()
            self._update_status_cache(snapshot)
            return dict(snapshot)
        with self._status_lock:
            return dict(self._status_cache)

    def is_service_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and self._service is not None)

    def phone_page_url(self) -> str:
        return str(self.status_snapshot().get("url", ""))

    def _submit(self, coro) -> Future:
        if not self._loop:
            raise RuntimeError(t("error.remote_phone_service_not_started"))
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def _require_service(self) -> None:
        if not self._service or not self._loop:
            raise RuntimeError(t("error.remote_phone_service_not_started"))

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            self._service = self._build_service()
            if self._pending_frame_handler is not None:
                self._service.set_frame_handler(self._pending_frame_handler)
            self._update_status_cache(self._service.status_snapshot_sync())
            loop.run_until_complete(self._bootstrap())
        finally:
            self._service = None
            self._loop = None
            self._update_status_cache(self._build_stopped_snapshot(last_service_error=""))
            loop.close()

    async def _bootstrap(self) -> None:
        try:
            assert self._service is not None
            await self._service.start()
            self._update_status_cache(self._service.status_snapshot_sync())
        except Exception as exc:
            self._startup_error = exc
            self._update_status_cache(self._build_stopped_snapshot(last_service_error=str(exc)))
            self._startup_event.set()
            return
        self._startup_event.set()
        try:
            await self._service.wait_closed()
        finally:
            await self._service.shutdown()
            self._update_status_cache(self._build_stopped_snapshot(last_service_error=""))

    def _build_service(self) -> RemotePhoneService:
        bind_host = self.config.remote_phone_host or "0.0.0.0"
        web_root = package_resource("web", "remote_phone")
        runtime_dir = runtime_root() / "remote_phone"
        return RemotePhoneService(bind_host=bind_host, public_host=self._public_host, http_port=self.config.remote_phone_http_port, control_port=self.config.remote_phone_control_port, audio_port=self.config.remote_phone_audio_port, web_root=web_root, runtime_root=runtime_dir)

    def _resolve_public_host(self) -> str:
        if self.config.remote_phone_host and self.config.remote_phone_host not in {"0.0.0.0", "::"}:
            return self.config.remote_phone_host
        return detect_local_ip()

    def _build_stopped_snapshot(self, *, last_service_error: str) -> dict:
        return {"service_running": False, "state": "PHONE_OFFLINE", "connected": False, "ready": False, "url": f"https://{self._public_host}:{self.config.remote_phone_http_port}", "public_host": self._public_host, "http_port": self.config.remote_phone_http_port, "control_port": self.config.remote_phone_control_port, "audio_port": self.config.remote_phone_audio_port, "cert_status": "missing", "last_service_error": last_service_error}

    def _update_status_cache(self, snapshot: dict) -> None:
        with self._status_lock:
            self._status_cache = dict(snapshot)
