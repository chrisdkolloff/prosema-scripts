# Gruppenverwaltung – was geht und was nicht

*Stand: August 2026. Zum späteren Schulen der Tools-Website.*

Die **Gruppenverwaltung** pflegt Hauptgruppen und Untergruppen. Daraus entstehen die PROSEMA-Artikelnummern (`MMM.SSS.…`).

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

- Beide Einträge stehen in der Gruppenverwaltung.
- In weclapp erscheinen beide als **Artikelkategorien**: zuerst die Hauptgruppe, die Untergruppe darunter.

Wenn weclapp ablehnt, speichert auch die Tools-Website **nichts**. Es bleibt nichts Halbes stehen.

Eine **weitere Untergruppe** zu einer bestehenden Hauptgruppe legt man auf der Detailseite der Hauptgruppe an. Auf tools.prosema.ch wird diese Untergruppe ebenfalls in weclapp erstellt (unter der bestehenden Hauptgruppe).


## Was funktioniert

- Neue Hauptgruppe **zusammen mit** der ersten Untergruppe anlegen → Tools-Website **und** weclapp.
- Weitere Untergruppe zu einer bestehenden Hauptgruppe hinzufügen → Tools-Website **und** weclapp (nur auf tools.prosema.ch).
- **Umbenennen** (Bezeichnung) → Tools-Website **und** weclapp (nur auf tools.prosema.ch). Wenn weclapp ablehnt, bleibt auch in den Tools der alte Name.
- **Artikel einer anderen Haupt-/Untergruppe zuordnen** → in der Artikelübersicht im Modus **Ändern** an Noa, z. B. «Ordne alle Artikel, deren Artikelnummer mit 060.020 anfangen, der Haupt- und Untergruppe 100.130 zu.» Noa schlägt vor; die Vorschau schreibt in weclapp nur die Artikelkategorie (`articleCategoryId`). Die Artikelnummern bleiben unverändert. Die Shopify-Auswahllisten Hauptwarengruppe/Warengruppe werden nicht mitgeschrieben.
- **Löschen und Wiederherstellen** → Tools-Website **und** weclapp (nur auf tools.prosema.ch). Wenn weclapp die Kategorie nicht löschen kann, bleibt auch in den Tools der alte Stand.
- **Löschen** einer Gruppe mit noch zugeordneten Artikeln (Nummern `MMM.SSS.…` in der Artikelübersicht) wird abgelehnt. Die Warnung enthält einen Text, den man in der Artikelübersicht im Modus Ändern an Noa schicken kann, um die Artikel zuerst umzuhängen.
- Codes und Aliase **in der Tools-Website** pflegen.
- Diagramm der aktiven Gruppen ansehen.


## Was nicht funktioniert

- **Keine weclapp-Änderung vom Laptop.** Lokal wird nur die lokale Datenbank geschrieben. weclapp wird nur von tools.prosema.ch angesprochen.
- **Keine Hauptgruppe allein.** Das Formular verlangt immer die erste Untergruppe mit.
- **Code ändern** gilt nur für die Tools-Website. weclapp wird dabei **nicht** mitgeändert. Auf der Gruppenliste erscheint dann eine Warnung, wenn Tools und weclapp auseinanderlaufen; die Einträge müssen manuell angeglichen werden.
- Die Shopify-Auswahllisten **Hauptwarengruppe** und **Warengruppe** in weclapp werden **nicht** ergänzt. Es entstehen nur die Artikelkategorien (der Gruppenbaum).
- Die Artikelregistrierung prüft Hauptgruppe und Untergruppe **nur** gegen die Gruppenverwaltung. Eine neue Gruppe ist dort gültig, auch wenn sie in den weclapp-Shopify-Listen noch fehlt.
- Eine fehlgeschlagene weclapp-Anlage, -Umbenennung oder -Löschung speichert auch auf der Tools-Website nichts bzw. den alten Stand. Zuerst Token und Rechte prüfen, dann erneut speichern.


## Kurz für die Schulung

> Auf tools.prosema.ch eine neue Gruppe immer als Paar anlegen (Hauptgruppe + Untergruppe). Umbenennen, Löschen und Wiederherstellen gehen dort ebenfalls nach weclapp. Code ändern und Shopify-Listen bleiben Handarbeit bzw. nur in den Tools.
