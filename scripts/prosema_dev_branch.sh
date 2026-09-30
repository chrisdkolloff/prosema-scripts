#!/usr/bin/env bash
# Resolve the day-to-day development branch for this machine.
#
# Primary operator (Chris): `dev`
# Everyone else (e.g. Dennis): `dev-dk`
#
# Override anytime: export PROSEMA_DEV_BRANCH=my-branch
#
# Primary detection (first match wins):
#   1. File .prosema-primary-operator in repo root (gitignored, optional)
#   2. Hostname listed in scripts/prosema_primary_hostnames (one per line)
#
# shellcheck shell=bash

prosema_repo_root() {
  if [[ -n "${PROSEMA_REPO_ROOT:-}" ]]; then
    echo "${PROSEMA_REPO_ROOT}"
    return 0
  fi
  local here
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  echo "${here}"
}

prosema_short_hostname() {
  hostname -s 2>/dev/null || hostname
}

prosema_is_primary_operator() {
  local root host line file
  root="$(prosema_repo_root)"
  if [[ -f "${root}/.prosema-primary-operator" ]]; then
    return 0
  fi
  file="${root}/scripts/prosema_primary_hostnames"
  if [[ ! -f "${file}" ]]; then
    return 1
  fi
  host="$(prosema_short_hostname)"
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%%#*}"
    line="$(echo "${line}" | tr -d '[:space:]')"
    [[ -z "${line}" ]] && continue
    if [[ "${host}" == "${line}" ]]; then
      return 0
    fi
  done < "${file}"
  return 1
}

prosema_dev_branch() {
  if [[ -n "${PROSEMA_DEV_BRANCH:-}" ]]; then
    echo "${PROSEMA_DEV_BRANCH}"
    return 0
  fi
  if prosema_is_primary_operator; then
    echo "dev"
  else
    echo "dev-dk"
  fi
}

prosema_dev_branch_label() {
  if prosema_is_primary_operator; then
    echo "primary operator → dev"
  else
    echo "secondary operator → dev-dk"
  fi
}
