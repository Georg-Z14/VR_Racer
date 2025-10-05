#!/bin/bash
set -euo pipefail

ENV_FILE=".env"
ENV_ENCRYPTED=".env.gpg"
BACKUP_FILE=".env.backup_$(date +%Y%m%d_%H%M%S)"

echo "=============================================="
echo "🔐 ENV-Verwaltung — Passwort & Token-Dauer"
echo "=============================================="
echo "1) Passwort ändern (.env.gpg neu verschlüsseln)"
echo "2) Token-Laufzeit (JWT_EXPIRE_MINUTES) ändern"
echo "3) Beenden"
echo "----------------------------------------------"
read -rp "👉 Auswahl (1-3): " choice

decrypt_env() {
  echo ""
  echo "🧩 Entschlüssele aktuelle .env..."
  read -rsp "🔑 Passphrase eingeben: " GPG_PASS
  echo ""
  chmod 600 "$ENV_ENCRYPTED" 2>/dev/null || true
  if ! gpg --batch --yes --pinentry-mode loopback --passphrase "$GPG_PASS" -d -o "$ENV_FILE" "$ENV_ENCRYPTED"; then
    echo "❌ Entschlüsselung fehlgeschlagen. Falsche Passphrase?"
    exit 1
  fi
}

encrypt_env() {
  echo "🔐 Neu verschlüsseln..."
  read -rsp "🔑 Neues Passwort eingeben: " NEW_PASS
  echo ""
  read -rsp "🔁 Wiederhole neues Passwort: " REPEAT_PASS
  echo ""
  if [[ "$NEW_PASS" != "$REPEAT_PASS" ]]; then
    echo "❌ Passwörter stimmen nicht überein!"
    rm -f "$ENV_FILE"
    exit 1
  fi
  chmod 600 "$ENV_ENCRYPTED" 2>/dev/null || true
  gpg --batch --yes --pinentry-mode loopback --passphrase "$NEW_PASS" -c --cipher-algo AES256 "$ENV_FILE"
  rm -f "$ENV_FILE"
  chmod 400 "$ENV_ENCRYPTED"
}

case $choice in
1)
  decrypt_env
  echo "✅ .env entschlüsselt."
  cp "$ENV_FILE" "$BACKUP_FILE"
  echo "📦 Backup erstellt: $BACKUP_FILE"

  encrypt_env
  echo "✅ Neues Passwort aktiv. (.env.gpg)"
  ;;

2)
  decrypt_env
  cp "$ENV_FILE" "$BACKUP_FILE"
  echo "📦 Backup erstellt: $BACKUP_FILE"

  OLD_VALUE=$(grep -E '^JWT_EXPIRE_MINUTES=' "$ENV_FILE" | cut -d'=' -f2 || echo "")
  echo "⏱️ Aktuelle Laufzeit: ${OLD_VALUE:-nicht gesetzt}"
  read -rp "👉 Neue Laufzeit in Minuten: " NEW_VALUE

  if [[ -z "$NEW_VALUE" ]]; then
    echo "⚠️ Keine Eingabe — Abbruch."
    rm -f "$ENV_FILE"
    exit 1
  fi

  if grep -qE '^JWT_EXPIRE_MINUTES=' "$ENV_FILE"; then
    sed -i '' "s/^JWT_EXPIRE_MINUTES=.*/JWT_EXPIRE_MINUTES=$NEW_VALUE/" "$ENV_FILE"
  else
    echo "JWT_EXPIRE_MINUTES=$NEW_VALUE" >> "$ENV_FILE"
  fi

  echo "✅ Laufzeit geändert auf $NEW_VALUE Minuten."
  echo ""
  echo "🔐 Neu verschlüsseln mit demselben Passwort..."
  read -rsp "🔑 Aktuelle Passphrase: " GPG_PASS
  echo ""
  chmod 600 "$ENV_ENCRYPTED" 2>/dev/null || true
  gpg --batch --yes --pinentry-mode loopback --passphrase "$GPG_PASS" -c --cipher-algo AES256 "$ENV_FILE"
  rm -f "$ENV_FILE"
  chmod 400 "$ENV_ENCRYPTED"
  echo "✅ Neue Laufzeit gespeichert!"
  ;;

3)
  echo "🚪 Abbruch."
  exit 0
  ;;

*)
  echo "❌ Ungültige Auswahl."
  exit 1
  ;;
esac