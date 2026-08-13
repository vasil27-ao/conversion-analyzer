"""Ошибки вызова агента-аналитика (LLM-клиент)."""


class AgentClientError(Exception):
    """Базовая ошибка AgentClient."""


class AgentApiError(AgentClientError):
    """Сбой вызова LLM API (сеть, квота, 4xx/5xx и т.п.)."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        api_status: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.api_status = api_status


class AgentInvalidResponseError(AgentClientError):
    """Ответ LLM пуст, не JSON или не соответствует LlmAgentResult."""


class AgentConfigError(AgentClientError):
    """Некорректная конфигурация клиента (нет ключа, модели и т.п.)."""
