"""HTTP API: создание анализа и получение статуса/результата."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.api.deps import get_orchestrator, get_repository
from app.api.schemas import (
    AnalysisCreateRequest,
    AnalysisCreateResponse,
    AnalysisStatusResponse,
    ErrorResponse,
)
from app.services.orchestrator import AnalysisOrchestrator
from app.storage.repository import AnalysisRepository

router = APIRouter()


@router.post(
    "/analyses",
    response_model=AnalysisCreateResponse,
    responses={400: {"model": ErrorResponse}},
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_analysis(
    body: AnalysisCreateRequest,
    background_tasks: BackgroundTasks,
    orchestrator: AnalysisOrchestrator = Depends(get_orchestrator),
) -> AnalysisCreateResponse:
    """Принимает URL, сохраняет pending и запускает анализ в фоне."""
    analysis = await orchestrator.create(str(body.url))
    background_tasks.add_task(orchestrator.process, analysis.id)
    return AnalysisCreateResponse(id=analysis.id, status=analysis.status)


@router.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_analysis(
    analysis_id: str,
    repository: AnalysisRepository = Depends(get_repository),
) -> AnalysisStatusResponse:
    """Возвращает статус, результат или ошибку сохранённого анализа."""
    analysis = await repository.get(analysis_id)
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Анализ не найден: {analysis_id}",
        )
    return AnalysisStatusResponse(
        id=analysis.id,
        url=analysis.url,
        status=analysis.status,
        result=analysis.result,
        error_message=analysis.error_message,
    )
