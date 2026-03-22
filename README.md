# TEASR

![teasr-en](https://github.com/DDDeeeee/Teasr/blob/main/pics/teasr-en.png)

Microphone-free speech recognition and text polishing for vibe coding on Windows.
TEASR is a desktop voice input app that turns speech into text with as little friction as possible.

面向 Windows 的无麦克风语音识别与文本润色工具，适合 vibe coding。
TEASR 是一个桌面语音输入应用，目标是把说话变成文字这件事做得尽量直接、顺手。包含中英双语。

## Features

![speaking](https://github.com/DDDeeeee/Teasr/blob/main/pics/Speaking.png)

- Hotkey-driven voice input.
- Realtime and non-realtime recognition modes.
- Optional text polishing after recognition.
- Phone-as-microphone support over local network.
- Windows-native desktop workflow with tray support.

- 通过热键直接开始语音输入。
- 同时支持实时识别和非实时识别。
- 识别完成后可选文本润色。
- 支持在局域网内用手机充当麦克风。
- 面向 Windows 桌面工作流，支持托盘常驻。

## Quick Start

1. Download the Windows release ZIP and extract the full folder.

   下载 Windows 发布版 ZIP，并完整解压整个目录。
2. Run `TEASR.exe`.

   运行 `TEASR.exe`。
3. Open Settings and fill in your ASR and text polish configuration.

   打开设置，填写 ASR 和文本润色配置。
4. Choose `Local Microphone` or `Remote Phone Microphone`.

   选择“本地麦克风”或“手机远程麦克风”。
5. Pick a recognition mode and start speaking.

   选择识别模式后开始说话。

## Remote Phone Input

![PHONE-MICROPHONE](https://github.com/DDDeeeee/Teasr/blob/main/pics/PHONE-MICROPHONE.png)

If your computer does not have a microphone, you can open the phone page and use your phone as the audio input source.
The desktop app shows the access URL and QR code automatically.

如果电脑没有麦克风，可以打开手机页面，让手机充当音频输入来源。
桌面端会自动显示访问 URL 和二维码。

## Local Development

Run the GUI app:
启动 GUI：

```powershell
.\venv\Scripts\activate
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m asr_app
```

Run the legacy CLI path:
启动旧版 CLI 路径：

```powershell
python -m asr_app --cli
```

Or use:
或者直接运行：

```powershell
.\start_asr.bat
```

## Configuration

The app loads defaults from `.env` and persists GUI overrides with `QSettings`.
应用会先从 `.env` 读取默认值，再通过 `QSettings` 持久化 GUI 配置。

Useful keys include `ASR_API_KEY`, `ASR_BASE_URL`, `TEXT_POLISH_API_KEY`, `TEXT_POLISH_BASE_URL`, `ASR_NON_STREAM_MODEL`, `ASR_REALTIME_MODEL`, `ASR_TEXT_POLISH_MODEL`, `TEXT_POLISH_OUTPUT_KEY`, and `ASR_REMOTE_PHONE_*`.
常用配置项包括 `ASR_API_KEY`、`ASR_BASE_URL`、`TEXT_POLISH_API_KEY`、`TEXT_POLISH_BASE_URL`、`ASR_NON_STREAM_MODEL`、`ASR_REALTIME_MODEL`、`ASR_TEXT_POLISH_MODEL`、`TEXT_POLISH_OUTPUT_KEY` 以及 `ASR_REMOTE_PHONE_*`。

See `.env.example` for a complete template.
完整模板请查看 `.env.example`。

## Project Structure

`src/asr_app/`: active application package.
`src/asr_app/`：当前生效的应用代码。

`src/asr_app/ui/qml/`: Qt Quick frontend.
`src/asr_app/ui/qml/`：Qt Quick 前端。

`src/asr_app/app/controller.py`: GUI controller.
`src/asr_app/app/controller.py`：GUI 控制器。

`src/asr_app/services/audio_recorder.py`: recording and recognition pipeline.
`src/asr_app/services/audio_recorder.py`：录音与识别流程。

`src/asr_app/services/remote_phone_runtime.py`: phone microphone runtime.
`src/asr_app/services/remote_phone_runtime.py`：手机远程麦克风运行时。

`scripts/`: launcher and build helpers.
`scripts/`：启动与构建辅助脚本。

## Notes

TEASR is currently Windows-focused.
TEASR 当前主要面向 Windows。

Unsigned builds may trigger SmartScreen or antivirus warnings.
未签名构建可能触发 SmartScreen 或安全软件提示。

Remote phone mode may trigger firewall, HTTPS trust, or microphone permission prompts.
手机远程模式可能触发防火墙、HTTPS 信任或麦克风权限提示。
