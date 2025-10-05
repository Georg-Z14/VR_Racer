#!/bin/zsh
set -euo pipefail

# === Konfiguration ===
ENV_GPG=".env.gpg"
SERVER_SCRIPT="server.py"
PYTHON_BIN="${PYTHON_BIN:-python3}"
CACHE_DIR="/tmp/vr_env_cache"
PASSFILE="$CACHE_DIR/.pass"
ENV_RAM="$CACHE_DIR/.env"
CACHE_TTL=${CACHE_TTL:-60}

# === Funktionen ===
cleanup_cache() {
  echo "🧹 Lösche Cache-Dateien..."
  rm -f "$PASSFILE" "$ENV_RAM" 2>/dev/null || true
  [[ -d "$CACHE_DIR" ]] && rmdir "$CACHE_DIR" 2>/dev/null || true
  echo "✅ Cache & RAM-Daten entfernt."
}

cleanup_all() {
  echo "🧹 Cleanup nach Script-Ende..."
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  echo "✅ Server gestoppt."
}

trap cleanup_all EXIT

# === Prüfung ===
if [[ ! -f "$ENV_GPG" ]]; then
  echo "❌ $ENV_GPG nicht gefunden. Abbruch."
  exit 1
fi

mkdir -p "$CACHE_DIR"
chmod 700 "$CACHE_DIR"

# === Cache prüfen ===
if [[ -f "$PASSFILE" ]]; then
  # Prüfe, ob Cache jünger als TTL ist → macOS & Linux kompatibel
  if [[ "$OSTYPE" == "darwin"* ]]; then
    LAST_MOD=$(stat -f %m "$PASSFILE")     # macOS
  else
    LAST_MOD=$(stat -c %Y "$PASSFILE")     # Linux
  fi

  NOW=$(date +%s)
  AGE=$((NOW - LAST_MOD))
  if (( AGE < CACHE_TTL )); then
    echo "🔁 Verwende gespeicherte Passphrase (Cache gültig, noch $((CACHE_TTL - AGE)) s)."
  else
    echo "⏱️ Cache abgelaufen ($AGE s alt). Neue Passphrase erforderlich."
    rm -f "$PASSFILE"
  fi
fi

# === Passwort ggf. neu eingeben ===
if [[ ! -f "$PASSFILE" ]]; then
  echo -n "🔑 Bitte GPG-Passphrase eingeben: "
  stty -echo
  read -r PASSPHRASE
  stty echo
  echo
  printf "%s" "$PASSPHRASE" > "$PASSFILE"
  chmod 600 "$PASSFILE"
  unset PASSPHRASE
fi

# === Entschlüsseln in RAM ===
if ! gpg --batch --yes --quiet --pinentry-mode loopback \
  --passphrase-file "$PASSFILE" -o "$ENV_RAM" -d "$ENV_GPG"; then
  echo "❌ Entschlüsselung fehlgeschlagen."
  rm -f "$ENV_RAM"
  exit 1
fi
chmod 600 "$ENV_RAM"

# === ENV laden ===
set -o allexport
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" ]] && continue
  [[ "$line" == \#* ]] && continue
  key="${line%%=*}"
  value="${line#*=}"
  value="${value#\"}"
  value="${value%\"}"
  export "$key=$value"
done < "$ENV_RAM"
set +o allexport

# === Server starten ===
echo "🚀 Starte Server..."
$PYTHON_BIN "$SERVER_SCRIPT" &
SERVER_PID=$!

# === Autolöschung nach Ablauf ===
(
  sleep "$CACHE_TTL"
  echo
  echo "⏱️ Cache-TTL ($CACHE_TTL s) abgelaufen — lösche alles sicher."
  cleanup_cache
) &

# === Warten bis Server stoppt ===
wait "$SERVER_PID"

echo "🛑 Server beendet."