let authPassword = null;
let vrMode = false;
let overlayTimeout;

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
const status = document.getElementById("status");
const hud = document.querySelector(".hud");
let pc;

// -------------------------
async function start() {
  status.textContent = "🔄 Verbinde...";
  pc = new RTCPeerConnection({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] });
  pc.addTransceiver("video", { direction: "recvonly" });

  pc.ontrack = (event) => {
    video.srcObject = event.streams[0];
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
    status.textContent = "❌ Zugriff verweigert!";
    return;
  }

  const answer = await res.json();
  await pc.setRemoteDescription(answer);
  status.textContent = "✅ Verbunden!";
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
  if (isFps) hudFps = text; else hudPing = text;
  hud.textContent = `${hudPing} | ${hudFps}`;
}

function toggleFullscreen() {
  if (video.requestFullscreen) video.requestFullscreen();
  else if (video.webkitRequestFullscreen) video.webkitRequestFullscreen();
}
function restartStream() { location.reload(); }
function toggleView() {
  vrMode = !vrMode;
  video.style.width = vrMode ? "50%" : "100%";
  video.style.transform = vrMode ? "scale(1.2)" : "none";
  status.textContent = vrMode ? "👓 VR-Modus aktiv" : "🖥 Normal-Modus";
}

// -------------------------
document.addEventListener("DOMContentLoaded", () => {
  const pw = document.getElementById("password");
  const toggle = document.getElementById("toggle-password");
  toggle.addEventListener("click", () => {
    if (pw.type === "password") { pw.type = "text"; toggle.textContent = "🙈"; }
    else { pw.type = "password"; toggle.textContent = "👁️"; }
  });
  pw.addEventListener("keypress", e => { if (e.key === "Enter") login(); });
});