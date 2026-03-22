const runtimeConfig = {
  controlPort: 8765,
  audioPort: 8766,
  language: "zh",
  translations: {},
  ...(window.ASR_REMOTE_PHONE_CONFIG || {}),
};

const pageTitleEl = document.getElementById("page-title");
const headingEl = document.getElementById("heading");
const subtitleEl = document.getElementById("subtitle");
const connectionLabelEl = document.getElementById("connection-label");
const permissionLabelEl = document.getElementById("permission-label");
const captureLabelEl = document.getElementById("capture-label");
const connectionEl = document.getElementById("connection-state");
const permissionEl = document.getElementById("permission-state");
const captureEl = document.getElementById("capture-state");
const authorizeBtn = document.getElementById("authorize-btn");
const disconnectBtn = document.getElementById("disconnect-btn");
const logEl = document.getElementById("log");

const state = {
  clientId: loadClientId(),
  sessionId: null,
  controlSocket: null,
  audioSocket: null,
  mediaStream: null,
  audioContext: null,
  sourceNode: null,
  processingNode: null,
  gainNode: null,
  permission: "required",
  connection: "connecting",
  capture: "idle",
  currentCaptureId: null,
  frameSeq: 0,
  audioFramesSent: 0,
  captureAckSent: false,
  disconnecting: false,
  reconnectTimer: null,
  manualDisconnect: false,
  processorKind: "uninitialized",
};

const textEncoder = new TextEncoder();

function accessToken() {
  const value = new URLSearchParams(window.location.search).get("token");
  return (value || "").trim();
}

function buildAuthorizedPath(path) {
  const token = accessToken();
  if (!token) {
    return path;
  }
  const url = new URL(path, window.location.origin);
  url.searchParams.set("token", token);
  return `${url.pathname}${url.search}`;
}

function markAccessDenied(message) {
  clearReconnectTimer();
  state.manualDisconnect = true;
  state.connection = "error";
  updateView();
  log(message);
}

function tr(name, params = {}) {
  const template = (runtimeConfig.translations || {})[name] || name;
  return template.replace(/\{(\w+)\}/g, (_, key) => String(params[key] ?? `{${key}}`));
}

function applyRuntimeConfig(nextConfig = {}) {
  Object.assign(runtimeConfig, nextConfig || {});
  document.documentElement.lang = runtimeConfig.language === "en" ? "en" : "zh-CN";
  document.title = tr("pageTitle");
  pageTitleEl.textContent = document.title;
  headingEl.textContent = tr("heading");
  subtitleEl.textContent = tr("subtitle");
  connectionLabelEl.textContent = tr("connectionLabel");
  permissionLabelEl.textContent = tr("permissionLabel");
  captureLabelEl.textContent = tr("captureLabel");
  authorizeBtn.textContent = tr("authorize");
  disconnectBtn.textContent = tr("disconnect");
  updateView();
}

async function refreshRuntimeConfig() {
  try {
    const response = await window.fetch(buildAuthorizedPath("/runtime-config"), { cache: "no-store" });
    if (response.status === 401) {
      markAccessDenied("Access token is invalid or expired.");
      return false;
    }
    if (!response.ok) {
      return false;
    }
    applyRuntimeConfig(await response.json());
    return true;
  } catch {
    return false;
  }
}

function loadClientId() {
  const storageKey = "asr-remote-phone-client-id";
  const existing = window.localStorage.getItem(storageKey);
  if (existing) {
    return existing;
  }
  const generated = `client_${Math.random().toString(36).slice(2, 10)}`;
  window.localStorage.setItem(storageKey, generated);
  return generated;
}

function connectionLabel() {
  return tr(`connection_${state.connection}`);
}

function permissionLabel() {
  return tr(`permission_${state.permission}`);
}

function captureLabel() {
  return tr(`capture_${state.capture}`);
}

function updateView() {
  connectionEl.textContent = connectionLabel();
  permissionEl.textContent = permissionLabel();
  captureEl.textContent = captureLabel();
  connectionEl.className = `value ${toneForConnection()}`;
  permissionEl.className = `value ${toneForPermission()}`;
  captureEl.className = `value ${toneForCapture()}`;
}

function toneForConnection() {
  if (state.connection === "connected") return "ok";
  if (state.connection === "error" || state.connection === "disconnected") return "bad";
  return "warn";
}

function toneForPermission() {
  if (state.permission === "granted") return "ok";
  if (state.permission === "denied") return "bad";
  return "warn";
}

function toneForCapture() {
  if (state.capture === "capturing" || state.capture === "ready") return "ok";
  if (state.capture === "error") return "bad";
  return "warn";
}

function log(message) {
  const timestamp = new Date().toLocaleTimeString();
  logEl.textContent = `[${timestamp}] ${message}\n${logEl.textContent}`.slice(0, 3200);
}

function controlUrl() {
  const token = accessToken();
  return `wss://${window.location.hostname}:${runtimeConfig.controlPort}?client_id=${encodeURIComponent(state.clientId)}&token=${encodeURIComponent(token)}`;
}

function audioUrl(sessionId) {
  const token = accessToken();
  return `wss://${window.location.hostname}:${runtimeConfig.audioPort}?session_id=${encodeURIComponent(sessionId)}&token=${encodeURIComponent(token)}`;
}

function clearReconnectTimer() {
  if (state.reconnectTimer !== null) {
    window.clearTimeout(state.reconnectTimer);
    state.reconnectTimer = null;
  }
}

function scheduleReconnect(reason) {
  if (state.manualDisconnect || state.reconnectTimer !== null) {
    return;
  }
  state.connection = "reconnecting";
  updateView();
  log(tr("log_reconnect_planned", { reason }));
  state.reconnectTimer = window.setTimeout(() => {
    state.reconnectTimer = null;
    void connectControl();
  }, 1500);
}

function sendReadyIfPossible() {
  if (state.permission !== "granted") {
    return;
  }
  sendControl("ready", {
    device_name: navigator.userAgent,
    browser: navigator.userAgent,
    platform: navigator.platform || "unknown",
  });
  if (state.capture !== "capturing") {
    state.capture = "ready";
    updateView();
  }
}

function sendControl(type, payload = {}) {
  if (!state.controlSocket || state.controlSocket.readyState !== WebSocket.OPEN || !state.sessionId) {
    return;
  }
  state.controlSocket.send(JSON.stringify({ type, session_id: state.sessionId, ts: Date.now(), payload }));
}

function stopMediaTracks() {
  if (!state.mediaStream) {
    return;
  }
  for (const track of state.mediaStream.getTracks()) {
    track.stop();
  }
  state.mediaStream = null;
}

async function closeAudioPipeline() {
  if (state.processingNode) {
    if (state.processingNode.port) state.processingNode.port.onmessage = null;
    if (state.processingNode.onaudioprocess) state.processingNode.onaudioprocess = null;
    try { state.processingNode.disconnect(); } catch {}
    state.processingNode = null;
  }
  if (state.sourceNode) {
    try { state.sourceNode.disconnect(); } catch {}
    state.sourceNode = null;
  }
  if (state.gainNode) {
    try { state.gainNode.disconnect(); } catch {}
    state.gainNode = null;
  }
  if (state.audioContext) {
    try { await state.audioContext.close(); } catch {}
    state.audioContext = null;
  }
  state.processorKind = "uninitialized";
}

async function disconnectAll({ releaseMedia = true, reconnect = false } = {}) {
  if (state.disconnecting) {
    return;
  }
  state.disconnecting = true;
  try {
    const audioSocket = state.audioSocket;
    const controlSocket = state.controlSocket;
    state.audioSocket = null;
    state.controlSocket = null;
    state.currentCaptureId = null;
    state.frameSeq = 0;
    state.audioFramesSent = 0;
    state.captureAckSent = false;
    state.connection = reconnect ? "reconnecting" : "disconnected";
    state.capture = state.permission === "granted" && !releaseMedia ? "ready" : "idle";
    if (audioSocket && audioSocket.readyState < WebSocket.CLOSING) audioSocket.close();
    if (controlSocket && controlSocket.readyState < WebSocket.CLOSING) controlSocket.close();
    if (releaseMedia) {
      stopMediaTracks();
      await closeAudioPipeline();
      state.permission = "required";
      state.sessionId = null;
      clearReconnectTimer();
    }
    updateView();
  } finally {
    state.disconnecting = false;
  }
  if (reconnect) {
    scheduleReconnect("control channel closed");
  }
}

async function connectControl() {
  if (state.controlSocket && state.controlSocket.readyState <= WebSocket.OPEN) {
    return;
  }
  if (!accessToken()) {
    markAccessDenied("Access token is missing from the URL.");
    return;
  }
  await refreshRuntimeConfig();
  if (state.manualDisconnect && state.connection === "error") {
    return;
  }
  clearReconnectTimer();
  state.manualDisconnect = false;
  state.connection = "connecting";
  updateView();
  state.controlSocket = new WebSocket(controlUrl());
  state.controlSocket.addEventListener("open", () => {
    state.connection = "connected";
    updateView();
    log(tr("log_connected_client", { client_id: state.clientId }));
  });

  state.controlSocket.addEventListener("message", async (event) => {
    const message = JSON.parse(event.data);
    const { type, session_id: sessionId, payload = {} } = message;
    if (sessionId) state.sessionId = sessionId;

    if (type === "hello") {
      const suffix = payload.resumed ? tr("log_session_resumed_suffix") : "";
      log(tr("log_session_ready", { session_id: state.sessionId, suffix }));
      sendReadyIfPossible();
    } else if (type === "start_capture") {
      await startCapture(payload.capture_id);
    } else if (type === "stop_capture") {
      await stopCapture(payload.capture_id);
    } else if (type === "disconnect") {
      log(tr("log_desktop_disconnected", { reason: payload.reason || "unknown" }));
      await disconnectAll({ releaseMedia: false, reconnect: !state.manualDisconnect });
    } else if (type === "ping") {
      sendControl("pong", { nonce: payload.nonce });
    } else if (type === "error") {
      log(tr("log_server_error", { code: payload.code || "unknown" }));
    }
  });

  state.controlSocket.addEventListener("close", (event) => {
    if (event.code === 1008) {
      void (async () => {
        await disconnectAll({ releaseMedia: false, reconnect: false });
        markAccessDenied("Access token is invalid or expired.");
      })();
      return;
    }
    if (state.connection !== "disconnected") {
      log(tr("log_control_closed", { code: event.code, reason: event.reason || "-" }));
    }
    void disconnectAll({ releaseMedia: false, reconnect: !state.manualDisconnect });
  });

  state.controlSocket.addEventListener("error", () => {
    state.connection = "error";
    updateView();
    log(tr("log_control_error"));
  });
}

async function authorize() {
  try {
    if (!state.mediaStream) {
      state.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false },
      });
      await ensureAudioPipeline();
    }
    if (state.audioContext && state.audioContext.state === "suspended") {
      await state.audioContext.resume();
    }
    state.permission = "granted";
    state.capture = "ready";
    updateView();
    sendReadyIfPossible();
    log(tr("log_authorized", { processor: state.processorKind }));
  } catch (error) {
    state.permission = "denied";
    state.capture = "error";
    updateView();
    sendControl("error", { code: "mic_denied", message: String(error) });
    log(tr("log_authorize_failed", { error: String(error) }));
  }
}

async function ensureAudioPipeline() {
  if (state.audioContext) return;
  const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextCtor) {
    throw new Error(tr("log_audio_context_unsupported"));
  }
  state.audioContext = new AudioContextCtor();
  state.sourceNode = state.audioContext.createMediaStreamSource(state.mediaStream);
  state.gainNode = state.audioContext.createGain();
  state.gainNode.gain.value = 0;

  try {
    if (state.audioContext.audioWorklet && typeof state.audioContext.audioWorklet.addModule === "function") {
      await state.audioContext.audioWorklet.addModule(buildAuthorizedPath("/audio-worklet.js"));
      const workletNode = new AudioWorkletNode(state.audioContext, "pcm-resampler");
      workletNode.port.onmessage = (event) => handleOutgoingAudioFrame(event.data);
      state.sourceNode.connect(workletNode);
      workletNode.connect(state.gainNode);
      state.processingNode = workletNode;
      state.processorKind = "audio_worklet";
    } else {
      setupScriptProcessorFallback();
    }
  } catch (error) {
    log(tr("log_audio_worklet_fallback", { error: String(error) }));
    setupScriptProcessorFallback();
  }

  state.gainNode.connect(state.audioContext.destination);
}

function setupScriptProcessorFallback() {
  const processor = state.audioContext.createScriptProcessor(1024, 1, 1);
  const accumulator = createPcmAccumulator(state.audioContext.sampleRate);
  processor.onaudioprocess = (event) => accumulator.append(event.inputBuffer, handleOutgoingAudioFrame);
  state.sourceNode.connect(processor);
  processor.connect(state.gainNode);
  state.processingNode = processor;
  state.processorKind = "script_processor";
}

function createPcmAccumulator(sourceRate) {
  const targetRate = 16000;
  const frameSize = 640;
  const ratio = sourceRate / targetRate;
  let sourceBuffer = [];
  let readIndex = 0;

  function canEmitFrame() {
    const required = readIndex + (frameSize - 1) * ratio + 1;
    return sourceBuffer.length > required;
  }

  return {
    append(inputBuffer, emitFrame) {
      const channelCount = inputBuffer.numberOfChannels;
      const sampleCount = inputBuffer.length;
      for (let i = 0; i < sampleCount; i += 1) {
        let mono = 0;
        for (let channel = 0; channel < channelCount; channel += 1) {
          mono += inputBuffer.getChannelData(channel)[i] || 0;
        }
        sourceBuffer.push(mono / channelCount);
      }

      while (canEmitFrame()) {
        const frame = new Int16Array(frameSize);
        for (let i = 0; i < frameSize; i += 1) {
          const position = readIndex + i * ratio;
          const leftIndex = Math.floor(position);
          const rightIndex = Math.min(leftIndex + 1, sourceBuffer.length - 1);
          const fraction = position - leftIndex;
          const sample = sourceBuffer[leftIndex] * (1 - fraction) + sourceBuffer[rightIndex] * fraction;
          const clamped = Math.max(-1, Math.min(1, sample));
          frame[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
        }
        readIndex += frameSize * ratio;
        const consumed = Math.floor(readIndex);
        if (consumed > 0) {
          sourceBuffer.splice(0, consumed);
          readIndex -= consumed;
        }
        emitFrame(frame.buffer);
      }
    },
  };
}

function handleOutgoingAudioFrame(pcmArrayBuffer) {
  if (state.capture !== "capturing" || !state.audioSocket || state.audioSocket.readyState !== WebSocket.OPEN || !state.currentCaptureId) {
    return;
  }
  try {
    const packet = buildAudioPacket(state.currentCaptureId, state.frameSeq++, pcmArrayBuffer);
    state.audioSocket.send(packet);
    state.audioFramesSent += 1;
    if (!state.captureAckSent) {
      state.captureAckSent = true;
      sendControl("capturing", { capture_id: state.currentCaptureId });
    }
  } catch (error) {
    state.capture = "error";
    updateView();
    sendControl("error", { code: "audio_send_failed", message: String(error) });
    log(tr("log_audio_send_failed", { error: String(error) }));
  }
}

async function ensureAudioSocket() {
  if (state.audioSocket && state.audioSocket.readyState === WebSocket.OPEN) return;
  state.audioSocket = new WebSocket(audioUrl(state.sessionId));
  state.audioSocket.binaryType = "arraybuffer";
  await new Promise((resolve, reject) => {
    let settled = false;
    const socket = state.audioSocket;
    const succeed = () => { if (!settled) { settled = true; resolve(); } };
    const fail = (message) => { if (!settled) { settled = true; reject(new Error(message)); } };
    socket.addEventListener("open", succeed, { once: true });
    socket.addEventListener("error", () => fail("audio websocket error"), { once: true });
    socket.addEventListener("close", (event) => fail(`audio websocket closed before open (${event.code})`), { once: true });
  });
  state.audioSocket.addEventListener("close", (event) => {
    log(tr("log_audio_closed", { code: event.code, reason: event.reason || "-" }));
  }, { once: true });
}

async function startCapture(captureId) {
  if (state.permission !== "granted") {
    sendControl("error", { code: "capture_start_failed", message: "permission not granted" });
    return;
  }
  try {
    await ensureAudioSocket();
    if (state.audioContext.state === "suspended") await state.audioContext.resume();
  } catch (error) {
    state.capture = "error";
    updateView();
    sendControl("error", { code: "capture_start_failed", message: String(error) });
    log(tr("log_capture_start_failed", { error: String(error) }));
    return;
  }
  state.currentCaptureId = captureId;
  state.frameSeq = 0;
  state.audioFramesSent = 0;
  state.captureAckSent = false;
  state.capture = "capturing";
  updateView();
  log(tr("log_capture_started", { capture_id: captureId }));
}

async function stopCapture(captureId) {
  if (state.capture !== "capturing") return;
  const stoppingCaptureId = captureId || state.currentCaptureId;
  state.currentCaptureId = null;
  state.frameSeq = 0;
  state.audioFramesSent = 0;
  state.captureAckSent = false;
  state.capture = "ready";
  updateView();
  sendControl("stopped", { capture_id: stoppingCaptureId });
  if (state.audioSocket && state.audioSocket.readyState < WebSocket.CLOSING) state.audioSocket.close();
  state.audioSocket = null;
  log(tr("log_capture_stopped", { capture_id: stoppingCaptureId }));
}

function buildAudioPacket(captureId, frameSeq, pcmArrayBuffer) {
  const captureBytes = textEncoder.encode(captureId);
  const pcmLength = pcmArrayBuffer.byteLength;
  const headerLength = 25 + captureBytes.length;
  const packet = new ArrayBuffer(headerLength + pcmLength);
  const view = new DataView(packet);
  const bytes = new Uint8Array(packet);
  bytes.set([82, 77, 73, 67], 0);
  view.setUint8(4, 1);
  view.setUint8(5, 0);
  view.setUint16(6, headerLength);
  view.setUint32(8, pcmLength);
  view.setUint8(12, captureBytes.length);
  view.setUint32(13, frameSeq);
  writeUint64(view, 17, Date.now());
  bytes.set(captureBytes, 25);
  bytes.set(new Uint8Array(pcmArrayBuffer), headerLength);
  return packet;
}

function writeUint64(view, offset, value) {
  const high = Math.floor(value / 2 ** 32);
  const low = value >>> 0;
  view.setUint32(offset, high);
  view.setUint32(offset + 4, low);
}

authorizeBtn.addEventListener("click", async () => {
  state.manualDisconnect = false;
  if (state.connection !== "connected") {
    log(tr("log_desktop_not_ready"));
    await connectControl();
    return;
  }
  await authorize();
});

disconnectBtn.addEventListener("click", () => {
  state.manualDisconnect = true;
  void disconnectAll({ releaseMedia: true, reconnect: false });
});

applyRuntimeConfig(runtimeConfig);
void refreshRuntimeConfig();
void connectControl();
