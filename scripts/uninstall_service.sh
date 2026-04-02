#!/usr/bin/env bash
set -euo pipefail

DEFAULT_SERVICE_NAME="ocr.service"
LEGACY_SERVICE_NAME="wuwa-ocr.service"
if [[ -n "${SERVICE_NAME:-}" ]]; then
  SERVICE_NAME="${SERVICE_NAME}"
elif [[ -f "/etc/systemd/system/${DEFAULT_SERVICE_NAME}" ]]; then
  SERVICE_NAME="${DEFAULT_SERVICE_NAME}"
else
  SERVICE_NAME="${LEGACY_SERVICE_NAME}"
fi
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"

if systemctl list-unit-files "${SERVICE_NAME}" --no-legend >/dev/null 2>&1; then
  systemctl disable --now "${SERVICE_NAME}" || true
fi

rm -f "${SERVICE_PATH}"
systemctl daemon-reload
systemctl reset-failed

echo "Removed ${SERVICE_NAME}"
