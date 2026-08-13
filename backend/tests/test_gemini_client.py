"""Тесты GeminiAgentClient без реального сетевого вызова."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from google.genai import errors as genai_errors
from pydantic import HttpUrl

from app.agent.errors import (
    AgentApiError,
    AgentConfigError,
    AgentInvalidResponseError,
)
from app.agent.gemini_client import (
    DEFAULT_SYSTEM_PROMPT_PATH,
    GeminiAgentClient,
    build_gemini_response_json_schema,
    build_page_payload,
    load_system_prompt,
)
from app.agent.mock_client import build_mock_llm_result
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


def _client_with_mock_response(response: object) -> GeminiAgentClient:
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=response)
    return GeminiAgentClient(
        api_key="test-key-not-real",
        model="gemini-3.6-flash",
        client=mock_client,
    )


def test_load_system_prompt_reads_file():
    text = load_system_prompt(DEFAULT_SYSTEM_PROMPT_PATH)
    assert "агент-аналитик" in text.lower() or "чек-лист" in text.lower()
    assert "LlmAgentResult" in text


def test_missing_api_key_raises_config_error():
    with pytest.raises(AgentConfigError, match="GEMINI_API_KEY"):
        GeminiAgentClient(api_key="   ")


def test_analyze_returns_llm_agent_result_without_numeric_score():
    expected = build_mock_llm_result()
    client = _client_with_mock_response(SimpleNamespace(parsed=expected, text=None))

    result = asyncio.run(client.analyze(_sample_page()))

    assert isinstance(result, LlmAgentResult)
    assert result.overall.summary == expected.overall.summary
    # Numeric overall score живёт в AgentResult, не в LlmOverall.
    assert not hasattr(result.overall, "score")
    assert "score" not in result.model_dump()["overall"]


def test_analyze_parses_json_text_when_parsed_missing():
    expected = build_mock_llm_result()
    client = _client_with_mock_response(
        SimpleNamespace(parsed=None, text=expected.model_dump_json())
    )

    result = asyncio.run(client.analyze(_sample_page()))
    assert isinstance(result, LlmAgentResult)
    assert len(result.blocks) == 6
    assert sum(len(b.criteria) for b in result.blocks) == 20


def test_analyze_invalid_json_raises():
    client = _client_with_mock_response(
        SimpleNamespace(parsed=None, text="not-json{{{")
    )
    with pytest.raises(AgentInvalidResponseError, match="JSON"):
        asyncio.run(client.analyze(_sample_page()))


def test_analyze_schema_mismatch_raises():
    client = _client_with_mock_response(
        SimpleNamespace(parsed=None, text='{"overall": {"summary": "x"}}')
    )
    with pytest.raises(AgentInvalidResponseError, match="LlmAgentResult"):
        asyncio.run(client.analyze(_sample_page()))


def test_analyze_api_error_raises_agent_api_error():
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=genai_errors.APIError(
            429,
            {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}},
        )
    )
    client = GeminiAgentClient(
        api_key="test-key-not-real",
        model="gemini-3.6-flash",
        client=mock_client,
    )
    with pytest.raises(AgentApiError, match="слишком много запросов") as exc_info:
        asyncio.run(client.analyze(_sample_page()))
    assert exc_info.value.status_code == 429


def test_build_page_payload_uses_skeleton_and_strips_scripts():
    from app.agent.common import HTML_CHAR_LIMIT, truncate_html_for_llm

    head_marker = "<!--HEAD_UNIQUE-->"
    mid_script = "<script>" + ("x" * 50_000) + "</script>"
    tail_marker = "<!--TAIL_UNIQUE_FOOTER_REVIEWS-->"
    huge_html = (
        f"<html><body>{head_marker}<h1>Offer</h1>{mid_script}"
        f"<footer>{tail_marker}</footer></body></html>"
    )
    page = PageData(
        url=HttpUrl("https://example.com/big"),
        html=huge_html,
        visible_text="text",
        layout_desktop=LayoutSnapshot(viewport=ViewportSize(width=1280, height=800)),
        layout_mobile=LayoutSnapshot(viewport=ViewportSize(width=390, height=844)),
    )
    payload = build_page_payload(page)
    assert payload["html_truncated"] is True
    assert payload["html_mode"].startswith("skeleton")
    assert len(payload["html"]) < len(huge_html)
    assert "<script" not in payload["html"].lower()
    assert "Offer" in payload["html"]
    assert len(payload["html"]) <= HTML_CHAR_LIMIT

    kept, truncated = truncate_html_for_llm("short")
    assert truncated is False
    assert kept == "short"


def test_analyze_passes_system_instruction_and_schema():
    expected = build_mock_llm_result()
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(parsed=expected, text=None)
    )
    client = GeminiAgentClient(
        api_key="test-key-not-real",
        model="gemini-3.6-flash",
        client=mock_client,
    )
    asyncio.run(client.analyze(_sample_page()))

    kwargs = mock_client.aio.models.generate_content.await_args.kwargs
    assert kwargs["model"] == "gemini-3.6-flash"
    config = kwargs["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_schema is None
    schema = config.response_json_schema
    assert isinstance(schema, dict)
    assert schema.get("title") == "LlmAgentResult" or "properties" in schema
    # integer Literal заменены на enum — иначе Gemini падает.
    dumped = json.dumps(schema)
    assert '"const": 0' not in dumped
    assert '"enum": [0, 1, 2]' in dumped or '"enum":[0,1,2]' in dumped
    assert getattr(config, "temperature", None) is None
    assert getattr(config, "top_p", None) is None
    assert getattr(config, "top_k", None) is None
    assert "чек-лист" in config.system_instruction.lower() or "критер" in config.system_instruction.lower()


def test_build_gemini_response_json_schema_avoids_integer_literals():
    schema = build_gemini_response_json_schema()
    dumped = json.dumps(schema)
    assert '"const": 0' not in dumped
    assert "N/A" in dumped
    # Schema всё ещё описывает LlmAgentResult.
    assert "overall" in schema.get("properties", {}) or "overall" in dumped