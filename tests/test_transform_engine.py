"""Pure transform engine — no weclapp, no database."""

from __future__ import annotations

from app.transform.engine import apply_operations
from app.transform.schemas import RemoveLiteral, RemoveWord, ReplaceLiteral, ReplaceWord
from app.transform.word_position import literal_match_embedded
from core.article_write_fields import ValueKind


def test_operation_order_avoids_winkel_winkelprofil():
    ops = [
        ReplaceLiteral(op="replace_literal", search="Winkel-Abschlussprofil", replace="Winkelprofil"),
        ReplaceLiteral(op="replace_literal", search="Abschlussprofil", replace="Winkelprofil"),
    ]
    assert (
        apply_operations("Winkel-Abschlussprofil Aluminium", ops, ValueKind.PLAIN_TEXT)
        == "Winkelprofil Aluminium"
    )


def test_reversed_order_produces_winkel_winkelprofil():
    ops = [
        ReplaceLiteral(op="replace_literal", search="Abschlussprofil", replace="Winkelprofil"),
        ReplaceLiteral(op="replace_literal", search="Winkel-Abschlussprofil", replace="Winkelprofil"),
    ]
    # First op already turned the compound into Winkel-Winkelprofil; second no longer matches.
    assert (
        apply_operations("Winkel-Abschlussprofil", ops, ValueKind.PLAIN_TEXT)
        == "Winkel-Winkelprofil"
    )


def test_word_does_not_match_inside_eckverbinder_or_hyphen():
    ops = [ReplaceWord(op="replace_word", search="verbinder", replace="Verbinder")]
    assert apply_operations("Eckverbinder", ops, ValueKind.PLAIN_TEXT) == "Eckverbinder"
    assert apply_operations("verbinder-set", ops, ValueKind.PLAIN_TEXT) == "verbinder-set"
    assert apply_operations("Alu verbinder gerade", ops, ValueKind.PLAIN_TEXT) == (
        "Alu Verbinder gerade"
    )


def test_html_substitution_leaves_tags():
    ops = [ReplaceLiteral(op="replace_literal", search="Winkelprofil", replace="X")]
    html = '<p class="Winkelprofil">Winkelprofil</p>'
    out = apply_operations(html, ops, ValueKind.HTML)
    assert out == '<p class="Winkelprofil">X</p>'


def test_remove_literal_and_unchanged():
    ops = [RemoveLiteral(op="remove_literal", search="foo")]
    assert apply_operations("bar", ops, ValueKind.PLAIN_TEXT) == "bar"
    assert apply_operations("foo bar", ops, ValueKind.PLAIN_TEXT) == " bar"


def test_replace_literal_empty_replace_deletes_search():
    from app.transform.schemas import ReplaceLiteral

    ops = [ReplaceLiteral(op="replace_literal", search="[", replace="")]
    assert apply_operations("Alu [eloxiert]", ops, ValueKind.PLAIN_TEXT) == "Alu eloxiert]"


def test_remove_word():
    ops = [RemoveWord(op="remove_word", search="verbinder")]
    assert apply_operations("Alu verbinder", ops, ValueKind.PLAIN_TEXT) == "Alu "


def test_literal_match_embedded_standalone_compound_hyphen():
    assert literal_match_embedded(
        "Abschlussprofil Aluminium", "Abschlussprofil", ValueKind.PLAIN_TEXT
    ) == [False]
    assert literal_match_embedded(
        "XAbschlussprofil", "Abschlussprofil", ValueKind.PLAIN_TEXT
    ) == [True]
    assert literal_match_embedded(
        "Winkel-Abschlussprofil", "Abschlussprofil", ValueKind.PLAIN_TEXT
    ) == [True]


def test_literal_match_html_ignores_tag_attribute():
    html = '<p class="Abschlussprofil">Abschlussprofil</p>'
    assert literal_match_embedded(html, "Abschlussprofil", ValueKind.HTML) == [False]
