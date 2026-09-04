"""Offline eval harness for the article assistant.

Not a pytest test — this calls a real model and costs tokens. Invoke from the
repo root:

    python tests/eval/run_eval.py --provider openai_compatible --model qwen2.5
    python tests/eval/run_eval.py --id count-all --limit 1
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from unittest.mock import patch

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.assistant.catalog import get_column
from app.assistant.client import LLMResponse, ToolCall
from app.assistant.service import ask
from app.assistant.tools import resolve_current_snapshot
from app.config import settings
from app.db import SessionLocal
from app.models import AssistantQuery

EVAL_DIR = Path(__file__).resolve().parent
QUESTIONS_PATH = EVAL_DIR / "questions.yaml"
RESULTS_DIR = EVAL_DIR / "results"
DEFAULT_LOCAL_BASE_URL = "http://127.0.0.1:1234/v1"
EVAL_TIMEOUT_SECONDS = 120
EVAL_USER = {
    "oid": "eval-harness",
    "name": "Eval harness",
    "email": "eval@local",
    "roles": ["user"],
}

CRITERIA = (
    "tool",
    "columns",
    "operators",
    "rows",
    "group_by",
    "sort",
    "forbid",
    "conditions",
    "outcome",
    "refusal",
    "verified",
)
DEFAULT_OUTCOMES = ("answered",)

Mark = Literal["pass", "fail", "n/a"]


@dataclass
class Expect:
    kind: Literal["tool_call", "refusal"]
    tools: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    operators: list[str] = field(default_factory=list)
    min_rows: int | None = None
    max_rows: int | None = None
    reason: str | None = None
    score_group_by: bool = False
    group_by: str | None = None
    score_sort: bool = False
    sort_column: str | None = None
    sort_direction: str | None = None
    forbid_columns: list[str] = field(default_factory=list)
    max_conditions: int | None = None
    outcomes: list[str] | None = None


@dataclass
class Question:
    id: str
    question_de: str
    expect: Expect
    notes: str = ""


@dataclass
class Score:
    tool: Mark
    columns: Mark
    operators: Mark
    rows: Mark
    group_by: Mark
    sort: Mark
    forbid: Mark
    conditions: Mark
    outcome: Mark
    refusal: Mark
    verified: Mark

    def overall(self) -> Mark:
        marks = [
            self.tool,
            self.columns,
            self.operators,
            self.rows,
            self.group_by,
            self.sort,
            self.forbid,
            self.conditions,
            self.outcome,
            self.refusal,
            self.verified,
        ]
        scored = [m for m in marks if m != "n/a"]
        if not scored:
            return "n/a"
        return "pass" if all(m == "pass" for m in scored) else "fail"

    def failed_names(self) -> list[str]:
        pairs = [
            ("tool match", self.tool),
            ("column match", self.columns),
            ("operator match", self.operators),
            ("row-count plausible", self.rows),
            ("group_by match", self.group_by),
            ("sort match", self.sort),
            ("no forbidden columns", self.forbid),
            ("condition count", self.conditions),
            ("outcome acceptable", self.outcome),
            ("refusal correct", self.refusal),
            ("verification passed", self.verified),
        ]
        return [name for name, mark in pairs if mark == "fail"]


@dataclass
class QuestionResult:
    question: Question
    score: Score
    outcome: str
    answer_de: str | None
    hinweis_de: str | None
    tool_calls: list[dict[str, Any]]
    total_count: int | None
    prompt_tokens: int
    completion_tokens: int
    model: str
    snapshot_id: str | None
    error: str | None


def _canonical_column(name: str) -> str:
    col = get_column(name)
    return col.name if col is not None else name


def _parse_string_list(raw: object, *, field: str, qid: object) -> list[str]:
    """YAML string or list of strings."""
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        name = raw.strip()
        return [name] if name else []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    raise SystemExit(f"{qid}: expect.{field} must be a string or a list of strings")


def _parse_tools(raw: object, *, qid: object) -> list[str]:
    """YAML `tool` is a string or a list; any listed name is acceptable."""
    return _parse_string_list(raw, field="tool", qid=qid)


def _parse_sort(raw: object, *, qid: object) -> tuple[bool, str | None, str | None]:
    """Return (score_sort, column, direction). Direction is optional."""
    if raw is None or raw == "":
        return False, None, None
    if isinstance(raw, str):
        column = raw.strip()
        if not column:
            return False, None, None
        return True, column, None
    if isinstance(raw, dict):
        column = str(raw.get("column") or "").strip()
        if not column:
            raise SystemExit(f"{qid}: expect.sort needs a column")
        direction_raw = raw.get("direction")
        if direction_raw is None or direction_raw == "":
            return True, column, None
        direction = str(direction_raw).strip().casefold()
        if direction not in {"asc", "desc"}:
            raise SystemExit(f"{qid}: expect.sort.direction must be asc or desc")
        return True, column, direction
    raise SystemExit(f"{qid}: expect.sort must be a column name or a mapping")


def load_questions(path: Path) -> list[Question]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        entries = raw.get("questions")
    else:
        entries = raw
    if not isinstance(entries, list) or not entries:
        raise SystemExit(f"No questions in {path}")
    questions: list[Question] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise SystemExit(f"Question entry is not a mapping: {entry!r}")
        expect_raw = entry.get("expect") or {}
        if not isinstance(expect_raw, dict):
            raise SystemExit(f"{entry.get('id')}: expect must be a mapping")
        kind = str(expect_raw.get("kind") or "").strip()
        if kind not in {"tool_call", "refusal"}:
            raise SystemExit(f"{entry.get('id')}: expect.kind must be tool_call or refusal")
        qid = entry.get("id")
        score_sort, sort_column, sort_direction = (
            _parse_sort(expect_raw.get("sort"), qid=qid)
            if "sort" in expect_raw
            else (False, None, None)
        )
        outcomes_raw = (
            _parse_string_list(expect_raw.get("outcome"), field="outcome", qid=qid)
            if "outcome" in expect_raw
            else None
        )
        questions.append(
            Question(
                id=str(entry.get("id") or "").strip(),
                question_de=str(entry.get("question_de") or "").strip(),
                notes=str(entry.get("notes") or "").strip(),
                expect=Expect(
                    kind=kind,  # type: ignore[arg-type]
                    tools=_parse_tools(expect_raw.get("tool"), qid=qid),
                    columns=[str(c) for c in (expect_raw.get("columns") or [])],
                    operators=[str(o) for o in (expect_raw.get("operators") or [])],
                    min_rows=expect_raw.get("min_rows"),
                    max_rows=expect_raw.get("max_rows"),
                    reason=(
                        str(expect_raw["reason"]).strip() if expect_raw.get("reason") else None
                    ),
                    score_group_by="group_by" in expect_raw,
                    group_by=(
                        str(expect_raw["group_by"]).strip()
                        if expect_raw.get("group_by") not in (None, "")
                        else None
                    ),
                    score_sort=score_sort,
                    sort_column=sort_column,
                    sort_direction=sort_direction,
                    forbid_columns=[str(c) for c in (expect_raw.get("forbid_columns") or [])],
                    max_conditions=expect_raw.get("max_conditions"),
                    outcomes=outcomes_raw or None,
                ),
            )
        )
    missing = [q.id or "(no id)" for q in questions if not q.id or not q.question_de]
    if missing:
        raise SystemExit(f"Questions missing id or question_de: {missing}")
    return questions


def eval_model_label(
    provider: str,
    *,
    assistant_model: str | None,
    azure_deployment: str | None,
) -> str:
    """Name recorded in the results file. Azure routes by deployment, not ASSISTANT_MODEL."""
    if provider == "azure":
        return (azure_deployment or "").strip() or (assistant_model or "").strip()
    return (assistant_model or "").strip()


def apply_runtime_settings(*, provider: str | None, model: str | None) -> None:
    """Point service.ask at the requested provider/model without editing app/."""
    settings.assistant_enabled = True
    if provider:
        settings.assistant_provider = provider  # type: ignore[assignment]
    if model:
        settings.assistant_model = model
        if settings.assistant_provider == "azure":
            settings.azure_openai_deployment = model
    if settings.assistant_provider == "openai_compatible" and not settings.assistant_base_url:
        settings.assistant_base_url = DEFAULT_LOCAL_BASE_URL
    settings.assistant_timeout_seconds = max(
        settings.assistant_timeout_seconds, EVAL_TIMEOUT_SECONDS
    )


def _conditions_from_calls(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for call in tool_calls:
        args = call.get("arguments") or {}
        if not isinstance(args, dict):
            continue
        filters = args.get("filters") or {}
        if not isinstance(filters, dict):
            continue
        conditions = filters.get("conditions") or []
        if isinstance(conditions, list):
            found.extend(c for c in conditions if isinstance(c, dict))
    return found


def _filter_columns(tool_calls: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for cond in _conditions_from_calls(tool_calls):
        column = cond.get("column")
        if column:
            names.add(_canonical_column(str(column)))
    return names


def _group_bys(tool_calls: list[dict[str, Any]]) -> list[str]:
    found: list[str] = []
    for call in tool_calls:
        args = call.get("arguments") or {}
        if not isinstance(args, dict):
            continue
        group_by = args.get("group_by")
        if group_by is None or str(group_by).strip() == "":
            continue
        found.append(_canonical_column(str(group_by)))
    return found


def _sorts(tool_calls: list[dict[str, Any]]) -> list[tuple[str, str | None]]:
    found: list[tuple[str, str | None]] = []
    for call in tool_calls:
        args = call.get("arguments") or {}
        if not isinstance(args, dict):
            continue
        sort = args.get("sort")
        if not sort:
            continue
        if isinstance(sort, str):
            found.append((_canonical_column(sort), None))
            continue
        if not isinstance(sort, dict):
            continue
        column = sort.get("column")
        if not column:
            continue
        direction_raw = sort.get("direction")
        direction = str(direction_raw).strip().casefold() if direction_raw else None
        found.append((_canonical_column(str(column)), direction or None))
    return found


def _condition_counts(tool_calls: list[dict[str, Any]]) -> list[int]:
    counts: list[int] = []
    for call in tool_calls:
        args = call.get("arguments") or {}
        if not isinstance(args, dict):
            counts.append(0)
            continue
        filters = args.get("filters") or {}
        conditions = filters.get("conditions") if isinstance(filters, dict) else []
        counts.append(len(conditions) if isinstance(conditions, list) else 0)
    return counts


def _referenced_columns(tool_calls: list[dict[str, Any]]) -> set[str]:
    names = _filter_columns(tool_calls)
    names.update(_group_bys(tool_calls))
    return names


def _referenced_operators(tool_calls: list[dict[str, Any]]) -> set[str]:
    ops: set[str] = set()
    for cond in _conditions_from_calls(tool_calls):
        operator = cond.get("operator")
        if operator:
            ops.add(str(operator))
    return ops


def _mark_subset(expected: list[str], actual: set[str], *, canonicalize: bool) -> Mark:
    if not expected:
        return "n/a"
    want = {_canonical_column(item) if canonicalize else item for item in expected}
    return "pass" if want <= actual else "fail"


def _shape_marks(expect: Expect, tool_calls: list[dict[str, Any]]) -> dict[str, Mark]:
    group_by: Mark = "n/a"
    if expect.score_group_by:
        actual = _group_bys(tool_calls)
        if expect.group_by is None:
            group_by = "pass" if not actual else "fail"
        else:
            want = _canonical_column(expect.group_by)
            group_by = "pass" if want in actual else "fail"

    sort: Mark = "n/a"
    if expect.score_sort and expect.sort_column:
        want = _canonical_column(expect.sort_column)
        want_dir = expect.sort_direction
        sort = "fail"
        for column, direction in _sorts(tool_calls):
            if column != want:
                continue
            if want_dir is None or direction == want_dir:
                sort = "pass"
                break

    forbid: Mark = "n/a"
    if expect.forbid_columns:
        banned = {_canonical_column(name) for name in expect.forbid_columns}
        used = _filter_columns(tool_calls)
        forbid = "fail" if banned & used else "pass"

    conditions: Mark = "n/a"
    if expect.max_conditions is not None:
        counts = _condition_counts(tool_calls) or [0]
        conditions = "pass" if max(counts) <= int(expect.max_conditions) else "fail"

    return {
        "group_by": group_by,
        "sort": sort,
        "forbid": forbid,
        "conditions": conditions,
    }


def _outcome_mark(expect: Expect, outcome: str) -> Mark:
    acceptable = expect.outcomes if expect.outcomes else list(DEFAULT_OUTCOMES)
    return "pass" if outcome in acceptable else "fail"


def score_question(
    question: Question,
    *,
    outcome: str,
    tool_calls: list[dict[str, Any]],
    total_count: int | None,
) -> Score:
    expect = question.expect
    called = [str(call.get("name") or "") for call in tool_calls]
    verified: Mark = "fail" if outcome == "answered_unverified" else "pass"
    shape = _shape_marks(expect, tool_calls)
    outcome_ok = _outcome_mark(expect, outcome)

    if expect.kind == "refusal":
        refused = not called and outcome in {"answered", "refused", "no_result"}
        if outcome == "refused":
            refused = True
        return Score(
            tool="n/a",
            columns="n/a",
            operators="n/a",
            rows="n/a",
            group_by=shape["group_by"],
            sort=shape["sort"],
            forbid=shape["forbid"],
            conditions=shape["conditions"],
            outcome=outcome_ok,
            refusal="pass" if refused else "fail",
            verified=verified,
        )

    tool_ok: Mark = "n/a"
    if expect.tools:
        acceptable = set(expect.tools)
        tool_ok = "pass" if acceptable.intersection(called) else "fail"

    rows: Mark = "n/a"
    if expect.min_rows is not None or expect.max_rows is not None:
        if total_count is None:
            rows = "fail"
        else:
            lo = expect.min_rows
            hi = expect.max_rows
            rows = "pass"
            if lo is not None and total_count < lo:
                rows = "fail"
            if hi is not None and total_count > hi:
                rows = "fail"

    return Score(
        tool=tool_ok,
        columns=_mark_subset(expect.columns, _referenced_columns(tool_calls), canonicalize=True),
        operators=_mark_subset(
            expect.operators, _referenced_operators(tool_calls), canonicalize=False
        ),
        rows=rows,
        group_by=shape["group_by"],
        sort=shape["sort"],
        forbid=shape["forbid"],
        conditions=shape["conditions"],
        outcome=outcome_ok,
        refusal="n/a",
        verified=verified,
    )


def _placeholder_value(operator: str) -> Any:
    if operator in {"is_null", "is_not_null"}:
        return None
    if operator == "in_list":
        return ["020."]
    if operator in {"gt", "gte", "lt", "lte"}:
        return "1"
    return "020."


def _scripted_tool_args(expect: Expect) -> dict[str, Any]:
    conditions = []
    ops = list(expect.operators)
    for index, column in enumerate(expect.columns):
        operator = ops[index] if index < len(ops) else (ops[-1] if ops else "eq")
        cond: dict[str, Any] = {"column": column, "operator": operator}
        value = _placeholder_value(operator)
        if value is not None:
            cond["value"] = value
        conditions.append(cond)
    args: dict[str, Any] = {}
    if conditions:
        args["filters"] = {"conditions": conditions}
    if expect.group_by:
        args["group_by"] = expect.group_by
    if expect.score_sort and expect.sort_column:
        sort: dict[str, str] = {"column": expect.sort_column}
        if expect.sort_direction:
            sort["direction"] = expect.sort_direction
        args["sort"] = sort
    return args


def _scripted_responses(question: Question, *, provider: str) -> list[LLMResponse]:
    """Deterministic client used by --mock so the table format can be inspected."""
    expect = question.expect
    if expect.kind == "refusal":
        answer = (
            "Ich kann «VPE 1» nicht numerisch vergleichen, weil Komma- und "
            "Punkt-Schreibweisen gemischt vorkommen (1,00 und 1.000)."
        )
        if provider == "openai_compatible":
            return [
                LLMResponse(
                    text=json.dumps({"answer": answer}, ensure_ascii=False),
                    model="mock",
                )
            ]
        return [LLMResponse(text=answer, model="mock")]

    args = _scripted_tool_args(expect)
    name = expect.tools[0] if expect.tools else "artikel_zaehlen"
    answer = "Ich habe die Treffer gefunden. Sie stehen in der Tabelle."
    if provider == "openai_compatible":
        return [
            LLMResponse(
                text=json.dumps({"tool": name, "args": args}, ensure_ascii=False),
                model="mock",
            ),
            LLMResponse(
                text=json.dumps({"answer": answer}, ensure_ascii=False),
                model="mock",
            ),
        ]
    return [
        LLMResponse(
            text=None,
            tool_calls=[ToolCall(name=name, arguments=args)],
            model="mock",
        ),
        LLMResponse(text=answer, model="mock"),
    ]


class _ScriptedClient:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)

    def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str | None = None,
    ) -> LLMResponse:
        if not self._responses:
            raise RuntimeError("mock client has no further scripted responses")
        return self._responses.pop(0)


def run_question(
    session,
    question: Question,
    *,
    mock: bool,
) -> QuestionResult:
    context: Any = nullcontext()
    if mock:
        client = _ScriptedClient(
            _scripted_responses(question, provider=settings.assistant_provider)
        )
        context = patch("app.assistant.service.get_client", return_value=client)
    with context:
        result = ask(session, EVAL_USER, question.question_de)
    audit = session.get(AssistantQuery, result.audit_id)
    tool_calls = list(audit.tool_calls) if audit is not None else []
    prompt_tokens = int(audit.prompt_tokens or 0) if audit is not None else 0
    completion_tokens = int(audit.completion_tokens or 0) if audit is not None else 0
    model_name = str(audit.model or "") if audit is not None else ""
    snapshot_id = str(audit.snapshot_id) if audit is not None and audit.snapshot_id else None
    error = str(audit.error) if audit is not None and audit.error else None
    score = score_question(
        question,
        outcome=result.outcome,
        tool_calls=tool_calls,
        total_count=result.total_count,
    )
    return QuestionResult(
        question=question,
        score=score,
        outcome=result.outcome,
        answer_de=result.answer_de,
        hinweis_de=result.hinweis_de,
        tool_calls=tool_calls,
        total_count=result.total_count,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        model=model_name,
        snapshot_id=snapshot_id,
        error=error,
    )


def _pipe(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_report(
    results: list[QuestionResult],
    *,
    provider: str,
    model: str,
    snapshot_id: str | None,
    mock: bool,
    timestamp: str,
) -> str:
    prompt_tokens = sum(item.prompt_tokens for item in results)
    completion_tokens = sum(item.completion_tokens for item in results)
    total_tokens = prompt_tokens + completion_tokens
    reported_model = model or next((item.model for item in results if item.model), "")
    reported_snapshot = snapshot_id or next(
        (item.snapshot_id for item in results if item.snapshot_id), None
    )

    lines: list[str] = [
        "# Assistant eval",
        "",
        f"- timestamp: `{timestamp}`",
        f"- provider: `{provider}`",
        f"- model: `{reported_model or '(unknown)'}`",
        f"- snapshot_id: `{reported_snapshot or '(none)'}`",
        f"- prompt_tokens: {prompt_tokens}",
        f"- completion_tokens: {completion_tokens}",
        f"- total_tokens: {total_tokens}",
        f"- mock: `{str(mock).lower()}`",
        "",
        "## Per question",
        "",
        "| id | tool | columns | operators | rows | group_by | sort | forbid | conditions | outcome | refusal | verified | overall |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in results:
        s = item.score
        lines.append(
            "| "
            + " | ".join(
                _pipe(v)
                for v in (
                    item.question.id,
                    s.tool,
                    s.columns,
                    s.operators,
                    s.rows,
                    s.group_by,
                    s.sort,
                    s.forbid,
                    s.conditions,
                    s.outcome,
                    s.refusal,
                    s.verified,
                    s.overall(),
                )
            )
            + " |"
        )

    totals: dict[str, tuple[int, int]] = {name: (0, 0) for name in CRITERIA}
    full_pass = 0
    for item in results:
        if item.score.overall() == "pass":
            full_pass += 1
        marks = {
            "tool": item.score.tool,
            "columns": item.score.columns,
            "operators": item.score.operators,
            "rows": item.score.rows,
            "group_by": item.score.group_by,
            "sort": item.score.sort,
            "forbid": item.score.forbid,
            "conditions": item.score.conditions,
            "outcome": item.score.outcome,
            "refusal": item.score.refusal,
            "verified": item.score.verified,
        }
        for name, mark in marks.items():
            if mark == "n/a":
                continue
            passed, scored = totals[name]
            totals[name] = (passed + (1 if mark == "pass" else 0), scored + 1)

    labels = {
        "tool": "tool match",
        "columns": "column match",
        "operators": "operator match",
        "rows": "row-count plausible",
        "group_by": "group_by match",
        "sort": "sort match",
        "forbid": "no forbidden columns",
        "conditions": "condition count",
        "outcome": "outcome acceptable",
        "refusal": "refusal correct",
        "verified": "verification passed",
    }
    lines += [
        "",
        "## Totals",
        "",
        f"Fully passed: **{full_pass} / {len(results)}**",
        "",
        "| criterion | passed | scored |",
        "| --- | --- | --- |",
    ]
    for name in CRITERIA:
        passed, scored = totals[name]
        lines.append(f"| {labels[name]} | {passed} | {scored} |")

    failures = [item for item in results if item.score.overall() == "fail"]
    lines += ["", "## Failures", ""]
    if not failures:
        lines.append("None.")
    else:
        for item in failures:
            lines += _failure_detail(item)
    lines.append("")
    return "\n".join(lines)


def _failure_detail(item: QuestionResult) -> list[str]:
    filter_conditions = _conditions_from_calls(item.tool_calls)
    answer = item.answer_de or item.hinweis_de or ""
    lines = [
        f"### {item.question.id}",
        "",
        f"- failed: {', '.join(item.score.failed_names()) or '(overall)'}",
        f"- outcome: `{item.outcome}`",
        f"- total_count: {item.total_count}",
        f"- question: {item.question.question_de}",
        "",
        "Tool calls:",
        "",
        "```json",
        json.dumps(item.tool_calls, ensure_ascii=False, indent=2, default=str),
        "```",
        "",
        "Filter:",
        "",
        "```json",
        json.dumps(filter_conditions, ensure_ascii=False, indent=2, default=str),
        "```",
        "",
        "German answer:",
        "",
        answer or "(none)",
        "",
    ]
    if item.error:
        lines += ["Error:", "", "```", item.error, "```", ""]
    return lines


TRANSFORM_QUESTIONS_PATH = EVAL_DIR / "transform_questions.yaml"
WRITE_CRITERIA = (
    "scope_match",
    "fields_match",
    "ops_match",
    "order_correct",
    "op_type_correct",
    "outcome",
)
PROPOSED_OUTCOMES = frozenset({"proposed"})
NO_SPEC_OUTCOMES = frozenset({"clarified", "refused", "refused_or_clarified"})


@dataclass
class TransformExpect:
    outcome: str
    fields: list[str] = field(default_factory=list)
    ops: list[dict[str, Any]] = field(default_factory=list)
    order_required: bool = False
    op_type_required: str | None = None
    min_rows: int | None = None
    max_rows: int | None = None
    reason_contains: str | None = None
    warns_nonidempotent: bool = False
    empty_scope: bool = False
    scope_columns: list[str] = field(default_factory=list)
    scope_operators: list[str] = field(default_factory=list)


@dataclass
class TransformQuestion:
    id: str
    question_de: str
    expect: TransformExpect
    notes: str = ""


@dataclass
class TransformScore:
    scope_match: Mark
    fields_match: Mark
    ops_match: Mark
    order_correct: Mark
    op_type_correct: Mark
    outcome: Mark

    def overall(self) -> Mark:
        scored = [
            self.scope_match,
            self.fields_match,
            self.ops_match,
            self.order_correct,
            self.op_type_correct,
            self.outcome,
        ]
        marks = [m for m in scored if m != "n/a"]
        if not marks:
            return "n/a"
        return "pass" if all(m == "pass" for m in marks) else "fail"

    def failed_names(self) -> list[str]:
        pairs = [
            ("scope_match", self.scope_match),
            ("fields_match", self.fields_match),
            ("ops_match", self.ops_match),
            ("order_correct", self.order_correct),
            ("op_type_correct", self.op_type_correct),
            ("outcome", self.outcome),
        ]
        return [name for name, mark in pairs if mark == "fail"]


@dataclass
class TransformQuestionResult:
    question: TransformQuestion
    score: TransformScore
    inferred_outcome: str
    ask_outcome: str
    answer_de: str | None
    hinweis_de: str | None
    tool_calls: list[dict[str, Any]]
    spec: dict[str, Any] | None
    total_count: int | None
    prompt_tokens: int
    completion_tokens: int
    model: str
    snapshot_id: str | None
    error: str | None


def load_transform_questions(path: Path) -> list[TransformQuestion]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise SystemExit(f"No transform questions in {path}")
    questions: list[TransformQuestion] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise SystemExit(f"Transform entry is not a mapping: {entry!r}")
        expect_raw = entry.get("expect") or {}
        if not isinstance(expect_raw, dict):
            raise SystemExit(f"{entry.get('id')}: expect must be a mapping")
        outcome = str(expect_raw.get("outcome") or "").strip()
        if outcome not in {"proposed", "clarified", "refused", "refused_or_clarified"}:
            raise SystemExit(f"{entry.get('id')}: unknown expect.outcome {outcome!r}")
        ops_raw = expect_raw.get("ops") or []
        if ops_raw and not isinstance(ops_raw, list):
            raise SystemExit(f"{entry.get('id')}: expect.ops must be a list")
        questions.append(
            TransformQuestion(
                id=str(entry.get("id") or "").strip(),
                question_de=str(entry.get("frage") or entry.get("question_de") or "").strip(),
                notes=str(entry.get("notes") or "").strip(),
                expect=TransformExpect(
                    outcome=outcome,
                    fields=[str(item) for item in (expect_raw.get("fields") or [])],
                    ops=[item for item in ops_raw if isinstance(item, dict)],
                    order_required=bool(expect_raw.get("order_required")),
                    op_type_required=(
                        str(expect_raw["op_type_required"]).strip()
                        if expect_raw.get("op_type_required")
                        else None
                    ),
                    min_rows=expect_raw.get("min_rows"),
                    max_rows=expect_raw.get("max_rows"),
                    reason_contains=(
                        str(expect_raw["reason_contains"])
                        if expect_raw.get("reason_contains") is not None
                        else None
                    ),
                    warns_nonidempotent=bool(expect_raw.get("warns_nonidempotent")),
                    empty_scope=bool(expect_raw.get("empty_scope")),
                    scope_columns=[str(c) for c in (expect_raw.get("columns") or [])],
                    scope_operators=[str(o) for o in (expect_raw.get("operators") or [])],
                ),
            )
        )
    missing = [q.id or "(no id)" for q in questions if not q.id or not q.question_de]
    if missing:
        raise SystemExit(f"Transform questions missing id or frage: {missing}")
    return questions


def _last_proposed_spec(tool_calls: list[dict[str, Any]]) -> dict[str, Any] | None:
    for call in reversed(tool_calls):
        if str(call.get("name") or "") not in {
            "transform_vorschlagen",
            "gruppen_zuordnen",
        }:
            continue
        spec = call.get("spec")
        if isinstance(spec, dict):
            return spec
    return None


def _transform_filters(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for call in tool_calls:
        if str(call.get("name") or "") not in {
            "transform_vorschlagen",
            "gruppen_zuordnen",
        }:
            continue
        args = call.get("arguments") or {}
        if not isinstance(args, dict):
            continue
        filters = args.get("filters") or {}
        if isinstance(filters, dict):
            conditions = filters.get("conditions") or []
            if isinstance(conditions, list):
                found.extend(c for c in conditions if isinstance(c, dict))
        scope = args.get("scope") if isinstance(args.get("scope"), dict) else None
        if scope:
            qf = scope.get("query_filter") or {}
            if isinstance(qf, dict):
                conditions = qf.get("conditions") or []
                if isinstance(conditions, list):
                    found.extend(c for c in conditions if isinstance(c, dict))
    return found


def _norm_op(item: dict[str, Any]) -> tuple[str, str, str]:
    op = str(item.get("type") or item.get("op") or "")
    search = str(item.get("search") or "")
    replace = str(item.get("replace") or "")
    if op == "replace_literal" and replace == "":
        op = "remove_literal"
    return op, search, replace


def _inferred_write_outcome(spec: dict[str, Any] | None) -> str:
    return "proposed" if spec is not None else "clarified"


def score_transform_question(
    question: TransformQuestion,
    *,
    spec: dict[str, Any] | None,
    tool_calls: list[dict[str, Any]],
    total_count: int | None,
    answer_de: str | None,
    hinweis_de: str | None,
) -> TransformScore:
    expect = question.expect
    wants_spec = expect.outcome in PROPOSED_OUTCOMES
    forbids_spec = expect.outcome in NO_SPEC_OUTCOMES

    if forbids_spec and spec is not None:
        return TransformScore(
            scope_match="fail",
            fields_match="fail",
            ops_match="fail",
            order_correct="fail",
            op_type_correct="fail",
            outcome="fail",
        )

    outcome_ok: Mark = "fail"
    if wants_spec:
        outcome_ok = "pass" if spec is not None else "fail"
    elif expect.outcome == "refused_or_clarified":
        outcome_ok = "pass" if spec is None else "fail"
    elif expect.outcome == "refused":
        outcome_ok = "pass" if spec is None else "fail"
    elif expect.outcome == "clarified":
        outcome_ok = "pass" if spec is None else "fail"

    prose = f"{answer_de or ''}\n{hinweis_de or ''}"
    if expect.reason_contains and expect.reason_contains not in prose:
        outcome_ok = "fail"
    if expect.warns_nonidempotent:
        warnings = []
        if spec:
            warnings.extend(str(w) for w in (spec.get("idempotency_warnings") or []))
        for call in tool_calls:
            warnings.extend(str(w) for w in (call.get("warnings") or []))
        blob = prose + "\n" + "\n".join(warnings)
        if "nicht idempotent" not in blob.casefold() and "nicht-idempotent" not in blob.casefold():
            outcome_ok = "fail"

    fields_mark: Mark = "n/a"
    ops_mark: Mark = "n/a"
    order_mark: Mark = "n/a"
    type_mark: Mark = "n/a"
    scope_mark: Mark = "n/a"

    if wants_spec and spec is not None:
        actual_fields = [str(f) for f in (spec.get("fields") or [])]
        if expect.fields:
            fields_mark = "pass" if set(expect.fields) == set(actual_fields) else "fail"
        actual_ops = spec.get("operations") or []
        if not isinstance(actual_ops, list):
            actual_ops = []
        actual_norm = [_norm_op(op) if isinstance(op, dict) else ("", "", "") for op in actual_ops]
        if expect.ops:
            expected_norm = [_norm_op(op) for op in expect.ops]
            if expect.order_required:
                ops_mark = "pass" if actual_norm == expected_norm else "fail"
                order_mark = ops_mark
            else:
                ops_mark = "pass" if sorted(actual_norm) == sorted(expected_norm) else "fail"
        elif expect.order_required:
            order_mark = "pass"
        if expect.op_type_required:
            types = {item[0] for item in actual_norm}
            type_mark = "pass" if types == {expect.op_type_required} else "fail"

        if expect.min_rows is not None or expect.max_rows is not None:
            if total_count is None:
                scope_mark = "fail"
            else:
                scope_mark = "pass"
                if expect.min_rows is not None and total_count < expect.min_rows:
                    scope_mark = "fail"
                if expect.max_rows is not None and total_count > expect.max_rows:
                    scope_mark = "fail"
        if expect.scope_columns or expect.scope_operators:
            conds = _transform_filters(tool_calls)
            cols = {_canonical_column(str(c.get("column"))) for c in conds if c.get("column")}
            ops = {str(c.get("operator")) for c in conds if c.get("operator")}
            col_ok = (
                not expect.scope_columns
                or {_canonical_column(c) for c in expect.scope_columns} <= cols
            )
            op_ok = not expect.scope_operators or set(expect.scope_operators) <= ops
            filter_ok = col_ok and op_ok
            if scope_mark == "n/a":
                scope_mark = "pass" if filter_ok else "fail"
            elif not filter_ok:
                scope_mark = "fail"
        if expect.empty_scope:
            conds = _transform_filters(tool_calls)
            qf = (spec.get("scope") or {}).get("query_filter") or {}
            spec_conds = qf.get("conditions") if isinstance(qf, dict) else None
            empty_ok = (not conds) and (spec_conds == [] or spec_conds is None)
            if scope_mark == "n/a":
                scope_mark = "pass" if empty_ok else "fail"
            elif not empty_ok:
                scope_mark = "fail"

    return TransformScore(
        scope_match=scope_mark,
        fields_match=fields_mark,
        ops_match=ops_mark,
        order_correct=order_mark,
        op_type_correct=type_mark,
        outcome=outcome_ok,
    )


def run_transform_question(
    session,
    question: TransformQuestion,
    *,
    mock: bool,
) -> TransformQuestionResult:
    context: Any = nullcontext()
    if mock:
        client = _ScriptedClient(
            [
                LLMResponse(
                    text=(
                        json.dumps({"answer": "Ich kann das nicht so ausdrücken."}, ensure_ascii=False)
                        if settings.assistant_provider == "openai_compatible"
                        else None
                    ),
                    tool_calls=[],
                    model="mock",
                )
                if question.expect.outcome in NO_SPEC_OUTCOMES
                else LLMResponse(
                    text=None,
                    tool_calls=[
                        ToolCall(
                            name="transform_vorschlagen",
                            arguments={
                                "filters": {"conditions": []},
                                "fields": question.expect.fields
                                or ["Prosema-Artikelname"],
                                "operations": [
                                    {
                                        "op": item.get("type") or "replace_word",
                                        "search": item.get("search") or "a",
                                        **(
                                            {"replace": item.get("replace") or "b"}
                                            if (item.get("type") or "replace_word")
                                            in {"replace_word", "replace_literal"}
                                            else {}
                                        ),
                                    }
                                    for item in (question.expect.ops or [{"type": "replace_word", "search": "a", "replace": "b"}])
                                ],
                            },
                        )
                    ],
                    model="mock",
                )
            ]
            + (
                []
                if question.expect.outcome in NO_SPEC_OUTCOMES
                else [
                    LLMResponse(
                        text=(
                            json.dumps({"answer": "Vorgabe steht bereit."}, ensure_ascii=False)
                            if settings.assistant_provider == "openai_compatible"
                            else "Vorgabe steht bereit."
                        ),
                        model="mock",
                    )
                ]
            )
        )
        if settings.assistant_provider == "openai_compatible" and question.expect.outcome in PROPOSED_OUTCOMES:
            first = client._responses[0]
            args = first.tool_calls[0].arguments if first.tool_calls else {}
            client._responses[0] = LLMResponse(
                text=json.dumps({"tool": "transform_vorschlagen", "args": args}, ensure_ascii=False),
                model="mock",
            )
        context = patch("app.assistant.service.get_client", return_value=client)
    with context:
        result = ask(session, EVAL_USER, question.question_de, write_mode=True)
    audit = session.get(AssistantQuery, result.audit_id)
    tool_calls = list(audit.tool_calls) if audit is not None else []
    spec = _last_proposed_spec(tool_calls)
    score = score_transform_question(
        question,
        spec=spec,
        tool_calls=tool_calls,
        total_count=result.total_count,
        answer_de=result.answer_de,
        hinweis_de=result.hinweis_de,
    )
    return TransformQuestionResult(
        question=question,
        score=score,
        inferred_outcome=_inferred_write_outcome(spec),
        ask_outcome=result.outcome,
        answer_de=result.answer_de,
        hinweis_de=result.hinweis_de,
        tool_calls=tool_calls,
        spec=spec,
        total_count=result.total_count,
        prompt_tokens=int(audit.prompt_tokens or 0) if audit is not None else 0,
        completion_tokens=int(audit.completion_tokens or 0) if audit is not None else 0,
        model=str(audit.model or "") if audit is not None else "",
        snapshot_id=str(audit.snapshot_id) if audit is not None and audit.snapshot_id else None,
        error=str(audit.error) if audit is not None and audit.error else None,
    )


def render_transform_report(
    results: list[TransformQuestionResult],
    *,
    provider: str,
    model: str,
    snapshot_id: str | None,
    mock: bool,
    timestamp: str,
) -> str:
    tokens_in = sum(item.prompt_tokens for item in results)
    tokens_out = sum(item.completion_tokens for item in results)
    lines = [
        f"# Write-mode eval {timestamp}",
        "",
        f"- provider: `{provider}`",
        f"- model: `{model or '(unknown)'}`",
        f"- snapshot_id: `{snapshot_id or '(none)'}`",
        f"- mock: `{mock}`",
        f"- prompt_tokens: {tokens_in}",
        f"- completion_tokens: {tokens_out}",
        f"- total_tokens: {tokens_in + tokens_out}",
        "",
        "| id | outcome | scope | fields | ops | order | op_type | overall |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in results:
        s = item.score
        lines.append(
            f"| {item.question.id} | {s.outcome} | {s.scope_match} | {s.fields_match} | "
            f"{s.ops_match} | {s.order_correct} | {s.op_type_correct} | {s.overall()} |"
        )
        lines.append("")
        lines.append(f"- inferred: `{item.inferred_outcome}` ask=`{item.ask_outcome}`")
        lines.append(f"- frage: {item.question.question_de.strip()}")
        if item.answer_de:
            lines.append(f"- answer: {item.answer_de}")
        if item.tool_calls and item.score.overall() != "pass":
            lines.append("")
            lines.append("Tool calls:")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(item.tool_calls, ensure_ascii=False, indent=2, default=str))
            lines.append("```")
        if item.spec:
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(item.spec, ensure_ascii=False, indent=2, default=str))
            lines.append("```")
        if s.overall() == "fail":
            lines.append(f"- failed: {', '.join(s.failed_names())}")
        lines.append("")
    full_pass = sum(1 for item in results if item.score.overall() == "pass")
    lines += ["## Totals", "", f"Fully passed: **{full_pass} / {len(results)}**", ""]
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score assistant tool-calling against a fixed article snapshot."
    )
    parser.add_argument(
        "--provider",
        choices=("azure", "openai_compatible"),
        help="Override ASSISTANT_PROVIDER for this run.",
    )
    parser.add_argument(
        "--model",
        help=(
            "openai_compatible: model name sent in the request. "
            "azure: deployment name (also sets AZURE_OPENAI_DEPLOYMENT)."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Run only the first N questions (after --id filtering).",
    )
    parser.add_argument(
        "--id",
        dest="question_id",
        help="Run a single question by slug.",
    )
    parser.add_argument(
        "--questions",
        type=Path,
        default=None,
        help="Question YAML (default: questions.yaml, or transform_questions.yaml with --set write).",
    )
    parser.add_argument(
        "--set",
        dest="eval_set",
        choices=("read", "write"),
        default="read",
        help="read: questions.yaml (default). write: transform_questions.yaml with write_mode.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Scripted client: no model HTTP, still runs tools against the snapshot.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    write_mode = args.eval_set == "write"
    questions_path = args.questions or (
        TRANSFORM_QUESTIONS_PATH if write_mode else QUESTIONS_PATH
    )
    apply_runtime_settings(provider=args.provider, model=args.model)
    provider = settings.assistant_provider
    model = eval_model_label(
        provider,
        assistant_model=settings.assistant_model,
        azure_deployment=settings.azure_openai_deployment,
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    snapshot_id: str | None = None

    session = SessionLocal()
    try:
        snapshot = resolve_current_snapshot(session)
        snapshot_id = str(snapshot.id) if snapshot is not None else None
        if snapshot is None:
            print(
                "No complete article snapshot for this tenant; "
                "every question will score as unavailable.",
                file=sys.stderr,
            )
        if write_mode:
            questions = load_transform_questions(questions_path)
            if args.question_id:
                questions = [q for q in questions if q.id == args.question_id]
                if not questions:
                    raise SystemExit(f"No question with id {args.question_id!r}")
            if args.limit is not None:
                if args.limit < 1:
                    raise SystemExit("--limit must be >= 1")
                questions = questions[: args.limit]
            print(
                f"Eval write {len(questions)} question(s)  provider={provider}  "
                f"model={model or '(from server)'}  snapshot={snapshot_id or '(none)'}"
                f"{'  [mock]' if args.mock else ''}",
                file=sys.stderr,
            )
            results: list[TransformQuestionResult] = []
            for question in questions:
                print(f"  {question.id} …", file=sys.stderr, flush=True)
                results.append(run_transform_question(session, question, mock=args.mock))
            report = render_transform_report(
                results,
                provider=provider,
                model=model,
                snapshot_id=snapshot_id,
                mock=args.mock,
                timestamp=timestamp,
            )
            failed = any(item.score.overall() == "fail" for item in results)
        else:
            questions_read = load_questions(questions_path)
            if args.question_id:
                questions_read = [q for q in questions_read if q.id == args.question_id]
                if not questions_read:
                    raise SystemExit(f"No question with id {args.question_id!r}")
            if args.limit is not None:
                if args.limit < 1:
                    raise SystemExit("--limit must be >= 1")
                questions_read = questions_read[: args.limit]
            print(
                f"Eval {len(questions_read)} question(s)  provider={provider}  "
                f"model={model or '(from server)'}  snapshot={snapshot_id or '(none)'}"
                f"{'  [mock]' if args.mock else ''}",
                file=sys.stderr,
            )
            read_results: list[QuestionResult] = []
            for question in questions_read:
                print(f"  {question.id} …", file=sys.stderr, flush=True)
                read_results.append(run_question(session, question, mock=args.mock))
            report = render_report(
                read_results,
                provider=provider,
                model=model,
                snapshot_id=snapshot_id,
                mock=args.mock,
                timestamp=timestamp,
            )
            failed = any(item.score.overall() == "fail" for item in read_results)
    finally:
        session.close()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{timestamp}.md"
    out_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"Wrote {out_path}", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
