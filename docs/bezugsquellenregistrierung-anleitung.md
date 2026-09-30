# Bezugsquellenregistrierung – Anleitung & FAQ

*Stand: September 2026. Für die Schulungs-Website / interne Hilfe.*

Die Bezugsquellenregistrierung verbindet Lieferantenpreislisten mit weclapp: Datei oder Abgleich laden, Zuordnung zu PROSEMA-Artikeln prüfen, Rabatte und EK/VK berechnen, dann ausgewählte Änderungen per API nach weclapp schreiben.

Adresse: [https://tools.prosema.ch/bezugsquellen/neu](https://tools.prosema.ch/bezugsquellen/neu)

Optional danach: «weclapp-Assistent-CSV» für Felder, die der API-Lauf nicht abdeckt — Import manuell in weclapp.

Ein älterer, separater Weg ohne API-Schreiben ist der Bezugsquellenexport unter `/bezugsquellen` (nur CSV für den weclapp-Assistenten). In der Navigation findest du die Registrierung unter «Bezugsquellenregistrierung».


## Ablauf (typisch mit Lieferantenfile)

1. «Vorlage erzeugen» → Excel ausfüllen (Lieferantenartikelnummer, Listenpreis, Rabattcode, EAN, Einheit, …).
2. «Datei prüfen» → Lieferant wählen → Upload startet Parse und Abgleich.
3. Warten, bis Status «Vorschau» ist (Seite lädt neu).
4. Im Raster: Artikel zuordnen, Rabattsätze setzen, Einstellungen (Währung, Kurs, Aufschlag, Preis-Eintritt) prüfen.
5. «Lauf freigeben und schreiben» → weclapp wird in Abschnitten beschrieben.
6. Ergebnis lesen; bei Bedarf «Nächsten Abschnitt schreiben» oder «Erneut abgleichen».
7. Optional: «weclapp-Assistent-CSV herunterladen» und Rest in weclapp importieren.

Alternativ: «Ohne Datei aus weclapp abgleichen» — gleiche Vorschau, aber ohne neue Lieferantenzeilen aus einer Datei (nur Stand in weclapp / lokaler Index).


## Voraussetzungen

- Angemeldet auf PROSEMA.
- Für Abgleich und Schreiben: gültiges weclapp-Token unter «Einstellungen» (Lizenz — sonst bricht Schreiben mit AUTH ab).
- Lieferant ist in PROSEMA hinterlegt und aktiv.
- Pro Lieferant läuft höchstens ein Abgleich oder Schreibvorgang gleichzeitig.
- Für EAN-Treffer ohne gespeichertes Alias: sinnvoller [Artikelübersicht](artikel-uebersicht.md)-Stand (EAN-Suche im Snapshot).
- Neue PROSEMA-Artikel, die noch gar nicht in weclapp existieren: zuerst [Artikelregistrierung](artikel-registrierung-anleitung.md), dann Bezugsquelle zuordnen.


## Startseite

| Aktion | Wirkung |
| --- | --- |
| Vorlage erzeugen | Leere Excel mit aktuellen Spalten (Version siehe Admin «Spalten der Vorlage») |
| Datei prüfen | `.xlsx` / `.csv` einlesen; danach Lieferant wählen (Pflicht) |
| Ohne Datei … abgleichen | Pull-Lauf für Standard-Lieferant der Maske |
| Lauf in der Tabelle | Weiterbearbeiten oder Ergebnis ansehen |

Die Liste auf der Startseite zeigt pro Lauf: Zeit, Lieferant, Status, «· Datei» wenn aus Upload.


## Status eines Laufs

| Status | Bedeutung |
| --- | --- |
| Abfrage läuft… | Index/Resolve-Job |
| Vorschau | Bearbeiten im Raster, Freigabe möglich wenn alles grün |
| Freigegeben | Teil geschrieben, noch Zeilen offen → «Nächsten Abschnitt schreiben» |
| Wird geschrieben… | Apply-Job |
| Geschrieben | Lauf fertig |
| Fehlgeschlagen | Fehlertext; «Erneut abgleichen» |

Datenstand in der Kopfzeile = Beginn der weclapp-Abfrage für diesen Lauf, nicht zwingend «jetzt live».


## Nach dem Upload: Parse-Hinweise

Grüne Info-Box u. a.:

- wie viele Zeilen übernommen wurden;
- Bezugsquellen ohne Preis (Liste);
- zurückgewiesene Zeilen (Format, Pflichtfelder);
- unbekannte Einheit — Zeile bleibt, Einheit muss im Raster gesetzt werden.

Schwere Parse-Fehler stoppen den Upload komplett (mehrere Meldungen in einem Block).


## Abgleich: wie Artikel gefunden werden

Grober Stufenplan pro Lieferantenartikelnummer (SAN):

1. Bekannte Zuordnung (Alias Lieferant ↔ PROSEMA-Artikel) — wird übernommen.
2. EAN-Treffer — Vorschlag; Zeile kann ausgeschlossen sein («Vorschlag über EAN, nicht bestätigt»), bis du sie bestätigst/zuordnest.
3. Kein Treffer — «ohne Artikelzuordnung»; manuell zuordnen, sonst keine Freigabe.

Bei weclapp-Ausfall kann gegen den lokalen Bezugsquellen-Index und die Artikelübersicht (EAN) abgeglichen werden — Hinweis im Lauf.


## Raster & Einstellungen

### Lauf-Einstellungen

Einkaufswährung, Kurs, Verkaufswährung, Aufschlag (%), Preis-Eintritt (Datum). «Einstellungen übernehmen» rechen EK/VK/Marge neu.

Preis-Eintritt ist Pflicht vor dem Schreiben — kein stilles «heute». Überschneidende Preiszeiträume lehnt weclapp ab; anderes Datum wählen.

### Rabatte

- Pro Rabattcode bulk: Rabatt 1 / Rabatt 2 in Prozent («50» = 50 %, nicht 0,5).
- «Kein Rabatt» setzt explizit Null.
- Zähler «Noch ohne Rabattsatz» muss auf 0, bevor Freigabe geht.

### Zeilen

- Gelb markiert: Abweichung Vorlage ↔ weclapp — «Vorlagenwert übernehmen» wo angeboten.
- Ausgeschlossene Zeilen (opacity): z. B. unbestätigter EAN-Vorschlag.
- Einheit bei «neu anlegen» oder «zuordnen» muss gesetzt sein (Dropdown / weclapp-Einheit).

### Artikel manuell zuordnen

Im Grid (oder zugehörige Aktion): PROSEMA-Artikelnummer eingeben — speichert Alias für künftige Läufe.


## Freigabe & Schreiben

Der Button «Lauf freigeben und schreiben» ist deaktiviert, solange:

- Artikelzuordnungen fehlen;
- Rabattsätze fehlen;
- bei neuen Bezugsquellen oder Zuordnungen die Einheit fehlt;
- Preisaktualisierungen ohne Listenpreis vorgesehen sind.

Vor dem Klick: Preis-Eintritt setzen. Die Zusammenfassung nennt Anzahlen (Preisaktualisierung, neu, zuordnen, Umnummerierung, ohne Preis).

Schreiben läuft in Abschnitten — bei vielen Zeilen mehrmals «Nächsten Abschnitt schreiben». Nach AUTH-Fehler (Token/Lizenz) werden folgende Zeilen nicht mehr angefasst; Token prüfen und Lauf neu starten.

Nach «Geschrieben»: Ergebnis-Details (Aktualisiert, Konflikt, Abgelehnt, …) in aufklappbaren Listen.


## weclapp-Assistent-CSV

Download in Vorschau und nach dem Schreiben. Ergänzt den API-Weg — nicht jeder weclapp-Import-Assistent-Fall ist in PROSEMA abgebildet. Datei manuell in weclapp importieren, wenn nötig.

Hinweis aus dem separaten Bezugsquellenexport (manueller CSV-Weg): Spalte Verkaufsartikel-Nummer leer zu lassen kann in weclapp unerwünschte neue Artikel erzeugen — in PROSEMA immer bewusst zuordnen.


## Admin: Spalten der Vorlage

Unter «Spalten der Vorlage» (nur Admin) neue Vorlagenversion aktivieren. Bestehende Läufe behalten ihre Spalten; neue Uploads nutzen die aktive Version.


---

## FAQ

### Warum «Für diesen Lieferanten läuft bereits ein Abgleich»?

Warten, bis der andere Lauf «Vorschau», «Geschrieben» oder «Fehlgeschlagen» ist — pro Lieferant nur ein busy Lauf.

### Datei wird komplett abgelehnt

Typisch: leere Datei, nur Kopfzeile, falsches Format, unbekannte Spalten, doppelte Header, kaputtes Excel/CSV. Meldungen stehen auf der Startseite oder im roten Kasten.

### Freigabe bleibt grau — was zuerst?

Oben die Summary-Zeile lesen (ohne Zuordnung, ohne Rabatt, ohne Einheit, …). Im Grid filtern und Rabatt-Bulk für fehlende Codes nutzen.

### «Preis-Eintritt fehlt»

Datum im Formular setzen und «Einstellungen übernehmen» oder beim Freigabe-Formular mitgeben.

### Preis-Overlap / «überschneidet sich»

Anderes Preis-Eintrittsdatum wählen; nicht raten oder still verschieben.

### Konflikt nach dem Schreiben

Jemand hat die Bezugsquelle in weclapp geändert, seit du abgeglichen hast. Nicht blind nochmal schreiben — «Erneut abgleichen», dann neu freigeben.

### EAN-Vorschlag, Zeile ausgegraut

Bestätigen oder manuell zuordnen; ausgeschlossene EAN-Vorschläge blockieren Freigabe nicht allein, aber unmatched schon — prüfen, ob die Zeile wirklich «ohne Artikelzuordnung» ist.

### Unbekannte Einheit aus der Datei

Im Raster Einheit wählen oder in weclapp anlegen (über Grid-Flow, wenn angeboten). Datei-Einheit ohne Mapping erscheint in der Summary.

### «Ohne Datei abgleichen» — wann?

Preise/Bezugsquellen in weclapp mit lokalem Stand vergleichen, ohne neue SAN aus Excel — z. B. Kontrolle oder Rabatt-Nachpflege.

### Brauche ich die Vorlage jedes Mal neu?

Nein — nur wenn sich Spalten ändern (neue Vorlagenversion) oder der Lieferant ein anderes Layout schickt. Ansonsten gleiche Vorlage wiederverwenden.

### Unterschied Registrierung vs. Bezugsquellenexport?

| | Registrierung (`/bezugsquellen/neu`) | Export (`/bezugsquellen`) |
| --- | --- | --- |
| Schreiben | API (Freigabe) | nein — nur CSV |
| Lieferant | wählbar | fest (Dural) |
| Typischer Einsatz | neue Preisliste + Schreiben | manueller Massenimport-CSV |

### Bezugsquelle und Artikelregistrierung

Artikel anlegen: Registrierung. Lieferantenbezug und Preise: Bezugsquellenregistrierung. Umnummerierung in weclapp kann im Lauf vorkommen — Shopify-SKU bleibt Handarbeit (wie bei Artikel-Umnummerierung).

### Token ok, aber AUTH beim Schreiben

Lizenz in weclapp temporär woanders belegt — Meldung ähnlich «Keine weclapp-Lizenz». Später erneut versuchen; bereits geschriebene Zeilen in der Ergebnisliste prüfen.


## Kurz für die Schulung

> Vorlage → Datei prüfen → in der Vorschau Zuordnung, Rabatt, Einheit und Preis-Eintritt klären → freigeben und schreiben. Ein Lauf pro Lieferant. EAN ohne Alias nicht blind übernehmen. Bei Konflikt neu abgleichen. CSV-Assistent nur für den Rest — nicht als Ersatz für saubere Artikelzuordnung.
