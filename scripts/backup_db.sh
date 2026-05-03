#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
BACKUP_DIR="${ROOT_DIR}/backups/db"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}" >&2
  exit 1
fi

set -a
source "${ENV_FILE}"
set +a

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is not set in ${ENV_FILE}" >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"
BACKUP_FILE="${BACKUP_DIR}/wuwa_ocr_$(date +%Y%m%d_%H%M%S).sql"

pg_dump "${DATABASE_URL}" \
  --format=plain \
  --no-owner \
  --no-privileges \
  --file "${BACKUP_FILE}"

if [[ ! -s "${BACKUP_FILE}" ]]; then
  echo "Backup file is empty: ${BACKUP_FILE}" >&2
  exit 1
fi

if ! grep -q "wuwa_rebuild_log" "${BACKUP_FILE}"; then
  echo "Backup does not contain expected wuwa_rebuild_log references: ${BACKUP_FILE}" >&2
  exit 1
fi

echo "Database backup written to ${BACKUP_FILE}"
