#!/usr/bin/env bash
# Squash-merge the development branch into main as a single commit, then return to dev.
#
# Usage:
#   ./scripts/squash-merge-dev-to-main.sh --dry-run
#   ./scripts/squash-merge-dev-to-main.sh --push -m "Release subject line"
#   ./scripts/squash-merge-dev-to-main.sh --push --auto-message
#   ./release.sh --push
#
# Environment overrides:
#   DEV_BRANCH=dev MAIN_BRANCH=main

set -euo pipefail

# Avoid interactive pagers when listing commits in the terminal.
export GIT_PAGER=cat

DEV_BRANCH="${DEV_BRANCH:-dev}"
MAIN_BRANCH="${MAIN_BRANCH:-main}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRY_RUN=false
DO_PUSH=false
AUTO_MESSAGE=false
DO_BUMP=false
BUMP_PART="patch"
COMMIT_MESSAGE=""

usage() {
  cat <<'EOF'
Squash-merge dev into main as one commit, reset dev to main, optionally push.

Usage:
  squash-merge-dev-to-main.sh --dry-run
  squash-merge-dev-to-main.sh --push -m "Commit message"
  squash-merge-dev-to-main.sh --push --auto-message

Options:
  --dry-run        Show commits and diff stats without changing branches
  --push           Push main and force-with-lease push dev after squash merge
  --auto-message   Derive the squash commit message from dev commits
  --bump           Bump app/releases.toml (patch) and add a changelog entry
  --no-bump        Do not change the version
  --minor          With --bump, increment minor instead of patch
  --major          With --bump, increment major instead of patch
  -m, --message    Commit message (required unless --dry-run or --auto-message)
  -h, --help       Show this help

Environment:
  DEV_BRANCH   Source branch (default: dev)
  MAIN_BRANCH  Target branch (default: main)

Pushing main triggers the Azure App Service workflow
(.github/workflows/main_prosema-tools-prod.yml).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --push)
      DO_PUSH=true
      shift
      ;;
    --auto-message)
      AUTO_MESSAGE=true
      shift
      ;;
    --bump)
      DO_BUMP=true
      shift
      ;;
    --no-bump)
      DO_BUMP=false
      shift
      ;;
    --minor)
      DO_BUMP=true
      BUMP_PART="minor"
      shift
      ;;
    --major)
      DO_BUMP=true
      BUMP_PART="major"
      shift
      ;;
    -m|--message)
      COMMIT_MESSAGE="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      COMMIT_MESSAGE="$1"
      shift
      ;;
  esac
done

log() {
  echo ""
  echo "==> $*"
}

python_bin() {
  if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
    echo "${REPO_ROOT}/.venv/bin/python"
    return 0
  fi
  if command -v python3.12 >/dev/null 2>&1; then
    echo "python3.12"
    return 0
  fi
  echo "python3"
}

next_versions() {
  "$(python_bin)" "${REPO_ROOT}/scripts/bump_releases_toml.py" --print-next --part "${BUMP_PART}"
}

prefix_message_with_version() {
  local version="$1"
  local message="$2"
  local first rest
  first="$(printf '%s\n' "${message}" | head -n 1)"
  rest="$(printf '%s\n' "${message}" | tail -n +2)"
  if [[ -z "${rest}" ]]; then
    printf '%s: %s\n' "${version}" "${first}"
  else
    printf '%s: %s\n%s\n' "${version}" "${first}" "${rest}"
  fi
}

auto_commit_message() {
  local count
  count="$(git rev-list --count "${MAIN_BRANCH}..${DEV_BRANCH}")"
  if [[ "${count}" -eq 0 ]]; then
    echo "Release $(date +%Y-%m-%d)"
    return
  fi

  local subject
  subject="$(git log -1 --pretty=format:%s "${MAIN_BRANCH}..${DEV_BRANCH}")"
  if [[ "${count}" -gt 1 ]]; then
    subject="${subject} (+$((count - 1)) more)"
  fi

  {
    printf '%s\n\n' "${subject}"
    git log --reverse --pretty=format:'- %s' "${MAIN_BRANCH}..${DEV_BRANCH}"
  } | sed '/^$/d'
}

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "Error: not inside a git repository." >&2
  exit 1
fi

if ! git show-ref --verify --quiet "refs/heads/${DEV_BRANCH}"; then
  echo "Error: source branch '${DEV_BRANCH}' does not exist." >&2
  exit 1
fi

if ! git show-ref --verify --quiet "refs/heads/${MAIN_BRANCH}"; then
  echo "Error: target branch '${MAIN_BRANCH}' does not exist." >&2
  exit 1
fi

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  if [[ "${DRY_RUN}" == true ]]; then
    echo "Warning: tracked changes are not committed (ignored for --dry-run)."
    git status --short --untracked-files=no
    echo
  else
    echo "Error: tracked changes are not committed. Commit or stash them first." >&2
    exit 1
  fi
fi

COMMIT_COUNT="$(git rev-list --count "${MAIN_BRANCH}..${DEV_BRANCH}")"
if [[ "${COMMIT_COUNT}" -eq 0 ]]; then
  echo "Nothing to merge: ${DEV_BRANCH} has no commits ahead of ${MAIN_BRANCH}."
  if [[ "${DO_PUSH}" == true ]]; then
    echo
    echo "Would still push ${MAIN_BRANCH} if it is ahead of origin:"
    echo "  git push origin ${MAIN_BRANCH}"
    if [[ "${DRY_RUN}" == false ]]; then
      log "Pushing ${MAIN_BRANCH} (if needed)"
      git push origin "${MAIN_BRANCH}"
    fi
  fi
  exit 0
fi

if [[ "${AUTO_MESSAGE}" == true && -z "${COMMIT_MESSAGE}" ]]; then
  COMMIT_MESSAGE="$(auto_commit_message)"
fi

NEXT_OLD=""
NEXT_NEW=""
CHANGELOG_MESSAGE="${COMMIT_MESSAGE}"
if [[ "${DO_BUMP}" == true ]]; then
  read -r NEXT_OLD NEXT_NEW < <(next_versions)
  if [[ -n "${COMMIT_MESSAGE}" ]]; then
    COMMIT_MESSAGE="$(prefix_message_with_version "${NEXT_NEW}" "${COMMIT_MESSAGE}")"
  fi
fi

echo "Commits on ${DEV_BRANCH} not yet on ${MAIN_BRANCH} (${COMMIT_COUNT}):"
git log --oneline "${MAIN_BRANCH}..${DEV_BRANCH}"
echo
echo "Diff stat (${MAIN_BRANCH}...${DEV_BRANCH}):"
git diff --stat "${MAIN_BRANCH}...${DEV_BRANCH}"

if [[ "${DRY_RUN}" == true ]]; then
  echo
  echo "Dry run only — no branches changed."
  if [[ -n "${COMMIT_MESSAGE}" ]]; then
    echo
    echo "Would use commit message:"
    echo "${COMMIT_MESSAGE}"
  else
    echo
    echo "Provide a commit message when running without --dry-run."
  fi
  if [[ "${DO_BUMP}" == true ]]; then
    echo
    echo "Would bump version: ${NEXT_OLD} → ${NEXT_NEW} (${BUMP_PART})"
  fi
  if [[ "${DO_PUSH}" == true ]]; then
    echo
    echo "Would push:"
    echo "  git push origin ${MAIN_BRANCH}"
    echo "  git push --force-with-lease origin ${DEV_BRANCH}"
    echo "  (Azure App Service deploys from origin/${MAIN_BRANCH})"
  fi
  exit 0
fi

if [[ -z "${COMMIT_MESSAGE}" ]]; then
  echo "Error: commit message is required. Use -m, --auto-message, or --dry-run." >&2
  usage >&2
  exit 1
fi

START_BRANCH="$(git rev-parse --abbrev-ref HEAD)"

log "Squash-merging ${DEV_BRANCH} into ${MAIN_BRANCH}"
git checkout "${MAIN_BRANCH}"
git merge --squash "${DEV_BRANCH}"

if [[ -n "$(git diff --name-only --diff-filter=U)" ]]; then
  echo "Error: squash merge has conflicts. Resetting ${MAIN_BRANCH} and aborting." >&2
  git reset --hard HEAD
  git checkout "${START_BRANCH}"
  exit 1
fi

if [[ "${DO_BUMP}" == true ]]; then
  log "Bumping version ${NEXT_OLD} → ${NEXT_NEW}"
  "$(python_bin)" "${REPO_ROOT}/scripts/bump_releases_toml.py" \
    --write \
    --part "${BUMP_PART}" \
    --message "${CHANGELOG_MESSAGE}"
  git add "${REPO_ROOT}/app/releases.toml"
fi

git commit -m "${COMMIT_MESSAGE}"

echo
echo "Created squash commit on ${MAIN_BRANCH}:"
git log -1 --oneline

git checkout "${DEV_BRANCH}"
git reset --hard "${MAIN_BRANCH}"

echo "Reset ${DEV_BRANCH} to ${MAIN_BRANCH} ($(git rev-parse --short HEAD))."
echo "Checked out ${DEV_BRANCH} (was on ${START_BRANCH})."

if [[ "${DO_PUSH}" == false ]]; then
  echo "Done. Did not push — run:"
  echo "  git push origin ${MAIN_BRANCH}"
  echo "  git push --force-with-lease origin ${DEV_BRANCH}   # if ${DEV_BRANCH} was already on the remote"
  echo "Azure deploys tools.prosema.ch from origin/${MAIN_BRANCH}."
  exit 0
fi

log "Pushing ${MAIN_BRANCH} to origin"
git push origin "${MAIN_BRANCH}"

log "Pushing ${DEV_BRANCH} to origin (force-with-lease after reset)"
git push --force-with-lease origin "${DEV_BRANCH}"

log "Done"
echo "Azure App Service should deploy from origin/${MAIN_BRANCH}."
