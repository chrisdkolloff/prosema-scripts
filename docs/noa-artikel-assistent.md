# Noa – Artikel-Assistent (Anleitung & FAQ)

*Stand: September 2026. Ergänzung zur [Artikelübersicht](artikel-uebersicht.md).*

Noa ist der KI-Assistent in PROSEMA für Fragen und Vorschläge rund um die Artikelliste. Du findest Noa oben in der Karte auf einem abgeschlossenen Artikel-Snapshot ([Artikelübersicht](https://tools.prosema.ch/artikel-uebersicht)).

Noa ersetzt weder weclapp noch Excel — sie nutzt den gespeicherten Datenstand des Snapshots und die Werkzeuge, die PROSEMA dafür vorsieht.


## Lesen vs. Ändern

| Modus | Button | Was Noa tut |
| --- | --- | --- |
| Lesen | «Fragen» | Antworten, zählen, filtern; Treffer können in der Tabelle ausgewählt werden. |
| Ändern | «Vorschlagen» | Vorgabe für Textänderungen, Gruppen-Umhängen oder (Admin) Umnummerierung — schreibt noch nichts. Du startest danach selbst die Vorschau. |

Details zum Schreiben nach weclapp (24-Stunden-Regel, Vorschau, Bestätigen): Abschnitt «Modus Ändern» in der [Artikelübersicht](artikel-uebersicht.md).


## Worauf Noa sich stützt

- Immer der Snapshot, den du gerade geöffnet hast — nicht live-weclapp.
- Der Zeitstempel ist der Beginn der Abfrage, nicht unbedingt der Moment «Abgeschlossen».
- Frisch registrierte Artikel fehlen, bis eine neue Abfrage gelaufen ist.
- Zahlen in Antworten sollen aus den Abfrage-Werkzeugen kommen; Noa soll nichts erfinden. Manchmal schlägt die automatische Prüfung fehl (siehe unten).

Es gibt keinen Chat-Verlauf: Jede Eingabe ist eine eigene Anfrage. Bestätigen für Änderungen passiert nur in der Vorschau-Oberfläche, nicht mit «Ja/Nein» im Textfeld.


## Gut funktionierende Fragen (Beispiele)

Orientierung an dem, wofür Noa gebaut ist — Formulierungen können variieren:

- «Wie viele Artikel gibt es?» / «… pro Hauptgruppe?»
- «Wie aktuell sind die Daten und wie viele Artikel sind drin?»
- «Welche Artikel von Dural wiegen mehr als 2 kg?»
- «Zeig mir alle eloxierten Artikel» (über Volltextsuche)
- «Was sind die teuersten Artikel bei den Duschsystemen?» (Sortierung, kein erfundener Mindestpreis)
- «Welche Artikel in der Hauptgruppe Profile sind aus Messing?»
- «Artikel, die im Shop aktiv sind, aber in weclapp nicht aktiv»
- «Welche Artikel haben keine EAN-Nummer?»
- «Welche Untergruppen gibt es bei den Profilen?»
- «Welche Mengeneinheiten kommen vor?»

Im Eingabefeld rotiert ein zufälliges Beispiel als Platzhalter.


## Was du fragen kannst (Lesen)

Noa hat Zugriff auf den Katalog der Snapshot-Spalten (Namen, Preise, Masse, Gruppen, Shop-Attribute, Lieferant, …) mit festen Operatoren (gleich, enthält, grösser als, beginnt mit, …).

Typische Aufgaben:

- Artikel suchen und sortieren (`artikel_suchen`)
- Zählen, auch gruppiert (`artikel_zaehlen`)
- Einen Artikel anhand der Prosema-Artikelnummer (`artikel_details`)
- Haupt- und Untergruppen aus der Gruppenverwaltung mit Stückzahlen (`gruppen_auflisten`)
- Vorkommende Einheiten (`einheiten_auflisten`)
- Metadaten zum Datenstand (`datenstand`)

Antworten sind kurz (ein paar Sätze). Die vollständige Trefferliste siehst du in der Tabelle; Noa listet höchstens wenige Beispiele im Text.

Tipps für bessere Treffer:

- Material, Farbe, Oberfläche, «eloxiert», «Messing»: lieber breit über Volltext formulieren als eine einzelne Spalte raten.
- «Edelstahl» trifft nicht automatisch «Edelstahl V2A» — eher «enthält Edelstahl».
- Superlative («teuerste», «schwerste»): Sortierung — keine erfundene Preis- oder Gewichtsgrenze.
- Hauptgruppe in Filtern ist der deutsche Name, nicht der dreistellige Code (Code steht in der Artikelnummer `MMM.SSS.…`).
- Bei Zählungen und Preisen nennt Noa den Datenstand mit.


## Was du nicht (oder nur eingeschränkt) fragen kannst

### Spalte gegen Spalte

«Verkaufspreis kleiner als Einkaufspreis» oder «Gewicht grösser als VPE» geht nicht — Filter vergleichen immer eine Spalte mit einem festen Wert, nie zwei Spalten untereinander.

### Numerische Vergleiche auf Text-/Identifikator-Feldern

Nicht sinnvoll bzw. abgelehnt:

- VPE 1 / VPE 2 / VPE 3 (gemischte Schreibweisen wie `1,00` und `1.000`)
- EAN/GTIN, Lieferanten-Art.-Nr., Referenz/Matchcode
- Lieferantennummer als Zahl

Beispiel-Ablehnung: «VPE grösser als 10» — Noa soll erklären, dass numerischer Vergleich dort nicht zuverlässig ist.

### Felder ausserhalb des Katalogs

Wenn eine Spalte im Snapshot-Katalog nicht existiert (z. B. Lieferzeit), kann Noa die Frage nicht sauber beantworten — sie soll sagen, was fehlt, statt zu raten.

### Alles ausserhalb der Artikelliste

Keine allgemeine Weltkenntnis, keine Shopify-Admin-Aktionen, kein «schreib mir eine E-Mail», kein Ersetzen von weclapp durch Raten.

### Ändern: Was Noa nicht als Vorgabe ausdrücken kann

Im Modus Ändern gelten extra Grenzen (Details auch in [Artikelübersicht](artikel-uebersicht.md)):

- Kein «Feld auf XYZ setzen» — nur Text ersetzen oder entfernen (vier Operationen).
- Kein Platzhalter `*` für «alles».
- Kein gezieltes Einfügen fehlender Leerzeichen (z. B. «mm» → « mm»), wenn dadurch korrekte Werte kaputtgehen würden.
- Gruppen-Umhängen: Ziel als `MMM.SSS`, Scope über Filter — Artikelnummern ändern sich dabei nicht.
- Umnummerierung: keine Wunsch-Zielnummer vom Benutzer; Admin-Thema mit eigenen Ablehnungsgründen.
- `&` im Suchbegriff einer Textoperation wird abgelehnt.


## Was in der Oberfläche passiert (Ergebnisse & Fehler)

Nach «Fragen» / «Vorschlagen» erscheint ein Banner mit deiner Frage und dem Ergebnis. Farbe und Text hängen vom Ergebnistyp ab:

| Ergebnis | Bedeutung | Typisch was tun |
| --- | --- | --- |
| Antwort + Auswahl in der Tabelle | Treffer gefunden und verifiziert | Tabelle prüfen; «Auswahl aufheben» zum Zurücksetzen |
| Gelbe Warnung «Antwort nicht geprüft» | Antwort da, Zahlen konnten nicht gegen die Daten abgeglichen werden | Zahlen kritisch lesen; ggf. präzisere Frage oder Filter in der Tabelle |
| «Keine Zusammenfassung» | Rohresultat, Modell hat keinen Fliesstext geliefert | Tabelle / Banner-Text lesen |
| Keine Treffer (`no_result`) | Filter ergab 0 Zeilen | «Warum keine Treffer?» wenn angeboten; «Nur aktive» oder Gruppe prüfen |
| Grau / zurückgewiesen | Frage ausserhalb der Möglichkeiten | Formulierung ändern oder manuell filtern |
| Rot «Anfrage fehlgeschlagen» | Technischer Fehler (Modell, Timeout, Parsing) | Später erneut versuchen; bei Dauerfehler Admin |
| Noa nicht aktiv | Assistent abgeschaltet oder kein abgeschlossener Snapshot | Einstellungen / zuerst Abfrage starten |

Weitere UI-Hinweise:

- Mehr als ca. 5000 Treffer: keine Tabellen-Auswahl — Frage eingrenzen.
- Leere Eingabe: «Bitte eine Frage eingeben.»
- Frage gehört einem anderen Benutzer oder anderem Snapshot: Link «Auswahl aufheben» bzw. Snapshot wechseln.
- Modell nicht erreichbar: Hinweis zur Sprachmodell-Schnittstelle (Konfiguration / Azure).

Im Modus Ändern: erfolgreiche Vorgabe → «Vorschau öffnen»; Validierungsfehler stehen in `hinweis_de` im Banner (z. B. leerer Suchbegriff, Feld nicht erlaubt, Warnung bei riskantem Ersetzen).


## Modus «Ändern» – Kurzüberblick

Noa schlägt nur vor; PROSEMA schreibt erst nach deiner Vorschau und Bestätigung.

| Intent | Beispiel |
| --- | --- |
| Texte umbenennen | «In Untergruppe X: Winkel-Abschlussprofil → Winkelprofil, danach …» |
| Gruppe wechseln | «Alle Artikel mit Nummer beginnend 060.020 → Gruppe 100.130» |
| Umnummerierung (Admin) | «Welche Artikel passen nicht zur Kategorie?» / «Umnummerierung vorschlagen für …» |

Reihenfolge der Textoperationen ist wichtig; «Wort ersetzen» vs. «Text ersetzen» ist nicht dasselbe (siehe [Artikelübersicht](artikel-uebersicht.md)).

Scope für Vorgaben: aktueller Listenfilter und/oder markierte Zeilen in der Tabelle — nicht das Suchfeld allein.


---

## FAQ

### Warum antwortet Noa «Datenstand vom …» bei jeder Zählung?

Damit klar ist, dass die Zahl zum Snapshot gehört, nicht zu live-weclapp.

### Warum steht in der Antwort nur «47 Artikel» und fast keine Namen?

Absicht — die Liste steht im Raster. Noa soll nicht hunderte Zeilen wiederholen.

### Die Tabelle zeigt andere Zeilen als erwartet

Checkliste:

1. Steht «Auswahl aus der Frage» im Banner? → «Auswahl aufheben» oder engere Frage.
2. Ist «Nur aktive Artikel» an? Noa-Auswahl schaltet das manchmal aus — Filter bewusst setzen.
3. Alte `frage=…` in der URL? Anderen Snapshot oder Auswahl zurücksetzen.

### «Warum keine Treffer?» — wann klicken?

Wenn Noa 0 Treffer meldet, aber du Artikel erwartest. PROSEMA erklärt dann oft einen zu strengen Filter (z. B. exakte Gleichheit statt «enthält»).

### Noa nennt eine Zahl, die ich nicht nachvollziehen kann

Bei gelber «nicht geprüft»-Warnung: nicht blind vertrauen. Frage schärfer stellen («wie viele mit Filter …») oder in der Tabelle manuell filtern und zählen.

### «Die Anfrage konnte nicht innerhalb der zulässigen Schritte beantwortet werden»

Noa hat zu viele Werkzeug-Schritte gebraucht. Einfachere Frage stellen oder in zwei separate Fragen teilen.

### Kann ich Noa bitten, direkt in weclapp zu speichern?

Nein. Im Modus Ändern immer: Vorschlagen → Vorschau öffnen → Zeilen wählen → Bestätigen.

### Funktioniert Noa auf alten Snapshots?

Lesen: ja, für diesen Stand. Ändern: nur am neuesten abgeschlossenen Stand und innerhalb von 24 Stunden — sonst ist der Modus gesperrt.

### Kann Noa neue Artikel anlegen?

Nein. Neue Verkaufsartikel → [Artikelregistrierung](artikel-registrierung-anleitung.md).

### Unterscheidet Noa «Einheit» und «Verkaufseinheit»?

Ja — das sind getrennte Felder (`Stk.` vs. `Stück`). Fragen explizit formulieren.

### Kann Noa Preise in Euro und Franken vermischen?

Verkaufspreis (CHF, Punkt als Dezimal) und Einkaufspreis (EUR netto, Punkt) sind getrennte Spalten — Vergleiche nur mit festen Schwellen, nicht miteinander.

### Was, wenn Noa «derzeit nicht aktiv» ist?

Der Assistent ist in der Umgebung abgeschaltet oder nicht konfiguriert. Lesen/Ändern über Noa geht dann nicht; Filter und Excel in der Artikelübersicht schon.


## Kurz für die Schulung

> Noa kennt nur den geöffneten Artikel-Snapshot. Lesen = recherchieren und Auswahl in der Tabelle. Ändern = Vorschlag, nie Sofort-Schreiben. Keine Spalte-gegen-Spalte-Fragen, keine VPE-Vergleiche, kein «Feld auf Wert setzen». Bei riesigen Treffermengen Frage verengen; bei Warnungen Banner und Tabelle mitlesen.
