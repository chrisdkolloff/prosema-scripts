"""Local browser editor for the weclapp article import CSV."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd


def _ensure_project_root() -> None:
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _running_in_streamlit() -> bool:
    return "streamlit.runtime.scriptrunner.script_runner" in sys.modules


def _default_csv_path() -> Path:
    from scripts.paths import DATA_DIR, resolve_path

    env_path = os.environ.get("PROSEMA_IMPORT_CSV", "").strip()
    if env_path:
        return resolve_path(env_path)
    return DATA_DIR / "weclapp_article_import_template.csv"


def _empty_row() -> dict[str, str]:
    from scripts.weclapp.article_import import DEFAULTS, IMPORT_COLUMNS

    return {column: DEFAULTS.get(column, "") for column in IMPORT_COLUMNS}


def _ensure_columns(frame: pd.DataFrame) -> pd.DataFrame:
    from scripts.weclapp.article_import import IMPORT_COLUMNS

    out = frame.copy()
    aliases = {
        "Artikelnr.": "Lieferantenartikelnummer",
        "Hauptwarengruppe": "Hauptgruppe",
        "Warengruppe": "Untergruppe",
    }
    for old, new in aliases.items():
        if old in out.columns and (new not in out.columns or out[new].fillna("").eq("").all()):
            out[new] = out[old]
    for column in IMPORT_COLUMNS:
        if column not in out.columns:
            out[column] = ""
        out[column] = out[column].fillna("").astype(str)
    return out[list(IMPORT_COLUMNS)]


def _dataframe_from_path(path: Path) -> pd.DataFrame:
    from scripts.weclapp.article_import import IMPORT_COLUMNS, load_import_rows

    if path.is_file():
        rows = load_import_rows(path)
    else:
        rows = []
    if not rows:
        rows = [_empty_row()]
    normalized = []
    for row in rows:
        normalized.append({column: str(row.get(column, "") or "") for column in IMPORT_COLUMNS})
    return pd.DataFrame(normalized, columns=list(IMPORT_COLUMNS))


def _rows_from_df(frame: pd.DataFrame) -> list[dict[str, str]]:
    from scripts.weclapp.article_import import IMPORT_COLUMNS

    rows: list[dict[str, str]] = []
    for raw in frame.fillna("").to_dict(orient="records"):
        row = {column: str(raw.get(column, "") or "").strip() for column in IMPORT_COLUMNS}
        if any(row.values()):
            rows.append(row)
    return rows


def _column_config(options: dict[str, list[str]]) -> dict:
    import streamlit as st
    from scripts.weclapp.article_import import RESTRICTED_SELECT_COLUMNS

    config: dict = {}
    for column, values in options.items():
        allow_empty = column not in RESTRICTED_SELECT_COLUMNS
        config[column] = st.column_config.SelectboxColumn(
            column,
            options=([""] + values) if allow_empty else values,
            required=not allow_empty,
        )
    config["Prosema Artikelnummer"] = st.column_config.TextColumn(
        "Prosema Artikelnummer",
        disabled=True,
        help="Wird aus Hauptgruppe und Untergruppe anhand der Masterliste erzeugt.",
        width="medium",
    )
    config["Lieferantenartikelnummer"] = st.column_config.TextColumn(
        "Lieferantenartikelnummer",
        help="Original-Artikelnummer des Lieferanten. Wird nicht nach weclapp hochgeladen.",
        width="medium",
    )
    config["PROSEMA Langtext"] = st.column_config.TextColumn("PROSEMA Langtext", width="large")
    config["Artikelbeschreibung HTML"] = st.column_config.TextColumn(
        "Artikelbeschreibung HTML",
        width="medium",
    )
    config["Produkt-ID (Prosema)"] = st.column_config.TextColumn(
        "Produkt-ID (Prosema)",
        disabled=True,
        help="Wird später von der weclapp-Shopify-Synchronisation gefüllt.",
    )
    config["Varianten-ID (Prosema)"] = st.column_config.TextColumn(
        "Varianten-ID (Prosema)",
        disabled=True,
        help="Wird später von der weclapp-Shopify-Synchronisation gefüllt.",
    )
    return config


def render_app() -> None:
    _ensure_project_root()
    import streamlit as st

    from scripts.weclapp.article_import import (
        IMPORT_COLUMNS,
        dropdown_options,
        generate_article_numbers,
        import_articles,
        save_import_rows,
        validate_import_rows,
    )

    st.set_page_config(
        page_title="PROSEMA Artikel-Import",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.title("weclapp-Artikelimport")
    st.caption("CSV laden, filtern, Werte zuweisen und nach weclapp anlegen.")

    options = dropdown_options()
    default_path = _default_csv_path()

    if "source_path" not in st.session_state:
        st.session_state.source_path = str(default_path)
    if "df" not in st.session_state:
        st.session_state.df = _ensure_columns(_dataframe_from_path(Path(st.session_state.source_path)))
    if "grid_revision" not in st.session_state:
        st.session_state.grid_revision = 0
    if "number_errors" not in st.session_state:
        st.session_state.number_errors = []

    with st.sidebar:
        st.header("Datei")
        path_text = st.text_input("CSV-Pfad", value=st.session_state.source_path)
        col_load, col_save = st.columns(2)
        if col_load.button("Laden", use_container_width=True):
            st.session_state.source_path = path_text
            st.session_state.df = _ensure_columns(_dataframe_from_path(Path(path_text)))
            st.session_state.grid_revision += 1
            st.rerun()
        if col_save.button("Speichern", type="primary", use_container_width=True):
            st.session_state.save_requested = True

        uploaded = st.file_uploader("Oder CSV hochladen", type=["csv"])
        if uploaded is not None:
            upload_id = f"{uploaded.name}:{uploaded.size}"
            if st.session_state.get("last_upload_id") != upload_id:
                from scripts.paths import OUTPUT_DIR

                target = OUTPUT_DIR / "weclapp" / uploaded.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(uploaded.getvalue())
                st.session_state.source_path = str(target)
                st.session_state.df = _ensure_columns(_dataframe_from_path(target))
                st.session_state.grid_revision += 1
                st.session_state.last_upload_id = upload_id
                st.rerun()

        st.header("Filter")
        query = st.text_input("Suche", placeholder="Prosema-Nr., Lieferantenartikelnummer oder Name")
        filter_category = st.selectbox(
            "Kategorie",
            options=["(alle)"] + options.get("Kategorie", []),
        )
        filter_group = st.selectbox(
            "Hauptgruppe",
            options=["(alle)"] + options.get("Hauptgruppe", []),
        )
        filter_active = st.selectbox("Aktiv", options=["(alle)", "Ja", "Nein"])

        st.header("Sammelzuweisung")
        bulk_column = st.selectbox(
            "Spalte",
            options=[
                "Kategorie",
                "Hauptgruppe",
                "Untergruppe",
                "Einheit",
                "Artikeltyp",
                "Aktiv",
                "Im Shop verfügbar",
                "Im Shop aktiv",
                "Bestand übertragen",
                "Gewichtseinheit",
            ],
        )
        bulk_choices = options.get(bulk_column, [])
        if bulk_choices:
            bulk_value = st.selectbox("Wert", options=bulk_choices, key=f"bulk_{bulk_column}")
        else:
            bulk_value = st.text_input("Wert", key=f"bulk_text_{bulk_column}")
        if st.button("Auf gefilterte Zeilen anwenden", use_container_width=True):
            mask = _filter_mask(
                st.session_state.df,
                query=query,
                category=filter_category,
                group=filter_group,
                active=filter_active,
            )
            st.session_state.df.loc[mask, bulk_column] = bulk_value
            st.session_state.grid_revision += 1
            st.success(f"{int(mask.sum())} Zeile(n) aktualisiert.")
            st.rerun()

        st.header("Artikelnummern")
        st.caption("Hauptgruppe und Untergruppe müssen gesetzt sein. Nummern kommen aus der Masterliste.")
        if st.button("Artikelnummern erzeugen", use_container_width=True):
            generated, stats = generate_article_numbers(_rows_from_df(st.session_state.df))
            st.session_state.df = pd.DataFrame(generated, columns=list(IMPORT_COLUMNS))
            st.session_state.number_errors = stats.get("errors") or []
            st.session_state.grid_revision += 1
            if stats["assigned"] or stats["kept"]:
                st.success(f"{stats['assigned']} neu erzeugt, {stats['kept']} behalten.")
            st.rerun()

        if st.button("Leere Zeile hinzufügen", use_container_width=True):
            st.session_state.df = pd.concat(
                [st.session_state.df, pd.DataFrame([_empty_row()])],
                ignore_index=True,
            )
            st.session_state.grid_revision += 1
            st.rerun()

    frame = _ensure_columns(st.session_state.df)
    st.session_state.df = frame
    mask = _filter_mask(
        frame,
        query=query,
        category=filter_category,
        group=filter_group,
        active=filter_active,
    )
    view = frame.loc[mask].copy()
    count_col, save_col, _ = st.columns([2, 1, 5])
    count_col.write(f"{len(view)} von {len(frame)} Zeilen sichtbar")
    if save_col.button("Speichern", type="primary", use_container_width=True, key="save_main"):
        st.session_state.save_requested = True

    edited = st.data_editor(
        view,
        column_config=_column_config(options),
        hide_index=True,
        num_rows="fixed",
        use_container_width=True,
        height=560,
        key=f"import_grid_{st.session_state.grid_revision}",
    )
    if len(edited.index) == len(view.index):
        edited = edited.copy()
        edited.index = view.index
        for column in IMPORT_COLUMNS:
            if column in edited.columns:
                st.session_state.df.loc[view.index, column] = edited[column].fillna("").astype(str)

    if st.session_state.pop("save_requested", False):
        from scripts.paths import resolve_path

        target = resolve_path(st.session_state.source_path)
        save_import_rows(target, _rows_from_df(st.session_state.df))
        st.session_state.source_path = str(target)
        st.success(f"Gespeichert: {target}")

    number_errors = st.session_state.get("number_errors") or []
    if number_errors:
        st.error(f"{len(number_errors)} Artikelnummer(n) konnten nicht erzeugt werden.")
        st.dataframe(
            pd.DataFrame({"Hinweis": number_errors}),
            hide_index=True,
            use_container_width=True,
        )

    rows = _rows_from_df(st.session_state.df)
    errors = validate_import_rows(rows)
    missing_required = [
        error for error in errors
        if "fehlt" in error.message.lower() or "unbekannt" in error.message.lower()
        or "ungültig" in error.message.lower() or "doppelt" in error.message.lower()
    ]

    left, right = st.columns(2)
    with left:
        st.subheader("Prüfung")
        if missing_required:
            st.warning(f"{len(missing_required)} Problem(e) in der Datei")
            st.dataframe(
                pd.DataFrame(
                    [
                        {"Artikelnummer": error.article_number, "Hinweis": error.message}
                        for error in missing_required
                    ]
                ),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.success("Pflichtfelder und Dropdown-Werte sehen gültig aus.")

    with right:
        st.subheader("nach weclapp")
        dry = st.button("Dry-Run", use_container_width=True)
        create = st.button("Artikel anlegen", type="primary", use_container_width=True)
        if dry or create:
            target = Path(st.session_state.source_path)
            save_import_rows(target, rows)
            stats = import_articles(target, dry_run=not create)
            for line in stats.summary_lines():
                st.write(line)
            if stats.errors and not (stats.created and not create):
                st.error("Es gab Fehler. Details stehen in der Zusammenfassung.")
            elif create:
                st.success("Anlegen abgeschlossen.")
            else:
                st.info("Dry-Run abgeschlossen. Es wurde nichts gespeichert in weclapp.")


def _filter_mask(
    frame: pd.DataFrame,
    *,
    query: str,
    category: str,
    group: str,
    active: str,
) -> pd.Series:
    mask = pd.Series(True, index=frame.index)
    needle = (query or "").strip().lower()
    if needle:
        number = frame["Prosema Artikelnummer"].fillna("").str.lower()
        supplier = frame.get("Lieferantenartikelnummer", pd.Series("", index=frame.index)).fillna("").str.lower()
        name = frame["PROSEMA Kurztext"].fillna("").str.lower()
        matchcode = frame["Referenz (Matchcode)"].fillna("").str.lower()
        mask &= (
            number.str.contains(needle, regex=False)
            | supplier.str.contains(needle, regex=False)
            | name.str.contains(needle, regex=False)
            | matchcode.str.contains(needle, regex=False)
        )
    if category and category != "(alle)":
        mask &= frame["Kategorie"].fillna("") == category
    if group and group != "(alle)":
        mask &= frame["Hauptgruppe"].fillna("") == group
    if active and active != "(alle)":
        mask &= frame["Aktiv"].fillna("") == active
    return mask


def launch_editor(input_path: Path | None = None) -> subprocess.Popen:
    _ensure_project_root()
    from scripts.paths import PROJECT_ROOT

    env = os.environ.copy()
    env["PROSEMA_IMPORT_CSV"] = str(input_path or _default_csv_path())
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(Path(__file__).resolve()),
            "--browser.gatherUsageStats=false",
            "--server.headless=true",
        ],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdin=subprocess.DEVNULL,
    )


def run_job(params: dict):
    from gui.job_spec import RunResult, coerce_params, validate_params
    from scripts.paths import resolve_path

    params = coerce_params(JOB_SPEC, params)
    validate_params(JOB_SPEC, params)
    input_path = resolve_path(params["input"])
    process = launch_editor(input_path)
    return RunResult(
        summary="Artikel-Editor im Browser gestartet.",
        details=[
            f"CSV: {input_path}",
            f"Prozess-ID: {process.pid}",
            "Falls sich kein Browser öffnet: http://localhost:8501",
        ],
        show_success_dialog=False,
    )


def _build_job_spec():
    from gui.job_spec import FieldKind, FieldSpec, JobSpec

    return JobSpec(
        id="weclapp_article_editor",
        title="Artikel-Import Editor",
        description=(
            "Öffnet einen Browser-Editor für die standardisierte Import-CSV: "
            "filtern, Dropdowns zuweisen, speichern und Artikel in weclapp anlegen."
        ),
        fields=(
            FieldSpec(
                "input",
                "Import-CSV",
                FieldKind.FILE_IN,
                "data/weclapp_article_import_template.csv",
            ),
        ),
        run=run_job,
    )


def main(argv: list[str] | None = None) -> int:
    _ensure_project_root()
    if _running_in_streamlit():
        render_app()
        return 0

    parser = argparse.ArgumentParser(description="Browser-Editor für die weclapp-Import-CSV.")
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="CSV-Datei, Standard: data/weclapp_article_import_template.csv",
    )
    args = parser.parse_args(argv)
    process = launch_editor(args.input)
    print(f"Artikel-Editor gestartet (PID {process.pid}).")
    print("Browser: http://localhost:8501")
    print("Beenden mit Ctrl+C.")
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait(timeout=5)
        return 0


_ensure_project_root()
JOB_SPEC = _build_job_spec()


if __name__ == "__main__":
    raise SystemExit(main())
