"""
Абстракция хранения результатов анализа.

Реализация для MVP: `SqliteAnalysisRepository` в `sqlite_repository.py`.
Остальной backend работает через этот интерфейс.
"""

from abc import ABC, abstractmethod
from typing import Optional

from app.core.models import Analysis


class AnalysisRepository(ABC):
    @abstractmethod
    async def save(self, analysis: Analysis) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get(self, analysis_id: str) -> Optional[Analysis]:
        raise NotImplementedError
