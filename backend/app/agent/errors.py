"""Ошибки вызова агента-аналитика (LLM-клиент)."""


class AgentClientError(Exception):
    """Базовая ошибка AgentClient."""


class AgentApiError(AgentClientError):
    """Сбой вызова LLM API (сеть, квота, 4xx/5xx и т.п.)."""


class AgentInvalidResponseError(AgentClientError):
    """Ответ LLM пуст, не JSON или не соответствует LlmAgentResult."""


class AgentConfigError(AgentClientError):
    """Некорректная конфигурация клиента (нет ключа, модели и т.п.)."""
