"""
Реализация AgentClient через Gemini API.

Один вызов модели → сырой `LlmAgentResult`. Numeric score не считается здесь
(это делает `assemble_agent_result` на backend).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import ValidationError

from app.agent.common import (
    DEFAULT_SYSTEM_PROMPT_PATH,
    HTML_CHAR_LIMIT,
    build_analysis_user_message,
    build_page_payload,
    load_system_prompt,
    parse_llm_agent_result_from_text,
    truncate_html_for_llm,
    user_facing_agent_api_error,
)
from app.agent.errors import (
    AgentApiError,
    AgentConfigError,
    AgentInvalidResponseError,
)
from app.agent.interface import AgentClient
from app.agent.schemas import LlmAgentResult
from app.page_collector.models import PageData

logger = logging.getLogger(__name__)

# Реэкспорт для обратной совместимости импортов в тестах/скриптах.
__all__ = [
    "DEFAULT_GEMINI_MODEL",
    "DEFAULT_SYSTEM_PROMPT_PATH",
    "GeminiAgentClient",
    "HTML_CHAR_LIMIT",
    "build_gemini_response_json_schema",
    "build_page_payload",
    "load_system_prompt",
    "truncate_html_for_llm",
]

DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"


def _rewrite_score_literals(node: Any) -> Any:
    """
    Gemini SDK отклоняет integer Literal/const в response_schema
    (`Literal values must be strings`). Для score 0/1/2/N/A заменяем на
    integer enum + string enum, сохраняя ту же семантику для LlmAgentResult.
    """
    if isinstance(node, list):
        return [_rewrite_score_literals(item) for item in node]
    if not isinstance(node, dict):
        return node

    rewritten = {key: _rewrite_score_literals(value) for key, value in node.items()}
    any_of = rewritten.get("anyOf")
    if isinstance(any_of, list) and any_of:
        int_consts: list[int] = []
        str_consts: list[str] = []
        only_consts = True
        for branch in any_of:
            if not isinstance(branch, dict) or "const" not in branch:
                only_consts = False
                break
            const = branch["const"]
            if isinstance(const, bool):
                only_consts = False
                break
            if isinstance(const, int):
                int_consts.append(const)
            elif isinstance(const, str):
                str_consts.append(const)
            else:
                only_consts = False
                break
        if only_consts and int_consts and str_consts:
            rewritten["anyOf"] = [
                {"type": "integer", "enum": int_consts},
                {"type": "string", "enum": str_consts},
            ]
        elif only_consts and int_consts and not str_consts:
            rewritten.pop("anyOf", None)
            rewritten["type"] = "integer"
            rewritten["enum"] = int_consts
        elif only_consts and str_consts and not int_consts:
            rewritten.pop("anyOf", None)
            rewritten["type"] = "string"
            rewritten["enum"] = str_consts
    return rewritten


def build_gemini_response_json_schema() -> dict[str, Any]:
    """JSON Schema LlmAgentResult, совместимая с Gemini structured output."""
    schema = LlmAgentResult.model_json_schema()
    return _rewrite_score_literals(schema)


def _parse_llm_agent_result(response: Any) -> LlmAgentResult:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, LlmAgentResult):
        return parsed
    if isinstance(parsed, dict):
        try:
            return LlmAgentResult.model_validate(parsed)
        except ValidationError as exc:
            raise AgentInvalidResponseError(
                f"Ответ Gemini не соответствует LlmAgentResult: {exc}"
            ) from exc

    text = getattr(response, "text", None)
    return parse_llm_agent_result_from_text(
        str(text) if text is not None else "",
        provider_label="Gemini",
    )


class GeminiAgentClient(AgentClient):
    """Вызов Gemini с structured JSON по схеме LlmAgentResult."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_GEMINI_MODEL,
        system_prompt_path: Path | None = None,
        client: Optional[genai.Client] = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise AgentConfigError(
                "GEMINI_API_KEY не задан. Укажите ключ в backend/.env."
            )
        self._model = (model or "").strip() or DEFAULT_GEMINI_MODEL
        self._system_prompt_path = system_prompt_path or DEFAULT_SYSTEM_PROMPT_PATH
        self._client = client or genai.Client(api_key=api_key.strip())

    async def analyze(self, page_data: PageData) -> LlmAgentResult:
        user_text = build_analysis_user_message(page_data)
        system_prompt = load_system_prompt(self._system_prompt_path)

        payload_chars = len(user_text)
        logger.info(
            "Calling Gemini model=%s url=%s payload_chars=%s",
            self._model,
            page_data.url,
            payload_chars,
        )
        gemini_started = time.perf_counter()

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=user_text,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_json_schema=build_gemini_response_json_schema(),
                ),
            )
        except genai_errors.APIError as exc:
            # Не включаем тело исключения целиком — там теоретически может
            # оказаться чувствительный контекст запроса.
            code = getattr(exc, "code", None)
            status = getattr(exc, "status", None)
            logger.error("Gemini API error: code=%s status=%s", code, status)
            raise AgentApiError(user_facing_agent_api_error(code, status)) from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected Gemini client failure")
            raise AgentApiError(
                "Не удалось выполнить анализ страницы. Попробуйте ещё раз."
            ) from exc

        result = _parse_llm_agent_result(response)
        gemini_s = time.perf_counter() - gemini_started
        logger.info(
            "Gemini response parsed: blocks=%s problems=%s backlog=%s",
            len(result.blocks),
            len(result.problems),
            len(result.backlog),
        )
        logger.info(
            "Timing gemini model=%s url=%s gemini_s=%.3f",
            self._model,
            page_data.url,
            gemini_s,
        )
        return result
