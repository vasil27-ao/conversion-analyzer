"""
Запасной AgentClient: цепочка провайдеров при временных сбоях API.

Один LLM-запрос в полёте на клиент. Для 429/503 — retry с exponential backoff
на том же провайдере; fallback только после реального отказа предыдущего.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence

from app.agent.common import is_retryable_agent_error, is_transient_agent_error
from app.agent.errors import AgentApiError, AgentClientError
from app.agent.interface import AgentClient
from app.agent.llm_stats import LlmCallStats, reset_llm_stats
from app.agent.schemas import LlmAgentResult
from app.page_collector.models import PageData

logger = logging.getLogger(__name__)

LLM_RETRY_MAX_ATTEMPTS = 3
LLM_RETRY_BASE_DELAY_S = 2.0
LLM_RETRY_MAX_DELAY_S = 8.0

SleepFn = Callable[[float], Awaitable[None]]


def retry_delay_s(
    failed_attempt: int,
    *,
    base_delay_s: float = LLM_RETRY_BASE_DELAY_S,
    max_delay_s: float = LLM_RETRY_MAX_DELAY_S,
) -> float:
    """Delay after the Nth failed attempt (1-based) before the next try."""
    delay = base_delay_s * (2 ** max(0, failed_attempt - 1))
    return min(max_delay_s, delay)


class FailoverAgentClient(AgentClient):
    """
    Пробует провайдеров строго по порядку.

    На каждом: до LLM_RETRY_MAX_ATTEMPTS попыток при 429/503 с backoff.
    Следующий провайдер — только если текущий реально отказал.
    """

    def __init__(
        self,
        providers: Sequence[tuple[str, AgentClient]] | None = None,
        *,
        primary: AgentClient | None = None,
        fallback: AgentClient | None = None,
        primary_name: str = "primary",
        fallback_name: str = "fallback",
        sleep_fn: SleepFn | None = None,
        max_attempts: int = LLM_RETRY_MAX_ATTEMPTS,
        base_delay_s: float = LLM_RETRY_BASE_DELAY_S,
        max_delay_s: float = LLM_RETRY_MAX_DELAY_S,
    ) -> None:
        if providers is not None:
            chain = [(str(name), client) for name, client in providers]
        elif primary is not None and fallback is not None:
            chain = [
                (primary_name, primary),
                (fallback_name, fallback),
            ]
        else:
            raise ValueError(
                "FailoverAgentClient: передайте providers=[...] "
                "или пару primary/fallback."
            )
        if not chain:
            raise ValueError("FailoverAgentClient: нужна хотя бы 1 запись в цепочке.")
        self._providers = chain
        self._sleep = sleep_fn
        self._max_attempts = max(1, int(max_attempts))
        self._base_delay_s = float(base_delay_s)
        self._max_delay_s = float(max_delay_s)
        self._llm_lock: asyncio.Lock | None = None
        self.last_stats: LlmCallStats | None = None

    def _get_lock(self) -> asyncio.Lock:
        if self._llm_lock is None:
            self._llm_lock = asyncio.Lock()
        return self._llm_lock

    async def _sleep_backoff(self, delay: float) -> None:
        if delay <= 0:
            return
        if self._sleep is not None:
            await self._sleep(delay)
            return
        await asyncio.sleep(delay)

    async def analyze(self, page_data: PageData) -> LlmAgentResult:
        stats = reset_llm_stats()
        self.last_stats = stats
        chain_started = time.perf_counter()
        async with self._get_lock():
            try:
                return await self._analyze_locked(page_data, stats)
            finally:
                stats.llm_elapsed_s = time.perf_counter() - chain_started
                logger.info(
                    "LLM chain finished url=%s provider=%s llm_s=%.3f "
                    "success_call_s=%.3f retries=%s fallback=%s "
                    "tried=%s codes=%s had_429=%s had_503=%s",
                    page_data.url,
                    stats.success_provider,
                    stats.llm_elapsed_s,
                    stats.success_call_s,
                    stats.retry_count,
                    stats.fallback_used,
                    ",".join(stats.providers_tried) or "-",
                    ",".join(str(code) for code in stats.status_codes_seen) or "-",
                    stats.had_429,
                    stats.had_503,
                )

    async def _analyze_locked(
        self,
        page_data: PageData,
        stats,
    ) -> LlmAgentResult:
        last_error: AgentClientError | None = None
        provider_count = len(self._providers)

        for provider_index, (name, client) in enumerate(self._providers):
            stats.providers_tried.append(name)
            provider_error: AgentClientError | None = None

            for attempt in range(1, self._max_attempts + 1):
                logger.info(
                    "LLM request provider=%s attempt=%s/%s url=%s",
                    name,
                    attempt,
                    self._max_attempts,
                    page_data.url,
                )
                call_started = time.perf_counter()
                try:
                    result = await client.analyze(page_data)
                except AgentClientError as exc:
                    call_s = time.perf_counter() - call_started
                    provider_error = exc
                    last_error = exc
                    status_code = (
                        exc.status_code if isinstance(exc, AgentApiError) else None
                    )
                    stats.mark_status(status_code)
                    logger.warning(
                        "LLM error provider=%s attempt=%s/%s elapsed_s=%.3f "
                        "status_code=%s error=%s",
                        name,
                        attempt,
                        self._max_attempts,
                        call_s,
                        status_code,
                        exc,
                    )
                    if is_retryable_agent_error(exc) and attempt < self._max_attempts:
                        delay = retry_delay_s(
                            attempt,
                            base_delay_s=self._base_delay_s,
                            max_delay_s=self._max_delay_s,
                        )
                        stats.retry_count += 1
                        logger.warning(
                            "LLM retry provider=%s next_attempt=%s delay_s=%.1f "
                            "status_code=%s",
                            name,
                            attempt + 1,
                            delay,
                            status_code,
                        )
                        await self._sleep_backoff(delay)
                        continue
                    break

                call_s = time.perf_counter() - call_started
                stats.success_provider = name
                stats.success_call_s = call_s
                stats.fallback_used = provider_index > 0
                if attempt > 1:
                    # Успех после retry на этом провайдере уже учтён в retry_count.
                    pass
                logger.info(
                    "LLM success provider=%s url=%s elapsed_s=%.3f "
                    "retries=%s fallback=%s",
                    name,
                    page_data.url,
                    call_s,
                    stats.retry_count,
                    stats.fallback_used,
                )
                return result

            assert provider_error is not None
            can_fallback = (
                provider_index + 1 < provider_count
                and is_transient_agent_error(provider_error)
            )
            if not can_fallback:
                raise provider_error
            logger.warning(
                "LLM fallback from=%s to=%s after real failure error=%s",
                name,
                self._providers[provider_index + 1][0],
                provider_error,
            )

        assert last_error is not None
        raise last_error
