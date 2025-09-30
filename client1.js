const video = document.getElementById("video");
const status = document.getElementById("status");
const hud = document.querySelector(".hud");

const pc = new RTCPeerConnection();

pc.addTransceiver("video", { direction: "recvonly" });

pc.ontrack = (event) => {
    console.log("📡 Video-Track empfangen");
    video.srcObject = event.streams[0];

    // FPS Monitoring starten
    monitorFPS(video);
};

async function start() {
    try {
        status.innerText = "🔄 Sende Offer...";

        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        const response = await fetch("/offer", {
            method: "POST",
            body: JSON.stringify(pc.localDescription),
            headers: { "Content-Type": "application/json" }
        });

        const answer = await response.json();
        await pc.setRemoteDescription(answer);

        status.innerText = "✅ Verbunden!";

        // Ping Monitoring starten
        monitorPing(pc);

    } catch (err) {
        status.innerText = "❌ Fehler beim Offer!";
        console.error(err);
    }
}

start();

// ----------------------
// 🔹 Ping messen (über candidate-pair)
// ----------------------
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

        if (rtt !== null) {
            updateHud(`📡 Ping: ${rtt} ms`);
        }
    }, 1000);
}

// ----------------------
// 🔹 FPS messen (über VideoFrameCallback)
// ----------------------
function monitorFPS(video) {
    let lastTime = performance.now();
    let frames = 0;

    if ("requestVideoFrameCallback" in HTMLVideoElement.prototype) {
        const callback = (now, metadata) => {
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

// ----------------------
// 🔹 HUD aktualisieren
// ----------------------
let hudPing = "📡 Ping: -- ms";
let hudFps = "🎥 -- FPS";

function updateHud(text, isFps = false) {
    if (isFps) hudFps = text;
    else hudPing = text;

    hud.innerText = `${hudPing} | ${hudFps}`;
}
