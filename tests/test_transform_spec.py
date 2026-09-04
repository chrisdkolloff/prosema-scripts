"""TransformSpec validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.transform.schemas import TransformSpec


def _base(**overrides):
    data = {
        "scope": {"article_numbers": ["999.999.001"]},
        "fields": ["Prosema-Artikelname"],
        "operations": [
            {"op": "replace_literal", "search": "Abschlussprofil", "replace": "Winkelprofil"}
        ],
    }
    data.update(overrides)
    return data


def test_ampersand_search_refused_in_german():
    with pytest.raises(ValidationError, match="Suchbegriffe mit & werden nicht unterstützt"):
        TransformSpec.model_validate(
            _base(
                operations=[
                    {"op": "replace_literal", "search": "a & b", "replace": "x"}
                ]
            )
        )


def test_empty_search_refused():
    with pytest.raises(ValidationError, match="Suchbegriff darf nicht leer sein"):
        TransformSpec.model_validate(
            _base(operations=[{"op": "remove_literal", "search": ""}])
        )


def test_star_search_is_not_a_wildcard():
    with pytest.raises(ValidationError, match="kein Platzhalter"):
        TransformSpec.model_validate(
            _base(
                operations=[
                    {
                        "op": "replace_literal",
                        "search": "*",
                        "replace": "TEST BESCHREIBUNG",
                    }
                ]
            )
        )


def test_search_equals_replace_refused():
    with pytest.raises(ValidationError, match="Suche und Ersatz sind identisch"):
        TransformSpec.model_validate(
            _base(
                operations=[
                    {"op": "replace_literal", "search": "x", "replace": "x"}
                ]
            )
        )


def test_empty_replace_is_allowed_deletion():
    spec = TransformSpec.model_validate(
        _base(
            operations=[
                {"op": "replace_literal", "search": "[", "replace": ""}
            ]
        )
    )
    assert spec.operations[0].replace == ""


def test_non_pass1_field_refused():
    with pytest.raises(ValidationError, match="Prosema-Artikelnummer"):
        TransformSpec.model_validate(_base(fields=["Prosema-Artikelnummer"]))


def test_scope_must_be_xor():
    with pytest.raises(ValidationError, match="Artikelnummern oder einen Filter"):
        TransformSpec.model_validate(
            {
                "scope": {},
                "fields": ["Prosema-Artikelname"],
                "operations": [{"op": "remove_literal", "search": "x"}],
            }
        )


def test_valid_spec():
    spec = TransformSpec.model_validate(_base())
    assert spec.operations[0].op == "replace_literal"


def test_replace_literal_substring_warns_when_search_in_replace():
    spec = TransformSpec.model_validate(
        _base(
            operations=[
                {
                    "op": "replace_literal",
                    "search": "Profil",
                    "replace": "xProfil",
                }
            ]
        )
    )
    assert spec.idempotency_warnings
    assert "nicht idempotent" in spec.idempotency_warnings[0]


def test_replace_literal_weiss_to_weiss_titlecase_does_not_warn():
    spec = TransformSpec.model_validate(
        _base(
            operations=[
                {"op": "replace_literal", "search": "weiss", "replace": "Weiss"}
            ]
        )
    )
    assert spec.idempotency_warnings == []


def test_replace_word_warns_when_replace_still_contains_token():
    spec = TransformSpec.model_validate(
        _base(
            operations=[
                {"op": "replace_word", "search": "foo", "replace": "foo bar"}
            ]
        )
    )
    assert spec.idempotency_warnings
    assert "nicht idempotent" in spec.idempotency_warnings[0]


def test_replace_word_case_only_is_idempotent():
    spec = TransformSpec.model_validate(
        _base(
            operations=[
                {
                    "op": "replace_word",
                    "search": "verbinder",
                    "replace": "Verbinder",
                }
            ]
        )
    )
    assert spec.idempotency_warnings == []


def test_supplied_idempotency_warnings_are_recomputed():
    spec = TransformSpec.model_validate(
        _base(
            operations=[{"op": "remove_literal", "search": "x"}],
            idempotency_warnings=["stale"],
        )
    )
    assert spec.idempotency_warnings == []


def test_destructive_insertion_when_replace_already_in_values():
    from app.transform.schemas import destructive_insertion_refusal

    spec = TransformSpec.model_validate(
        _base(
            operations=[
                {"op": "replace_literal", "search": "mm", "replace": " mm"}
            ]
        )
    )
    op = spec.operations[0]
    assert destructive_insertion_refusal(op, ["150mm"]) is None
    refused = destructive_insertion_refusal(
        op, ["Winkelprofil 150 mm", "Abschlussprofil 200 mm", "Winkelprofil 150 mm"]
    )
    assert refused is not None
    assert "3 bestehende Werte enthalten bereits « mm»" in refused
    assert "würden verdorben" in refused
    assert "«Winkelprofil 150 mm»" in refused
    assert "«Abschlussprofil 200 mm»" in refused


def test_destructive_insertion_singular_count():
    from app.transform.schemas import destructive_insertion_refusal

    spec = TransformSpec.model_validate(
        _base(
            operations=[
                {"op": "replace_literal", "search": "mm", "replace": " mm"}
            ]
        )
    )
    refused = destructive_insertion_refusal(spec.operations[0], ["Winkelprofil 150 mm"])
    assert refused is not None
    assert "1 bestehender Wert enthält bereits « mm»" in refused
    assert "würde verdorben" in refused
    assert "«Winkelprofil 150 mm»" in refused


def test_destructive_insertion_does_not_fire_without_substring():
    from app.transform.schemas import destructive_insertion_refusal

    spec = TransformSpec.model_validate(
        _base(
            operations=[
                {"op": "replace_word", "search": "weiss", "replace": "Weiss"}
            ]
        )
    )
    assert destructive_insertion_refusal(spec.operations[0], ["Weiss weiss"]) is None
