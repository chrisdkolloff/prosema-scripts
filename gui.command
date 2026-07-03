#!/bin/bash
cd "$(dirname "$0")" || exit 1

if [ ! -f ".venv/bin/activate" ]; then
    osascript -e 'display alert "Einrichtung fehlt" message "Bitte zuerst setup.command doppelklicken." as critical'
    exit 1
fi

source ".venv/bin/activate"
exec pythonw -m gui
