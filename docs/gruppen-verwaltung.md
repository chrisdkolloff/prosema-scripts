# Gruppen-Verwaltung – was geht und was nicht

*Stand: August 2026. Zum späteren Schulen der Tools-Website.*

Die **Gruppen-Verwaltung** pflegt Hauptgruppen und Untergruppen. Daraus entstehen die PROSEMA-Artikelnummern (`MMM.SSS.…`).

Adresse: [https://tools.prosema.ch/gruppen](https://tools.prosema.ch/gruppen)

Nur **Admins** können anlegen, umbenennen oder löschen. Alle angemeldeten Nutzer können die Liste und das Diagramm ansehen.


## Voraussetzung zum Anlegen in weclapp

1. Auf **https://tools.prosema.ch** arbeiten (nicht lokal, nicht eine andere Adresse).
2. Unter **Einstellungen** ein gültiges **weclapp-Token** hinterlegt haben.
3. Als Admin angemeldet sein.

Ohne Token legt die Website auf tools.prosema.ch **nichts** an – weder in der Tools-Datenbank noch in weclapp.


## Neue Gruppe anlegen (Hauptgruppe + erste Untergruppe)

Auf der Listen-Seite gibt es das Formular **Neue Hauptgruppe mit Untergruppe**.

Ausfüllen:

| Feld | Beispiel |
|---|---|
| Hauptgruppe Code | drei Ziffern, z. B. `010` |
| Hauptgruppe Bezeichnung | z. B. `Zubehör` |
| Untergruppe Code | drei Ziffern, z. B. `030` |
| Untergruppe Bezeichnung | z. B. `Werkzeug` |

**Speichern.** Ein Schritt legt beides an.

Was danach stimmt:

- Beide Einträge stehen in der Gruppen-Verwaltung.
- In weclapp erscheinen beide als **Artikelkategorien**: zuerst die Hauptgruppe, die Untergruppe darunter.

Wenn weclapp ablehnt, speichert auch die Tools-Website **nichts**. Es bleibt nichts Halbes stehen.

Eine **weitere Untergruppe** zu einer bestehenden Hauptgruppe legt man auf der Detailseite der Hauptgruppe an. Auf tools.prosema.ch wird diese Untergruppe ebenfalls in weclapp erstellt (unter der bestehenden Hauptgruppe).


## Was funktioniert

- Neue Hauptgruppe **zusammen mit** der ersten Untergruppe anlegen → Tools-Website **und** weclapp.
- Weitere Untergruppe zu einer bestehenden Hauptgruppe hinzufügen → Tools-Website **und** weclapp (nur auf tools.prosema.ch).
- Codes, Bezeichnungen, Aliase, Löschen und Wiederherstellen **in der Tools-Website** pflegen.
- Diagramm der aktiven Gruppen ansehen.


## Was nicht funktioniert

- **Keine weclapp-Änderung vom Laptop.** Lokal wird nur die lokale Datenbank geschrieben. weclapp wird nur von tools.prosema.ch angesprochen.
- **Keine Hauptgruppe allein.** Das Formular verlangt immer die erste Untergruppe mit.
- **Umbenennen, Code ändern, Löschen** gelten nur für die Tools-Website. weclapp wird dabei **nicht** mitgeändert.
- Die Shopify-Auswahllisten **Hauptwarengruppe** und **Warengruppe** in weclapp werden **nicht** ergänzt. Es entstehen nur die Artikelkategorien (der Gruppenbaum).
- Eine fehlgeschlagene weclapp-Anlage speichert auch auf der Tools-Website nichts. Zuerst Token und Rechte prüfen, dann erneut speichern.


## Kurz für die Schulung

> Auf tools.prosema.ch eine neue Gruppe immer als Paar anlegen (Hauptgruppe + Untergruppe). Dann gibt es sie in den Tools **und** in weclapp. Alles andere (umbenennen, löschen, Shopify-Listen) bleibt Handarbeit bzw. nur in den Tools.
