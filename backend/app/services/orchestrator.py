"""
Оркестрация одного полного анализа страницы.

Склеивает готовые компоненты без новых доменных сущностей:
collect_page_data → AgentClient → assemble_agent_result → AnalysisRepository.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from app.agent.errors import AgentClientError
from app.agent.interface import AgentClient
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
        return str(exc) or "Ошибка при обращении к агенту-аналитику."
    if isinstance(exc, AgentResponseValidationError):
        return f"Ответ агента не прошёл проверку методики: {exc}"
    if isinstance(exc, OverallCalculationError):
        return f"Не удалось рассчитать оценку страницы: {exc}"
    return "Анализ прервался из-за внутренней ошибки."


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
    ) -> None:
        self._repository = repository
        self._agent = agent
        self._collect = collect_fn or collect_page_data

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

    async def process(self, analysis_id: str) -> Analysis:
        analysis = await self._repository.get(analysis_id)
        if analysis is None:
            raise AnalysisNotFoundError(f"Анализ не найден: {analysis_id}")

        analysis = analysis.model_copy(update={"status": AnalysisStatus.RUNNING})
        await self._repository.save(analysis)
        logger.info("Analysis id=%s status=running", analysis.id)

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
            logger.info(
                "Analysis id=%s status=done score=%s",
                analysis.id,
                agent_result.overall.score,
            )
            return analysis
        except Exception as exc:  # noqa: BLE001 — фиксируем failed и не роняем оркестратор
            message = _user_error_message(exc)
            logger.exception(
                "Analysis id=%s failed: %s",
                analysis.id,
                type(exc).__name__,
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
