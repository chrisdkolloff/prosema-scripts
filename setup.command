#!/bin/bash
cd "$(dirname "$0")" || exit 1
# shellcheck source=python_env.sh
source "$(dirname "$0")/python_env.sh"

pause() {
    echo ""
    read -r -p "Drücke die Eingabetaste, um dieses Fenster zu schließen." _
}
trap pause EXIT

echo "Einrichtung für den Artikelnummern-Generator"
echo "--------------------------------------------"

if ! prosema_require_system_python; then
    exit 1
fi

echo "Verwende: $PROSEMA_PYTHON ($($PROSEMA_PYTHON --version))"

echo ""
echo "Erstelle die lokale Arbeitsumgebung .venv (Python ${PROSEMA_PYTHON_VERSION}) ..."
if [ -d ".venv" ]; then
    rm -rf .venv
fi
"$PROSEMA_PYTHON" -m venv .venv

VENV_PYTHON="$(prosema_venv_python)" || {
    echo ""
    echo "Die virtuelle Umgebung konnte nicht eingerichtet werden."
    exit 1
}

echo ""
echo "Aktualisiere pip ..."
"$VENV_PYTHON" -m pip install --upgrade pip

echo ""
echo "Installiere benötigte Python-Erweiterungen ..."
"$VENV_PYTHON" -m pip install -r requirements.txt

echo ""
echo "Fertig. Die Einrichtung war erfolgreich."
echo "Ab jetzt kannst du gui.command oder run.command doppelklicken."
