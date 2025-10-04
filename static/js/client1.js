let authPassword = null;
let vrMode = false;
let overlayTimeout;
let currentStream = null;
let pc;
let isAdmin = false;

/* =====================================================
   🔑 LOGIN / REGISTRIERUNG
===================================================== */

async function login() {
  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value.trim();
  const card = document.getElementById("login-card");
  const status = document.getElementById("login-status");

  card.classList.remove("success", "error");
  status.textContent = "";

  try {
    const res = await fetch("/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });

    if (res.status === 200) {
      authPassword = password;
      isAdmin = false;
      card.classList.add("success");
      status.textContent = "✅ Login erfolgreich!";
      setTimeout(() => {
        card.style.display = "none";
        document.getElementById("stream-card").style.display = "block";
        start();
      }, 600);
    } else if (res.status === 202) {
      // Admin
      authPassword = password;
      isAdmin = true;
      card.classList.add("success");
      status.textContent = "👑 Admin-Login erfolgreich!";
      setTimeout(() => {
        card.style.display = "none";
        document.getElementById("stream-card").style.display = "block";
        start();
      }, 600);
    } else if (res.status === 403) {
      card.classList.add("error");
      status.textContent = "❌ Benutzername oder Passwort falsch!";
    } else {
      card.classList.add("error");
      status.textContent = "⚠️ Unbekannter Fehler beim Login!";
    }
  } catch {
    card.classList.add("error");
    status.textContent = "⚠️ Server nicht erreichbar!";
  }
}

async function registerUser() {
  const username = document.getElementById("new-username").value.trim();
  const password = document.getElementById("new-password").value.trim();
  const card = document.getElementById("register-card");
  const status = document.getElementById("register-status");

  card.classList.remove("success", "error");
  status.textContent = "";

  if (!username || !password) {
    card.classList.add("error");
    status.textContent = "⚠️ Bitte alle Felder ausfüllen!";
    return;
  }

  try {
    const res = await fetch("/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });

    if (res.status === 200) {
      card.classList.add("success");
      status.textContent = "✅ Benutzer erfolgreich angelegt!";
      setTimeout(() => switchToLogin(), 900);
    } else if (res.status === 409) {
      card.classList.add("error");
      status.textContent = "❌ Benutzername bereits vergeben!";
    } else {
      card.classList.add("error");
      status.textContent = "⚠️ Fehler bei der Registrierung!";
    }
  } catch {
    card.classList.add("error");
    status.textContent = "⚠️ Server nicht erreichbar!";
  }
}

function switchToRegister() {
  document.getElementById("login-card").style.display = "none";
  document.getElementById("register-card").style.display = "block";
}

function switchToLogin() {
  document.getElementById("register-card").style.display = "none";
  document.getElementById("login-card").style.display = "block";
}

/* =====================================================
   👑 ADMIN OVERLAY (Liste / Löschen / Ändern)
===================================================== */

function openAdminPanel() {
  const overlay = document.getElementById("admin-overlay");
  if (!overlay) return;
  overlay.style.display = "block";
  loadAdminPanel();
}

function closeAdminPanel() {
  const overlay = document.getElementById("admin-overlay");
  if (!overlay) return;
  overlay.style.display = "none";
}

async function loadAdminPanel() {
  const container = document.getElementById("admin-list");
  if (!container) return;
  container.innerHTML = "⏳ Lade Benutzer...";

  try {
    const res = await fetch("/admin/users");
    if (!res.ok) {
      container.innerHTML = "❌ Fehler beim Laden!";
      return;
    }
    const users = await res.json();

    if (!users || users.length === 0) {
      container.innerHTML = "<p>Keine Benutzer registriert.</p>";
      return;
    }

    container.innerHTML = "";
    users.forEach(u => {
      const row = document.createElement("div");
      row.className = "user-row";
      row.innerHTML = `
        <input class="admin-name-input" id="name-${u.id}" value="${escapeHtml(u.username)}" ${u.is_admin ? "disabled" : ""} />
        <input class="admin-pass-input" id="pass-${u.id}" placeholder="${u.is_admin ? "Admin geschützt" : "Neues Passwort (optional)"}" type="text" ${u.is_admin ? "disabled" : ""} />
        <div class="admin-actions">
          <button class="save-btn" ${u.is_admin ? "disabled" : ""} onclick="saveUser(${u.id})">💾</button>
          <button class="delete-btn" ${u.is_admin ? "disabled" : ""} onclick="deleteUser(${u.id})">🗑️</button>
          ${u.is_admin ? '<span class="admin-badge">👑</span>' : ""}
        </div>
      `;
      container.appendChild(row);
    });
  } catch (e) {
    console.error(e);
    container.innerHTML = "⚠️ Serverfehler beim Laden!";
  }
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}

async function saveUser(id) {
  const nameEl = document.getElementById(`name-${id}`);
  const passEl = document.getElementById(`pass-${id}`);
  const newName = nameEl.value.trim();
  const newPass = passEl.value.trim();

  if (!newName && !newPass) {
    alert("Bitte Name und/oder Passwort ändern.");
    return;
  }

  try {
    const res = await fetch("/admin/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, username: newName, password: newPass })
    });

    if (res.status === 200) {
      passEl.value = "";
      loadAdminPanel();
    } else if (res.status === 409) {
      alert("❌ Benutzername bereits vergeben.");
    } else if (res.status === 403) {
      alert("⚠️ Admin-Konten sind geschützt.");
    } else if (res.status === 404) {
      alert("⚠️ Benutzer nicht gefunden.");
    } else {
      alert("❌ Fehler beim Speichern.");
    }
  } catch {
    alert("⚠️ Server nicht erreichbar!");
  }
}

async function deleteUser(id) {
  if (!confirm("Benutzer wirklich löschen?")) return;

  try {
    const res = await fetch("/admin/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id })
    });

    if (res.ok) {
      loadAdminPanel();
    } else if (res.status === 404) {
      alert("⚠️ Benutzer nicht gefunden oder Admin (geschützt).");
    } else {
      alert("❌ Fehler beim Löschen des Benutzers!");
    }
  } catch {
    alert("⚠️ Server nicht erreichbar!");
  }
}

/* =====================================================
   📡 STREAMING & WEBRTC
===================================================== */

const video = document.getElementById("video");
const statusTxt = document.getElementById("status");
const hud = document.querySelector(".hud");

async function start() {
  statusTxt.textContent = "🔄 Verbinde...";
  pc = new RTCPeerConnection({
    iceServers: [{ urls: "stun:stun.l.google.com:19302" }]
  });
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
    headers: { "Content-Type": "application/json", "Authorization": authPassword || "" },
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

/* =====================================================
   🎛 OVERLAY BUTTONS (inkl. Admin)
===================================================== */

function createOverlay() {
  if (document.querySelector(".control-overlay")) return;

  const overlay = document.createElement("div");
  overlay.className = "control-overlay";
  overlay.innerHTML = `
    <button class="overlay-btn" title="Neu verbinden" onclick="restartStream()">🔄</button>
    <button class="overlay-btn" title="Vollbild" onclick="toggleFullscreen()">🖥️</button>
    <button class="overlay-btn" title="Ansicht wechseln" onclick="toggleView()">👓</button>
  `;

  if (isAdmin) {
    const adminBtn = document.createElement("button");
    adminBtn.className = "overlay-btn";
    adminBtn.title = "Benutzerverwaltung";
    adminBtn.textContent = "🛠️";
    adminBtn.onclick = openAdminPanel;
    overlay.appendChild(adminBtn);
  }

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

/* =====================================================
   📊 FPS & PING
===================================================== */

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
let pingValue = 0, fpsValue = 0;

function updateHud(text, isFps = false) {
  if (isFps) {
    hudFps = text;
    fpsValue = parseInt(text.match(/\d+/));
  } else {
    hudPing = text;
    pingValue = parseFloat(text.match(/\d+(\.\d+)?/));
  }
  hud.textContent = `${hudPing} | ${hudFps}`;
  updateHudColor();
}

function updateHudColor() {
  hud.classList.remove("ping-low", "ping-mid", "ping-high", "fps-high", "fps-low");
  if (pingValue < 60) hud.classList.add("ping-low");
  else if (pingValue < 120) hud.classList.add("ping-mid");
  else hud.classList.add("ping-high");

  if (fpsValue > 40) hud.classList.add("fps-high");
  else hud.classList.add("fps-low");
}

/* =====================================================
   🖥️ STEUERUNG
===================================================== */

function toggleFullscreen() {
  if (video.requestFullscreen) video.requestFullscreen();
  else if (video.webkitRequestFullscreen) video.webkitRequestFullscreen();
}

function restartStream() { location.reload(); }

/* =====================================================
   👓 VR
===================================================== */

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
      vrWrap.style.width = "100%";
      const left = document.createElement("video");
      const right = document.createElement("video");
      [left, right].forEach(v => {
        v.autoplay = true;
        v.playsInline = true;
        v.muted = true;
        v.srcObject = currentStream;
        v.style.width = "50%";
        v.style.objectFit = "cover";
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

/* =====================================================
   👁️ PASSWORT TOGGLES
===================================================== */

document.addEventListener("DOMContentLoaded", () => {
  const pw = document.getElementById("password");
  const toggle = document.getElementById("toggle-password");
  if (toggle && pw) {
    toggle.addEventListener("click", () => {
      if (pw.type === "password") { pw.type = "text"; toggle.textContent = "🙈"; }
      else { pw.type = "password"; toggle.textContent = "👁️"; }
    });
  }

  const npw = document.getElementById("new-password");
  const ntoggle = document.getElementById("toggle-new-password");
  if (ntoggle && npw) {
    ntoggle.addEventListener("click", () => {
      if (npw.type === "password") { npw.type = "text"; ntoggle.textContent = "🙈"; }
      else { npw.type = "password"; ntoggle.textContent = "👁️"; }
    });
  }
});

/* =====================================================
   🔴 BEWEGUNGSERKENNUNG & 🌈 NEON
===================================================== */

let motionActive = false;

async function checkMotion() {
  try {
    const res = await fetch("/motion");
    const data = await res.json();
    if (data.motion && !motionActive) {
      motionActive = true;
      const hudEl = document.querySelector(".hud");
      hudEl.style.color = "#ff0040";
      hudEl.style.textShadow = "0 0 30px #ff0040";
      hudEl.textContent = "🔴 Bewegung erkannt!";
      setTimeout(() => {
        hudEl.style.color = "var(--primary)";
        hudEl.style.textShadow = "0 0 10px var(--primary)";
        motionActive = false;
      }, 2000);
    }
  } catch (e) {
    console.warn("⚠️ Motion check failed:", e);
  }
}
setInterval(checkMotion, 500);

let hue = 0;
setInterval(() => {
  hue = (hue + 1) % 360;
  document.documentElement.style.setProperty("--primary", `hsl(${hue}, 100%, 60%)`);
  document.documentElement.style.setProperty("--secondary", `hsl(${(hue + 120) % 360}, 100%, 60%)`);
}, 200);