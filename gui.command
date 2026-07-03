#!/bin/bash
cd "$(dirname "$0")" || exit 1

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
    osascript -e 'display alert "GUI nicht verfügbar" message "Kein Python mit Tkinter in .venv gefunden. Bitte setup.command erneut ausführen (Python von python.org installieren, falls nötig)." as critical'
    exit 1
}

# pythonw exists only with some python.org installs.
if [ -x ".venv/bin/pythonw" ] && [ "$PYTHON" = ".venv/bin/pythonw" ]; then
    exec .venv/bin/pythonw -m gui
fi

# Start GUI in background so the Terminal window can close.
"$PYTHON" -m gui &
exit 0
