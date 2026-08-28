#!/usr/bin/env bash
# Release pipeline for PROSEMA tools — run checks, then squash-merge to main.
# Pushing main triggers Azure App Service (tools.prosema.ch).
#
# Typical usage:
#   ./release.sh --dry-run
#   ./release.sh
#   ./release.sh --push
#
# Checks (pytest, ruff) always run unless skipped. --dry-run skips git
# squash/push and only prints production Alembic current vs head.
#
# What each step does:
#   1. Tests    — pytest (and ruff, if installed)
#   2. Migrate  — alembic upgrade head against production (before the push, so
#                 the schema is ready when Azure starts the new code)
#   3. Release  — optional squash-merge of dev into main, with an auto message
#                 built from the dev commits, then push main + reset/push dev
#
# Environment overrides:
#   DEV_BRANCH=dev MAIN_BRANCH=main

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

DEV_BRANCH="${DEV_BRANCH:-dev}"
MAIN_BRANCH="${MAIN_BRANCH:-main}"
SQUASH_SCRIPT="${ROOT}/scripts/squash-merge-dev-to-main.sh"
MIGRATE_SCRIPT="${ROOT}/scripts/upgrade_prod_db.sh"

DRY_RUN=false
SKIP_TESTS=false
SKIP_LINT=false
DO_PUSH=false
DO_BUMP=true
BUMP_ARGS=()

usage() {
  cat <<'EOF'
Release: run checks on dev, optionally squash-merge to main and push.

Usage:
  release.sh
  release.sh --dry-run
  release.sh --push

Options:
  --dry-run      Run checks, then preview the squash/push (no git changes)
  --skip-tests   Skip pytest
  --skip-lint    Skip ruff
  --push         Upgrade production DB, squash-merge dev into main, bump version, and push
  --no-bump      Do not change app/releases.toml
  --minor        Bump minor version (0.2.2 → 0.3.0)
  --major        Bump major version (0.2.2 → 1.0.0)
  -h, --help     Show this help

Environment:
  DEV_BRANCH    Branch to run from (default: dev)
  MAIN_BRANCH   Release branch (default: main)

Prerequisites:
  - checkout on dev before running
  - Python 3.12 venv with the app installed (pip install -e ".[dev]")
  - Postgres available for pytest
  - PRODUCTION_DATABASE_URL in .env (for --push)

Squash-merge only (no tests):
  ./scripts/squash-merge-dev-to-main.sh --push --auto-message
  ./scripts/squash-merge-dev-to-main.sh --dry-run --auto-message --push

Pushing main deploys to Azure App Service (tools.prosema.ch).
--push runs alembic upgrade head against PRODUCTION_DATABASE_URL first.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true; shift ;;
    --skip-tests) SKIP_TESTS=true; shift ;;
    --skip-lint) SKIP_LINT=true; shift ;;
    --push) DO_PUSH=true; shift ;;
    --no-bump) DO_BUMP=false; shift ;;
    --minor) DO_BUMP=true; BUMP_ARGS=(--minor); shift ;;
    --major) DO_BUMP=true; BUMP_ARGS=(--major); shift ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

log() {
  echo ""
  echo "==> $*"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: required command not found: $1" >&2
    exit 1
  fi
}

require_git_branch() {
  local branch="$1"
  if ! git show-ref --verify --quiet "refs/heads/${branch}"; then
    echo "Error: branch '${branch}' does not exist." >&2
    exit 1
  fi
}

current_branch() {
  git rev-parse --abbrev-ref HEAD
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

preflight() {
  require_cmd git

  if ! git rev-parse --git-dir >/dev/null 2>&1; then
    echo "Error: not inside a git repository." >&2
    exit 1
  fi

  require_git_branch "${DEV_BRANCH}"
  require_git_branch "${MAIN_BRANCH}"

  local branch
  branch="$(current_branch)"
  if [[ "${branch}" != "${DEV_BRANCH}" ]]; then
    echo "Error: checkout ${DEV_BRANCH} first (currently on ${branch})." >&2
    exit 1
  fi

  if [[ ! -x "${SQUASH_SCRIPT}" ]]; then
    echo "Error: missing executable ${SQUASH_SCRIPT}" >&2
    exit 1
  fi
  if [[ ! -x "${MIGRATE_SCRIPT}" ]]; then
    echo "Error: missing executable ${MIGRATE_SCRIPT}" >&2
    exit 1
  fi
}

step_lint() {
  if [[ "${SKIP_LINT}" == true ]]; then
    log "Skipping lint (--skip-lint)"
    return 0
  fi

  local py
  py="$(python_bin)"
  if ! "${py}" -m ruff --version >/dev/null 2>&1; then
    log "Skipping lint (ruff not installed in ${py})"
    return 0
  fi

  log "Linting (ruff check app core tests)"
  if ! "${py}" -m ruff check app core tests >/dev/null; then
    echo "ruff reported issues (not blocking the release):"
    "${py}" -m ruff check app core tests --statistics || true
  fi
}

step_tests() {
  if [[ "${SKIP_TESTS}" == true ]]; then
    log "Skipping tests (--skip-tests)"
    return 0
  fi

  local py
  py="$(python_bin)"
  log "Running tests (${py} -m pytest)"
  "${py}" -m pytest
}

step_prod_migrate() {
  if [[ "${DO_PUSH}" != true ]]; then
    return 0
  fi

  if [[ "${DRY_RUN}" == true ]]; then
    log "Production database (dry run)"
    "${MIGRATE_SCRIPT}" --dry-run
    return 0
  fi

  log "Upgrading production database (alembic upgrade head)"
  "${MIGRATE_SCRIPT}" --yes
}

step_release() {
  if [[ "${DO_PUSH}" != true ]]; then
    return 0
  fi

  local args=(--auto-message --push)
  if [[ "${DO_BUMP}" == true ]]; then
    args+=(--bump)
    if [[ ${#BUMP_ARGS[@]} -gt 0 ]]; then
      args+=("${BUMP_ARGS[@]}")
    fi
  else
    args+=(--no-bump)
  fi
  if [[ "${DRY_RUN}" == true ]]; then
    args+=(--dry-run)
  fi

  log "Squash-merging ${DEV_BRANCH} into ${MAIN_BRANCH} (auto commit message)"
  "${SQUASH_SCRIPT}" "${args[@]}"
}

main() {
  log "PROSEMA tools release pipeline"
  echo "Branch: $(current_branch)"
  if [[ "${DRY_RUN}" == true ]]; then
    echo "Mode: dry run (no changes)"
  fi

  preflight
  step_lint
  step_tests
  step_prod_migrate
  step_release

  log "Done"
  echo ""
  if [[ "${DRY_RUN}" == true ]]; then
    echo "Dry run finished — no next steps."
  elif [[ "${DO_PUSH}" == true ]]; then
    echo "Release pushed. Production schema is at Alembic head."
    echo "Azure should deploy tools.prosema.ch from origin/${MAIN_BRANCH}."
  elif [[ -n "$(git status --porcelain)" ]]; then
    echo "Working tree has changes. Commit them on ${DEV_BRANCH} first, then:"
    echo ""
    echo "  ./release.sh --push"
    echo ""
    echo "Or squash-merge only:"
    echo "  ./scripts/squash-merge-dev-to-main.sh --push --auto-message"
  else
    echo "Checks passed. Squash-merge to main when ready:"
    echo ""
    echo "  ./release.sh --push"
    echo ""
    echo "Or preview the auto commit message:"
    echo "  ./scripts/squash-merge-dev-to-main.sh --dry-run --auto-message --push"
  fi
}

main "$@"
