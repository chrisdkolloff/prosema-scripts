# PROSEMA — guide for AI coding agents

This file is for **LLMs** (Cursor Agent, etc.) working in this repo when the human operator is not the original developer. Read it before changing code, committing, or deploying.

Human onboarding (macOS, GitHub Desktop): [`ANLEITUNG.md`](ANLEITUNG.md).  
Developer setup and architecture notes: [`README.md`](README.md).

---

## Warn the human operator

Before starting non-trivial work, tell the user in plain language (German is fine):

1. **Small fixes** (one bug, one screen, a few files) are usually fine with your help.
2. **Large projects** (new feature across many modules, schema changes, weclapp write paths, assistant behaviour, pricing/numbering rules) need **Chris’s review** — do not deploy without coordination.
3. **Production writes to weclapp** are dangerous. Live article creation/updates must follow [`docs/artikel-registrierung.md`](docs/artikel-registrierung.md) (test article **`999.999`** only unless explicitly approved).

---

## Git branches (mandatory)

| Branch | Who | Purpose |
|--------|-----|---------|
| **`dev-dk`** | Dennis / secondary machines | All day-to-day commits and pushes |
| **`dev`** | Chris / primary developer machine | Same role on the primary laptop |
| **`main`** | Release only | Squash-merge from the work branch triggers **production deploy** |

**Never commit directly to `main`.** Always work on the machine’s work branch (`dev-dk` or `dev`).

### Which branch is this machine?

Logic lives in [`scripts/prosema_dev_branch.sh`](scripts/prosema_dev_branch.sh):

- Override: `export PROSEMA_DEV_BRANCH=...`
- Primary (uses **`dev`**): hostname in [`scripts/prosema_primary_hostnames`](scripts/prosema_primary_hostnames) or file `.prosema-primary-operator` in repo root (gitignored)
- Otherwise: **`dev-dk`**

Check out and sync:

```bash
./scripts/checkout_work_branch.sh
```

### Commit and push workflow

1. `./scripts/checkout_work_branch.sh` (stay on the correct branch; pull latest)
2. Make changes; run `pytest` (and fix failures)
3. Commit on **`dev-dk`** (or `dev` on primary machine)
4. `git push origin dev-dk` (or `dev`)

Do **not** push to `main` except via the release script below.

---

## Release and deploy (production)

Production site: **https://tools.prosema.ch** (Azure App Service).

Deploy path:

1. Work branch (`dev-dk` or `dev`) is squash-merged into **`main`** (one commit)
2. **`main` is pushed** → GitHub Actions [`.github/workflows/main_prosema-tools-prod.yml`](.github/workflows/main_prosema-tools-prod.yml) builds and deploys
3. **`./release.sh --push`** also runs **Alembic migrations** against production Postgres **before** the push (from the operator laptop, not from GitHub)

Release commands (must be on the **work branch** for this machine):

```bash
./release.sh              # pytest + lint; shows next steps
./release.sh --dry-run --push   # preview squash message + migration plan
./release.sh --push       # migrate prod DB, bump version, squash-merge, push main + reset work branch
```

Requirements for `--push`: `.env` with `PRODUCTION_DATABASE_URL`, Azure CLI (`az login`), Python 3.12 venv with `pip install -e ".[dev]"`.

**Inform the team** before `./release.sh --push`: pushing `main` deploys live within minutes. See [`docs/deploy-koordination.md`](docs/deploy-koordination.md).

After release, the work branch is **reset to match `main`** and force-pushed (`--force-with-lease`). That is intentional.

---

## Repository map

| Path | Role |
|------|------|
| [`app/`](app/) | FastAPI web app (Jinja2 + HTMX), job worker thread, routes under `app/routes/` |
| [`core/`](core/) | Shared domain logic (numbering, article fields) |
| [`migrations/`](migrations/) | Alembic DB migrations — always add a revision for schema changes |
| [`scripts/`](scripts/) | CLI utilities, release helpers, offline processing, weclapp helpers |
| [`scripts/weclapp/article_import.py`](scripts/weclapp/article_import.py) | **Library + template writer only** — CLI article **create** is retired; use web `/artikel-registrierung` |
| [`scripts/job_spec.py`](scripts/job_spec.py) | Shared CLI argparse helpers for offline Excel scripts |
| [`tests/`](tests/) | pytest suite — run before commit/release |
| [`docs/`](docs/) | Feature docs and operator guides (German) |

Entry point: `uvicorn app.main:app --reload` (local), `app.main:app` on Azure.

Auth: Microsoft Entra ID; group IDs in token. Admin vs user from Entra groups (see README).

Secrets: `.env` locally (never commit). Web weclapp tokens are **per user** in Postgres (encrypted), not `WECLAPP_API_TOKEN`.

---

## Documentation index (prefer these over guessing)

| Topic | Doc |
|-------|-----|
| Article registration (web) | [`docs/artikel-registrierung.md`](docs/artikel-registrierung.md), [`docs/artikel-registrierung-anleitung.md`](docs/artikel-registrierung-anleitung.md) |
| Article overview / snapshots | [`docs/artikel-uebersicht.md`](docs/artikel-uebersicht.md) |
| Supply sources | [`docs/bezugsquellenregistrierung-anleitung.md`](docs/bezugsquellenregistrierung-anleitung.md) |
| Accounting export | [`docs/buchhaltungsexport-anleitung.md`](docs/buchhaltungsexport-anleitung.md) |
| NOA assistant | [`docs/noa-artikel-assistent.md`](docs/noa-artikel-assistent.md) |
| Shopify images | [`docs/shopify-produktbilder-anleitung.md`](docs/shopify-produktbilder-anleitung.md) |
| Groups / weclapp sync | [`docs/gruppen-verwaltung.md`](docs/gruppen-verwaltung.md) |
| weclapp API notes | [`docs/weclapp-api-ueberblick.md`](docs/weclapp-api-ueberblick.md) |
| Dependencies | [`docs/dependencies.md`](docs/dependencies.md) |
| Deploy coordination | [`docs/deploy-koordination.md`](docs/deploy-koordination.md) |

---

## Coding conventions

- Python **3.12**; match existing style (ruff in dev extras).
- Minimize diff scope; do not refactor unrelated code.
- DB changes: new Alembic revision under `migrations/versions/`, never edit old revisions.
- Front-end assets in `app/static/` are **vendored** (no CDN); Jspreadsheet/jSuites versions must stay paired (see README).
- Jobs: persisted in PostgreSQL; long work runs in the in-process worker — keep App Service **Always On** in production.

---

## Offline CLI scripts

- `run.command` → `scripts/processing/artikelnummern.py` (Excel article numbers).
- Other batch tools: run the matching file under `scripts/` with `--help` (export, reports, weclapp tests).

## Scratch / non-production paths

- [`scripts/tmp/`](scripts/tmp/) — one-off probes and experiments; **not** part of the deployed app; safe to ignore unless a task explicitly references a file there.
- [`output/`](output/) — local GUI/script output (gitignored contents).
- [`data/Branding/`](data/Branding/) — brand assets, not application logic.

---

## What not to do

- Commit `.env`, tokens, or production URLs.
- Run live weclapp writes outside documented test rules.
- Skip `pytest` before release.
- Force-push `main`.
- Assume GitHub Actions can run migrations (it cannot reach Azure Postgres firewall).
