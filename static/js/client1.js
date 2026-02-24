// Globale Variablen für Authentifizierung, VR-Modus und Streaming
let authPassword = null;      // Wird aktuell nicht genutzt, Platzhalter für künftige Authentifizierung
let vrMode = false;           // Gibt an, ob der VR-Modus aktiv ist
let overlayTimeout;           // Timeout für Overlay-Anzeigen
let currentStream = null;     // Aktueller Video-Stream (WebRTC)
let rightStream = null;       // Zweiter Video-Stream (VR rechts)
let pc;                       // RTCPeerConnection-Objekt (nicht genutzt im go2rtc-Modus)
let go2rtcPlayer = null;
let vrLeftPlayer = null;
let vrRightPlayer = null;
let go2rtcScriptLoaded = false;
let isAdmin = false;          // Benutzerrolle (Admin oder normaler Nutzer)
let token = null;             // JWT-Token für Login-Sitzung
let tokenExpiry = null;       // Zeitpunkt, wann der Token abläuft
let tokenTimer = null;        // Timer für automatischen Logout bei Ablauf
let pingTimer = null;         // Ping-Interval
let fpsMonitorStarted = false;
let connecting = false;

// HUD-Werte (werden später im Stream angezeigt)
let hudTimer = "⏰ --:--";     // Zeigt verbleibende Login-Zeit
let hudPing = "📡 -- ms";      // Netzwerkverzögerung
let hudFps  = "🎥 -- FPS";     // Frames pro Sekunde

// go2rtc-Settings
const GO2RTC_STREAM_PRIMARY = "cam_r"; // Rechte Kamera (Standard)
const GO2RTC_STREAM_VR = "cam_l";      // Linke Kamera (nur im VR-Modus)
const GO2RTC_PORT = 1984;

/* =====================================================
   🔑 LOGIN / REGISTRIERUNG (JWT)
===================================================== */

// Login-Funktion – meldet Benutzer am Server an
async function login() {
  // Eingaben abrufen
  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value.trim();
  const card = document.getElementById("login-card");
  const status = document.getElementById("login-status");

  // Vorherige Statusanzeigen zurücksetzen
  card.classList.remove("success", "error");
  status.textContent = "";

  try {
    // Login-Anfrage an Server schicken
    const res = await fetch("/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });

    const data = await res.text(); // Antwort lesen

    // Erfolgreicher Login (200 = User, 202 = Admin)
    if (res.status === 200 || res.status === 202) {
      const json = JSON.parse(data);
      token = json.token;                               // JWT speichern
      tokenExpiry = Date.now() + json.expires_in * 1000; // Ablaufzeit berechnen
      isAdmin = (res.status === 202);                    // Admin-Flag

      // Token lokal im Browser speichern
      localStorage.setItem("jwt_token", token);
      localStorage.setItem("jwt_expiry", String(tokenExpiry));
      localStorage.setItem("is_admin", String(isAdmin));

      // Visuelles Feedback
      card.classList.add("success");
      status.textContent = isAdmin ? "👑 Admin-Login erfolgreich!" : "✅ Login erfolgreich!";
      showFeedback(status.textContent, "success");

      // Token-Ablauf-Überwachung starten
      scheduleTokenExpiryLogout();

      createOverlay();

      // Nach kurzer Zeit zum Stream wechseln
      setTimeout(() => {
        card.style.display = "none";
        document.getElementById("stream-card").style.display = "block";
        hideLoginVideo(); // <— Hintergrundvideo ausblenden
        start(); // Verbindung aufbauen
      }, 600);
    }
    // Login-Daten falsch
    else if (res.status === 403) {
      card.classList.add("error");
      status.textContent = "❌ Benutzername oder Passwort falsch!";
      showFeedback("❌ Benutzername oder Passwort falsch!", "error");
    }
    // Sonstiger Fehler
    else {
      card.classList.add("error");
      status.textContent = "⚠️ Unbekannter Fehler beim Login!";
      showFeedback("⚠️ Unbekannter Fehler beim Login!", "error");
    }
  } catch {
    // Keine Verbindung zum Server
    card.classList.add("error");
    status.textContent = "⚠️ Server nicht erreichbar!";
    showFeedback("⚠️ Server nicht erreichbar!", "error");
  }
}

// Registrierung eines neuen Benutzers
async function registerUser() {
  const username = document.getElementById("new-username").value.trim();
  const password = document.getElementById("new-password").value.trim();
  const card = document.getElementById("register-card");
  const status = document.getElementById("register-status");

  card.classList.remove("success", "error");
  status.textContent = "";

  // Eingaben prüfen
  if (!username || !password) {
    card.classList.add("error");
    status.textContent = "⚠️ Bitte alle Felder ausfüllen!";
    showFeedback("⚠️ Bitte alle Felder ausfüllen!", "error");
    return;
  }

  try {
    // Registrierung an Server senden
    const res = await fetch("/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });

    // Erfolgreich
    if (res.status === 200) {
      card.classList.add("success");
      status.textContent = "✅ Benutzer erfolgreich angelegt!";
      showFeedback("✅ Benutzer erfolgreich angelegt!", "success");
      setTimeout(() => switchToLogin(), 900);
    }
    // Benutzername existiert schon
    else if (res.status === 409) {
      card.classList.add("error");
      status.textContent = "❌ Benutzername bereits vergeben!";
      showFeedback("❌ Benutzername bereits vergeben!", "error");
    }
    // Allgemeiner Fehler
    else {
      card.classList.add("error");
      status.textContent = "⚠️ Fehler bei der Registrierung!";
      showFeedback("⚠️ Fehler bei der Registrierung!", "error");
    }
  } catch {
    // Server nicht erreichbar
    card.classList.add("error");
    status.textContent = "⚠️ Server nicht erreichbar!";
    showFeedback("⚠️ Server nicht erreichbar!", "error");
  }
}

// Ansicht zwischen Login und Registrierung wechseln
function switchToRegister() {
  document.getElementById("login-card").style.display = "none";
  document.getElementById("register-card").style.display = "block";
}
function switchToLogin() {
  document.getElementById("register-card").style.display = "none";
  document.getElementById("login-card").style.display = "block";
}

/* =====================================================
   👁️ PASSWORT-TOGGLE + ENTER LOGIN
===================================================== */

// Umschalten zwischen „Passwort anzeigen / verbergen“
function setupPasswordToggles() {
  const pw = document.getElementById("password");
  const toggle = document.getElementById("toggle-password");
  if (toggle && pw) {
    toggle.addEventListener("click", () => {
      if (pw.type === "password") {
        pw.type = "text";
        toggle.textContent = "🙈"; // Symbol für „versteckt“
      } else {
        pw.type = "password";
        toggle.textContent = "👁️"; // Symbol für „sichtbar“
      }
    });
  }

  // Für Registrierungspasswort
  const npw = document.getElementById("new-password");
  const ntoggle = document.getElementById("toggle-new-password");
  if (ntoggle && npw) {
    ntoggle.addEventListener("click", () => {
      if (npw.type === "password") {
        npw.type = "text";
        ntoggle.textContent = "🙈";
      } else {
        npw.type = "password";
        ntoggle.textContent = "👁️";
      }
    });
  }
}

// „Enter“-Taste löst Login oder Registrierung aus
function setupEnterShortcuts() {
  const loginInputs = [document.getElementById("username"), document.getElementById("password")];
  loginInputs.forEach(input => {
    if (input) {
      input.addEventListener("keypress", e => {
        if (e.key === "Enter") {
          e.preventDefault();
          login();
        }
      });
    }
  });

  const registerInputs = [document.getElementById("new-username"), document.getElementById("new-password")];
  registerInputs.forEach(input => {
    if (input) {
      input.addEventListener("keypress", e => {
        if (e.key === "Enter") {
          e.preventDefault();
          registerUser();
        }
      });
    }
  });
}

/* =====================================================
   👑 ADMIN OVERLAY
===================================================== */

// Adminbereich öffnen
function openAdminPanel() {
  const overlay = document.getElementById("admin-overlay");
  overlay.style.display = "flex";
  loadAdminPanel(); // Benutzerliste laden
}

// Adminbereich schließen
function closeAdminPanel() {
  document.getElementById("admin-overlay").style.display = "none";
}

// Benutzerliste laden
async function loadAdminPanel() {
  const container = document.getElementById("admin-list");
  container.innerHTML = "<p>⏳ Lade Benutzer...</p>";

  // Kein Token → kein Zugriff
  if (!token) {
    container.innerHTML = "❌ Kein Token – bitte neu anmelden.";
    return;
  }

  try {
    const res = await fetch("/admin/users", {
      headers: { "Authorization": `Bearer ${token}` }
    });

    // Token ungültig / keine Rechte
    if (res.status === 401) {
      container.innerHTML = "⚠️ Sitzung abgelaufen oder keine Admin-Rechte.";
      showFeedback("⚠️ Sitzung abgelaufen – bitte neu anmelden!", "error");
      setTimeout(() => location.reload(), 2000);
      return;
    }

    // Fehlerbehandlung
    if (!res.ok) {
      const msg = await res.text().catch(() => "");
      container.innerHTML = `❌ Fehler (${res.status}): ${msg}`;
      console.warn("Admin-Users fetch failed:", res.status, msg);
      return;
    }

    // Benutzerliste anzeigen
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
        <input id="user-name-${u.id}" value="${escapeHtml(u.username)}" ${u.is_admin ? "disabled" : ""} />
        <input id="user-pass-${u.id}" type="text" placeholder="${u.is_admin ? "Admin geschützt" : "Neues Passwort"}" ${u.is_admin ? "disabled" : ""}/>
        <div class="admin-actions">
          <button class="delete-btn" ${u.is_admin ? "disabled" : ""} onclick="deleteUser(${u.id})">🗑️</button>
          <button class="save-btn" ${u.is_admin ? "disabled" : ""} onclick="saveUser(${u.id})">💾</button>
          ${u.is_admin ? "👑" : ""}
        </div>
      `;
      container.appendChild(row);
    });
  } catch (e) {
    console.error("⚠️ Serverfehler /admin/users:", e);
    container.innerHTML = "⚠️ Serverfehler (Konsole prüfen).";
  }
}// Benutzer aktualisieren (Name/Passwort ändern)
async function saveUser(id) {
  const newName = document.getElementById(`user-name-${id}`).value.trim(); // Neuer Benutzername
  const newPass = document.getElementById(`user-pass-${id}`).value.trim(); // Neues Passwort

  // Wenn nichts geändert wurde → Abbruch
  if (!newName && !newPass) {
    showFeedback("⚠️ Bitte Name oder Passwort ändern!", "error");
    return;
  }

  try {
    // Anfrage an den Server senden
    const res = await fetch("/admin/update", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}` // JWT zur Authentifizierung
      },
      body: JSON.stringify({ id, username: newName, password: newPass })
    });

    // Antwort auswerten
    if (res.status === 200) {
      showFeedback("✅ Benutzer aktualisiert!", "success");
      loadAdminPanel(); // Liste neu laden
    } else if (res.status === 409) {
      showFeedback("❌ Benutzername bereits vergeben!", "error");
    } else if (res.status === 403) {
      showFeedback("⚠️ Admin-Konto geschützt!", "error");
    } else {
      showFeedback("❌ Fehler beim Speichern!", "error");
    }
  } catch {
    // Kein Serverkontakt
    showFeedback("⚠️ Server nicht erreichbar!", "error");
  }
}

// Benutzer löschen
async function deleteUser(id) {
  // Bestätigung abfragen
  if (!confirm("Benutzer wirklich löschen?")) return;

  try {
    // Anfrage an Backend
    const res = await fetch("/admin/delete", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify({ id })
    });
    // Erfolg oder Fehler anzeigen
    if (res.ok) {
      showFeedback("✅ Benutzer gelöscht!", "success");
      loadAdminPanel();
    } else {
      showFeedback("❌ Fehler beim Löschen!", "error");
    }
  } catch {
    showFeedback("⚠️ Server nicht erreichbar!", "error");
  }
}

// HTML-Sonderzeichen sicher escapen (Schutz vor XSS)
function escapeHtml(str) {
  return str.replace(/[&<>"']/g, m => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]
  ));
}

/* =====================================================
   TOKEN-EXPIRY-HANDLING + COUNTDOWN → HUD Timer
===================================================== */

// Logout planen, wenn Token abläuft
function scheduleTokenExpiryLogout() {
  if (tokenTimer) clearTimeout(tokenTimer);
  const timeLeft = tokenExpiry - Date.now();
  if (timeLeft <= 0) {
    logoutDueToExpiry(); // Falls bereits abgelaufen
    return;
  }
  startTokenCountdown(); // Countdown starten
  tokenTimer = setTimeout(logoutDueToExpiry, timeLeft);
}

// Countdown für HUD-Anzeige (zeigt Restzeit)
function startTokenCountdown() {
  const interval = setInterval(() => {
    if (!tokenExpiry) return clearInterval(interval);
    const remaining = tokenExpiry - Date.now();
    if (remaining <= 0) {
      clearInterval(interval);
      logoutDueToExpiry();
      return;
    }
    const min = Math.floor(remaining / 60000);
    const sec = Math.floor((remaining % 60000) / 1000).toString().padStart(2, "0");
    hudTimer = `⏰ ${min}:${sec}`;
    updateHudDisplay();
  }, 1000);
}

// Automatischer Logout, wenn Token abläuft
function logoutDueToExpiry() {
  showFeedback("⚠️ Sitzung abgelaufen – bitte neu anmelden!", "error");
  localStorage.removeItem("jwt_token");
  localStorage.removeItem("jwt_expiry");
  localStorage.removeItem("is_admin");
  token = null;
  tokenExpiry = null;
  isAdmin = false;
  setTimeout(() => location.reload(), 2000);
}

/* =====================================================
   AUTO-LOGIN (Token-basierter Login beim Laden)
===================================================== */

document.addEventListener("DOMContentLoaded", () => {
  setupPasswordToggles();   // Buttons 👁️ aktivieren
  setupEnterShortcuts();    // Enter-Tasten aktivieren

  const savedToken = localStorage.getItem("jwt_token");
  const savedExpiry = localStorage.getItem("jwt_expiry");
  const adminFlag = localStorage.getItem("is_admin");

  // Wenn gültiger Token existiert → Auto-Login
  if (savedToken && savedExpiry && Date.now() < parseInt(savedExpiry)) {
    token = savedToken;
    tokenExpiry = parseInt(savedExpiry);
    isAdmin = (adminFlag === "true");
    scheduleTokenExpiryLogout();
        // Video sicher entfernen, falls noch da
    hideLoginVideo(); // 🔥 <—— DAS IST NEU
    document.getElementById("login-card").style.display = "none";
    document.getElementById("stream-card").style.display = "block";
    start(); // Stream starten
  }
  createOverlay();
});

/* =====================================================
   STREAM / HUD / VR-STEUERUNG
===================================================== */

const statusTxt = document.getElementById("status"); // Statusanzeige

function resetStreams() {
  currentStream = null;
  rightStream = null;
  if (go2rtcPlayer) {
    go2rtcPlayer.remove();
    go2rtcPlayer = null;
  }
  if (vrLeftPlayer) {
    vrLeftPlayer.remove();
    vrLeftPlayer = null;
  }
  if (vrRightPlayer) {
    vrRightPlayer.remove();
    vrRightPlayer = null;
  }
}

function getVideoFromPlayer(player) {
  if (!player) return null;
  if (player.video) return player.video;
  const direct = player.querySelector("video");
  if (direct) return direct;
  const shadow = player.shadowRoot ? player.shadowRoot.querySelector("video") : null;
  return shadow || null;
}

function loadGo2RTCScript() {
  return new Promise((resolve, reject) => {
    if (go2rtcScriptLoaded) return resolve();
    const script = document.createElement("script");
    const scheme = location.protocol === "https:" ? "https" : "http";
    script.src = `${scheme}://${location.hostname}:${GO2RTC_PORT}/video-rtc.js`;
    script.onload = () => {
      go2rtcScriptLoaded = true;
      resolve();
    };
    script.onerror = () => reject(new Error("go2rtc script load failed"));
    document.head.appendChild(script);
  });
}

function createGo2RTCPlayer(streamName) {
  const player = document.createElement("video-rtc");
  player.setAttribute("autoplay", "");
  player.setAttribute("playsinline", "");
  player.setAttribute("muted", "true");
  player.style.width = "100%";
  player.style.height = "100%";
  const wsScheme = location.protocol === "https:" ? "wss" : "ws";
  const wsUrl = `${wsScheme}://${location.hostname}:${GO2RTC_PORT}/api/ws?src=${streamName}`;
  player.setAttribute("src", wsUrl);
  return player;
}

function attachFpsMonitor(player) {
  let tries = 0;
  const timer = setInterval(() => {
    const vid = getVideoFromPlayer(player);
    if (vid && !fpsMonitorStarted) {
      monitorFPS(vid);
      fpsMonitorStarted = true;
      clearInterval(timer);
    }
    if (++tries > 10) clearInterval(timer);
  }, 300);
}

async function startGo2RTC() {
  await loadGo2RTCScript();
  const wrap = document.getElementById("player-wrap");
  if (!wrap) throw new Error("player wrap missing");

  go2rtcPlayer = createGo2RTCPlayer(GO2RTC_STREAM_PRIMARY);
  wrap.innerHTML = "";
  wrap.appendChild(go2rtcPlayer);

  setTimeout(() => attachFpsMonitor(go2rtcPlayer), 600);
}

async function startGo2RTCVR() {
  await loadGo2RTCScript();
  const body = document.body;
  const header = document.querySelector("header");
  const loginCard = document.getElementById("login-card");
  const registerCard = document.getElementById("register-card");
  const streamCard = document.getElementById("stream-card");
  const footer = document.querySelector("footer");
  const overlay = document.querySelector(".control-overlay");
  const hudEl = document.querySelector(".hud");

  if (header) header.style.display = "none";
  if (loginCard) loginCard.style.display = "none";
  if (registerCard) registerCard.style.display = "none";
  if (footer) footer.style.display = "none";
  if (streamCard) streamCard.style.display = "none";
  if (overlay) overlay.style.display = "none";
  if (hudEl) hudEl.style.display = "none";

  let vrWrap = document.getElementById("vr-sbs-wrap");
  if (!vrWrap) {
    vrWrap = document.createElement("div");
    vrWrap.id = "vr-sbs-wrap";
    Object.assign(vrWrap.style, {
      display: "flex",
      flexDirection: "row",
      width: "100vw",
      height: "100vh",
      position: "fixed",
      top: "0",
      left: "0",
      zIndex: "9999",
      background: "black",
    });

    vrLeftPlayer = createGo2RTCPlayer(GO2RTC_STREAM_VR);
    vrRightPlayer = createGo2RTCPlayer(GO2RTC_STREAM_PRIMARY);

    [vrLeftPlayer, vrRightPlayer].forEach((p) => {
      p.style.width = "50%";
      p.style.height = "100%";
      p.style.display = "block";
    });

    vrWrap.appendChild(vrLeftPlayer);
    vrWrap.appendChild(vrRightPlayer);

    const exitBtn = document.createElement("button");
    exitBtn.textContent = "🚪";
    exitBtn.title = "VR verlassen";
    exitBtn.className = "overlay-btn vr-exit";
    Object.assign(exitBtn.style, {
      position: "absolute",
      top: "20px",
      right: "20px",
      zIndex: "10000"
    });
    exitBtn.onclick = () => toggleView();
    vrWrap.appendChild(exitBtn);

    document.body.appendChild(vrWrap);
  }

  body.classList.add("vr-active");
  vrWrap.style.display = "flex";
  if (vrWrap.requestFullscreen) vrWrap.requestFullscreen().catch(() => {});

  setTimeout(() => attachFpsMonitor(vrRightPlayer), 600);
}

// Verbindung zu go2rtc-Stream aufbauen
async function start({ vr = false } = {}) {
  if (connecting) return;
  connecting = true;
  statusTxt.textContent = "🔄 Verbinde...";
  resetStreams();
  try {
    if (vr) {
      await startGo2RTCVR();
      statusTxt.textContent = "👓 VR verbunden!";
    } else {
      await startGo2RTC();
      statusTxt.textContent = "✅ Verbunden!";
    }
    monitorPing();
  } catch {
    statusTxt.textContent = "⚠️ Stream-Fehler!";
  } finally {
    connecting = false;
  }
}

// Overlay mit Buttons (Neu laden, VR etc.)
function createOverlay() {
  // Entferne altes Overlay, falls vorhanden (wichtig!)
  const oldOverlay = document.querySelector(".control-overlay");
  if (oldOverlay) oldOverlay.remove();

  // Neues Overlay erzeugen
  const overlay = document.createElement("div");
  overlay.className = "control-overlay";
  overlay.innerHTML = `
    <button class="overlay-btn" title="Neu verbinden" onclick="restartStream()">🔄</button>
    <button class="overlay-btn" title="Vollbild" onclick="toggleFullscreen()">🖥️</button>
    <button class="overlay-btn" title="VR-Modus" onclick="toggleView()">👓</button>
    ${isAdmin ? `<button class="overlay-btn" title="Benutzerverwaltung" onclick="openAdminPanel()">🛠️</button>` : ""}
    <button class="overlay-btn" title="Abmelden" onclick="logoutUser()">🚪</button>
  `;
  document.querySelector(".status-bar").appendChild(overlay);
}

async function stopConnection() {
  if (pc) {
    pc.ontrack = null;
    const receivers = pc.getReceivers ? pc.getReceivers() : [];
    receivers.forEach(r => r.track && r.track.stop());
    pc.close();
    pc = null;
  }
  if (currentStream) currentStream.getTracks().forEach(t => t.stop());
  if (rightStream) rightStream.getTracks().forEach(t => t.stop());
  if (pingTimer) clearInterval(pingTimer);
  resetStreams();
}

async function switchStreamMode(vr) {
  if (connecting) return;
  await stopConnection();
  await start({ vr });
}

function updateVrSources() {
  // VR deaktiviert im go2rtc-Modus
}

/* =====================================================
   ✅ FPS & PING → HUD-Anzeige
===================================================== */

// HUD-Werte aktualisieren
function updateHud(text, isFps = false) {
  if (isFps) hudFps = text;
  else hudPing = text;
  updateHudDisplay();
}

// HUD-Anzeige im DOM aktualisieren
function updateHudDisplay() {
  const hudEl = document.querySelector(".hud");
  if (!hudEl) return;
  hudEl.textContent = `${hudPing} | ${hudFps} | ${hudTimer}`;
}

// Ping-Messung über WebRTC-Statistiken
function monitorPing(pc) {
  if (pingTimer) clearInterval(pingTimer);
  pingTimer = setInterval(async () => {
    const t0 = performance.now();
    try {
      await fetch("/ping", { cache: "no-store" });
      const ms = (performance.now() - t0).toFixed(1);
      updateHud(`📡 ${ms} ms`);
    } catch {}
  }, 1000);
}

// FPS-Messung des Videostreams
function monitorFPS(videoEl) {
  // Exakte Methode mit requestVideoFrameCallback (wenn unterstützt)
  if ("requestVideoFrameCallback" in HTMLVideoElement.prototype) {
    let last = performance.now(), frames = 0;
    const cb = (now) => {
      frames++;
      const diff = (now - last) / 1000;
      if (diff >= 1) {
        const fps = (frames / diff).toFixed(0);
        updateHud(`🎥 ${fps} FPS`, true);
        frames = 0;
        last = now;
      }
      videoEl.requestVideoFrameCallback(cb);
    };
    videoEl.requestVideoFrameCallback(cb);
    return;
  }

  // Fallback (schätzt FPS über currentTime)
  let lastTime = 0, lastTs = Date.now(), frames = 0;
  setInterval(() => {
    if (!videoEl || videoEl.readyState < 2) return;
    const ct = videoEl.currentTime;
    frames += (ct !== lastTime) ? 1 : 0;
    const now = Date.now();
    const diff = (now - lastTs) / 1000;
    if (diff >= 1) {
      updateHud(`🎥 ${frames} FPS`, true);
      frames = 0;
      lastTs = now;
    }
    lastTime = ct;
  }, 200);
}

/* =====================================================
   ✅ VR-VOLLANSICHT (Side-by-Side)
===================================================== */

// Schaltet zwischen normaler und VR-Ansicht
async function toggleView() {
  if (connecting) return;
  vrMode = !vrMode;

  const body = document.body;
  const header = document.querySelector("header");
  const loginCard = document.getElementById("login-card");
  const registerCard = document.getElementById("register-card");
  const streamCard = document.getElementById("stream-card");
  const footer = document.querySelector("footer");
  const overlay = document.querySelector(".control-overlay");
  const hudEl = document.querySelector(".hud");

  if (vrMode) {
    await stopConnection();
    await start({ vr: true });
  } else {
    body.classList.remove("vr-active");
    const wrap = document.getElementById("vr-sbs-wrap");
    if (wrap) wrap.remove();

    if (header) header.style.display = "";
    if (loginCard) loginCard.style.display = "none";
    if (registerCard) registerCard.style.display = "none";
    if (footer) footer.style.display = "";
    if (streamCard) streamCard.style.display = "block";
    if (overlay) overlay.style.display = "";
    if (hudEl) hudEl.style.display = "";

    document.exitFullscreen?.().catch(() => {});
    await stopConnection();
    await start({ vr: false });
  }
}

/* =====================================================
   🔧 HILFSFUNKTIONEN
===================================================== */

// Vollbildmodus aktivieren
function toggleFullscreen() {
  const target =
    document.getElementById("vr-sbs-wrap") ||
    go2rtcPlayer ||
    document.getElementById("player-wrap");
  if (!target) return;
  if (target.requestFullscreen) target.requestFullscreen();
  else if (target.webkitRequestFullscreen) target.webkitRequestFullscreen();
}

// Seite neu laden (z. B. bei Streamfehler)
function restartStream() { location.reload(); }

// Kurze visuelle Rückmeldung anzeigen
function showFeedback(message, type = "success") {
  const box = document.getElementById("ui-feedback");
  if (!box) return;
  box.textContent = message;
  box.className = `ui-feedback show ${type}`;
  setTimeout(() => { box.className = "ui-feedback"; }, 3000);
}

// Farbanimation für UI-Akzente
let hue = 0;
setInterval(() => {
  hue = (hue + 1) % 360;
  document.documentElement.style.setProperty("--primary", `hsl(${hue}, 100%, 60%)`);
  document.documentElement.style.setProperty("--secondary", `hsl(${(hue + 120) % 360}, 100%, 60%)`);
}, 200);
/* =====================================================
   🔧 LOGIN VIDEO BACKGROUND HANDLING
===================================================== */

// Wenn der Benutzer sich einloggt oder registriert → Login-Hintergrund ausblenden
function hideLoginVideo() {
  const vid = document.getElementById("login-bg-video");
  if (vid) {
    vid.style.opacity = "0";
    setTimeout(() => {
      vid.remove();
      document.body.classList.remove("login-active");
    }, 800);
  }
}

/* =====================================================
   🚪 MANUELLER LOGOUT (ALLE BENUTZER)
===================================================== */
function logoutUser() {
  // Verbindung schließen, falls vorhanden
  try {
    if (pc) pc.close();
  } catch {}

  // Token & Status löschen
  localStorage.removeItem("jwt_token");
  localStorage.removeItem("jwt_expiry");
  localStorage.removeItem("is_admin");

  token = null;
  tokenExpiry = null;
  isAdmin = false;

  showFeedback("👋 Erfolgreich abgemeldet!", "success");

  // Nach 1 Sekunde zurück zur Login-Seite
  setTimeout(() => {
    location.reload();
  }, 1000);
}
