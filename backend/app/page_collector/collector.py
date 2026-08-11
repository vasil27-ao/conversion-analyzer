"""
Сбор данных страницы через Playwright.

Один URL → рендер → HTML / видимый текст / layout desktop и mobile.
Скриншоты не создаются, на другие страницы сайта переходов нет.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import urlparse

from playwright.async_api import (
    Browser,
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
# Сколько ждать авто-прохождения antibot-challenge (Ozon FAB и аналоги).
CHALLENGE_WAIT_MS = 25_000
# HTTP-коды, при которых страница считается недоступной для анализа.
# 403 обрабатывается отдельно: часто это antibot challenge, а не финальный отказ.
_UNAVAILABLE_STATUS_CODES = {401, 402, 404, 407, 408, 410, 451}
_CHALLENGE_TEXT_MARKERS = (
    "доступ ограничен",
    "нет соединения",
    "выключите vpn",
    "fab_chlg",
    "antibot challenge",
)


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PageUnavailableError(
            f"Некорректный URL: ожидается http(s)-ссылка, получено {url!r}."
        )
    return url


def _is_auth_wall(page: Page, status: int | None) -> bool:
    """Грубая эвристика страницы, требующей авторизации."""
    if status in {401, 407}:
        return True
    path = (urlparse(page.url).path or "").lower()
    auth_path_markers = ("/login", "/signin", "/sign-in", "/auth", "/account/login")
    if any(marker in path for marker in auth_path_markers):
        return True
    return False


async def _page_visible_text(page: Page) -> str:
    return await page.evaluate(
        "() => (document.body && document.body.innerText) || ''"
    )


async def _is_challenge_page(page: Page) -> bool:
    """Страница antibot/FAB challenge, которую ещё нельзя считать итогом загрузки."""
    title = (await page.title()).lower()
    text = (await _page_visible_text(page)).lower()
    if "antibot" in title:
        return True
    return any(marker in text for marker in _CHALLENGE_TEXT_MARKERS)


async def _wait_out_challenge(page: Page) -> None:
    """Ждёт, пока antibot JS завершит challenge (или истечёт таймаут)."""
    deadline = time.perf_counter() + CHALLENGE_WAIT_MS / 1000
    reloaded = False
    while time.perf_counter() < deadline:
        if not await _is_challenge_page(page):
            return
        # Иногда FAB просит «Обновить страницу» — один мягкий reload помогает.
        remaining_ms = (deadline - time.perf_counter()) * 1000
        if not reloaded and remaining_ms < CHALLENGE_WAIT_MS * 0.55:
            reloaded = True
            try:
                await page.reload(wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
            except PlaywrightError:
                logger.debug("Challenge reload failed; continuing wait", exc_info=True)
        await page.wait_for_timeout(500)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _chromium_browser_executable(playwright: Any) -> str:
    """
    Полный Chromium (chrome), не chrome-headless-shell.

    Headless shell чаще режется antibot; для CDP нужен обычный chrome.
    """
    # В новых Playwright executable_path может указывать на headless shell.
    os.environ.setdefault("PLAYWRIGHT_CHROMIUM_USE_HEADLESS_SHELL", "0")
    exe = Path(playwright.chromium.executable_path)
    if "headless" not in exe.name.lower():
        return str(exe)

    search_roots = [exe.parent, exe.parent.parent]
    for root in search_roots:
        for name in ("chrome", "chrome.exe", "chromium", "chromium.exe"):
            candidate = root / name
            if candidate.is_file():
                return str(candidate)
        for candidate in root.rglob("chrome"):
            if candidate.is_file() and "headless" not in candidate.name.lower():
                return str(candidate)
        for candidate in root.rglob("chrome.exe"):
            if candidate.is_file():
                return str(candidate)
    return str(exe)


@asynccontextmanager
async def _connect_chromium_over_cdp(playwright: Any) -> AsyncIterator[Browser]:
    """
    Запускает Chromium вне Playwright launch и подключается по CDP.

    Playwright.chromium.launch() выставляет automation-флаги, из-за которых
    сайты вроде Ozon (FAB) отвечают HTTP 403 и не пропускают challenge.
    Голый Chromium + connect_over_cdp challenge проходит.
    """
    port = _free_port()
    # ignore_cleanup_errors: Chromium может ещё держать файлы профиля на Linux.
    profile = tempfile.TemporaryDirectory(
        prefix="pw-cdp-",
        ignore_cleanup_errors=True,
    )
    exe = _chromium_browser_executable(playwright)
    logger.info("Launching Chromium over CDP executable=%s", exe)
    cmd = [
        exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile.name}",
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        "--headless=new",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        f"--window-size={DESKTOP_VIEWPORT['width']},{DESKTOP_VIEWPORT['height']}",
        "about:blank",
    ]
    proxy_server = (os.environ.get("COLLECTOR_PROXY_SERVER") or "").strip()
    if proxy_server:
        cmd.insert(-1, f"--proxy-server={proxy_server}")
        logger.info("Collector Chromium uses COLLECTOR_PROXY_SERVER")
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    browser: Browser | None = None
    last_error: BaseException | None = None
    try:
        for _ in range(40):
            try:
                browser = await playwright.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{port}"
                )
                break
            except Exception as exc:  # noqa: BLE001 — ждём готовности порта
                last_error = exc
                await asyncio.sleep(0.25)
        if browser is None:
            raise PageUnavailableError(
                "Не удалось запустить браузер для сбора страницы."
            ) from last_error
        try:
            yield browser
        finally:
            await browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()
            try:
                proc.wait(timeout=3)
            except Exception:  # noqa: BLE001
                pass
        profile.cleanup()


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

    # Ozon FAB и похожие antibot: первый ответ часто 403 + challenge page,
    # затем JS догружает контент. Нельзя сразу трактовать 403 как отказ.
    if status == 403 or await _is_challenge_page(page):
        await _wait_out_challenge(page)
        if await _is_challenge_page(page):
            title = await page.title()
            text_preview = (await _page_visible_text(page))[:240]
            logger.warning(
                "Antibot challenge unresolved url=%s http=%s title=%r text=%r",
                url,
                status,
                title,
                text_preview,
            )
            text_low = text_preview.lower()
            if any(
                marker in text_low
                for marker in ("нет соединения", "выключите vpn", "fab_chlg")
            ):
                raise PageUnavailableError(
                    "Сайт ограничил доступ к странице (защита от ботов). "
                    f"Попробуйте другую ссылку или повторите позже: {url}"
                )
            raise PageUnavailableError(
                f"Страница недоступна (HTTP {status or 403}): {url}"
            )
        # Challenge пройден — исходный 403 больше не считаем финальным статусом.
        status = None

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
    collect_started = time.perf_counter()
    page_load_s: float | None = None
    extract_s: float | None = None

    try:
        async with async_playwright() as playwright:
            async with _connect_chromium_over_cdp(playwright) as browser:
                context = await browser.new_context(
                    viewport=DESKTOP_VIEWPORT,
                    java_script_enabled=True,
                    locale="ru-RU",
                )
                page = await context.new_page()
                load_started = time.perf_counter()
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
                page_load_s = time.perf_counter() - load_started
                logger.info(
                    "Timing page_load url=%s page_load_s=%.3f",
                    target_url,
                    page_load_s,
                )

                extract_started = time.perf_counter()
                html = await page.content()
                visible_text = await page.evaluate(
                    "() => (document.body && document.body.innerText) || ''"
                )
                desktop_started = time.perf_counter()
                layout_desktop = await _extract_layout(page)
                desktop_layout_s = time.perf_counter() - desktop_started
                logger.info(
                    "Timing desktop_layout url=%s desktop_layout_s=%.3f",
                    target_url,
                    desktop_layout_s,
                )

                await page.set_viewport_size(MOBILE_VIEWPORT)
                # Пересчёт layout после media-query; без ухода на другой URL.
                await page.wait_for_timeout(300)
                mobile_started = time.perf_counter()
                layout_mobile = await _extract_layout(page)
                mobile_layout_s = time.perf_counter() - mobile_started
                logger.info(
                    "Timing mobile_layout url=%s mobile_layout_s=%.3f",
                    target_url,
                    mobile_layout_s,
                )
                extract_s = time.perf_counter() - extract_started

                final_url = page.url
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
    collect_total_s = time.perf_counter() - collect_started
    logger.info(
        "Collected page data for %s (headings=%s, forms=%s, named_blocks=%s)",
        final_url,
        len(layout_desktop.headings),
        len(layout_desktop.forms),
        len(layout_desktop.named_blocks),
    )
    logger.info(
        "Timing collect url=%s page_load_s=%.3f extract_s=%.3f collect_total_s=%.3f",
        final_url,
        page_load_s if page_load_s is not None else -1.0,
        extract_s if extract_s is not None else -1.0,
        collect_total_s,
    )
    return page_data
