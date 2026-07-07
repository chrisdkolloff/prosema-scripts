#!/bin/bash
# Dural-Bilder nach Prosema-Artikelnummern umbenennen (Kopie in separate Ordner).
#
# Verwendung:
#   ./scripts/processing/rename_dural_images.sh
#   ./scripts/processing/rename_dural_images.sh --dry-run
#
# Umgebungsvariablen (optional):
#   PROSEMA_MASTER   Pfad zur Master-Excel (Standard: input/input.xlsx)
#   PROSEMA_BASE_DIR Basisordner in Dropbox (Standard: Bilder Preisliste)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# shellcheck source=../../python_env.sh
source "$PROJECT_ROOT/python_env.sh"

DEFAULT_BASE="/Users/chris-mbp/Library/CloudStorage/Dropbox/PPROSEMA/Dural/Bilder Preisliste"
MASTER_PATH="${PROSEMA_MASTER:-$PROJECT_ROOT/input/input.xlsx}"
BASE_DIR="${PROSEMA_BASE_DIR:-$DEFAULT_BASE}"

PYTHON="$(prosema_venv_python)" || {
    echo "Virtuelle Umgebung nicht gefunden. Bitte zuerst setup.command ausführen." >&2
    exit 1
}

if [[ ! -f "$MASTER_PATH" ]]; then
    echo "Masterdatei nicht gefunden: $MASTER_PATH" >&2
    exit 1
fi

if [[ ! -d "$BASE_DIR" ]]; then
    echo "Basisordner nicht gefunden: $BASE_DIR" >&2
    exit 1
fi

echo "Dural-Bilder umbenennen"
echo "-----------------------"
echo "Masterdatei: $MASTER_PATH"
echo "Basisordner: $BASE_DIR"
echo ""

ARGS=(--master "$MASTER_PATH" --base-dir "$BASE_DIR")
if [[ "${1:-}" == "--dry-run" ]]; then
    ARGS+=(--dry-run)
    shift
fi

if [[ $# -gt 0 ]]; then
    echo "Unbekannte Argumente: $*" >&2
    echo "Verwendung: $0 [--dry-run]" >&2
    exit 1
fi

cd "$PROJECT_ROOT"
"$PYTHON" -m scripts.processing.rename_dural_images "${ARGS[@]}"
