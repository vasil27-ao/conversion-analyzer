"""Сборка зависимостей backend из Settings."""

from __future__ import annotations

from app.agent.errors import AgentConfigError
from app.agent.failover_client import FailoverAgentClient
from app.agent.gemini_client import DEFAULT_GEMINI_MODEL, GeminiAgentClient
from app.agent.groq_client import DEFAULT_GROQ_MODEL, GroqAgentClient
from app.agent.interface import AgentClient
from app.agent.mock_client import MockAgentClient
from app.agent.openrouter_client import (
    DEFAULT_OPENROUTER_MODEL,
    OpenRouterAgentClient,
)
from app.config import Settings
from app.services.orchestrator import AnalysisOrchestrator
from app.storage.repository import AnalysisRepository
from app.storage.sqlite_repository import SqliteAnalysisRepository

# Вторая free Gemini, если GEMINI_MODEL_FALLBACK пуст.
DEFAULT_GEMINI_MODEL_FALLBACK = "gemini-2.5-flash"


def _build_gemini(settings: Settings, *, model: str) -> GeminiAgentClient:
    return GeminiAgentClient(api_key=settings.gemini_api_key, model=model)


def _build_openrouter(settings: Settings) -> OpenRouterAgentClient:
    model = (settings.openrouter_model or "").strip() or DEFAULT_OPENROUTER_MODEL
    return OpenRouterAgentClient(
        api_key=settings.openrouter_api_key,
        model=model,
        base_url=settings.openrouter_base_url,
        site_url=settings.openrouter_site_url,
        site_name=settings.openrouter_site_name,
    )


def _build_groq(settings: Settings) -> GroqAgentClient:
    model = (settings.groq_model or "").strip() or DEFAULT_GROQ_MODEL
    return GroqAgentClient(
        api_key=settings.groq_api_key,
        model=model,
        base_url=settings.groq_base_url,
    )


def build_agent_client(settings: Settings) -> AgentClient:
    """Выбирает Mock / Gemini / OpenRouter / Groq; gemini → цепочка failover."""
    impl = (settings.agent_impl or "mock").strip().lower()
    if impl == "mock":
        return MockAgentClient()

    openrouter_key = (settings.openrouter_api_key or "").strip()
    groq_key = (settings.groq_api_key or "").strip()

    if impl == "openrouter":
        return _build_openrouter(settings)

    if impl == "groq":
        return _build_groq(settings)

    if impl == "gemini":
        primary_model = (settings.gemini_model or "").strip() or DEFAULT_GEMINI_MODEL
        secondary_model = (
            (settings.gemini_model_fallback or "").strip() or DEFAULT_GEMINI_MODEL_FALLBACK
        )

        providers: list[tuple[str, AgentClient]] = [
            (f"gemini:{primary_model}", _build_gemini(settings, model=primary_model)),
        ]
        if secondary_model.lower() != primary_model.lower():
            providers.append(
                (
                    f"gemini:{secondary_model}",
                    _build_gemini(settings, model=secondary_model),
                )
            )
        if openrouter_key:
            or_model = (settings.openrouter_model or "").strip() or DEFAULT_OPENROUTER_MODEL
            providers.append((f"openrouter:{or_model}", _build_openrouter(settings)))
        if groq_key:
            groq_model = (settings.groq_model or "").strip() or DEFAULT_GROQ_MODEL
            providers.append((f"groq:{groq_model}", _build_groq(settings)))

        if len(providers) == 1:
            return providers[0][1]
        return FailoverAgentClient(providers=providers)

    raise AgentConfigError(
        f"Неизвестное значение AGENT_IMPL={settings.agent_impl!r}. "
        "Ожидается 'mock', 'gemini', 'openrouter' или 'groq'."
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
