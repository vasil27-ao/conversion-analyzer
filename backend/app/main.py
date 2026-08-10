"""
Точка входа FastAPI-приложения.

Эндпоинты: health, создание анализа, статус/результат.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_analyses import router as analyses_router
from app.api.routes_health import router as health_router
from app.config import Settings, get_settings
from app.dependencies import build_agent_client, build_orchestrator, build_repository


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    app = FastAPI(
        title="Анализатор конверсионности страниц — backend",
        description="Backend MVP (этап 3): URL → анализ → отчёт по API.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.get_cors_origins(),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    repository = build_repository(app_settings)
    agent = build_agent_client(app_settings)
    orchestrator = build_orchestrator(
        app_settings,
        repository=repository,
        agent=agent,
    )

    app.state.settings = app_settings
    app.state.repository = repository
    app.state.agent = agent
    app.state.orchestrator = orchestrator

    app.include_router(health_router, prefix="/api", tags=["health"])
    app.include_router(analyses_router, prefix="/api", tags=["analyses"])

    return app


app = create_app()
