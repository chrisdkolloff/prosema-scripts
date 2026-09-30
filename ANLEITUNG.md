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

PROSEMA braucht **Python 3.12**.

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

## 8. Web-App (Hauptwerkzeug)

Artikelregistrierung, Artikeluebersicht, Assistent und weitere Tools: **https://tools.prosema.ch** (Microsoft-Anmeldung).

## 9. Optional: Artikelnummern per Doppelklick (Excel)

1. Excel-Datei nach `input/input.xlsx` legen.
2. Doppelklick auf `run.command`.
3. Ergebnis: `output/processing/output_mit_artikelnummern.xlsx`.

## 10. macOS-Hinweis beim ersten Start von .command-Dateien

Wenn macOS beim ersten Doppelklick blockiert:

1. Rechtsklick auf die Datei (z. B. `setup.command` oder `run.command`).
2. **Oeffnen** waehlen.
3. Im Dialog nochmal **Oeffnen** bestaetigen.

Falls noetig: **Systemeinstellungen -> Datenschutz & Sicherheit -> Trotzdem oeffnen**.

## 11. Web-App und KI-Hilfe (Cursor)

Die **Web-Anwendung** (Artikelregistrierung, Artikelübersicht, Assistent, …) läuft auf **https://tools.prosema.ch**. Lokale Entwicklung: siehe [`README.md`](README.md).

Wenn du mit **Cursor** (KI) am Code arbeitest:

1. Repository in Cursor öffnen (gleicher Ordner wie bei GitHub Desktop).
2. Vor Änderungen: `./scripts/checkout_work_branch.sh` im Terminal — du landest auf Branch **`dev-dk`**.
3. Der KI-Assistent soll [`AGENTS.md`](AGENTS.md) lesen (dort: Commits, Release, Warnungen).
4. Kleine Bugfixes: KI kann oft allein helfen. **Grössere Features** oder viele geänderte Dateien: bitte **Chris** einbeziehen, bevor live released wird.
5. Live schalten: nur über `./release.sh --push` (nach Absprache mit dem Team — siehe [`docs/deploy-koordination.md`](docs/deploy-koordination.md)).

## 12. Wenn etwas nicht klappt

Bitte diese Punkte pruefen:
1. Wurde `setup.command` nach der Python-Installation ausgefuehrt?
2. Ist wirklich Python 3.12 installiert (`python3.12 --version`)?
3. Ist die Excel-Datei vor dem Start geschlossen?
4. Liegt die Eingabedatei unter `input/input.xlsx` (bei `run.command`)?
5. Bei Fehlern: bitte die genaue Meldung schicken (Screenshot oder Text).
