"""
Сбор данных страницы через Playwright.

Один URL → рендер → HTML / видимый текст / layout desktop и mobile.
Скриншоты не создаются, на другие страницы сайта переходов нет.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)
from playwright.async_api import Page

from app.page_collector.errors import PageUnavailableError
from app.page_collector.models import LayoutSnapshot, PageData

logger = logging.getLogger(__name__)

_EXTRACT_SCRIPT = (
    Path(__file__).with_name("extract_layout.js").read_text(encoding="utf-8")
)

DESKTOP_VIEWPORT = {"width": 1280, "height": 800}
MOBILE_VIEWPORT = {"width": 390, "height": 844}
NAVIGATION_TIMEOUT_MS = 30_000
# HTTP-коды, при которых страница считается недоступной для анализа.
_UNAVAILABLE_STATUS_CODES = {401, 402, 403, 404, 407, 408, 410, 451}


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PageUnavailableError(
            f"Некорректный URL: ожидается http(s)-ссылка, получено {url!r}."
        )
    return url


def _is_auth_wall(page: Page, status: int | None) -> bool:
    """Грубая эвристика страницы, требующей авторизации."""
    if status in {401, 403, 407}:
        return True
    path = (urlparse(page.url).path or "").lower()
    auth_path_markers = ("/login", "/signin", "/sign-in", "/auth", "/account/login")
    if any(marker in path for marker in auth_path_markers):
        return True
    return False


async def _extract_layout(page: Page) -> LayoutSnapshot:
    raw: dict[str, Any] = await page.evaluate(_EXTRACT_SCRIPT)
    return LayoutSnapshot.model_validate(raw)


async def _goto(page: Page, url: str) -> int | None:
    try:
        response = await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=NAVIGATION_TIMEOUT_MS,
        )
    except PlaywrightTimeoutError as exc:
        raise PageUnavailableError(
            f"Таймаут при загрузке страницы: {url}"
        ) from exc
    except PlaywrightError as exc:
        raise PageUnavailableError(
            f"Не удалось открыть страницу: {url}. Причина: {_short_playwright_reason(exc)}."
        ) from exc

    status = response.status if response is not None else None
    if status is not None and status in _UNAVAILABLE_STATUS_CODES:
        raise PageUnavailableError(
            f"Страница недоступна (HTTP {status}): {url}"
        )
    if status is not None and status >= 500:
        raise PageUnavailableError(
            f"Ошибка сервера при загрузке страницы (HTTP {status}): {url}"
        )
    if _is_auth_wall(page, status):
        raise PageUnavailableError(
            f"Страница требует авторизации или недоступна без входа: {url}"
        )
    return status


def _short_playwright_reason(exc: BaseException) -> str:
    """Короткое человекочитаемое описание ошибки Playwright без технического дампа."""
    text = str(exc).strip()
    lowered = text.lower()
    if "executable doesn't exist" in lowered or "playwright install" in lowered:
        return "браузер Playwright не установлен или недоступен"
    if "err_name_not_resolved" in lowered or "getaddrinfo" in lowered:
        return "домен не найден или сайт недоступен"
    if "err_connection" in lowered or "econnrefused" in lowered:
        return "не удалось установить соединение с сайтом"
    if "timeout" in lowered:
        return "таймаут при работе браузера"
    # Берём только первую строку, без рамок/длинного help-текста Playwright.
    first_line = text.splitlines()[0].strip() if text else "неизвестная ошибка Playwright"
    # Убираем префиксы вроде "Page.goto: net::ERR_..."
    if "net::" in first_line:
        return "сайт недоступен по указанному адресу"
    if len(first_line) > 180:
        return first_line[:177] + "..."
    return first_line


async def collect_page_data(url: str) -> PageData:
    """
    Собирает PageData для одного URL.

    Не переходит по внутренним ссылкам сайта и не делает скриншоты.
    """
    target_url = _validate_url(url)
    logger.info("Collecting page data for %s", target_url)

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    viewport=DESKTOP_VIEWPORT,
                    java_script_enabled=True,
                )
                page = await context.new_page()
                await _goto(page, target_url)

                # Дать отработать короткой отложенной отрисовке после DOMContentLoaded.
                try:
                    await page.wait_for_load_state(
                        "networkidle", timeout=5_000
                    )
                except PlaywrightTimeoutError:
                    logger.debug(
                        "networkidle wait timed out for %s; continuing with current DOM",
                        target_url,
                    )

                html = await page.content()
                visible_text = await page.evaluate(
                    "() => (document.body && document.body.innerText) || ''"
                )
                layout_desktop = await _extract_layout(page)

                await page.set_viewport_size(MOBILE_VIEWPORT)
                # Пересчёт layout после media-query; без ухода на другой URL.
                await page.wait_for_timeout(300)
                layout_mobile = await _extract_layout(page)

                final_url = page.url
            finally:
                await browser.close()
    except PageUnavailableError:
        raise
    except PlaywrightError as exc:
        logger.exception("Playwright error while collecting %s", target_url)
        raise PageUnavailableError(
            f"Не удалось собрать данные страницы: {target_url}. "
            f"Причина: {_short_playwright_reason(exc)}."
        ) from exc
    except Exception as exc:  # noqa: BLE001 — наружу только доменная ошибка сбора
        logger.exception("Unexpected error while collecting %s", target_url)
        raise PageUnavailableError(
            f"Неожиданная ошибка сбора данных страницы: {target_url}"
        ) from exc

    page_data = PageData(
        url=final_url,
        html=html,
        visible_text=visible_text,
        layout_desktop=layout_desktop,
        layout_mobile=layout_mobile,
    )
    logger.info(
        "Collected page data for %s (headings=%s, forms=%s, named_blocks=%s)",
        final_url,
        len(layout_desktop.headings),
        len(layout_desktop.forms),
        len(layout_desktop.named_blocks),
    )
    return page_data
