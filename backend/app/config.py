"""
Настройки приложения, читаются из переменных окружения / файла .env.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8-sig",
        extra="ignore",
    )

    app_env: str = "development"

    # Какая реализация AgentClient: "mock" | "gemini" | "openrouter" | "groq".
    # При gemini + ключах OpenRouter/Groq собирается цепочка failover.
    agent_impl: str = "mock"

    # Gemini. Ключ только из .env; в логи не писать.
    gemini_api_key: str = ""
    # По умолчанию 3.6 Flash: structured JSON без deprecated sampling-параметров.
    gemini_model: str = "gemini-3.6-flash"
    # Вторая free-модель Gemini в ротации (отдельная per-model квота).
    gemini_model_fallback: str = "gemini-2.5-flash"

    # OpenRouter (бесплатный запасной LLM).
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemma-4-31b-it:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Для рейтинга приложений OpenRouter (необязательно).
    openrouter_site_url: str = ""
    openrouter_site_name: str = "Conversion Analyzer"

    # Groq — третий бесплатный LLM (отдельная квота: https://console.groq.com/keys).
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Не больше одного анализа одновременно: бесплатные квоты не сгорают
    # от конкурирующих запросов к LLM.
    max_concurrent_analyses: int = 1

    # Путь к SQLite-файлу для AnalysisRepository.
    sqlite_path: str = "data/analyses.db"

    # CORS: origins через запятую (локальный Vite + production frontend).
    cors_origins: str = (
        "http://127.0.0.1:5173,"
        "http://localhost:5173,"
        "http://127.0.0.1:4173,"
        "http://localhost:4173"
    )

    def get_cors_origins(self) -> list[str]:
        return [part.strip() for part in self.cors_origins.split(",") if part.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
