#!/usr/bin/env bash
# Shared helpers for PostgreSQL client binaries (pg_dump, psql).
# Production runs a newer major than typical local servers; pg_dump must be
# at least as new as the server it dumps from.

pg_client_brew_prefix() {
  if [[ -n "${HOMEBREW_PREFIX:-}" && -d "${HOMEBREW_PREFIX}/opt" ]]; then
    printf '%s' "$HOMEBREW_PREFIX"
    return 0
  fi
  if [[ -d /opt/homebrew/opt ]]; then
    printf '%s' /opt/homebrew
    return 0
  fi
  if [[ -d /usr/local/opt ]]; then
    printf '%s' /usr/local
    return 0
  fi
  return 1
}

pg_client_major_from_version_string() {
  # "pg_dump (PostgreSQL) 18.6 (Homebrew)" -> 18
  sed -E 's/.*PostgreSQL\) ([0-9]+).*/\1/' <<<"$1"
}

pg_client_major_for_bin() {
  local bin="$1"
  [[ -x "$bin" ]] || return 1
  pg_client_major_from_version_string "$("$bin" --version 2>/dev/null)"
}

# Prepend the highest-version Homebrew PostgreSQL client bin directory to PATH.
ensure_pg_client_on_path() {
  local prefix dir major best_major=0 best_dir=""
  prefix="$(pg_client_brew_prefix)" || return 0

  for dir in "${prefix}/opt"/postgresql@*/bin "${prefix}/opt/postgresql/bin"; do
    [[ -d "$dir" && -x "${dir}/pg_dump" ]] || continue
    major="$(pg_client_major_for_bin "${dir}/pg_dump")" || continue
    if [[ "$major" -gt "$best_major" ]]; then
      best_major="$major"
      best_dir="$dir"
    fi
  done

  if [[ -n "$best_dir" ]]; then
    export PATH="${best_dir}:${PATH}"
  fi
}

pg_dump_major() {
  command -v pg_dump >/dev/null 2>&1 || return 1
  pg_client_major_for_bin "$(command -v pg_dump)"
}

server_major_from_psql() {
  local url="$1"
  local version
  version="$(psql "$url" -tAc "SHOW server_version;" 2>/dev/null | tr -d '[:space:]')" || return 1
  sed -E 's/^([0-9]+).*/\1/' <<<"$version"
}

require_pg_dump_new_enough_for_server() {
  local prod_url="$1"
  local server_major dump_major
  server_major="$(server_major_from_psql "$prod_url")" || {
    echo "Could not read production server version (network, firewall, or credentials)." >&2
    return 1
  }
  dump_major="$(pg_dump_major)" || {
    echo "pg_dump not found after PATH setup." >&2
    return 1
  }
  if [[ "$dump_major" -lt "$server_major" ]]; then
    cat >&2 <<EOF
pg_dump is too old for production PostgreSQL ${server_major}.

  pg_dump version: ${dump_major}
  server version:  ${server_major}

Install matching client tools, then retry:

  brew install postgresql@${server_major}
  PATH="/opt/homebrew/opt/postgresql@${server_major}/bin:\$PATH" ./pull-prod-db.sh --yes

(this script prepends Homebrew postgresql@* clients automatically when they are installed)
EOF
    return 1
  fi
}
