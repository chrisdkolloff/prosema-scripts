# weclapp-API – ein Überblick für Nicht-Techniker

*Stand: Juli 2026*


## Was die weclapp-API **kann**

### Daten aus weclapp auslesen

Das ist der häufigste und sicherste Einsatz. Über die API lassen sich zum Beispiel abrufen:

- **Artikel** – Nummer, Name, Beschreibung, Maße, Gewicht, EAN-Code
- **Preise** – Einkaufs- und Verkaufspreise (je nach Einrichtung)
- **Kategorien** – z. B. Hauptgruppe und Untergruppe
- **Lieferanten** – Firmenname, Lieferantennummer, Bezugsquellen
- **Zusatzfelder** – z. B. Grundmaterial, Oberfläche, Farbe, Verpackung, VPE-Angaben
- **Stammdaten** – Einheiten, Zolltarifnummern, Währungen

In unserem PROSEMA-Projekt nutzen wir genau das: Artikel werden aus weclapp geladen und in eine Masterliste überführt. Davon kann man Berichte erstellen, oder das interaktive Dashboard aufrufen.

### Verbindung und Übersicht prüfen

Mit einem API-Zugang kann man testen, ob die Verbindung funktioniert und wie viele Artikel oder Geschäftspartner im System hinterlegt sind – ohne jeden Datensatz einzeln im Browser aufzusuchen.

### Automatisierung und regelmäßige Abgleiche

Die API eignet sich gut, wenn etwas **wiederholt** passieren soll:

- Aktuelle Artikelstände regelmäßig exportieren
- weclapp-Daten mit einer Excel-Masterliste vergleichen
- Auswertungen erstellen (z. B. fehlende Angaben, Preisübersichten)
- Daten für andere Systeme vorbereiten

### Daten in weclapp schreiben – grundsätzlich möglich

weclapp bietet über die API auch Wege, **neue oder geänderte Daten einzutragen** – Artikel anlegen, Preise setzen, Lieferanten zuordnen usw. Das ist technisch machbar, aber deutlich anspruchsvoller als reines Auslesen.

**Wichtig für PROSEMA:** Aktuell schreiben wir Daten **nicht direkt** über die API zurück nach weclapp. Stattdessen erzeugen wir **Import-Dateien** (CSV), die man in weclapp wie gewohnt per Import einspielt. Das ist bewusst der sicherere und für euch nachvollziehbarere Weg.

### Was weclapp insgesamt über die API abdeckt

Unter anderem Artikel, Kunden und Lieferanten, Aufträge, Lager, Dokumente und Buchhaltung.

---

## Was die weclapp-API **nicht** (oder nur eingeschränkt) kann

### Nicht alles aus der Masterliste kommt aus weclapp

Unsere Masterliste enthält Spalten, die **nur bei PROSEMA** existieren oder woanders gepflegt werden – zum Beispiel:

- SEO-Texte (Meta-Titel, Meta-Beschreibung, Fokus-Keyword)
- Shopify-Tags
- manche Verkaufspreise und interne Statusfelder
- Produktfotos

Diese Angaben liegen oft nicht (oder nicht vollständig) in weclapp. Der API-Export kann sie deshalb nicht automatisch füllen. Umgekehrt gilt: Was in weclapp steht, muss nicht 1:1 mit jeder Excel-Spalte übereinstimmen. Es braucht daher eine Zuordnung (Mapping).

### Bilder und Anhänge sind umständlich

Produktfotos und Dateianhänge sind in weclapp wichtig, lassen sich über die API aber **nicht so einfach** wie Text und Zahlen austauschen. Unser aktueller Artikel-Export über die API liefert **keine Produktfotos**. Dafür bleiben der manuelle Upload in weclapp oder der Datei-Import der praktikablere Weg.


### Schreiben ist fehleranfälliger als Lesen

Wenn man Daten **eintragen oder ändern** will, gelten strenge Regeln:

- Pflichtfelder müssen ausgefüllt sein
- Verknüpfungen (z. B. Kategorie, Lieferant) brauchen oft interne **IDs**, nicht nur den lesbaren Namen
- Manche Felder sind schreibgeschützt oder hängen vom Status ab (z. B. ein abgeschlossener Auftrag)
- Falsche Eingaben werden abgelehnt (früher wurden sie teils still ignoriert, heute kommt eine klare Fehlermeldung)

Deshalb ist der Weg über **CSV-Import in weclapp** für Massenänderungen oft einfacher zu kontrollieren: Man sieht die Datei vorher, weclapp zeigt Import-Vorschauen, und man kann Schritt für Schritt vorgehen.

### Keine separate „Übungsumgebung“

weclapp stellt in der Regel keine eigene Test-Welt nur für die API bereit. API-Zugriffe laufen gegen das echte System. Fehler beim Schreiben können echte Daten betreffen. 