"""Orchestration loop for the article assistant.

The only database write in this module is the assistant_queries audit row.
Tool calls stay read-only.
"""

from __future__ import annotations

import json
import logging
import re
import time
import traceback
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ValidationError
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.assistant.client import AssistantUnavailable, LLMClient, LLMResponse, ToolCall, get_client
from app.assistant.prompts import (
    ANSWER_NOW_HINT,
    FINAL_TURN_HINT,
    PARSE_RETRY_HINT,
    build_system_prompt,
    compatible_protocol_suffix,
)
from app.assistant.schemas import (
    ArtikelDetailsArgs,
    ArtikelSuchenArgs,
    ArtikelZaehlenArgs,
    DatenstandArgs,
    EinheitenAuflistenArgs,
    GruppenAuflistenArgs,
    QueryFilter,
)
from app.assistant.tools import (
    ToolResult,
    _filter_clauses,
    artikel_details,
    artikel_suchen,
    artikel_zaehlen,
    datenstand,
    einheiten_auflisten,
    gruppen_auflisten,
    resolve_current_snapshot,
)
from app.assistant.verification import _TOKEN_RE, verify_numbers
from app.auth import SessionUser
from app.config import settings
from app.models import ArticleSnapshot, ArticleSnapshotRow, AssistantQuery
from app.snapshots import format_snapshot_timestamp

logger = logging.getLogger(__name__)

Outcome = Literal[
    "answered",
    "answered_unverified",
    "no_result",
    "no_answer",
    "refused",
    "invalid_input",
    "error",
    "unavailable",
]

MSG_DISABLED = f"{settings.assistant_name} ist derzeit nicht aktiv."
MSG_NO_SNAPSHOT = (
    "Es liegt noch kein abgeschlossener Artikel-Snapshot vor. "
    "Bitte zuerst eine Artikelübersicht abfragen."
)
MSG_TURN_BUDGET = (
    "Die Frage konnte nicht innerhalb der zulässigen Schritte beantwortet werden."
)
MSG_NO_ANSWER = (
    "Ich konnte keine Zusammenfassung erzeugen. "
    "Stattdessen wird das Rohresultat gezeigt."
)
MSG_DUPLICATE_CALL = (
    "Diese Abfrage wurde bereits ausgeführt. "
    "Bitte das Ergebnis jetzt zusammenfassen."
)
MSG_GENERIC_ERROR = "Die Anfrage ist fehlgeschlagen. Bitte später erneut versuchen."
MSG_UNVERIFIED = (
    "Ich konnte die Antwort nicht anhand der Daten prüfen. "
    "Es wird nur die Tabelle gezeigt."
)
MSG_EMPTY_QUESTION = "Bitte eine Frage eingeben."
MSG_PARSE_ERROR = "Die Modellantwort war kein gültiges JSON."
MSG_EMPTY_ANSWER = "Das Modell hat keine Antwort geliefert."

MAX_SELECTION_ROWS = 5000
_SELECTION_OUTCOMES = frozenset(
    {"answered", "answered_unverified", "no_answer", "no_result"}
)
_SELECTION_TOOLS = frozenset({"artikel_suchen", "artikel_zaehlen"})

_FENCE_RE = re.compile(r"^```(?:json)?\s*", re.IGNORECASE)


@dataclass
class AssistantResult:
    answer_de: str | None
    rows: list[dict[str, Any]]
    columns: list[str]
    total_count: int | None
    truncated: bool
    datenstand: datetime | None
    datenstand_hinweis_de: str
    outcome: Outcome
    hinweis_de: str | None
    audit_id: uuid.UUID
    applied_article_numbers: list[str] | None = None
    selection_truncated: bool = False


@dataclass
class _ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Any


TOOL_SPECS: tuple[_ToolSpec, ...] = (
    _ToolSpec(
        "artikel_suchen",
        "Filter, sort, and return article rows from the current snapshot.",
        ArtikelSuchenArgs,
        artikel_suchen,
    ),
    _ToolSpec(
        "artikel_zaehlen",
        "Count articles, optionally grouped by a catalogue column. Use this for how-many questions.",
        ArtikelZaehlenArgs,
        artikel_zaehlen,
    ),
    _ToolSpec(
        "artikel_details",
        "Return one article by its article_number. Do not query live weclapp.",
        ArtikelDetailsArgs,
        artikel_details,
    ),
    _ToolSpec(
        "gruppen_auflisten",
        "List registry Hauptgruppen and Untergruppen with article counts from the article number.",
        GruppenAuflistenArgs,
        gruppen_auflisten,
    ),
    _ToolSpec(
        "einheiten_auflisten",
        "List distinct Einheit values in the snapshot with usage counts.",
        EinheitenAuflistenArgs,
        einheiten_auflisten,
    ),
    _ToolSpec(
        "datenstand",
        "Return snapshot id, pull-start timestamp, row_count, and the latest snapshot job.",
        DatenstandArgs,
        datenstand,
    ),
)
TOOLS_BY_NAME = {spec.name: spec for spec in TOOL_SPECS}


def _tool_schemas() -> list[dict[str, Any]]:
    schemas: list[dict[str, Any]] = []
    for spec in TOOL_SPECS:
        parameters = spec.args_model.model_json_schema()
        parameters.setdefault("type", "object")
        parameters.setdefault("additionalProperties", False)
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": parameters,
                },
            }
        )
    return schemas


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = _FENCE_RE.sub("", stripped, count=1)
        if stripped.endswith("```"):
            stripped = stripped[: stripped.rfind("```")]
    return stripped.strip()


def _parse_json_object(raw: str) -> Any:
    """First complete JSON value; trailing content is ignored."""
    try:
        payload, end = json.JSONDecoder().raw_decode(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(str(exc)) from exc
    trailing = raw[end:].strip()
    if trailing:
        logger.debug(
            "assistant discarded trailing JSON content length=%s",
            len(trailing),
        )
    return payload


def _parse_compatible_text(text: str | None) -> tuple[str | None, list[ToolCall]]:
    if not text or not text.strip():
        raise ValueError("empty response")
    raw = _strip_fences(text)
    payload = _parse_json_object(raw)
    if not isinstance(payload, dict):
        raise ValueError("JSON root must be an object")  # noqa: TRY004
    if "tool" in payload:
        name = str(payload.get("tool") or "")
        args = payload.get("args") or {}
        if not name:
            raise ValueError("missing tool name")
        if not isinstance(args, dict):
            raise ValueError("args must be an object")
        return None, [ToolCall(name=name, arguments=args)]
    if "answer" in payload:
        answer = payload.get("answer")
        if not isinstance(answer, str):
            raise ValueError("answer must be a string")
        return answer, []
    raise ValueError("object must contain tool or answer")


def _next_step(
    client: LLMClient,
    *,
    provider: str,
    system: str,
    messages: list[dict[str, Any]],
    schemas: list[dict[str, Any]],
    tool_choice: str | None = None,
) -> LLMResponse:
    """One model turn. Native tools on Azure; JSON protocol otherwise."""
    if provider == "openai_compatible":
        prompt = system + compatible_protocol_suffix(schemas)
        return client.complete(prompt, messages, [])
    if tool_choice:
        return client.complete(system, messages, schemas, tool_choice=tool_choice)
    return client.complete(system, messages, schemas)


def _validation_message(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        msg = str(err.get("msg") or "")
        msg = msg.removeprefix("Value error, ")
        if msg:
            parts.append(msg)
    return " ".join(parts) or "Ungültige Tool-Argumente."


def _serialize_tool_result(result: ToolResult) -> dict[str, Any]:
    return {
        "rows": result.rows,
        "total_count": result.total_count,
        "truncated": result.truncated,
        "datenstand": result.datenstand.isoformat() if result.datenstand else None,
        "datenstand_hinweis_de": result.datenstand_hinweis_de,
        "hinweis_de": result.hinweis_de,
    }


def _canonical_tool_key(name: str, args: BaseModel) -> tuple[str, str]:
    """Identity for duplicate detection: tool name plus sorted validated args."""
    return (
        name,
        json.dumps(args.model_dump(mode="json"), sort_keys=True, ensure_ascii=False),
    )


def _with_duplicate_note(payload: dict[str, Any]) -> dict[str, Any]:
    current = str(payload.get("hinweis_de") or "").strip()
    hinweis = f"{current} {MSG_DUPLICATE_CALL}".strip() if current else MSG_DUPLICATE_CALL
    return {**payload, "hinweis_de": hinweis}


def _collect_numbers(*objs: Any) -> set[str]:
    found: set[str] = set()

    def walk(value: Any) -> None:
        if value is None or isinstance(value, bool):
            return
        if isinstance(value, Decimal):
            found.add(format(value, "f"))
            return
        if isinstance(value, int):
            found.add(str(value))
            return
        if isinstance(value, float):
            found.add(format(value, "g"))
            return
        if isinstance(value, datetime):
            found.update(_TOKEN_RE.findall(value.isoformat()))
            found.update(_TOKEN_RE.findall(format_snapshot_timestamp(value)))
            return
        if isinstance(value, str):
            found.update(_TOKEN_RE.findall(value))
            return
        if isinstance(value, Mapping):
            for item in value.values():
                walk(item)
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                walk(item)

    for obj in objs:
        walk(obj)
    return found


def _columns_for(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    return list(rows[0].keys())


def _tool_messages(
    provider: str, calls: list[ToolCall]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if provider == "openai_compatible":
        if len(calls) == 1:
            content = json.dumps(
                {"tool": calls[0].name, "args": calls[0].arguments},
                ensure_ascii=False,
            )
        else:
            content = json.dumps(
                [{"tool": call.name, "args": call.arguments} for call in calls],
                ensure_ascii=False,
            )
        assistant = {"role": "assistant", "content": content}
        placeholders = [{"role": "user"} for _ in calls]
        return assistant, placeholders
    tool_calls = []
    placeholders = []
    for call in calls:
        call_id = f"call_{uuid.uuid4().hex[:12]}"
        tool_calls.append(
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                },
            }
        )
        placeholders.append({"role": "tool", "tool_call_id": call_id})
    assistant = {"role": "assistant", "content": None, "tool_calls": tool_calls}
    return assistant, placeholders


def _tool_payload_message(
    provider: str,
    placeholder: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    content = json.dumps(payload, ensure_ascii=False, default=str)
    if provider == "openai_compatible":
        return {"role": "user", "content": f"{content}\n{ANSWER_NOW_HINT}"}
    return {
        "role": "tool",
        "tool_call_id": placeholder["tool_call_id"],
        "content": content,
    }


def _pin_selection(
    session: Session,
    snapshot: ArticleSnapshot,
    query_filter: QueryFilter,
) -> tuple[list[str] | None, bool]:
    """Article numbers matching the validated filter, for the grid.

    The 50 rows the model saw are a projection for summarising, not the answer.
    This second query selects only article_number, with no model-facing limit,
    capped at MAX_SELECTION_ROWS + 1 so truncation is detectable.
    """
    clauses = _filter_clauses(session, snapshot, query_filter)
    stmt = (
        select(ArticleSnapshotRow.article_number)
        .where(and_(*clauses))
        .order_by(ArticleSnapshotRow.position)
        .limit(MAX_SELECTION_ROWS + 1)
    )
    fetched = list(session.scalars(stmt))
    if len(fetched) > MAX_SELECTION_ROWS:
        return None, True
    return [number for number in fetched if number], False


def ask(session: Session, user: SessionUser, question_de: str) -> AssistantResult:
    started = time.perf_counter()
    audit_id = uuid.uuid4()
    snapshot: ArticleSnapshot | None = None
    recorded_calls: list[dict[str, Any]] = []
    prompt_tokens = 0
    completion_tokens = 0
    model_name = ""
    turns = 0
    stand_hinweis = ""
    last_selection_filter: QueryFilter | None = None

    def finish(
        *,
        outcome: Outcome,
        answer_de: str | None = None,
        rows: list[dict[str, Any]] | None = None,
        columns: list[str] | None = None,
        total_count: int | None = None,
        truncated: bool = False,
        datenstand: datetime | None = None,
        datenstand_hinweis_de: str = "",
        hinweis_de: str | None = None,
        error: str | None = None,
    ) -> AssistantResult:
        applied_numbers: list[str] | None = None
        selection_truncated = False
        applied_filter: dict[str, Any] | None = None
        if (
            outcome in _SELECTION_OUTCOMES
            and last_selection_filter is not None
            and snapshot is not None
        ):
            applied_filter = last_selection_filter.model_dump(mode="json")
            try:
                applied_numbers, selection_truncated = _pin_selection(
                    session, snapshot, last_selection_filter
                )
            except (ValidationError, ValueError):
                logger.exception(
                    "assistant selection pin failed audit_id=%s", audit_id
                )
        result = AssistantResult(
            answer_de=answer_de,
            rows=rows or [],
            columns=columns or [],
            total_count=total_count,
            truncated=truncated,
            datenstand=datenstand,
            datenstand_hinweis_de=datenstand_hinweis_de,
            outcome=outcome,
            hinweis_de=hinweis_de,
            audit_id=audit_id,
            applied_article_numbers=applied_numbers,
            selection_truncated=selection_truncated,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "assistant ask question_len=%s turns=%s tools=%s latency_ms=%s "
            "prompt_tokens=%s completion_tokens=%s outcome=%s",
            len(question_de or ""),
            turns,
            [call.get("name") for call in recorded_calls],
            latency_ms,
            prompt_tokens,
            completion_tokens,
            outcome,
        )
        try:
            session.add(
                AssistantQuery(
                    id=audit_id,
                    user_oid=str(user.get("oid") or ""),
                    user_name=str(user.get("name") or ""),
                    question_de=question_de or "",
                    snapshot_id=snapshot.id if snapshot is not None else None,
                    tool_calls=list(recorded_calls),
                    answer_de=result.answer_de,
                    outcome=result.outcome,
                    total_count=result.total_count,
                    turns=turns,
                    prompt_tokens=prompt_tokens or None,
                    completion_tokens=completion_tokens or None,
                    model=model_name or None,
                    latency_ms=latency_ms or None,
                    error=error,
                    applied_article_numbers=applied_numbers,
                    applied_filter=applied_filter,
                    selection_truncated=selection_truncated,
                )
            )
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("assistant audit write failed audit_id=%s", audit_id)
        return result

    if not settings.assistant_enabled:
        return finish(outcome="unavailable", hinweis_de=MSG_DISABLED, error=MSG_DISABLED)

    snapshot = resolve_current_snapshot(session)
    if snapshot is None:
        return finish(outcome="unavailable", hinweis_de=MSG_NO_SNAPSHOT, error=MSG_NO_SNAPSHOT)

    stand_hinweis = (
        f"Datenstand: Beginn des Abzugs vom {format_snapshot_timestamp(snapshot.created_at)}. "
        "Der Zeitpunkt ist der Start der Abfrage, nicht deren Abschluss."
    )

    if not (question_de or "").strip():
        return finish(
            outcome="invalid_input",
            hinweis_de=MSG_EMPTY_QUESTION,
            datenstand=snapshot.created_at,
            datenstand_hinweis_de=stand_hinweis,
            error=MSG_EMPTY_QUESTION,
        )

    schemas = _tool_schemas()
    system = build_system_prompt(session)
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": question_de.strip()},
    ]
    provider = settings.assistant_provider
    client = get_client()
    last_rows: list[dict[str, Any]] = []
    last_columns: list[str] = []
    last_total: int | None = None
    last_truncated = False
    last_datenstand = snapshot.created_at
    last_stand_hinweis = stand_hinweis
    last_empty_rows = False
    had_row_returning = False
    executed_payloads: dict[tuple[str, str], dict[str, Any]] = {}
    call_counts: dict[tuple[str, str], int] = {}
    allowed: set[str] = _collect_numbers(snapshot.created_at, question_de)

    def finish_without_answer() -> AssistantResult:
        # The table alone is more useful to the user than an error page, and this
        # mirrors the existing answered_unverified behaviour where the prose is
        # suppressed but the data is still shown.
        if had_row_returning:
            return finish(
                outcome="no_answer",
                answer_de=None,
                hinweis_de=MSG_NO_ANSWER,
                rows=last_rows,
                columns=last_columns,
                total_count=last_total,
                truncated=last_truncated,
                datenstand=last_datenstand,
                datenstand_hinweis_de=last_stand_hinweis,
            )
        return finish(
            outcome="error",
            hinweis_de=MSG_TURN_BUDGET,
            datenstand=last_datenstand,
            datenstand_hinweis_de=last_stand_hinweis,
            rows=last_rows,
            columns=last_columns,
            total_count=last_total,
            truncated=last_truncated,
            error=MSG_TURN_BUDGET,
        )

    max_turns = max(1, int(settings.assistant_max_tool_turns))
    try:
        for turn_index in range(max_turns):
            last_turn = turn_index == max_turns - 1
            parse_hint: str | None = None
            step: LLMResponse | None = None
            for attempt in range(2):
                turn_messages = list(messages)
                if last_turn:
                    turn_messages.append({"role": "user", "content": FINAL_TURN_HINT})
                if parse_hint:
                    turn_messages.append({"role": "user", "content": parse_hint})
                step = _next_step(
                    client,
                    provider=provider,
                    system=system,
                    messages=turn_messages,
                    schemas=schemas,
                    tool_choice="none" if last_turn else None,
                )
                turns += 1
                prompt_tokens += step.prompt_tokens
                completion_tokens += step.completion_tokens
                if step.model:
                    model_name = step.model
                if provider != "openai_compatible":
                    break
                try:
                    answer, calls = _parse_compatible_text(step.text)
                    step = LLMResponse(
                        text=answer,
                        tool_calls=calls,
                        prompt_tokens=step.prompt_tokens,
                        completion_tokens=step.completion_tokens,
                        model=step.model,
                        raw_finish_reason=step.raw_finish_reason,
                    )
                    break
                except ValueError as exc:
                    parse_hint = PARSE_RETRY_HINT.format(error=exc)
                    if attempt == 0:
                        continue
                    return finish(
                        outcome="error",
                        hinweis_de=MSG_PARSE_ERROR,
                        datenstand=last_datenstand,
                        datenstand_hinweis_de=last_stand_hinweis,
                        rows=last_rows,
                        columns=last_columns,
                        total_count=last_total,
                        truncated=last_truncated,
                        error=str(exc),
                    )
            assert step is not None

            if step.tool_calls:
                assistant_msg, tool_msgs = _tool_messages(provider, step.tool_calls)
                messages.append(assistant_msg)
                for call, tool_msg in zip(step.tool_calls, tool_msgs, strict=True):
                    spec = TOOLS_BY_NAME.get(call.name)
                    recorded: dict[str, Any] = {
                        "name": call.name,
                        "arguments": call.arguments,
                    }
                    if spec is None:
                        payload = {"error": f"Unbekanntes Tool «{call.name}»."}
                        recorded["error"] = payload["error"]
                        recorded_calls.append(recorded)
                        messages.append(_tool_payload_message(provider, tool_msg, payload))
                        continue
                    try:
                        args = spec.args_model.model_validate(call.arguments or {})
                    except ValidationError as exc:
                        message = _validation_message(exc)
                        recorded["error"] = message
                        recorded_calls.append(recorded)
                        messages.append(
                            _tool_payload_message(provider, tool_msg, {"error": message})
                        )
                        continue
                    key = _canonical_tool_key(spec.name, args)
                    if key in executed_payloads:
                        call_counts[key] += 1
                        count = call_counts[key]
                        logger.info(
                            "assistant duplicate tool call name=%s repeat_count=%s",
                            spec.name,
                            count,
                        )
                        cached = executed_payloads[key]
                        recorded["total_count"] = cached.get("total_count")
                        recorded_calls.append(recorded)
                        if count >= 3:
                            return finish_without_answer()
                        messages.append(
                            _tool_payload_message(
                                provider, tool_msg, _with_duplicate_note(cached)
                            )
                        )
                        continue
                    try:
                        result: ToolResult = spec.handler(session, args)
                    except ValidationError as exc:
                        message = _validation_message(exc)
                        recorded["error"] = message
                        recorded_calls.append(recorded)
                        messages.append(
                            _tool_payload_message(provider, tool_msg, {"error": message})
                        )
                        continue
                    except ValueError as exc:
                        message = str(exc)
                        recorded["error"] = message
                        recorded_calls.append(recorded)
                        messages.append(
                            _tool_payload_message(provider, tool_msg, {"error": message})
                        )
                        continue
                    payload = _serialize_tool_result(result)
                    recorded["total_count"] = result.total_count
                    recorded_calls.append(recorded)
                    executed_payloads[key] = payload
                    call_counts[key] = 1
                    had_row_returning = True
                    allowed.update(_collect_numbers(call.arguments, payload, result.total_count))
                    last_rows = result.rows
                    last_columns = _columns_for(result.rows)
                    last_total = result.total_count
                    last_truncated = result.truncated
                    last_empty_rows = not result.rows
                    if spec.name in _SELECTION_TOOLS:
                        last_selection_filter = args.filters
                    if result.datenstand is not None:
                        last_datenstand = result.datenstand
                    if result.datenstand_hinweis_de:
                        last_stand_hinweis = result.datenstand_hinweis_de
                    messages.append(_tool_payload_message(provider, tool_msg, payload))
                continue

            text = (step.text or "").strip()
            if not text:
                return finish(
                    outcome="error",
                    hinweis_de=MSG_EMPTY_ANSWER,
                    datenstand=last_datenstand,
                    datenstand_hinweis_de=last_stand_hinweis,
                    rows=last_rows,
                    columns=last_columns,
                    total_count=last_total,
                    truncated=last_truncated,
                    error=MSG_EMPTY_ANSWER,
                )

            ok, unaccounted = verify_numbers(text, allowed)
            if not ok:
                logger.warning(
                    "assistant answer unverified audit_id=%s unaccounted=%s answer=%s",
                    audit_id,
                    sorted(unaccounted),
                    text,
                )
                return finish(
                    outcome="answered_unverified",
                    answer_de=None,
                    hinweis_de=MSG_UNVERIFIED,
                    rows=last_rows,
                    columns=last_columns,
                    total_count=last_total,
                    truncated=last_truncated,
                    datenstand=last_datenstand,
                    datenstand_hinweis_de=last_stand_hinweis,
                )
            outcome: Outcome = "no_result" if last_empty_rows else "answered"
            return finish(
                outcome=outcome,
                answer_de=text,
                rows=last_rows,
                columns=last_columns,
                total_count=last_total,
                truncated=last_truncated,
                datenstand=last_datenstand,
                datenstand_hinweis_de=last_stand_hinweis,
            )

        return finish_without_answer()
    except AssistantUnavailable as exc:
        message = str(exc) or MSG_GENERIC_ERROR
        return finish(
            outcome="unavailable",
            hinweis_de=message,
            datenstand=snapshot.created_at if snapshot is not None else None,
            datenstand_hinweis_de=stand_hinweis,
            error=message,
        )
    except Exception as exc:
        logger.exception("assistant ask failed")
        return finish(
            outcome="error",
            hinweis_de=MSG_GENERIC_ERROR,
            datenstand=snapshot.created_at if snapshot is not None else None,
            datenstand_hinweis_de=stand_hinweis,
            error=traceback.format_exc() or str(exc),
        )
