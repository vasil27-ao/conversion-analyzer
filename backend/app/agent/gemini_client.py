"""
Реализация AgentClient через Gemini API.

Один вызов модели → сырой `LlmAgentResult`. Numeric score не считается здесь
(это делает `assemble_agent_result` на backend).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import ValidationError

from app.agent.errors import (
    AgentApiError,
    AgentConfigError,
    AgentInvalidResponseError,
)
from app.agent.interface import AgentClient
from app.agent.schemas import LlmAgentResult
from app.page_collector.models import PageData

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT_PATH = (
    Path(__file__).resolve().parent / "prompts" / "system_prompt.md"
)
# HTML лендингов часто слишком большой для одного запроса; layout и текст
# остаются полными, HTML обрезается с явной пометкой.
HTML_CHAR_LIMIT = 120_000
# Доля лимита на начало страницы; остаток — на хвост (футер, отзывы, CTA снизу).
HTML_HEAD_RATIO = 0.55
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"


def load_system_prompt(path: Path | None = None) -> str:
    prompt_path = path or DEFAULT_SYSTEM_PROMPT_PATH
    text = prompt_path.read_text(encoding="utf-8").strip()
    if not text:
        raise AgentConfigError(f"Системный промпт пуст: {prompt_path}")
    return text


def truncate_html_for_llm(html: str, limit: int = HTML_CHAR_LIMIT) -> tuple[str, bool]:
    """
    Обрезает HTML до limit, сохраняя начало и конец страницы.

    Так в LLM остаются и первый экран, и нижние блоки (футер, отзывы,
    гарантии, кейсы, повторные CTA). Середина может быть опущена.
    """
    if len(html) <= limit:
        return html, False

    marker = (
        "\n<!-- HTML middle omitted for LLM input: kept page head + tail "
        f"(limit={limit}, original_len={len(html)}) -->\n"
    )
    # Маркер входит в лимит, чтобы итоговая длина не превышала limit.
    budget = limit - len(marker)
    if budget < 2:
        return html[:limit], True

    head_len = max(1, int(budget * HTML_HEAD_RATIO))
    tail_len = budget - head_len
    if tail_len < 1:
        head_len = budget - 1
        tail_len = 1

    truncated = html[:head_len] + marker + html[-tail_len:]
    return truncated, True


def build_page_payload(page_data: PageData) -> dict[str, Any]:
    """Сериализует PageData для user-сообщения без скриншотов и без ключей."""
    payload = page_data.model_dump(mode="json")
    html = payload.get("html") or ""
    truncated_html, was_truncated = truncate_html_for_llm(html)
    payload["html"] = truncated_html
    payload["html_truncated"] = was_truncated
    if was_truncated:
        logger.warning(
            "Page HTML truncated for LLM input (head+tail): url=%s "
            "original_len=%s limit=%s kept_len=%s",
            page_data.url,
            len(html),
            HTML_CHAR_LIMIT,
            len(truncated_html),
        )
    return payload


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
    if not text or not str(text).strip():
        raise AgentInvalidResponseError("Пустой ответ Gemini.")

    try:
        data = json.loads(str(text))
    except json.JSONDecodeError as exc:
        raise AgentInvalidResponseError(
            "Ответ Gemini не является валидным JSON."
        ) from exc

    try:
        return LlmAgentResult.model_validate(data)
    except ValidationError as exc:
        raise AgentInvalidResponseError(
            f"Ответ Gemini не соответствует LlmAgentResult: {exc}"
        ) from exc


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
        system_prompt = load_system_prompt(self._system_prompt_path)
        user_payload = build_page_payload(page_data)
        user_text = (
            "Проанализируй лендинг строго по системному промпту и верни только "
            "JSON по схеме LlmAgentResult (без numeric overall/block score).\n\n"
            f"Данные страницы (JSON):\n{json.dumps(user_payload, ensure_ascii=False)}"
        )

        logger.info(
            "Calling Gemini model=%s url=%s",
            self._model,
            page_data.url,
        )

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
            logger.error(
                "Gemini API error: code=%s status=%s",
                getattr(exc, "code", None),
                getattr(exc, "status", None),
            )
            raise AgentApiError(
                f"Ошибка Gemini API (code={getattr(exc, 'code', None)})."
            ) from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected Gemini client failure")
            raise AgentApiError("Не удалось выполнить вызов Gemini API.") from exc

        result = _parse_llm_agent_result(response)
        logger.info(
            "Gemini response parsed: blocks=%s problems=%s backlog=%s",
            len(result.blocks),
            len(result.problems),
            len(result.backlog),
        )
        return result
