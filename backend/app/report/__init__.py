"""
Модуль сборки отчёта из итогового результата анализа (`AgentResult`).

Формат MVP-отчёта для пользователя (без отдельных сущностей «сильных сторон»
и т.п.):

1. overall.score / 100 + overall.level;
2. overall.summary (2–3 содержательных предложения от LLM);
3. «Что улучшить в первую очередь» — первые 3 задачи из backlog
   (backlog уже отсортирован LLM по приоритету; отдельная сущность не нужна);
4. оценка по 6 блокам: название, block.score, what_is_wrong, why_it_matters,
   подробные критерии;
5. полный список problems;
6. полный backlog.

Сборка файла экспорта и экран отчёта реализуются на следующих этапах.
"""

from typing import List

from app.agent.schemas import AgentResult, BacklogItem

MVP_PRIORITY_TASK_COUNT = 3


def mvp_priority_tasks(result: AgentResult, limit: int = MVP_PRIORITY_TASK_COUNT) -> List[BacklogItem]:
    """Первые N задач backlog для блока «Что улучшить в первую очередь»."""
    return list(result.backlog[:limit])
