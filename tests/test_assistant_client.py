"""Synchronous LLM clients: retry, auth, logging guards."""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.assistant.client import (
    AssistantUnavailable,
    AzureOpenAIClient,
    OpenAICompatibleClient,
    _debug_prompt_allowed,
    get_client,
    strictify_json_schema,
)
from app.config import Settings


def _settings(**overrides) -> Settings:
    data = {
        "database_url": "postgresql+psycopg://localhost/x",
        "session_secret": "s",
        "entra_tenant_id": "t",
        "entra_client_id": "c",
        "entra_client_secret": "cs",
        "entra_redirect_uri": "http://localhost/callback",
        "entra_group_users_id": "u",
        "entra_group_admins_id": "a",
        "weclapp_tenant": "prosema",
        "token_encryption_key": "k",
        "assistant_provider": "openai_compatible",
        "assistant_base_url": "http://127.0.0.1:1234/v1",
        "assistant_model": "local-model",
        "assistant_timeout_seconds": 20,
        "azure_openai_endpoint": "https://example.openai.azure.com",
        "azure_openai_deployment": "gpt-test",
        "azure_openai_api_version": "2024-10-21",
        "environment": "local",
    }
    data.update(overrides)
    return Settings.model_construct(**data)


def _http_response(status: int, payload: dict | None = None, headers: dict | None = None):
    return httpx.Response(
        status,
        json=payload or {},
        headers=headers or {},
        request=httpx.Request("POST", "http://example.test"),
    )


def test_get_client_selects_provider():
    azure = get_client(_settings(assistant_provider="azure"))
    local = get_client(_settings(assistant_provider="openai_compatible"))
    assert isinstance(azure, AzureOpenAIClient)
    assert isinstance(local, OpenAICompatibleClient)


def test_openai_compatible_parses_tool_calls():
    client = OpenAICompatibleClient(_settings())
    payload = {
        "model": "local-model",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "function": {
                                "name": "artikel_zaehlen",
                                "arguments": '{"filters": {"conditions": []}}',
                            }
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 4},
    }
    with patch.object(client._http, "post", return_value=_http_response(200, payload)) as post:
        result = client.complete("sys", [{"role": "user", "content": "hi"}], [])
    assert result.tool_calls[0].name == "artikel_zaehlen"
    assert result.prompt_tokens == 11
    assert result.raw_finish_reason == "tool_calls"
    posted = post.call_args
    assert "Authorization" not in posted.kwargs["headers"]
    assert posted.kwargs["json"]["model"] == "local-model"
    assert posted.kwargs["json"]["enable_thinking"] is False
    assert posted.kwargs["json"]["chat_template_kwargs"] == {
        "enable_thinking": False
    }


def test_retries_once_on_429_honouring_retry_after():
    client = OpenAICompatibleClient(_settings())
    ok = {
        "model": "local-model",
        "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    responses = [
        _http_response(429, {}, {"Retry-After": "0"}),
        _http_response(200, ok),
    ]
    with (
        patch.object(client._http, "post", side_effect=responses),
        patch("app.assistant.client.time.sleep") as sleep,
    ):
        result = client.complete("sys", [], [])
    assert result.text == "ok"
    sleep.assert_called_once_with(0.0)


def test_does_not_retry_other_4xx():
    client = OpenAICompatibleClient(_settings())
    with (
        patch.object(client._http, "post", return_value=_http_response(400, {})),
        pytest.raises(AssistantUnavailable, match="abgelehnt"),
    ):
        client.complete("sys", [], [])


def test_timeout_raises_german():
    client = OpenAICompatibleClient(_settings())
    with (
        patch.object(client._http, "post", side_effect=httpx.TimeoutException("t")),
        pytest.raises(AssistantUnavailable, match="fehlgeschlagen"),
    ):
        client.complete("sys", [], [])


def test_azure_uses_bearer_and_pinned_api_version():
    client = AzureOpenAIClient(_settings(assistant_provider="azure"))
    client._token = "tok"
    client._token_expires_on = 10**12
    payload = {
        "choices": [{"finish_reason": "stop", "message": {"content": "hi"}}],
        "usage": {},
    }
    with patch.object(client._http, "post", return_value=_http_response(200, payload)) as post:
        client.complete("sys", [], [])
    url = post.call_args.args[0]
    assert "api-version=2024-10-21" in url
    assert "/openai/deployments/gpt-test/chat/completions" in url
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer tok"
    assert "model" not in post.call_args.kwargs["json"]
    assert "enable_thinking" not in post.call_args.kwargs["json"]


def test_local_client_connect_timeout_is_short():
    client = OpenAICompatibleClient(_settings(assistant_timeout_seconds=120))
    assert client._http.timeout.connect == 5.0
    assert client._http.timeout.read == 120.0


def test_azure_auth_failure_german():
    client = AzureOpenAIClient(_settings(assistant_provider="azure"))
    cred = MagicMock()
    cred.get_token.side_effect = RuntimeError("denied")
    client._credential = cred
    with pytest.raises(AssistantUnavailable, match="Azure-Anmeldung"):
        client.complete("sys", [], [])


def test_prompt_debug_disabled_in_production():
    assert _debug_prompt_allowed("production") is False
    assert _debug_prompt_allowed("local") is True


def test_strictify_nested_model_has_no_ref_or_omitted_optional():
    from app.assistant.schemas import ArtikelSuchenArgs

    raw = ArtikelSuchenArgs.model_json_schema()
    assert "$ref" in json.dumps(raw)
    originally_required = set(raw.get("required") or [])
    strict = strictify_json_schema(raw)
    blob = json.dumps(strict)
    assert "$ref" not in blob
    assert "$defs" not in strict

    def assert_objects(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                assert_objects(item)
            return
        if not isinstance(node, dict):
            return
        properties = node.get("properties")
        if isinstance(properties, dict):
            assert node.get("additionalProperties") is False
            assert set(node.get("required") or []) == set(properties)
        for value in node.values():
            assert_objects(value)

    assert_objects(strict)
    assert set(strict["required"]) == set(strict["properties"])
    for name in strict["properties"]:
        if name not in originally_required:
            assert _is_nullable_for_test(strict["properties"][name])
    assert '"default"' not in blob

    def first_named(node: object, name: str) -> dict | None:
        if isinstance(node, list):
            for item in node:
                found = first_named(item, name)
                if found is not None:
                    return found
            return None
        if not isinstance(node, dict):
            return None
        properties = node.get("properties")
        if isinstance(properties, dict) and name in properties:
            spec = properties[name]
            return spec if isinstance(spec, dict) else None
        for value in node.values():
            found = first_named(value, name)
            if found is not None:
                return found
        return None

    value_schema = first_named(strict, "value")
    assert value_schema is not None
    options = value_schema.get("anyOf") or [value_schema]
    assert options
    for option in options:
        assert isinstance(option, dict)
        assert "type" in option or "anyOf" in option or "enum" in option


def _is_nullable_for_test(schema: dict) -> bool:
    if schema.get("type") == "null":
        return True
    types = schema.get("type")
    if isinstance(types, list) and "null" in types:
        return True
    for option in schema.get("anyOf") or []:
        if isinstance(option, dict) and option.get("type") == "null":
            return True
    return False


def _sample_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "artikel_zaehlen",
                "description": "count",
                "parameters": {
                    "type": "object",
                    "properties": {"group_by": {"type": "string"}},
                },
            },
        }
    ]


def test_strict_schema_400_retries_once_without_strict(caplog):
    client = OpenAICompatibleClient(_settings(assistant_strict_schema=True))
    ok = {
        "model": "local-model",
        "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    responses = [
        _http_response(
            400,
            {"error": {"message": "Invalid schema for strict: additionalProperties must be false"}},
        ),
        _http_response(200, ok),
    ]
    tools = _sample_tools()
    with (
        caplog.at_level(logging.WARNING, logger="app.assistant.client"),
        patch.object(client._http, "post", side_effect=responses) as post,
    ):
        result = client.complete("sys", [], tools)
    assert result.text == "ok"
    assert post.call_count == 2
    first = post.call_args_list[0].kwargs["json"]["tools"][0]["function"]
    second = post.call_args_list[1].kwargs["json"]["tools"][0]["function"]
    assert first.get("strict") is True
    assert second.get("strict") is not True
    assert "retrying without strict" in caplog.text
    assert "additionalProperties must be false" in caplog.text


def test_400_other_message_does_not_retry():
    client = OpenAICompatibleClient(_settings(assistant_strict_schema=True))
    with (
        patch.object(
            client._http,
            "post",
            return_value=_http_response(400, {"error": {"message": "invalid api key"}}),
        ) as post,
        pytest.raises(AssistantUnavailable, match="abgelehnt"),
    ):
        client.complete("sys", [], _sample_tools())
    assert post.call_count == 1


def test_tool_choice_none_sent_in_body():
    client = OpenAICompatibleClient(_settings())
    ok = {
        "model": "local-model",
        "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    with patch.object(client._http, "post", return_value=_http_response(200, ok)) as post:
        client.complete("sys", [], _sample_tools(), tool_choice="none")
    assert post.call_args.kwargs["json"]["tool_choice"] == "none"
    assert post.call_args.kwargs["json"]["tools"]
