"""Read-only assistant query tools against a tenant-scoped snapshot."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assistant.schemas import (
    ArtikelDetailsArgs,
    ArtikelSuchenArgs,
    ArtikelZaehlenArgs,
    DatenstandArgs,
    EinheitenAuflistenArgs,
    FilterCondition,
    GruppenAuflistenArgs,
    Operator,
    QueryFilter,
    SortSpec,
)
from app.assistant.tools import (
    artikel_details,
    artikel_suchen,
    artikel_zaehlen,
    datenstand,
    einheiten_auflisten,
    gruppen_auflisten,
    resolve_current_snapshot,
)
from app.db import engine
from app.models import ArticleSnapshot, ArticleSnapshotRow, Hauptgruppe, Job, Untergruppe

TENANT = "assistant-tools-tenant"

HEADER = [
    {"key": key, "title": key, "width": 120}
    for key in (
        "Prosema Artikelnummer",
        "PROSEMA Kurztext",
        "Nettogewicht kg",
        "Verkaufspreis €, BE",
        "Einkaufspreis EUR netto",
        "Einheit",
        "Hauptgruppe",
        "Untergruppe",
        "Länge in cm",
        "Gewichtseinheit",
        "Aktiv",
    )
]


@pytest.fixture
def db_session():
    connection = engine.connect()
    trans = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


def _add_row(db_session, snapshot, position: int, data: dict, **indexed) -> None:
    db_session.add(
        ArticleSnapshotRow(
            snapshot_id=snapshot.id,
            position=position,
            data=data,
            article_number=indexed.get(
                "article_number", data.get("Prosema Artikelnummer", "")
            ),
            article_name=indexed.get("article_name", data.get("PROSEMA Kurztext", "")),
            active=indexed.get("active", data.get("Aktiv", "Ja") == "Ja"),
            weclapp_id=indexed.get("weclapp_id", f"id-{position}"),
        )
    )


@pytest.fixture
def snapshot(db_session):
    snap = ArticleSnapshot(
        status="complete",
        created_by_oid="oid",
        created_by_name="Tester",
        weclapp_tenant=TENANT,
        row_count=4,
        columns=HEADER,
        non_conforming_number_count=1,
        created_at=datetime.now(UTC),
    )
    db_session.add(snap)
    db_session.flush()
    _add_row(
        db_session,
        snap,
        0,
        {
            "Prosema Artikelnummer": "881.010.0010",
            "PROSEMA Kurztext": "Alpha",
            "Nettogewicht kg": "1,50",
            "Verkaufspreis €, BE": "12.50",
            "Einkaufspreis EUR netto": "8.00",
            "Einheit": "Stk.",
            "Hauptgruppe": "AssistHG",
            "Untergruppe": "AssistUG",
            "Länge in cm": "120",
            "Gewichtseinheit": "KILOGRAM",
            "Aktiv": "Ja",
        },
        article_number="881.010.0010",
        article_name="Alpha",
        active=True,
    )
    _add_row(
        db_session,
        snap,
        1,
        {
            "Prosema Artikelnummer": "881.010.0020",
            "PROSEMA Kurztext": "Beta",
            "Nettogewicht kg": "10",
            "Verkaufspreis €, BE": "3.00",
            "Einheit": "lfm",
            "Hauptgruppe": "AssistHG",
            "Untergruppe": "AssistUG",
            "Länge in cm": "1.234",
            "Gewichtseinheit": "kg",
            "Aktiv": "Ja",
        },
        article_number="881.010.0020",
        article_name="Beta",
        active=True,
    )
    _add_row(
        db_session,
        snap,
        2,
        {
            "Prosema Artikelnummer": "881.010.0030",
            "PROSEMA Kurztext": "Gamma",
            "Nettogewicht kg": "abc",
            "Verkaufspreis €, BE": "1.00",
            "Einheit": "Stk.",
            "Hauptgruppe": "AssistHG",
            "Untergruppe": "AssistUG",
            "Aktiv": "Nein",
        },
        article_number="881.010.0030",
        article_name="Gamma",
        active=False,
    )
    _add_row(
        db_session,
        snap,
        3,
        {
            "Prosema Artikelnummer": "LEGACY",
            "PROSEMA Kurztext": "Legacy",
            "Nettogewicht kg": "0,10",
            "Verkaufspreis €, BE": "0.50",
            "Einheit": "Stk.",
            "Aktiv": "Ja",
        },
        article_number="LEGACY",
        article_name="Legacy",
        active=True,
    )
    db_session.flush()
    return snap


@patch("app.assistant.tools.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_resolve_current_snapshot_filters_tenant(db_session, snapshot):
    other = ArticleSnapshot(
        status="complete",
        created_by_oid="oid",
        created_by_name="Other",
        weclapp_tenant="other-tenant",
        row_count=0,
        columns=[],
        created_at=datetime.now(UTC),
    )
    db_session.add(other)
    db_session.flush()
    current = resolve_current_snapshot(db_session)
    assert current is not None
    assert current.id == snapshot.id


@patch("app.assistant.tools.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_suchen_count_not_inferred_from_limit(db_session, snapshot):
    args = ArtikelSuchenArgs(
        filters=QueryFilter(
            conditions=[FilterCondition(column="Einheit", operator=Operator.eq, value="Stk.")]
        ),
        limit=1,
    )
    result = artikel_suchen(db_session, args)
    assert result.total_count == 3
    assert len(result.rows) == 1
    assert result.truncated is True
    assert "Beginn des Abzugs" in result.datenstand_hinweis_de
    assert result.datenstand == snapshot.created_at


@patch("app.assistant.tools.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_numeric_comma_weight_and_non_matching_text_null(db_session, snapshot):
    args = ArtikelSuchenArgs(
        filters=QueryFilter(
            conditions=[
                FilterCondition(column="Nettogewicht kg", operator=Operator.gt, value="2")
            ]
        )
    )
    result = artikel_suchen(db_session, args)
    numbers = {row["article_number"] for row in result.rows}
    assert numbers == {"881.010.0020"}
    assert "881.010.0030" not in numbers


DIMENSION_KEYS = ("Länge in cm", "Breite in mm", "Höhe in mm")


@patch("app.assistant.tools.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_dimension_numeric_filter_keeps_comma_drops_dot(db_session):
    """Comma-format values match; the other decimal convention is NULL, not an error."""
    header = [{"key": key, "title": key, "width": 120} for key in DIMENSION_KEYS]
    header.append({"key": "Prosema Artikelnummer", "title": "Prosema Artikelnummer", "width": 160})
    snap = ArticleSnapshot(
        status="complete",
        created_by_oid="oid",
        created_by_name="Tester",
        weclapp_tenant=TENANT,
        row_count=2,
        columns=header,
        created_at=datetime.now(UTC),
    )
    db_session.add(snap)
    db_session.flush()
    declared = {key: "80,5" for key in DIMENSION_KEYS}
    other = {key: "90.5" for key in DIMENSION_KEYS}
    _add_row(
        db_session,
        snap,
        0,
        {"Prosema Artikelnummer": "883.010.0010", **declared},
        article_number="883.010.0010",
        article_name="Comma",
        active=True,
    )
    _add_row(
        db_session,
        snap,
        1,
        {"Prosema Artikelnummer": "883.010.0020", **other},
        article_number="883.010.0020",
        article_name="Dot",
        active=True,
    )
    db_session.flush()
    for column in DIMENSION_KEYS:
        result = artikel_suchen(
            db_session,
            ArtikelSuchenArgs(
                filters=QueryFilter(
                    conditions=[
                        FilterCondition(column=column, operator=Operator.gt, value="50")
                    ]
                )
            ),
        )
        numbers = {row["article_number"] for row in result.rows}
        assert numbers == {"883.010.0010"}, column
        assert result.total_count == 1, column


@patch("app.assistant.tools.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_dot_price_and_absent_einkauf(db_session, snapshot):
    cheap = artikel_suchen(
        db_session,
        ArtikelSuchenArgs(
            filters=QueryFilter(
                conditions=[
                    FilterCondition(
                        column="Verkaufspreis €, BE", operator=Operator.lt, value="5"
                    )
                ]
            )
        ),
    )
    assert cheap.total_count == 3
    missing_ek = artikel_suchen(
        db_session,
        ArtikelSuchenArgs(
            filters=QueryFilter(
                conditions=[
                    FilterCondition(
                        column="Einkaufspreis EUR netto", operator=Operator.is_null
                    )
                ]
            )
        ),
    )
    assert missing_ek.total_count == 3


@patch("app.assistant.tools.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_gewicht_filter_matches_either_spelling(db_session, snapshot):
    result = artikel_suchen(
        db_session,
        ArtikelSuchenArgs(
            filters=QueryFilter(
                conditions=[
                    FilterCondition(column="Gewichtseinheit", operator=Operator.eq, value="kg")
                ]
            )
        ),
    )
    assert result.total_count == 2


@patch("app.assistant.tools.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_details_not_found_is_hinweis(db_session, snapshot):
    result = artikel_details(db_session, ArtikelDetailsArgs(article_number="missing"))
    assert result.rows == []
    assert "Kein Artikel" in result.hinweis_de
    found = artikel_details(db_session, ArtikelDetailsArgs(article_number="881.010.0010"))
    assert found.total_count == 1
    assert found.rows[0]["article_name"] == "Alpha"


@patch("app.assistant.tools.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_zaehlen_group_by_truncates(db_session, snapshot):
    result = artikel_zaehlen(
        db_session,
        ArtikelZaehlenArgs(
            filters=QueryFilter(),
            group_by="Einheit",
        ),
    )
    assert result.total_count == 2
    assert {row["gruppe"] for row in result.rows} == {"Stk.", "lfm"}


@patch("app.assistant.tools.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_gruppen_counts_from_article_number_not_code_column(db_session, snapshot):
    haupt = Hauptgruppe(code="881", name="AssistHG")
    db_session.add(haupt)
    db_session.flush()
    db_session.add(Untergruppe(hauptgruppe_id=haupt.id, code="010", name="AssistUG"))
    db_session.add(Hauptgruppe(code="882", name="Leer"))
    db_session.flush()
    result = gruppen_auflisten(db_session, GruppenAuflistenArgs())
    haupt_881 = next(
        row for row in result.rows if row["ebene"] == "hauptgruppe" and row["code"] == "881"
    )
    unter = next(
        row
        for row in result.rows
        if row["ebene"] == "untergruppe"
        and row["code"] == "010"
        and row.get("hauptgruppe_code") == "881"
    )
    leer = next(
        row for row in result.rows if row["ebene"] == "hauptgruppe" and row["code"] == "882"
    )
    assert haupt_881["anzahl"] == 3
    assert unter["anzahl"] == 3
    assert leer["anzahl"] == 0
    assert "konforme Nummer" in result.hinweis_de


@patch("app.assistant.tools.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_einheiten_and_datenstand(db_session, snapshot):
    units = einheiten_auflisten(db_session, EinheitenAuflistenArgs())
    names = {row["name"]: row["anzahl"] for row in units.rows}
    assert names["Stk."] == 3
    assert names["lfm"] == 1
    job = Job(
        job_type="weclapp_article_snapshot",
        payload={"snapshot_id": str(snapshot.id)},
        status="succeeded",
        created_by_oid="oid",
        created_by_name="Tester",
    )
    db_session.add(job)
    db_session.flush()
    info = datenstand(db_session, DatenstandArgs())
    assert info.rows[0]["snapshot_id"] == str(snapshot.id)
    assert info.rows[0]["non_conforming_number_count"] == 1
    assert info.rows[0]["job"]["status"] == "succeeded"
    assert "Beginn des Abzugs" in info.datenstand_hinweis_de


@patch("app.assistant.tools.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_select_value_rejected(db_session, snapshot):
    args = ArtikelSuchenArgs(
        filters=QueryFilter(
            conditions=[FilterCondition(column="Einheit", operator=Operator.eq, value="Tonne")]
        )
    )
    with pytest.raises(ValueError, match="Erlaubte Werte"):
        artikel_suchen(db_session, args)


@patch("app.assistant.tools.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_sort_numeric_weight(db_session, snapshot):
    result = artikel_suchen(
        db_session,
        ArtikelSuchenArgs(
            filters=QueryFilter(
                conditions=[
                    FilterCondition(column="Nettogewicht kg", operator=Operator.gt, value="0")
                ]
            ),
            sort=SortSpec(column="Nettogewicht kg", direction="desc"),
        ),
    )
    weights_order = [row["article_number"] for row in result.rows]
    assert weights_order[0] == "881.010.0020"
    assert "881.010.0030" not in weights_order


@patch("app.assistant.tools.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_no_writes(db_session, snapshot):
    before = db_session.scalars(
        select(ArticleSnapshotRow).where(ArticleSnapshotRow.snapshot_id == snapshot.id)
    ).first()
    artikel_suchen(db_session, ArtikelSuchenArgs())
    db_session.flush()
    after = db_session.get(ArticleSnapshotRow, before.id)
    assert after.data == before.data


VOLLTEXT_KEYS = (
    "Prosema Artikelnummer",
    "PROSEMA Kurztext",
    "Hauptgruppe",
    "Kurzbeschreibung",
    "PROSEMA Langtext",
    "Grundmaterial",
    "Farbe",
    "Oberfläche",
    "Produktfamilie",
    "Aktiv",
)
VOLLTEXT_HEADER = [{"key": key, "title": key, "width": 120} for key in VOLLTEXT_KEYS]


def _volltext_snapshot(db_session, *, columns=None, extra_rows=None):
    snap = ArticleSnapshot(
        status="complete",
        created_by_oid="oid",
        created_by_name="Tester",
        weclapp_tenant=TENANT,
        row_count=3,
        columns=columns if columns is not None else VOLLTEXT_HEADER,
        created_at=datetime.now(UTC),
    )
    db_session.add(snap)
    db_session.flush()
    rows = [
        {
            "Prosema Artikelnummer": "882.010.0010",
            "PROSEMA Kurztext": "Profil Alpha",
            "Hauptgruppe": "Profile",
            "Kurzbeschreibung": "",
            "PROSEMA Langtext": "Langtext mit Sonderlegierung im Satz",
            "Grundmaterial": "Stahl",
            "Farbe": "natur",
            "Oberfläche": "eloxiert",
            "Produktfamilie": "Standard",
            "Aktiv": "Ja",
        },
        {
            "Prosema Artikelnummer": "882.010.0020",
            "PROSEMA Kurztext": "Winkel Beta",
            "Hauptgruppe": "Zubehör",
            "Kurzbeschreibung": "",
            "PROSEMA Langtext": "Kein Hinweis auf das Material",
            "Grundmaterial": "Sonderlegierung",
            "Farbe": "silber",
            "Oberfläche": "roh",
            "Produktfamilie": "Standard",
            "Aktiv": "Ja",
        },
        {
            "Prosema Artikelnummer": "882.010.0030",
            "PROSEMA Kurztext": "Leiste Gamma",
            "Hauptgruppe": "Profile",
            "Kurzbeschreibung": "",
            "PROSEMA Langtext": "Aluminiumprofil",
            "Grundmaterial": "Aluminium",
            "Farbe": "weiss",
            "Oberfläche": "pulverbeschichtet",
            "Produktfamilie": "Standard",
            "Aktiv": "Ja",
        },
    ]
    if extra_rows:
        rows.extend(extra_rows)
    for position, data in enumerate(rows):
        _add_row(
            db_session,
            snap,
            position,
            data,
            article_number=data["Prosema Artikelnummer"],
            article_name=data["PROSEMA Kurztext"],
            active=True,
        )
    db_session.flush()
    return snap


@patch("app.assistant.tools.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_volltext_contains_langtext_or_grundmaterial(db_session):
    _volltext_snapshot(db_session)
    result = artikel_suchen(
        db_session,
        ArtikelSuchenArgs(
            filters=QueryFilter(
                conditions=[
                    FilterCondition(
                        column="volltext", operator=Operator.contains, value="Sonderlegierung"
                    )
                ]
            )
        ),
    )
    numbers = {row["article_number"] for row in result.rows}
    assert numbers == {"882.010.0010", "882.010.0020"}
    assert "882.010.0030" not in numbers


@patch("app.assistant.tools.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_volltext_and_hauptgruppe(db_session):
    _volltext_snapshot(db_session)
    result = artikel_suchen(
        db_session,
        ArtikelSuchenArgs(
            filters=QueryFilter(
                conditions=[
                    FilterCondition(column="Hauptgruppe", operator=Operator.eq, value="Profile"),
                    FilterCondition(
                        column="volltext", operator=Operator.contains, value="Sonderlegierung"
                    ),
                ]
            )
        ),
    )
    numbers = {row["article_number"] for row in result.rows}
    assert numbers == {"882.010.0010"}


@patch("app.assistant.tools.settings.weclapp_tenant", TENANT)
@patch("app.assistant.catalog.settings.weclapp_tenant", TENANT)
def test_volltext_skips_missing_snapshot_column(db_session):
    columns = [col for col in VOLLTEXT_HEADER if col["key"] != "Farbe"]
    _volltext_snapshot(db_session, columns=columns)
    result = artikel_suchen(
        db_session,
        ArtikelSuchenArgs(
            filters=QueryFilter(
                conditions=[
                    FilterCondition(
                        column="volltext", operator=Operator.contains, value="Sonderlegierung"
                    )
                ]
            )
        ),
    )
    numbers = {row["article_number"] for row in result.rows}
    assert numbers == {"882.010.0010", "882.010.0020"}
