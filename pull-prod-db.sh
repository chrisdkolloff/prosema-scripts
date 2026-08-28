#!/usr/bin/env bash
# Overwrite the local Postgres database with a copy from production.
#
# Production is read-only here (pg_dump). Local DATABASE_URL is replaced.
#
# Setup (once): add to .env (never commit the production URL):
#   PRODUCTION_DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DB?sslmode=require
#
# Usage:
#   ./pull-prod-db.sh              # interactive confirm
#   ./pull-prod-db.sh --yes        # skip confirmation
#   ./pull-prod-db.sh --dry-run    # show URLs and exit
#
# Requires: pg_dump, psql (PostgreSQL client tools)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

ENV_FILE="${ENV_FILE:-${ROOT}/.env}"
CONFIRM=yes
DRY_RUN=false

usage() {
  cat <<'EOF'
Usage: ./pull-prod-db.sh [--yes] [--dry-run]

  --yes       Skip the confirmation prompt (still runs safety checks).
  --dry-run   Print source/target and exit without copying.
  -h, --help  Show this help.

Environment (from .env unless overridden):
  PRODUCTION_DATABASE_URL   Source (production Postgres). Required.
  DATABASE_URL              Target (local prosema_dev). Required.

EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) CONFIRM=no ;;
    --dry-run) DRY_RUN=true ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1 (install PostgreSQL client tools)" >&2
    exit 1
  fi
}

env_get() {
  local file="$1" key="$2"
  [[ -f "$file" ]] || return 1
  local line
  line=$(grep -E "^${key}=" "$file" | tail -1) || return 1
  line="${line#${key}=}"
  line="${line%\"}"
  line="${line#\"}"
  line="${line%\'}"
  line="${line#\'}"
  printf '%s' "$line"
}

normalize_pg_url() {
  local url="$1"
  url="${url/postgresql+psycopg2/postgresql}"
  url="${url/postgresql+psycopg/postgresql}"
  printf '%s' "$url"
}

redact_url() {
  # postgresql://user:secret@host:5432/db -> postgresql://user:***@host:5432/db
  printf '%s' "$1" | sed -E 's#(://[^:/@]+):[^@]*@#\1:***@#'
}

looks_local() {
  local url="${1,,}"
  [[ "$url" == *localhost* || "$url" == *127.0.0.1* || "$url" == *"@host.docker.internal"* ]]
}

looks_production() {
  local url="${1,,}"
  [[ "$url" == *azure* || "$url" == *tools.prosema* || "$url" == *prod* ]]
}

need_cmd pg_dump
need_cmd psql

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing ${ENV_FILE}. Copy .env.example to .env and set DATABASE_URL." >&2
  exit 1
fi

PRODUCTION_DATABASE_URL="${PRODUCTION_DATABASE_URL:-$(env_get "$ENV_FILE" PRODUCTION_DATABASE_URL || true)}"
DATABASE_URL="${DATABASE_URL:-$(env_get "$ENV_FILE" DATABASE_URL || true)}"

if [[ -z "$PRODUCTION_DATABASE_URL" ]]; then
  cat >&2 <<'EOF'
PRODUCTION_DATABASE_URL is not set.

Add it to .env (do not commit):
  PRODUCTION_DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DB?sslmode=require

Copy the connection string from Azure Portal → PostgreSQL → Connection strings.
EOF
  exit 1
fi

if [[ -z "$DATABASE_URL" ]]; then
  echo "DATABASE_URL is not set in ${ENV_FILE}." >&2
  exit 1
fi

PROD_URL="$(normalize_pg_url "$PRODUCTION_DATABASE_URL")"
LOCAL_URL="$(normalize_pg_url "$DATABASE_URL")"

if looks_local "$PROD_URL"; then
  echo "Refusing: PRODUCTION_DATABASE_URL looks like a local database." >&2
  exit 1
fi

if ! looks_local "$LOCAL_URL"; then
  echo "Refusing: DATABASE_URL does not look local (expected localhost)." >&2
  echo "  Target: $(redact_url "$LOCAL_URL")" >&2
  exit 1
fi

if looks_production "$LOCAL_URL"; then
  echo "Refusing: DATABASE_URL looks like production." >&2
  exit 1
fi

echo "Source (production): $(redact_url "$PROD_URL")"
echo "Target (local):      $(redact_url "$LOCAL_URL")"

if [[ "$DRY_RUN" == true ]]; then
  echo "Dry run — no changes made."
  exit 0
fi

if [[ "$CONFIRM" == yes ]]; then
  cat <<'EOF'

This will DROP and recreate objects in the LOCAL database from production.
Local-only data (draft batches, test groups, etc.) will be lost.

EOF
  read -r -p "Type 'pull' to continue: " answer
  if [[ "$answer" != "pull" ]]; then
    echo "Aborted."
    exit 1
  fi
fi

echo "Dumping production and restoring into local database…"
pg_dump "$PROD_URL" --no-owner --no-acl --clean --if-exists | psql "$LOCAL_URL" -v ON_ERROR_STOP=1 -q

echo "Done. Local database now matches production."
