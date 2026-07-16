# Anleitung: PROSEMA Schritt fuer Schritt (macOS)

Diese Anleitung ist fuer macOS und fuer Einsteiger gedacht.

## 1. GitHub-Konto erstellen (nur einmal)

1. Oeffne [https://github.com](https://github.com).
2. Klicke auf **Sign up**.
3. Erstelle ein Konto (E-Mail, Passwort, Benutzername).
4. Bestaetige die Anmeldung (E-Mail von GitHub).
5. Sende mir deinen GitHub-Benutzernamen.

## 2. Repository-Einladung annehmen (nur einmal)

1. Du bekommst von mir eine Einladung fuer das Repository.
2. Oeffne die Einladung (in E-Mail oder auf GitHub).
3. Klicke auf **Accept invitation**.

## 3. GitHub Desktop installieren (nur einmal)

1. Oeffne [https://desktop.github.com](https://desktop.github.com).
2. Lade **GitHub Desktop** herunter und installiere es.
3. Starte GitHub Desktop und melde dich mit deinem GitHub-Konto an.

## 4. Repository auf den Mac laden (clone, nur einmal)

1. In GitHub Desktop: **File -> Clone repository...**
2. Waehle das geteilte Repository aus.
3. Waehle einen Ordner auf dem Mac (z. B. Dokumente).
4. Klicke auf **Clone**.

## 5. Python installieren: genau Version 3.12 (wichtig)

PROSEMA braucht **Python 3.12** mit **Tkinter**.

1. Oeffne [https://www.python.org/downloads/](https://www.python.org/downloads/).
2. Lade **Python 3.12 fuer macOS** herunter (nicht 3.13, nicht 3.11).
3. Fuehre den Installer aus und installiere Python.
4. Oeffne danach das Programm **Terminal** und pruefe:

```bash
python3.12 --version
```

Wenn dort etwas wie `Python 3.12.x` steht, ist alles korrekt installiert.

## 6. Einmalige lokale Einrichtung

1. Oeffne den geklonten Projektordner im Finder.
2. Doppelklicke auf `setup.command`.
3. Warte, bis im Terminal steht, dass die Einrichtung fertig ist.
4. Druecke am Ende die Eingabetaste, um das Fenster zu schliessen.

Das machst du nur einmal (oder erneut nach Python-Aenderungen).

## 7. Bei jeder Nutzung: erst aktualisieren (Pull)

Bevor du arbeitest, immer kurz die neueste Version holen:

1. Oeffne GitHub Desktop.
2. Waehle links das richtige Repository.
3. Klicke oben auf **Fetch origin** / **Pull origin**.

So hast du immer den neuesten Stand.

## 8. GUI starten (empfohlen)

1. In GitHub Desktop: **Repository -> Show in Finder**.
2. Im Finder Doppelklick auf `gui.command`.
3. Das PROSEMA-Fenster oeffnet sich.
4. Werkzeug auswaehlen (z. B. **Artikelnummern erstellen**).
5. Eingabedatei auswaehlen und Ausgabeort kontrollieren.
6. Auf **Generieren** klicken.

Wichtig: Vor dem Start immer pruefen, ob **Input** und **Output** auf die richtigen Dateien/Ordner zeigen. Falls nicht, bitte anpassen.

## 9. macOS-Hinweis beim ersten Start von .command-Dateien

Wenn macOS beim ersten Doppelklick blockiert:

1. Rechtsklick auf die Datei (z. B. `setup.command` oder `gui.command`).
2. **Oeffnen** waehlen.
3. Im Dialog nochmal **Oeffnen** bestaetigen.

Falls noetig: **Systemeinstellungen -> Datenschutz & Sicherheit -> Trotzdem oeffnen**.

## 10. Alternative ohne GUI: run.command

Wenn du stattdessen den Direktlauf nutzen willst:

1. Datei nach `input/input.xlsx` legen.
2. Doppelklick auf `run.command`.
3. Ergebnis liegt danach in `output/processing/output_mit_artikelnummern.xlsx`.

## 11. Wenn etwas nicht klappt

Bitte diese Punkte pruefen:
1. Wurde `setup.command` nach der Python-Installation ausgefuehrt?
2. Ist wirklich Python 3.12 installiert (`python3.12 --version`)?
3. Ist die Excel-Datei vor dem Start geschlossen?
4. Stimmen die Input- und Output-Pfade in der GUI?
5. Bei Fehlern: bitte die genaue Meldung schicken (Screenshot oder Text).
