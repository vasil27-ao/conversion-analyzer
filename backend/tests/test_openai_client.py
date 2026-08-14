"""Тесты OpenAIAgentClient без реальной сети."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from pydantic import HttpUrl

from app.agent.errors import AgentApiError, AgentConfigError, AgentInvalidResponseError
from app.agent.mock_client import build_mock_llm_result
from app.agent.openai_client import OpenAIAgentClient
from app.agent.schemas import LlmAgentResult
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
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
        headers={"Content-Type": "application/json"},
    )


def test_openai_missing_api_key_raises():
    with pytest.raises(AgentConfigError, match="OPENAI_API_KEY"):
        OpenAIAgentClient(api_key="  ")


def test_openai_analyze_parses_json_content():
    expected = build_mock_llm_result()
    http_client = MagicMock()
    http_client.post = AsyncMock(
        return_value=_http_response(
            200,
            {"choices": [{"message": {"content": expected.model_dump_json()}}]},
        )
    )
    client = OpenAIAgentClient(
        api_key="test-key",
        model="gpt-4o",
        http_client=http_client,
    )
    result = asyncio.run(client.analyze(_sample_page()))
    assert isinstance(result, LlmAgentResult)
    assert len(result.blocks) == 6
    assert result.overall.summary == expected.overall.summary
    kwargs = http_client.post.await_args.kwargs
    assert kwargs["json"]["model"] == "gpt-4o"
    assert kwargs["json"]["response_format"] == {"type": "json_object"}


def test_openai_api_error_maps_to_user_message():
    http_client = MagicMock()
    http_client.post = AsyncMock(
        return_value=_http_response(
            429,
            {"error": {"message": "quota", "code": "rate_limit_exceeded"}},
        )
    )
    client = OpenAIAgentClient(api_key="test-key", http_client=http_client)
    with pytest.raises(AgentApiError, match="слишком много запросов") as exc_info:
        asyncio.run(client.analyze(_sample_page()))
    assert exc_info.value.status_code == 429


def test_openai_invalid_json_raises():
    http_client = MagicMock()
    http_client.post = AsyncMock(
        return_value=_http_response(
            200,
            {"choices": [{"message": {"content": "not-json{{{"}}]},
        )
    )
    client = OpenAIAgentClient(api_key="test-key", http_client=http_client)
    with pytest.raises(AgentInvalidResponseError, match="JSON"):
        asyncio.run(client.analyze(_sample_page()))
