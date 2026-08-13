"""
Оркестрация одного полного анализа страницы.

Склеивает готовые компоненты без новых доменных сущностей:
collect_page_data → AgentClient → assemble_agent_result → AnalysisRepository.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from app.agent.errors import AgentClientError
from app.agent.interface import AgentClient
from app.agent.llm_stats import get_llm_stats, reset_llm_stats
from app.agent.overall import OverallCalculationError, assemble_agent_result
from app.agent.validation import AgentResponseValidationError
from app.core.models import Analysis
from app.core.status import AnalysisStatus
from app.page_collector.collector import collect_page_data
from app.page_collector.errors import PageCollectionError
from app.page_collector.models import PageData
from app.storage.repository import AnalysisRepository

logger = logging.getLogger(__name__)

CollectPageDataFn = Callable[[str], Awaitable[PageData]]


class AnalysisNotFoundError(LookupError):
    """Анализ с указанным id не найден в хранилище."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_analysis_id() -> str:
    return str(uuid.uuid4())


def _user_error_message(exc: BaseException) -> str:
    """Понятное сообщение для сохранения в Analysis.error_message."""
    if isinstance(exc, PageCollectionError):
        return str(exc) or "Не удалось собрать данные страницы."
    if isinstance(exc, AgentClientError):
        return str(exc) or "Не удалось выполнить анализ страницы. Попробуйте ещё раз."
    if isinstance(exc, AgentResponseValidationError):
        return "Не удалось сформировать отчёт по методике. Попробуйте ещё раз."
    if isinstance(exc, OverallCalculationError):
        return "Не удалось рассчитать оценку страницы. Попробуйте ещё раз."
    return "Анализ прервался из-за внутренней ошибки. Попробуйте ещё раз."


class AnalysisOrchestrator:
    """
    Полный цикл одного анализа.

    create() — сразу pending (для API + BackgroundTasks);
    process() — running → done|failed;
    run() — create + process (удобно для sync/тестов).
    """

    def __init__(
        self,
        repository: AnalysisRepository,
        agent: AgentClient,
        collect_fn: Optional[CollectPageDataFn] = None,
        max_concurrent_analyses: int = 1,
    ) -> None:
        self._repository = repository
        self._agent = agent
        self._collect = collect_fn or collect_page_data
        self._max_concurrent_analyses = max(1, int(max_concurrent_analyses))
        self._analysis_semaphore: asyncio.Semaphore | None = None

    async def create(self, url: str) -> Analysis:
        analysis = Analysis(
            id=_new_analysis_id(),
            url=url,
            status=AnalysisStatus.PENDING,
            created_at=_utc_now(),
            result=None,
            error_message=None,
        )
        await self._repository.save(analysis)
        logger.info("Analysis created id=%s status=pending url=%s", analysis.id, url)
        return analysis

    def _get_analysis_semaphore(self) -> asyncio.Semaphore:
        if self._analysis_semaphore is None:
            self._analysis_semaphore = asyncio.Semaphore(self._max_concurrent_analyses)
        return self._analysis_semaphore

    def _log_llm_stats(self, analysis_id: str, url: str) -> None:
        stats = get_llm_stats()
        agent_stats = getattr(self._agent, "last_stats", None)
        if agent_stats is not None:
            stats = agent_stats
        if stats is None:
            return
        logger.info(
            "Analysis LLM id=%s url=%s provider=%s llm_s=%.3f success_call_s=%.3f "
            "retries=%s fallback=%s tried=%s codes=%s had_429=%s had_503=%s",
            analysis_id,
            url,
            stats.success_provider or "-",
            stats.llm_elapsed_s,
            stats.success_call_s,
            stats.retry_count,
            stats.fallback_used,
            ",".join(stats.providers_tried) or "-",
            ",".join(str(code) for code in stats.status_codes_seen) or "-",
            stats.had_429,
            stats.had_503,
        )

    async def process(self, analysis_id: str) -> Analysis:
        analysis = await self._repository.get(analysis_id)
        if analysis is None:
            raise AnalysisNotFoundError(f"Анализ не найден: {analysis_id}")

        async with self._get_analysis_semaphore():
            return await self._process_locked(analysis)

    async def _process_locked(self, analysis: Analysis) -> Analysis:
        reset_llm_stats()
        analysis = analysis.model_copy(update={"status": AnalysisStatus.RUNNING})
        await self._repository.save(analysis)
        logger.info("Analysis id=%s status=running", analysis.id)
        process_started = time.perf_counter()

        try:
            page_data = await self._collect(str(analysis.url))
            llm_result = await self._agent.analyze(page_data)
            agent_result = assemble_agent_result(llm_result)
            analysis = analysis.model_copy(
                update={
                    "status": AnalysisStatus.DONE,
                    "result": agent_result,
                    "error_message": None,
                }
            )
            await self._repository.save(analysis)
            total_s = time.perf_counter() - process_started
            self._log_llm_stats(analysis.id, str(analysis.url))
            logger.info(
                "Analysis id=%s status=done score=%s",
                analysis.id,
                agent_result.overall.score,
            )
            logger.info(
                "Timing total id=%s url=%s total_s=%.3f",
                analysis.id,
                analysis.url,
                total_s,
            )
            return analysis
        except Exception as exc:  # noqa: BLE001 — фиксируем failed и не роняем оркестратор
            message = _user_error_message(exc)
            total_s = time.perf_counter() - process_started
            self._log_llm_stats(analysis.id, str(analysis.url))
            logger.exception(
                "Analysis id=%s failed: %s",
                analysis.id,
                type(exc).__name__,
            )
            logger.info(
                "Timing total id=%s url=%s total_s=%.3f status=failed",
                analysis.id,
                analysis.url,
                total_s,
            )
            analysis = analysis.model_copy(
                update={
                    "status": AnalysisStatus.FAILED,
                    "result": None,
                    "error_message": message,
                }
            )
            await self._repository.save(analysis)
            return analysis

    async def run(self, url: str) -> Analysis:
        """Синхронная для вызывающего полная цепочка: pending → … → done|failed."""
        analysis = await self.create(url)
        return await self.process(analysis.id)
