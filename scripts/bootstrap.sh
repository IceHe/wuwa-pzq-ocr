#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv312"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Missing Python interpreter: ${PYTHON_BIN}" >&2
  echo "You can override it with PYTHON_BIN=/path/to/python" >&2
  exit 1
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install -r "${ROOT_DIR}/requirements.txt"
