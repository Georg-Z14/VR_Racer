#!/bin/bash
# ============================================================================
# Service-Installations-Script
# Datei: install_services.sh
# Version: 1.0
# Datum: 30.09.2025
#
# Installiert Systemd-Services für beide Streaming-Versionen
# Ausführung: sudo bash install_services.sh
# ============================================================================

echo "============================================================================"
echo "  SYSTEMD SERVICE INSTALLATION"
echo "============================================================================"
echo ""

# Prüfe ob Script als root ausgeführt wird
if [ "$EUID" -ne 0 ]; then
    echo "❌ Fehler: Bitte als root ausführen (sudo bash install_services.sh)"
    exit 1
fi

# Frage welche Version installiert werden soll
echo "Welche Version möchten Sie installieren?"
echo "1) MJPEG (höhere Kompatibilität, alle Browser)"
echo "2) WebRTC (niedrige Latenz, beste Qualität)"
echo "3) Beide Versionen (nicht gleichzeitig nutzbar!)"
echo ""
read -p "Auswahl [1-3]: " choice

case $choice in
    1)
        SERVICE="camera_mjpeg"
        echo ""
        echo "📦 Installiere MJPEG-Version..."
        ;;
    2)
        SERVICE="camera_webrtc"
        echo ""
        echo "📦 Installiere WebRTC-Version..."
        ;;
    3)
        SERVICE="both"
        echo ""
        echo "📦 Installiere beide Versionen..."
        echo "⚠️  WICHTIG: Nur eine Version kann gleichzeitig laufen!"
        ;;
    *)
        echo "❌ Ungültige Auswahl"
        exit 1
        ;;
esac

echo ""

# Funktion zum Installieren eines Services
install_service() {
    local service_name=$1
    local service_file="${service_name}.service"

    echo "➤ Installiere ${service_name}..."

    # Kopiere Service-Datei
    if [ -f "$service_file" ]; then
        cp "$service_file" /etc/systemd/system/
        echo "  ✓ Service-Datei kopiert"
    else
        echo "  ❌ Fehler: ${service_file} nicht gefunden"
        return 1
    fi

    # Systemd neu laden
    systemctl daemon-reload
    echo "  ✓ Systemd neu geladen"

    # Service aktivieren (Autostart)
    systemctl enable "$service_file"
    echo "  ✓ Autostart aktiviert"

    # Service starten
    systemctl start "$service_file"
    echo "  ✓ Service gestartet"

    # Status prüfen
    sleep 2
    if systemctl is-active --quiet "$service_file"; then
        echo "  ✅ Service läuft erfolgreich!"
    else
        echo "  ⚠️  Service-Status unklar, prüfe mit: sudo systemctl status $service_file"
    fi

    echo ""
}

# Installiere ausgewählten Service(s)
if [ "$SERVICE" = "both" ]; then
    install_service "camera_mjpeg"
    install_service "camera_webrtc"

    echo "⚠️  WICHTIG: Beide Services sind installiert, aber nur EINER sollte laufen!"
    echo ""
    echo "Aktuell läuft:"
    systemctl is-active camera_mjpeg.service && echo "  - camera_mjpeg.service"
    systemctl is-active camera_webrtc.service && echo "  - camera_webrtc.service"
    echo ""
    echo "Um zwischen Versionen zu wechseln:"
    echo "  sudo systemctl stop camera_mjpeg.service"
    echo "  sudo systemctl start camera_webrtc.service"
    echo ""
else
    install_service "$SERVICE"
fi

echo "============================================================================"
echo "  INSTALLATION ABGESCHLOSSEN"
echo "============================================================================"
echo ""
echo "Nützliche Befehle:"
echo ""
echo "Status prüfen:"
echo "  sudo systemctl status ${SERVICE}.service"
echo ""
echo "Service stoppen:"
echo "  sudo systemctl stop ${SERVICE}.service"
echo ""
echo "Service starten:"
echo "  sudo systemctl start ${SERVICE}.service"
echo ""
echo "Service neu starten:"
echo "  sudo systemctl restart ${SERVICE}.service"
echo ""
echo "Logs anzeigen:"
echo "  sudo journalctl -u ${SERVICE}.service -f"
echo ""
echo "Autostart deaktivieren:"
echo "  sudo systemctl disable ${SERVICE}.service"
echo ""
echo "============================================================================"
