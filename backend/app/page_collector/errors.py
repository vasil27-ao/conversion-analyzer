class PageCollectionError(Exception):
    """Базовая ошибка сбора данных страницы."""


class PageUnavailableError(PageCollectionError):
    """Страница недоступна: 404, таймаут, требует авторизации и т.п."""
