# Buchhaltungsexport – Anleitung & FAQ

*Stand: September 2026. Für die Schulungs-Website / interne Hilfe.*

Der Buchhaltungsexport holt Buchungen aus weclapp für einen Datumsbereich und erzeugt eine CSV im Rombro-Format für die Treuhand. Es wird nichts in weclapp geändert — nur gelesen und lokal als Datei abgelegt.

Adresse: [https://tools.prosema.ch/buchhaltung-export](https://tools.prosema.ch/buchhaltung-export)

Unter «Finanzen» in der Navigation.


## Kurz: Ablauf

1. Von- und Bis-Datum wählen (Kalenderfelder, Format ISO im Browser).
2. Optional: «Entwürfe einschließen» / «Storno-Buchungen einschließen» setzen oder abwählen.
3. «Export starten» — ein Hintergrundjob liest weclapp.
4. Status wartet (Seite aktualisiert sich per HTMX), dann «CSV herunterladen».
5. Hinweise aufklappen, wenn Buchungen übersprungen oder auffällig waren.


## Voraussetzungen

- Angemeldet auf PROSEMA.
- Gültiges weclapp-Token unter «Einstellungen» mit Zugriff auf Buchhaltung (`accountingTransaction`, Kontenplan, Währungen). Ohne Token erscheint eine rote Meldung statt des Formulars.
- weclapp-Lizenz für den API-Zugriff (wie bei anderen Schreib-/Lesetools).

Der Export läuft mit deinem persönlichen Token — nicht geteilt zwischen Benutzern. Download-Link und Job-Status gehören nur dir.


## Formular

| Feld | Bedeutung |
| --- | --- |
| Von / Bis | Buchungsdatum in weclapp (`transactionDate`), inklusive Endtag bis 23:59:59 (Europe/Zurich) |
| Entwürfe einschließen | Standard: an — Entwürfe (`draft` / Status DRAFT) mit exportieren |
| Storno-Buchungen einschließen | Standard: aus — Storno-Buchungen (`reverseTransaction`) weglassen |

«Von» darf nicht nach «Bis» liegen.


## CSV-Inhalt (Rombro)

Spalten der Datei:

Belegnummer, Datum, Beschreibung, Betrag, Währung, Wechselkurs, Soll, Haben, MWST Code, MWST Konto.

Wichtig:

- Belegnummer = externe Belegnummer aus weclapp (`externalRecordNumber`), nicht die interne Buchungsnummer.
- Fehlt die externe Belegnummer, wird die ganze Buchung übersprungen (Hinweis in der Liste).
- Soll/Haben = Kontonummern aus dem weclapp-Kontenplan.
- MWST Code und MWST Konto sind in PROSEMA derzeit immer leer — ggf. in Rombro nachpflegen.
- CHF: Wechselkurs-Spalte leer; Fremdwährung: Kurs aus weclapp, wenn gesetzt.

Einfache Buchungen (1 Soll, 1 Haben) → eine CSV-Zeile. Mehrere Zeilen auf einer Seite (z. B. 1 Haben, mehrere Soll) → mehrere CSV-Zeilen mit aufgeteilten Beträgen. Buchungen mit mehreren Soll- und mehreren Haben-Zeilen werden nicht automatisch gemappt und erscheinen als übersprungen mit Hinweis.


## Job-Status

| Status | Was tun |
| --- | --- |
| Wartet / Läuft | Seite offen lassen oder später mit `?job=…` in der URL zurück |
| Erfolgreich | Zusammenfassung (Zeilen, gelesene Buchungen, übersprungen) + Download |
| Fehlgeschlagen | Fehlertext; «Erneut versuchen», Token/Lizenz prüfen |

Die CSV liegt serverseitig unter einer Job-ID. Wenn die Datei später fehlt («Exportdatei nicht mehr vorhanden»), Export erneut starten.


---

## FAQ

### Warum sehe ich kein Formular?

weclapp-Zugriff fehlt — Meldung und Link zu «Einstellungen». Token hinterlegen und testen.

### Export startet, aber Download fehlt

Job noch nicht «Erfolgreich» — warten. Bei Fehler: Hinweise und «Erneut versuchen». Nur der Benutzer, der den Export gestartet hat, darf die Datei laden.

### 0 Zeilen, obwohl Buchungen da sein sollten

Zeitraum prüfen (weclapp-Datum, nicht Belegdatum anderer Systeme). Entwürfe standardmässig ein — wenn alles Entwurf war und du sie abgewählt hast, kann leer rauskommen. Hinweis «Keine exportierbaren Zeilen» wenn Buchungen da waren, aber keine Zeile gebaut werden konnte.

### Buchungen «übersprungen»

Typische Gründe in «Hinweise»:

- externe Belegnummer fehlt;
- keine oder unvollständige Buchungszeilen;
- mehrere Soll- und mehrere Haben-Zeilen (nicht unterstütztes Muster);
- Kontonummer im Kontenplan nicht gefunden (Soll/Haben leer, trotzdem evtl. Zeile).

In weclapp Beleg pflegen oder Buchung vereinfachen, dann Zeitraum erneut exportieren.

### Soll ≠ Haben in der Hinweisliste

Bei 1:1-Buchungen: Warnung, Export trotzdem. Bei aufgespaltenen Mehrzeilen-Buchungen: Summenabweichung — Zeilen werden einzeln exportiert, Hinweis lesen.

### Storno mit exportieren?

Checkbox «Storno-Buchungen einschließen» — sonst werden Storno-Buchungen weggelassen.

### Entwürfe absichtlich weglassen?

«Entwürfe einschließen» abhaken — dann nur gebuchte (nicht-DRAFT) Transaktionen.

### Ändert der Export etwas in weclapp?

Nein. Read-only über die API.

### Welches Encoding?

UTF-8 CSV mit Kopfzeile — für Rombro/Excel üblich öffnen.

### Kann ich den gleichen Zeitraum nochmal exportieren?

Ja, neuer Job, neue Datei. Alte Server-Datei kann weggeräumt sein — immer die frische Download-Schaltfläche nutzen.

### Unterschied zu Artikel- oder Bezugsquellen-Tools?

Buchhaltungsexport ist nur Finanz-Buchungsjournal → Rombro. Kein Bezug zu [Artikelregistrierung](artikel-registrierung-anleitung.md) oder [Bezugsquellenregistrierung](bezugsquellenregistrierung-anleitung.md).


## Kurz für die Schulung

> Token setzen, Von/Bis wählen, Entwürfe/Storno bewusst setzen, exportieren, Hinweise lesen, CSV an die Treuhand. Belegnummer = externe Belegnummer in weclapp — ohne die Nummer keine Zeile. Komplexe Mehr-Mehr-Buchungen manuell in weclapp klären.
