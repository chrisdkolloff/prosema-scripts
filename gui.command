#!/bin/bash
cd "$(dirname "$0")" || exit 1
# shellcheck source=python_env.sh
source "$(dirname "$0")/python_env.sh"

pause() {
    echo ""
    read -r -p "Drücke die Eingabetaste, um dieses Fenster zu schließen." _
}

close_terminal() {
    if [ -n "${TERM_SESSION_ID:-}" ]; then
        osascript -e "tell application \"Terminal\" to close (every window whose id is \"$TERM_SESSION_ID\")" >/dev/null 2>&1 &
    fi
}

PYTHON="$(prosema_find_gui_python)" || {
    echo ""
    echo "Keine virtuelle Umgebung mit Python ${PROSEMA_PYTHON_VERSION} gefunden."
    echo "Bitte setup.command ausführen."
    pause
    exit 1
}

echo "PROSEMA Werkzeuge"
echo "-----------------"
echo ""
echo "Python: $PYTHON ($("$PYTHON" --version))"
echo ""
echo "Das Fenster öffnet sich gleich."
echo ""

"$PYTHON" -m gui
EXIT_CODE=$?

if [ "$EXIT_CODE" -eq 0 ]; then
    close_terminal
else
    pause
fi

exit "$EXIT_CODE"
