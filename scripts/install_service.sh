#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEFAULT_SERVICE_NAME="ocr.service"
LEGACY_SERVICE_NAME="wuwa-ocr.service"
if [[ -n "${SERVICE_NAME:-}" ]]; then
  SERVICE_NAME="${SERVICE_NAME}"
elif [[ -f "/etc/systemd/system/${LEGACY_SERVICE_NAME}" && ! -f "/etc/systemd/system/${DEFAULT_SERVICE_NAME}" ]]; then
  SERVICE_NAME="${LEGACY_SERVICE_NAME}"
else
  SERVICE_NAME="${DEFAULT_SERVICE_NAME}"
fi
SERVICE_TEMPLATE="${ROOT_DIR}/deploy/systemd/ocr.service"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"
RUN_USER="${RUN_USER:-$(id -un)}"
PORT="${PORT:-8012}"
HOST="${HOST:-0.0.0.0}"
BOOTSTRAP="${BOOTSTRAP:-1}"

if [[ ! -f "${SERVICE_TEMPLATE}" ]]; then
  echo "Missing service template: ${SERVICE_TEMPLATE}" >&2
  exit 1
fi

if [[ "${BOOTSTRAP}" == "1" ]]; then
  "${ROOT_DIR}/scripts/bootstrap.sh"
elif [[ ! -x "${ROOT_DIR}/.venv312/bin/python" ]]; then
  echo "Missing virtualenv: ${ROOT_DIR}/.venv312" >&2
  echo "Run ./scripts/bootstrap.sh first, or set BOOTSTRAP=1." >&2
  exit 1
elif ! "${ROOT_DIR}/.venv312/bin/python" -c "import flask" >/dev/null 2>&1; then
  echo "Missing Python dependencies in ${ROOT_DIR}/.venv312" >&2
  echo "Run ./scripts/bootstrap.sh first, or set BOOTSTRAP=1." >&2
  exit 1
fi

tmp_service="$(mktemp)"
trap 'rm -f "${tmp_service}"' EXIT

sed \
  -e "s#__PROJECT_ROOT__#${ROOT_DIR}#g" \
  -e "s#__RUN_USER__#${RUN_USER}#g" \
  -e "s#Environment=HOST=0.0.0.0#Environment=HOST=${HOST}#g" \
  -e "s#Environment=PORT=8012#Environment=PORT=${PORT}#g" \
  "${SERVICE_TEMPLATE}" > "${tmp_service}"

install -m 644 "${tmp_service}" "${SERVICE_PATH}"
systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"
systemctl status "${SERVICE_NAME}" --no-pager
