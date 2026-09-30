#!/usr/bin/env bash
# Check out the correct development branch for this machine and sync with origin.
#
# Usage: ./scripts/checkout_work_branch.sh
#
# Creates local dev-dk from origin/dev when missing, then pushes -u origin dev-dk.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
export PROSEMA_REPO_ROOT="${REPO_ROOT}"
# shellcheck source=prosema_dev_branch.sh
source "${REPO_ROOT}/scripts/prosema_dev_branch.sh"

BR="$(prosema_dev_branch)"

echo "Work branch: ${BR} (${prosema_dev_branch_label})"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "Error: not a git repository." >&2
  exit 1
fi

git fetch origin

if git show-ref --verify --quiet "refs/heads/${BR}"; then
  git checkout "${BR}"
elif git show-ref --verify --quiet "refs/remotes/origin/${BR}"; then
  git checkout -b "${BR}" "origin/${BR}"
else
  if ! git show-ref --verify --quiet "refs/remotes/origin/dev"; then
    echo "Error: origin/dev not found. Fetch failed or remote has no dev branch." >&2
    exit 1
  fi
  echo "Creating ${BR} from origin/dev (first time on this machine)."
  git checkout -b "${BR}" "origin/dev"
  git push -u origin "${BR}"
  exit 0
fi

if git rev-parse --abbrev-ref --symbolic-full-name "@{u}" >/dev/null 2>&1; then
  git pull --ff-only
else
  echo "No upstream set. Pushing -u origin ${BR} ..."
  git push -u origin "${BR}"
fi
