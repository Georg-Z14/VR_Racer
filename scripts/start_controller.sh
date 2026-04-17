#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export PYTHONUNBUFFERED=1
export CONTROLLER_AUTO_SELECT="${CONTROLLER_AUTO_SELECT:-1}"
export CONTROLLER_STATUS_FILE="${CONTROLLER_STATUS_FILE:-/tmp/vr-racer-controller.status}"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

exec venv/bin/python Steuerung_VR_Racer/Steuerung_stable.py
