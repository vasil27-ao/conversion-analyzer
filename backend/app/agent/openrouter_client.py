"""
Реализация AgentClient через OpenRouter (OpenAI-compatible Chat Completions).

Используется как бесплатный запасной LLM (по умолчанию Qwen :free).
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

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# Бесплатный fallback на OpenRouter; при исчезновении :free — задайте OPENROUTER_MODEL.
DEFAULT_OPENROUTER_MODEL = "google/gemma-4-31b-it:free"
OPENROUTER_TIMEOUT_S = 180.0


class OpenRouterAgentClient(AgentClient):
    """Вызов OpenRouter chat/completions → LlmAgentResult (JSON в ответе)."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_OPENROUTER_MODEL,
        *,
        base_url: str = DEFAULT_OPENROUTER_BASE_URL,
        system_prompt_path: Path | None = None,
        http_client: Optional[httpx.AsyncClient] = None,
        site_url: str = "",
        site_name: str = "Conversion Analyzer",
    ) -> None:
        if not api_key or not api_key.strip():
            raise AgentConfigError(
                "OPENROUTER_API_KEY не задан. Укажите ключ в backend/.env."
            )
        self._api_key = api_key.strip()
        self._model = (model or "").strip() or DEFAULT_OPENROUTER_MODEL
        self._base_url = (base_url or DEFAULT_OPENROUTER_BASE_URL).rstrip("/")
        self._system_prompt_path = system_prompt_path or DEFAULT_SYSTEM_PROMPT_PATH
        self._http_client = http_client
        self._site_url = (site_url or "").strip()
        self._site_name = (site_name or "").strip() or "Conversion Analyzer"

    async def analyze(self, page_data: PageData) -> LlmAgentResult:
        system_prompt = load_system_prompt(self._system_prompt_path)
        user_text = build_analysis_user_message(page_data)
        logger.info(
            "Calling OpenRouter model=%s url=%s payload_chars=%s",
            self._model,
            page_data.url,
            len(user_text),
        )
        started = time.perf_counter()

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Title": self._site_name,
        }
        if self._site_url:
            headers["HTTP-Referer"] = self._site_url

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
                async with httpx.AsyncClient(timeout=OPENROUTER_TIMEOUT_S) as client:
                    response = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers=headers,
                        json=body,
                    )
        except httpx.TimeoutException as exc:
            logger.error("OpenRouter timeout model=%s", self._model)
            raise AgentApiError(
                "Сервис анализа временно недоступен. Попробуйте позже.",
                status_code=504,
                api_status="timeout",
            ) from exc
        except httpx.HTTPError as exc:
            logger.exception("OpenRouter network error")
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
                    if status is None and isinstance(err.get("metadata"), dict):
                        status = err["metadata"].get("raw")
            except Exception:  # noqa: BLE001
                err_payload = None
            logger.error(
                "OpenRouter API error: code=%s status=%s body=%s",
                code,
                status,
                (response.text or "")[:300],
            )
            raise make_agent_api_error(code, status)

        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            logger.error("OpenRouter unexpected response shape")
            raise AgentApiError(
                "Не удалось выполнить анализ страницы. Попробуйте ещё раз."
            ) from exc

        if isinstance(content, list):
            # Некоторые модели возвращают content parts.
            text_parts = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict)
            ]
            content = "".join(text_parts)

        result = parse_llm_agent_result_from_text(
            str(content),
            provider_label="OpenRouter",
        )
        elapsed = time.perf_counter() - started
        logger.info(
            "OpenRouter response parsed: blocks=%s problems=%s backlog=%s",
            len(result.blocks),
            len(result.problems),
            len(result.backlog),
        )
        logger.info(
            "Timing openrouter model=%s url=%s openrouter_s=%.3f",
            self._model,
            page_data.url,
            elapsed,
        )
        return result
