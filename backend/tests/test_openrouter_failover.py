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

    client = FailoverAgentClient(primary=primary, fallback=fallback, sleep_fn=AsyncMock())
    result = asyncio.run(client.analyze(_sample_page()))

    assert result.overall.summary == expected.overall.summary
    assert primary.analyze.await_count == 1
    assert fallback.analyze.await_count == 1
    assert fallback.analyze.await_args_list[0].args[0] is not None


def test_failover_does_not_retry_primary_after_fallback_real_failure():
    primary = MagicMock()
    primary.analyze = AsyncMock(
        side_effect=AgentApiError("Сервис анализа временно недоступен. Попробуйте позже.")
    )
    fallback = MagicMock()
    fallback.analyze = AsyncMock(
        side_effect=AgentApiError(
            "Сейчас слишком много запросов к сервису анализа. "
            "Подождите 1–2 минуты и попробуйте снова."
        )
    )

    client = FailoverAgentClient(primary=primary, fallback=fallback, sleep_fn=AsyncMock())
    with pytest.raises(AgentApiError, match="слишком много запросов"):
        asyncio.run(client.analyze(_sample_page()))

    assert primary.analyze.await_count == 1
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


def test_failover_chain_tries_providers_in_order():
    expected = build_mock_llm_result()
    first = MagicMock()
    first.analyze = AsyncMock(
        side_effect=AgentApiError("Сервис анализа временно недоступен. Попробуйте позже.")
    )
    second = MagicMock()
    second.analyze = AsyncMock(
        side_effect=AgentApiError(
            "Сейчас слишком много запросов к сервису анализа. "
            "Подождите 1–2 минуты и попробуйте снова."
        )
    )
    third = MagicMock()
    third.analyze = AsyncMock(return_value=expected)

    client = FailoverAgentClient(
        providers=[("a", first), ("b", second), ("c", third)]
    )
    result = asyncio.run(client.analyze(_sample_page()))
    assert result.overall.summary == expected.overall.summary
    assert first.analyze.await_count == 1
    assert second.analyze.await_count == 1
    assert third.analyze.await_count == 1


def test_build_agent_client_gemini_rotates_two_models_without_other_keys():
    settings = Settings(
        _env_file=None,
        agent_impl="gemini",
        gemini_api_key="gemini-test-key",
        gemini_model="gemini-3.6-flash",
        gemini_model_fallback="gemini-2.5-flash",
        openrouter_api_key="",
        groq_api_key="",
    )
    client = build_agent_client(settings)
    assert isinstance(client, FailoverAgentClient)
    assert len(client._providers) == 2
    assert client._providers[0][0] == "gemini:gemini-3.6-flash"
    assert client._providers[1][0] == "gemini:gemini-2.5-flash"


def test_build_agent_client_gemini_chain_includes_openrouter_and_groq():
    settings = Settings(
        _env_file=None,
        agent_impl="gemini",
        gemini_api_key="gemini-test-key",
        gemini_model="gemini-3.6-flash",
        gemini_model_fallback="gemini-2.5-flash",
        openrouter_api_key="openrouter-test-key",
        groq_api_key="groq-test-key",
    )
    client = build_agent_client(settings)
    assert isinstance(client, FailoverAgentClient)
    names = [name for name, _ in client._providers]
    assert names[0].startswith("gemini:")
    assert names[1].startswith("gemini:")
    assert names[2].startswith("openrouter:")
    assert names[3].startswith("groq:")


def test_build_agent_client_groq_only():
    from app.agent.groq_client import GroqAgentClient

    settings = Settings(
        _env_file=None,
        agent_impl="groq",
        groq_api_key="groq-test-key",
    )
    client = build_agent_client(settings)
    assert isinstance(client, FailoverAgentClient)
    assert len(client._providers) == 1
    assert client._providers[0][0].startswith("groq:")
    assert isinstance(client._providers[0][1], GroqAgentClient)


def test_build_agent_client_wraps_gemini_with_failover_when_openrouter_key_set():
    settings = Settings(
        _env_file=None,
        agent_impl="gemini",
        gemini_api_key="gemini-test-key",
        openrouter_api_key="openrouter-test-key",
    )
    client = build_agent_client(settings)
    assert isinstance(client, FailoverAgentClient)


def test_build_agent_client_openrouter_only():
    settings = Settings(
        _env_file=None,
        agent_impl="openrouter",
        openrouter_api_key="openrouter-test-key",
    )
    client = build_agent_client(settings)
    assert isinstance(client, FailoverAgentClient)
    assert len(client._providers) == 1
    assert isinstance(client._providers[0][1], OpenRouterAgentClient)


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


def test_failover_retries_429_on_same_provider_then_succeeds():
    expected = build_mock_llm_result()
    primary = MagicMock()
    primary.analyze = AsyncMock(
        side_effect=[
            AgentApiError("rate", status_code=429, api_status="RESOURCE_EXHAUSTED"),
            expected,
        ]
    )
    fallback = MagicMock()
    fallback.analyze = AsyncMock(return_value=build_mock_llm_result())
    sleep_fn = AsyncMock()

    client = FailoverAgentClient(
        providers=[("gemini:primary", primary), ("openrouter:fb", fallback)],
        sleep_fn=sleep_fn,
    )
    result = asyncio.run(client.analyze(_sample_page()))

    assert result.overall.summary == expected.overall.summary
    assert primary.analyze.await_count == 2
    fallback.analyze.assert_not_awaited()
    sleep_fn.assert_awaited_once()
    stats = client.last_stats
    assert stats is not None
    assert stats.success_provider == "gemini:primary"
    assert stats.retry_count == 1
    assert stats.fallback_used is False
    assert stats.had_429 is True
    assert stats.had_503 is False


def test_failover_goes_to_next_provider_only_after_429_retries_exhausted():
    expected = build_mock_llm_result()
    primary = MagicMock()
    primary.analyze = AsyncMock(
        side_effect=AgentApiError("busy", status_code=503, api_status="UNAVAILABLE")
    )
    fallback = MagicMock()
    fallback.analyze = AsyncMock(return_value=expected)
    sleep_fn = AsyncMock()

    client = FailoverAgentClient(
        providers=[("gemini:primary", primary), ("groq:fb", fallback)],
        sleep_fn=sleep_fn,
        max_attempts=3,
    )
    result = asyncio.run(client.analyze(_sample_page()))

    assert result.overall.summary == expected.overall.summary
    assert primary.analyze.await_count == 3
    assert fallback.analyze.await_count == 1
    assert sleep_fn.await_count == 2
    stats = client.last_stats
    assert stats is not None
    assert stats.success_provider == "groq:fb"
    assert stats.retry_count == 2
    assert stats.fallback_used is True
    assert stats.had_503 is True
    assert stats.providers_tried == ["gemini:primary", "groq:fb"]


def test_failover_does_not_start_fallback_until_primary_finished():
    order: list[str] = []

    async def primary_analyze(page):
        order.append("primary-start")
        raise AgentApiError("busy", status_code=503, api_status="UNAVAILABLE")

    async def fallback_analyze(page):
        order.append("fallback-start")
        return build_mock_llm_result()

    primary = MagicMock()
    primary.analyze = AsyncMock(side_effect=primary_analyze)
    fallback = MagicMock()
    fallback.analyze = AsyncMock(side_effect=fallback_analyze)

    client = FailoverAgentClient(
        providers=[("a", primary), ("b", fallback)],
        sleep_fn=AsyncMock(),
        max_attempts=2,
    )
    asyncio.run(client.analyze(_sample_page()))
    assert order == ["primary-start", "primary-start", "fallback-start"]


def test_retry_delay_is_exponential_and_capped():
    from app.agent.failover_client import retry_delay_s

    assert retry_delay_s(1, base_delay_s=2.0, max_delay_s=8.0) == 2.0
    assert retry_delay_s(2, base_delay_s=2.0, max_delay_s=8.0) == 4.0
    assert retry_delay_s(3, base_delay_s=2.0, max_delay_s=8.0) == 8.0
    assert retry_delay_s(4, base_delay_s=2.0, max_delay_s=8.0) == 8.0
