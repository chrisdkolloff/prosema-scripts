"""Shared transform UI copy and availability gate. No routes."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.assistant.catalog import snapshot_for_query
from app.batch_actions import snapshot_age_warning
from app.models import ArticleSnapshot
from app.transform.schemas import MSG_AMP, MSG_EMPTY_SEARCH, MSG_NON_IDEM, MSG_NOOP, TransformSpec
from core.article_write_fields import pass_1_fields

MSG_MODE_READ = "Lesen"
MSG_MODE_EDIT = "Ändern"
MSG_TRANSFORM_UNAVAILABLE = (
    "Ändern ist nur mit der aktuellen Artikelübersicht möglich, und nur "
    "innerhalb von 24 Stunden nach der Abfrage."
)
MSG_TRANSFORM_PULL = "Neue Abfrage starten"
MSG_OPS_ORDER = (
    "Die Reihenfolge ist maßgeblich: «Winkel-Abschlussprofil» → «Winkelprofil» "
    "muss vor «Abschlussprofil» → «Winkelprofil» stehen, sonst entsteht "
    "«Winkel-Winkelprofil»."
)
MSG_REPLACE_WORD_HINT = (
    "Wort ersetzen ist die Vorgabe für eigenständige deutsche Substantive. "
    "Gemessen: «verbinder» lässt Winkelverbinder und LED-Direktverbinder unangetastet."
)
MSG_SCOPE_GRID = (
    "Die Suche im Formular wählt keine Artikel. Gilt der aktuelle Filter "
    "der Übersicht oder die in der Tabelle markierten Zeilen."
)
MSG_OPEN_PREVIEW = "Vorschau öffnen"
MSG_MANUAL_FALLBACK = "Vorgabe manuell korrigieren"
MSG_WRITE_PROMPT = (
    "Beschreibe die gewünschte Änderung. {name} schlägt eine Vorgabe vor; "
    "die Vorschau startest du selbst."
)
FIELD_LABELS_DE = {
    "Prosema-Artikelname": "Name",
    "Prosema-Langtext": "Langtext",
    "Kurzbeschreibung": "Kurzbeschreibung",
}
OP_LABELS = {
    "replace_word": "Wort ersetzen",
    "replace_literal": "Text ersetzen",
    "remove_word": "Wort entfernen",
    "remove_literal": "Text entfernen",
}


def pass_1_choices() -> list[str]:
    return [field.snapshot_key for field in pass_1_fields()]


def transform_gate(db: Session, snapshot: ArticleSnapshot) -> dict[str, Any]:
    current = snapshot_for_query(db)
    is_current = current is not None and current.id == snapshot.id
    stale = snapshot_age_warning(snapshot)
    allowed = bool(snapshot.status == "complete" and is_current and stale is None)
    reasons: list[str] = []
    if snapshot.status == "complete" and not allowed:
        reasons.append(MSG_TRANSFORM_UNAVAILABLE)
        if stale:
            reasons.append(stale)
    return {
        "transform_allowed": allowed,
        "transform_unavailable_reasons": reasons,
        "transform_is_current": is_current,
    }


def transform_form_context() -> dict[str, Any]:
    return {
        "pass_1_fields": pass_1_choices(),
        "op_labels": OP_LABELS,
        "msg_amp": MSG_AMP,
        "msg_empty_search": MSG_EMPTY_SEARCH,
        "msg_noop": MSG_NOOP,
        "msg_non_idem": MSG_NON_IDEM,
        "msg_ops_order": MSG_OPS_ORDER,
        "msg_replace_word_hint": MSG_REPLACE_WORD_HINT,
        "msg_scope_grid": MSG_SCOPE_GRID,
        "msg_mode_read": MSG_MODE_READ,
        "msg_mode_edit": MSG_MODE_EDIT,
        "msg_transform_unavailable": MSG_TRANSFORM_UNAVAILABLE,
        "msg_transform_pull": MSG_TRANSFORM_PULL,
        "msg_open_preview": MSG_OPEN_PREVIEW,
        "msg_manual_fallback": MSG_MANUAL_FALLBACK,
    }


def _scope_phrase_de(spec: TransformSpec) -> str:
    if spec.scope.article_numbers is not None:
        n = len(spec.scope.article_numbers)
        return f"Bei {n} ausgewählten Artikeln"
    raw = spec.scope.query_filter or {}
    conditions = raw.get("conditions") or []
    if not conditions:
        return "Im gesamten Katalog"
    parts: list[str] = []
    for condition in conditions:
        if not isinstance(condition, dict):
            continue
        column = str(condition.get("column") or "")
        operator = str(condition.get("operator") or "")
        value = condition.get("value")
        if operator == "eq" and column in {"Untergruppe", "untergruppe"}:
            parts.append(f"in der Untergruppe «{value}»")
        elif operator == "eq" and column in {"Hauptgruppe", "hauptgruppe"}:
            parts.append(f"in der Hauptgruppe «{value}»")
        else:
            parts.append(f"«{column}» {operator} «{value}»")
    if not parts:
        return "Im gesamten Katalog"
    first = parts[0]
    if first.startswith("in der "):
        first = "In der " + first[len("in der ") :]
    rest = ", ".join(parts[1:])
    return f"{first}, {rest}" if rest else first


def format_spec_summary_de(spec: TransformSpec | Any) -> str:
    from app.group_assign import GroupAssignSpec, format_group_assign_summary_de

    if isinstance(spec, GroupAssignSpec):
        return format_group_assign_summary_de(spec)
    fields = ", ".join(FIELD_LABELS_DE.get(key, key) for key in spec.fields)
    header = f"{_scope_phrase_de(spec)}, Felder {fields}:"
    lines = [header]
    for index, operation in enumerate(spec.operations, start=1):
        replace = getattr(operation, "replace", None)
        if replace is not None:
            lines.append(f"  {index}. «{operation.search}» → «{replace}»")
        else:
            lines.append(f"  {index}. «{operation.search}» entfernen")
    return "\n".join(lines)


def proposed_spec_from_tool_calls(
    tool_calls: list[dict[str, Any]] | None,
) -> TransformSpec | Any | None:
    if not tool_calls:
        return None
    from app.group_assign import GroupAssignSpec

    for call in reversed(tool_calls):
        if not isinstance(call, dict) or call.get("error"):
            continue
        name = call.get("name")
        raw = call.get("spec")
        if not isinstance(raw, dict):
            continue
        if name == "gruppen_zuordnen":
            try:
                return GroupAssignSpec.model_validate(raw)
            except (ValueError, TypeError):
                return None
        if name == "transform_vorschlagen":
            try:
                return TransformSpec.model_validate(raw)
            except (ValueError, TypeError):
                return None
    return None
