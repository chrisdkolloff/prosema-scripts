# Artikelregistrierung

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

The group registry zero-pads Untergruppe codes to three digits
(`Nivelliersystem - 010`). weclapp's `Warengruppe (Auswahl)` list is mixed:
most values use two digits (`Nivelliersystem - 10`), codes ≥ 100 use three.

Do not canonicalise either direction. Match selectable values on **display
name + integer code**; the payload uses weclapp's own option id (and thus
weclapp's literal label). The registry owns the code; weclapp owns its label.

## Deploy order

Production was at `010_sales_article_number_always` when this feature landed.
Deploy `011_job_leases`, confirm the app is up, then deploy
`012_batch_submit_artefacts`. Do not land both on one startup.

Later releases run `alembic upgrade head` from `./release.sh --push` and again
in GitHub Actions before the App Service zip deploy.
