"""FastAPI Depends для доступа к orchestrator и repository."""

from __future__ import annotations

from fastapi import Request

from app.services.orchestrator import AnalysisOrchestrator
from app.storage.repository import AnalysisRepository


def get_orchestrator(request: Request) -> AnalysisOrchestrator:
    return request.app.state.orchestrator


def get_repository(request: Request) -> AnalysisRepository:
    return request.app.state.repository
