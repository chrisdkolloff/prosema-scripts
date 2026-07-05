#!/bin/bash
cd "$(dirname "$0")" || exit 1
# shellcheck source=python_env.sh
source "$(dirname "$0")/python_env.sh"

pause() {
    echo ""
    read -r -p "Drücke die Eingabetaste, um dieses Fenster zu schließen." _
}
trap pause EXIT

echo "Artikelnummern-Generator"
echo "------------------------"

PYTHON="$(prosema_venv_python)" || {
    echo ""
    echo "Die Einrichtung wurde noch nicht gefunden."
    echo "Bitte doppelklicke zuerst setup.command."
    exit 1
}

if [ ! -f "input/input.xlsx" ]; then
    echo ""
    echo "Die Datei input/input.xlsx wurde nicht gefunden."
    echo "Bitte speichere deine Excel-Datei im Ordner input/ unter dem Namen input.xlsx."
    exit 1
fi

echo "Starte Verarbeitung ..."
echo ""

"$PYTHON" scripts/processing/artikelnummern.py

echo ""
echo "Wenn oben 'Fertig' steht, findest du das Ergebnis in:"
echo "output/processing/output_mit_artikelnummern.xlsx"
