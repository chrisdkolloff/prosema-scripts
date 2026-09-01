"""Bezugsquellenexport column catalog.

Source of truth for field_alias seed, grid, picker, write_policy, and serialisation.
Visibility is a user preference; write_policy decides what reaches the CSV.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Scope = Literal["supply_source", "article", "derived", "context"]
WritePolicy = Literal["always", "on_value", "locked"]
EditPolicy = Literal["editable", "read_only", "derived"]
PickerGroup = Literal["identity", "working", "context", "optional", "article"]
InputKind = Literal["text", "ja_nein", "date", "numeric", "percent", "dropdown", "derived"]
Store = Literal["row", "extras", "article_context", "computed", "derived"]

TOOL_KEY = "supply_source_export"

PICKER_GROUPS: tuple[tuple[PickerGroup, str, str], ...] = (
    ("identity", "Pflichtfelder", ""),
    ("working", "Arbeitsspalten", ""),
    ("context", "Kontext", ""),
    ("optional", "Bezugsquelle (optional)", "Leere Zelle belässt den weclapp-Wert."),
    (
        "article",
        "Artikel",
        "Schreiben würde den Verkaufsartikel ändern — nicht im Umfang.",
    ),
)

PRESET_STANDARD = "standard"
PRESET_MANDATORY = "mandatory"
PRESET_ALL = "all"

ARTICLE_READ_ONLY_NOTE = (
    "Nur Anzeige. Schreiben würde Verkaufsartikel-Stammdaten ändern "
    "(nicht im Umfang, Spalte V ungetestet)."
)


@dataclass(frozen=True, slots=True)
class FieldSpec:
    field_key: str
    label_internal: str
    scope: Scope
    write_policy: WritePolicy
    edit_policy: EditPolicy
    default_visible: bool
    label_weclapp: str = ""
    weclapp_column: str = ""
    max_length: int | None = None
    is_mandatory: bool = False
    phase: int = 1
    note: str = ""
    description: str = ""
    picker_group: PickerGroup | None = None
    input_kind: InputKind = "text"
    grid_title: str = ""
    width: int = 120
    store: Store = "derived"
    orm_attr: str = ""

    @property
    def in_picker(self) -> bool:
        return self.picker_group is not None and self.phase == 1

    @property
    def hideable(self) -> bool:
        return self.in_picker and self.picker_group != "identity"

    @property
    def title(self) -> str:
        return self.grid_title or self.label_internal

    @property
    def row_attr(self) -> str:
        return self.orm_attr or self.field_key


def _f(**kwargs: Any) -> FieldSpec:
    return FieldSpec(**kwargs)


_ARTICLE = dict(
    scope="article",
    write_policy="locked",
    edit_policy="read_only",
    default_visible=False,
    picker_group="article",
    store="article_context",
    note=ARTICLE_READ_ONLY_NOTE,
    phase=1,
)

_OPTIONAL = dict(
    scope="supply_source",
    write_policy="on_value",
    edit_policy="editable",
    default_visible=False,
    picker_group="optional",
    store="extras",
    note="Leer = bestehender Wert in weclapp bleibt.",
    phase=1,
)

_LOCKED_PHASE2 = dict(
    write_policy="locked",
    edit_policy="read_only",
    default_visible=False,
    picker_group=None,
    store="derived",
    phase=2,
    note="nur bei Neuanlage",
)


FIELDS: tuple[FieldSpec, ...] = (
    # --- Pflichtfelder (never hideable, read-only) ---
    _f(
        field_key="supplier_article_number",
        label_internal="Lieferanten-Art.-Nr.",
        label_weclapp="Lieferantenartikelnummer",
        weclapp_column="D",
        scope="supply_source",
        max_length=1000,
        is_mandatory=True,
        write_policy="on_value",
        edit_policy="read_only",
        default_visible=True,
        picker_group="identity",
        grid_title="Lieferanten-Art.-Nr.",
        width=130,
        store="row",
        description="Halber Match-Schlüssel",
    ),
    _f(
        field_key="supplier_number",
        label_internal="Lieferantennummer",
        label_weclapp="LIEFERANTENNUMMER",
        weclapp_column="F",
        scope="supply_source",
        max_length=64,
        is_mandatory=True,
        write_policy="on_value",
        edit_policy="read_only",
        default_visible=True,
        picker_group="identity",
        grid_title="Lief.-Nr.",
        width=90,
        store="row",
        description="Halber Match-Schlüssel",
    ),
    _f(
        field_key="article_name",
        label_internal="Artikelname",
        label_weclapp="ARTIKELNAME",
        weclapp_column="A",
        scope="article",
        max_length=300,
        is_mandatory=True,
        write_policy="on_value",
        edit_policy="read_only",
        default_visible=True,
        picker_group="identity",
        width=220,
        store="row",
        description="Pflichtfeld; max. 300 Zeichen",
    ),
    _f(
        field_key="unit",
        label_internal="Mengeneinheit",
        label_weclapp="Artikel-Mengeneinheit",
        weclapp_column="O",
        scope="article",
        max_length=150,
        is_mandatory=True,
        write_policy="on_value",
        edit_policy="read_only",
        default_visible=True,
        picker_group="identity",
        grid_title="Einheit",
        width=80,
        store="row",
    ),
    # --- Arbeitsspalten ---
    _f(
        field_key="ek_price_before_discount",
        label_internal="EK vor Rabatt (EUR)",
        label_weclapp="Bruttokaufpreis",
        weclapp_column="G",
        scope="supply_source",
        write_policy="on_value",
        edit_policy="editable",
        default_visible=True,
        picker_group="working",
        input_kind="numeric",
        grid_title="EK vor Rabatt",
        width=110,
        store="row",
        description="Netto-Einkaufspreis vor Rabatt (EUR)",
    ),
    _f(
        field_key="discount_category",
        label_internal="Rabattkategorie",
        scope="derived",
        write_policy="locked",
        edit_policy="editable",
        default_visible=True,
        picker_group="working",
        input_kind="dropdown",
        grid_title="Rabattkat.",
        width=120,
        store="row",
        note="Dropdown aus dem Register, plus — kein Rabatt —",
        description="Lieferanten-Rabattkategorie; treibt I/J/L/M",
    ),
    _f(
        field_key="base_discount_pct",
        label_internal="Rabatt 1 (%)",
        label_weclapp="Zu- und Abschläge Wert 1",
        weclapp_column="J",
        scope="supply_source",
        write_policy="always",
        edit_policy="editable",
        default_visible=True,
        picker_group="working",
        input_kind="percent",
        grid_title="D1 %",
        width=70,
        store="row",
        note="Leer löscht den Rabatt in weclapp. Abweichung vom Register braucht Begründung.",
    ),
    _f(
        field_key="customer_discount_pct",
        label_internal="Rabatt 2 (%)",
        label_weclapp="Zu- und Abschläge Wert 2",
        weclapp_column="M",
        scope="supply_source",
        write_policy="always",
        edit_policy="editable",
        default_visible=True,
        picker_group="working",
        input_kind="percent",
        grid_title="D2 %",
        width=70,
        store="row",
        note="Leer löscht den Rabatt in weclapp. Abweichung vom Register braucht Begründung.",
    ),
    _f(
        field_key="override_reason",
        label_internal="Override-Grund",
        scope="context",
        write_policy="locked",
        edit_policy="editable",
        default_visible=True,
        picker_group="working",
        width=180,
        store="row",
        note="Pflicht bei Abweichung vom Register; fliesst in die Provenienz (H/K).",
    ),
    _f(
        field_key="matchcode",
        label_internal="Matchcode",
        label_weclapp="Matchcode",
        weclapp_column="P",
        scope="supply_source",
        max_length=256,
        write_policy="on_value",
        edit_policy="editable",
        default_visible=True,
        picker_group="working",
        width=120,
        store="row",
    ),
    _f(
        field_key="is_primary",
        label_internal="Primäre Bezugsquelle",
        label_weclapp="Primäre Bezugsquelle",
        weclapp_column="BQ",
        scope="supply_source",
        write_policy="on_value",
        edit_policy="editable",
        default_visible=True,
        picker_group="working",
        input_kind="ja_nein",
        grid_title="Primär",
        width=90,
        store="row",
        orm_attr="weclapp_current_is_primary",
        note="Vorgabe aus weclapp, nie fest auf ja.",
    ),
    _f(
        field_key="dropshipping_possible",
        label_internal="Dropshipping möglich",
        label_weclapp="Dropshipping möglich",
        weclapp_column="BL",
        scope="supply_source",
        write_policy="on_value",
        edit_policy="editable",
        default_visible=True,
        picker_group="working",
        input_kind="ja_nein",
        grid_title="Dropship",
        width=90,
        store="row",
        note="Vorgabe aus weclapp.",
    ),
    # --- Kontext (never exported) ---
    _f(
        field_key="article_number",
        label_internal="Prosema-Art.-Nr.",
        scope="context",
        write_policy="locked",
        edit_policy="read_only",
        default_visible=True,
        picker_group="context",
        grid_title="Prosema-Art.-Nr.",
        width=130,
        store="row",
        note="Nur Anzeige im Raster. Dieselbe Nummer wird immer nach Spalte W geschrieben.",
        description="PROSEMA article number; serialised as Verkaufsartikel-Nummer (W)",
    ),
    _f(
        field_key="ek_after",
        label_internal="EK nach Rabatt (EUR)",
        scope="context",
        write_policy="locked",
        edit_policy="derived",
        default_visible=True,
        picker_group="context",
        input_kind="derived",
        grid_title="EK nach Rabatt",
        width=110,
        store="computed",
    ),
    _f(
        field_key="sale_chf",
        label_internal="VK inkl. Zuschlag (CHF)",
        scope="context",
        write_policy="locked",
        edit_policy="derived",
        default_visible=True,
        picker_group="context",
        input_kind="derived",
        grid_title="VK CHF",
        width=100,
        store="computed",
    ),
    _f(
        field_key="hauptgruppe_code",
        label_internal="Hauptgruppe",
        scope="context",
        write_policy="locked",
        edit_policy="read_only",
        default_visible=True,
        picker_group="context",
        grid_title="Hauptgr.",
        width=90,
        store="row",
    ),
    _f(
        field_key="untergruppe_code",
        label_internal="Untergruppe",
        scope="context",
        write_policy="locked",
        edit_policy="read_only",
        default_visible=True,
        picker_group="context",
        grid_title="Untergr.",
        width=90,
        store="row",
    ),
    _f(
        field_key="weclapp_current_ek",
        label_internal="weclapp aktuell: EK",
        scope="context",
        write_policy="locked",
        edit_policy="read_only",
        default_visible=True,
        picker_group="context",
        input_kind="numeric",
        grid_title="weclapp EK",
        width=100,
        store="row",
    ),
    _f(
        field_key="weclapp_current_d1",
        label_internal="weclapp aktuell: Rabatt 1",
        scope="context",
        write_policy="locked",
        edit_policy="read_only",
        default_visible=True,
        picker_group="context",
        input_kind="percent",
        grid_title="weclapp D1",
        width=90,
        store="row",
        orm_attr="weclapp_current_base_discount_pct",
    ),
    _f(
        field_key="weclapp_current_d2",
        label_internal="weclapp aktuell: Rabatt 2",
        scope="context",
        write_policy="locked",
        edit_policy="read_only",
        default_visible=True,
        picker_group="context",
        input_kind="percent",
        grid_title="weclapp D2",
        width=90,
        store="row",
        orm_attr="weclapp_current_customer_discount_pct",
    ),
    _f(
        field_key="_status",
        label_internal="Status",
        scope="context",
        write_policy="locked",
        edit_policy="derived",
        default_visible=True,
        picker_group="context",
        input_kind="derived",
        width=200,
        store="computed",
    ),
    # --- Bezugsquelle optional ---
    _f(
        field_key="article_active",
        label_internal="Artikel aktiv",
        label_weclapp="Artikel aktiv",
        weclapp_column="Q",
        input_kind="ja_nein",
        width=90,
        **_OPTIONAL,
    ),
    _f(
        field_key="supplier_company",
        label_internal="Name Lieferant",
        label_weclapp="Lieferanten Firmenname",
        weclapp_column="E",
        max_length=255,
        width=180,
        **_OPTIONAL,
    ),
    _f(
        field_key="goods_group_name",
        label_internal="Warengruppen-Name",
        label_weclapp="Warengruppen-Name",
        weclapp_column="S",
        max_length=255,
        width=160,
        **_OPTIONAL,
    ),
    _f(
        field_key="goods_group_description",
        label_internal="Warengruppen Beschreibung",
        label_weclapp="Warengruppen Beschreibung",
        weclapp_column="T",
        max_length=255,
        width=180,
        **_OPTIONAL,
    ),
    _f(
        field_key="tax_rate",
        label_internal="Steuersatz",
        label_weclapp="Steuersatz",
        weclapp_column="U",
        max_length=50,
        width=110,
        **_OPTIONAL,
    ),
    _f(
        field_key="buffer_days",
        label_internal="Sicherheitstage",
        label_weclapp="Sicherheitstage",
        weclapp_column="BD",
        input_kind="numeric",
        width=110,
        **_OPTIONAL,
    ),
    _f(
        field_key="min_stock",
        label_internal="Mindestlagerbestand",
        label_weclapp="Mindestlagerbestand",
        weclapp_column="BE",
        input_kind="numeric",
        width=130,
        **_OPTIONAL,
    ),
    _f(
        field_key="target_stock",
        label_internal="Zielbestand",
        label_weclapp="Zielbestand",
        weclapp_column="BF",
        input_kind="numeric",
        width=110,
        **_OPTIONAL,
    ),
    _f(
        field_key="replenishment_days",
        label_internal="Wiederbeschaffungstage",
        label_weclapp="Wiederbeschaffungstage",
        weclapp_column="BG",
        input_kind="numeric",
        width=140,
        **_OPTIONAL,
    ),
    _f(
        field_key="avg_delivery_time",
        label_internal="Durchschnittliche Lieferzeit",
        label_weclapp="Durchschnittliche Lieferzeit",
        weclapp_column="BH",
        input_kind="numeric",
        width=160,
        **_OPTIONAL,
    ),
    _f(
        field_key="min_order_qty",
        label_internal="Mindestbestellmenge",
        label_weclapp="Mindestbestellmenge",
        weclapp_column="BI",
        input_kind="numeric",
        width=140,
        **_OPTIONAL,
    ),
    _f(
        field_key="fixed_order_qty",
        label_internal="Fixe Bestellmenge",
        label_weclapp="Gebindemenge",
        weclapp_column="BJ",
        input_kind="numeric",
        width=130,
        note="Leer = bestehender Wert in weclapp bleibt. weclapp-Spalte: Gebindemenge.",
        **{k: v for k, v in _OPTIONAL.items() if k != "note"},
    ),
    _f(
        field_key="supplier_stock",
        label_internal="Lieferantenbestand",
        label_weclapp="Lieferantenbestand",
        weclapp_column="BK",
        input_kind="numeric",
        width=130,
        **_OPTIONAL,
    ),
    _f(
        field_key="ignore_dropship_automation",
        label_internal="In Dropshipping-Automatisierung ignorieren",
        label_weclapp="In Dropshipping-Automatisierung ignorieren",
        weclapp_column="BM",
        input_kind="ja_nein",
        width=180,
        **_OPTIONAL,
    ),
    _f(
        field_key="cost_center_sales",
        label_internal="Kostenstelle Verkauf",
        label_weclapp="Kostenstelle Verkauf",
        weclapp_column="BN",
        max_length=64,
        width=150,
        **_OPTIONAL,
    ),
    _f(
        field_key="cost_center_purchase",
        label_internal="Kostenstelle Einkauf",
        label_weclapp="Kostenstelle Einkauf",
        weclapp_column="BO",
        max_length=64,
        width=150,
        **_OPTIONAL,
    ),
    _f(
        field_key="cost_type",
        label_internal="Kostenart",
        label_weclapp="Kostenart",
        weclapp_column="BP",
        max_length=64,
        width=120,
        **_OPTIONAL,
    ),
    # --- Artikel ---
    _f(
        field_key="local_article_name",
        label_internal="Lokaler Artikelname",
        label_weclapp="Lokaler Artikelname",
        weclapp_column="C",
        max_length=300,
        width=200,
        **_ARTICLE,
    ),
    _f(
        field_key="short_text_1",
        label_internal="Kurztext 1",
        label_weclapp="Kurztext 1",
        weclapp_column="AB",
        max_length=255,
        width=200,
        **_ARTICLE,
    ),
    _f(
        field_key="short_text_1_language",
        label_internal="Handelssprache (Kurztext 1)",
        label_weclapp="Handelssprache",
        weclapp_column="AC",
        max_length=10,
        width=110,
        **_ARTICLE,
    ),
    _f(
        field_key="localized_short_text_1",
        label_internal="Lokalisierte Kurztext 1",
        label_weclapp="Lokalisierte Kurztext 1",
        weclapp_column="AD",
        max_length=255,
        width=200,
        **_ARTICLE,
    ),
    _f(
        field_key="short_text_2",
        label_internal="Kurztext 2",
        label_weclapp="Kurztext 2",
        weclapp_column="AE",
        max_length=255,
        width=200,
        **_ARTICLE,
    ),
    _f(
        field_key="short_text_2_language",
        label_internal="Handelssprache (Kurztext 2)",
        label_weclapp="Handelssprache",
        weclapp_column="AF",
        max_length=10,
        width=110,
        **_ARTICLE,
    ),
    _f(
        field_key="localized_short_text_2",
        label_internal="Lokalisierte Kurztext 2",
        label_weclapp="Lokalisierte Kurztext 2",
        weclapp_column="AG",
        max_length=255,
        width=200,
        **_ARTICLE,
    ),
    _f(
        field_key="article_description",
        label_internal="Artikelbeschreibung",
        label_weclapp="Artikelbeschreibung",
        weclapp_column="AH",
        max_length=4000,
        width=220,
        **_ARTICLE,
    ),
    _f(
        field_key="article_description_language",
        label_internal="Handelssprache (Beschreibung)",
        label_weclapp="Handelssprache",
        weclapp_column="AI",
        max_length=10,
        width=110,
        **_ARTICLE,
    ),
    _f(
        field_key="localized_article_description",
        label_internal="Lokalisierte Artikelbeschreibung",
        label_weclapp="Lokalisierte Artikelbeschreibung",
        weclapp_column="AJ",
        max_length=4000,
        width=220,
        **_ARTICLE,
    ),
    _f(
        field_key="internal_note",
        label_internal="Interner Hinweis",
        label_weclapp="Interner Hinweis",
        weclapp_column="AK",
        max_length=4000,
        width=180,
        **_ARTICLE,
    ),
    _f(
        field_key="internal_note_language",
        label_internal="Handelssprache (Hinweis)",
        label_weclapp="Handelssprache",
        weclapp_column="AL",
        max_length=10,
        width=110,
        **_ARTICLE,
    ),
    _f(
        field_key="localized_internal_note",
        label_internal="Lokalisierter interner Hinweis",
        label_weclapp="Lokalisierter interner Hinweis",
        weclapp_column="AM",
        max_length=4000,
        width=180,
        **_ARTICLE,
    ),
    _f(
        field_key="long_description",
        label_internal="Artikel-Langbeschreibung",
        label_weclapp="Artikel-Langbeschreibung",
        weclapp_column="AN",
        max_length=4000,
        width=220,
        **_ARTICLE,
    ),
    _f(
        field_key="long_description_language",
        label_internal="Handelssprache (Langbeschreibung)",
        label_weclapp="Handelssprache",
        weclapp_column="AO",
        max_length=10,
        width=110,
        **_ARTICLE,
    ),
    _f(
        field_key="localized_long_description",
        label_internal="Lokalisierte Lange Artikelbeschreibung",
        label_weclapp="Lokalisierte Lange Artikelbeschreibung",
        weclapp_column="AP",
        max_length=4000,
        width=220,
        **_ARTICLE,
    ),
    _f(
        field_key="ean",
        label_internal="EAN-Nummer",
        label_weclapp="EAN-Nummer",
        weclapp_column="AQ",
        max_length=20,
        width=120,
        **_ARTICLE,
    ),
    _f(
        field_key="mpn",
        label_internal="MPN-Nummer",
        label_weclapp="MPN-Nummer",
        weclapp_column="AR",
        max_length=50,
        width=120,
        **_ARTICLE,
    ),
    _f(
        field_key="manufacturer",
        label_internal="Hersteller",
        label_weclapp="Hersteller",
        weclapp_column="AU",
        max_length=255,
        width=140,
        **_ARTICLE,
    ),
    _f(
        field_key="gross_weight",
        label_internal="Bruttogewicht",
        label_weclapp="Bruttogewicht",
        weclapp_column="AV",
        input_kind="numeric",
        width=110,
        **_ARTICLE,
    ),
    _f(
        field_key="net_weight",
        label_internal="Nettogewicht",
        label_weclapp="Nettogewicht",
        weclapp_column="AW",
        input_kind="numeric",
        width=110,
        **_ARTICLE,
    ),
    _f(
        field_key="customs_tariff",
        label_internal="Zolltarifnummer",
        label_weclapp="Zolltarifnummer",
        weclapp_column="AX",
        max_length=20,
        width=130,
        **_ARTICLE,
    ),
    _f(
        field_key="article_length",
        label_internal="Länge Artikel",
        label_weclapp="Länge Artikel",
        weclapp_column="AY",
        input_kind="numeric",
        width=110,
        **_ARTICLE,
    ),
    _f(
        field_key="article_width",
        label_internal="Breite Artikel",
        label_weclapp="Breite Artikel",
        weclapp_column="AZ",
        input_kind="numeric",
        width=110,
        **_ARTICLE,
    ),
    _f(
        field_key="article_height",
        label_internal="Höhe Artikel",
        label_weclapp="Höhe Artikel",
        weclapp_column="BA",
        input_kind="numeric",
        width=110,
        **_ARTICLE,
    ),
    _f(
        field_key="manufacturer_type",
        label_internal="Herstellertyp",
        label_weclapp="Herstellertyp",
        weclapp_column="BB",
        max_length=100,
        width=120,
        **_ARTICLE,
    ),
    _f(
        field_key="launch_date",
        label_internal="Einführungsdatum",
        label_weclapp="Einführungsdatum",
        weclapp_column="BC",
        input_kind="date",
        width=120,
        **_ARTICLE,
    ),
    # --- Derived CSV columns, never in picker ---
    _f(
        field_key="disc1_label",
        label_internal="Zu- und Abschläge Bezeichnung 1",
        label_weclapp="Zu- und Abschläge Bezeichnung 1",
        weclapp_column="H",
        scope="derived",
        max_length=1000,
        write_policy="always",
        edit_policy="derived",
        default_visible=False,
        input_kind="derived",
        store="derived",
        description="Provenienz Rabatt 1",
    ),
    _f(
        field_key="disc1_type",
        label_internal="Zu- und Abschläge Preisart 1",
        label_weclapp="Zu- und Abschläge Preisart 1",
        weclapp_column="I",
        scope="derived",
        write_policy="always",
        edit_policy="derived",
        default_visible=False,
        input_kind="derived",
        store="derived",
        note="Immer DISCOUNT_PCT; nicht anzeigen.",
        description="Preisart 1, abgeleitet von Rabattkat.",
    ),
    _f(
        field_key="disc2_label",
        label_internal="Zu- und Abschläge Bezeichnung 2",
        label_weclapp="Zu- und Abschläge Bezeichnung 2",
        weclapp_column="K",
        scope="derived",
        max_length=1000,
        write_policy="always",
        edit_policy="derived",
        default_visible=False,
        input_kind="derived",
        store="derived",
        description="Provenienz Rabatt 2",
    ),
    _f(
        field_key="disc2_type",
        label_internal="Zu- und Abschläge Preisart 2",
        label_weclapp="Zu- und Abschläge Preisart 2",
        weclapp_column="L",
        scope="derived",
        write_policy="always",
        edit_policy="derived",
        default_visible=False,
        input_kind="derived",
        store="derived",
        note="Immer DISCOUNT_PCT; nicht anzeigen.",
        description="Preisart 2, abgeleitet von Rabattkat.",
    ),
    _f(
        field_key="currency",
        label_internal="Währung",
        label_weclapp="Währung",
        weclapp_column="N",
        scope="derived",
        write_policy="always",
        edit_policy="derived",
        default_visible=False,
        input_kind="derived",
        store="derived",
        description="Immer EUR zum Bruttokaufpreis",
    ),
    _f(
        field_key="trade_language",
        label_internal="Handelssprache",
        label_weclapp="Handelssprache",
        weclapp_column="B",
        scope="article",
        max_length=10,
        write_policy="locked",
        edit_policy="read_only",
        default_visible=False,
        picker_group="article",
        store="article_context",
        note=ARTICLE_READ_ONLY_NOTE,
        width=110,
    ),
    # --- Phase 2 / never shown ---
    _f(
        field_key="price_entry",
        label_internal="Preis-Eintritt",
        label_weclapp="Preis-Eintritt",
        weclapp_column="R",
        scope="derived",
        write_policy="always",
        edit_policy="derived",
        default_visible=False,
        input_kind="date",
        store="derived",
        phase=1,
        note="Gültig-ab des Einkaufspreises. Am Lauf setzen — kein stilles «heute».",
        description="Purchase-price start date; required run setting, no default",
    ),
    _f(
        field_key="create_sales_article",
        label_internal="Zugehörigen Verkaufsartikel erstellen oder aktualisieren",
        label_weclapp="Zugehörigen Verkaufsartikel erstellen oder aktualisieren",
        weclapp_column="V",
        scope="article",
        input_kind="ja_nein",
        **_LOCKED_PHASE2,
    ),
    _f(
        field_key="sales_article_number",
        label_internal="Verkaufsartikel-Nummer",
        label_weclapp="Verkaufsartikel-Nummer",
        weclapp_column="W",
        scope="derived",
        max_length=1000,
        is_mandatory=True,
        write_policy="always",
        edit_policy="derived",
        default_visible=False,
        store="derived",
        phase=1,
        note=(
            "Immer die PROSEMA-Artikelnummer. Leer lässt weclapp einen neuen "
            "Verkaufsartikel aus der Lieferantenartikelnummer anlegen."
        ),
        description="Sales-article link; always export_row.article_number",
    ),
    _f(
        field_key="sales_price",
        label_internal="Bruttopreis des zugehörigen Verkaufsartikels",
        label_weclapp="Bruttopreis des zugehörigen Verkaufsartikels",
        weclapp_column="X",
        scope="article",
        write_policy="locked",
        edit_policy="read_only",
        default_visible=False,
        phase=1,
        note="Verkaufspreis-Kaskade; würde N, R, Z pflichtig machen.",
        description="Phase 1 gesperrt",
        store="derived",
    ),
    _f(
        field_key="sales_currency",
        label_internal="Verkaufsartikel-Währung",
        label_weclapp="Verkaufsartikel-Währung",
        weclapp_column="Y",
        scope="derived",
        write_policy="always",
        edit_policy="derived",
        default_visible=False,
        input_kind="derived",
        store="derived",
        phase=1,
        note="Verkaufswährung der PROSEMA-Artikel: EUR (bestätigt). CHF in der Maske ist Planungszahl, nicht weclapp.",
        description="PROSEMA sales-article currency; EUR is correct, not a placeholder",
    ),
    _f(
        field_key="sales_channel",
        label_internal="Vertriebsweg",
        label_weclapp="Vertriebsweg",
        weclapp_column="Z",
        scope="article",
        **_LOCKED_PHASE2,
    ),
    _f(
        field_key="sales_channel_tax",
        label_internal="Vertriebsweg-Steuersatz",
        label_weclapp="Vertriebsweg-Steuersatz",
        weclapp_column="AA",
        scope="article",
        **_LOCKED_PHASE2,
    ),
    _f(
        field_key="article_type",
        label_internal="Artikeltyp",
        label_weclapp="Artikeltyp",
        weclapp_column="AS",
        scope="article",
        write_policy="locked",
        edit_policy="read_only",
        default_visible=False,
        phase=1,
        note="Nur bei Artikelanlage; auf Update wirkungslos.",
        store="derived",
    ),
    _f(
        field_key="serial_article",
        label_internal="Serienartikel",
        label_weclapp="Serienartikel",
        weclapp_column="AT",
        scope="article",
        write_policy="locked",
        edit_policy="read_only",
        default_visible=False,
        phase=1,
        note="Nur bei Artikelanlage; auf Update wirkungslos.",
        store="derived",
    ),
)


BY_KEY: dict[str, FieldSpec] = {}
for _spec in FIELDS:
    if _spec.field_key in BY_KEY:
        raise RuntimeError(f"duplicate field_key {_spec.field_key!r}")
    BY_KEY[_spec.field_key] = _spec

BY_COLUMN: dict[str, FieldSpec] = {
    spec.weclapp_column: spec for spec in FIELDS if spec.weclapp_column
}


def identity_keys() -> tuple[str, ...]:
    return tuple(spec.field_key for spec in FIELDS if spec.picker_group == "identity")


def picker_fields() -> tuple[FieldSpec, ...]:
    return tuple(spec for spec in FIELDS if spec.in_picker)


def grid_field_order() -> tuple[str, ...]:
    """Display order: article number + name frozen, then remaining picker groups."""
    leading = (
        "article_number",
        "article_name",
        "supplier_article_number",
        "supplier_number",
        "unit",
    )
    keys: list[str] = [key for key in leading if key in BY_KEY]
    seen = set(keys)
    for group, _label, _hint in PICKER_GROUPS:
        for spec in FIELDS:
            if spec.picker_group == group and spec.field_key not in seen and spec.in_picker:
                keys.append(spec.field_key)
                seen.add(spec.field_key)
    return tuple(keys)


def default_visible_keys() -> tuple[str, ...]:
    order = grid_field_order()
    return tuple(key for key in order if BY_KEY[key].default_visible)


def preset_keys(preset: str) -> tuple[str, ...]:
    order = grid_field_order()
    if preset == PRESET_ALL:
        return order
    if preset == PRESET_MANDATORY:
        allowed = {"identity", "working"}
        return tuple(key for key in order if BY_KEY[key].picker_group in allowed)
    allowed = {"identity", "working", "context"}
    return tuple(key for key in order if BY_KEY[key].picker_group in allowed)


def resolve_visible_keys(stored: list[str] | None) -> list[str]:
    available = {spec.field_key for spec in picker_fields()}
    identity = set(identity_keys())
    if not stored:
        chosen = set(default_visible_keys())
    else:
        chosen = {key for key in stored if key in available}
    chosen |= identity
    return [key for key in grid_field_order() if key in chosen]


def editable_keys() -> frozenset[str]:
    return frozenset(
        spec.field_key
        for spec in FIELDS
        if spec.edit_policy == "editable" and spec.phase == 1
    )


def freeze_candidates() -> tuple[str, ...]:
    return ("article_number", "article_name")


def freeze_column_count(visible: list[str]) -> int:
    n = 0
    for key in freeze_candidates():
        if n < len(visible) and visible[n] == key:
            n += 1
        else:
            break
    return n


def field_alias_seed_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in FIELDS:
        rows.append(
            {
                "field_key": spec.field_key,
                "label_internal": spec.label_internal,
                "label_weclapp": spec.label_weclapp,
                "weclapp_column": spec.weclapp_column,
                "description": spec.description or spec.note,
                "scope": spec.scope,
                "max_length": spec.max_length,
                "is_mandatory": spec.is_mandatory,
                "write_policy": spec.write_policy,
                "edit_policy": spec.edit_policy,
                "default_visible": spec.default_visible,
                "phase": spec.phase,
                "note": spec.note,
            }
        )
    return rows


def column_letter_index(letter: str) -> int:
    """A→0, Z→25, AA→26. Empty letter returns -1."""
    text = (letter or "").strip().upper()
    if not text or not text.isalpha():
        return -1
    n = 0
    for char in text:
        n = n * 26 + (ord(char) - 64)
    return n - 1
