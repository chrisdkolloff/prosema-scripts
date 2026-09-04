"""Transform specification.

Operations are applied in list order to the running value. That order is
semantic, not cosmetic: "Winkel-Abschlussprofil" → "Winkelprofil" must run
before "Abschlussprofil" → "Winkelprofil", or the result is "Winkel-Winkelprofil".

replace_word is the correct default for standalone German nouns. replace_literal
is for fragments and hyphenated compounds. The measured --verbinder result is
the worked example: replace_word correctly skipped Winkelverbinder and
LED-Direktverbinder.

Known gap, not solved here: stripping a trailing ", Artikelnummer: …" cannot be
expressed in this vocabulary. That needs a future bounded operation, not a
regex escape hatch.

The snapshot (via scope) chooses WHICH articles. It never supplies values.
Preview and apply read live weclapp for old/new.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.article_write_fields import Writability, write_field

MSG_AMP = "Suchbegriffe mit & werden nicht unterstützt"
MSG_EMPTY_SEARCH = "Suchbegriff darf nicht leer sein"
MSG_STAR_SEARCH = (
    "«*» ist kein Platzhalter. Die Operationen ersetzen nur Text, der im "
    "Feld wirklich vorkommt; sie setzen kein Feld auf einen neuen Wert."
)
MSG_NOOP = "Suche und Ersatz sind identisch"
MSG_NOT_PASS_1 = "Feld «{field}» darf in diesem Schritt nicht geändert werden"
MSG_SCOPE = "Bitte entweder Artikelnummern oder einen Filter angeben, nicht beides und nicht keines."
MSG_NO_OPS = "Mindestens eine Operation ist erforderlich"
MSG_NO_FIELDS = "Mindestens ein Feld ist erforderlich"
MSG_NON_IDEM = (
    "Die Operation «{search}» → «{replace}» ist nicht idempotent. "
    "Sie kann nicht sicher erneut angewandt werden. Zeilen mit unbekanntem "
    "Ausgang müssen manuell abgeglichen werden, nicht erneut ausgeführt."
)
MSG_RERUN_NON_IDEM = (
    "Die Vorgabe enthält eine nicht-idempotente Operation. Offene Zeilen "
    "dürfen nicht erneut angewandt werden. Bitte unbekannte Ausgänge "
    "manuell abgleichen."
)
MSG_DESTRUCTIVE_INSERT = (
    "Die Operation «{search}» → «{replace}» kann nicht vorgeschlagen werden. "
    "{count_phrase} bereits «{replace}» und {verb} verdorben, "
    "zum Beispiel {examples}."
)


class TransformSpecError(ValueError):
    def __init__(self, message_de: str, message_en: str) -> None:
        super().__init__(f"{message_de} ({message_en})")
        self.message_de = message_de
        self.message_en = message_en


def _refuse(message_de: str, message_en: str) -> None:
    raise TransformSpecError(message_de, message_en)


class ReplaceLiteral(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["replace_literal"]
    search: str
    replace: str


class RemoveLiteral(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["remove_literal"]
    search: str


class ReplaceWord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["replace_word"]
    search: str
    replace: str


class RemoveWord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["remove_word"]
    search: str


TransformOperation = Annotated[
    ReplaceLiteral | RemoveLiteral | ReplaceWord | RemoveWord,
    Field(discriminator="op"),
]

# Same boundaries as app.transform.engine (must not import engine from here).
_WORD_GUARD = r"A-Za-zÄÖÜäöüß-"


def _word_still_matches(search: str, replace: str) -> bool:
    """True if replace_word(search→replace) applied to replace still changes it."""
    pattern = re.compile(
        rf"(?<![{_WORD_GUARD}]){re.escape(search)}(?![{_WORD_GUARD}])",
        re.IGNORECASE,
    )
    return pattern.sub(lambda _m: replace, replace) != replace


def non_idempotent_warning(operation: TransformOperation) -> str | None:
    replace = getattr(operation, "replace", None)
    if replace is None:
        return None
    if operation.op == "replace_literal" and operation.search in replace:
        return MSG_NON_IDEM.format(search=operation.search, replace=replace)
    if operation.op == "replace_word" and _word_still_matches(operation.search, replace):
        return MSG_NON_IDEM.format(search=operation.search, replace=replace)
    return None


def _clip_example(text: str) -> str:
    clipped = text if len(text) <= 80 else text[:77] + "…"
    return f"«{clipped}»"


def destructive_insertion_refusal(
    operation: TransformOperation, field_values: list[str]
) -> str | None:
    """Refuse insert/expand ops whose destination form already exists in the data.

    Narrower than the non-idempotency warning: search must be a proper substring
    of replace, and replace must already occur in a target-field value.
    """
    replace = getattr(operation, "replace", None)
    if replace is None or operation.search == replace:
        return None
    if operation.search not in replace:
        return None
    hits = [text for text in field_values if text and replace in text]
    if not hits:
        return None
    unique: list[str] = []
    seen: set[str] = set()
    for text in hits:
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
        if len(unique) == 2:
            break
    count = len(hits)
    if count == 1:
        count_phrase, verb = "1 bestehender Wert enthält", "würde"
    else:
        count_phrase, verb = f"{count} bestehende Werte enthalten", "würden"
    return MSG_DESTRUCTIVE_INSERT.format(
        search=operation.search,
        replace=replace,
        count_phrase=count_phrase,
        verb=verb,
        examples=" und ".join(_clip_example(item) for item in unique),
    )


def _validate_search(search: str, replace: str | None) -> None:
    if search == "":
        _refuse(MSG_EMPTY_SEARCH, "search must not be empty")
    if search == "*":
        _refuse(
            MSG_STAR_SEARCH,
            "'*' is not a whole-field wildcard",
        )
    if "&" in search:
        _refuse(
            MSG_AMP,
            "search terms containing '&' cannot cross HTML entity boundaries",
        )
    if replace is not None and search == replace:
        _refuse(MSG_NOOP, "search equals replace; that is a no-op")
    # replace == "" is allowed: replace_literal then deletes search, same as
    # remove_literal. Only search-equals-replace is the no-op.


class TransformScope(BaseModel):
    """Exactly one of article_numbers or query_filter.

    Scope is resolved against a named snapshot to pick candidates. The snapshot
    never supplies field values — live GETs do.
    """

    model_config = ConfigDict(extra="forbid")

    article_numbers: list[str] | None = None
    query_filter: dict[str, Any] | None = None

    @model_validator(mode="after")
    def exactly_one(self) -> Self:
        has_numbers = self.article_numbers is not None
        has_filter = self.query_filter is not None
        if has_numbers == has_filter:
            _refuse(MSG_SCOPE, "scope must be article_numbers xor query_filter")
        if has_numbers and len(self.article_numbers or []) == 0:
            _refuse(MSG_SCOPE, "article_numbers must not be empty")
        if self.query_filter is not None:
            from app.filter_clauses import parse_query_filter

            parse_query_filter(self.query_filter)
        return self


class TransformSpec(BaseModel):
    """Ordered field transforms over a snapshot-chosen candidate set."""

    model_config = ConfigDict(extra="forbid")

    scope: TransformScope
    fields: list[str]
    operations: list[TransformOperation] = Field(min_length=1)
    idempotency_warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_spec(self) -> Self:
        if not self.fields:
            _refuse(MSG_NO_FIELDS, "at least one field is required")
        if not self.operations:
            _refuse(MSG_NO_OPS, "at least one operation is required")
        seen: set[str] = set()
        for key in self.fields:
            if key in seen:
                continue
            seen.add(key)
            try:
                spec = write_field(key)
            except KeyError:
                _refuse(
                    MSG_NOT_PASS_1.format(field=key),
                    f"unknown field {key!r}",
                )
            if spec.writability is not Writability.PASS_1:
                _refuse(
                    MSG_NOT_PASS_1.format(field=key),
                    f"{key!r} is not PASS_1 ({spec.writability.value})",
                )
        warnings: list[str] = []
        for operation in self.operations:
            replace = getattr(operation, "replace", None)
            _validate_search(operation.search, replace)
            note = non_idempotent_warning(operation)
            if note is not None:
                warnings.append(note)
        object.__setattr__(self, "idempotency_warnings", warnings)
        return self


def spec_has_non_idempotent_ops(spec: TransformSpec) -> bool:
    return bool(spec.idempotency_warnings)
