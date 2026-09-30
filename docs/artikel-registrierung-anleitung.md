# Artikelregistrierung – Anleitung & FAQ

*Stand: September 2026. Für die Schulungs-Website / interne Hilfe.*

Die Artikelregistrierung ist der vorgesehene Weg, neue Verkaufsartikel in weclapp anzulegen: Lieferanten-Excel oder manuelle Erfassung → prüfen im Raster → freigeben → an weclapp senden.

Adresse: [https://tools.prosema.ch/artikel-registrierung](https://tools.prosema.ch/artikel-registrierung)

Der alte Weg über Desktop-Tools und `article_import.py` ist abgelöst. Technische Details für Entwickler: [`docs/artikel-registrierung.md`](artikel-registrierung.md).


## Ablauf in vier Schritten

1. Datei hochladen oder «Manuell erfassen» → neuer Batch (Entwurf).
2. Im Raster Daten prüfen und korrigieren; Fehler in der Spalte «Status».
3. «Freigeben» — reserviert Nummern und fixiert die Nutzlast (nur Zeilen mit Häkchen «Übernehmen»).
4. «An weclapp senden» — Hintergrundjob legt die Artikel an.

Zwischen Freigabe und Senden existieren die Nummern in PROSEMA noch nicht in weclapp. Nach erfolgreichem Senden steht der Batch auf «Gesendet»; pro Zeile siehst du, was geschrieben wurde.


## Voraussetzungen

- Angemeldet auf PROSEMA (für Senden und neue Einheiten in weclapp: gültiges weclapp-Token unter «Einstellungen»).
- Mindestens ein abgeschlossener Stand der [Artikelübersicht](artikel-uebersicht.md) — sonst geht «Freigeben» nicht (Nummernvergabe).
- Hauptgruppe und Untergruppe müssen in der [Gruppenverwaltung](gruppen-verwaltung.md) existieren; die Dropdowns im Raster kommen von dort, nicht aus den Shopify-Listen in weclapp.

Ohne weclapp-Zugriff kannst du Entwürfe weiter bearbeiten; Senden ist gesperrt (Hinweis auf der Startseite und am Batch).


## Startseite: Upload & Batches

### Vorlage

«Artikelregistrierungsvorlage herunterladen» liefert die aktuelle Excel-Vorlage (Version und Stand stehen auf der Seite). Spaltennamen müssen exakt passen — Gross-/Kleinschreibung ist egal. Die «Feldübersicht» unten auf der Seite listet Pflichtfelder, Typ und Beispiele.

### Upload

- Formate: `.xlsx` oder `.csv`.
- Maximal 2000 Datenzeilen pro Datei.
- Leere Datei, fehlende Pflichtspalten oder doppelte Spaltenüberschriften → Fehlermeldung, kein Batch.
- Gleiche Datei (Hash) schon einmal hochgeladen → Warnung mit Datum und Batch-Nummer; «Trotzdem hochladen» ist möglich.

### Manuell erfassen

1–200 leere Zeilen auf einmal (Standard 20). Sinnvoll für wenige Artikel ohne Lieferantenfile.

### Batch-Liste

Filter nach Status (standardmässig ohne «Verworfen»). Spalten: Zeilen, Fehler, «Geschrieben», Status. Klick auf «Batch #…» öffnet den Editor.


## Im Batch arbeiten

### Status eines Batches

| Status | Bedeutung |
| --- | --- |
| Entwurf | Bearbeiten, Freigeben oder Verwerfen |
| Freigegeben | Nummern fix; «An weclapp senden» möglich |
| Wird gesendet | Job läuft |
| Gesendet | Anlage abgeschlossen (evtl. teilweise fehlgeschlagen — Status-Spalte) |
| Verworfen | Abgebrochen, aus der Standardliste ausgeblendet |

### Raster

- Prosema-Artikelnummer: wird automatisch vergeben (`MMM.SSS.NNNN`), nicht von Hand editierbar.
- Spalte «Status»: Validierungs- oder Schreibfehler.
- «Übernehmen» (Häkchen): nur angehakte Zeilen zählen für Fehlerzählung, Freigabe und Senden.
- Dropdowns für Gruppen, Steuersatz, Shop-Felder, Einheit, … — Werte aus weclapp-Schema bzw. Gruppenverwaltung.
- Einheit unbekannt: im Raster kann eine neue Einheit angelegt werden (schreibt nach weclapp und setzt den Batch ggf. zurück auf Entwurf).
- Mehrere Personen: Banner «Auch geöffnet: …» — Absprache vermeidet überschriebene Edits.

Nach Freigabe sind Zellen read-only, bis du wieder etwas änderst (z. B. neue Einheit) — dann wird der Batch wieder Entwurf und Freigabe ist nötig.

### Filter & Hilfen

Suche, Hauptgruppe, Kategorie, Aktiv, «Nur Fehler». «Leere Zeilen entfernen» nimmt leere Zeilen von der Übernahme aus. «Zeilen hinzufügen» nur im Entwurf (bis 2000 Zeilen gesamt).

«Als Excel herunterladen» — Export des Batches inkl. Nummern und Status (Archiv «was haben wir wann angelegt?»).

### Stand der Artikelübersicht

Unter der Batch-Karte siehst du den verknüpften Snapshot-Stand. Wenn er älter als 24 Stunden ist, erscheint eine Warnung — Nummern könnten mit neueren Artikeln kollidieren. «Aktualisieren» startet eine neue Artikelübersicht-Abfrage (braucht weclapp).

Freigabe verlangt einen existierenden Snapshot; die Warnung blockiert nicht hart, sollte aber ernst genommen werden.


## Freigeben

Voraussetzungen:

- Status Entwurf.
- Bei allen übernommenen Zeilen: kein Fehler in «Status».
- Jede übernommene Zeile hat eine eindeutige vorgeschlagene Artikelnummer.

Der Bestätigungsdialog zeigt Anzahl, Nummernbereich und Snapshot-Stand. Freigabe ist nicht rückgängig machbar in dem Sinne, dass Nummern vergeben und Nutzdaten eingefroren werden — du kannst aber vor dem Senden noch durch Bearbeitung wieder in den Entwurf fallen.

Artikelnummern werden aus Gruppe + laufender Nummer gebildet. Reservierung berücksichtigt den neuesten Artikel-Snapshot und andere offene Batches. Deaktivierte Artikel in weclapp geben ihre Nummer nicht frei.


## An weclapp senden

- Nur im Status «Freigegeben».
- Startet einen Hintergrundjob («Wird gesendet…»); Seite aktualisiert sich.
- Vor dem Schreiben: Probelauf — wenn der fehlschlägt, wird nichts angelegt.
- Einzelne Zeilen können scheitern (z. B. Nummer existiert schon in weclapp, auch wenn inaktiv); andere können trotzdem durchgehen — Meldung und Status-Spalte prüfen.
- Lizenz- oder Token-Fehler: Job bricht ab, nichts oder nur Teilerfolg — Token prüfen und erneut senden (bereits angelegte Zeilen haben weclapp-ID).

Link zum Job erscheint bei Fehlern, falls vorhanden.


## Was du hier nicht machst

- Bestehende Artikel massenhaft ändern → [Artikelübersicht](artikel-uebersicht.md), Modus «Ändern».
- Neue Gruppen anlegen → [Gruppenverwaltung](gruppen-verwaltung.md).
- Artikelnummern manuell frei wählen — PROSEMA vergibt sie nach Schema.
- Lieferantenbezug und Preise — [Bezugsquellenregistrierung](bezugsquellenregistrierung-anleitung.md). Shopify-SKU automatisch mit anlegen geht hier nicht; Fokus ist weclapp-Artikel-Create.


---

## FAQ

### Warum kann ich nicht freigeben?

Häufige Gründe: Zeilen mit Fehler in «Status», fehlende Haupt-/Untergruppe, unbekannte Gruppe, ungültige Pflichtfelder, doppelte oder leere Artikelnummern bei übernommenen Zeilen, oder noch keine Artikelübersicht abgefragt.

### Was bedeutet «Unbekannte Hauptgruppe / Untergruppe»?

Der Text in der Zelle passt nicht eindeutig zur Gruppenverwaltung. Dropdown nutzen oder Bezeichnung wie in der Verwaltung (z. B. «Name - 010»).

### Artikelnummer hat sich geändert, ohne dass ich sie tippte

Nach Änderung der Gruppe vergibt PROSEMA eine passende Nummer neu — Hinweis «Artikelnummer wurde neu vergeben.»

### Muss jede Zeile das Häkchen «Übernehmen» haben?

Nein. Ausgeschlossene Zeilen werden ignoriert (z. B. Leerzeilen oder Testzeilen). Für den Export aus der Lieferantenliste oft sinnvoll, Leeres vorher zu entfernen.

### Freigabe ging, Senden ist ausgegraut

weclapp-Token fehlt oder ist ungültig → «Einstellungen». Entwurf ist nicht mehr nötig; Status muss «Freigegeben» sein.

### Warnung «Artikelübersicht ist X Stunden alt»

Kein harter Stopp, aber Risiko für Nummernkollision. «Aktualisieren» und danach prüfen, ob Nummern noch plausibel sind — bei Zweifel Freigabe vermeiden, bis der Stand frisch ist.

### Vorlage «nicht mehr aktuell» am Batch

Die aktive Vorlagen-Version hat sich geändert, seit der Batch erstellt wurde. Inhaltlich prüfen; für neue Lieferantenfiles immer die neueste Vorlage laden.

### Doppel-Upload derselben Datei

Absichtliche Warnung gegen versehentliches Doppel-Anlegen. Wenn es wirklich ein neuer Versuch sein soll: «Trotzdem hochladen».

### Senden: «Probelauf fehlgeschlagen»

Kein Artikel wurde geschrieben. Status-Spalte / Job-Detail lesen, Daten korrigieren, ggf. Batch wieder bearbeiten (Entwurf) und neu freigeben.

### Senden: «Artikelnummer bereits in weclapp vorhanden»

Die Nummer ist belegt — auch durch inaktive Artikel. Zeile aus dem Batch nehmen oder Gruppe/Nummernlauf klären; ggf. Artikelübersicht aktualisieren.

### Kann ich einen freigegebenen Batch noch ändern?

Ja, solange noch nicht gesendet: Zelle ändern oder Einheit anlegen → Status springt zurück auf Entwurf, Freigabe erneut.

### Verwerfen vs. leere Zeilen entfernen

«Leere Zeilen entfernen» lässt den Batch leben, setzt nur `include` aus. «Verwerfen» markiert den ganzen Batch als verworfen (nur Entwurf).

### Wo sehe ich, was wirklich in weclapp landete?

Status «Gesendet», Spalte «Geschrieben» in der Liste, Status pro Zeile, Excel-Download des Batches, Audit/Job unter «Aufträge» bei Fehlern.

### Einheit «Stk.» vs. «Stück»

Verschiedene Felder (Einheit vs. Verkaufseinheit) mit unterschiedlichen erlaubten Werten — exakt aus Dropdown wählen oder neue Einheit anlegen, wenn vorgesehen.

### Shopify Hauptwarengruppe / Warengruppe

Die Registrierung schreibt weclapp-Felder laut Vorlage. Shopify-Auswahllisten können hinterher fehlen, obwohl die Gruppe in PROSEMA stimmt — siehe [Gruppenverwaltung](gruppen-verwaltung.md).

### Brauche ich tools.prosema.ch?

Für produktives Anlegen in weclapp ja (Token, Einheiten anlegen, Senden). Lokale Umgebungen können je nach Setup eingeschränkt sein.


## Kurz für die Schulung

> Vorlage laden, uploaden oder manuell starten, Gruppen aus der Verwaltung wählen, Fehler in «Status» leeren, Artikelübersicht-Stand beachten, freigeben, dann senden. Nummern kommen automatisch; Häkchen «Übernehmen» steuert, was mitgeht. Ändern bestehender Artikel ist Aufgabe der Artikelübersicht, nicht der Registrierung.
