"""
Доменная модель одного анализа.

Соответствует требованию ТЗ «один анализ — один сохранённый результат»
(раздел 6). Способ фактического хранения (SQLite, файлы и т.п.) здесь
не фигурирует — это дело реализации AnalysisRepository.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, HttpUrl

from app.agent.schemas import AgentResult
from app.core.status import AnalysisStatus


class Analysis(BaseModel):
    id: str
    url: HttpUrl
    status: AnalysisStatus
    created_at: datetime
    result: Optional[AgentResult] = None
    error_message: Optional[str] = None
