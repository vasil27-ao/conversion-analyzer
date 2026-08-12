"""
Общие хелперы для LLM-клиентов агента (промпт, payload, разбор JSON, тексты ошибок).
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.agent.errors import AgentApiError, AgentConfigError, AgentInvalidResponseError
from app.agent.schemas import LlmAgentResult
from app.page_collector.models import PageData

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT_PATH = (
    Path(__file__).resolve().parent / "prompts" / "system_prompt.md"
)
HTML_CHAR_LIMIT = 120_000
HTML_HEAD_RATIO = 0.55

# Для сравнительных прогонов head_tail vs skeleton без смены AgentClient API.
html_mode_override: ContextVar[str | None] = ContextVar(
    "html_mode_override",
    default=None,
)

def user_facing_agent_api_error(code: object, status: object) -> str:
    """Сообщение для клиента без привязки к конкретному LLM-провайдеру."""
    status_text = str(status or "").upper()
    try:
        code_int = int(code) if code is not None else None
    except (TypeError, ValueError):
        code_int = None

    if code_int == 429 or status_text in {"RESOURCE_EXHAUSTED", "TOO_MANY_REQUESTS"}:
        return (
            "Сейчас слишком много запросов к сервису анализа. "
            "Подождите 1–2 минуты и попробуйте снова."
        )
    if code_int in {401, 403} or status_text in {
        "UNAUTHENTICATED",
        "PERMISSION_DENIED",
    }:
        return "Сервис анализа временно недоступен. Попробуйте позже."
    if code_int in {500, 502, 503, 504} or status_text in {
        "UNAVAILABLE",
        "INTERNAL",
        "DEADLINE_EXCEEDED",
    }:
        return "Сервис анализа временно недоступен. Попробуйте позже."
    return "Не удалось выполнить анализ страницы. Попробуйте ещё раз."


def is_transient_agent_error(exc: BaseException) -> bool:
    """Ошибки, при которых имеет смысл сразу переключиться на запасной LLM."""
    if isinstance(exc, AgentInvalidResponseError):
        return True
    if not isinstance(exc, AgentApiError):
        return False
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "временно недоступен",
            "слишком много запросов",
            "попробуйте позже",
            "попробуйте ещё раз",
            "попробуйте еще раз",
        )
    )


def load_system_prompt(path: Path | None = None) -> str:
    prompt_path = path or DEFAULT_SYSTEM_PROMPT_PATH
    text = prompt_path.read_text(encoding="utf-8").strip()
    if not text:
        raise AgentConfigError(f"Системный промпт пуст: {prompt_path}")
    return text


def truncate_html_for_llm(html: str, limit: int = HTML_CHAR_LIMIT) -> tuple[str, bool]:
    """Обрезает HTML до limit, сохраняя начало и конец страницы (legacy / fallback)."""
    if len(html) <= limit:
        return html, False

    marker = (
        "\n<!-- HTML middle omitted for LLM input: kept page head + tail "
        f"(limit={limit}, original_len={len(html)}) -->\n"
    )
    budget = limit - len(marker)
    if budget < 2:
        return html[:limit], True

    head_len = max(1, int(budget * HTML_HEAD_RATIO))
    tail_len = budget - head_len
    if tail_len < 1:
        head_len = budget - 1
        tail_len = 1

    truncated = html[:head_len] + marker + html[-tail_len:]
    return truncated, True


def prepare_html_for_llm(
    html: str,
    *,
    mode: str | None = None,
) -> tuple[str, bool, str]:
    """
    Готовит HTML для LLM.

    mode:
      - "skeleton" (default / production) — semantic skeleton;
      - "head_tail" — legacy head+tail truncation (для сравнения).
    """
    from app.agent.html_skeleton import build_html_skeleton, strip_collector_invisible

    selected = (mode or html_mode_override.get() or "skeleton").strip().lower()
    if not html or not html.strip():
        return "", False, "raw"

    # Невидимые (помеченные коллектором) узлы не должны попадать в LLM как «контент».
    html = strip_collector_invisible(html)

    if selected in {"head_tail", "head+tail", "truncate"}:
        truncated, was_truncated = truncate_html_for_llm(html)
        return truncated, was_truncated, "head_tail"

    skeleton, hard_trimmed = build_html_skeleton(html)
    if not skeleton.strip():
        truncated, was_truncated = truncate_html_for_llm(html)
        return truncated, was_truncated, "raw"

    was_reduced = hard_trimmed or len(skeleton) < len(html)
    out_mode = "skeleton+trim" if hard_trimmed else "skeleton"
    return skeleton, was_reduced, out_mode


def build_page_payload(
    page_data: PageData,
    *,
    html_mode: str | None = None,
) -> dict[str, Any]:
    """Сериализует PageData для user-сообщения без скриншотов и без ключей."""
    payload = page_data.model_dump(mode="json")
    html = payload.get("html") or ""
    prepared_html, was_reduced, mode = prepare_html_for_llm(html, mode=html_mode)
    payload["html"] = prepared_html
    # Совместимость с промптом: флаг означает «HTML уплотнён для лимита запроса».
    payload["html_truncated"] = was_reduced
    payload["html_mode"] = mode
    if was_reduced or mode.startswith("skeleton") or mode == "head_tail":
        logger.warning(
            "Page HTML prepared for LLM: mode=%s url=%s original_len=%s kept_len=%s",
            mode,
            page_data.url,
            len(html),
            len(prepared_html),
        )
    return payload


def build_analysis_user_message(
    page_data: PageData,
    *,
    html_mode: str | None = None,
) -> str:
    user_payload = build_page_payload(page_data, html_mode=html_mode)
    return (
        "Проанализируй лендинг строго по системному промпту и верни только "
        "JSON по схеме LlmAgentResult (без numeric overall/block score).\n\n"
        f"Данные страницы (JSON):\n{json.dumps(user_payload, ensure_ascii=False)}"
    )


def parse_llm_agent_result_from_text(text: str, *, provider_label: str) -> LlmAgentResult:
    if not text or not str(text).strip():
        raise AgentInvalidResponseError(f"Пустой ответ {provider_label}.")

    cleaned = str(text).strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AgentInvalidResponseError(
            f"Ответ {provider_label} не является валидным JSON."
        ) from exc

    try:
        return LlmAgentResult.model_validate(data)
    except ValidationError as exc:
        raise AgentInvalidResponseError(
            f"Ответ {provider_label} не соответствует LlmAgentResult: {exc}"
        ) from exc
