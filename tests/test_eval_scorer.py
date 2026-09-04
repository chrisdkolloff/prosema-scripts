"""Unit tests for tests/eval/run_eval.py scoring helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_RUN_EVAL = Path(__file__).resolve().parent / "eval" / "run_eval.py"
_SPEC = importlib.util.spec_from_file_location("eval_run_eval", _RUN_EVAL)
assert _SPEC is not None and _SPEC.loader is not None
eval_run = importlib.util.module_from_spec(_SPEC)
sys.modules["eval_run_eval"] = eval_run
_SPEC.loader.exec_module(eval_run)

Expect = eval_run.Expect
Question = eval_run.Question
score_question = eval_run.score_question
load_questions = eval_run.load_questions
QUESTIONS_PATH = eval_run.QUESTIONS_PATH
eval_model_label = eval_run.eval_model_label


def _q(**expect_kw) -> Question:
    kind = expect_kw.pop("kind", "tool_call")
    return Question(
        id="t",
        question_de="?",
        expect=Expect(kind=kind, **expect_kw),
    )


def _call(name: str, arguments: dict | None = None) -> dict:
    return {"name": name, "arguments": arguments or {}}


def test_load_questions_parses_new_fields():
    questions = {q.id: q for q in load_questions(QUESTIONS_PATH)}
    teuerste = questions["teuerste-duschsysteme"].expect
    assert teuerste.score_sort is True
    assert teuerste.sort_column == "Nettoverkaufspreis CHF"
    assert teuerste.sort_direction == "desc"
    assert teuerste.max_conditions == 1
    assert teuerste.forbid_columns == ["Nettoverkaufspreis CHF"]
    grouped = questions["count-by-hauptgruppe"].expect
    assert grouped.score_group_by is True
    assert grouped.group_by == "Hauptgruppe"
    datenstand = questions["datenstand-und-anzahl"].expect
    assert datenstand.score_group_by is True
    assert datenstand.group_by is None
    assert datenstand.max_conditions == 0
    refusal = questions["lieferzeit"].expect
    assert "refused" in (refusal.outcomes or [])
    omitted = questions["count-all"].expect
    assert omitted.score_group_by is False
    assert omitted.outcomes is None
    dural = questions["dural-ohne-ek"].expect
    assert "no_result" in (dural.outcomes or [])
    assert "answered" in (dural.outcomes or [])
    dural_score = score_question(
        questions["dural-ohne-ek"],
        outcome="no_result",
        tool_calls=[
            _call(
                "artikel_suchen",
                {
                    "filters": {
                        "conditions": [
                            {
                                "column": "Lieferanten Firmenname",
                                "operator": "eq",
                                "value": "DURAL GmbH",
                            },
                            {
                                "column": "Einkaufspreis EUR netto",
                                "operator": "is_null",
                            },
                        ]
                    }
                },
            )
        ],
        total_count=0,
    )
    assert dural_score.outcome == "pass"
    assert dural_score.overall() == "pass"
    schwere = questions["schwere-profile"].expect
    assert "no_result" in (schwere.outcomes or [])


def test_error_outcome_fails_even_with_correct_filter():
    question = _q(tools=["artikel_suchen"], columns=["article_number"], operators=["starts_with"])
    score = score_question(
        question,
        outcome="error",
        tool_calls=[
            _call(
                "artikel_suchen",
                {
                    "filters": {
                        "conditions": [
                            {
                                "column": "article_number",
                                "operator": "starts_with",
                                "value": "020.",
                            }
                        ]
                    }
                },
            )
        ],
        total_count=10,
    )
    assert score.tool == "pass"
    assert score.columns == "pass"
    assert score.operators == "pass"
    assert score.outcome == "fail"
    assert score.overall() == "fail"


def test_invented_price_filter_fails_forbid_and_max_conditions():
    question = _q(
        tools=["artikel_suchen"],
        columns=["Hauptgruppe"],
        operators=["eq"],
        score_sort=True,
        sort_column="Nettoverkaufspreis CHF",
        sort_direction="desc",
        max_conditions=1,
        forbid_columns=["Nettoverkaufspreis CHF"],
    )
    score = score_question(
        question,
        outcome="answered",
        tool_calls=[
            _call(
                "artikel_suchen",
                {
                    "filters": {
                        "conditions": [
                            {"column": "Hauptgruppe", "operator": "eq", "value": "Duschsysteme"},
                            {
                                "column": "Nettoverkaufspreis CHF",
                                "operator": "gt",
                                "value": "0",
                            },
                        ]
                    },
                    "sort": {"column": "Nettoverkaufspreis CHF", "direction": "desc"},
                },
            )
        ],
        total_count=508,
    )
    assert score.sort == "pass"
    assert score.forbid == "fail"
    assert score.conditions == "fail"
    assert score.outcome == "pass"
    assert score.overall() == "fail"


def test_group_by_null_rejects_grouping():
    question = _q(tools=["datenstand"], score_group_by=True, group_by=None, max_conditions=0)
    grouped = score_question(
        question,
        outcome="answered",
        tool_calls=[_call("datenstand", {"group_by": "Hauptgruppe"})],
        total_count=1,
    )
    assert grouped.group_by == "fail"
    clean = score_question(
        question,
        outcome="answered",
        tool_calls=[_call("datenstand", {})],
        total_count=1,
    )
    assert clean.group_by == "pass"
    assert clean.conditions == "pass"


def test_sort_direction_optional():
    question = _q(
        tools=["artikel_suchen"],
        score_sort=True,
        sort_column="Nettoverkaufspreis CHF",
    )
    score = score_question(
        question,
        outcome="answered",
        tool_calls=[
            _call(
                "artikel_suchen",
                {"sort": {"column": "Nettoverkaufspreis CHF", "direction": "desc"}},
            )
        ],
        total_count=1,
    )
    assert score.sort == "pass"


def test_omitted_shape_fields_are_na():
    question = _q(tools=["artikel_zaehlen"])
    score = score_question(
        question,
        outcome="answered",
        tool_calls=[_call("artikel_zaehlen", {"group_by": "Hauptgruppe"})],
        total_count=16,
    )
    assert score.group_by == "n/a"
    assert score.sort == "n/a"
    assert score.forbid == "n/a"
    assert score.conditions == "n/a"
    assert score.outcome == "pass"


def test_eval_model_label_uses_azure_deployment_not_local_model():
    assert (
        eval_model_label(
            "azure",
            assistant_model="qwen/qwen3-4b-2507",
            azure_deployment="gpt-4.1-mini",
        )
        == "gpt-4.1-mini"
    )
    assert (
        eval_model_label(
            "openai_compatible",
            assistant_model="qwen/qwen3-4b-2507",
            azure_deployment="gpt-4.1-mini",
        )
        == "qwen/qwen3-4b-2507"
    )
    assert eval_model_label("azure", assistant_model="qwen", azure_deployment=None) == "qwen"
    assert eval_model_label("azure", assistant_model="qwen", azure_deployment="") == "qwen"


def test_no_answer_fails_default_outcome():
    question = _q(tools=["artikel_suchen"])
    score = score_question(
        question,
        outcome="no_answer",
        tool_calls=[_call("artikel_suchen")],
        total_count=4,
    )
    assert score.outcome == "fail"
    assert score.overall() == "fail"


def test_empty_replace_literal_scores_as_remove_literal():
    question = eval_run.TransformQuestion(
        id="grundmaterial-brackets",
        question_de="?",
        expect=eval_run.TransformExpect(
            outcome="proposed",
            fields=["Grundmaterial"],
            ops=[
                {"type": "remove_literal", "search": "["},
                {"type": "remove_literal", "search": "]"},
            ],
        ),
    )
    spec = {
        "fields": ["Grundmaterial"],
        "operations": [
            {"op": "replace_literal", "search": "[", "replace": ""},
            {"op": "replace_literal", "search": "]", "replace": ""},
        ],
    }
    score = eval_run.score_transform_question(
        question,
        spec=spec,
        tool_calls=[],
        total_count=1,
        answer_de="",
        hinweis_de=None,
    )
    assert score.ops_match == "pass"
    assert score.overall() == "pass"
