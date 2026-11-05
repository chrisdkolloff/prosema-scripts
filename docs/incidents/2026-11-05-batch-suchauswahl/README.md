# Batch-Suche: aktuelle Auswahl aus weclapp

Die Suchfelder auf `/batches/{id}` lesen bei jedem Seitenaufruf die aktuellen
Hauptgruppen aus `customAttributeDefinition` / `Hauptwarengruppe (Auswahl)`,
Kategorien aus `articleCategory` und aktive Lieferanten aus `party`.
Alle Kataloge werden über `iter_pages` vollständig paginiert und mit dem
persönlichen Token des angemeldeten Benutzers gelesen.

Das zusätzliche Feld «Lieferant» bietet Nummern mit Firmennamen als
Suchvorschläge. Nummern filtern exakt; Namen erlauben Teiltreffer ohne
Beachtung der Grossschreibung. Ist in einer älteren Batch-Zeile nur der
Firmenname vorhanden, kann die aktuelle Nummer über den Katalog zugeordnet
werden. Auch die allgemeine Suche berücksichtigt jetzt Firmenname und Nummer.
Die Hauptgruppensuche berücksichtigt historische Bezeichnungen mit Gruppencode
(z.B. «Zubehör - 010» beim aktuellen Auswahlwert «Zubehör»).

Scheitert die Katalogabfrage, bleibt die Batch-Seite verfügbar und zeigt einen
Hinweis. Bereits gesetzte Gruppen- und Kategoriefilter bleiben ausgewählt.
Es wird kein veralteter Dateikatalog als aktueller weclapp-Stand ausgegeben.

Die Änderung betrifft die Suchfilter. Gruppenverwaltung, Zellenauswahl,
Artikelnummernvergabe und Freigabe-/Sendeverhalten bleiben unverändert.
Keine Migration und keine weclapp-Schreiboperation erforderlich.

## Prüfung

`tests/test_batch_filter_options.py` prüft aktuelle Auswahlwerte, inaktive
Lieferanten/Auswahlwerte, Fehlerweitergabe, Lieferantensuche und historische
Gruppenbezeichnungen. API-Aufrufe sind dabei gemockt.

Gesamtsuite auf temporärem PostgreSQL mit Migrationen bis 043:
**760 bestanden, 1 fehlgeschlagen**. Der fehlgeschlagene bestehende Test
`test_retention_keeps_snapshot_within_day_floor_outside_newest_20` betrifft
Snapshot-Aufbewahrung ausserhalb der geänderten Codepfade. Neue Filtertests
bestehen. Ruff für die geänderten Python-Dateien, Jinja-Parsing und
`git diff --check` sind erfolgreich. Keine produktiven API-Aufrufe durchgeführt;
der geschützte Live-Batch konnte nicht per Webzugriff eingesehen werden.

## Veröffentlichung

Release 1.4.7 basiert isoliert auf Produktionsstand 1c8737e (1.4.6).
Enthalten sind ausschliesslich Batch-Suchfilter und linksbündige Darstellung
mit Zeilenumbruch. Kein Schemawechsel gegenüber Produktion (Revision 040),
keine Produktionsmigration notwendig. Die weiteren Entwicklungsänderungen
(Sales Navigator, Kundenberichte, Shopify) sind nicht enthalten.

Prüfung der isolierten Release-Version: **678 Tests bestanden, 1 bestehender
Snapshot-Aufbewahrungstest fehlgeschlagen**. Derselbe Fehler wurde separat
auf dem unveränderten Produktionsstand 1c8737e reproduziert.
Die Koordinationsvorgabe wurde vom Benutzer am 05.11.2026 ausdrücklich für
diesen Release aufgehoben; Veröffentlichung ist autorisiert.
