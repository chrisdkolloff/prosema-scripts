# Artikelübersicht – Anleitung & FAQ

*Stand: September 2026. Für die Schulungs-Website / interne Hilfe.*

Die Artikelübersicht holt alle Verkaufsartikel aus weclapp in PROSEMA und zeigt sie in einer durchsuchbaren Tabelle. Du kannst filtern, als Excel exportieren, mit [Noa](noa-artikel-assistent.md) Fragen stellen und — unter bestimmten Bedingungen — Änderungen vorbereiten und nach weclapp schreiben.

Adresse: [https://tools.prosema.ch/artikel-uebersicht](https://tools.prosema.ch/artikel-uebersicht)

Angemeldet sein musst du; für manche Aktionen (z. B. Umnummerierung) zusätzlich Admin.


## Kurz: Was passiert bei «Neue Abfrage starten»?

1. PROSEMA liest alle Artikel aus weclapp (dauert ein paar Minuten).
2. Es entsteht ein neuer Datenstand (Snapshot) mit Zeitstempel — die alten Stände bleiben erhalten.
3. Die Abfrage ist read-only gegenüber weclapp: Beim Pull passiert in weclapp nichts.
4. Schreiben in weclapp gibt es nur über den Modus «Ändern» → Vorschau → Bestätigen (siehe unten).

Es kann immer nur eine Abfrage gleichzeitig laufen. Wenn schon eine läuft, ist der Button deaktiviert.


## Schritt für Schritt: Erste Abfrage

1. In der Navigation «Artikelübersicht» öffnen.
2. «Neue Abfrage starten» klicken.
3. Die Seite aktualisiert sich automatisch, bis der Stand «Abgeschlossen» ist (oder eine Fehlermeldung erscheint).
4. In der Liste aller Abfragen den Zeitstempel anklicken → du landest in der Tabelle.

Tipp: Notiere dir den Zeitstempel des neuesten Stands. Viele Funktionen («Ändern», Nummernvergabe bei der Artikelregistrierung) beziehen sich auf den aktuellsten abgeschlossenen Stand.


## In der Tabelle arbeiten

### Filter

- Suche: Artikelnummer oder Name (Teiltreffer).
- Hauptgruppe / Untergruppe: Codes aus der Gruppenverwaltung (nicht die Shopify-Auswahllisten in weclapp).
- Nur aktive Artikel: standardmässig an — inaktive ausblenden. Für gezielte Fragen an Noa kann es sinnvoll sein, die Checkbox abzuhaken.

Mit «Filtern» wird die Tabelle neu geladen. Die URL merkt sich die Filter — du kannst sie teilen oder bookmarken.

### Tabelle & Seiten

- Pro Seite sind 250 Zeilen sichtbar; unten blätterst du weiter.
- Die erste Spalte bleibt beim Scrollen sichtbar (eingefroren).
- Oben siehst du: «Gefiltert: *x* von *y* Zeilen».

### Excel

«Als Excel herunterladen» exportiert genau den aktuellen Filter (inkl. Noa-Auswahl, falls aktiv). Maximal 50 000 Zeilen pro Export — bei mehr musst du enger filtern.

Dateiname ungefähr: `prosema-artikel_YYYY-MM-DD_HHMM.xlsx`.


## Noa (Modus «Lesen»)

Noa ist der KI-Assistent in der oberen Karte. Im Modus «Lesen» beantwortet sie Fragen zur Artikelliste — z. B. zählen, filtern, sortieren, Gruppen auflisten.

- Eine Beispielfrage erscheint als Platzhalter im Eingabefeld (wechselt zufällig).
- Nach «Fragen» siehst du eine Antwort; passende Artikel werden in der Tabelle ausgewählt (sofern die Treffermenge nicht zu gross ist).
- «Auswahl aufheben» entfernt die Noa-Filterung wieder.

Was du fragen darfst, was schiefgeht und wie die Banner zu lesen sind: [Noa – Anleitung & FAQ](noa-artikel-assistent.md).

Wenn Noa deaktiviert ist, erscheint ein Hinweis statt des Formulars.


## Modus «Ändern» (Schreiben nach weclapp)

«Lesen» und «Ändern» umschaltest du oben in der Karte.

«Ändern» ist nur möglich, wenn alle Punkte stimmen:

1. Du schaust den neuesten abgeschlossenen Datenstand an (nicht einen älteren aus der Historie).
2. Die Abfrage ist höchstens 24 Stunden alt.
3. weclapp-Zugriff ist konfiguriert (Token unter «Einstellungen»).

Sonst ist «Ändern» ausgegraut; dort steht auch, warum — oft hilft «Neue Abfrage starten».

### Typischer Ablauf

1. Modus «Ändern» wählen.
2. Gewünschte Änderung beschreiben → «Vorschlagen» (Noa erstellt eine Vorgabe).
3. «Vorschau öffnen» → PROSEMA holt live aus weclapp und zeigt Zeile für Zeile, was sich ändern würde.
4. Zeilen abwählen, die du nicht willst → Bestätigen → Schreiben nach weclapp.

Alternativ: unter «Vorgabe manuell korrigieren» Felder und Operationen (Wort ersetzen, Text ersetzen, …) selbst bauen → «Vorschau».

Wichtig:

- Gilt der aktuelle Tabellenfilter — oder nur markierte Zeilen in der Tabelle. Das Suchfeld oben wählt für die Vorgabe keine Artikel aus.
- Bei Textoperationen ist die Reihenfolge entscheidend (z. B. längere Begriffe zuerst ersetzen).
- «Wort ersetzen» trifft nur eigenständige Wörter — «verbinder» ändert nicht «Winkelverbinder».

### Was lässt sich in «Pass 1» ändern?

Primär Textfelder wie Prosema-Artikelname, Prosema-Langtext, Kurzbeschreibung (je nach weclapp-Setup). Kein Ersatz für beliebige Felder in weclapp.

### Gruppen umhängen (Kategorie)

Artikel einer anderen Haupt-/Untergruppe zuordnen (weclapp Artikelkategorie), ohne Artikelnummer zu ändern: im Modus «Ändern» an Noa formulieren, z. B. «Ordne alle Artikel, deren Nummer mit 060.020 beginnt, der Gruppe 100.130 zu.»

Mehr Kontext: [`docs/gruppen-verwaltung.md`](gruppen-verwaltung.md).

### Artikelnummer neu vergeben (Admin)

Wenn Nummer und Gruppe nicht mehr zusammenpassen, kann ein Admin nach Gruppenwechsel eine Umnummerierung vorschlagen lassen. Das ist ein eigener, strenger Flow mit Shopify-/Bezugsquellen-Warnungen — nur für Admins, nur am aktuellen Stand.

Shopify-SKUs werden von PROSEMA nicht automatisch überall mitgezogen; Warnungen ernst nehmen. Lieferantenbezug und Preise: [Bezugsquellenregistrierung](bezugsquellenregistrierung-anleitung.md).


## Zusammenhang mit anderen Tools

### Artikelregistrierung

Neue Artikel legst du über die Artikelregistrierung an — nicht über die Übersicht. Ablauf und FAQ: [Artikelregistrierung – Anleitung](artikel-registrierung-anleitung.md).

Die Registrierung braucht einen Artikel-Snapshot für freie Nummern und warnt, wenn der Stand älter als 24 Stunden ist. Im Batch siehst du den Stand der Artikelübersicht und kannst «Aktualisieren» starten.

### Gruppenverwaltung

Filter Hauptgruppe/Untergruppe und Nummernschema (`MMM.SSS.…`) kommen aus der Gruppenverwaltung.


## Alte Datenstände

PROSEMA behält mehrere Snapshots (u. a. die letzten Abfragen und monatliche Archive). Ältere Stände kannst du noch ansehen und exportieren — aber nicht im Modus «Ändern» bearbeiten. Für Schreibaktionen immer zuerst eine frische Abfrage.


---

## FAQ

### Warum dauert die Abfrage so lange?

Es werden alle Artikel aus weclapp gelesen und lokal gespeichert. Je nach Menge und weclapp-Antwortzeit sind mehrere Minuten normal. Seite offen lassen — sie lädt neu, wenn fertig.

### Kann ich während der Abfrage weiterarbeiten?

Ja, andere PROSEMA-Seiten gehen. Eine zweite Abfrage parallel starten geht nicht.

### Was ist der Unterschied zwischen «Lesen» und «Ändern»?

- Lesen: Noa beantwortet Fragen; nichts wird in weclapp geändert.
- Ändern: Noa (oder das manuelle Formular) erzeugt Vorgaben für echte Updates — aber erst nach deiner Vorschau und Bestätigung.

Mehr zu Noa: [noa-artikel-assistent.md](noa-artikel-assistent.md).

### Warum ist «Ändern» ausgegraut?

Meistens: falscher Datenstand (nicht der neueste), Stand älter als 24 h, oder Abfrage noch nicht «Abgeschlossen». Text unter den Buttons erklärt es; oft hilft «Neue Abfrage starten».

### Spiegelt die Tabelle live-weclapp?

Nein. Es ist ein Screenshot zum Zeitpunkt der Abfrage. Für aktuelle Zahlen: neue Abfrage. Für Schreibvorgänge holt die Vorschau trotzdem live aus weclapp, ob der Artikel noch so aussieht.

### Ich habe gefiltert, aber Noa/Ändern trifft andere Artikel?

Die Vorgabe bezieht sich auf den Listenfilter (Hauptgruppe, Suche, …) und optional markierte Zeilen — nicht auf das Noa-Fragefeld allein. Noa-Auswahl in der Tabelle ist ein zusätzlicher Filter, solange «Auswahl aus der Frage» aktiv ist.

### Excel-Export schlägt fehl («Zu viele Zeilen»)

Mehr als 50 000 Zeilen im aktuellen Filter. Hauptgruppe einschränken, Suche verfeinern oder «Nur aktive» nutzen.

### Noa sagt «zu gross für eine Auswahl»

Über 5000 Treffer — die Tabelle wird ungefiltert gezeigt. Frage eingrenzen; siehe [Noa-FAQ](noa-artikel-assistent.md).

### Kann ich alte Snapshots löschen?

Als Nutzer nicht manuell. PROSEMA räumt alte Stände im Hintergrund auf (Rolling Window + Monatsarchive). Für den Alltag: einfach den neuesten Stand verwenden.

### Ändert die Artikelübersicht etwas an Shopify?

Nein, ausser indirekt über weclapp-Felder, die du bewusst änderst. Shopify-Listen Hauptwarengruppe/Warengruppe werden bei Gruppen-Umhängen nicht mitgeschrieben. Bei Umnummerierung: SKU in Shopify ggf. manuell anpassen.

### Wo finde ich Fehlerdetails, wenn die Abfrage fehlschlägt?

Auf der Detailseite des fehlgeschlagenen Stands steht die Fehlermeldung. Typisch: weclapp nicht erreichbar, Token ungültig, Lizenz — «Einstellungen» prüfen und Abfrage wiederholen.

### Muss ich auf tools.prosema.ch sein?

Für produktives Arbeiten mit weclapp-Schreibzugriff ja — wie bei der Gruppenverwaltung. Lokal kannst du Snapshots ansehen; Schreibpfade hängen vom Setup ab.


## Kurz für die Schulung

> Einmal «Neue Abfrage starten», neuesten Stand öffnen, mit Filtern und Noa (Lesen) recherchieren. Änderungen in weclapp nur im Modus «Ändern», am frischen Stand, immer über Vorschau und bewusstes Bestätigen. Für neue Artikel: Artikelregistrierung — die Übersicht ist Katalog, Suche und kontrolliertes Ändern, kein Ersatz für den Import.
