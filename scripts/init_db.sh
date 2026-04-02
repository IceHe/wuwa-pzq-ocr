#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
SQL_FILE="${ROOT_DIR}/backend/db.sql"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}" >&2
  exit 1
fi

if [[ ! -f "${SQL_FILE}" ]]; then
  echo "Missing ${SQL_FILE}" >&2
  exit 1
fi

set -a
source "${ENV_FILE}"
set +a

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is not set in ${ENV_FILE}" >&2
  exit 1
fi

psql "${DATABASE_URL}" -f "${SQL_FILE}"
