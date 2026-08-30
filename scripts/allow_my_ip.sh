#!/usr/bin/env bash
# Write this machine's current public IPv4 into a named Azure Postgres
# firewall rule so laptop scripts (release.sh --push, pull-prod-db.sh) can
# reach production. Home/office IPs change; this refreshes one dedicated rule.
#
# Usage:
#   ./scripts/allow_my_ip.sh
#   ./scripts/allow_my_ip.sh --dry-run
#
# Requires Azure CLI (`brew install azure-cli`) and `az login`.
# SKIP_FIREWALL_ALLOW=1 skips the call from upgrade_prod_db.sh.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

ENV_FILE="${ENV_FILE:-${ROOT}/.env}"
DRY_RUN=false
PROPAGATION_WAIT_SECONDS="${AZURE_POSTGRES_FIREWALL_WAIT_SECONDS:-10}"

usage() {
  cat <<'EOF'
Usage: ./scripts/allow_my_ip.sh [--dry-run]

  --dry-run   Print the public IP and intended rule; do not change Azure.
  -h, --help  Show this help.

Environment (from .env unless overridden):
  AZURE_POSTGRES_SERVER_NAME          Default: prosema-tools-db-prod
  AZURE_POSTGRES_RESOURCE_GROUP       Looked up from the server name if unset
  AZURE_POSTGRES_FIREWALL_RULE_NAME   Default: operator-laptop
  AZURE_SUBSCRIPTION_ID               Optional; uses the current az account

EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
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

is_ipv4() {
  local ip="$1"
  [[ "$ip" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || return 1
  local o
  IFS=. read -r -a o <<<"$ip"
  [[ ${#o[@]} -eq 4 ]] || return 1
  local n
  for n in "${o[@]}"; do
    [[ "$n" -ge 0 && "$n" -le 255 ]] || return 1
  done
}

get_public_ip() {
  local url ip
  for url in https://api.ipify.org https://ifconfig.me/ip https://ipv4.icanhazip.com; do
    ip=$(curl -4 -fsS --max-time 8 "$url" | tr -d '[:space:]') || continue
    if is_ipv4 "$ip"; then
      printf '%s' "$ip"
      return 0
    fi
  done
  return 1
}

require_az() {
  if ! command -v az >/dev/null 2>&1; then
    cat >&2 <<'EOF'
Azure CLI (az) is not installed. It is required to update the Postgres firewall.

  brew install azure-cli
  az login

If this machine is already allowlisted, skip the firewall step:

  SKIP_FIREWALL_ALLOW=1 ./scripts/upgrade_prod_db.sh
EOF
    exit 1
  fi
  if ! az account show --output none 2>/dev/null; then
    echo "Azure CLI is installed but you are not logged in. Run: az login" >&2
    exit 1
  fi
}

# Wrapper so we do not expand an empty array under bash 3.2 + set -u.
az_cli() {
  if [[ -n "$SUBSCRIPTION" ]]; then
    az "$@" --subscription "$SUBSCRIPTION"
  else
    az "$@"
  fi
}

SERVER="${AZURE_POSTGRES_SERVER_NAME:-}"
RG="${AZURE_POSTGRES_RESOURCE_GROUP:-}"
RULE="${AZURE_POSTGRES_FIREWALL_RULE_NAME:-}"
SUBSCRIPTION="${AZURE_SUBSCRIPTION_ID:-}"

if [[ -f "$ENV_FILE" ]]; then
  [[ -n "$SERVER" ]] || SERVER="$(env_get "$ENV_FILE" AZURE_POSTGRES_SERVER_NAME || true)"
  [[ -n "$RG" ]] || RG="$(env_get "$ENV_FILE" AZURE_POSTGRES_RESOURCE_GROUP || true)"
  [[ -n "$RULE" ]] || RULE="$(env_get "$ENV_FILE" AZURE_POSTGRES_FIREWALL_RULE_NAME || true)"
  [[ -n "$SUBSCRIPTION" ]] || SUBSCRIPTION="$(env_get "$ENV_FILE" AZURE_SUBSCRIPTION_ID || true)"
fi

SERVER="${SERVER:-prosema-tools-db-prod}"
RULE="${RULE:-operator-laptop}"

echo "Public IP lookup…"
IP="$(get_public_ip)" || {
  echo "Could not determine this machine's public IPv4." >&2
  exit 1
}
echo "  This machine: ${IP}"
echo "  Rule:         ${RULE} on ${SERVER}"

if [[ "$DRY_RUN" == true ]]; then
  echo "Dry run — no Azure changes."
  exit 0
fi

require_az

KIND=""
if [[ -z "$RG" ]]; then
  RG="$(az_cli postgres flexible-server list --query "[?name=='${SERVER}'].resourceGroup" -o tsv 2>/dev/null | head -1 || true)"
  if [[ -n "$RG" ]]; then
    KIND=flexible
  else
    RG="$(az_cli postgres server list --query "[?name=='${SERVER}'].resourceGroup" -o tsv 2>/dev/null | head -1 || true)"
    if [[ -n "$RG" ]]; then
      KIND=single
    fi
  fi
fi

if [[ -z "$RG" ]]; then
  cat >&2 <<EOF
Could not find Postgres server '${SERVER}' in the current Azure subscription.

Set AZURE_POSTGRES_RESOURCE_GROUP (and optionally AZURE_SUBSCRIPTION_ID) in .env,
or pass them as environment variables. Check: az account show
EOF
  exit 1
fi

if [[ -z "$KIND" ]]; then
  if az_cli postgres flexible-server show --resource-group "$RG" --name "$SERVER" --output none 2>/dev/null; then
    KIND=flexible
  elif az_cli postgres server show --resource-group "$RG" --name "$SERVER" --output none 2>/dev/null; then
    KIND=single
  else
    echo "No Flexible or Single Server named '${SERVER}' in resource group '${RG}'." >&2
    exit 1
  fi
fi

echo "  Resource group: ${RG} (${KIND})"

existing=""
if [[ "$KIND" == flexible ]]; then
  existing="$(az_cli postgres flexible-server firewall-rule show \
    --resource-group "$RG" \
    --server-name "$SERVER" \
    --name "$RULE" \
    --query startIpAddress -o tsv 2>/dev/null || true)"
else
  existing="$(az_cli postgres server firewall-rule show \
    --resource-group "$RG" \
    --server-name "$SERVER" \
    --name "$RULE" \
    --query startIpAddress -o tsv 2>/dev/null || true)"
fi

if [[ "$existing" == "$IP" ]]; then
  echo "Firewall rule '${RULE}' already allows ${IP}."
  exit 0
fi

changed=create
if [[ -n "$existing" ]]; then
  changed=update
  echo "Updating '${RULE}' ${existing} → ${IP}…"
  if [[ "$KIND" == flexible ]]; then
    az_cli postgres flexible-server firewall-rule update \
      --resource-group "$RG" \
      --server-name "$SERVER" \
      --name "$RULE" \
      --start-ip-address "$IP" \
      --end-ip-address "$IP" \
      --output none
  else
    az_cli postgres server firewall-rule update \
      --resource-group "$RG" \
      --server-name "$SERVER" \
      --name "$RULE" \
      --start-ip-address "$IP" \
      --end-ip-address "$IP" \
      --output none
  fi
else
  echo "Creating firewall rule '${RULE}' for ${IP}…"
  if [[ "$KIND" == flexible ]]; then
    az_cli postgres flexible-server firewall-rule create \
      --resource-group "$RG" \
      --server-name "$SERVER" \
      --name "$RULE" \
      --start-ip-address "$IP" \
      --end-ip-address "$IP" \
      --output none
  else
    az_cli postgres server firewall-rule create \
      --resource-group "$RG" \
      --server-name "$SERVER" \
      --name "$RULE" \
      --start-ip-address "$IP" \
      --end-ip-address "$IP" \
      --output none
  fi
fi

if [[ "$PROPAGATION_WAIT_SECONDS" -gt 0 ]]; then
  echo "Waiting ${PROPAGATION_WAIT_SECONDS}s for the ${changed} to take effect…"
  sleep "$PROPAGATION_WAIT_SECONDS"
fi
echo "Firewall rule '${RULE}' now allows ${IP}."
