# PROSEMA internal tooling

Web application for the PROSEMA internal tools (FastAPI, server-rendered Jinja2 + HTMX).
Identity comes from Entra ID; jobs are stored in PostgreSQL and executed by an in-process worker thread.

The desktop GUI (`gui.command`) is unchanged and still uses `requirements.txt`.

## Local setup

1. Create a database (Postgres must already be running natively):

   ```bash
   # Homebrew:
   brew services start postgresql@16
   export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"
   createdb prosema_dev
   ```

2. Copy `.env.example` to `.env` and fill in every value. `DATABASE_URL` should look like:

   ```
   DATABASE_URL=postgresql+psycopg://USER@localhost:5432/prosema_dev
   ```

   `ENTRA_REDIRECT_URI` locally is `http://localhost:8000/auth/callback`.

3. Install the app (from the repo root, Python 3.12):

   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

4. Apply migrations:

   ```bash
   alembic upgrade head
   ```

5. Run the server:

   ```bash
   uvicorn app.main:app --reload
   ```

   Open http://localhost:8000 — unauthenticated visits redirect to Microsoft login.

## Entra ID token configuration

The app reads **group object IDs** from the ID token `groups` claim (not group names).

In the app registration: **Token configuration → Add groups claim → Groups assigned to the application**.

Assign both `PROSEMA-Tools-Users` and `PROSEMA-Tools-Admins` to the application (and to the people who should have those roles). Admins are not inferred from users in code; membership in both groups is required for `["user", "admin"]`.

If the claim is missing entirely, the callback renders an error page instead of silently allowing or denying access.

## Azure App Service

Enable **Always On**. The worker is a `threading.Thread` inside the web process; if the app idles and is unloaded, that thread dies and queued jobs wait until the next request starts the process again.

Queued jobs themselves live in PostgreSQL and are picked up after a restart.

## weclapp tokens (per user)

The web app does not use `WECLAPP_API_TOKEN`. Each signed-in user stores their
own weclapp API token in `user_weclapp_tokens`, encrypted with Fernet.
`WECLAPP_TENANT` is shared application config. `TOKEN_ENCRYPTION_KEY` lives
next to the other secrets (`.env` locally, App Service application setting in
production) — never in the database it protects.

Decrypt happens only when building a weclapp client. Tokens are never written
to `jobs.payload`, sessions, templates, logs, or exception messages.

weclapp returns **401** when the AuthenticationToken is wrong and **403** when
the caller is authenticated but lacks privileges for the operation. A token
whose user has a role but no licence is therefore the 403 case, not 401.

### Rotating `TOKEN_ENCRYPTION_KEY`

Re-encrypting is required; old ciphertext cannot be read with a new key.
Do this with the app stopped, in one database transaction:

1. Stop the web app (no worker claiming jobs).
2. Load every `user_weclapp_tokens.token_encrypted` row.
3. Decrypt each value with the **old** Fernet key.
4. Encrypt each plaintext with the **new** Fernet key.
5. Update all rows, then commit.
6. Set `TOKEN_ENCRYPTION_KEY` to the new key.
7. Start the app.

If the app runs during this window, a request may encrypt with one key while
rows still use the other. Keep the procedure offline.

Sketch (run once, app stopped; keys from the environment, not argv):

```python
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text

old = Fernet(old_key)
new = Fernet(new_key)
engine = create_engine(database_url)
with engine.begin() as conn:
    rows = conn.execute(text("SELECT oid, token_encrypted FROM user_weclapp_tokens")).all()
    for oid, blob in rows:
        conn.execute(
            text("UPDATE user_weclapp_tokens SET token_encrypted = :blob WHERE oid = :oid"),
            {"oid": oid, "blob": new.encrypt(old.decrypt(bytes(blob)))},
        )
```

### Week 3: article registration

Persist the approved batch **before** any weclapp write. A licence failure at
the write step must not discard upload, preview, or approval. The write step
consumes a stored artefact, not transient request state.

## Artikel-Übersicht (weclapp snapshot viewer)

`GET /artikel-uebersicht` pulls all articles from weclapp into immutable
PostgreSQL snapshots (job kind `weclapp_article_snapshot`). The feature is
read-only toward weclapp — no route issues POST or PUT to the API.

Each snapshot stores its own column list at pull time. weclapp's optimistic-lock
field is captured in `article_snapshot_rows.weclapp_version` from the v2 API
field `version` (also exported as `weclapp Version` in the flattened row).

Apply migration `006_article_snapshots` before using the viewer:

```bash
alembic upgrade head
```

## Vendored front-end

No CDN at runtime. Libraries live in `app/static/` and are committed.

| File | Version |
| --- | --- |
| `htmx.min.js` | 2.0.4 |
| `plotly.min.js` | Plotly.js (local copy) |
| `jspreadsheet.js` / `jspreadsheet.css` | Jspreadsheet CE **5.0.4** |
| `jsuites.js` / `jsuites.css` | jSuites **5.13.5** |

Jspreadsheet CE v5 requires jSuites v5. Those two versions are coupled; a
mismatch produces broken widgets rather than a clean error. The grid uses the
v5 API (`worksheets: [{ data, columns }]`) with `parseFormulas: false`.

## Tests

```bash
pytest
```

Teaching notes for Gruppen-Verwaltung (what syncs to weclapp, what does not): [`docs/gruppen-verwaltung.md`](docs/gruppen-verwaltung.md).

To lock groups already referenced by weclapp articles, run `python scripts/lock_groups_from_weclapp.py` (dry-run) then `--commit`. This is a one-off; re-run by hand if articles are created in weclapp outside the registration tool.
