"""
Общие хелперы для LLM-клиентов агента (промпт, payload, разбор JSON, тексты ошибок).
"""

from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.agent.errors import AgentApiError, AgentConfigError, AgentInvalidResponseError
from app.agent.schemas import LlmAgentResult
from app.page_collector.models import PageData

RETRYABLE_HTTP_CODES = frozenset({429, 503})
TRANSIENT_HTTP_CODES = frozenset({429, 500, 502, 503, 504})
NON_FAILOVER_HTTP_CODES = frozenset({401, 403})

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT_PATH = (
    Path(__file__).resolve().parent / "prompts" / "system_prompt.md"
)
HTML_CHAR_LIMIT = 120_000
HTML_HEAD_RATIO = 0.55
LAYOUT_LINK_CAP = 80
LAYOUT_DROP_KEYS = frozenset({"display", "color", "background_color", "opacity"})
LAYOUT_ROUND_KEYS = frozenset({"x", "y", "width", "height", "page_x", "page_y"})

_PROMPT_SCALE_DUPLICATE_RE = re.compile(
    r"Общий смысл уровней \(ориентир.*?(?=\n### Блок 1)",
    re.S,
)
_PROMPT_DATA_LINE_RE = re.compile(
    r"^Данные:.*(?:\n(?![-\n#*\d]).+)*\n?",
    re.M,
)
_PROMPT_CHECKED_LINE_RE = re.compile(
    r"^Проверяется:.*(?:\n(?![-\n#*\d]).+)*\n?",
    re.M,
)
_PROMPT_JSON_EXAMPLE_RE = re.compile(r"```json.*?```", re.S)

_COMPACT_ROLE_AND_RULES = """## 1. Роль
Ты — агент-аналитик конверсионности лендингов. Проверь одну страницу по 20 критериям (раздел 4) и верни только JSON `LlmAgentResult`. Не свободный текст. Один вызов: критерии, `what_is_wrong`/`why_it_matters` блоков, problems, backlog, `overall.summary`. Numeric score считает backend.

## 2. Вход
JSON: `url`; `html` — semantic skeleton без script/style и без невидимых узлов; `visible_text` — только реально видимый текст; `layout_desktop`/`layout_mobile` — только visible-элементы (координаты, размеры, visible, in_viewport). Скриншотов нет — визуальные критерии только по layout.
`html_truncated` / `html_mode=skeleton` значит HTML уплотнён; visible_text и layout полные по видимому контенту. Это не повод для N/A и не снимает проверку низа страницы (футер, отзывы, гарантии, кейсы, повторные CTA).
DOM ≠ видимость. «Пользователь видит X» только по `visible_text` и layout с `visible=true`. Скрытые заголовки вроде «Reviews for …» не описывай как видимый блок. Нет видимых отзывов — фиксируй отсутствие соцдоказательства.

## 3. Правила
1. Все 20 критериев без пропусков. Score только 0 / 1 / 2 / `"N/A"`.
2. Только этот URL. Факт ссылки на другой раздел можно отметить, содержимое той страницы — нет.
3. Не выдумывай элементы, которых нет во входе.
4. Перед `0` за отсутствие проверь всю страницу: низ, футер, галереи, отзывы, портфолио, повторные CTA.
5. Явная ссылка/кнопка на релевантный раздел («Отзывы», «Работы», «Гарантии») = обычно `1`, без оценки той страницы.
6. N/A vs 0: сначала применимость и ожидаемость элемента для этого лендинга (оффер и риски пользователя, не ярлык B2B/B2C). Если ожидается, но нет — `0`. N/A только если критерий объективно неприменим или вход явно пометил неполноту. Не переклассифицируй страницу в «документацию/заглушку» ради N/A. При сомнении — `0`.
7. `justification`: наблюдение из visible_text/html/layout + почему этот уровень, не соседний.
8. `recommendation`: строка при 0/1, иначе `null`.
9. Можно объяснять потенциальное влияние CRO-паттернов; нельзя выдумывать метрики сайта и обещать рост конверсии.
10. Где указано — сравни desktop и mobile (1.3, 4.3, 5.1, 5.2).
11. Не ставь numeric overall/block score.

## 4. Чек-лист
Конкретные 0/1/2/N/A — ниже. Шкала: 2 — функция без потерь; 1 — есть недостаток; 0 — ожидаемый элемент не выполнен.
"""


_SHORT_JSON_SCHEMA = (
    "Верни только JSON объекта `LlmAgentResult` без markdown:\n"
    '{"overall":{"summary":"2-3 предложения"},'
    '"blocks":[{"block_id":"1","block_name":"Первый экран и оффер",'
    '"what_is_wrong":"...","why_it_matters":"...",'
    '"criteria":[{"id":"1.1","score":0,"justification":"наблюдение",'
    '"recommendation":"действие или null"}]}],'
    '"problems":[{"description":"...","location":"..."}],'
    '"backlog":[{"task":"...","zone":"...","priority":"высокий",'
    '"expected_effect":"..."}]}\n'
    "Ровно 6 блоков (`block_id` 1–6) и 20 `criteria`; "
    "`recommendation` — строка при 0/1, иначе `null`. "
    "Без numeric `overall.score`/`level` и без `blocks[].score`."
)

_SHORT_SELF_CHECK = """## 6. Самопроверка
1. 6 блоков и 20 критериев, все id из раздела 4, без пропусков/дублей.
2. У блоков заполнены `what_is_wrong` и `why_it_matters`.
3. `score` только 0/1/2/`N/A`; `recommendation` строка при 0/1, иначе null.
4. Только переданный URL и реально найденные элементы; нет выдуманных блоков.
5. Перед `0` «за отсутствие» — вся страница и явные ссылки (правила 5–6).
6. `justification` с наблюдением из visible_text/html/layout; при `0` за отсутствие — почему элемент ожидался.
7. Нет массового N/A через переклассификацию страницы.
8. Фото бизнеса/интерьера не считай кейсами (критерий 3.2).
9. `problems`/`backlog` только из оценок 0/1; backlog высокий→средний→низкий.
10. Нет numeric overall/block score; summary — 2–3 предложения без уровня и метрик.
11. Ответ — валидный JSON без текста вокруг.
"""


# Для сравнительных прогонов head_tail vs skeleton без смены AgentClient API.
html_mode_override: ContextVar[str | None] = ContextVar(
    "html_mode_override",
    default=None,
)

def coerce_http_status_code(code: object) -> int | None:
    try:
        if code is None or isinstance(code, bool):
            return None
        return int(code)
    except (TypeError, ValueError):
        return None


def inferred_http_status_code(code: object, status: object) -> int | None:
    """HTTP-код из ответа провайдера или из текстового status."""
    code_int = coerce_http_status_code(code)
    if code_int is not None:
        return code_int
    status_text = str(status or "").upper()
    if status_text in {"RESOURCE_EXHAUSTED", "TOO_MANY_REQUESTS"}:
        return 429
    if status_text in {"UNAVAILABLE"}:
        return 503
    if status_text in {"INTERNAL"}:
        return 500
    if status_text in {"DEADLINE_EXCEEDED"}:
        return 504
    return None


def user_facing_agent_api_error(code: object, status: object) -> str:
    """Сообщение для клиента без привязки к конкретному LLM-провайдеру."""
    status_text = str(status or "").upper()
    code_int = inferred_http_status_code(code, status)

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


def make_agent_api_error(code: object, status: object) -> AgentApiError:
    return AgentApiError(
        user_facing_agent_api_error(code, status),
        status_code=inferred_http_status_code(code, status),
        api_status=str(status) if status is not None else None,
    )


def is_retryable_agent_error(exc: BaseException) -> bool:
    """429/503 — имеет смысл повторить тот же провайдер с backoff."""
    if not isinstance(exc, AgentApiError):
        return False
    code = inferred_http_status_code(exc.status_code, exc.api_status)
    return code in RETRYABLE_HTTP_CODES


def is_transient_agent_error(exc: BaseException) -> bool:
    """Ошибки, после реального отказа которых можно перейти к запасному LLM."""
    if isinstance(exc, AgentInvalidResponseError):
        return True
    if not isinstance(exc, AgentApiError):
        return False
    code = inferred_http_status_code(exc.status_code, exc.api_status)
    if code in NON_FAILOVER_HTTP_CODES:
        return False
    if code in TRANSIENT_HTTP_CODES:
        return True
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


def compact_system_prompt(text: str) -> str:
    """
    Ужимает системный промпт для LLM: те же 20 критериев и правила,
    без служебной преамбулы, дублей шкалы и длинного JSON-примера.
    """
    compact = (text or "").replace("\r\n", "\n").strip()
    if not compact:
        return compact
    block1 = compact.find("### Блок 1")
    rest = compact[block1:] if block1 != -1 else compact
    rest = _PROMPT_SCALE_DUPLICATE_RE.sub("", rest)
    rest = _PROMPT_DATA_LINE_RE.sub("", rest)
    rest = _PROMPT_CHECKED_LINE_RE.sub("", rest)
    rest = _PROMPT_JSON_EXAMPLE_RE.sub(_SHORT_JSON_SCHEMA, rest, count=1)
    sec6 = rest.find("## 6.")
    if sec6 != -1:
        rest = rest[:sec6].rstrip() + "\n\n" + _SHORT_SELF_CHECK
    rest = re.sub(r"\n{3,}", "\n\n", rest).strip()
    return (_COMPACT_ROLE_AND_RULES.rstrip() + "\n\n" + rest).strip()


def load_system_prompt(path: Path | None = None) -> str:
    prompt_path = path or DEFAULT_SYSTEM_PROMPT_PATH
    text = prompt_path.read_text(encoding="utf-8").strip()
    if not text:
        raise AgentConfigError(f"Системный промпт пуст: {prompt_path}")
    compact = compact_system_prompt(text)
    if len(compact) < len(text):
        logger.info(
            "System prompt compacted: original_chars=%s compact_chars=%s",
            len(text),
            len(compact),
        )
    return compact


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


def _omit_empty_strings(value: Any) -> Any:
    """Убирает пустые строки из JSON, не трогая списки и значащие поля."""
    if isinstance(value, dict):
        return {
            key: _omit_empty_strings(item)
            for key, item in value.items()
            if item != ""
        }
    if isinstance(value, list):
        return [_omit_empty_strings(item) for item in value]
    return value


def _compact_layout_value(value: Any, *, key: str | None = None) -> Any:
    if isinstance(value, dict):
        compacted: dict[str, Any] = {}
        for child_key, child in value.items():
            if child_key in LAYOUT_DROP_KEYS:
                continue
            compacted[child_key] = _compact_layout_value(child, key=child_key)
        return compacted
    if isinstance(value, list):
        items = [_compact_layout_value(item) for item in value]
        if key == "links" and len(items) > LAYOUT_LINK_CAP:
            in_view = [item for item in items if isinstance(item, dict) and item.get("in_viewport")]
            rest = [item for item in items if not (isinstance(item, dict) and item.get("in_viewport"))]
            items = (in_view + rest)[:LAYOUT_LINK_CAP]
        return items
    if key in LAYOUT_ROUND_KEYS and isinstance(value, float):
        return round(value, 1)
    if key == "href" and isinstance(value, str) and len(value) > 180:
        return value[:179] + "…"
    return value


def compact_layout_for_llm(layout: Any) -> Any:
    """Полный набор элементов layout, без служебных CSS и с лимитом ссылок."""
    return _omit_empty_strings(_compact_layout_value(layout))


def build_page_payload(
    page_data: PageData,
    *,
    html_mode: str | None = None,
) -> dict[str, Any]:
    """
    Сериализует PageData для LLM: полный visible_text, полный desktop/mobile
    layout и компактный semantic HTML skeleton вместо сырого HTML.
    """
    payload = page_data.model_dump(mode="json", exclude_none=True)
    raw_html = payload.get("html") or ""
    prepared_html, was_reduced, mode = prepare_html_for_llm(raw_html, mode=html_mode)
    payload["html"] = prepared_html
    # Совместимость с промптом: флаг означает «HTML уплотнён для лимита запроса».
    payload["html_truncated"] = was_reduced
    payload["html_mode"] = mode
    for layout_key in ("layout_desktop", "layout_mobile"):
        if layout_key in payload:
            payload[layout_key] = compact_layout_for_llm(payload[layout_key])
    logger.info(
        "Page payload for LLM: mode=%s url=%s raw_html=%s skeleton_html=%s "
        "visible_text=%s layout_desktop=%s layout_mobile=%s",
        mode,
        page_data.url,
        len(raw_html),
        len(prepared_html),
        len(page_data.visible_text or ""),
        len(json.dumps(payload.get("layout_desktop") or {}, ensure_ascii=False)),
        len(json.dumps(payload.get("layout_mobile") or {}, ensure_ascii=False)),
    )
    return payload


def build_analysis_user_message(
    page_data: PageData,
    *,
    html_mode: str | None = None,
) -> str:
    user_payload = build_page_payload(page_data, html_mode=html_mode)
    dumped = json.dumps(user_payload, ensure_ascii=False, separators=(",", ":"))
    logger.info(
        "LLM user message chars=%s url=%s html_mode=%s",
        len(dumped),
        page_data.url,
        user_payload.get("html_mode"),
    )
    return (
        "Проанализируй лендинг строго по системному промпту и верни только "
        "JSON по схеме LlmAgentResult (без numeric overall/block score).\n\n"
        f"Данные страницы (JSON):\n{dumped}"
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
