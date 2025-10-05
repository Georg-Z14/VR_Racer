#!/bin/zsh
echo "🔐 Entschlüssele .env.gpg sicher im RAM..."

cd "$(dirname "$0")"

# TMP-Verzeichnis im RAM anlegen
RAM_DIR="/tmp/env_ram_$$"
mkdir -p "$RAM_DIR"

# Passwort-Eingabe (zsh-kompatibel)
echo -n "Bitte Passphrase eingeben: "
read passphrase

# Entschlüsseln direkt ins RAM
echo "$passphrase" | gpg --batch --yes --quiet --pinentry-mode loopback --passphrase-fd 0 -o "$RAM_DIR/.env" -d .env.gpg

# Prüfen ob Entschlüsselung geklappt hat
if [ ! -f "$RAM_DIR/.env" ]; then
  echo "❌ Entschlüsselung fehlgeschlagen."
  rm -rf "$RAM_DIR"
  exit 1
fi

# Umgebungsvariablen in den Prozess laden
export $(grep -v '^#' "$RAM_DIR/.env" | xargs)

# Server starten
echo "🚀 Starte Server..."
python3 server.py &

SERVER_PID=$!

# Warten bis der Server läuft
sleep 5

# .env aus RAM löschen
echo "🧹 Lösche sensible Daten aus RAM..."
rm -f "$RAM_DIR/.env"
rmdir "$RAM_DIR"

# Auf Serverende warten
wait $SERVER_PID

echo "🛑 Server gestoppt — alle Daten sicher gelöscht."