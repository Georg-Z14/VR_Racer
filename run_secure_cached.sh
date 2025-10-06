#!/bin/zsh
set -euo pipefail
# → Skript bricht bei Fehlern ab (-e)
# → Unbenutzte Variablen werden als Fehler behandelt (-u)
# → Fehler in Pipes werden weitergegeben (-o pipefail)

# ======================================================
# ⚙️ KONFIGURATION
# ======================================================
ENV_GPG=".env.gpg"           # verschlüsselte .env-Datei
SERVER_SCRIPT="server.py"    # Python-Server, der gestartet werden soll
PYTHON_BIN="${PYTHON_BIN:-python3}"   # Python-Interpreter
CACHE_DIR="/tmp/vr_env_cache"         # temporäres Verzeichnis im RAM
PASSFILE="$CACHE_DIR/.pass"           # Datei für zwischengespeichertes Passwort
ENV_RAM="$CACHE_DIR/.env"             # entschlüsselte .env (wird nach TTL gelöscht)
CACHE_TTL=${CACHE_TTL:-60}            # wie lange das Passwort zwischengespeichert bleibt (Sekunden)

# ======================================================
# 🧹 CLEANUP-FUNKTIONEN
# ======================================================

# → Löscht nur Cache & temporäre Dateien
cleanup_cache() {
  echo "🧹 Lösche Cache-Dateien..."
  rm -f "$PASSFILE" "$ENV_RAM" 2>/dev/null || true
  [[ -d "$CACHE_DIR" ]] && rmdir "$CACHE_DIR" 2>/dev/null || true
  echo "✅ Cache & RAM-Daten entfernt."
}

# → Wird beim Beenden (CTRL+C oder Serverende) aufgerufen
cleanup_all() {
  echo "🧹 Cleanup nach Script-Ende..."
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  echo "✅ Server gestoppt."
}

# Trap = bei EXIT (also auch STRG+C) wird cleanup_all() aufgerufen
trap cleanup_all EXIT

# ======================================================
# 🧩 GRUNDPRÜFUNG
# ======================================================
if [[ ! -f "$ENV_GPG" ]]; then
  echo "❌ $ENV_GPG nicht gefunden. Abbruch."
  exit 1
fi

mkdir -p "$CACHE_DIR"
chmod 700 "$CACHE_DIR"  # nur Besitzer darf lesen/schreiben

# ======================================================
# 🔁 CACHE-PRÜFUNG
# ======================================================
if [[ -f "$PASSFILE" ]]; then
  # macOS & Linux verwenden unterschiedliche stat-Befehle
  if [[ "$OSTYPE" == "darwin"* ]]; then
    LAST_MOD=$(stat -f %m "$PASSFILE")     # macOS
  else
    LAST_MOD=$(stat -c %Y "$PASSFILE")     # Linux / Raspberry Pi
  fi

  NOW=$(date +%s)
  AGE=$((NOW - LAST_MOD))

  # Cache gültig?
  if (( AGE < CACHE_TTL )); then
    echo "🔁 Verwende gespeicherte Passphrase (Cache gültig, noch $((CACHE_TTL - AGE)) s)."
  else
    echo "⏱️ Cache abgelaufen ($AGE s alt). Neue Passphrase erforderlich."
    rm -f "$PASSFILE"
  fi
fi

# ======================================================
# 🔑 PASSWORT-EINGABE
# ======================================================
if [[ ! -f "$PASSFILE" ]]; then
  echo -n "🔑 Bitte GPG-Passphrase eingeben (wird im Cache gespeichert): "
  stty -echo         # verhindert, dass das Passwort im Terminal sichtbar ist
  read -r PASSPHRASE # Eingabe lesen
  stty echo
  echo
  printf "%s" "$PASSPHRASE" > "$PASSFILE"
  chmod 600 "$PASSFILE"    # nur Besitzer darf lesen
  unset PASSPHRASE         # Passwort sofort aus Speicher löschen
fi

# ======================================================
# 🔓 ENTSCHLÜSSELN .ENV → RAM
# ======================================================
echo "🧩 Entschlüssele .env.gpg temporär..."
if ! gpg --batch --yes --quiet --pinentry-mode loopback \
  --passphrase-file "$PASSFILE" -o "$ENV_RAM" -d "$ENV_GPG"; then
  echo "❌ Entschlüsselung fehlgeschlagen."
  rm -f "$ENV_RAM"
  exit 1
fi
chmod 600 "$ENV_RAM"

# ======================================================
# 🌍 ENV LADEN
# ======================================================
echo "📦 Lade Umgebungsvariablen..."
# Jede Zeile der .env-Datei exportieren (z. B. JWT_SECRET, DB_PATH)
set -o allexport
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" ]] && continue         # leere Zeilen ignorieren
  [[ "$line" == \#* ]] && continue     # Kommentare ignorieren
  key="${line%%=*}"
  value="${line#*=}"
  value="${value#\"}"
  value="${value%\"}"
  export "$key=$value"
done < "$ENV_RAM"
set +o allexport

# ======================================================
# 🚀 SERVER STARTEN
# ======================================================
echo "🚀 Starte Server..."

LOGFILE="$(pwd)/server.log"  # Log-Datei im Projektverzeichnis
$PYTHON_BIN "$SERVER_SCRIPT" > "$LOGFILE" 2>&1 &  # Server im Hintergrund starten
SERVER_PID=$!

echo "✅ Server läuft (PID: $SERVER_PID)"
echo "📄 Logs: $LOGFILE"
echo "🕒 Cache bleibt aktiv für $CACHE_TTL Sekunden"

# ======================================================
# 🧨 AUTO-LÖSCHUNG NACH ABLAUF
# ======================================================
(
  # Timer im Hintergrund → nach Ablauf der Zeit werden Pass & .env gelöscht
  sleep "$CACHE_TTL"
  echo
  echo "⏱️ Cache-TTL ($CACHE_TTL s) abgelaufen — lösche alles sicher."
  cleanup_cache
) &

# ======================================================
# ⏳ SERVER-LAUFZEIT
# ======================================================
wait "$SERVER_PID"  # wartet, bis Python-Server stoppt
echo "🛑 Server beendet."