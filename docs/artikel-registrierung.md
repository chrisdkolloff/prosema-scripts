# Artikelregistrierung (Entwickler)

Schulungsanleitung (Deutsch): [`artikel-registrierung-anleitung.md`](artikel-registrierung-anleitung.md).

Upload → grid → Freigeben → Senden. **This is the only supported path** to create
sales articles in weclapp. The desktop/CLI path
`Excel → artikelnummern → import template → article_import.py` is retired.

## Acceptance criteria

1. A user can go from a supplier `.xlsx` to articles in weclapp without touching the CLI.
2. Killing the worker mid-submit and restarting loses no record of what was created.
3. A licence failure at submit time costs nothing but a retry click.
4. The batch Excel download is sufficient on its own to answer "what did we create and when".
5. No CDN requests; the vendored files load from `/static/`.
6. `/artikel-registrierung` no longer says `folgt in Woche 3`.
7. **Every write test that POSTs to weclapp targets group pair `999.999` — no exceptions, including one-row smoke tests.** Live sequences (`010.010`, …) must not be consumed by throwaway work. Deactivating an article does not reclaim its number.

## Retired CLI

`python -m scripts.weclapp.article_import` refuses to create articles and prints
a pointer to `/artikel-registrierung`. Shared helpers stay importable. The
Streamlit/desktop GUI no longer lists the import or article-editor create jobs.

## Numbering and inactive articles

High-water marks read `article_snapshot_rows.article_number` for the latest
completed snapshot **without** filtering on `active`, plus proposed numbers from
non-`discarded` batches. An article number is taken forever.

The submit dry-run existence check is `GET /article?articleNumber-eq=…` with
**no** `active-eq` filter. Confirmed against live weclapp: inactive articles
still appear in that result set.

## Group labels (registry vs weclapp)

The group registry (Gruppenverwaltung) is the only source of valid
Hauptgruppe / Untergruppe values: dropdowns, numbering, and grid validation
all read from there. weclapp's Shopify lists `Hauptwarengruppe (Auswahl)` and
`Warengruppe (Auswahl)` are a write target, not a second catalogue.

Before **every submit attempt**, including retries of approved batches, the worker
reads all pages of `customAttributeDefinition` from the user's current weclapp
tenant. The committed schema is only a historic lookup for removing old group
attribute IDs; its selectable-value IDs are never used for the final group write.

Group values match by name (case-insensitive) and integer code when weclapp's
option includes a code (`Werkzeug - 030` matches `Werkzeug - 30`). A current
option without a code (`Werkzeug`) can match the registry name when unique.
Missing or ambiguous options, unavailable definitions, and catalogue read errors
abort the preflight before any article POST. No automatic group rename or option
creation is performed. Maintain groups in Tools first, then align weclapp's lists.
This is stricter than draft validation: a locally valid group may still fail the
live preflight if the Shopify list has not caught up.

Only the two group custom attributes are rebuilt for sending. Approved content
and article numbers stay unchanged. The refreshed payload is held for this run;
`approved_payload` remains the approval snapshot. Each successful row records
the actual group attribute IDs and option IDs in the audit log under
`group_options_resolved`. A failed batch stays approved and can be retried after
the lists have been aligned; no Excel re-upload or new approval is needed just
to refresh these technical IDs.

## Deploy order

Production was at `010_sales_article_number_always` when this feature landed.
Deploy `011_job_leases`, confirm the app is up, then deploy
`012_batch_submit_artefacts`. Do not land both on one startup.

Later releases run `alembic upgrade head` from `./release.sh --push` before
GitHub Actions deploys the zip. Migrations are not run on GitHub-hosted
runners (Azure Postgres firewall).
