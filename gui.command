#!/bin/bash
cd "$(dirname "$0")" || exit 1
# shellcheck source=python_env.sh
source "$(dirname "$0")/python_env.sh"

pause() {
    echo ""
    read -r -p "Drücke die Eingabetaste, um dieses Fenster zu schließen." _
}
trap pause EXIT

PYTHON="$(prosema_find_gui_python)" || {
    echo ""
    echo "Keine virtuelle Umgebung mit Python ${PROSEMA_PYTHON_VERSION} gefunden."
    echo "Bitte setup.command ausführen."
    exit 1
}

echo "PROSEMA Werkzeuge"
echo "-----------------"
echo ""
echo "Python: $PYTHON ($("$PYTHON" --version))"
echo ""
echo "Das Fenster öffnet sich gleich. Dieses Terminal kann minimiert werden."
echo ""

exec "$PYTHON" -m gui
