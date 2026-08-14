"""Тесты semantic HTML skeleton."""

from __future__ import annotations

from app.agent.common import build_page_payload, prepare_html_for_llm, truncate_html_for_llm
from app.agent.html_skeleton import build_html_skeleton
from app.page_collector.models import LayoutSnapshot, PageData, ViewportSize
from pydantic import HttpUrl


SAMPLE_HTML = """
<html>
<head>
  <title>Demo landing</title>
  <script>window.TRACK=1;</script>
  <style>.x{color:red}</style>
  <meta charset="utf-8"/>
</head>
<body>
  <header><h1>Сервис ремонта</h1></header>
  <main>
    <section>
      <h2>Оффер</h2>
      <p>Считаем стоимость за 5 минут</p>
      <a href="/order" class="btn huge" data-analytics="cta1">Получить расчёт</a>
      <button type="button" aria-label="Открыть чат">Чат</button>
    </section>
    <form action="/submit" method="post">
      <label for="phone">Телефон</label>
      <input id="phone" name="phone" type="tel" required placeholder="+7"/>
      <textarea name="comment" class="big"> </textarea>
      <button type="submit">Отправить</button>
    </form>
    <div><div><span></span></div></div>
    <script>alert(1)</script>
  </main>
  <footer><p>Контакты: 8-800</p></footer>
</body>
</html>
"""


def test_skeleton_strips_scripts_styles_and_keeps_semantics():
    skeleton, limited = build_html_skeleton(SAMPLE_HTML)
    assert limited is False
    assert "<script" not in skeleton.lower()
    assert "<style" not in skeleton.lower()
    assert "window.TRACK" not in skeleton
    assert "<h1>Сервис ремонта</h1>" in skeleton
    assert 'href="/order"' in skeleton
    assert 'name="phone"' in skeleton
    assert 'type="tel"' in skeleton
    assert "required" in skeleton
    assert "Получить расчёт" in skeleton
    assert "data-analytics" not in skeleton
    assert "class=" not in skeleton


def test_prepare_html_default_is_skeleton_and_smaller_than_head_tail_on_noisy_page():
    noisy = SAMPLE_HTML + ("<script>var x=" + ("1" * 50_000) + ";</script>")
    skeleton, reduced, mode = prepare_html_for_llm(noisy, mode="skeleton")
    head_tail, _, head_mode = prepare_html_for_llm(noisy, mode="head_tail")
    assert mode.startswith("skeleton")
    assert head_mode == "head_tail"
    assert reduced is True
    assert len(skeleton) < len(head_tail)
    assert "<script" not in skeleton.lower()


def test_build_page_payload_keeps_visible_text_and_layout_full():
    page = PageData(
        url=HttpUrl("https://example.com/x"),
        html=SAMPLE_HTML + ("<script>" + ("x" * 10_000) + "</script>"),
        visible_text="FULL TEXT MIDDLE AND FOOTER",
        layout_desktop=LayoutSnapshot(viewport=ViewportSize(width=1280, height=800)),
        layout_mobile=LayoutSnapshot(viewport=ViewportSize(width=390, height=844)),
    )
    payload = build_page_payload(page)
    assert payload["visible_text"] == "FULL TEXT MIDDLE AND FOOTER"
    assert payload["layout_desktop"]["viewport"]["width"] == 1280
    assert payload["layout_mobile"]["viewport"]["width"] == 390
    assert payload["html_mode"].startswith("skeleton")
    assert "<script" not in payload["html"].lower()
    assert "window.TRACK" not in payload["html"]


def test_build_page_payload_drops_unused_layout_css_and_caps_links():
    from app.agent.common import LAYOUT_LINK_CAP
    from app.page_collector.models import HeadingItem, LinkItem

    links = [
        LinkItem(
            tag="a",
            text=f"link-{i}",
            href=f"https://example.com/{i}",
            x=1.234,
            y=2.345,
            width=10.0,
            height=10.0,
            page_x=1.234,
            page_y=2.345,
            visible=True,
            in_viewport=i < 3,
            color="rgb(0,0,0)",
            background_color="rgb(255,255,255)",
            display="block",
            opacity="1",
        )
        for i in range(LAYOUT_LINK_CAP + 20)
    ]
    page = PageData(
        url=HttpUrl("https://example.com/x"),
        html=SAMPLE_HTML,
        visible_text="FULL TEXT MIDDLE AND FOOTER",
        layout_desktop=LayoutSnapshot(
            viewport=ViewportSize(width=1280, height=800),
            headings=[
                HeadingItem(
                    tag="h1",
                    text="Offer",
                    level=1,
                    x=0,
                    y=0,
                    width=100,
                    height=40,
                    page_x=0,
                    page_y=0,
                    visible=True,
                    in_viewport=True,
                    color="#111",
                )
            ],
            links=links,
        ),
        layout_mobile=LayoutSnapshot(viewport=ViewportSize(width=390, height=844)),
    )
    payload = build_page_payload(page)
    heading = payload["layout_desktop"]["headings"][0]
    assert heading["text"] == "Offer"
    assert "color" not in heading
    assert len(payload["layout_desktop"]["links"]) == LAYOUT_LINK_CAP
    assert payload["visible_text"] == "FULL TEXT MIDDLE AND FOOTER"


def test_truncate_html_for_llm_still_keeps_head_and_tail():
    huge = "HEAD" + ("m" * 200_000) + "TAIL"
    out, truncated = truncate_html_for_llm(huge, limit=1000)
    assert truncated is True
    assert out.startswith("HEAD")
    assert out.endswith("TAIL")
