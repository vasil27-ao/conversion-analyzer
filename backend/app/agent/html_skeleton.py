"""
Компактный semantic HTML skeleton для LLM.

Убирает scripts/styles/служебную разметку, сохраняет структуру важных блоков,
формы, кнопки, ссылки, заголовки и значимые атрибуты.
"""

from __future__ import annotations

import re
from bs4 import BeautifulSoup, Comment, NavigableString, Tag

# Жёсткий потолок на всякий случай (после скелета обычно сильно меньше).
SKELETON_CHAR_LIMIT = 80_000
TEXT_NODE_LIMIT = 400
ATTR_VALUE_LIMIT = 180

# Корни поддеревьев, которые коллектор пометил как невидимые пользователю.
COLLECTOR_INVISIBLE_ATTR = "data-collector-invisible"

_REMOVE_TAGS = frozenset(
    {
        "script",
        "style",
        "noscript",
        "template",
        "svg",
        "canvas",
        "iframe",
        "object",
        "embed",
        "link",
        "meta",
        "source",
        "track",
    }
)

# Семантика / интерактив, которые нельзя «схлопывать».
_KEEP_TAGS = frozenset(
    {
        "html",
        "head",
        "body",
        "main",
        "header",
        "footer",
        "nav",
        "section",
        "article",
        "aside",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "p",
        "ul",
        "ol",
        "li",
        "a",
        "button",
        "form",
        "input",
        "textarea",
        "select",
        "option",
        "label",
        "img",
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "th",
        "td",
        "fieldset",
        "legend",
        "strong",
        "em",
        "b",
        "i",
        "small",
        "br",
        "hr",
        "blockquote",
        "figcaption",
        "figure",
        "summary",
        "details",
        "title",
    }
)

_ATTR_KEEP = frozenset(
    {
        "href",
        "src",
        "alt",
        "name",
        "type",
        "role",
        "placeholder",
        "required",
        "action",
        "method",
        "for",
        "title",
        "disabled",
        "checked",
        "selected",
        "value",
        "aria-label",
        "aria-labelledby",
        "aria-describedby",
        "aria-hidden",
        "aria-expanded",
        "aria-controls",
        "contenteditable",
    }
)

_SPACE_RE = re.compile(r"\s+")


def _clip(value: str, limit: int) -> str:
    text = _SPACE_RE.sub(" ", (value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _strip_comments(soup: BeautifulSoup) -> None:
    for comment in soup.find_all(string=lambda node: isinstance(node, Comment)):
        comment.extract()


def _remove_unwanted_tags(soup: BeautifulSoup) -> None:
    for tag_name in _REMOVE_TAGS:
        for node in soup.find_all(tag_name):
            node.decompose()
    # picture: оставляем img, оболочку убираем.
    for picture in soup.find_all("picture"):
        picture.unwrap()


def _sanitize_attributes(tag: Tag) -> None:
    allowed: dict[str, str] = {}
    for key, raw in list(tag.attrs.items()):
        key_l = str(key).lower()
        if key_l not in _ATTR_KEEP:
            continue
        if isinstance(raw, list):
            value = " ".join(str(part) for part in raw)
        else:
            value = str(raw)
        value = _clip(value, ATTR_VALUE_LIMIT)
        if not value and key_l not in {"required", "disabled", "checked", "selected"}:
            continue
        # boolean attrs
        if key_l in {"required", "disabled", "checked", "selected"}:
            allowed[key_l] = key_l
        else:
            allowed[key_l] = value
    tag.attrs = allowed


def _truncate_text_nodes(root: Tag) -> None:
    for node in root.descendants:
        if isinstance(node, NavigableString) and not isinstance(node, Comment):
            text = str(node)
            clipped = _clip(text, TEXT_NODE_LIMIT)
            if clipped != text:
                node.replace_with(clipped)


def _is_empty_wrapper(tag: Tag) -> bool:
    if tag.name in _KEEP_TAGS and tag.name not in {"div", "span"}:
        # для keep-тегов пустоту тоже можно чистить, но осторожнее с br/hr/img/input
        if tag.name in {"br", "hr", "img", "input"}:
            return False
        if tag.name in {"a", "button", "label", "option"} and tag.get_text(strip=True):
            return False
    has_meaningful_child = False
    for child in tag.children:
        if isinstance(child, NavigableString):
            if str(child).strip():
                has_meaningful_child = True
                break
        elif isinstance(child, Tag):
            has_meaningful_child = True
            break
    return not has_meaningful_child


def _unwrap_generic_wrappers(soup: BeautifulSoup, *, max_passes: int = 8) -> None:
    """Схлопывает бессмысленные div/span, сохраняя семантические теги."""
    for _ in range(max_passes):
        changed = False
        for tag in list(soup.find_all(["div", "span"])):
            if not isinstance(tag, Tag):
                continue
            _sanitize_attributes(tag)
            # если после sanitize остались полезные aria/role — оставляем как есть
            if tag.attrs:
                continue
            if _is_empty_wrapper(tag):
                tag.decompose()
                changed = True
                continue
            # один ребёнок-тег → unwrap
            child_tags = [c for c in tag.children if isinstance(c, Tag)]
            texts = [
                c for c in tag.children if isinstance(c, NavigableString) and str(c).strip()
            ]
            if len(child_tags) == 1 and not texts:
                tag.unwrap()
                changed = True
            elif not child_tags and texts:
                # оставить текст, убрать обёртку
                tag.unwrap()
                changed = True
        if not changed:
            break


def _hard_trim(html: str, limit: int) -> tuple[str, bool]:
    if len(html) <= limit:
        return html, False
    marker = (
        f"\n<!-- skeleton truncated for LLM input: limit={limit}, "
        f"original_skeleton_len={len(html)} -->\n"
    )
    budget = max(2, limit - len(marker))
    head = max(1, int(budget * 0.7))
    tail = budget - head
    return html[:head] + marker + html[-tail:], True


def strip_collector_invisible(html: str) -> str:
    """Убирает поддеревья, помеченные коллектором как невидимые пользователю."""
    if not html or COLLECTOR_INVISIBLE_ATTR not in html:
        return html
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select(f"[{COLLECTOR_INVISIBLE_ATTR}]"):
        tag.decompose()
    return str(soup)


def build_html_skeleton(html: str, *, limit: int = SKELETON_CHAR_LIMIT) -> tuple[str, bool]:
    """
    Строит компактный semantic HTML skeleton.

    Returns:
        (skeleton_html, was_limited) — was_limited=True, если пришлось ещё обрезать
        по символьному лимиту после очистки.
    """
    if not html or not html.strip():
        return "", False

    soup = BeautifulSoup(strip_collector_invisible(html), "html.parser")
    _strip_comments(soup)
    _remove_unwanted_tags(soup)

    # Удаляем из head всё, кроме title.
    head = soup.head
    if head is not None:
        for child in list(head.children):
            if isinstance(child, Tag) and child.name != "title":
                child.decompose()

    for tag in soup.find_all(True):
        if not isinstance(tag, Tag):
            continue
        if tag.name not in _KEEP_TAGS and tag.name not in {"div", "span"}:
            # неизвестный/служебный тег: сохраняем содержимое
            tag.unwrap()
            continue
        _sanitize_attributes(tag)

    _truncate_text_nodes(soup)
    _unwrap_generic_wrappers(soup)

    # Убрать совсем пустые семантические контейнеры без атрибутов.
    for tag in list(soup.find_all(_KEEP_TAGS)):
        if (
            isinstance(tag, Tag)
            and tag.name
            in {"section", "article", "aside", "nav", "header", "footer", "main", "div", "span", "p", "li"}
            and not tag.attrs
            and _is_empty_wrapper(tag)
        ):
            tag.decompose()

    body = soup.body
    if body is not None:
        rendered = body.decode_contents()
        title = soup.title.get_text(strip=True) if soup.title else ""
        if title:
            rendered = f"<title>{_clip(title, 200)}</title>\n{rendered}"
    else:
        rendered = str(soup)

    rendered = _SPACE_RE.sub(" ", rendered).strip()
    # чуть восстановить переносы между блоками для читаемости
    for token in (
        "</p>",
        "</h1>",
        "</h2>",
        "</h3>",
        "</h4>",
        "</h5>",
        "</h6>",
        "</li>",
        "</form>",
        "</section>",
        "</article>",
        "</header>",
        "</footer>",
        "</nav>",
        "</main>",
    ):
        rendered = rendered.replace(token, token + "\n")

    trimmed, limited = _hard_trim(rendered, limit)
    return trimmed, limited


def skeleton_stats(original_html: str, skeleton_html: str) -> dict[str, int]:
    return {
        "original_len": len(original_html or ""),
        "skeleton_len": len(skeleton_html or ""),
        "saved_chars": max(0, len(original_html or "") - len(skeleton_html or "")),
    }
