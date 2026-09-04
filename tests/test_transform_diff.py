"""Transform diff segmentation and HTML projection."""

from __future__ import annotations

from app.transform.diff import (
    MSG_HTML_FORMAT,
    contains_markup,
    html_projection,
    render_diff_html,
    segments_from_fired,
)
from app.transform.engine import operations_fired
from app.transform.schemas import ReplaceLiteral
from core.article_write_fields import ValueKind


def test_html_projection_strips_tags_and_render_escapes():
    raw = '<p class="x">Altes <b>Wort</b> &amp; Co</p>'
    assert html_projection(raw) == "Altes Wort &amp; Co"
    assert contains_markup(raw)
    segs = segments_from_fired(
        raw,
        '<p class="x">Neues <b>Wort</b> &amp; Co</p>',
        [
            {
                "op": "replace_literal",
                "search": "Altes",
                "replace": "Neues",
                "before": raw,
                "after": '<p class="x">Neues <b>Wort</b> &amp; Co</p>',
            }
        ],
        value_kind=ValueKind.HTML,
    )
    html = str(render_diff_html(segs))
    assert "<p" not in html
    assert "<b>" not in html
    assert "&amp;" in html or "amp" in html
    assert "text-danger" in html
    assert "text-success" in html
    assert MSG_HTML_FORMAT


def test_two_operation_ordered_spec_not_naive_endpoint_diff():
    ops = [
        ReplaceLiteral(op="replace_literal", search="Winkel-Abschlussprofil", replace="Winkelprofil"),
        ReplaceLiteral(op="replace_literal", search="Abschlussprofil", replace="Winkelprofil"),
    ]
    old = "Abschlussprofil und Winkel-Abschlussprofil"
    fired = operations_fired(old, ops, ValueKind.PLAIN_TEXT)
    assert len(fired) == 2
    assert "before" in fired[0] and "after" in fired[0]
    segs = segments_from_fired(old, fired[-1]["after"], fired, value_kind=ValueKind.PLAIN_TEXT)
    kinds = [s.kind for s in segs]
    assert "deleted" in kinds
    assert "inserted" in kinds
    # Naive old-vs-new would also delete the hyphenated prefix as several spans;
    # per-op rendering keeps the first replacement as one inserted Winkelprofil.
    inserted = "".join(s.text for s in segs if s.kind == "inserted")
    deleted = "".join(s.text for s in segs if s.kind == "deleted")
    assert "Winkelprofil" in inserted
    assert "Winkel-Abschlussprofil" in deleted
    assert "Abschlussprofil" in deleted
