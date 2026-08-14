"""Сборка зависимостей backend из Settings."""

from __future__ import annotations

from app.agent.errors import AgentConfigError
from app.agent.failover_client import FailoverAgentClient
from app.agent.gemini_client import DEFAULT_GEMINI_MODEL, GeminiAgentClient
from app.agent.groq_client import DEFAULT_GROQ_MODEL, GroqAgentClient
from app.agent.interface import AgentClient
from app.agent.mock_client import MockAgentClient
from app.agent.openai_client import DEFAULT_OPENAI_MODEL, OpenAIAgentClient
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


def _build_openai(settings: Settings) -> OpenAIAgentClient:
    model = (settings.openai_model or "").strip() or DEFAULT_OPENAI_MODEL
    return OpenAIAgentClient(
        api_key=settings.openai_api_key,
        model=model,
        base_url=settings.openai_base_url,
    )


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


def _openai_entry(settings: Settings) -> tuple[str, AgentClient]:
    model = (settings.openai_model or "").strip() or DEFAULT_OPENAI_MODEL
    return (f"openai:{model}", _build_openai(settings))


def _gemini_entries(settings: Settings) -> list[tuple[str, AgentClient]]:
    if not (settings.gemini_api_key or "").strip():
        return []
    primary_model = (settings.gemini_model or "").strip() or DEFAULT_GEMINI_MODEL
    secondary_model = (
        (settings.gemini_model_fallback or "").strip() or DEFAULT_GEMINI_MODEL_FALLBACK
    )
    entries: list[tuple[str, AgentClient]] = [
        (f"gemini:{primary_model}", _build_gemini(settings, model=primary_model)),
    ]
    if secondary_model.lower() != primary_model.lower():
        entries.append(
            (
                f"gemini:{secondary_model}",
                _build_gemini(settings, model=secondary_model),
            )
        )
    return entries


def _openrouter_entry(settings: Settings) -> tuple[str, AgentClient] | None:
    if not (settings.openrouter_api_key or "").strip():
        return None
    model = (settings.openrouter_model or "").strip() or DEFAULT_OPENROUTER_MODEL
    return (f"openrouter:{model}", _build_openrouter(settings))


def _groq_entry(settings: Settings) -> tuple[str, AgentClient] | None:
    if not (settings.groq_api_key or "").strip():
        return None
    model = (settings.groq_model or "").strip() or DEFAULT_GROQ_MODEL
    return (f"groq:{model}", _build_groq(settings))


def _append_free_fallbacks(
    providers: list[tuple[str, AgentClient]],
    settings: Settings,
    *,
    include_gemini: bool = True,
) -> None:
    if include_gemini:
        providers.extend(_gemini_entries(settings))
    openrouter = _openrouter_entry(settings)
    if openrouter is not None:
        providers.append(openrouter)
    groq = _groq_entry(settings)
    if groq is not None:
        providers.append(groq)


def _wrap_providers(providers: list[tuple[str, AgentClient]]) -> AgentClient:
    if not providers:
        raise AgentConfigError("Не удалось собрать цепочку LLM-провайдеров.")
    return FailoverAgentClient(providers=providers)


def build_agent_client(settings: Settings) -> AgentClient:
    """Выбирает Mock / OpenAI / Gemini / OpenRouter / Groq; gpt → failover."""
    impl = (settings.agent_impl or "mock").strip().lower()
    if impl == "mock":
        return MockAgentClient()

    openai_key = (settings.openai_api_key or "").strip()

    if impl == "openai":
        if not openai_key:
            raise AgentConfigError(
                "OPENAI_API_KEY не задан. Укажите ключ в backend/.env "
                "(https://platform.openai.com/api-keys)."
            )
        providers: list[tuple[str, AgentClient]] = [_openai_entry(settings)]
        _append_free_fallbacks(providers, settings)
        return _wrap_providers(providers)

    if impl == "openrouter":
        entry = _openrouter_entry(settings)
        if entry is None:
            raise AgentConfigError(
                "OPENROUTER_API_KEY не задан. Укажите ключ в backend/.env."
            )
        return _wrap_providers([entry])

    if impl == "groq":
        entry = _groq_entry(settings)
        if entry is None:
            raise AgentConfigError(
                "GROQ_API_KEY не задан. Укажите ключ в backend/.env "
                "(https://console.groq.com/keys)."
            )
        return _wrap_providers([entry])

    if impl == "gemini":
        providers = []
        # Платный GPT — основной, если ключ уже задан (даже при AGENT_IMPL=gemini).
        if openai_key:
            providers.append(_openai_entry(settings))
        _append_free_fallbacks(providers, settings)
        if not providers:
            raise AgentConfigError(
                "Для AGENT_IMPL=gemini нужен GEMINI_API_KEY или OPENAI_API_KEY."
            )
        return _wrap_providers(providers)

    raise AgentConfigError(
        f"Неизвестное значение AGENT_IMPL={settings.agent_impl!r}. "
        "Ожидается 'mock', 'openai', 'gemini', 'openrouter' или 'groq'."
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
        max_concurrent_analyses=settings.max_concurrent_analyses,
    )
