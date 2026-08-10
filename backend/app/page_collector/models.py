"""
Схема данных страницы, которые backend собирает перед вызовом агента.

По решению PM (2026-08-10) сервис не создаёт и не анализирует скриншоты.
Данные — из отрендеренной страницы (Playwright): HTML/DOM, видимый текст,
layout desktop/mobile. Изображения учитываются как факт наличия + контекст
блока; OCR текста на картинках не выполняется.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


class ViewportSize(BaseModel):
    width: int
    height: int


class ElementGeometry(BaseModel):
    """Геометрия и видимость элемента после рендера."""

    tag: str
    text: str = ""
    x: float
    y: float
    width: float
    height: float
    page_x: float
    page_y: float
    visible: bool
    in_viewport: bool
    display: str = ""
    position: str = ""
    z_index: str = ""
    font_size: str = ""
    font_weight: str = ""
    color: str = ""
    background_color: str = ""
    opacity: str = ""


class HeadingItem(ElementGeometry):
    level: int


class CtaItem(ElementGeometry):
    href: Optional[str] = None
    role: Optional[str] = None
    input_type: Optional[str] = None


class LinkItem(ElementGeometry):
    href: str


class FormFieldItem(ElementGeometry):
    name: Optional[str] = None
    input_type: Optional[str] = None
    label: Optional[str] = None
    placeholder: Optional[str] = None
    required: bool = False


class FormItem(ElementGeometry):
    action: Optional[str] = None
    method: Optional[str] = None
    fields: List[FormFieldItem] = Field(default_factory=list)


class ImageItem(ElementGeometry):
    src: Optional[str] = None
    alt: str = ""
    # Ближайший заголовок / подпись секции вокруг изображения.
    block_context: Optional[str] = None
    # Если изображение внутри явно названного блока (например «Отзывы»).
    named_block: Optional[str] = None


NamedBlockKind = Literal[
    "reviews",
    "works",
    "cases",
    "portfolio",
    "guarantees",
    "other",
]


class NamedBlockItem(ElementGeometry):
    """Явно обозначенный смысловой блок страницы (по заголовку секции)."""

    name: str
    kind: NamedBlockKind
    has_images: bool
    image_count: int
    text_preview: str = ""


class LayoutSnapshot(BaseModel):
    """Структурированный снимок layout для одного viewport (desktop или mobile)."""

    viewport: ViewportSize
    headings: List[HeadingItem] = Field(default_factory=list)
    ctas: List[CtaItem] = Field(default_factory=list)
    links: List[LinkItem] = Field(default_factory=list)
    forms: List[FormItem] = Field(default_factory=list)
    images: List[ImageItem] = Field(default_factory=list)
    named_blocks: List[NamedBlockItem] = Field(default_factory=list)


class PageData(BaseModel):
    url: HttpUrl
    html: str
    visible_text: str
    layout_desktop: LayoutSnapshot
    layout_mobile: LayoutSnapshot
