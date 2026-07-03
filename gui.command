#!/bin/bash
cd "$(dirname "$0")" || exit 1

pause() {
    echo ""
    read -r -p "Drücke die Eingabetaste, um dieses Fenster zu schließen." _
}
trap pause EXIT

find_gui_python() {
    for candidate in \
        .venv/bin/pythonw \
        .venv/bin/python3.13 \
        .venv/bin/python3.12 \
        .venv/bin/python3.11 \
        .venv/bin/python3 \
        .venv/bin/python; do
        if [ -x "$candidate" ] && "$candidate" -c "import tkinter" 2>/dev/null; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

PYTHON="$(find_gui_python)" || {
    echo ""
    echo "Kein Python mit Tkinter in .venv gefunden."
    echo "Bitte Python von python.org installieren und setup.command erneut ausführen:"
    echo "https://www.python.org/downloads/"
    exit 1
}

echo "PROSEMA Werkzeuge"
echo "-----------------"
echo ""
echo "Das Fenster öffnet sich gleich. Dieses Terminal kann minimiert werden."
echo ""

exec "$PYTHON" -m gui
