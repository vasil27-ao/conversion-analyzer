"""Unit-тесты AnalysisOrchestrator с моками зависимостей."""

from __future__ import annotations

import asyncio
from typing import List, Optional
from unittest.mock import AsyncMock

import pytest
from pydantic import HttpUrl

from app.agent.errors import AgentApiError
from app.agent.interface import AgentClient
from app.agent.mock_client import build_mock_llm_result
from app.agent.schemas import LlmAgentResult, LlmBlockResult, LlmOverall
from app.agent.validation import AgentResponseValidationError
from app.core.models import Analysis
from app.core.status import AnalysisStatus
from app.page_collector.errors import PageUnavailableError
from app.page_collector.models import LayoutSnapshot, PageData, ViewportSize
from app.services.orchestrator import AnalysisOrchestrator
from app.storage.repository import AnalysisRepository


class InMemoryAnalysisRepository(AnalysisRepository):
    """Простой репозиторий + журнал сохранений для проверки статусов."""

    def __init__(self) -> None:
        self.items: dict[str, Analysis] = {}
        self.saved_statuses: List[AnalysisStatus] = []

    async def save(self, analysis: Analysis) -> None:
        self.items[analysis.id] = analysis.model_copy(deep=True)
        self.saved_statuses.append(analysis.status)

    async def get(self, analysis_id: str) -> Optional[Analysis]:
        item = self.items.get(analysis_id)
        return item.model_copy(deep=True) if item is not None else None


def _sample_page(url: str = "https://example.com/landing") -> PageData:
    return PageData(
        url=HttpUrl(url),
        html="<html><body><h1>Demo</h1></body></html>",
        visible_text="Demo",
        layout_desktop=LayoutSnapshot(viewport=ViewportSize(width=1280, height=800)),
        layout_mobile=LayoutSnapshot(viewport=ViewportSize(width=390, height=844)),
    )


def _orchestrator(
    *,
    agent: AgentClient | AsyncMock,
    collect_fn: AsyncMock,
    repo: InMemoryAnalysisRepository | None = None,
) -> tuple[AnalysisOrchestrator, InMemoryAnalysisRepository]:
    repository = repo or InMemoryAnalysisRepository()
    return (
        AnalysisOrchestrator(
            repository=repository,
            agent=agent,
            collect_fn=collect_fn,
        ),
        repository,
    )


def test_run_successful_analysis_pending_running_done():
    agent = AsyncMock(spec=AgentClient)
    agent.analyze = AsyncMock(return_value=build_mock_llm_result())
    collect_fn = AsyncMock(return_value=_sample_page())
    orch, repo = _orchestrator(agent=agent, collect_fn=collect_fn)

    result = asyncio.run(orch.run("https://example.com/ok"))

    assert result.status == AnalysisStatus.DONE
    assert result.result is not None
    assert result.error_message is None
    assert isinstance(result.result.overall.score, float)
    assert repo.saved_statuses == [
        AnalysisStatus.PENDING,
        AnalysisStatus.RUNNING,
        AnalysisStatus.DONE,
    ]
    collect_fn.assert_awaited_once()
    agent.analyze.assert_awaited_once()
    stored = asyncio.run(repo.get(result.id))
    assert stored is not None
    assert stored.status == AnalysisStatus.DONE
    assert stored.result is not None


def test_run_collector_error_sets_failed():
    agent = AsyncMock(spec=AgentClient)
    agent.analyze = AsyncMock()
    collect_fn = AsyncMock(
        side_effect=PageUnavailableError("Страница недоступна (HTTP 404)")
    )
    orch, repo = _orchestrator(agent=agent, collect_fn=collect_fn)

    result = asyncio.run(orch.run("https://example.com/missing"))

    assert result.status == AnalysisStatus.FAILED
    assert result.result is None
    assert result.error_message == "Страница недоступна (HTTP 404)"
    assert repo.saved_statuses == [
        AnalysisStatus.PENDING,
        AnalysisStatus.RUNNING,
        AnalysisStatus.FAILED,
    ]
    agent.analyze.assert_not_awaited()


def test_run_llm_error_sets_failed():
    agent = AsyncMock(spec=AgentClient)
    agent.analyze = AsyncMock(
        side_effect=AgentApiError(
            "Сейчас слишком много запросов к сервису анализа. "
            "Подождите 1–2 минуты и попробуйте снова."
        )
    )
    collect_fn = AsyncMock(return_value=_sample_page())
    orch, repo = _orchestrator(agent=agent, collect_fn=collect_fn)

    result = asyncio.run(orch.run("https://example.com/llm-fail"))

    assert result.status == AnalysisStatus.FAILED
    assert result.result is None
    assert "слишком много запросов" in (result.error_message or "")
    assert repo.saved_statuses == [
        AnalysisStatus.PENDING,
        AnalysisStatus.RUNNING,
        AnalysisStatus.FAILED,
    ]


def test_run_validation_error_sets_failed():
    invalid = LlmAgentResult(
        overall=LlmOverall(summary="Короткий summary без нужного состава блоков."),
        blocks=[
            LlmBlockResult(
                block_id="1",
                block_name="Первый экран и оффер",
                what_is_wrong="x",
                why_it_matters="y",
                criteria=[],
            )
        ],
        problems=[],
        backlog=[],
    )
    agent = AsyncMock(spec=AgentClient)
    agent.analyze = AsyncMock(return_value=invalid)
    collect_fn = AsyncMock(return_value=_sample_page())
    orch, repo = _orchestrator(agent=agent, collect_fn=collect_fn)

    result = asyncio.run(orch.run("https://example.com/invalid-llm"))

    assert result.status == AnalysisStatus.FAILED
    assert result.result is None
    assert result.error_message is not None
    assert "сформировать отчёт" in (result.error_message or "")
    assert repo.saved_statuses == [
        AnalysisStatus.PENDING,
        AnalysisStatus.RUNNING,
        AnalysisStatus.FAILED,
    ]
    # Убеждаемся, что упали именно на validation/assemble, а не раньше.
    with pytest.raises(AgentResponseValidationError):
        from app.agent.overall import assemble_agent_result

        assemble_agent_result(invalid)


def test_orchestrator_serializes_concurrent_analyses():
    current = 0
    max_seen = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_analyze(page_data: PageData) -> LlmAgentResult:
        nonlocal current, max_seen
        current += 1
        max_seen = max(max_seen, current)
        started.set()
        await release.wait()
        current -= 1
        return build_mock_llm_result()

    agent = AsyncMock(spec=AgentClient)
    agent.analyze = AsyncMock(side_effect=slow_analyze)
    collect_fn = AsyncMock(return_value=_sample_page())
    orch, _repo = _orchestrator(agent=agent, collect_fn=collect_fn)

    async def run_two() -> None:
        first = asyncio.create_task(orch.run("https://example.com/one"))
        await started.wait()
        second = asyncio.create_task(orch.run("https://example.com/two"))
        await asyncio.sleep(0.05)
        assert max_seen == 1
        release.set()
        results = await asyncio.gather(first, second)
        assert all(item.status == AnalysisStatus.DONE for item in results)
        assert max_seen == 1

    asyncio.run(run_two())
    assert agent.analyze.await_count == 2
