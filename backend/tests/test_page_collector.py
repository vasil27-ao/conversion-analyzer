"""Минимальные тесты сбора данных страницы (Playwright)."""

from __future__ import annotations

import asyncio
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from app.page_collector.collector import collect_page_data
from app.page_collector.errors import PageUnavailableError

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def local_site_url() -> str:
    handler = partial(SimpleHTTPRequestHandler, directory=str(FIXTURES_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}/sample_landing.html"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_collect_page_data_extracts_structure_and_named_blocks(local_site_url: str):
    page_data = asyncio.run(collect_page_data(local_site_url))

    assert str(page_data.url).startswith("http://127.0.0.1:")
    assert "Сервис расчёта стоимости ремонта" in page_data.visible_text
    assert "<h1>" in page_data.html

    desktop = page_data.layout_desktop
    mobile = page_data.layout_mobile

    assert desktop.viewport.width == 1280
    assert mobile.viewport.width == 390

    heading_texts = [item.text for item in desktop.headings]
    assert "Сервис расчёта стоимости ремонта" in heading_texts
    assert "Отзывы клиентов" in heading_texts
    assert "Наши работы" in heading_texts

    assert any("Получить расчёт" in cta.text for cta in desktop.ctas)
    assert len(desktop.forms) == 1
    assert {field.name for field in desktop.forms[0].fields} >= {"name", "phone"}

    reviews = next(
        block for block in desktop.named_blocks if block.kind == "reviews"
    )
    assert reviews.has_images is True
    assert reviews.image_count >= 2

    works = next(block for block in desktop.named_blocks if block.kind == "works")
    assert works.has_images is True
    assert works.image_count >= 1

    review_images = [
        image for image in desktop.images if image.named_block == "Отзывы клиентов"
    ]
    assert len(review_images) >= 2
    assert all(image.block_context for image in review_images)

    # На mobile desktop-CTA скрыт media-query, mobile-CTA видим.
    assert any("Заявка с телефона" in cta.text for cta in mobile.ctas if cta.visible)
    assert not any(
        "Получить расчёт" in cta.text and cta.visible for cta in mobile.ctas
    )


def test_collect_page_data_raises_on_http_404(local_site_url: str):
    missing_url = local_site_url.rsplit("/", 1)[0] + "/missing-page.html"
    with pytest.raises(PageUnavailableError, match="HTTP 404"):
        asyncio.run(collect_page_data(missing_url))


def test_collect_page_data_raises_on_invalid_url():
    with pytest.raises(PageUnavailableError, match="Некорректный URL"):
        asyncio.run(collect_page_data("not-a-url"))


def test_collect_page_data_raises_on_connection_error():
    with pytest.raises(PageUnavailableError):
        asyncio.run(collect_page_data("http://127.0.0.1:1/"))


def test_collect_page_data_detects_soft_named_blocks_without_h_tags(local_site_url: str):
    soft_url = local_site_url.rsplit("/", 1)[0] + "/soft_headings_landing.html"
    page_data = asyncio.run(collect_page_data(soft_url))

    assert page_data.layout_desktop.headings == []

    works = next(
        block
        for block in page_data.layout_desktop.named_blocks
        if block.kind == "works"
    )
    assert works.name == "Наши работы"
    assert works.has_images is True
    assert works.image_count >= 2

    reviews = next(
        block
        for block in page_data.layout_desktop.named_blocks
        if block.kind == "reviews"
    )
    assert "Отзывы" in reviews.name
    assert reviews.has_images is True
    assert reviews.image_count >= 2

    assert any(
        image.named_block == "Наши работы" for image in page_data.layout_desktop.images
    )
    assert any(
        image.named_block and "Отзывы" in image.named_block
        for image in page_data.layout_desktop.images
    )


def test_collect_excludes_hidden_and_collapsed_reviews_from_visible_data(local_site_url: str):
    hidden_url = local_site_url.rsplit("/", 1)[0] + "/hidden_reviews_landing.html"
    page_data = asyncio.run(collect_page_data(hidden_url))

    text = page_data.visible_text.lower()
    assert "visible offer" in text
    assert "contacts visible" in text
    assert "reviews for women's strider" not in text
    assert "secret review text" not in text
    assert "hidden attribute reviews" not in text
    assert "aria hidden reviews" not in text

    # В сыром HTML скрытое может остаться (с маркером коллектора) — это ок.
    assert "Reviews for Women's Strider" in page_data.html
    assert "data-collector-invisible" in page_data.html

    from app.agent.common import prepare_html_for_llm

    llm_html, _, _ = prepare_html_for_llm(page_data.html)
    assert "Reviews for Women's Strider" not in llm_html
    assert "Secret review text" not in llm_html

    review_blocks = [
        b for b in page_data.layout_desktop.named_blocks if b.kind == "reviews"
    ]
    assert review_blocks == []
    assert not any(
        "review" in (h.text or "").lower() for h in page_data.layout_desktop.headings
    )