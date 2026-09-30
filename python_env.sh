#!/bin/bash
# Shared Python 3.12 resolution for PROSEMA launchers.

PROSEMA_PYTHON_VERSION="3.12"
PROSEMA_PYTHON="python${PROSEMA_PYTHON_VERSION}"

prosema_require_system_python() {
    if ! command -v "$PROSEMA_PYTHON" >/dev/null 2>&1; then
        echo ""
        echo "Python ${PROSEMA_PYTHON_VERSION} wurde nicht gefunden."
        echo "Bitte installiere Python ${PROSEMA_PYTHON_VERSION} von:"
        echo "https://www.python.org/downloads/"
        return 1
    fi
    return 0
}

prosema_venv_python() {
    local py=".venv/bin/python${PROSEMA_PYTHON_VERSION}"
    if [ -x "$py" ]; then
        echo "$py"
        return 0
    fi
    return 1
}
