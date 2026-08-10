"""Сборка зависимостей backend из Settings."""

from __future__ import annotations

from app.agent.errors import AgentConfigError
from app.agent.gemini_client import DEFAULT_GEMINI_MODEL, GeminiAgentClient
from app.agent.interface import AgentClient
from app.agent.mock_client import MockAgentClient
from app.config import Settings
from app.services.orchestrator import AnalysisOrchestrator
from app.storage.repository import AnalysisRepository
from app.storage.sqlite_repository import SqliteAnalysisRepository


def build_agent_client(settings: Settings) -> AgentClient:
    """Выбирает Mock или Gemini по AGENT_IMPL."""
    impl = (settings.agent_impl or "mock").strip().lower()
    if impl == "mock":
        return MockAgentClient()
    if impl == "gemini":
        model = (settings.gemini_model or "").strip() or DEFAULT_GEMINI_MODEL
        return GeminiAgentClient(api_key=settings.gemini_api_key, model=model)
    raise AgentConfigError(
        f"Неизвестное значение AGENT_IMPL={settings.agent_impl!r}. "
        "Ожидается 'mock' или 'gemini'."
    )


def build_repository(settings: Settings) -> AnalysisRepository:
    return SqliteAnalysisRepository(settings.sqlite_path)


def build_orchestrator(
    settings: Settings,
    *,
    repository: AnalysisRepository | None = None,
    agent: AgentClient | None = None,
) -> AnalysisOrchestrator:
    return AnalysisOrchestrator(
        repository=repository or build_repository(settings),
        agent=agent or build_agent_client(settings),
    )
