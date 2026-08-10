"""
Детерминированный расчёт overall- и block-score на backend.

Формула (MVP, одинаковый вес критериев):
    score = sum(applicable_scores) / (2 * applicable_count) * 100

N/A исключается из расчёта. Округление score до 1 знака.

Overall:
- пороги level: <50 → низкий; [50, 75) → средний; >=75 → высокий;
- если applicable_count == 0 — ошибка расчёта.

Block score:
- та же формула внутри блока;
- если все критерии блока = N/A — score блока = None (не 0).
"""

from typing import Iterable, List, Optional, Sequence

from app.agent.schemas import (
    AgentResult,
    BlockResult,
    LlmAgentResult,
    LlmBlockResult,
    OverallAssessment,
    OverallLevel,
    Score,
)
from app.agent.validation import validate_llm_agent_result


class OverallCalculationError(ValueError):
    """Невозможно посчитать overall (например, все критерии = N/A)."""


def level_from_score(score: float) -> OverallLevel:
    """Пороги level по числовому score (0–100)."""
    if score < 50:
        return "низкий"
    if score < 75:
        return "средний"
    return "высокий"


def _split_scores(scores: Sequence[Score]) -> tuple[List[int], int]:
    applicable: List[int] = []
    na_count = 0
    for score in scores:
        if score == "N/A":
            na_count += 1
        else:
            applicable.append(int(score))
    return applicable, na_count


def score_from_applicable(applicable: Sequence[int]) -> float:
    """Считает numeric score по уже отфильтрованным оценкам 0/1/2."""
    if not applicable:
        raise OverallCalculationError(
            "Невозможно рассчитать score: нет применимых критериев."
        )
    raw = sum(applicable) / (2 * len(applicable)) * 100
    return round(raw, 1)


def compute_overall(scores: Sequence[Score]) -> OverallAssessment:
    """
    Считает overall score/level/счётчики по списку оценок критериев.

    Поле `summary` здесь пустое — его подставляет сборка итогового
    результата из ответа LLM (`assemble_agent_result`).
    """
    applicable, na_count = _split_scores(scores)
    applicable_count = len(applicable)
    if applicable_count == 0:
        raise OverallCalculationError(
            "Невозможно рассчитать overall: нет ни одного применимого "
            "критерия (applicable_count == 0)."
        )

    numeric_score = score_from_applicable(applicable)
    return OverallAssessment(
        score=numeric_score,
        level=level_from_score(numeric_score),
        summary="",
        applicable_count=applicable_count,
        na_count=na_count,
    )


def compute_block_score(scores: Sequence[Score]) -> Optional[float]:
    """
    Score одного блока по той же формуле, что и overall.

    Если все критерии блока = N/A, возвращает None (не искусственный 0).
    """
    applicable, _ = _split_scores(scores)
    if not applicable:
        return None
    return score_from_applicable(applicable)


def iter_criterion_scores(llm_result: LlmAgentResult) -> Iterable[Score]:
    for block in llm_result.blocks:
        for criterion in block.criteria:
            yield criterion.score


def _assemble_block(llm_block: LlmBlockResult) -> BlockResult:
    scores = [c.score for c in llm_block.criteria]
    return BlockResult(
        block_id=llm_block.block_id,
        block_name=llm_block.block_name,
        score=compute_block_score(scores),
        what_is_wrong=llm_block.what_is_wrong,
        why_it_matters=llm_block.why_it_matters,
        criteria=llm_block.criteria,
    )


def assemble_agent_result(llm_result: LlmAgentResult) -> AgentResult:
    """
    Валидирует ответ LLM, затем объединяет его с детерминированными score.

    При ошибке валидации score не рассчитывается.
    """
    validate_llm_agent_result(llm_result)

    computed = compute_overall(list(iter_criterion_scores(llm_result)))
    overall = OverallAssessment(
        score=computed.score,
        level=computed.level,
        summary=llm_result.overall.summary,
        applicable_count=computed.applicable_count,
        na_count=computed.na_count,
    )
    return AgentResult(
        overall=overall,
        blocks=[_assemble_block(block) for block in llm_result.blocks],
        problems=llm_result.problems,
        backlog=llm_result.backlog,
    )
