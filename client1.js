let authPassword = null;

// -------------------------
// 🔑 Login
// -------------------------
async function login() {
    const pw = document.getElementById("password").value;

    const res = await fetch("/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: pw })
    });

    if (res.status === 200) {
        authPassword = pw;

        // Login Card ausblenden, Stream Card einblenden
        document.getElementById("login-card").style.display = "none";
        document.getElementById("stream-card").style.display = "block";

        start();
    } else {
        document.getElementById("login-status").innerText = "❌ Falsches Passwort!";
    }
}

// -------------------------
// 🔹 WebRTC
// -------------------------
const video = document.getElementById("video");
const status = document.getElementById("status");
const hud = document.querySelector(".hud");

const pc = new RTCPeerConnection();
pc.addTransceiver("video", { direction: "recvonly" });

pc.ontrack = (event) => {
    video.srcObject = event.streams[0];
    monitorFPS(video);
};

async function start() {
    try {
        status.innerText = "🔄 Verbinde...";

        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        const response = await fetch("/offer", {
            method: "POST",
            body: JSON.stringify(pc.localDescription),
            headers: {
                "Content-Type": "application/json",
                "Authorization": authPassword
            }
        });

        if (!response.ok) {
            status.innerText = "❌ Zugriff verweigert!";
            return;
        }

        const answer = await response.json();
        await pc.setRemoteDescription(answer);

        status.innerText = "✅ Verbunden!";
        monitorPing(pc);

    } catch (err) {
        status.innerText = "❌ Fehler beim Offer!";
        console.error(err);
    }
}

// -------------------------
// 📡 Ping Monitoring
// -------------------------
async function monitorPing(pc) {
    setInterval(async () => {
        const stats = await pc.getStats();
        let rtt = null;

        stats.forEach(report => {
            if (report.type === "candidate-pair" && report.state === "succeeded") {
                if (report.currentRoundTripTime) {
                    rtt = (report.currentRoundTripTime * 1000).toFixed(1);
                }
            }
        });

        if (rtt !== null) updateHud(`📡 Ping: ${rtt} ms`);
    }, 1000);
}

// -------------------------
// 🎥 FPS Monitoring
// -------------------------
function monitorFPS(video) {
    let lastTime = performance.now();
    let frames = 0;

    if ("requestVideoFrameCallback" in HTMLVideoElement.prototype) {
        const callback = (now) => {
            frames++;
            const diff = (now - lastTime) / 1000;
            if (diff >= 1) {
                const fps = (frames / diff).toFixed(0);
                updateHud(`🎥 ${fps} FPS`, true);
                frames = 0;
                lastTime = now;
            }
            video.requestVideoFrameCallback(callback);
        };
        video.requestVideoFrameCallback(callback);
    }
}

// -------------------------
// 🎛 HUD aktualisieren
// -------------------------
let hudPing = "📡 Ping: -- ms";
let hudFps = "🎥 -- FPS";

function updateHud(text, isFps = false) {
    if (isFps) hudFps = text;
    else hudPing = text;
    hud.innerText = `${hudPing} | ${hudFps}`;
}

// -------------------------
// 🛠 Utils
// -------------------------
function toggleFullscreen() {
    if (video.requestFullscreen) video.requestFullscreen();
    else if (video.webkitRequestFullscreen) video.webkitRequestFullscreen();
}

function restartStream() { location.reload(); }

// -------------------------
// 👁️ Passwort anzeigen/ausblenden
// + Enter-Taste zum Login
// -------------------------
document.addEventListener("DOMContentLoaded", () => {
    const pwInput = document.getElementById("password");
    const toggle = document.getElementById("toggle-password");

    toggle.addEventListener("click", () => {
        if (pwInput.type === "password") {
            pwInput.type = "text";
            toggle.innerText = "🙈";
        } else {
            pwInput.type = "password";
            toggle.innerText = "👁️";
        }
    });

    pwInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
            login();
        }
    });
});