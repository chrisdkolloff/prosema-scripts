#!/bin/bash
cd "$(dirname "$0")" || exit 1

pause() {
    echo ""
    read -r -p "Drücke die Eingabetaste, um dieses Fenster zu schließen." _
}
trap pause EXIT

echo "Artikelnummern-Generator"
echo "------------------------"

if [ ! -f ".venv/bin/activate" ]; then
    echo ""
    echo "Die Einrichtung wurde noch nicht gefunden."
    echo "Bitte doppelklicke zuerst setup.command."
    exit 1
fi

if [ ! -f "input.xlsx" ]; then
    echo ""
    echo "Die Datei input.xlsx wurde nicht gefunden."
    echo "Bitte speichere deine Excel-Datei in diesem Ordner unter dem Namen input.xlsx."
    exit 1
fi

echo "Starte Verarbeitung ..."
echo ""

source ".venv/bin/activate"
python3 scripts/artikelnummern.py

echo ""
echo "Wenn oben 'Fertig' steht, findest du das Ergebnis in:"
echo "output_mit_artikelnummern.xlsx"
