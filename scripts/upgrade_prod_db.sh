#!/usr/bin/env bash
# Apply Alembic migrations to production Postgres.
#
# Uses PRODUCTION_DATABASE_URL from .env (same variable as ./pull-prod-db.sh).
# Other app settings still come from .env; only DATABASE_URL is overridden.
# Before connecting, runs ./scripts/allow_my_ip.sh so this machine's public IP
# is on the Azure Postgres firewall (home/office IPs change).
#
# Usage:
#   ./scripts/upgrade_prod_db.sh           # interactive confirm
#   ./scripts/upgrade_prod_db.sh --yes     # skip confirmation
#   ./scripts/upgrade_prod_db.sh --dry-run # print current vs head, do not upgrade
#
# Called by ./release.sh --push so the schema is ahead of the Azure deploy.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

ENV_FILE="${ENV_FILE:-${ROOT}/.env}"
CONFIRM=yes
DRY_RUN=false
SKIP_FIREWALL=false

usage() {
  cat <<'EOF'
Usage: ./scripts/upgrade_prod_db.sh [--yes] [--dry-run] [--skip-firewall]

  --yes             Skip the confirmation prompt (still runs safety checks).
  --dry-run         Print current and head revisions, then exit.
  --skip-firewall   Do not update the Azure Postgres firewall rule.
  -h, --help        Show this help.

Environment (from .env unless overridden):
  PRODUCTION_DATABASE_URL   Production Postgres. Required.
  SKIP_FIREWALL_ALLOW=1     Same as --skip-firewall.

EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) CONFIRM=no ;;
    --dry-run) DRY_RUN=true ;;
    --skip-firewall) SKIP_FIREWALL=true ;;
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

looks_local() {
  local url
  url="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  [[ "$url" == *localhost* || "$url" == *127.0.0.1* || "$url" == *"@host.docker.internal"* ]]
}

looks_production() {
  local url
  url="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  [[ "$url" == *azure* || "$url" == *tools.prosema* || "$url" == *prod* ]]
}

redact_url() {
  printf '%s' "$1" | sed -E 's#(://[^:/@]+):[^@]*@#\1:***@#'
}

to_sqlalchemy_url() {
  local url="$1"
  url="${url/postgresql+psycopg2/postgresql+psycopg}"
  if [[ "$url" == postgresql://* ]]; then
    url="postgresql+psycopg://${url#postgresql://}"
  fi
  if [[ "$url" != *"sslmode="* ]]; then
    if [[ "$url" == *"?"* ]]; then
      url="${url}&sslmode=require"
    else
      url="${url}?sslmode=require"
    fi
  fi
  printf '%s' "$url"
}

python_bin() {
  if [[ -x "${ROOT}/.venv/bin/python" ]]; then
    echo "${ROOT}/.venv/bin/python"
    return 0
  fi
  if command -v python3.12 >/dev/null 2>&1; then
    echo "python3.12"
    return 0
  fi
  echo "Error: no .venv/bin/python or python3.12 found." >&2
  exit 1
}

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing ${ENV_FILE}." >&2
  exit 1
fi

PRODUCTION_DATABASE_URL="${PRODUCTION_DATABASE_URL:-$(env_get "$ENV_FILE" PRODUCTION_DATABASE_URL || true)}"

if [[ -z "$PRODUCTION_DATABASE_URL" ]]; then
  cat >&2 <<'EOF'
PRODUCTION_DATABASE_URL is not set.

Add it to .env (do not commit), same value as Azure App Service DATABASE_URL:
  PRODUCTION_DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DB?sslmode=require

Copy the connection string from Azure Portal → PostgreSQL → Connection strings.
EOF
  exit 1
fi

if looks_local "$PRODUCTION_DATABASE_URL"; then
  echo "Refusing: PRODUCTION_DATABASE_URL looks like a local database." >&2
  exit 1
fi

if ! looks_production "$PRODUCTION_DATABASE_URL"; then
  echo "Refusing: PRODUCTION_DATABASE_URL does not look like production." >&2
  echo "  Target: $(redact_url "$PRODUCTION_DATABASE_URL")" >&2
  exit 1
fi

SA_URL="$(to_sqlalchemy_url "$PRODUCTION_DATABASE_URL")"
PY="$(python_bin)"

if [[ "$SKIP_FIREWALL" != true && "${SKIP_FIREWALL_ALLOW:-}" != "1" ]]; then
  echo "Allowing this machine's public IP on Azure Postgres firewall…"
  "${ROOT}/scripts/allow_my_ip.sh"
fi

echo "Target: $(redact_url "$SA_URL")"

run_alembic() {
  DATABASE_URL="$SA_URL" "${PY}" -m alembic "$@"
}

echo "Current revision:"
run_alembic current
echo "Head revision:"
run_alembic heads

if [[ "$DRY_RUN" == true ]]; then
  echo "Dry run — no upgrade."
  exit 0
fi

if [[ "$CONFIRM" == yes ]]; then
  cat <<'EOF'

This will run 'alembic upgrade head' against production Postgres.

EOF
  read -r -p "Type 'upgrade' to continue: " answer
  if [[ "$answer" != "upgrade" ]]; then
    echo "Aborted."
    exit 1
  fi
fi

echo "Running alembic upgrade head…"
run_alembic upgrade head
echo "Done."
run_alembic current
