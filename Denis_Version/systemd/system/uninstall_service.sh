#!/bin/bash
# ============================================================================
# Service-Deinstallations-Script
# Datei: uninstall_services.sh
# Version: 1.0
# Datum: 30.09.2025
#
# Deinstalliert Systemd-Services
# Ausführung: sudo bash uninstall_services.sh
# ============================================================================

echo "============================================================================"
echo "  SYSTEMD SERVICE DEINSTALLATION"
echo "============================================================================"
echo ""

# Prüfe ob Script als root ausgeführt wird
if [ "$EUID" -ne 0 ]; then
    echo "❌ Fehler: Bitte als root ausführen (sudo bash uninstall_services.sh)"
    exit 1
fi

# Warnung
echo "⚠️  WARNUNG: Diese Aktion deinstalliert alle Kamera-Services!"
echo ""
read -p "Möchten Sie fortfahren? (ja/nein): " confirm

if [ "$confirm" != "ja" ]; then
    echo "Abgebrochen."
    exit 0
fi

echo ""

# Funktion zum Deinstallieren eines Services
uninstall_service() {
    local service_name=$1
    local service_file="${service_name}.service"

    echo "➤ Deinstalliere ${service_name}..."

    # Stoppe Service
    if systemctl is-active --quiet "$service_file"; then
        systemctl stop "$service_file"
        echo "  ✓ Service gestoppt"
    fi

    # Deaktiviere Autostart
    if systemctl is-enabled --quiet "$service_file" 2>/dev/null; then
        systemctl disable "$service_file"
        echo "  ✓ Autostart deaktiviert"
    fi

    # Lösche Service-Datei
    if [ -f "/etc/systemd/system/$service_file" ]; then
        rm "/etc/systemd/system/$service_file"
        echo "  ✓ Service-Datei gelöscht"
    fi

    echo ""
}

# Deinstalliere beide Services
uninstall_service "camera_mjpeg"
uninstall_service "camera_webrtc"

# Systemd neu laden
systemctl daemon-reload
echo "✓ Systemd neu geladen"

echo ""
echo "============================================================================"
echo "  DEINSTALLATION ABGESCHLOSSEN"
echo "============================================================================"
echo ""
echo "Services wurden entfernt. Das Hauptprogramm ist weiterhin vorhanden."
echo "Um es manuell zu starten:"
echo "  cd /home/pi/camera_system"
echo "  source venv/bin/activate"
echo "  python3 main_mjpeg.py"
echo ""
