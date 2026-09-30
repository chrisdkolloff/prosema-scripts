# Deploy-Koordination (tools.prosema.ch)

Kurzinfo für Team und Betrieb, wenn Releases nicht mehr nur vom Hauptentwickler-Rechner kommen.

## Was passiert bei einem Release?

1. Auf dem Entwicklungsbranch (`dev` oder `dev-dk`) laufen Tests und ggf. DB-Migrationen lokal.
2. `./release.sh --push` führt einen **Squash-Merge** in **`main`** aus und pusht `main`.
3. **GitHub Actions** (Workflow `.github/workflows/main_prosema-tools-prod.yml`) baut die App und deployt nach **Azure App Service** (`prosema-tools-prod`).
4. Die Live-Seite **https://tools.prosema.ch** aktualisiert sich typischerweise innerhalb weniger Minuten.

## Wer sollte vorher informiert werden?

Vor `./release.sh --push` (Push auf `main`) kurz Bescheid geben an:

- Personen, die gerade **Artikelregistrierung**, **Bezugsquellen**, **Artikelübersicht** oder **Assistent** nutzen
- Wer **weclapp-Schreibvorgänge** plant (Release kann Worker/Jobs kurz neu starten)

Kein formales Change-Management — aber **kein Release mitten in einem kritischen Batch** ohne Absprache.

## Datenbank

Schema-Updates laufen **vor** dem Deploy über `./release.sh --push` gegen die Produktions-Postgres-URL (`PRODUCTION_DATABASE_URL` in `.env` auf dem Rechner, der das Release ausführt).

GitHub Actions führt **keine** Migrationen aus (Firewall).

## Version sichtbar für Nutzer

Jedes Release mit Bump aktualisiert `app/releases.toml` (Header der Web-App und Seite `/changelog`).

## Branches

| Branch | Bedeutung |
|--------|-----------|
| `dev-dk` | Tägliche Arbeit (Dennis / sekundärer Rechner) |
| `dev` | Tägliche Arbeit (primärer Entwickler-Rechner) |
| `main` | Produktion — nur via Release-Skript |

Details für KI-Agenten: [`AGENTS.md`](../AGENTS.md).
