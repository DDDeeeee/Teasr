import base64
import ctypes
import io
import signal
import sys
import threading
import time
import traceback

import keyboard
import numpy as np
import sounddevice as sd
import soundfile as sf
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from .caret_locator import enable_per_monitor_dpi_awareness, get_caret_position
from .config import AppConfig
from .modes import MODE_NON_STREAM, MODE_NON_STREAM_POLISH, MODE_REALTIME, MODE_REALTIME_POLISH
from .runtime_env import LOG_PATH
from .runtime_logging import logger
from .polish_parser import describe_stream_issue
from .text_polisher import TextPolisherError, request_polished_text, stream_polished_text
from .runtime_core import (
    add_log_listener,
    remove_log_listener,
    log,
    send_unicode_text,
    get_foreground_window,
    is_same_foreground_window,
    transcribe_non_stream,
    RealtimeTranscriber,
)


enable_per_monitor_dpi_awareness()

osd_bubble = None
recording_indicator = None


class AudioRecorder:
    def __init__(self, sample_rate=16000, mode=MODE_NON_STREAM, config=None, input_device=None):
        self.recording = False
        self.audio_data = []
        self.stream = None
        self.sample_rate = sample_rate
        self.caps_state_before = None
        self._suppress_until = 0
        self._press_time = 0
        self.mode = mode
        self.config = config or AppConfig.from_env()
        self.input_device = input_device
        self._realtime = None

    def _is_realtime_mode(self):
        return self.mode in {MODE_REALTIME, MODE_REALTIME_POLISH}

    def _is_non_realtime_polish_mode(self):
        return self.mode == MODE_NON_STREAM_POLISH

    def _is_polish_mode(self):
        return self.mode == MODE_REALTIME_POLISH

    def callback(self, indata, frames, time_info, status):
        if status:
            log(f"[音频状态] {status}")
        if not self.recording:
            return
        if self._is_realtime_mode() and self._realtime is not None:
            pcm_int16 = (indata[:, 0] * 32767).astype(np.int16)
            self._realtime.send_audio(pcm_int16.tobytes())
            return
        self.audio_data.append(indata.copy())
        if recording_indicator is not None:
            rms = float(np.sqrt(np.mean(indata ** 2)))
            recording_indicator.sig_audio_level.emit([rms])

    def start_recording(self):
        if self.recording or time.time() < self._suppress_until:
            return

        vk_capital = 0x14
        self.caps_state_before = ctypes.windll.user32.GetKeyState(vk_capital) & 0x0001
        self._press_time = time.time()
        log("\n[录音中] ...")
        self.recording = True
        self.audio_data = []

        if self._is_realtime_mode():
            caret = get_caret_position()
            if osd_bubble is not None:
                osd_bubble.sig_show.emit(caret.x, caret.y, caret.height, caret.source)
            try:
                self._realtime = RealtimeTranscriber(self.config.resolved_asr_api_key(), self.config.asr_realtime_model)
                self._realtime.start()
            except Exception as e:
                self.recording = False
                self._realtime = None
                log(f"[错误] 无法建立实时连接: {e}")
                logger.exception("Failed to start realtime connection")
                return
        else:
            if recording_indicator is not None:
                recording_indicator.sig_show.emit()

        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                callback=self.callback,
                dtype="float32",
                device=self.input_device,
            )
            self.stream.start()
        except Exception as e:
            self.recording = False
            self.stream = None
            if self._realtime is not None:
                self._realtime.close()
                self._realtime = None
            log(f"[错误] 无法启动录音: {e}")
            logger.exception("Failed to start recording")

    def stop_and_transcribe(self):
        if not self.recording:
            return

        self.recording = False
        stream = self.stream
        self.stream = None
        if stream is not None:
            stream.stop()
            stream.close()

        if self._is_realtime_mode():
            self._stop_realtime()
            return

        self._hide_indicator()

        if not self.audio_data:
            log("[提示] 本次录音为空")
            return

        my_recording = np.concatenate(self.audio_data, axis=0)
        try:
            buf = io.BytesIO()
            sf.write(buf, my_recording, self.sample_rate, format="WAV")
            audio_base64 = base64.b64encode(buf.getvalue()).decode()

            log("[识别中] ...")

            full_text = ""
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    full_text = transcribe_non_stream(
                        audio_base64,
                        self.config.resolved_asr_api_key(),
                        self.config.asr_non_stream_model,
                    )
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait = attempt + 1
                        log(
                            f"[重试] 第{attempt + 1}次请求失败，"
                            f"{wait}秒后重试: {e}"
                        )
                        time.sleep(wait)
                        full_text = ""
                    else:
                        raise

            if self._is_non_realtime_polish_mode():
                self._input_polished_text(full_text, "[录音+优化]")
            else:
                self._input_text(full_text)
        except Exception as e:
            log(f"[错误] {e}")
            logger.exception("Transcribe failed")
            traceback.print_exc()

    def _stop_realtime(self):
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
            threading.Thread(
                target=self._cleanup_realtime,
                args=(realtime,),
                daemon=True,
            ).start()

    def _stop_realtime_plain(self, realtime):
        self._hide_osd()
        full_text = realtime.finish_and_get_text()
        self._input_text(full_text)

    def _stop_realtime_with_polish(self, realtime):
        full_text = realtime.finish_and_get_text()
        if not full_text:
            self._hide_osd()
            log("[提示] 实时模式未识别到文字")
            return

        log(f"[实时+优化] 原始文本: {full_text}")
        if osd_bubble is not None:
            osd_bubble.sig_set_phase.emit("polishing")

        self._input_polished_text(full_text, "[实时+优化]", before_first_chunk=self._hide_osd)

    def _cleanup_realtime(self, realtime):
        try:
            realtime.close()
        except Exception:
            logger.exception("Realtime cleanup failed")

    def _hide_osd(self):
        if osd_bubble is not None:
            osd_bubble.sig_hide.emit()

    def _hide_indicator(self):
        if recording_indicator is not None:
            recording_indicator.sig_hide.emit()

    def cancel_recording(self, *, restore_caps_lock=False):
        self.recording = False
        self.audio_data = []
        self._press_time = 0

        stream = self.stream
        self.stream = None
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                logger.exception("Failed to stop input stream during cleanup")
            try:
                stream.close()
            except Exception:
                logger.exception("Failed to close input stream during cleanup")

        if self._realtime is not None:
            try:
                self._realtime.close()
            except Exception:
                logger.exception("Failed to close realtime session during cleanup")
            self._realtime = None

        self._hide_osd()
        self._hide_indicator()

        if restore_caps_lock:
            self._restore_caps_lock_state()
        else:
            self.caps_state_before = None

    def _restore_caps_lock_state(self):
        vk_capital = 0x14
        try:
            caps_state_after = ctypes.windll.user32.GetKeyState(vk_capital) & 0x0001
        except Exception:
            logger.exception("Failed to read Caps Lock state")
            self.caps_state_before = None
            return

        if self.caps_state_before is not None and caps_state_after != self.caps_state_before:
            try:
                self._suppress_until = time.time() + 0.5
                ctypes.windll.user32.keybd_event(vk_capital, 0x3A, 0, 0)
                ctypes.windll.user32.keybd_event(vk_capital, 0x3A, 2, 0)
            except Exception:
                logger.exception("Failed to restore Caps Lock state")
        self.caps_state_before = None

    def _input_polished_text(self, full_text, log_prefix, before_first_chunk=None):
        if not full_text:
            log("[提示] 没有识别到文字")
            return

        log(f"{log_prefix} 原始文本: {full_text}")
        target_hwnd = get_foreground_window()
        typed_text_parts = []
        released_before_output = False
        injection_cancelled = False

        def release_before_output():
            nonlocal released_before_output
            if not released_before_output and before_first_chunk is not None:
                before_first_chunk()
                released_before_output = True

        def append_suffix_if_safe(final_text, reason):
            current_text = "".join(typed_text_parts)
            release_before_output()
            if not is_same_foreground_window(target_hwnd):
                log(f"{log_prefix} [警告] 输入焦点已切换，取消自动补全")
                return False
            if not final_text:
                if current_text:
                    log(f"{log_prefix} 最终文本: {current_text}")
                    log("[完成] 文字已填入")
                else:
                    log("[提示] 没有识别到文字")
                return True
            if not current_text:
                self._write_text(final_text)
                typed_text_parts.append(final_text)
                log(f"{log_prefix} [警告] {reason}，已直接补全全量文本")
                log(f"{log_prefix} 最终文本: {final_text}")
                log("[完成] 文字已填入")
                return True
            if final_text.startswith(current_text):
                suffix = final_text[len(current_text):]
                if suffix:
                    self._write_text(suffix)
                    typed_text_parts.append(suffix)
                    log(f"{log_prefix} [警告] {reason}，已补全剩余内容")
                log(f"{log_prefix} 最终文本: {final_text}")
                log("[完成] 文字已填入")
                return True
            log(
                f"{log_prefix} [警告] 无法安全补全："
                f"已输出内容与最终结果不是前缀关系"
            )
            return False

        def handle_stream_chunk(chunk):
            nonlocal injection_cancelled
            if not chunk or injection_cancelled:
                return
            if not is_same_foreground_window(target_hwnd):
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
            logger.exception("Polish stream failed")

        if stream_result is not None:
            if stream_result.first_chunk_latency_ms is not None:
                log(f"{log_prefix} 首个输出片段到达: {stream_result.first_chunk_latency_ms}ms")
            log(
                f"{log_prefix} 流式解析状态: "
                f"len={len(stream_result.text)}, "
                f"target_started={stream_result.target_started}, "
                f"target_completed={stream_result.target_completed}, "
                f"json_completed={stream_result.json_completed}, "
                f"resolved_len={len(stream_result.resolved_text or '')}"
            )

        if injection_cancelled:
            release_before_output()
            log(f"{log_prefix} [警告] 输入焦点已切换，已取消后续流式注入")
            return

        if stream_result is not None and stream_result.resolved_text is not None:
            append_suffix_if_safe(stream_result.resolved_text, "流式监测")
            if stream_result.is_complete:
                log(f"{log_prefix} 流式输出完成，耗时: {stream_result.elapsed_ms}ms")
            return

        fallback_reason = "流式请求失败" if stream_error else describe_stream_issue(stream_result)
        log(f"{log_prefix} [警告] 流式结果未通过校验，尝试补全: {fallback_reason}")
        if stream_error:
            log(f"{log_prefix} [警告] 流式请求异常: {stream_error}")

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
            log(f"{log_prefix} [警告] 非流式补全失败: {exc}")

        append_suffix_if_safe(replacement_text, "非流式补全")

    def _write_text(self, text):
        try:
            keyboard.write(text)
        except Exception as e:
            log(f"[警告] keyboard.write 失败，改用 SendInput: {e}")
            send_unicode_text(text)

    def _input_text(self, full_text):
        if full_text:
            log(f"\n识别结果: {full_text}")
            self._write_text(full_text)
            log("[完成] 文字已填入")
        else:
            log("[提示] 没有识别到文字")

    def stop_and_transcribe_with_toggle(self):
        vk_capital = 0x14
        hold_duration = time.time() - self._press_time if self._press_time else 0

        if hold_duration < 0.3:
            self.recording = False
            if self.stream is not None:
                self.stream.stop()
                self.stream.close()
                self.stream = None
            if self._realtime is not None:
                self._realtime.close()
                self._realtime = None
            self._hide_osd()
            self._hide_indicator()
            log(f"[提示] 短按 ({hold_duration:.2f}s)，视为 Caps Lock 切换")
            return

        self.stop_and_transcribe()

        caps_state_after = ctypes.windll.user32.GetKeyState(vk_capital) & 0x0001
        if self.caps_state_before is not None and caps_state_after != self.caps_state_before:
            try:
                self._suppress_until = time.time() + 0.5
                ctypes.windll.user32.keybd_event(vk_capital, 0x3A, 0, 0)
                ctypes.windll.user32.keybd_event(vk_capital, 0x3A, 2, 0)
            except Exception:
                logger.exception("Failed to restore Caps Lock state")


def select_mode():
    print("\n=============================================")
    print("请选择识别模式：")
    print("  1. 录音文件识别 - 非流式（松开后一次性返回结果）")
    print("  2. 录音文件识别 + 文本优化")
    print("  3. 实时语音识别（边说边识别）")
    print("  4. 实时语音识别 + 文本优化")
    print("=============================================")
    while True:
        choice = input("请输入选项 (1/2/3/4) [默认1]: ").strip()
        if choice == "" or choice == MODE_NON_STREAM:
            return MODE_NON_STREAM
        if choice == MODE_NON_STREAM_POLISH:
            return MODE_NON_STREAM_POLISH
        if choice == MODE_REALTIME:
            return MODE_REALTIME
        if choice == MODE_REALTIME_POLISH:
            return MODE_REALTIME_POLISH
        print("[提示] 无效选项，请重新输入。")


def main():
    log("正在初始化 Qwen ASR (DashScope) ...")

    config = AppConfig.from_env()
    if not config.resolved_asr_api_key():
        log("[错误] 请在 .env 文件中设置 ASR_API_KEY（兼容旧键名 API_KEY）")
        return

    mode = select_mode()
    mode_names = {
        MODE_NON_STREAM: "录音文件识别 - 非流式",
        MODE_NON_STREAM_POLISH: "录音文件识别 + 文本优化",
        MODE_REALTIME: "实时语音识别",
        MODE_REALTIME_POLISH: "实时语音识别 + 文本优化",
    }
    log(f"[OK] 已选择: {mode_names[mode]}")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    global osd_bubble
    if mode in {MODE_REALTIME, MODE_REALTIME_POLISH}:
        from .osd_widget import OsdBubble

        osd_bubble = OsdBubble()
        log("[OSD] PyQt6 气泡已就绪")

    recorder = AudioRecorder(mode=mode, config=config)
    try:
        keyboard.on_press_key("caps lock", lambda e: recorder.start_recording())
        keyboard.on_release_key("caps lock", lambda e: recorder.stop_and_transcribe_with_toggle())
        keyboard.on_press_key("f2", lambda e: recorder.start_recording())
        keyboard.on_release_key("f2", lambda e: recorder.stop_and_transcribe_with_toggle())
    except Exception:
        log("[错误] 注册全局热键失败，请尝试以管理员身份运行。")
        logger.exception("Hotkey register failed")
        return

    is_admin = False
    try:
        is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        logger.exception("Admin check failed")

    log(f"[状态] 管理员权限: {is_admin}")
    log("[状态] 触发键: Caps Lock（主） / F2（备用）")
    log(f"[状态] 运行日志: {LOG_PATH}")
    print("\n=============================================")
    print("使用方法：按住 [Caps Lock] 或 [F2] 说话，松开自动填入")
    print("（自动恢复 Caps Lock 状态，不影响剪贴板）")
    print("=============================================\n")

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal_timer = QTimer()
    signal_timer.start(200)
    signal_timer.timeout.connect(lambda: None)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

