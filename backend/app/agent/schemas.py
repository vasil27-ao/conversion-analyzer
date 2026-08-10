"""
Модели результата анализа страницы.

Разделение намеренно минимальное:
- `LlmAgentResult` — сырой ответ одного вызова LLM (без numeric score/level
  и без score блоков);
- `AgentResult` — итоговый результат после валидации и расчёта overall /
  block score на backend.

Numeric score считает backend (см. `app.agent.overall`), а не LLM.
"""

from typing import List, Literal, Optional, Union

from pydantic import BaseModel

Score = Union[Literal[0], Literal[1], Literal[2], Literal["N/A"]]
OverallLevel = Literal["низкий", "средний", "высокий"]


class CriterionResult(BaseModel):
    id: str
    score: Score
    justification: str
    # Всегда присутствует в ответе LLM: строка при 0/1, null при 2/N/A.
    recommendation: Optional[str]


class LlmBlockResult(BaseModel):
    """Блок в ответе LLM: аналитика + критерии, без numeric score."""

    block_id: str
    block_name: str
    # Кратко: основные проблемы блока (или что существенных нет).
    what_is_wrong: str
    # Почему это важно для понимания / доверия / доступности действия.
    why_it_matters: str
    criteria: List[CriterionResult]


class BlockResult(BaseModel):
    """Итоговый блок: аналитика LLM + score, посчитанный backend."""

    block_id: str
    block_name: str
    # None, если все критерии блока = N/A (не подставляем искусственный 0).
    score: Optional[float]
    what_is_wrong: str
    why_it_matters: str
    criteria: List[CriterionResult]


class ProblemItem(BaseModel):
    description: str
    location: str


class BacklogItem(BaseModel):
    task: str
    zone: str
    priority: Literal["высокий", "средний", "низкий"]
    expected_effect: str


class LlmOverall(BaseModel):
    """Часть overall, которую пишет LLM: только аналитический summary."""

    summary: str


class LlmAgentResult(BaseModel):
    """Сырой структурированный ответ LLM (один вызов)."""

    overall: LlmOverall
    blocks: List[LlmBlockResult]
    problems: List[ProblemItem]
    backlog: List[BacklogItem]


class OverallAssessment(BaseModel):
    """Итоговый overall: summary от LLM + детерминированный расчёт backend."""

    score: float
    level: OverallLevel
    summary: str
    applicable_count: int
    na_count: int


class AgentResult(BaseModel):
    """Итоговый результат анализа после расчёта score на backend."""

    overall: OverallAssessment
    blocks: List[BlockResult]
    problems: List[ProblemItem]
    backlog: List[BacklogItem]
