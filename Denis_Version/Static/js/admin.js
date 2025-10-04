/**
 * ============================================================================
 * Admin Dashboard JavaScript
 * Datei: static/js/admin.js
 * Version: 1.0
 * Datum: 30.09.2025
 *
 * Funktionen:
 * - Tab-Verwaltung
 * - Aufnahmen-Verwaltung
 * - Benutzer-Verwaltung
 * - Kamera-Einstellungen
 * - System-Steuerung
 * - WebRTC-Stream-Management
 * ============================================================================
 */

// ============================================================================
// GLOBALE VARIABLEN
// ============================================================================

let webrtcPeerConnection = null;
let recordingInterval = null;
let gpsUpdateInterval = null;

// ============================================================================
// TAB-VERWALTUNG
// ============================================================================

/**
 * Wechselt zwischen verschiedenen Tabs im Admin-Dashboard.
 *
 * @param {string} tabName - Name des zu aktivierenden Tabs
 */
function switchTab(tabName) {
    // Entferne 'active' Klasse von allen Tabs
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.remove('active');
    });

    // Verstecke alle Tab-Inhalte
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });

    // Aktiviere ausgewählten Tab
    event.target.classList.add('active');
    document.getElementById('tab-' + tabName).classList.add('active');

    // Lade Daten je nach Tab
    switch(tabName) {
        case 'recordings':
            loadRecordings();
            break;
        case 'users':
            loadUsers();
            break;
        case 'logs':
            loadLogs();
            break;
    }
}

// ============================================================================
// AUFNAHME-VERWALTUNG
// ============================================================================

/**
 * Startet eine Video-Aufnahme.
 */
async function startRecording() {
    const btn = document.getElementById('btnStartRecording');
    const statusDiv = document.getElementById('recordingStatus');

    // Button deaktivieren während Request
    btn.disabled = true;
    statusDiv.innerHTML = '<p style="color: #667eea;">⏳ Starte Aufnahme...</p>';

    try {
        const response = await fetch('/admin/start-recording', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (data.success) {
            // Erfolg - UI aktualisieren
            btn.disabled = true;
            document.getElementById('btnStopRecording').disabled = false;

            statusDiv.innerHTML = `
                <div style="padding: 15px; background: #e8f5e9; border-left: 4px solid #4CAF50; border-radius: 5px;">
                    <p style="color: #2e7d32; margin: 0;">
                        <strong>⏺️ Aufnahme läuft</strong><br>
                        Datei: ${data.filename}
                    </p>
                    <p id="recordingDuration" style="color: #666; margin: 10px 0 0 0;">Dauer: 00:00</p>
                </div>
            `;

            // Starte Timer für Aufnahme-Dauer
            let seconds = 0;
            recordingInterval = setInterval(() => {
                seconds++;
                const minutes = Math.floor(seconds / 60);
                const secs = seconds % 60;
                document.getElementById('recordingDuration').textContent =
                    `Dauer: ${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
            }, 1000);

        } else {
            // Fehler
            statusDiv.innerHTML = `<p style="color: #f44336;">❌ ${data.error}</p>`;
            btn.disabled = false;

            // Zeige Warnung wenn Speicher voll
            if (data.warning) {
                alert(data.warning);
            }
        }

    } catch (error) {
        console.error('Fehler beim Starten der Aufnahme:', error);
        statusDiv.innerHTML = '<p style="color: #f44336;">❌ Verbindungsfehler</p>';
        btn.disabled = false;
    }
}

/**
 * Stoppt die laufende Video-Aufnahme.
 */
async function stopRecording() {
    const btn = document.getElementById('btnStopRecording');
    const statusDiv = document.getElementById('recordingStatus');

    btn.disabled = true;
    statusDiv.innerHTML = '<p style="color: #667eea;">⏳ Stoppe Aufnahme...</p>';

    // Stoppe Timer
    if (recordingInterval) {
        clearInterval(recordingInterval);
        recordingInterval = null;
    }

    try {
        const response = await fetch('/admin/stop-recording', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (data.success) {
            // Erfolg - UI zurücksetzen
            document.getElementById('btnStartRecording').disabled = false;
            btn.disabled = true;

            statusDiv.innerHTML = `
                <div style="padding: 15px; background: #fff3e0; border-left: 4px solid #FF9800; border-radius: 5px;">
                    <p style="color: #e65100; margin: 0;">
                        <strong>✅ Aufnahme beendet</strong>
                    </p>
                    <p style="color: #666; margin: 5px 0 0 0;">
                        Dauer: ${data.stats.duration_formatted}<br>
                        Größe: ${data.stats.file_size_mb} MB
                    </p>
                </div>
            `;

            // Aktualisiere Aufnahmen-Liste
            loadRecordings();

        } else {
            statusDiv.innerHTML = `<p style="color: #f44336;">❌ ${data.error}</p>`;
            btn.disabled = false;
        }

    } catch (error) {
        console.error('Fehler beim Stoppen der Aufnahme:', error);
        statusDiv.innerHTML = '<p style="color: #f44336;">❌ Verbindungsfehler</p>';
        btn.disabled = false;
    }
}

/**
 * Lädt die Liste aller Aufnahmen vom Server.
 */
async function loadRecordings() {
    const tbody = document.getElementById('recordingsBody');
    tbody.innerHTML = '<tr><td colspan="4" style="text-align: center;">⏳ Lade Aufnahmen...</td></tr>';

    try {
        const response = await fetch('/admin/recordings');
        const data = await response.json();

        if (data.recordings && data.recordings.length > 0) {
            tbody.innerHTML = '';

            data.recordings.forEach(recording => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${recording.filename}</td>
                    <td>${recording.size_formatted}</td>
                    <td>${recording.created_formatted}</td>
                    <td>
                        <button class="btn btn-primary" onclick="downloadRecording('${recording.filename}')">
                            ⬇️ Download
                        </button>
                        <button class="btn btn-danger" onclick="deleteRecording('${recording.filename}')">
                            🗑️ Löschen
                        </button>
                    </td>
                `;
                tbody.appendChild(row);
            });

        } else {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center;">Keine Aufnahmen vorhanden</td></tr>';
        }

    } catch (error) {
        console.error('Fehler beim Laden der Aufnahmen:', error);
        tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: #f44336;">❌ Fehler beim Laden</td></tr>';
    }
}

/**
 * Lädt eine Aufnahme herunter.
 *
 * @param {string} filename - Name der herunterzuladenden Datei
 */
function downloadRecording(filename) {
    // Öffne Download-Link in neuem Tab
    window.open(`/admin/download/${filename}`, '_blank');
}

/**
 * Löscht eine Aufnahme nach Bestätigung.
 *
 * @param {string} filename - Name der zu löschenden Datei
 */
async function deleteRecording(filename) {
    // Bestätigungs-Dialog
    if (!confirm(`Möchten Sie die Aufnahme "${filename}" wirklich löschen?\n\nDiese Aktion kann nicht rückgängig gemacht werden.`)) {
        return;
    }

    try {
        const response = await fetch('/admin/delete-recording', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ filename: filename })
        });

        const data = await response.json();

        if (data.success) {
            alert('✅ Aufnahme erfolgreich gelöscht');
            loadRecordings(); // Liste aktualisieren
        } else {
            alert('❌ Fehler: ' + data.error);
        }

    } catch (error) {
        console.error('Fehler beim Löschen der Aufnahme:', error);
        alert('❌ Verbindungsfehler beim Löschen');
    }
}

// ============================================================================
// KAMERA-EINSTELLUNGEN
// ============================================================================

/**
 * Aktualisiert eine Kamera-Einstellung (Helligkeit, Kontrast, Zoom).
 *
 * @param {string} setting - Name der Einstellung
 * @param {number} value - Neuer Wert
 */
async function updateCameraSetting(setting, value) {
    try {
        const response = await fetch('/admin/camera-settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                setting: setting,
                value: parseFloat(value)
            })
        });

        const data = await response.json();

        if (!data.success) {
            console.error('Fehler beim Setzen der Kamera-Einstellung:', data.error);
            alert('❌ Fehler beim Ändern der Einstellung');
        }

    } catch (error) {
        console.error('Fehler beim Setzen der Kamera-Einstellung:', error);
    }
}

// ============================================================================
// BENUTZER-VERWALTUNG
// ============================================================================

/**
 * Lädt die Liste aller Benutzer vom Server.
 */
async function loadUsers() {
    const tbody = document.getElementById('usersBody');
    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center;">⏳ Lade Benutzer...</td></tr>';

    try {
        const response = await fetch('/admin/users');
        const data = await response.json();

        if (data.users && data.users.length > 0) {
            tbody.innerHTML = '';

            data.users.forEach(user => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${user.username}</td>
                    <td>
                        ${user.is_admin ?
                            '<span style="color: #FF9800; font-weight: bold;">👑 Admin</span>' :
                            '<span style="color: #666;">👤 User</span>'}
                    </td>
                    <td>${user.created_at || 'N/A'}</td>
                    <td>${user.last_login || 'Noch nie'}</td>
                    <td>
                        ${!['Admin_G', 'Admin_D'].includes(user.username) ?
                            `<button class="btn btn-danger" onclick="deleteUser('${user.username}')">🗑️ Löschen</button>` :
                            '<span style="color: #999;">Geschützt</span>'}
                    </td>
                `;
                tbody.appendChild(row);
            });

        } else {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center;">Keine Benutzer vorhanden</td></tr>';
        }

    } catch (error) {
        console.error('Fehler beim Laden der Benutzer:', error);
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #f44336;">❌ Fehler beim Laden</td></tr>';
    }
}

/**
 * Öffnet das Modal zum Erstellen eines neuen Benutzers.
 */
function openCreateUserModal() {
    document.getElementById('createUserModal').classList.add('active');
}

/**
 * Schließt das Benutzer-Erstellungs-Modal.
 */
function closeModal() {
    document.getElementById('createUserModal').classList.remove('active');
    document.getElementById('createUserForm').reset();
}

/**
 * Event-Listener für Formular-Absendung (Benutzer erstellen).
 */
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('createUserForm');

    if (form) {
        form.addEventListener('submit', async function(e) {
            e.preventDefault();

            const formData = new FormData(form);
            const userData = {
                username: formData.get('username'),
                password: formData.get('password'),
                email: formData.get('email'),
                is_admin: formData.get('is_admin') === 'true'
            };

            try {
                const response = await fetch('/admin/create-user', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(userData)
                });

                const data = await response.json();

                if (data.success) {
                    alert('✅ Benutzer erfolgreich erstellt');
                    closeModal();
                    loadUsers(); // Liste aktualisieren
                } else {
                    alert('❌ Fehler: ' + data.error);
                }

            } catch (error) {
                console.error('Fehler beim Erstellen des Benutzers:', error);
                alert('❌ Verbindungsfehler');
            }
        });
    }
});

/**
 * Löscht einen Benutzer nach Bestätigung.
 *
 * @param {string} username - Zu löschender Benutzername
 */
async function deleteUser(username) {
    if (!confirm(`Möchten Sie den Benutzer "${username}" wirklich löschen?`)) {
        return;
    }

    try {
        const response = await fetch('/admin/delete-user', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ username: username })
        });

        const data = await response.json();

        if (data.success) {
            alert('✅ Benutzer erfolgreich gelöscht');
            loadUsers();
        } else {
            alert('❌ Fehler: ' + data.error);
        }

    } catch (error) {
        console.error('Fehler beim Löschen des Benutzers:', error);
        alert('❌ Verbindungsfehler');
    }
}

// ============================================================================
// SYSTEM-LOGS
// ============================================================================

/**
 * Lädt System-Log-Statistiken vom Server.
 */
async function loadLogs() {
    const logsDiv = document.getElementById('logsContent');
    logsDiv.innerHTML = '<p>⏳ Lade Log-Daten...</p>';

    try {
        const response = await fetch('/admin/system-logs');
        const data = await response.json();

        if (data.logs) {
            let html = '<div style="display: grid; gap: 15px;">';

            for (const [logName, logInfo] of Object.entries(data.logs)) {
                const statusColor = logInfo.exists !== false ? '#4CAF50' : '#999';

                html += `
                    <div style="padding: 15px; background: #f9f9f9; border-radius: 5px; border-left: 4px solid ${statusColor};">
                        <h4 style="margin: 0 0 10px 0; color: #333;">${logName}</h4>
                        <p style="margin: 5px 0; color: #666;">
                            Größe: ${logInfo.size_mb} MB<br>
                            Zeilen: ${logInfo.line_count || 0}<br>
                            Pfad: <code style="background: white; padding: 2px 5px; border-radius: 3px;">${logInfo.path}</code>
                        </p>
                    </div>
                `;
            }

            html += '</div>';
            logsDiv.innerHTML = html;

        } else {
            logsDiv.innerHTML = '<p style="color: #f44336;">❌ Fehler beim Laden der Logs</p>';
        }

    } catch (error) {
        console.error('Fehler beim Laden der Logs:', error);
        logsDiv.innerHTML = '<p style="color: #f44336;">❌ Verbindungsfehler</p>';
    }
}

// ============================================================================
// SYSTEM-STEUERUNG
// ============================================================================

/**
 * Bestätigt und führt System-Aktion aus (Neustart/Herunterfahren).
 *
 * @param {string} action - 'restart' oder 'shutdown'
 */
function confirmSystemAction(action) {
    const messages = {
        'restart': 'Möchten Sie das System wirklich neu starten?\n\nDie Verbindung wird für etwa 30 Sekunden unterbrochen.',
        'shutdown': 'Möchten Sie das System wirklich herunterfahren?\n\nSie müssen das Gerät danach manuell neu starten!'
    };

    if (!confirm(messages[action])) {
        return;
    }

    // Zweite Bestätigung für kritische Aktion
    if (!confirm('Sind Sie WIRKLICH sicher? Diese Aktion wird sofort ausgeführt!')) {
        return;
    }

    executeSystemAction(action);
}

/**
 * Führt System-Aktion aus.
 *
 * @param {string} action - 'restart' oder 'shutdown'
 */
async function executeSystemAction(action) {
    const endpoint = action === 'restart' ? '/admin/system-restart' : '/admin/system-shutdown';

    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (data.success) {
            alert(data.message);

            // Nach Neustart: Zeige Countdown und versuche Reconnect
            if (action === 'restart') {
                showRestartCountdown();
            }
        }

    } catch (error) {
        console.error('Fehler bei System-Aktion:', error);
    }
}

/**
 * Zeigt Countdown während System-Neustart.
 */
function showRestartCountdown() {
    const overlay = document.createElement('div');
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.8);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 9999;
    `;

    overlay.innerHTML = `
        <div style="background: white; padding: 40px; border-radius: 10px; text-align: center;">
            <h2 style="color: #333; margin-bottom: 20px;">🔄 System wird neu gestartet</h2>
            <p style="color: #666; font-size: 18px;">Verbindung wird in <span id="countdown">30</span> Sekunden wiederhergestellt...</p>
        </div>
    `;

    document.body.appendChild(overlay);

    let seconds = 30;
    const countdownEl = document.getElementById('countdown');

    const interval = setInterval(() => {
        seconds--;
        countdownEl.textContent = seconds;

        if (seconds <= 0) {
            clearInterval(interval);
            window.location.reload();
        }
    }, 1000);
}

// ============================================================================
// WebRTC-STREAM (falls aktiviert)
// ============================================================================

/**
 * Initialisiert WebRTC-Stream für Admin-Dashboard.
 */
async function initWebRTC() {
    const videoElement = document.getElementById('videoElement');

    if (!videoElement) {
        return; // MJPEG-Version, kein WebRTC
    }

    try {
        webrtcPeerConnection = new RTCPeerConnection({
            iceServers: [{urls: 'stun:stun.l.google.com:19302'}]
        });

        webrtcPeerConnection.ontrack = (event) => {
            videoElement.srcObject = event.streams[0];
        };

        webrtcPeerConnection.addTransceiver('video', {direction: 'recvonly'});

        const offer = await webrtcPeerConnection.createOffer();
        await webrtcPeerConnection.setLocalDescription(offer);

        const response = await fetch('/webrtc/offer', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                sdp: offer.sdp,
                type: offer.type
            })
        });

        const answer = await response.json();
        await webrtcPeerConnection.setRemoteDescription(new RTCSessionDescription(answer));

        console.log('WebRTC-Stream initialisiert');

    } catch (error) {
        console.error('WebRTC-Fehler:', error);
    }
}

// Initialisiere WebRTC beim Laden
document.addEventListener('DOMContentLoaded', function() {
    initWebRTC();
});

// Cleanup beim Verlassen
window.addEventListener('beforeunload', async () => {
    if (webrtcPeerConnection) {
        webrtcPeerConnection.close();
        await fetch('/webrtc/close', {method: 'POST'});
    }
});

// ============================================================================
// GPS-KARTE
// ============================================================================

/**
 * Initialisiert GPS-Karte mit OpenStreetMap.
 */
function initGPSMap() {
    const mapElement = document.getElementById('map');

    if (!mapElement) {
        return; // GPS nicht aktiviert
    }

    // Karte wird im HTML-Template initialisiert
    // Hier nur zusätzliche Funktionen falls benötigt
}
