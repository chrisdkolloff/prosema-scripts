# Shopify Produktbilder – Anleitung & FAQ

*Stand: September 2026. Für die Schulungs-Website / interne Hilfe.*

Unter «Shopify → Produktbilder» lädst du Bilder aus einem SharePoint-Ordner zu passenden Shopify-Produkten hoch. Zuordnung über die PROSEMA-Artikelnummer im Dateinamen und als Varianten-SKU im Shop.

Adresse: [https://tools.prosema.ch/shopify-bilder](https://tools.prosema.ch/shopify-bilder)

Seitentitel in PROSEMA: «Shopify-Bilder».


## Kurz: Ablauf

1. Bilder in SharePoint benennen und in einen Ordner legen (siehe Namenskonvention).
2. Ordner in SharePoint öffnen → «Link kopieren» → in PROSEMA einfügen.
3. Modus wählen (Ergänzen oder Bestehende ersetzen), optional Vorschau.
4. «Starten» — Hintergrundjob liest SharePoint und schreibt nach Shopify.
5. Status und Hinweise lesen; bei Teilerfolg ggf. Fehlerzeilen nacharbeiten.


## Voraussetzungen

Zwei Zugänge, beide pro Benutzer:

| Was | Wo einrichten |
| --- | --- |
| Shopify Admin API | «Einstellungen» → Shopify: App-Schlüssel («Neu») speichern, «Verbindung testen» |
| SharePoint lesen | Beim PROSEMA-Login Microsoft-Zugriff bestätigen (`Files.Read.All` delegiert). Fehlt der Refresh-Token: abmelden und erneut anmelden |

Shop-Domain und Client-ID liegen in der Server-Konfiguration — nicht im Formular.

Das Shopify-Produkt muss existieren; die Variante braucht eine SKU gleich der Artikelnummer (`010.010.0010`). Neue Artikel zuerst in weclapp/Shop anlegen — siehe [Artikelregistrierung](artikel-registrierung-anleitung.md) und Shop-Pflege.


## Dateinamen (wichtig)

Muster: `MMM.SSS.NNNN` plus optional Suffix und Endung.

| Dateiname | Bedeutung |
| --- | --- |
| `010.010.0010-1.JPG` | Farbfoto (Index 1) |
| `010.010.0010-2.JPG` | Strichzeichnung (Index 2) |
| `010.010.0010.JPG` | ohne `-1` → wird wie Index 1 (Farbfoto) behandelt |

Andere Namen werden ignoriert ( erscheinen in den Job-Hinweisen).

macOS-Doppel «010.010.0010-1 2.JPG» wird als Strichzeichnung `-2` normalisiert.

Reihenfolge im Shop: zuerst Farbfotos (Index 1), dann Strichzeichnungen (Index 2). Im Modus «Ergänzen» sortiert PROSEMA bestehende Medien nach diesem Schema mit.

PROSEMA speichert den ursprünglichen Dateinamen im Alt-Text (`src:Dateiname|…`), damit «Ergänzen» erkennt, ob eine Datei schon hochgeladen wurde.


## Formular

### SharePoint-Ordnerlink

Vollständiger «Link kopieren»-URL aus dem Browser — typisch `https://…sharepoint.com/…`.

### Modus

- «Ergänzen» (Standard): nur fehlende Dateinamen hochladen; vorhandene (gleicher Name am Produkt) überspringen; Reihenfolge anpassen.
- «Bestehende ersetzen»: für jeden Artikel im Ordner alle Shopify-Produktbilder löschen und nur die Ordner-Dateien neu hochladen. Checkbox «Ich bestätige das Löschen…» ist Pflicht.

### Optionen

- «Unterordner einbeziehen»: rekursiv durchsuchen.
- «Nur Vorschau (kein Upload)»: zeigt geplante Aktionen (`DRY …` in den Meldungen), ändert Shopify nicht.

### Job-Status

Wie bei anderen Jobs: Status-Anzeige, bei Erfolg Zusammenfassung (hochgeladen, übersprungen, ohne Shopify-Produkt, Fehler). Details oft in «Hinweise» aufklappbar.

Der Job gehört dir — nur dein Benutzer sieht denselben Status/Download-Kontext (`?job=…`).


## Was der Job meldet

Typische Zähler in der Zusammenfassung:

- hochgeladen / übersprungen (Dateiname schon am Produkt)
- Artikel mit Bildern im Ordner (Shopify-Produkt gefunden)
- ohne Shopify-Produkt (SKU im Shop fehlt)
- Fehler (SharePoint, Shopify API, einzelner Artikel)
- bei Ersetzen: Artikel, bei denen Altbilder gelöscht wurden

Der Job gilt als fehlgeschlagen, wenn es Fehler gibt und nichts hochgeladen wurde. Teilerfolg (einige OK, einige FEHLER) kann trotzdem «Erfolgreich» sein — Hinweise lesen.


---

## FAQ

### Job startet nicht sofort mit Fehler «Kein Shopify-Token» / «Kein Microsoft-Zugriff»

Shopify-Schlüssel unter «Einstellungen» hinterlegen. Für SharePoint: aus PROSEMA abmelden, wieder anmelden und Microsoft-Berechtigung für Dateizugriff akzeptieren.

### SharePoint 401 / 403

Link prüfen, Ordner-Rechte, ggf. IT (delegiertes `Files.Read.All`, Admin-Einwilligung). Nach Token-Ablauf: erneut anmelden.

### «ohne Shopify-Produkt» hoch

Keine Variante mit SKU = Artikelnummer — Produkt/Variante im Shop anlegen oder SKU korrigieren.

### Dateien werden ignoriert

Name passt nicht auf `MMM.SSS.NNNN-…` — umbenennen. Keine PDFs o. Ä., nur Bilder mit gültigem Muster.

### Ergänzen lädt nichts hoch, «bereits vorhanden»

Alt-Text enthält schon `src:010.010.0010-1.JPG` — gewollt. Für erzwungenes Neuhochladen: Modus «Bestehende ersetzen» (mit Bestätigung).

### Ersetzen — was genau wird gelöscht?

Alle Medien am Shopify-Produkt, dessen SKU im Ordner vorkommt — danach nur die Dateien aus diesem Lauf. Andere Artikel im Ordner nicht betroffen; Artikel im Shop ohne Datei im Ordner unverändert.

### Vorschau zuerst?

Empfohlen bei neuem Ordner oder nach Umbenennung: «Nur Vorschau» + «Ergänzen», Meldungen prüfen, dann echter Lauf.

### Unterordner

Struktur egal, solange Dateinamen stimmen — oder flach in einen Ordner, ohne «Unterordner einbeziehen».

### Ändert PROSEMA weclapp?

Nein — nur SharePoint lesen und Shopify-Produktmedien schreiben. Artikelstammdaten bleiben in weclapp/Registrierung.

### Umnummerierte Artikel

Neue Artikelnummer = neue SKU in Shopify und neue Dateinamen. Alte Bilder hängen am alten Produkt — manuell im Shop aufräumen oder gezielt «Ersetzen» auf dem neuen SKU-Ordner.

### Verbindung testen

Shopify: «Verbindung testen» in den Einstellungen. SharePoint: indirekt durch Vorschau-Lauf mit kleinem Testordner.


## Kurz für die Schulung

> Dateinamen `Artikelnummer-1` / `-2`, SharePoint-Link kopieren, Shopify-Token + Microsoft-Login, erst Vorschau dann Ergänzen. SKU im Shop = Artikelnummer. Ersetzen nur mit Bestätigung — löscht alle Bilder am betroffenen Produkt.
