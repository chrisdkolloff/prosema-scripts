# Anleitung: Artikelnummern erstellen

Diese Anleitung ist für macOS.

## 1. Python 3 installieren

1. Öffne diese Seite: https://www.python.org/downloads/
2. Lade Python 3 für macOS herunter.
3. Öffne die heruntergeladene Datei.
4. Folge den Schritten im Installationsfenster.
5. Prüfen: Öffne das Programm „Terminal“ und schreibe:

```bash
python3 --version
```

Wenn eine Versionsnummer erscheint, ist Python installiert.

Falls Homebrew bereits installiert ist, geht auch dieser Befehl im Terminal:

```bash
brew install python
```

## 2. Einmalige Einrichtung

1. Öffne diesen Ordner im Finder.
2. Doppelklicke auf `setup.command`.
3. Es öffnet sich ein Terminalfenster.
4. Warte, bis dort steht, dass die Einrichtung erfolgreich war.
5. Drücke am Ende die Eingabetaste, damit sich das Fenster schließt.

Das musst du nur einmal machen.

## 3. Wichtiger macOS-Hinweis beim ersten Start

Beim ersten Doppelklick kann macOS eine Meldung zeigen wie:

„kann nicht geöffnet werden“ oder „unbekannter Entwickler“.

Dann:

1. Klicke die Datei mit der rechten Maustaste an.
2. Wähle „Öffnen“.
3. Klicke im Fenster noch einmal auf „Öffnen“.

Das ist nur einmal pro Datei nötig.

Falls das nicht klappt:

1. Öffne „Systemeinstellungen“.
2. Öffne „Datenschutz & Sicherheit“.
3. Klicke bei der blockierten Datei auf „Trotzdem öffnen“.

## 4. Mit der grafischen Oberfläche (empfohlen)

1. Doppelklicke auf `gui.command`.
2. Es öffnet sich kurz ein Terminalfenster und das PROSEMA-Fenster.
3. Wähle links das gewünschte Werkzeug, zum Beispiel **Artikelnummern erstellen**.
4. Klicke bei **Eingabedatei** auf **Durchsuchen…** und wähle deine Excel-Datei.
5. Die **Ausgabedatei** wird automatisch vorgeschlagen. Du kannst sie bei Bedarf ändern.
6. Schließe die Excel-Datei in Excel oder Numbers.
7. Klicke auf **Generieren**.
8. Wenn alles geklappt hat, erscheint eine Meldung **Fertig** und das Ergebnis liegt an dem gewählten Ausgabeort.
9. Schließe das PROSEMA-Fenster — das Terminal schließt sich dabei automatisch mit.

Weitere Optionen findest du unter **Erweitert**. Für den normalen Gebrauch musst du dort nichts ändern.

Beim ersten Doppelklick auf `gui.command` gilt derselbe macOS-Hinweis wie in Abschnitt 3 (rechte Maustaste → Öffnen).

## 5. Alternative: Artikelnummern über run.command

1. Speichere deine Excel-Datei in diesem Ordner.
2. Der Dateiname muss genau so sein:

```text
input.xlsx
```

3. Schließe die Datei in Excel oder Numbers.
4. Doppelklicke auf `run.command`.
5. Warte, bis im Terminalfenster „Fertig“ steht.
6. Drücke die Eingabetaste, damit sich das Fenster schließt.
7. Die neue Datei liegt danach in diesem Ordner und heißt:

```text
output_mit_artikelnummern.xlsx
```

## 6. Test mit Beispieldatei

1. Öffne den Ordner `beispiel`.
2. Kopiere die Datei `input.xlsx`.
3. Gehe zurück in den Hauptordner.
4. Füge die Datei dort ein.
5. Doppelklicke auf `run.command`.
6. Danach sollte die Datei `output_mit_artikelnummern.xlsx` erscheinen.

## 7. Wenn es nicht funktioniert

Prüfe diese Punkte:

1. Wurde `setup.command` schon einmal ausgeführt?
2. Ist die Excel-Datei in Excel oder Numbers noch geöffnet? Dann bitte schließen und noch einmal versuchen.
3. Bei `run.command`: Heißt die Excel-Datei genau `input.xlsx` und liegt sie im gleichen Ordner?
4. Steht eine Fehlermeldung im Fenster oder Protokoll? Dann die Meldung weitergeben.
5. Startet `gui.command` nicht: Python von [python.org](https://www.python.org/downloads/) installieren und `setup.command` noch einmal ausführen (Homebrew-Python unterstützt die Oberfläche oft nicht).
