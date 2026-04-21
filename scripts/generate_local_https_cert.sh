#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_DIR="$PROJECT_DIR/certs"
CERT_FILE="$CERT_DIR/vrracer.crt"
KEY_FILE="$CERT_DIR/vrracer.key"
OPENSSL_CONFIG="$CERT_DIR/vrracer-openssl.cnf"

HOSTNAME_SHORT="$(hostname -s 2>/dev/null || echo raspberrypi)"
PRIMARY_IP="${VR_RACER_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"

if [[ -z "${PRIMARY_IP:-}" ]]; then
  echo "Keine lokale IP gefunden. Setze sie explizit, z. B.:"
  echo "  VR_RACER_IP=192.168.1.50 ./scripts/generate_local_https_cert.sh"
  exit 1
fi

mkdir -p "$CERT_DIR"

cat > "$OPENSSL_CONFIG" <<EOF_CONFIG
[req]
default_bits = 2048
prompt = no
default_md = sha256
x509_extensions = v3_req
distinguished_name = dn

[dn]
CN = vrracer.local

[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = vrracer.local
DNS.2 = ${HOSTNAME_SHORT}.local
DNS.3 = ${HOSTNAME_SHORT}
IP.1 = ${PRIMARY_IP}
EOF_CONFIG

openssl req -x509 \
  -nodes \
  -days 825 \
  -newkey rsa:2048 \
  -keyout "$KEY_FILE" \
  -out "$CERT_FILE" \
  -config "$OPENSSL_CONFIG"

chmod 600 "$KEY_FILE"
chmod 644 "$CERT_FILE"

echo "Lokales HTTPS-Zertifikat erstellt:"
echo "  Zertifikat: $CERT_FILE"
echo "  Private Key: $KEY_FILE"
echo
echo "URL fuer den Test:"
echo "  https://${PRIMARY_IP}:8443"
echo "  https://vrracer.local:8443   falls mDNS im Netzwerk funktioniert"
echo
echo "Wichtig: Auf der Vision Pro muss dieses Zertifikat als vertrauenswuerdig installiert werden."
