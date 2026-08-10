"""Тесты схем агента и mock-клиента."""

import asyncio

import pytest
from pydantic import HttpUrl, ValidationError

from app.agent.checklist import EXPECTED_CRITERION_IDS
from app.agent.mock_client import MockAgentClient
from app.agent.overall import assemble_agent_result
from app.agent.schemas import (
    AgentResult,
    BacklogItem,
    BlockResult,
    CriterionResult,
    LlmAgentResult,
    LlmBlockResult,
    LlmOverall,
    OverallAssessment,
    ProblemItem,
)
from app.agent.validation import validate_llm_agent_result
from app.page_collector.models import LayoutSnapshot, PageData, ViewportSize
from app.report import mvp_priority_tasks


def test_llm_agent_result_does_not_require_numeric_scores():
    result = LlmAgentResult(
        overall=LlmOverall(summary="Работает оффер. Есть проблемы формы. Резерв — упростить форму."),
        blocks=[
            LlmBlockResult(
                block_id="1",
                block_name="Первый экран и оффер",
                what_is_wrong="Существенных проблем нет.",
                why_it_matters="Оффер понятен, действие доступно.",
                criteria=[
                    CriterionResult(
                        id="1.1",
                        score=2,
                        justification="Заголовок называет продукт.",
                        recommendation=None,
                    )
                ],
            )
        ],
        problems=[],
        backlog=[],
    )
    dumped = result.model_dump()
    assert "score" not in dumped["overall"]
    assert "level" not in dumped["overall"]
    assert "score" not in dumped["blocks"][0]
    assert dumped["blocks"][0]["what_is_wrong"]
    assert dumped["blocks"][0]["why_it_matters"]


def test_agent_result_requires_score_and_level():
    with pytest.raises(ValidationError):
        AgentResult(
            overall=OverallAssessment(  # type: ignore[call-arg]
                summary="Только summary без score/level недопустим в итоговой модели.",
                applicable_count=1,
                na_count=0,
            ),
            blocks=[],
            problems=[],
            backlog=[],
        )


def test_agent_result_accepts_full_overall_and_block_score():
    result = AgentResult(
        overall=OverallAssessment(
            score=62.5,
            level="средний",
            summary="Краткий вывод.",
            applicable_count=16,
            na_count=4,
        ),
        blocks=[
            BlockResult(
                block_id="1",
                block_name="Первый экран и оффер",
                score=75.0,
                what_is_wrong="Существенных проблем нет.",
                why_it_matters="Оффер и CTA считываются.",
                criteria=[],
            ),
            BlockResult(
                block_id="3",
                block_name="Доверие",
                score=None,
                what_is_wrong="Критерии блока неприменимы.",
                why_it_matters="Оценка доверия по этим пунктам не требуется.",
                criteria=[],
            ),
        ],
        problems=[ProblemItem(description="Проблема", location="Форма")],
        backlog=[
            BacklogItem(
                task="Упростить форму",
                zone="Форма",
                priority="высокий",
                expected_effect="Меньше трения при заявке",
            )
        ],
    )
    assert result.overall.score == 62.5
    assert result.blocks[0].score == 75.0
    assert result.blocks[1].score is None


def test_mock_client_returns_complete_llm_shape_and_assembles():
    empty_layout = LayoutSnapshot(viewport=ViewportSize(width=1280, height=800))
    page = PageData(
        url=HttpUrl("https://example.com/landing"),
        html="<html></html>",
        visible_text="Пример",
        layout_desktop=empty_layout,
        layout_mobile=LayoutSnapshot(viewport=ViewportSize(width=390, height=844)),
    )
    llm_result = asyncio.run(MockAgentClient().analyze(page))
    assert isinstance(llm_result, LlmAgentResult)
    validate_llm_agent_result(llm_result)
    assert sum(len(b.criteria) for b in llm_result.blocks) == len(EXPECTED_CRITERION_IDS)

    final = assemble_agent_result(llm_result)
    assert isinstance(final, AgentResult)
    assert final.overall.summary == llm_result.overall.summary
    assert final.overall.applicable_count + final.overall.na_count == 20
    assert final.overall.level in {"низкий", "средний", "высокий"}
    assert isinstance(final.overall.score, float)
    assert all(block.what_is_wrong for block in final.blocks)

    priority = mvp_priority_tasks(final)
    assert len(priority) == 3
    assert priority[0].priority == "высокий"
