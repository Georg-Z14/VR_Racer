let authPassword = null;
let vrMode = false;
let overlayTimeout;
let currentStream = null;

// -------------------------
// 🔑 Login mit Feedback
// -------------------------
async function login() {
  const pw = document.getElementById("password").value;
  const card = document.getElementById("login-card");
  const status = document.getElementById("login-status");

  card.classList.remove("success", "error");
  status.textContent = "";

  try {
    const res = await fetch("/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: pw })
    });

    if (res.status === 200) {
      authPassword = pw;
      status.textContent = "✅ Login erfolgreich!";
      card.classList.add("success");
      setTimeout(() => {
        card.style.display = "none";
        document.getElementById("stream-card").style.display = "block";
        start();
      }, 600);
    } else {
      status.textContent = "❌ Falsches Passwort!";
      card.classList.add("error");
    }
  } catch {
    status.textContent = "⚠️ Verbindung fehlgeschlagen!";
    card.classList.add("error");
  }
}

// -------------------------
const video = document.getElementById("video");
const statusTxt = document.getElementById("status");
const hud = document.querySelector(".hud");
let pc;

// -------------------------
// 📡 Verbindung starten
// -------------------------
async function start() {
  statusTxt.textContent = "🔄 Verbinde...";
  pc = new RTCPeerConnection({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] });
  pc.addTransceiver("video", { direction: "recvonly" });

  pc.ontrack = (event) => {
    currentStream = event.streams[0];
    video.srcObject = currentStream;
    video.classList.add("neon-active");
    monitorFPS(video);
    createOverlay();
  };

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  const res = await fetch("/offer", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": authPassword },
    body: JSON.stringify(pc.localDescription)
  });

  if (!res.ok) {
    statusTxt.textContent = "❌ Zugriff verweigert!";
    return;
  }

  const answer = await res.json();
  await pc.setRemoteDescription(answer);
  statusTxt.textContent = "✅ Verbunden!";
  monitorPing(pc);
}

// -------------------------
// 🎛 Control-Hub mit Auto-Hide
// -------------------------
function createOverlay() {
  if (document.querySelector(".control-overlay")) return;
  const overlay = document.createElement("div");
  overlay.className = "control-overlay";
  overlay.innerHTML = `
    <button class="overlay-btn" title="Neu verbinden" onclick="restartStream()">🔄</button>
    <button class="overlay-btn" title="Vollbild" onclick="toggleFullscreen()">🖥️</button>
    <button class="overlay-btn" title="Ansicht wechseln" onclick="toggleView()">👓</button>
  `;
  document.querySelector(".status-bar").appendChild(overlay);
  setupOverlayHide(overlay);
}

function setupOverlayHide(overlay) {
  const show = () => {
    overlay.classList.remove("hidden");
    clearTimeout(overlayTimeout);
    overlayTimeout = setTimeout(() => overlay.classList.add("hidden"), 5000);
  };
  document.addEventListener("mousemove", show);
  document.addEventListener("touchstart", show);
  show();
}

// -------------------------
// 📊 Ping- und FPS-Monitor
// -------------------------
async function monitorPing(pc) {
  setInterval(async () => {
    const stats = await pc.getStats();
    let rtt = null;
    stats.forEach(report => {
      if (report.type === "candidate-pair" && report.state === "succeeded" && report.currentRoundTripTime)
        rtt = (report.currentRoundTripTime * 1000).toFixed(1);
    });
    if (rtt) updateHud(`📡 ${rtt} ms`);
  }, 1000);
}

function monitorFPS(video) {
  let last = performance.now(), frames = 0;
  if ("requestVideoFrameCallback" in HTMLVideoElement.prototype) {
    const cb = (now) => {
      frames++;
      const diff = (now - last) / 1000;
      if (diff >= 1) {
        const fps = (frames / diff).toFixed(0);
        updateHud(`🎥 ${fps} FPS`, true);
        frames = 0;
        last = now;
      }
      video.requestVideoFrameCallback(cb);
    };
    video.requestVideoFrameCallback(cb);
  }
}

let hudPing = "📡 -- ms", hudFps = "🎥 -- FPS";
function updateHud(text, isFps = false) {
  if (isFps) {
    hudFps = text;
    const val = parseInt(text.match(/\d+/));
    fpsValue = val;
    updateHudColor();
  } else {
    hudPing = text;
    const val = parseFloat(text.match(/\d+(\.\d+)?/));
    pingValue = val;
    updateHudColor();
  }
  hud.textContent = `${hudPing} | ${hudFps}`;
}

// -------------------------
// 🖥️ Steuerung
// -------------------------
function toggleFullscreen() {
  if (video.requestFullscreen) video.requestFullscreen();
  else if (video.webkitRequestFullscreen) video.webkitRequestFullscreen();
}

function restartStream() { location.reload(); }

// -------------------------
// 👓 VR-Modus (Side-by-Side)
// -------------------------
function toggleView() {
  vrMode = !vrMode;

  const streamCard = document.getElementById("stream-card");
  let vrWrap = document.getElementById("vr-sbs-wrap");

  if (vrMode) {
    if (!currentStream) {
      statusTxt.textContent = "⚠️ Kein Stream geladen";
      vrMode = false;
      return;
    }

    if (!vrWrap) {
      vrWrap = document.createElement("div");
      vrWrap.id = "vr-sbs-wrap";
      vrWrap.style.display = "flex";
      vrWrap.style.flexDirection = "row";
      vrWrap.style.justifyContent = "center";
      vrWrap.style.alignItems = "center";
      vrWrap.style.width = "100%";
      vrWrap.style.gap = "0";
      vrWrap.style.margin = "0";
      vrWrap.style.padding = "0";

      // Zwei nebeneinanderliegende Videos
      const left = document.createElement("video");
      const right = document.createElement("video");

      [left, right].forEach(v => {
        v.autoplay = true;
        v.playsInline = true;
        v.muted = true;
        v.srcObject = currentStream;
        v.style.width = "50%";
        v.style.height = "auto";
        v.style.objectFit = "cover";
        v.style.display = "block";
      });

      vrWrap.appendChild(left);
      vrWrap.appendChild(right);

      streamCard.insertBefore(vrWrap, streamCard.querySelector(".status-bar"));
    }

    video.style.display = "none";
    vrWrap.style.display = "flex";

    statusTxt.textContent = "👓 VR-Modus aktiv";
  } else {
    video.style.display = "block";
    const wrap = document.getElementById("vr-sbs-wrap");
    if (wrap) wrap.style.display = "none";
    statusTxt.textContent = "🖥 Normal-Modus";
  }
}

// -------------------------
// 👁️ Passwort-Toggle
// -------------------------
document.addEventListener("DOMContentLoaded", () => {
  const pw = document.getElementById("password");
  const toggle = document.getElementById("toggle-password");
  toggle.addEventListener("click", () => {
    if (pw.type === "password") {
      pw.type = "text";
      toggle.textContent = "🙈";
    } else {
      pw.type = "password";
      toggle.textContent = "👁️";
    }
  });
  pw.addEventListener("keypress", e => { if (e.key === "Enter") login(); });
});

// ======================================================
// 🌈 DYNAMISCHE NEON-EFFEKTE
// ======================================================
let pingValue = 0, fpsValue = 0;

function updateHudColor() {
  hud.classList.remove("ping-low", "ping-mid", "ping-high", "fps-high", "fps-low");

  // Ping Bewertung
  if (pingValue < 60) hud.classList.add("ping-low");
  else if (pingValue < 120) hud.classList.add("ping-mid");
  else hud.classList.add("ping-high");

  // FPS Bewertung
  if (fpsValue > 40) hud.classList.add("fps-high");
  else hud.classList.add("fps-low");
}

// Farbfluss-Effekt (Hue-Rotation)
let hue = 0;
setInterval(() => {
  hue = (hue + 1) % 360;
  document.documentElement.style.setProperty("--primary", `hsl(${hue}, 100%, 60%)`);
  document.documentElement.style.setProperty("--secondary", `hsl(${(hue + 120) % 360}, 100%, 60%)`);
}, 200);

// ======================================================
// 🔴 Bewegungserkennung HUD-Feedback
// ======================================================
let motionActive = false;

async function checkMotion() {
  try {
    const res = await fetch("/motion");
    const data = await res.json();
    if (data.motion && !motionActive) {
      motionActive = true;
      showMotionAlert(true);
      setTimeout(() => {
        showMotionAlert(false);
        motionActive = false;
      }, 2000);
    }
  } catch (err) {
    console.warn("⚠️ Motion check failed:", err);
  }
}

function showMotionAlert(active) {
  const hud = document.querySelector(".hud");
  if (active) {
    hud.style.color = "#ff0040";
    hud.style.textShadow = "0 0 30px #ff0040";
    hud.textContent = "🔴 Bewegung erkannt!";
    hud.animate(
      [
        { transform: "scale(1)", opacity: 1 },
        { transform: "scale(1.3)", opacity: 0.7 },
        { transform: "scale(1)", opacity: 1 }
      ],
      { duration: 600, iterations: 3 }
    );
  } else {
    hud.style.color = "var(--primary)";
    hud.style.textShadow = "0 0 10px var(--primary)";
  }
}

// Bewegung alle 0.5 Sekunden prüfen
setInterval(checkMotion, 500);