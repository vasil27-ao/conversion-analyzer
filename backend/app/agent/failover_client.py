"""
Запасной AgentClient: цепочка провайдеров при временных сбоях API.

Без длинных sleep: при 503/перегрузке сразу следующий провайдер.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from app.agent.common import is_transient_agent_error
from app.agent.errors import AgentClientError
from app.agent.interface import AgentClient
from app.agent.schemas import LlmAgentResult
from app.page_collector.models import PageData

logger = logging.getLogger(__name__)


class FailoverAgentClient(AgentClient):
    """
    Пробует провайдеров по порядку один раз каждый.

    Пример: Gemini primary → Gemini secondary → OpenRouter → Groq.
    """

    def __init__(
        self,
        providers: Sequence[tuple[str, AgentClient]] | None = None,
        *,
        primary: AgentClient | None = None,
        fallback: AgentClient | None = None,
        primary_name: str = "primary",
        fallback_name: str = "fallback",
    ) -> None:
        if providers is not None:
            chain = [(str(name), client) for name, client in providers]
        elif primary is not None and fallback is not None:
            # Обратная совместимость со старым API primary/fallback + retry primary.
            chain = [
                (primary_name, primary),
                (fallback_name, fallback),
                (primary_name, primary),
            ]
        else:
            raise ValueError(
                "FailoverAgentClient: передайте providers=[...] "
                "или пару primary/fallback."
            )
        if len(chain) < 2:
            raise ValueError("FailoverAgentClient: нужно минимум 2 провайдера.")
        self._providers = chain

    async def analyze(self, page_data: PageData) -> LlmAgentResult:
        last_error: AgentClientError | None = None

        for attempt, (name, client) in enumerate(self._providers, start=1):
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
                if attempt >= len(self._providers) or not is_transient_agent_error(exc):
                    raise
                logger.warning(
                    "Provider %s failed transiently (attempt=%s); switching. error=%s",
                    name,
                    attempt,
                    exc,
                )

        assert last_error is not None
        raise last_error
