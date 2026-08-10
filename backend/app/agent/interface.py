"""
Абстракция вызова агента-аналитика.

Реализации (`MockAgentClient`, `GeminiAgentClient`) возвращают сырой
структурированный ответ LLM (`LlmAgentResult`). Итоговый `AgentResult` с
score/level собирается на backend через `assemble_agent_result`
(один вызов LLM → валидация → расчёт overall → итоговый результат).
"""

from abc import ABC, abstractmethod

from app.agent.schemas import LlmAgentResult
from app.page_collector.models import PageData


class AgentClient(ABC):
    @abstractmethod
    async def analyze(self, page_data: PageData) -> LlmAgentResult:
        raise NotImplementedError
