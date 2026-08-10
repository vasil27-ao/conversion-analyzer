"""
Pydantic-схемы запросов и ответов HTTP API.

Контракт этапа 3: создание анализа по URL и получение статуса/результата.
"""

from typing import Optional

from pydantic import BaseModel, HttpUrl

from app.agent.schemas import AgentResult
from app.core.status import AnalysisStatus


class AnalysisCreateRequest(BaseModel):
    url: HttpUrl


class AnalysisCreateResponse(BaseModel):
    id: str
    status: AnalysisStatus


class AnalysisStatusResponse(BaseModel):
    id: str
    url: HttpUrl
    status: AnalysisStatus
    result: Optional[AgentResult] = None
    error_message: Optional[str] = None


class ErrorResponse(BaseModel):
    detail: str
