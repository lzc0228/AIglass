const VIDEO_BRIGHTNESS = 1.24;
const VIDEO_CONTRAST = 1.08;
const VIDEO_SATURATE = 1.06;
const CHAT_MAX_MESSAGES = 80;
const RECONNECT_BASE_MS = 1200;
const RECONNECT_MAX_MS = 10000;

const dom = {
  canvas: document.getElementById("canvas"),
  partial: document.getElementById("partial"),
  finalList: document.getElementById("finalList"),
  camStatus: document.getElementById("camStatus"),
  asrStatus: document.getElementById("asrStatus"),
  fps: document.getElementById("fps"),
  imuStatus: document.getElementById("imu_ws_state"),
  imuHud: document.getElementById("imu_hud"),
  imuView: document.getElementById("imu_view"),
  btnReconnect: document.getElementById("btnReconnect"),
  btnClear: document.getElementById("btnClear"),
};

const ctx = dom.canvas ? dom.canvas.getContext("2d", { alpha: false }) : null;

const state = {
  wsViewer: null,
  wsUi: null,
  wsImu: null,
  reconnectTimers: { viewer: null, ui: null, imu: null },
  retryCount: { viewer: 0, ui: 0, imu: 0 },
  frameQueueLatest: null,
  frameDecodeBusy: false,
  frameCounter: 0,
  fpsTickTs: performance.now(),
  imuNeedleEl: null,
  imuAngleEl: null,
};

function wsUrl(path) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}${path}`;
}

function setBadge(el, text, level) {
  if (!el) return;
  el.textContent = text;
  el.classList.remove("ok", "err");
  if (level === "ok") el.classList.add("ok");
  if (level === "err") el.classList.add("err");
}

function fmtNum(v, digits = 2) {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(digits) : "--";
}

function clearReconnectTimer(kind) {
  if (state.reconnectTimers[kind]) {
    clearTimeout(state.reconnectTimers[kind]);
    state.reconnectTimers[kind] = null;
  }
}

function scheduleReconnect(kind) {
  if (state.reconnectTimers[kind]) return;
  const attempt = state.retryCount[kind] || 0;
  const delay = Math.min(
    RECONNECT_MAX_MS,
    Math.round(RECONNECT_BASE_MS * Math.pow(1.7, attempt))
  );
  state.retryCount[kind] = attempt + 1;
  state.reconnectTimers[kind] = setTimeout(() => {
    state.reconnectTimers[kind] = null;
    if (kind === "viewer") connectViewer();
    if (kind === "ui") connectUi();
    if (kind === "imu") connectImu();
  }, delay);
}

function resetRetry(kind) {
  state.retryCount[kind] = 0;
  clearReconnectTimer(kind);
}

function resizeCanvas() {
  if (!dom.canvas) return;
  const w = dom.canvas.clientWidth || 1280;
  const h = dom.canvas.clientHeight || 720;
  if (dom.canvas.width !== w || dom.canvas.height !== h) {
    dom.canvas.width = Math.max(1, w);
    dom.canvas.height = Math.max(1, h);
  }
}

function drawSource(source, sw, sh) {
  if (!ctx || !dom.canvas || !sw || !sh) return;
  const cw = dom.canvas.width;
  const ch = dom.canvas.height;
  const scale = Math.min(cw / sw, ch / sh);
  const dw = Math.max(1, Math.floor(sw * scale));
  const dh = Math.max(1, Math.floor(sh * scale));
  const dx = Math.floor((cw - dw) / 2);
  const dy = Math.floor((ch - dh) / 2);

  ctx.save();
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, cw, ch);
  ctx.filter = `brightness(${VIDEO_BRIGHTNESS}) contrast(${VIDEO_CONTRAST}) saturate(${VIDEO_SATURATE})`;
  ctx.drawImage(source, dx, dy, dw, dh);
  ctx.restore();
}

async function decodeAndDraw(buffer) {
  const blob = new Blob([buffer], { type: "image/jpeg" });
  if ("createImageBitmap" in window) {
    const bitmap = await createImageBitmap(blob);
    drawSource(bitmap, bitmap.width, bitmap.height);
    if (typeof bitmap.close === "function") bitmap.close();
    return;
  }

  await new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(blob);
    img.onload = () => {
      drawSource(img, img.naturalWidth, img.naturalHeight);
      URL.revokeObjectURL(url);
      resolve();
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("image decode failed"));
    };
    img.src = url;
  });
}

function enqueueFrame(buffer) {
  state.frameQueueLatest = buffer;
  if (!state.frameDecodeBusy) {
    void drainFrameQueue();
  }
}

async function drainFrameQueue() {
  if (state.frameDecodeBusy) return;
  state.frameDecodeBusy = true;
  while (state.frameQueueLatest) {
    const next = state.frameQueueLatest;
    state.frameQueueLatest = null;
    try {
      await decodeAndDraw(next);
      state.frameCounter += 1;
    } catch (err) {
      console.warn("[viewer] frame decode error:", err);
    }
  }
  state.frameDecodeBusy = false;
}

function updateFps() {
  const now = performance.now();
  const dt = Math.max(0.001, (now - state.fpsTickTs) / 1000);
  const fps = state.frameCounter / dt;
  state.frameCounter = 0;
  state.fpsTickTs = now;
  if (dom.fps) {
    dom.fps.textContent = `FPS: ${fps.toFixed(1)}`;
  }
}

function parseFinalMessage(rawText) {
  const text = (rawText || "").trim();
  if (!text) return null;
  if (text.startsWith("[用户]")) {
    return { fromMe: true, text: text.slice(4).trim() };
  }
  if (text.startsWith("[")) {
    return { fromMe: false, text: text.replace(/^\[[^\]]+\]\s*/, "").trim() };
  }
  return { fromMe: true, text };
}

function appendFinal(rawText) {
  if (!dom.finalList) return;
  const parsed = parseFinalMessage(rawText);
  if (!parsed || !parsed.text) return;

  const li = document.createElement("li");
  li.className = `bubble ${parsed.fromMe ? "from-me" : "from-bot"}`;
  li.textContent = parsed.text;
  dom.finalList.appendChild(li);

  while (dom.finalList.children.length > CHAT_MAX_MESSAGES) {
    dom.finalList.removeChild(dom.finalList.firstElementChild);
  }
  dom.finalList.scrollTop = dom.finalList.scrollHeight;
}

function clearFinals() {
  if (dom.finalList) dom.finalList.innerHTML = "";
}

function handleUiMessage(raw) {
  if (typeof raw !== "string") return;

  if (raw.startsWith("INIT:")) {
    try {
      const payload = JSON.parse(raw.slice(5));
      if (dom.partial) {
        const p = (payload.partial || "").trim();
        dom.partial.textContent = p || "（等待音频…）";
      }
      clearFinals();
      const finals = Array.isArray(payload.finals) ? payload.finals : [];
      finals.forEach((line) => appendFinal(line));
    } catch (err) {
      console.warn("[ui] INIT parse failed:", err);
    }
    return;
  }

  if (raw.startsWith("PARTIAL:")) {
    if (dom.partial) {
      const text = raw.slice(8).trim();
      dom.partial.textContent = text || "（等待音频…）";
    }
    return;
  }

  if (raw.startsWith("FINAL:")) {
    const text = raw.slice(6).trim();
    appendFinal(text);
    if (dom.partial) dom.partial.textContent = "";
  }
}

function initImuWidgets() {
  if (!dom.imuView) return;
  dom.imuView.innerHTML = `
    <div style="height:100%;display:grid;place-items:center;color:#d9e7ff;">
      <div style="display:grid;gap:10px;justify-items:center;">
        <div style="position:relative;width:170px;height:170px;border-radius:50%;border:2px solid rgba(92,156,255,.7);background:radial-gradient(circle at center, rgba(24,45,92,.78), rgba(9,17,33,.88));">
          <div style="position:absolute;left:50%;top:50%;width:6px;height:6px;border-radius:50%;background:#9cc3ff;transform:translate(-50%,-50%);"></div>
          <div id="imu_needle" style="position:absolute;left:50%;top:50%;width:3px;height:68px;background:linear-gradient(to top,#52d6ff,#90f4ff);border-radius:2px;transform:translate(-50%,-100%) rotate(0deg);transform-origin:50% 100%;box-shadow:0 0 10px rgba(82,214,255,.8);"></div>
          <div style="position:absolute;left:50%;top:10px;transform:translateX(-50%);font-size:12px;color:#9cc3ff;">N</div>
        </div>
        <div id="imu_angle_text" style="font-size:13px;color:#dbe8ff;">Yaw -- | Pitch -- | Roll --</div>
      </div>
    </div>
  `;
  state.imuNeedleEl = document.getElementById("imu_needle");
  state.imuAngleEl = document.getElementById("imu_angle_text");

  if (dom.imuHud) {
    dom.imuHud.innerHTML = `<div style="font-size:13px;color:#9fb0c3;">等待 IMU 数据...</div>`;
  }
}

function updateImuUi(payload) {
  const angles = payload && payload.angles ? payload.angles : {};
  const accel = payload && payload.accel ? payload.accel : {};
  const gyro = payload && payload.gyro ? payload.gyro : {};
  const yaw = Number(angles.yaw);
  const pitch = Number(angles.pitch);
  const roll = Number(angles.roll);

  if (state.imuNeedleEl && Number.isFinite(yaw)) {
    state.imuNeedleEl.style.transform = `translate(-50%,-100%) rotate(${yaw}deg)`;
  }
  if (state.imuAngleEl) {
    state.imuAngleEl.textContent = `Yaw ${fmtNum(yaw, 1)}° | Pitch ${fmtNum(pitch, 1)}° | Roll ${fmtNum(roll, 1)}°`;
  }
  if (dom.imuHud) {
    dom.imuHud.innerHTML = `
      <div style="display:grid;gap:6px;font-size:13px;color:#d9e6fb;">
        <div style="font-weight:700;color:#ffd769;">IMU 实时数据</div>
        <div>时间戳: <code>${fmtNum(payload.ts, 3)}</code></div>
        <div>Roll / Pitch / Yaw: <code>${fmtNum(roll, 2)} / ${fmtNum(pitch, 2)} / ${fmtNum(yaw, 2)}</code></div>
        <div>Accel (x,y,z): <code>${fmtNum(accel.x, 3)}, ${fmtNum(accel.y, 3)}, ${fmtNum(accel.z, 3)}</code></div>
        <div>Gyro (x,y,z): <code>${fmtNum(gyro.x, 3)}, ${fmtNum(gyro.y, 3)}, ${fmtNum(gyro.z, 3)}</code></div>
      </div>
    `;
  }
}

function connectViewer() {
  setBadge(dom.camStatus, "Camera: connecting…", null);
  const ws = new WebSocket(wsUrl("/ws/viewer"));
  ws.binaryType = "arraybuffer";
  state.wsViewer = ws;

  ws.onopen = () => {
    resetRetry("viewer");
    setBadge(dom.camStatus, "Camera: connected", "ok");
  };

  ws.onmessage = (ev) => {
    if (ev.data instanceof ArrayBuffer) {
      enqueueFrame(ev.data);
      setBadge(dom.camStatus, "Camera: streaming", "ok");
      return;
    }
    if (ev.data instanceof Blob) {
      void ev.data.arrayBuffer().then((buf) => {
        enqueueFrame(buf);
        setBadge(dom.camStatus, "Camera: streaming", "ok");
      });
    }
  };

  ws.onerror = () => {
    setBadge(dom.camStatus, "Camera: error", "err");
  };

  ws.onclose = () => {
    if (state.wsViewer === ws) state.wsViewer = null;
    setBadge(dom.camStatus, "Camera: disconnected", "err");
    scheduleReconnect("viewer");
  };
}

function connectUi() {
  setBadge(dom.asrStatus, "ASR: connecting…", null);
  const ws = new WebSocket(wsUrl("/ws_ui"));
  state.wsUi = ws;

  ws.onopen = () => {
    resetRetry("ui");
    setBadge(dom.asrStatus, "ASR: connected", "ok");
  };

  ws.onmessage = (ev) => {
    if (typeof ev.data === "string") {
      handleUiMessage(ev.data);
    }
  };

  ws.onerror = () => {
    setBadge(dom.asrStatus, "ASR: error", "err");
  };

  ws.onclose = () => {
    if (state.wsUi === ws) state.wsUi = null;
    setBadge(dom.asrStatus, "ASR: disconnected", "err");
    scheduleReconnect("ui");
  };
}

function connectImu() {
  setBadge(dom.imuStatus, "imu: connecting…", null);
  const ws = new WebSocket(wsUrl("/ws"));
  state.wsImu = ws;

  ws.onopen = () => {
    resetRetry("imu");
    setBadge(dom.imuStatus, "imu: connected", "ok");
  };

  ws.onmessage = (ev) => {
    if (typeof ev.data !== "string") return;
    try {
      const payload = JSON.parse(ev.data);
      updateImuUi(payload);
    } catch (err) {
      if (dom.imuHud) {
        dom.imuHud.textContent = `IMU 原始数据: ${String(ev.data).slice(0, 220)}`;
      }
    }
  };

  ws.onerror = () => {
    setBadge(dom.imuStatus, "imu: error", "err");
  };

  ws.onclose = () => {
    if (state.wsImu === ws) state.wsImu = null;
    setBadge(dom.imuStatus, "imu: disconnected", "err");
    scheduleReconnect("imu");
  };
}

function closeSocket(ws) {
  if (!ws) return;
  ws.onopen = null;
  ws.onmessage = null;
  ws.onerror = null;
  ws.onclose = null;
  try {
    ws.close(1000, "manual reconnect");
  } catch (_) {
    // ignore
  }
}

function reconnectAll() {
  clearReconnectTimer("viewer");
  clearReconnectTimer("ui");
  clearReconnectTimer("imu");

  closeSocket(state.wsViewer);
  closeSocket(state.wsUi);
  closeSocket(state.wsImu);

  state.wsViewer = null;
  state.wsUi = null;
  state.wsImu = null;

  connectViewer();
  connectUi();
  connectImu();
}

function bindEvents() {
  if (dom.btnReconnect) {
    dom.btnReconnect.addEventListener("click", () => reconnectAll());
  }
  if (dom.btnClear) {
    dom.btnClear.addEventListener("click", () => clearFinals());
  }
  window.addEventListener("resize", resizeCanvas);
  window.addEventListener("beforeunload", () => {
    closeSocket(state.wsViewer);
    closeSocket(state.wsUi);
    closeSocket(state.wsImu);
  });
}

function bootstrap() {
  initImuWidgets();
  bindEvents();
  resizeCanvas();
  reconnectAll();
  setInterval(updateFps, 1000);
}

bootstrap();
