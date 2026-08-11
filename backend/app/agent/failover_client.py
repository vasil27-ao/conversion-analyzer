"""
Запасной AgentClient: чередует primary/fallback при временных сбоях API.

Без длинных sleep: при 503/перегрузке сразу пробуем другой провайдер,
чтобы не крутить ретраи в один и тот же лимит.
"""

from __future__ import annotations

import logging

from app.agent.common import is_transient_agent_error
from app.agent.errors import AgentClientError
from app.agent.interface import AgentClient
from app.agent.schemas import LlmAgentResult
from app.page_collector.models import PageData

logger = logging.getLogger(__name__)


class FailoverAgentClient(AgentClient):
    """
    Порядок попыток (макс. 3):
    1) primary (Gemini)
    2) fallback (OpenRouter/Qwen) при временной ошибке
    3) ещё раз primary при временной ошибке fallback
    """

    def __init__(
        self,
        primary: AgentClient,
        fallback: AgentClient,
        *,
        primary_name: str = "primary",
        fallback_name: str = "fallback",
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._primary_name = primary_name
        self._fallback_name = fallback_name

    async def analyze(self, page_data: PageData) -> LlmAgentResult:
        sequence: list[tuple[str, AgentClient]] = [
            (self._primary_name, self._primary),
            (self._fallback_name, self._fallback),
            (self._primary_name, self._primary),
        ]
        last_error: AgentClientError | None = None

        for attempt, (name, client) in enumerate(sequence, start=1):
            try:
                logger.info(
                    "Failover attempt=%s provider=%s url=%s",
                    attempt,
                    name,
                    page_data.url,
                )
                return await client.analyze(page_data)
            except AgentClientError as exc:
                last_error = exc
                if attempt >= len(sequence) or not is_transient_agent_error(exc):
                    raise
                logger.warning(
                    "Provider %s failed transiently (attempt=%s); switching. error=%s",
                    name,
                    attempt,
                    exc,
                )

        assert last_error is not None
        raise last_error
