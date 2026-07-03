#!/bin/bash
cd "$(dirname "$0")" || exit 1

pause() {
    echo ""
    read -r -p "Drücke die Eingabetaste, um dieses Fenster zu schließen." _
}
trap pause EXIT

echo "Einrichtung für den Artikelnummern-Generator"
echo "--------------------------------------------"

if ! command -v python3 >/dev/null 2>&1; then
    echo ""
    echo "Python 3 wurde nicht gefunden."
    echo "Bitte installiere Python 3 von dieser Seite:"
    echo "https://www.python.org/downloads/"
    echo ""
    echo "Falls Homebrew bereits installiert ist, geht auch:"
    echo "brew install python"
    echo ""
    echo "Danach diese Datei bitte noch einmal doppelklicken."
    exit 1
fi

echo "Python gefunden:"
python3 --version

echo ""
echo "Erstelle die lokale Arbeitsumgebung .venv ..."
python3 -m venv .venv

echo ""
echo "Aktualisiere pip ..."
.venv/bin/python3 -m pip install --upgrade pip

echo ""
echo "Installiere benötigte Python-Erweiterungen ..."
.venv/bin/python3 -m pip install -r requirements.txt

echo ""
echo "Fertig. Die Einrichtung war erfolgreich."
echo "Ab jetzt kannst du jedes Mal run.command doppelklicken."
