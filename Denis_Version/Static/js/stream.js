/**
 * ============================================================================
 * Stream JavaScript für User-Dashboard
 * Datei: static/js/stream.js
 * Version: 1.0
 * Datum: 30.09.2025
 *
 * Funktionen:
 * - MJPEG-Stream-Verwaltung
 * - WebRTC-Stream-Verwaltung
 * - GPS-Daten aktualisieren
 * - Fahrtzeit-Anzeige
 * ============================================================================
 */

// ============================================================================
// GLOBALE VARIABLEN
// ============================================================================

let webrtcConnection = null;
let gpsUpdateTimer = null;
let trackingUpdateTimer = null;

// ============================================================================
// STREAM-VERWALTUNG
// ============================================================================

/**
 * Initialisiert den Video-Stream (MJPEG oder WebRTC).
 */
function initializeStream() {
    const videoElement = document.getElementById('videoElement');
    const streamImage = document.getElementById('streamImage');

    if (videoElement) {
        // WebRTC-Stream
        startWebRTCStream();
    } else if (streamImage) {
        // MJPEG-Stream (keine weitere Initialisierung nötig)
        console.log('MJPEG-Stream aktiv');

        // Fehlerbehandlung für MJPEG
        streamImage.onerror = function() {
            console.error('Fehler beim Laden des MJPEG-Streams');
            this.src = 'image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480"><rect fill="%23333" width="640" height="480"/><text fill="white" x="50%" y="50%" text-anchor="middle">Stream nicht verfügbar</text></svg>';
        };
    }
}

/**
 * Startet WebRTC-Stream.
 */
async function startWebRTCStream() {
    try {
        webrtcConnection = new RTCPeerConnection({
            iceServers: [
                {urls: 'stun:stun.l.google.com:19302'},
                {urls: 'stun:stun1.l.google.com:19302'}
            ]
        });

        // Event-Handler für Stream
        webrtcConnection.ontrack = (event) => {
            const videoElement = document.getElementById('videoElement');
            videoElement.srcObject = event.streams[0];
            console.log('WebRTC-Stream empfangen');
        };

        // Event-Handler für Verbindungsstatus
        webrtcConnection.onconnectionstatechange = () => {
            console.log('WebRTC Verbindungsstatus:', webrtcConnection.connectionState);

            if (webrtcConnection.connectionState === 'failed' ||
                webrtcConnection.connectionState === 'disconnected') {
                console.error('WebRTC-Verbindung verloren, versuche Reconnect...');
                setTimeout(startWebRTCStream, 5000); // Reconnect nach 5 Sekunden
            }
        };

        // Füge Transceiver für Video hinzu
        webrtcConnection.addTransceiver('video', {direction: 'recvonly'});

        // Erstelle Offer
        const offer = await webrtcConnection.createOffer();
        await webrtcConnection.setLocalDescription(offer);

        // Sende Offer an Server
        const response = await fetch('/webrtc/offer', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                sdp: offer.sdp,
                type: offer.type
            })
        });

        if (!response.ok) {
            throw new Error('Server-Fehler beim WebRTC-Signaling');
        }

        const answer = await response.json();

        // Setze Remote Description
        await webrtcConnection.setRemoteDescription(
            new RTCSessionDescription(answer)
        );

        console.log('WebRTC-Verbindung hergestellt');

    } catch (error) {
        console.error('WebRTC-Fehler:', error);
        alert('Fehler beim Starten des Video-Streams. Bitte Seite neu laden.');
    }
}

/**
 * Stoppt WebRTC-Stream und benachrichtigt Server.
 */
async function stopWebRTCStream() {
    if (webrtcConnection) {
        webrtcConnection.close();
        webrtcConnection = null;

        try {
            await fetch('/webrtc/close', {method: 'POST'});
        } catch (error) {
            console.error('Fehler beim Schließen der WebRTC-Verbindung:', error);
        }
    }
}

// ============================================================================
// GPS-FUNKTIONEN
// ============================================================================

/**
 * Startet automatische GPS-Daten-Aktualisierung.
 */
function startGPSUpdates() {
    // Aktualisiere GPS-Daten alle 5 Sekunden
    gpsUpdateTimer = setInterval(updateGPSData, 5000);

    // Erste Aktualisierung sofort
    updateGPSData();
}

/**
 * Aktualisiert GPS-Daten vom Server.
 */
async function updateGPSData() {
    try {
        const response = await fetch('/api/gps/position');

        if (response.ok) {
            const data = await response.json();

            // Aktualisiere Karte wenn vorhanden
            if (typeof updateMapPosition === 'function') {
                updateMapPosition(data.latitude, data.longitude);
            }

        }
    } catch (error) {
        console.error('Fehler beim Aktualisieren der GPS-Daten:', error);
    }
}

/**
 * Stoppt GPS-Daten-Aktualisierung.
 */
function stopGPSUpdates() {
    if (gpsUpdateTimer) {
        clearInterval(gpsUpdateTimer);
        gpsUpdateTimer = null;
    }
}

// ============================================================================
// FAHRTZEIT-AKTUALISIERUNG
// ============================================================================

/**
 * Startet automatische Fahrtzeit-Aktualisierung.
 */
function startTrackingUpdates() {
    // Aktualisiere Tracking-Stats alle 2 Sekunden
    trackingUpdateTimer = setInterval(updateTrackingStats, 2000);
}

/**
 * Aktualisiert Tracking-Statistiken.
 */
async function updateTrackingStats() {
    try {
        const response = await fetch('/api/gps/track');

        if (response.ok) {
            const data = await response.json();

            if (data.tracking && data.stats) {
                // Aktualisiere UI-Elemente
                const durationEl = document.getElementById('trackingDuration');
                const distanceEl = document.getElementById('trackingDistance');
                const pointsEl = document.getElementById('trackingPoints');

                if (durationEl) durationEl.textContent = data.stats.duration_formatted;
                if (distanceEl) distanceEl.textContent = data.stats.total_distance_km + ' km';
                if (pointsEl) pointsEl.textContent = data.stats.point_count;

                // Aktualisiere Route auf Karte
                if (data.points && typeof updateRoute === 'function') {
                    updateRoute(data.points);
                }
            }
        }
    } catch (error) {
        console.error('Fehler beim Aktualisieren der Tracking-Daten:', error);
    }
}

/**
 * Stoppt Tracking-Aktualisierung.
 */
function stopTrackingUpdates() {
    if (trackingUpdateTimer) {
        clearInterval(trackingUpdateTimer);
        trackingUpdateTimer = null;
    }
}

// ============================================================================
// INITIALISIERUNG
// ============================================================================

/**
 * Initialisiert alle Funktionen beim Laden der Seite.
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('User-Dashboard wird initialisiert...');

    // Initialisiere Stream
    initializeStream();

    // Starte GPS-Updates wenn GPS aktiviert
    if (document.getElementById('map')) {
        startGPSUpdates();
        startTrackingUpdates();
    }

    console.log('User-Dashboard initialisiert');
});

// ============================================================================
// CLEANUP
// ============================================================================

/**
 * Cleanup beim Verlassen der Seite.
 */
window.addEventListener('beforeunload', function() {
    // Stoppe WebRTC-Stream
    stopWebRTCStream();

    // Stoppe Timer
    stopGPSUpdates();
    stopTrackingUpdates();

    console.log('Cleanup abgeschlossen');
});

/**
 * Cleanup bei Sichtbarkeitswechsel (Tab wechseln).
 */
document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        // Tab nicht mehr sichtbar - pausiere Updates
        stopGPSUpdates();
        stopTrackingUpdates();
    } else {
        // Tab wieder sichtbar - reaktiviere Updates
        if (document.getElementById('map')) {
            startGPSUpdates();
            startTrackingUpdates();
        }
    }
});
