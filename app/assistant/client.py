"""Synchronous LLM HTTP clients for the article assistant."""

from __future__ import annotations

import copy
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.config import Settings
from app.config import settings as app_settings

logger = logging.getLogger(__name__)

AZURE_TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"
TOKEN_REFRESH_SKEW_SECONDS = 300
_STRICT_ERROR_MARKERS = ("strict", "additionalproperties", "schema")


class AssistantUnavailable(Exception):
    """Raised when the model endpoint cannot be reached or authenticated."""


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    raw_finish_reason: str = ""


class LLMClient(Protocol):
    def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str | None = None,
    ) -> LLMResponse: ...


def _debug_prompt_allowed(environment: str) -> bool:
    """Prompt text is never logged in production, even at DEBUG."""
    return environment != "production"


def _maybe_debug_prompt(environment: str, system: str, messages: list[dict[str, Any]]) -> None:
    if not _debug_prompt_allowed(environment):
        return
    logger.debug("assistant prompt system=%s messages=%s", system, messages)


def _parse_retry_after(response: httpx.Response) -> float:
    raw = response.headers.get("Retry-After")
    if raw is None:
        return 1.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.0


def _parse_response(payload: dict[str, Any]) -> LLMResponse:
    usage = payload.get("usage") or {}
    choices = payload.get("choices") or []
    choice = choices[0] if choices else {}
    message = choice.get("message") or {}
    finish = str(choice.get("finish_reason") or payload.get("finish_reason") or "")
    text = message.get("content")
    tool_calls: list[ToolCall] = []
    for entry in message.get("tool_calls") or []:
        function = entry.get("function") or {}
        name = str(function.get("name") or "")
        raw_args = function.get("arguments") or "{}"
        parsed: dict[str, Any]
        try:
            loaded = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            parsed = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            parsed = {}
        if name:
            tool_calls.append(ToolCall(name=name, arguments=parsed))
    return LLMResponse(
        text=text if isinstance(text, str) else None,
        tool_calls=tool_calls,
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        model=str(payload.get("model") or ""),
        raw_finish_reason=finish,
    )


def _is_nullable(schema: dict[str, Any]) -> bool:
    if schema.get("type") == "null":
        return True
    types = schema.get("type")
    if isinstance(types, list) and "null" in types:
        return True
    for key in ("anyOf", "oneOf"):
        for option in schema.get(key) or []:
            if isinstance(option, dict) and option.get("type") == "null":
                return True
    return False


def _make_nullable(schema: dict[str, Any]) -> dict[str, Any]:
    if _is_nullable(schema):
        return schema
    return {"anyOf": [schema, {"type": "null"}]}


_STRICT_UNSUPPORTED_KEYS = frozenset({"default"})
_ANY_VALUE_OPTIONS = (
    {"type": "string"},
    {"type": "number"},
    {"type": "integer"},
    {"type": "boolean"},
    {"type": "array", "items": {"type": "string"}},
    {"type": "null"},
)


def _walk_schema_nodes(node: Any):
    if isinstance(node, list):
        for item in node:
            yield from _walk_schema_nodes(item)
        return
    if not isinstance(node, dict):
        return
    yield node
    for key in ("anyOf", "oneOf", "allOf"):
        options = node.get(key)
        if isinstance(options, list):
            yield from _walk_schema_nodes(options)
    if "items" in node:
        yield from _walk_schema_nodes(node["items"])
    if "prefixItems" in node:
        yield from _walk_schema_nodes(node["prefixItems"])
    properties = node.get("properties")
    if isinstance(properties, dict):
        yield from _walk_schema_nodes(list(properties.values()))
    additional = node.get("additionalProperties")
    if isinstance(additional, dict):
        yield from _walk_schema_nodes(additional)


def _strip_unsupported_strict_keywords(node: Any) -> None:
    for schema in _walk_schema_nodes(node):
        for key in _STRICT_UNSUPPORTED_KEYS:
            schema.pop(key, None)


def _schema_declares_type(schema: dict[str, Any]) -> bool:
    return any(
        key in schema
        for key in (
            "type",
            "anyOf",
            "oneOf",
            "allOf",
            "$ref",
            "enum",
            "const",
            "properties",
            "items",
            "prefixItems",
        )
    )


def _ensure_schema_types(node: Any) -> None:
    """Pydantic `Any` becomes `{title, default}` with no type; Azure 400s on that."""
    for schema in _walk_schema_nodes(node):
        if not _schema_declares_type(schema):
            schema["anyOf"] = [copy.deepcopy(option) for option in _ANY_VALUE_OPTIONS]


def _inline_refs(node: Any, defs: dict[str, Any], seen: frozenset[str]) -> Any:
    if isinstance(node, list):
        return [_inline_refs(item, defs, seen) for item in node]
    if not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if isinstance(ref, str):
        name = ref.rsplit("/", 1)[-1]
        if name in seen:
            return {"type": "object"}
        target = defs.get(name)
        if not isinstance(target, dict):
            return {key: value for key, value in node.items() if key != "$ref"}
        merged = copy.deepcopy(target)
        for key, value in node.items():
            if key != "$ref":
                merged[key] = value
        return _inline_refs(merged, defs, seen | {name})
    return {
        key: _inline_refs(value, defs, seen)
        for key, value in node.items()
        if key not in {"$defs", "definitions"}
    }


def _enforce_strict_objects(node: Any) -> None:
    if isinstance(node, list):
        for item in node:
            _enforce_strict_objects(item)
        return
    if not isinstance(node, dict):
        return
    for key in ("anyOf", "oneOf", "allOf"):
        options = node.get(key)
        if isinstance(options, list):
            for item in options:
                _enforce_strict_objects(item)
    if "items" in node:
        _enforce_strict_objects(node["items"])
    if "prefixItems" in node:
        _enforce_strict_objects(node["prefixItems"])
    properties = node.get("properties")
    if not isinstance(properties, dict):
        return
    originally_required = set(node.get("required") or [])
    for name, spec in list(properties.items()):
        if isinstance(spec, dict):
            _enforce_strict_objects(spec)
            if name not in originally_required:
                properties[name] = _make_nullable(spec)
        elif name not in originally_required:
            properties[name] = _make_nullable({"type": "string"})
    node["required"] = list(properties.keys())
    node["additionalProperties"] = False
    node.setdefault("type", "object")


def strictify_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Make a Pydantic model_json_schema() result valid for Azure strict tools."""
    root = copy.deepcopy(schema)
    defs = root.pop("$defs", None) or root.pop("definitions", None) or {}
    inlined = _inline_refs(root, defs if isinstance(defs, dict) else {}, frozenset())
    _strip_unsupported_strict_keywords(inlined)
    _ensure_schema_types(inlined)
    _enforce_strict_objects(inlined)
    return inlined


def _tools_with_strict_schema(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for tool in tools:
        item = copy.deepcopy(tool)
        function = item.get("function")
        if isinstance(function, dict) and isinstance(function.get("parameters"), dict):
            function["parameters"] = strictify_json_schema(function["parameters"])
            function["strict"] = True
        prepared.append(item)
    return prepared


def _response_error_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        return response.text or ""
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err)
        if err:
            return str(err)
        return json.dumps(payload)
    return str(payload)


def _is_strict_schema_rejection(response: httpx.Response) -> bool:
    text = _response_error_text(response).casefold()
    return any(marker in text for marker in _STRICT_ERROR_MARKERS)


def _chat_body(
    *,
    model: str | None,
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    tool_choice: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "messages": [{"role": "system", "content": system}, *messages],
    }
    if model:
        body["model"] = model
    if tools:
        body["tools"] = tools
        body["tool_choice"] = tool_choice if tool_choice is not None else "auto"
    return body


def _http_timeout(timeout_seconds: int) -> httpx.Timeout:
    """Fail fast on a down server; keep the full budget for generation."""
    read = max(1.0, float(timeout_seconds))
    return httpx.Timeout(connect=5.0, read=read, write=read, pool=5.0)


class _SyncChatClient:
    """Shared POST/retry path so Azure and OpenAI-compatible stay equivalent."""

    def __init__(
        self,
        *,
        timeout_seconds: int,
        environment: str,
        deployment: str | None,
        model: str | None,
        strict_schema: bool,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._http = httpx.Client(timeout=_http_timeout(timeout_seconds))
        self._environment = environment
        self._deployment = deployment
        self._model = model
        self._strict_schema = strict_schema

    def close(self) -> None:
        self._http.close()

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def _url(self) -> str:
        raise NotImplementedError

    def _extra_body(self) -> dict[str, Any]:
        return {}

    def _request_model(self) -> str | None:
        return self._model

    def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str | None = None,
    ) -> LLMResponse:
        _maybe_debug_prompt(self._environment, system, messages)
        url = self._url()
        use_strict = bool(self._strict_schema and tools)
        outgoing = _tools_with_strict_schema(tools) if use_strict else tools
        body = _chat_body(
            model=self._request_model(),
            system=system,
            messages=messages,
            tools=outgoing,
            tool_choice=tool_choice,
        )
        body.update(self._extra_body())
        last_error: Exception | None = None
        started = time.perf_counter()
        omitted_strict = False
        for attempt in range(2):
            try:
                response = self._http.post(url, headers=self._headers(), json=body)
            except httpx.TimeoutException as exc:
                logger.warning(
                    "assistant complete timeout url=%s timeout_s=%s",
                    url,
                    self._timeout_seconds,
                )
                raise AssistantUnavailable(
                    "Die Sprachmodell-Anfrage ist wegen Zeitüberschreitung fehlgeschlagen."
                ) from exc
            except httpx.RequestError as exc:
                last_error = exc
                logger.warning(
                    "assistant complete request error url=%s attempt=%s err=%s",
                    url,
                    attempt,
                    exc,
                )
                if attempt == 0:
                    time.sleep(1.0)
                    continue
                raise AssistantUnavailable(
                    "Die Sprachmodell-Schnittstelle ist derzeit nicht erreichbar."
                ) from exc

            if response.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                time.sleep(_parse_retry_after(response))
                continue
            if (
                response.status_code == 400
                and use_strict
                and not omitted_strict
                and _is_strict_schema_rejection(response)
            ):
                logger.warning(
                    "assistant complete HTTP 400 looks like a strict-schema "
                    "rejection; retrying without strict: %s",
                    _response_error_text(response)[:2000],
                )
                omitted_strict = True
                body = _chat_body(
                    model=self._request_model(),
                    system=system,
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                )
                body.update(self._extra_body())
                continue
            if response.status_code >= 400:
                raise AssistantUnavailable(
                    "Die Sprachmodell-Schnittstelle hat die Anfrage abgelehnt "
                    f"(HTTP {response.status_code})."
                )
            parsed = _parse_response(response.json())
            latency_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "assistant complete model=%s deployment=%s latency_ms=%.0f "
                "prompt_tokens=%s completion_tokens=%s finish=%s",
                parsed.model or self._model,
                self._deployment,
                latency_ms,
                parsed.prompt_tokens,
                parsed.completion_tokens,
                parsed.raw_finish_reason,
            )
            return parsed

        raise AssistantUnavailable(
            "Die Sprachmodell-Schnittstelle ist derzeit nicht erreichbar."
        ) from last_error


class AzureOpenAIClient(_SyncChatClient):
    def __init__(self, config: Settings) -> None:
        super().__init__(
            timeout_seconds=config.assistant_timeout_seconds,
            environment=config.environment,
            deployment=config.azure_openai_deployment,
            model=config.assistant_model or config.azure_openai_deployment,
            strict_schema=config.assistant_strict_schema,
        )
        self._endpoint = (config.azure_openai_endpoint or "").rstrip("/")
        self._api_version = config.azure_openai_api_version
        self._credential = None
        self._token = None
        self._token_expires_on = 0.0

    def _bearer(self) -> str:
        now = time.time()
        if self._token is None or self._token_expires_on - now < TOKEN_REFRESH_SKEW_SECONDS:
            try:
                from azure.identity import DefaultAzureCredential
            except ImportError as exc:
                raise AssistantUnavailable(
                    "Die Azure-Anmeldung für das Sprachmodell ist nicht verfügbar."
                ) from exc
            if self._credential is None:
                self._credential = DefaultAzureCredential()
            try:
                token = self._credential.get_token(AZURE_TOKEN_SCOPE)
            except Exception as exc:
                raise AssistantUnavailable(
                    "Die Azure-Anmeldung für das Sprachmodell ist fehlgeschlagen."
                ) from exc
            self._token = token.token
            self._token_expires_on = float(token.expires_on)
        return self._token

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._bearer()}",
        }

    def _url(self) -> str:
        if not self._endpoint or not self._deployment:
            raise AssistantUnavailable(
                "Azure OpenAI ist nicht konfiguriert (Endpunkt oder Deployment fehlt)."
            )
        return (
            f"{self._endpoint}/openai/deployments/{self._deployment}"
            f"/chat/completions?api-version={self._api_version}"
        )

    def _request_model(self) -> str | None:
        # Azure routes by deployment; sending a model name is optional.
        return None


class OpenAICompatibleClient(_SyncChatClient):
    def __init__(self, config: Settings) -> None:
        super().__init__(
            timeout_seconds=config.assistant_timeout_seconds,
            environment=config.environment,
            deployment=None,
            model=config.assistant_model,
            strict_schema=config.assistant_strict_schema,
        )
        self._base_url = (config.assistant_base_url or "").rstrip("/")

    def _extra_body(self) -> dict[str, Any]:
        # Qwen3 and similar hybrid models otherwise spend the whole read
        # timeout on a hidden reasoning trace and return no tokens.
        return {
            "enable_thinking": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }

    def _url(self) -> str:
        if not self._base_url:
            raise AssistantUnavailable(
                "Die lokale Sprachmodell-URL ist nicht konfiguriert."
            )
        return f"{self._base_url}/chat/completions"


def get_client(config: Settings | None = None) -> LLMClient:
    cfg = config if config is not None else app_settings
    if cfg.assistant_provider == "openai_compatible":
        return OpenAICompatibleClient(cfg)
    return AzureOpenAIClient(cfg)
