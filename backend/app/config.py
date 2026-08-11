"""
Настройки приложения, читаются из переменных окружения / файла .env.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_env: str = "development"

    # Какая реализация AgentClient используется: "mock" | "gemini" | "openrouter".
    # При gemini + заданном OPENROUTER_API_KEY автоматически включается failover.
    agent_impl: str = "mock"

    # Gemini. Ключ только из .env; в логи не писать.
    gemini_api_key: str = ""
    # По умолчанию 3.6 Flash: structured JSON без deprecated sampling-параметров.
    gemini_model: str = "gemini-3.6-flash"

    # OpenRouter (бесплатный запасной LLM, обычно Qwen :free).
    openrouter_api_key: str = ""
    openrouter_model: str = "qwen/qwen3-32b:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Для рейтинга приложений OpenRouter (необязательно).
    openrouter_site_url: str = ""
    openrouter_site_name: str = "Conversion Analyzer"

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
