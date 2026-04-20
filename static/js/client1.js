// Globale Variablen für Authentifizierung, VR-Modus und Streaming
let authPassword = null;      // Wird aktuell nicht genutzt, Platzhalter für künftige Authentifizierung
let vrMode = false;           // Gibt an, ob der VR-Modus aktiv ist
let overlayTimeout;           // Timeout für Overlay-Anzeigen
let currentStream = null;     // Aktueller Video-Stream (WebRTC)
let pc;                       // RTCPeerConnection-Objekt (WebRTC-Verbindung)
let isAdmin = false;          // Benutzerrolle (Admin oder normaler Nutzer)
let token = null;             // JWT-Token für Login-Sitzung
let tokenExpiry = null;       // Zeitpunkt, wann der Token abläuft
let tokenTimer = null;        // Timer für automatischen Logout bei Ablauf
let pingTimer = null;         // Ping-Interval
let connecting = false;       // Verhindert Doppel-Connects
let vrStreams = [];           // Streams im VR-Modus (links/rechts)
let vrLeftVideo = null;
let vrRightVideo = null;
let vrStereoSbs = false;      // True, wenn ein kombinierter Stereo-Stream genutzt wird
let xrSession = null;         // Echte WebXR-Session für Apple Vision Pro
let xrState = null;           // WebGL/WebXR-Renderer-State
let xrVideoHost = null;       // Unsichtbarer Host fuer Safari/visionOS Video-Decoding
let vrPreparingWebXr = false; // VR-Stream wird aufgebaut, bevor WebXR startet
let xrRenderLoopStarted = false;
let xrTextureErrorLogged = false;
let threeModulePromise = null;
let xrSecondCameraEnabled = false;
const XR_VIDEO_FIT_MODE = "contain"; // "contain" verhindert gestauchte WebXR-Bilder.
const XR_RENDER_MODE = new URLSearchParams(window.location.search).get("xrMode") || "screen";
const XR_DISTANCE_OVERRIDE = readXrNumberParam("xrDistance", null);
const XR_WIDTH_OVERRIDE = readXrNumberParam("xrWidth", null);
const XR_FOV_OVERRIDE = readXrNumberParam("xrFov", null);
const XR_VIDEO_TIMEOUT_MS = 7000;
const XR_SCREEN_SCALE = Math.min(0.9, Math.max(0.2, readXrNumberParam("xrScale", 0.42)));
const XR_FRAMEBUFFER_SCALE = Math.min(1.8, Math.max(1.0, readXrNumberParam("xrFramebufferScale", 1.25)));
const XR_PLANE_HEIGHT = Math.min(2.2, Math.max(0.0, readSignedXrNumberParam("xrPlaneHeight", 1.6)));
const DEFAULT_VR_EYE_ASPECT = 16 / 9;
const XR_STEREO_EYE_ASPECT = readXrNumberParam("xrEyeAspect", DEFAULT_VR_EYE_ASPECT);
const XR_STEREO_CROP = Math.min(0.08, Math.max(0.0, readSignedXrNumberParam("xrStereoCrop", 0.035)));
const XR_CONVERGENCE = Math.min(0.08, Math.max(-0.08, readSignedXrNumberParam("xrConvergence", 0.0)));
const XR_VERTICAL_ALIGN = Math.min(0.06, Math.max(-0.06, readSignedXrNumberParam("xrVerticalAlign", 0.0)));
const XR_SWAP_EYES = readXrBoolParam("xrSwapEyes", false);
const XR_STEREO_ENABLED = readXrBoolParam("xrStereo", true);
const XR_MONO = !XR_STEREO_ENABLED;
const THREE_MODULE_URL = "https://cdn.jsdelivr.net/npm/three@0.164.1/build/three.module.js";
let vrEyeAspect = DEFAULT_VR_EYE_ASPECT;

// HUD-Werte (werden später im Stream angezeigt)
let hudTimer = "⏰ --:--";     // Zeigt verbleibende Login-Zeit
let hudPing = "📡 -- ms";      // Netzwerkverzögerung
let hudFps  = "🎥 -- FPS";     // Frames pro Sekunde

function readXrNumberParam(name, fallback) {
  const value = Number(new URLSearchParams(window.location.search).get(name));
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function readXrBoolParam(name, fallback) {
  const value = new URLSearchParams(window.location.search).get(name);
  if (value === null) return fallback;
  return value === "1" || value.toLowerCase() === "true" || value.toLowerCase() === "yes";
}

function readSignedXrNumberParam(name, fallback) {
  const value = Number(new URLSearchParams(window.location.search).get(name));
  return Number.isFinite(value) ? value : fallback;
}

function getClientProfile(vr) {
  return {
    vr,
    viewportWidth: window.innerWidth,
    viewportHeight: window.innerHeight,
    screenWidth: window.screen?.width || 0,
    screenHeight: window.screen?.height || 0,
    devicePixelRatio: window.devicePixelRatio || 1,
    hardwareConcurrency: navigator.hardwareConcurrency || 0,
    userAgent: navigator.userAgent,
    xrDistance: XR_DISTANCE_OVERRIDE,
    xrWidth: XR_WIDTH_OVERRIDE
  };
}

function getAdaptiveXrPlane(videoEl, stereoSbs = false) {
  const hasVideoSize = videoEl?.videoWidth && videoEl?.videoHeight;
  const sourceAspect = hasVideoSize
    ? videoEl.videoWidth / videoEl.videoHeight
    : (stereoSbs ? DEFAULT_VR_EYE_ASPECT * 2 : 16 / 9);
  const videoAspect = stereoSbs ? XR_STEREO_EYE_ASPECT : sourceAspect;
  const viewportAspect = window.innerWidth && window.innerHeight
    ? window.innerWidth / window.innerHeight
    : videoAspect;
  const curvedMode = XR_RENDER_MODE !== "plane";
  const baseDistance = XR_DISTANCE_OVERRIDE || (curvedMode ? 2.8 : Math.max(3.2, Math.min(5.0, 2.8 + (window.devicePixelRatio || 1) * 0.35)));
  const horizontalFovDeg = XR_FOV_OVERRIDE || (curvedMode ? 60 : 44);
  const fovWidth = 2 * baseDistance * Math.tan((horizontalFovDeg * Math.PI / 180) / 2);
  const baseWidth = XR_WIDTH_OVERRIDE || (curvedMode ? fovWidth : Math.max(1.8, Math.min(3.0, baseDistance * 0.72)));
  const width = viewportAspect < 1 ? baseWidth * 0.85 : baseWidth;
  return {
    distance: baseDistance,
    halfFov: (horizontalFovDeg * Math.PI / 180) / 2,
    width,
    height: width / videoAspect
  };
}

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

      // Nach kurzer Zeit zum Stream wechseln
      setTimeout(() => {
        card.style.display = "none";
        document.getElementById("stream-card").style.display = "block";
        hideLoginVideo(); // <— Hintergrundvideo ausblenden
        start({ vr: false }); // Verbindung aufbauen
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
  stopConnection();
  if (vrMode) {
    exitVrUi();
    vrMode = false;
  }
  localStorage.removeItem("jwt_token");
  localStorage.removeItem("jwt_expiry");
  localStorage.removeItem("is_admin");
  token = null;
  tokenExpiry = null;
  isAdmin = false;
  setTimeout(() => location.reload(), 2000);
}

// Manueller Logout (Button)
function logoutUser() {
  stopConnection();
  if (vrMode) {
    exitVrUi();
    vrMode = false;
  }
  localStorage.removeItem("jwt_token");
  localStorage.removeItem("jwt_expiry");
  localStorage.removeItem("is_admin");
  token = null;
  tokenExpiry = null;
  isAdmin = false;
  location.reload();
}

/* =====================================================
   AUTO-LOGIN (Token-basierter Login beim Laden)
===================================================== */

document.addEventListener("DOMContentLoaded", () => {
  setupPasswordToggles();   // Buttons 👁️ aktivieren
  setupEnterShortcuts();    // Enter-Tasten aktivieren
  setupFullscreenControls();

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
    start({ vr: false }); // Stream starten
  }
});

/* =====================================================
   STREAM / HUD / VR-STEUERUNG
===================================================== */

const video = document.getElementById("video");   // Videotag
const statusTxt = document.getElementById("status"); // Statusanzeige

function resetStreams() {
  currentStream = null;
  vrStreams = [];
  vrStereoSbs = false;
  if (video) video.srcObject = null;
  if (vrLeftVideo) vrLeftVideo.srcObject = null;
  if (vrRightVideo) vrRightVideo.srcObject = null;
}

function loadThreeModule() {
  if (!threeModulePromise) {
    threeModulePromise = import(THREE_MODULE_URL);
  }
  return threeModulePromise;
}

async function toggleSecondCamera(enabled) {
  try {
    const res = await fetch("/camera/second", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify({ enabled })
    });

    if (!res.ok) {
      throw new Error(`Second camera switch failed: ${res.status}`);
    }

    xrSecondCameraEnabled = enabled;
    return true;
  } catch (error) {
    console.warn("Zweite Kamera konnte nicht geschaltet werden:", error);
    showFeedback(
      enabled ? "⚠️ Zweite Kamera konnte nicht aktiviert werden." : "⚠️ Zweite Kamera konnte nicht deaktiviert werden.",
      "error"
    );
    return false;
  }
}

function createStereoVideoShaderMaterial(THREE, texture) {
  const uniforms = {
    map: { value: texture },
    isVR: { value: false },
    eyeIndex: { value: 0.0 },
    videoResolution: { value: new THREE.Vector2(16, 9) },
    eyeAspect: { value: DEFAULT_VR_EYE_ASPECT },
    planeAspect: { value: DEFAULT_VR_EYE_ASPECT }
  };

  return new THREE.ShaderMaterial({
    uniforms,
    depthTest: false,
    depthWrite: false,
    side: THREE.DoubleSide,
    vertexShader: `
      varying vec2 vUv;

      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      precision highp float;

      uniform sampler2D map;
      uniform bool isVR;
      uniform float eyeIndex;
      uniform vec2 videoResolution;
      uniform float eyeAspect;
      uniform float planeAspect;
      varying vec2 vUv;

      vec2 containUv(vec2 uv, float contentAspect, float viewportAspect) {
        if (viewportAspect > contentAspect) {
          float visibleWidth = contentAspect / viewportAspect;
          uv.x = (uv.x - 0.5) / visibleWidth + 0.5;
        } else {
          float visibleHeight = viewportAspect / contentAspect;
          uv.y = (uv.y - 0.5) / visibleHeight + 0.5;
        }
        return uv;
      }

      void main() {
        float monoAspect = max(videoResolution.x / max(videoResolution.y, 1.0), 0.0001);
        float cameraAspect = isVR ? eyeAspect : monoAspect;
        vec2 uv = containUv(vUv, cameraAspect, max(planeAspect, 0.0001));

        if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
          gl_FragColor = vec4(0.0, 0.0, 0.0, 1.0);
          return;
        }

        if (isVR) {
          float sideBySideOffset = eyeIndex < 0.5 ? 0.0 : 0.5;
          uv.x = uv.x * 0.5 + sideBySideOffset;
        }

        gl_FragColor = texture2D(map, uv);
      }
    `
  });
}

function compileShader(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const info = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(info || "Shader konnte nicht kompiliert werden");
  }
  return shader;
}

function createProgram(gl, vertexSource, fragmentSource) {
  const vertexShader = compileShader(gl, gl.VERTEX_SHADER, vertexSource);
  const fragmentShader = compileShader(gl, gl.FRAGMENT_SHADER, fragmentSource);
  const program = gl.createProgram();
  gl.attachShader(program, vertexShader);
  gl.attachShader(program, fragmentShader);
  gl.linkProgram(program);
  gl.deleteShader(vertexShader);
  gl.deleteShader(fragmentShader);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const info = gl.getProgramInfoLog(program);
    gl.deleteProgram(program);
    throw new Error(info || "WebGL-Programm konnte nicht gelinkt werden");
  }
  return program;
}

function createVideoTexture(gl) {
  const texture = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, texture);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texImage2D(
    gl.TEXTURE_2D,
    0,
    gl.RGBA,
    2,
    2,
    0,
    gl.RGBA,
    gl.UNSIGNED_BYTE,
    new Uint8Array([
      0, 120, 255, 255,
      255, 255, 255, 255,
      255, 255, 255, 255,
      0, 220, 120, 255
    ])
  );
  return texture;
}

function createXrMesh(horizontalSegments = 64, verticalSegments = 8) {
  const data = [];

  function pushVertex(xIndex, yIndex) {
    const x = (xIndex / horizontalSegments) * 2 - 1;
    const y = (yIndex / verticalSegments) * 2 - 1;
    const u = xIndex / horizontalSegments;
    const v = yIndex / verticalSegments;
    data.push(x, y, u, v);
  }

  for (let y = 0; y < verticalSegments; y++) {
    for (let x = 0; x < horizontalSegments; x++) {
      pushVertex(x, y);
      pushVertex(x + 1, y);
      pushVertex(x, y + 1);

      pushVertex(x, y + 1);
      pushVertex(x + 1, y);
      pushVertex(x + 1, y + 1);
    }
  }

  return new Float32Array(data);
}

function updateVideoTexture(gl, texture, videoEl) {
  if (!videoEl || videoEl.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || !videoEl.videoWidth || !videoEl.videoHeight) {
    return false;
  }
  gl.bindTexture(gl.TEXTURE_2D, texture);
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
  gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
  gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
  try {
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, videoEl);
    return true;
  } catch (error) {
    // Safari kann während des Stream-Wechsels kurzzeitig Frames ablehnen.
    if (!xrTextureErrorLogged) {
      console.warn("WebXR-Video konnte noch nicht als Textur geladen werden:", error);
      xrTextureErrorLogged = true;
    }
    return false;
  }
}

function getVideoLayout(videoEl, stereoSbs = false) {
  const plane = getAdaptiveXrPlane(videoEl, stereoSbs);
  if (!videoEl || !videoEl.videoWidth || !videoEl.videoHeight) {
    return {
      distance: plane.distance,
      planeScale: [plane.width / 2, plane.height / 2],
      uvScale: [1, 1],
      uvOffset: [0, 0]
    };
  }

  const videoAspect = getEyeVideoAspect(videoEl, stereoSbs);
  const eyeHeight = plane.width / videoAspect;

  if (XR_VIDEO_FIT_MODE === "cover") {
    return {
      distance: plane.distance,
      planeScale: [plane.width / 2, eyeHeight / 2],
      uvScale: [1, 1],
      uvOffset: [0, 0]
    };
  }

  return {
    distance: plane.distance,
    planeScale: [plane.width / 2, eyeHeight / 2],
    uvScale: [1, 1],
    uvOffset: [0, 0]
  };
}

function getEyeVideoAspect(videoEl, stereoSbs = false) {
  if (stereoSbs && XR_STEREO_EYE_ASPECT) {
    return XR_STEREO_EYE_ASPECT;
  }

  if (!videoEl || !videoEl.videoWidth || !videoEl.videoHeight) {
    return stereoSbs ? DEFAULT_VR_EYE_ASPECT : 16 / 9;
  }

  const sourceAspect = videoEl.videoWidth / videoEl.videoHeight;
  return stereoSbs ? sourceAspect / 2 : sourceAspect;
}

function getScreenContainScale(videoEl, stereoSbs, viewport) {
  const videoAspect = getEyeVideoAspect(videoEl, stereoSbs);
  const viewportAspect = viewport?.width && viewport?.height
    ? viewport.width / viewport.height
    : 1;

  let scaleX = XR_SCREEN_SCALE;
  let scaleY = XR_SCREEN_SCALE;

  if (videoAspect > viewportAspect) {
    scaleY *= viewportAspect / videoAspect;
  } else {
    scaleX *= videoAspect / viewportAspect;
  }

  return [scaleX, scaleY];
}

function getStereoUvWindow(isLeftEye, stereoSbs) {
  if (!stereoSbs) {
    return { offset: 0.0, scale: 1.0, verticalShift: 0.0 };
  }

  const sourceIsLeft = XR_MONO ? !XR_SWAP_EYES : (isLeftEye !== XR_SWAP_EYES);
  const baseOffset = sourceIsLeft ? 0.0 : 0.5;
  const scale = Math.max(0.34, 0.5 - 2 * XR_STEREO_CROP);
  const convergenceShift = XR_MONO ? 0.0 : (sourceIsLeft ? XR_CONVERGENCE : -XR_CONVERGENCE);
  const rawOffset = baseOffset + XR_STEREO_CROP + convergenceShift;
  const minOffset = baseOffset;
  const maxOffset = baseOffset + 0.5 - scale;

  return {
    offset: Math.min(maxOffset, Math.max(minOffset, rawOffset)),
    scale,
    verticalShift: XR_MONO ? 0.0 : (isLeftEye ? XR_VERTICAL_ALIGN : -XR_VERTICAL_ALIGN)
  };
}

function getMonoUvWindow(stereoSbs) {
  if (!stereoSbs) {
    return { offset: 0.0, scale: 1.0 };
  }

  const sourceIsLeft = !XR_SWAP_EYES;
  const baseOffset = sourceIsLeft ? 0.0 : 0.5;
  const scale = Math.max(0.34, 0.5 - 2 * XR_STEREO_CROP);

  return {
    offset: baseOffset + XR_STEREO_CROP,
    scale
  };
}

function createVrVideo(stream) {
  const videoEl = document.createElement("video");
  videoEl.autoplay = true;
  videoEl.playsInline = true;
  videoEl.setAttribute("playsinline", "");
  videoEl.setAttribute("webkit-playsinline", "");
  videoEl.muted = true;
  videoEl.defaultMuted = true;
  videoEl.disablePictureInPicture = true;
  videoEl.srcObject = stream;
  videoEl.addEventListener("loadedmetadata", () => videoEl.play().catch(() => {}));
  videoEl.addEventListener("canplay", () => videoEl.play().catch(() => {}));
  videoEl.play().catch(() => {});
  return videoEl;
}

function getVrEyeAspect(videoEl = vrLeftVideo, stereoSbs = vrStereoSbs) {
  if (stereoSbs && XR_STEREO_EYE_ASPECT) {
    return XR_STEREO_EYE_ASPECT;
  }

  if (!videoEl || !videoEl.videoWidth || !videoEl.videoHeight) {
    return DEFAULT_VR_EYE_ASPECT;
  }

  const sourceAspect = videoEl.videoWidth / videoEl.videoHeight;
  return stereoSbs ? sourceAspect / 2 : sourceAspect;
}

function updateVrEyeLayout() {
  const vrWrap = document.getElementById("vr-sbs-wrap");
  if (!vrWrap) return;

  vrEyeAspect = getVrEyeAspect();

  const eyeWidth = Math.max(1, window.innerWidth / 2);
  const eyeHeight = Math.max(1, window.innerHeight);
  const eyeViewportAspect = eyeWidth / eyeHeight;
  const frameWidth = eyeViewportAspect > vrEyeAspect ? eyeHeight * vrEyeAspect : eyeWidth;
  const frameHeight = eyeViewportAspect > vrEyeAspect ? eyeHeight : eyeWidth / vrEyeAspect;

  vrWrap.style.setProperty("--vr-eye-aspect", String(vrEyeAspect));
  vrWrap.style.setProperty("--vr-frame-width", `${frameWidth}px`);
  vrWrap.style.setProperty("--vr-frame-height", `${frameHeight}px`);
}

function configureVrVideoElement(videoEl) {
  videoEl.autoplay = true;
  videoEl.playsInline = true;
  videoEl.setAttribute("playsinline", "");
  videoEl.setAttribute("webkit-playsinline", "");
  videoEl.muted = true;
  videoEl.className = "vr-eye-video";
  videoEl.addEventListener("loadedmetadata", updateVrEyeLayout);
  videoEl.addEventListener("canplay", () => videoEl.play().catch(() => {}));
}

function ensureXrVideoHost() {
  if (xrVideoHost) return xrVideoHost;
  xrVideoHost = document.createElement("div");
  xrVideoHost.id = "webxr-video-host";
  Object.assign(xrVideoHost.style, {
    position: "fixed",
    left: "0",
    top: "0",
    width: "320px",
    height: "180px",
    overflow: "hidden",
    opacity: "1",
    pointerEvents: "none",
    zIndex: "9998"
  });
  document.body.appendChild(xrVideoHost);
  return xrVideoHost;
}

function attachHiddenXrVideo(videoEl) {
  if (!videoEl) return;
  const host = ensureXrVideoHost();
  Object.assign(videoEl.style, {
    width: "320px",
    height: "180px",
    objectFit: "contain",
    opacity: "1",
    pointerEvents: "none"
  });
  if (!host.contains(videoEl)) host.appendChild(videoEl);
  videoEl.play().catch(() => {});
}

async function waitForVrVideoReady(timeoutMs = 10000) {
  const started = performance.now();
  while (performance.now() - started < timeoutMs) {
    if (
      vrLeftVideo &&
      vrLeftVideo.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA &&
      vrLeftVideo.videoWidth > 0 &&
      vrLeftVideo.videoHeight > 0
    ) {
      return true;
    }
    if (vrLeftVideo) vrLeftVideo.play().catch(() => {});
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  console.warn("VR-Video hatte vor WebXR-Start noch kein Frame.");
  return false;
}

async function createWebXrRenderer(session) {
  const THREE = await loadThreeModule();
  const canvas = document.createElement("canvas");
  canvas.id = "webxr-vr-canvas";
  Object.assign(canvas.style, {
    position: "fixed",
    top: "0",
    left: "0",
    width: "100vw",
    height: "100vh",
    zIndex: "9999",
    background: "black"
  });
  document.body.appendChild(canvas);

  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    alpha: false
  });
  renderer.xr.enabled = true;
  if (renderer.xr.setReferenceSpaceType) {
    renderer.xr.setReferenceSpaceType("local");
  }
  if (renderer.xr.setFramebufferScaleFactor) {
    renderer.xr.setFramebufferScaleFactor(XR_FRAMEBUFFER_SCALE);
  }
  renderer.setClearColor(0x000000, 1);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 3));
  renderer.setSize(window.innerWidth, window.innerHeight, false);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(70, window.innerWidth / Math.max(window.innerHeight, 1), 0.01, 100);
  const placeholderData = new Uint8Array([
    0, 120, 255, 255,
    255, 255, 255, 255,
    255, 255, 255, 255,
    0, 220, 120, 255
  ]);
  const placeholderTexture = new THREE.DataTexture(placeholderData, 2, 2, THREE.RGBAFormat);
  placeholderTexture.needsUpdate = true;

  const material = createStereoVideoShaderMaterial(THREE, placeholderTexture);
  const geometry = new THREE.PlaneGeometry(1, 1, 1, 1);
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.z = -3;
  scene.add(mesh);

  const eyeProbe = new THREE.Vector3();
  const leftProbe = new THREE.Vector3();
  const rightProbe = new THREE.Vector3();

  mesh.onBeforeRender = (activeRenderer, activeScene, activeCamera) => {
    material.uniforms.isVR.value = activeRenderer.xr.isPresenting;
    if (!activeRenderer.xr.isPresenting) {
      material.uniforms.eyeIndex.value = 0.0;
      return;
    }

    const xrCamera = activeRenderer.xr.getCamera(camera);
    const eyeCameras = xrCamera?.cameras || [];
    if (eyeCameras.length >= 2) {
      if (activeCamera === eyeCameras[1]) {
        material.uniforms.eyeIndex.value = 1.0;
        return;
      }
      if (activeCamera === eyeCameras[0]) {
        material.uniforms.eyeIndex.value = 0.0;
        return;
      }

      activeCamera.getWorldPosition(eyeProbe);
      eyeCameras[0].getWorldPosition(leftProbe);
      eyeCameras[1].getWorldPosition(rightProbe);
      material.uniforms.eyeIndex.value =
        eyeProbe.distanceToSquared(rightProbe) < eyeProbe.distanceToSquared(leftProbe) ? 1.0 : 0.0;
    }
  };

  const onResize = () => {
    camera.aspect = window.innerWidth / Math.max(window.innerHeight, 1);
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight, false);
    updateWebXrPlaneLayout();
  };
  window.addEventListener("resize", onResize);
  renderer.xr.addEventListener("sessionstart", handleWebXrSessionStarted);
  renderer.xr.addEventListener("sessionend", handleWebXrSessionEnded);

  return {
    session,
    THREE,
    canvas,
    renderer,
    scene,
    camera,
    mesh,
    geometry,
    material,
    videoTexture: null,
    placeholderTexture,
    onResize,
    stereoSbs: false,
    videoReady: false,
    startedAt: performance.now(),
    firstVideoFrameAt: 0
  };
}

async function startWebXrSession() {
  if (!navigator.xr || !navigator.xr.requestSession) {
    showFeedback("WebXR-VR ist nicht verfügbar. Side-by-Side wird genutzt.", "error");
    return false;
  }

  try {
    xrSession = await navigator.xr.requestSession("immersive-vr", {
      optionalFeatures: ["local-floor", "hand-tracking"]
    });
    xrState = await createWebXrRenderer(xrSession);
    await xrState.renderer.xr.setSession(xrSession);
    document.addEventListener("keydown", handlePresentationExitKey);
    xrState.canvas.addEventListener("dblclick", exitPresentationMode);
    statusTxt.textContent = "👓 WebXR-VR aktiv";
    return true;
  } catch (error) {
    const failedSession = xrSession;
    console.warn("WebXR konnte nicht gestartet werden:", error);
    if (statusTxt) {
      statusTxt.textContent = `⚠️ WebXR-Fehler: ${error?.name || "unbekannt"}`;
    }
    cleanupWebXrRenderer();
    if (failedSession) {
      try {
        await failedSession.end();
      } catch {}
    }
    showFeedback("WebXR konnte nicht gestartet werden. Side-by-Side wird genutzt.", "error");
    return false;
  }
}

function startWebXrRenderLoop() {
  if (!xrSession || !xrState || xrRenderLoopStarted) return;
  xrRenderLoopStarted = true;
  xrTextureErrorLogged = false;
  updateWebXrPlaneLayout();
  xrState.renderer.setAnimationLoop(renderWebXrFrame);
}

function setWebXrVideoElement(videoEl, stereoSbs = true) {
  if (!xrState || !videoEl) return;

  const { THREE, material } = xrState;
  if (xrState.videoTexture) {
    xrState.videoTexture.dispose();
  }

  const texture = new THREE.VideoTexture(videoEl);
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.wrapS = THREE.ClampToEdgeWrapping;
  texture.wrapT = THREE.ClampToEdgeWrapping;
  texture.generateMipmaps = false;
  if ("SRGBColorSpace" in THREE) {
    texture.colorSpace = THREE.SRGBColorSpace;
  }

  xrState.videoTexture = texture;
  xrState.stereoSbs = stereoSbs;
  material.uniforms.map.value = texture;
  material.uniforms.isVR.value = true;
  updateWebXrPlaneLayout();
}

function updateWebXrPlaneLayout() {
  if (!xrState) return;

  const videoEl = vrLeftVideo || video;
  const stereoSbs = xrState.stereoSbs;
  const layout = getAdaptiveXrPlane(videoEl, stereoSbs);
  const aspect = getEyeVideoAspect(videoEl, stereoSbs);
  const width = layout.width;
  const height = width / Math.max(aspect || DEFAULT_VR_EYE_ASPECT, 0.0001);

  xrState.mesh.position.set(0, XR_PLANE_HEIGHT, -layout.distance);
  xrState.mesh.scale.set(width, height, 1);
  xrState.material.uniforms.eyeAspect.value = aspect || DEFAULT_VR_EYE_ASPECT;
  xrState.material.uniforms.planeAspect.value = width / Math.max(height, 0.0001);

  if (videoEl?.videoWidth && videoEl?.videoHeight) {
    xrState.material.uniforms.videoResolution.value.set(videoEl.videoWidth, videoEl.videoHeight);
  }
}

function renderWebXrFrame() {
  if (!xrSession || !xrState) return;

  const videoEl = vrLeftVideo;
  const hasVideoFrame = Boolean(
    videoEl &&
    videoEl.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA &&
    videoEl.videoWidth > 0 &&
    videoEl.videoHeight > 0
  );

  if (hasVideoFrame && !xrState.videoTexture) {
    setWebXrVideoElement(videoEl, vrStereoSbs);
  }

  if (hasVideoFrame) {
    xrState.videoReady = true;
    updateWebXrPlaneLayout();
  }

  if (xrState.videoReady && !xrState.firstVideoFrameAt) {
    xrState.firstVideoFrameAt = performance.now();
    if (statusTxt) statusTxt.textContent = "👓 WebXR-Video sichtbar";
  }

  if (!xrState.videoReady && performance.now() - xrState.startedAt > XR_VIDEO_TIMEOUT_MS) {
    console.warn("WebXR beendet: Es konnte kein Videoframe als XR-Textur geladen werden.");
    showFeedback("⚠️ WebXR zeigt kein Video. Zurück zum Normal-Modus.", "error");
    endWebXrSession();
    return;
  }

  xrState.renderer.render(xrState.scene, xrState.camera);
}

async function handleWebXrSessionStarted() {
  vrMode = true;
  if (xrState?.material) {
    xrState.material.uniforms.isVR.value = true;
  }
  await toggleSecondCamera(true);
  window.dispatchEvent(new CustomEvent("sessionstart", { detail: { xrSession } }));
}

function cleanupWebXrRenderer() {
  document.removeEventListener("keydown", handlePresentationExitKey);
  if (xrState) {
    if (xrState.renderer) {
      xrState.renderer.setAnimationLoop(null);
      xrState.renderer.xr.removeEventListener("sessionstart", handleWebXrSessionStarted);
      xrState.renderer.xr.removeEventListener("sessionend", handleWebXrSessionEnded);
    }
    if (xrState.onResize) {
      window.removeEventListener("resize", xrState.onResize);
    }
    if (xrState.videoTexture) xrState.videoTexture.dispose();
    if (xrState.placeholderTexture) xrState.placeholderTexture.dispose();
    if (xrState.geometry) xrState.geometry.dispose();
    if (xrState.material) xrState.material.dispose();
    if (xrState.renderer) xrState.renderer.dispose();
    if (xrState.canvas) xrState.canvas.remove();
  }
  if (xrVideoHost) {
    xrVideoHost.remove();
    xrVideoHost = null;
  }
  xrSession = null;
  xrState = null;
  xrRenderLoopStarted = false;
  xrTextureErrorLogged = false;
}

function handlePresentationExitKey(event) {
  if (event.key === "Escape" || event.key === "Esc" || event.key.toLowerCase() === "x") {
    event.preventDefault();
    exitPresentationMode();
  }
}

async function exitPresentationMode() {
  if (xrSession) {
    const wasVr = vrMode;
    vrMode = false;
    await exitVrUi();
    if (wasVr) {
      await switchStreamMode(false);
    }
    return;
  }

  exitBrowserFullscreen();
}

function getBrowserFullscreenElement() {
  return document.fullscreenElement || document.webkitFullscreenElement || null;
}

function setFullscreenActive(active) {
  document.body.classList.toggle("fullscreen-active", Boolean(active));
}

function setupFullscreenControls() {
  document.addEventListener("fullscreenchange", () => {
    setFullscreenActive(Boolean(getBrowserFullscreenElement()));
  });
  document.addEventListener("webkitfullscreenchange", () => {
    setFullscreenActive(Boolean(getBrowserFullscreenElement()));
  });
  video?.addEventListener("webkitbeginfullscreen", () => setFullscreenActive(true));
  video?.addEventListener("webkitendfullscreen", () => setFullscreenActive(false));
}

function exitBrowserFullscreen() {
  const exitPromise = document.exitFullscreen?.() || document.webkitExitFullscreen?.();
  if (exitPromise?.catch) exitPromise.catch(() => {});

  if (video?.webkitDisplayingFullscreen && video.webkitExitFullscreen) {
    video.webkitExitFullscreen();
  }

  setFullscreenActive(false);
}

async function endWebXrSession() {
  const session = xrSession;
  if (!session) {
    cleanupWebXrRenderer();
    return;
  }
  try {
    await session.end();
  } catch {
    cleanupWebXrRenderer();
  }
}

function handleWebXrSessionEnded() {
  const shouldReturnToNormal = vrMode;
  vrMode = false;
  void toggleSecondCamera(false);
  if (xrState?.material) {
    xrState.material.uniforms.isVR.value = false;
  }
  window.dispatchEvent(new CustomEvent("sessionend", { detail: { xrSession } }));
  cleanupWebXrRenderer();
  if (shouldReturnToNormal) {
    returnToNormalAfterXrEnd();
  }
}

async function returnToNormalAfterXrEnd() {
  restoreNormalUi();
  for (let i = 0; connecting && i < 30; i++) {
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  await switchStreamMode(false);
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
  vrStreams.forEach(s => s.getTracks().forEach(t => t.stop()));
  if (pingTimer) {
    clearInterval(pingTimer);
    pingTimer = null;
  }
  resetStreams();
}

function ensureVrWrap() {
  let vrWrap = document.getElementById("vr-sbs-wrap");
  if (vrWrap) return vrWrap;

  vrWrap = document.createElement("div");
  vrWrap.id = "vr-sbs-wrap";

  vrLeftVideo = document.createElement("video");
  vrRightVideo = document.createElement("video");

  [vrLeftVideo, vrRightVideo].forEach(configureVrVideoElement);

  const leftEye = document.createElement("div");
  const rightEye = document.createElement("div");
  const leftFrame = document.createElement("div");
  const rightFrame = document.createElement("div");

  leftEye.className = "vr-eye vr-eye-left";
  rightEye.className = "vr-eye vr-eye-right";
  leftFrame.className = "vr-eye-frame";
  rightFrame.className = "vr-eye-frame";

  leftFrame.appendChild(vrLeftVideo);
  rightFrame.appendChild(vrRightVideo);
  leftEye.appendChild(leftFrame);
  rightEye.appendChild(rightFrame);
  vrWrap.appendChild(leftEye);
  vrWrap.appendChild(rightEye);

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
  updateVrEyeLayout();
  return vrWrap;
}

function attachVrStreams(leftStream, rightStream = null) {
  vrStereoSbs = !rightStream;
  if (xrSession) {
    vrLeftVideo = createVrVideo(leftStream);
    vrRightVideo = rightStream ? createVrVideo(rightStream) : null;
    attachHiddenXrVideo(vrLeftVideo);
    attachHiddenXrVideo(vrRightVideo);
    if (xrState) xrState.stereoSbs = vrStereoSbs;
    setWebXrVideoElement(vrLeftVideo, vrStereoSbs);
    monitorFPS(vrLeftVideo);
    vrLeftVideo.play().catch(() => {});
    vrRightVideo?.play().catch(() => {});
    statusTxt.textContent = "👓 WebXR-VR verbunden";
    return;
  }

  const vrWrap = ensureVrWrap();
  vrWrap.classList.toggle("stereo-sbs", vrStereoSbs);
  vrWrap.classList.toggle("dual-stream", !vrStereoSbs);
  vrWrap.style.display = "flex";
  if (vrLeftVideo) vrLeftVideo.srcObject = leftStream;
  if (vrRightVideo) vrRightVideo.srcObject = vrStereoSbs ? leftStream : rightStream;
  if (vrStereoSbs) {
    if (vrRightVideo) vrRightVideo.style.display = "";
  } else {
    if (vrRightVideo) vrRightVideo.style.display = "";
  }
  [vrLeftVideo, vrRightVideo].forEach(v => v?.play().catch(() => {}));
  updateVrEyeLayout();
  window.addEventListener("resize", updateVrEyeLayout);
  if (vrWrap.requestFullscreen) vrWrap.requestFullscreen().catch(() => {});
  if (vrLeftVideo) monitorFPS(vrLeftVideo);
}

function attachXrMonoStream(stream) {
  vrStereoSbs = false;
  vrLeftVideo = createVrVideo(stream);
  vrRightVideo = createVrVideo(stream);
  attachHiddenXrVideo(vrLeftVideo);
  attachHiddenXrVideo(vrRightVideo);
  if (xrState) xrState.stereoSbs = false;
  setWebXrVideoElement(vrLeftVideo, false);
  monitorFPS(vrLeftVideo);
  vrLeftVideo.play().catch(() => {});
  vrRightVideo.play().catch(() => {});
  statusTxt.textContent = "👓 WebXR-Mono verbunden";
}

// Verbindung zu WebRTC-Server aufbauen
async function start({ vr = false, xrMonoStream = false } = {}) {
  if (connecting) return false;
  connecting = true;
  statusTxt.textContent = "🔄 Verbinde...";
  resetStreams();
  try {
    pc = new RTCPeerConnection({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] });
    const recvCount = 1;
    for (let i = 0; i < recvCount; i++) {
      pc.addTransceiver("video", { direction: "recvonly" });
    }

    pc.ontrack = (event) => {
      const stream = new MediaStream([event.track]);
      if (xrMonoStream) {
        vrStreams.push(stream);
        attachXrMonoStream(stream);
        return;
      }

      if (!vr) {
        currentStream = stream;
        video.srcObject = currentStream;
        monitorFPS(video);
        createOverlay();
        return;
      }
      vrStreams.push(stream);
      if (vrStreams.length >= 1) {
        attachVrStreams(vrStreams[0]);
      }
    };

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    const offerPayload = {
      sdp: pc.localDescription.sdp,
      type: pc.localDescription.type,
      vr,
      clientProfile: getClientProfile(vr)
    };
    const res = await fetch("/offer", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify(offerPayload)
    });

    if (!res.ok) {
      statusTxt.textContent = "❌ Zugriff verweigert!";
      await stopConnection();
      return false;
    }

    const answer = await res.json();
    await pc.setRemoteDescription(answer);
    statusTxt.textContent = vr ? "👓 VR verbunden!" : "✅ Verbunden!";
    monitorPing(pc);
    return true;
  } catch {
    statusTxt.textContent = "⚠️ Stream-Fehler!";
    await stopConnection();
    return false;
  } finally {
    connecting = false;
  }
}

// Overlay mit Buttons (Neu laden, VR etc.)
function createOverlay() {
  if (document.querySelector(".control-overlay")) return; // Nur einmal erzeugen
  const overlay = document.createElement("div");
  overlay.className = "control-overlay";
  overlay.innerHTML = `
    <button class="overlay-btn" title="Neu verbinden" onclick="restartStream()">🔄</button>
    <button class="overlay-btn" title="Enter VR" onclick="enterVisionProMode()">👓</button>
    ${isAdmin ? `<button class="overlay-btn" title="Benutzerverwaltung" onclick="openAdminPanel()">🛠️</button>` : ""}
    <button class="overlay-btn" title="Abmelden" onclick="logoutUser()">🚪</button>
  `;
  document.querySelector(".status-bar").appendChild(overlay);
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
    try {
      const stats = await pc.getStats();
      let rtt = null;
      stats.forEach(report => {
        if (report.type === "candidate-pair" && report.state === "succeeded" && report.currentRoundTripTime)
          rtt = (report.currentRoundTripTime * 1000).toFixed(1);
      });
      if (rtt) updateHud(`📡 ${rtt} ms`);
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
   ✅ VR-VOLLANSICHT (WebXR mit Side-by-Side-Fallback)
===================================================== */

async function enterVrUi() {
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

  body.classList.add("vr-active");
  statusTxt.textContent = "👓 Starte WebXR-VR...";

  const webXrStarted = await startWebXrSession();
  if (!webXrStarted) {
    if (vrStreams.length > 0) {
      attachVrStreams(vrStreams[0], vrStreams[1] || null);
    } else {
      const vrWrap = ensureVrWrap();
      vrWrap.style.display = "flex";
      if (vrWrap.requestFullscreen) vrWrap.requestFullscreen().catch(() => {});
    }
    statusTxt.textContent = "👓 Side-by-Side-VR aktiv";
    return false;
  } else {
    attachHiddenXrVideo(vrLeftVideo);
    attachHiddenXrVideo(vrRightVideo);
    if (xrState) xrState.stereoSbs = vrStereoSbs;
    return true;
  }
}

function restoreNormalUi() {
  const body = document.body;
  const header = document.querySelector("header");
  const footer = document.querySelector("footer");
  const streamCard = document.getElementById("stream-card");
  const overlay = document.querySelector(".control-overlay");
  const hudEl = document.querySelector(".hud");

  body.classList.remove("vr-active");
  window.removeEventListener("resize", updateVrEyeLayout);
  const wrap = document.getElementById("vr-sbs-wrap");
  if (wrap) wrap.remove();
  vrLeftVideo = null;
  vrRightVideo = null;

  if (header) header.style.display = "";
  if (footer) footer.style.display = "";
  if (streamCard) streamCard.style.display = "block";
  if (overlay) overlay.style.display = "";
  if (hudEl) hudEl.style.display = "";

  const exitFullscreenPromise = document.exitFullscreen?.();
  if (exitFullscreenPromise?.catch) exitFullscreenPromise.catch(() => {});
  statusTxt.textContent = "🖥 Normal-Modus";
}

async function exitVrUi() {
  await endWebXrSession();
  restoreNormalUi();
}

async function switchStreamMode(vr) {
  if (connecting) return false;
  await stopConnection();
  return await start({ vr });
}

async function switchXrMonoStreamMode() {
  if (connecting) return false;
  await stopConnection();
  return await start({ vr: false, xrMonoStream: true });
}

// Schaltet zwischen normaler und VR-Ansicht
async function toggleView() {
  if (connecting) return;
  const targetVr = !vrMode;
  vrMode = targetVr;
  if (targetVr) {
    const webXrStarted = await enterVrUi();
    vrPreparingWebXr = webXrStarted;
    const streamStarted = XR_MONO
      ? await switchXrMonoStreamMode()
      : await switchStreamMode(true);
    if (webXrStarted && streamStarted) {
      await waitForVrVideoReady();
      startWebXrRenderLoop();
    }
    vrPreparingWebXr = false;
  } else {
    vrPreparingWebXr = false;
    await exitVrUi();
    await switchStreamMode(false);
  }
}

/* =====================================================
   🔧 HILFSFUNKTIONEN
===================================================== */

// Vollbildmodus aktivieren
function enterVisionProMode() {
  toggleView();
}

function toggleFullscreen() {
  if (xrSession) {
    exitPresentationMode();
    return;
  }

  if (getBrowserFullscreenElement() || video?.webkitDisplayingFullscreen) {
    exitBrowserFullscreen();
    return;
  }

  const target = document.getElementById("vr-sbs-wrap") || document.getElementById("player-wrap") || video;
  if (!target) return;
  const requestPromise = target.requestFullscreen?.() || target.webkitRequestFullscreen?.();
  if (requestPromise?.catch) {
    requestPromise.catch(() => {
      if (video?.webkitEnterFullscreen) video.webkitEnterFullscreen();
    });
  } else if (video?.webkitEnterFullscreen && !getBrowserFullscreenElement()) {
    if (video?.webkitEnterFullscreen) video.webkitEnterFullscreen();
  }
  setFullscreenActive(true);
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
