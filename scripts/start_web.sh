#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv312"
ENV_FILE="${ROOT_DIR}/.env"
PORT="${1:-${PORT:-8000}}"
HOST="${HOST:-127.0.0.1}"
DEBUG="${DEBUG:-0}"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "Missing Python 3.12 virtualenv at ${VENV_DIR}." >&2
  echo "Create it first:" >&2
  echo "  ./scripts/bootstrap.sh" >&2
  exit 1
fi

if ! "${VENV_DIR}/bin/python" -c "import flask" >/dev/null 2>&1; then
  echo "Missing Python dependencies in ${VENV_DIR}." >&2
  echo "Install them first:" >&2
  echo "  ./scripts/bootstrap.sh" >&2
  exit 1
fi

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  source "${ENV_FILE}"
  set +a
fi

cd "${ROOT_DIR}"
echo "Starting web server on http://${HOST}:${PORT}"
exec "${VENV_DIR}/bin/python" -m backend.app
