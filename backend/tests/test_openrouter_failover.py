"""Тесты OpenRouterAgentClient и FailoverAgentClient без реальной сети."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from pydantic import HttpUrl

from app.agent.errors import AgentApiError, AgentConfigError, AgentInvalidResponseError
from app.agent.failover_client import FailoverAgentClient
from app.agent.mock_client import build_mock_llm_result
from app.agent.openrouter_client import OpenRouterAgentClient
from app.agent.schemas import LlmAgentResult
from app.config import Settings
from app.dependencies import build_agent_client
from app.page_collector.models import LayoutSnapshot, PageData, ViewportSize


def _sample_page() -> PageData:
    return PageData(
        url=HttpUrl("https://example.com/landing"),
        html="<html><body><h1>Demo</h1></body></html>",
        visible_text="Demo landing",
        layout_desktop=LayoutSnapshot(viewport=ViewportSize(width=1280, height=800)),
        layout_mobile=LayoutSnapshot(viewport=ViewportSize(width=390, height=844)),
    )


def _http_response(status_code: int, payload: dict | str) -> httpx.Response:
    if isinstance(payload, dict):
        content = json.dumps(payload)
    else:
        content = payload
    return httpx.Response(
        status_code=status_code,
        content=content.encode("utf-8"),
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
        headers={"Content-Type": "application/json"},
    )


def test_openrouter_missing_api_key_raises():
    with pytest.raises(AgentConfigError, match="OPENROUTER_API_KEY"):
        OpenRouterAgentClient(api_key="  ")


def test_openrouter_analyze_parses_json_content():
    expected = build_mock_llm_result()
    http_client = MagicMock()
    http_client.post = AsyncMock(
        return_value=_http_response(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": expected.model_dump_json(),
                        }
                    }
                ]
            },
        )
    )
    client = OpenRouterAgentClient(
        api_key="test-key",
        model="qwen/qwen3-32b:free",
        http_client=http_client,
    )
    result = asyncio.run(client.analyze(_sample_page()))
    assert isinstance(result, LlmAgentResult)
    assert len(result.blocks) == 6
    assert result.overall.summary == expected.overall.summary


def test_openrouter_api_error_maps_to_user_message():
    http_client = MagicMock()
    http_client.post = AsyncMock(
        return_value=_http_response(
            503,
            {"error": {"message": "busy", "code": "unavailable"}},
        )
    )
    client = OpenRouterAgentClient(api_key="test-key", http_client=http_client)
    with pytest.raises(AgentApiError, match="временно недоступен"):
        asyncio.run(client.analyze(_sample_page()))


def test_failover_switches_to_fallback_on_transient_primary_error():
    expected = build_mock_llm_result()
    primary = MagicMock()
    primary.analyze = AsyncMock(
        side_effect=AgentApiError("Сервис анализа временно недоступен. Попробуйте позже.")
    )
    fallback = MagicMock()
    fallback.analyze = AsyncMock(return_value=expected)

    client = FailoverAgentClient(primary=primary, fallback=fallback)
    result = asyncio.run(client.analyze(_sample_page()))

    assert result.overall.summary == expected.overall.summary
    assert primary.analyze.await_count == 1
    assert fallback.analyze.await_count == 1


def test_failover_retries_primary_after_fallback_transient_error():
    expected = build_mock_llm_result()
    primary = MagicMock()
    primary.analyze = AsyncMock(
        side_effect=[
            AgentApiError("Сервис анализа временно недоступен. Попробуйте позже."),
            expected,
        ]
    )
    fallback = MagicMock()
    fallback.analyze = AsyncMock(
        side_effect=AgentApiError(
            "Сейчас слишком много запросов к сервису анализа. "
            "Подождите 1–2 минуты и попробуйте снова."
        )
    )

    client = FailoverAgentClient(primary=primary, fallback=fallback)
    result = asyncio.run(client.analyze(_sample_page()))

    assert isinstance(result, LlmAgentResult)
    assert primary.analyze.await_count == 2
    assert fallback.analyze.await_count == 1


def test_failover_does_not_switch_on_config_error():
    primary = MagicMock()
    primary.analyze = AsyncMock(side_effect=AgentConfigError("bad config"))
    fallback = MagicMock()
    fallback.analyze = AsyncMock(return_value=build_mock_llm_result())

    client = FailoverAgentClient(primary=primary, fallback=fallback)
    with pytest.raises(AgentConfigError):
        asyncio.run(client.analyze(_sample_page()))
    fallback.analyze.assert_not_awaited()


def test_build_agent_client_wraps_gemini_with_failover_when_openrouter_key_set():
    settings = Settings(
        agent_impl="gemini",
        gemini_api_key="gemini-test-key",
        openrouter_api_key="openrouter-test-key",
    )
    client = build_agent_client(settings)
    assert isinstance(client, FailoverAgentClient)


def test_build_agent_client_openrouter_only():
    settings = Settings(
        agent_impl="openrouter",
        openrouter_api_key="openrouter-test-key",
    )
    client = build_agent_client(settings)
    assert isinstance(client, OpenRouterAgentClient)


def test_openrouter_invalid_json_raises():
    http_client = MagicMock()
    http_client.post = AsyncMock(
        return_value=_http_response(
            200,
            {"choices": [{"message": {"content": "not-json{{{"}}]},
        )
    )
    client = OpenRouterAgentClient(api_key="test-key", http_client=http_client)
    with pytest.raises(AgentInvalidResponseError, match="JSON"):
        asyncio.run(client.analyze(_sample_page()))
