# Artikelregistrierung: aktuelle weclapp-Auswahlwerte

Stand: 20.10.2026. Fehlerkorrektur für Version 1.4.3.

## Befund und Korrektur

Batch `80d321ba-fb8e-486a-bec8-158432eaa7f7`: 0 von 31 Artikeln angelegt;
weclapp verweigert die alte Auswahl-ID `226370` mit HTTP 400.
Der mitgelieferte Katalog stammt laut `retrievedAt` vom 18.08.2026.
Live sind in den Shop-Auswahllisten `Zubehör` und `Werkzeug` sichtbar.
Tools enthält `010 Zubehör` / `030 Werkzeug`. Zeitpunkt und Urheber der
Änderungen an weclapp-Auswahllisten sind nicht nachgewiesen.

Der Worker liest vor jedem Sendeversuch den aktuellen paginierten Katalog
`customAttributeDefinition`. Nur die zwei Gruppenattribute werden im Sende-
Payload ersetzt. Artikelnummern und andere freigegebene Inhalte bleiben
unverändert. Auch bestehende freigegebene Batches profitieren beim erneuten
Senden. Die tatsächlich verwendeten Gruppen-IDs werden pro erfolgreicher
Zeile als `group_options_resolved` im Audit protokolliert.

Fehlende oder mehrdeutige Auswahlwerte und Katalog-Lesefehler stoppen den
Probelauf vor der ersten Artikelanlage; der Batch bleibt erneut sendbar.
Gruppen werden weiterhin zuerst in Tools gepflegt. Es werden keine Gruppen
umbenannt, keine Auswahlwerte angelegt und keine bestehenden Artikel geändert.

## Validierung

Die fehlende lokale PostgreSQL-Testdatenbank wurde durch eine isolierte,
temporäre pgserver-Installation ersetzt. Beide vollständigen Testsuiten liefen
mit jeweils frisch initialisierter Datenbank und allen passenden Migrationen:

- Entwicklungsstand `dev-dk`: **682 Tests bestanden**.
- Isolierter Produktionsstand `10aa462` plus Fehlerkorrektur: **636 Tests bestanden**.
- Ruff für die neue Logik und neue Tests sowie `git diff --check`: erfolgreich.
- Bestehende Ruff-Befunde in `test_article_registration.py`: unverändert.
- Keine produktiven weclapp-POSTs ausgeführt.

## Release

Der isolierte Hotfix basiert auf Produktionsversion 1.4.2 und enthält nur die
Artikelregistrierung, zugehörige Tests, Dokumentation und Versionsnummer 1.4.3.
Die unveröffentlichten Sales-Navigator-/Kundenberichte-Änderungen des
Entwicklungsbranches sind nicht enthalten. Kein Datenbankschema geändert;
keine neue Migration erforderlich (Produktionsbasis bleibt bei Revision 040).

Nach Freigabe und Deployment kann der vorhandene Batch erneut gesendet werden.
Die Freigabe-Nutzlast muss wegen alter technischer IDs nicht manuell geändert
werden. Der produktive Batch wurde im Rahmen der Implementierung nicht gesendet.
