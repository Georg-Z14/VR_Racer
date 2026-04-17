#!/bin/bash
set -euo pipefail
# → Bricht bei Fehlern ab (-e)
# → Unbenutzte Variablen werden als Fehler behandelt (-u)
# → Fehler in Pipes werden weitergegeben (-o pipefail)

# ======================================================
# ⚙️ KONFIGURATION
# ======================================================
ENV_FILE=".env"                  # unverschlüsselte Umgebungsvariablen
SERVER_SCRIPT="server.py"        # Python-Server, der gestartet werden soll
VENV_DIR="${VENV_DIR:-venv}"
PYTHON_BIN="${PYTHON_BIN:-${VENV_DIR}/bin/python}"   # Python-Interpreter (immer venv)
# Ausgabe bleibt auf STDOUT/STDERR – keine server.log mehr
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

# ======================================================
# 🧩 GRUNDPRÜFUNG
# ======================================================
if [[ ! -f "$ENV_FILE" ]]; then
  echo "❌ Keine .env-Datei gefunden. Abbruch."
  exit 1
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "❌ Venv-Python nicht gefunden: $PYTHON_BIN"
  echo "   Stelle sicher, dass dein venv existiert (z. B.: python3 -m venv $VENV_DIR)."
  exit 1
fi

# ======================================================
# 🌍 ENV LADEN
# ======================================================
echo "📦 Lade Umgebungsvariablen..."
# Jede Zeile der .env-Datei exportieren (z. B. JWT_SECRET, DB_PATH)
set -o allexport
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" ]] && continue         # Leere Zeilen ignorieren
  [[ "$line" == \#* ]] && continue     # Kommentare ignorieren
  key="${line%%=*}"
  value="${line#*=}"
  value="${value#\"}"
  value="${value%\"}"
  export "$key=$value"
done < "$ENV_FILE"
set +o allexport

# ======================================================
# 🚀 SERVER STARTEN
# ======================================================
echo "🚀 Starte VR-Racer Server..."

$PYTHON_BIN "$SERVER_SCRIPT" &  # Server im Hintergrund starten
SERVER_PID=$!

# ======================================================
# 🧩 STATUSAUSGABE
# ======================================================
echo "✅ Server läuft (PID: $SERVER_PID)"

# ======================================================
# 🧹 CLEANUP BEI BEENDIGUNG
# ======================================================
cleanup() {
  echo "🧹 Stoppe Server..."
  if kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  echo "🛑 Server beendet."
}
trap cleanup EXIT

# ======================================================
# ⏳ SERVER LAUFEN LASSEN
# ======================================================
wait "$SERVER_PID"
