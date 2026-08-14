"""
Реализация AgentClient через OpenAI Chat Completions (платный GPT).

Основной провайдер, когда задан OPENAI_API_KEY. Бесплатные LLM остаются
в failover-цепочке после него.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from app.agent.common import (
    DEFAULT_SYSTEM_PROMPT_PATH,
    build_analysis_user_message,
    load_system_prompt,
    make_agent_api_error,
    parse_llm_agent_result_from_text,
)
from app.agent.errors import AgentApiError, AgentConfigError
from app.agent.interface import AgentClient
from app.agent.schemas import LlmAgentResult
from app.page_collector.models import PageData

logger = logging.getLogger(__name__)

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o"
OPENAI_TIMEOUT_S = 180.0


class OpenAIAgentClient(AgentClient):
    """Вызов OpenAI chat/completions → LlmAgentResult (JSON в ответе)."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_OPENAI_MODEL,
        *,
        base_url: str = DEFAULT_OPENAI_BASE_URL,
        system_prompt_path: Path | None = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise AgentConfigError(
                "OPENAI_API_KEY не задан. Укажите ключ в backend/.env "
                "(https://platform.openai.com/api-keys)."
            )
        self._api_key = api_key.strip()
        self._model = (model or "").strip() or DEFAULT_OPENAI_MODEL
        self._base_url = (base_url or DEFAULT_OPENAI_BASE_URL).rstrip("/")
        self._system_prompt_path = system_prompt_path or DEFAULT_SYSTEM_PROMPT_PATH
        self._http_client = http_client

    async def analyze(self, page_data: PageData) -> LlmAgentResult:
        system_prompt = load_system_prompt(self._system_prompt_path)
        user_text = build_analysis_user_message(page_data)
        logger.info(
            "Calling OpenAI model=%s url=%s payload_chars=%s",
            self._model,
            page_data.url,
            len(user_text),
        )
        started = time.perf_counter()

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }

        try:
            if self._http_client is not None:
                response = await self._http_client.post(
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=body,
                )
            else:
                async with httpx.AsyncClient(timeout=OPENAI_TIMEOUT_S) as client:
                    response = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers=headers,
                        json=body,
                    )
        except httpx.TimeoutException as exc:
            logger.error("OpenAI timeout model=%s", self._model)
            raise AgentApiError(
                "Сервис анализа временно недоступен. Попробуйте позже.",
                status_code=504,
                api_status="timeout",
            ) from exc
        except httpx.HTTPError as exc:
            logger.exception("OpenAI network error")
            raise AgentApiError(
                "Не удалось выполнить анализ страницы. Попробуйте ещё раз."
            ) from exc

        if response.status_code >= 400:
            code = response.status_code
            status = None
            try:
                err_payload = response.json()
                err = err_payload.get("error") if isinstance(err_payload, dict) else None
                if isinstance(err, dict):
                    status = err.get("code") or err.get("type") or err.get("status")
            except Exception:  # noqa: BLE001
                err_payload = None
            logger.error(
                "OpenAI API error: code=%s status=%s body=%s",
                code,
                status,
                (response.text or "")[:300],
            )
            raise make_agent_api_error(code, status)

        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            logger.error("OpenAI unexpected response shape")
            raise AgentApiError(
                "Не удалось выполнить анализ страницы. Попробуйте ещё раз."
            ) from exc

        if isinstance(content, list):
            text_parts = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict)
            ]
            content = "".join(text_parts)

        result = parse_llm_agent_result_from_text(
            str(content),
            provider_label="OpenAI",
        )
        elapsed = time.perf_counter() - started
        logger.info(
            "OpenAI response parsed: blocks=%s problems=%s backlog=%s",
            len(result.blocks),
            len(result.problems),
            len(result.backlog),
        )
        logger.info(
            "Timing openai model=%s url=%s openai_s=%.3f",
            self._model,
            page_data.url,
            elapsed,
        )
        return result
