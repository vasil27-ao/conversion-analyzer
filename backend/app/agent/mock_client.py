"""
Заглушка агента-аналитика для тестирования backend до подключения LLM.

Возвращает полный пример `LlmAgentResult` (6 блоков, 20 критериев) без
numeric score — их считает backend через `assemble_agent_result`.
"""

from typing import Dict, Optional, Tuple

from app.agent.checklist import METHODOLOGY_BLOCKS
from app.agent.interface import AgentClient
from app.agent.schemas import (
    BacklogItem,
    CriterionResult,
    LlmAgentResult,
    LlmBlockResult,
    LlmOverall,
    ProblemItem,
    Score,
)
from app.page_collector.models import PageData

# Переопределения для отдельных критериев в mock-сценарии.
# Остальные критерии получают нейтральный score=2.
_MOCK_OVERRIDES: Dict[str, Tuple[Score, str, Optional[str]]] = {
    "1.1": (
        2,
        "Заголовок и подзаголовок первого экрана прямо называют продукт и его назначение.",
        None,
    ),
    "1.3": (
        1,
        "По layout-данным desktop CTA в видимой области первого экрана, на mobile — вне её.",
        "Перенести CTA в пределы первого экрана на мобильной версии.",
    ),
    "2.3": (
        1,
        "Преимущества поданы единым текстовым массивом без визуального разделения.",
        "Разделить преимущества на отдельные визуально обособленные пункты.",
    ),
    "3.1": (
        "N/A",
        "Публичные отзывы не ожидаются для этого лендинга с индивидуальным расчётом.",
        None,
    ),
    "3.5": (
        1,
        "Контакты в футере есть, но малозаметны среди прочего мелкого текста.",
        "Сделать контактные данные в футере более заметными.",
    ),
    "4.1": (
        2,
        "Текст кнопки прямо называет результат («Отправить заявку на расчёт»).",
        None,
    ),
    "4.2": (
        1,
        "Часть полей формы не объясняет, зачем они нужны для заявки.",
        "Оставить только нужные поля или пояснить назначение остальных.",
    ),
    "5.2": (
        1,
        "На mobile CTA видим, но расположен теснее из-за уменьшенных отступов.",
        "Проверить отступы вокруг CTA в мобильной верстке.",
    ),
    "6.1": (
        2,
        "По layout-данным не найдено перекрывающих или посторонних элементов.",
        None,
    ),
}

_BLOCK_ANALYTICS: Dict[str, Tuple[str, str]] = {
    "1": (
        "Оффер понятен, но CTA на mobile выходит за пределы первого экрана.",
        "Без видимого способа действовать на mobile труднее перейти к заявке.",
    ),
    "2": (
        "Преимущества есть, но плохо структурированы.",
        "Без ясной структуры выгод сложнее быстро понять ценность предложения.",
    ),
    "3": (
        "Контакты малозаметны; отзывы для этого оффера не ожидаются.",
        "Слабо видимые контакты затрудняют понимание, кто стоит за страницей.",
    ),
    "4": (
        "Текст кнопки понятен, но состав полей формы частично неочевиден.",
        "Неочевидные поля повышают сомнение перед отправкой заявки.",
    ),
    "5": (
        "CTA на mobile размещён теснее, чем на desktop.",
        "Менее уверенное размещение снижает заметность действия на mobile.",
    ),
    "6": (
        "Существенных отвлекающих элементов не обнаружено.",
        "Внимание пользователя не перетягивается посторонними элементами.",
    ),
}


def _default_criterion(criterion_id: str) -> CriterionResult:
    override = _MOCK_OVERRIDES.get(criterion_id)
    if override is not None:
        score, justification, recommendation = override
        return CriterionResult(
            id=criterion_id,
            score=score,
            justification=justification,
            recommendation=recommendation,
        )
    return CriterionResult(
        id=criterion_id,
        score=2,
        justification=f"Критерий {criterion_id}: по mock-данным выполнен без заметных потерь.",
        recommendation=None,
    )


def build_mock_llm_result() -> LlmAgentResult:
    blocks = []
    for block_id, block_name, criterion_ids in METHODOLOGY_BLOCKS:
        what_is_wrong, why_it_matters = _BLOCK_ANALYTICS[block_id]
        blocks.append(
            LlmBlockResult(
                block_id=block_id,
                block_name=block_name,
                what_is_wrong=what_is_wrong,
                why_it_matters=why_it_matters,
                criteria=[_default_criterion(cid) for cid in criterion_ids],
            )
        )

    return LlmAgentResult(
        overall=LlmOverall(
            summary=(
                "На первом экране продукт считывается быстро, а формулировка "
                "основной кнопки понятно описывает результат действия. Основные "
                "проблемы — CTA уходит за пределы первого экрана на mobile и "
                "форма запрашивает поля без ясного назначения; главный резерв — "
                "сделать CTA стабильно доступным на первом экране mobile и "
                "упростить состав формы."
            ),
        ),
        blocks=blocks,
        problems=[
            ProblemItem(
                description="Кнопка целевого действия не видна без прокрутки на мобильной версии",
                location="Первый экран, мобильная версия (layout-данные)",
            ),
            ProblemItem(
                description="Форма запрашивает поля без очевидного назначения для пользователя",
                location="Форма, HTML-элемент формы",
            ),
            ProblemItem(
                description="Контактные данные в футере визуально малозаметны",
                location="Футер, видимый текст",
            ),
        ],
        backlog=[
            BacklogItem(
                task="Перенести кнопку целевого действия в пределы первого экрана на мобильной версии",
                zone="Первый экран / мобильная версия",
                priority="высокий",
                expected_effect=(
                    "Пользователь видит способ действовать сразу, не прокручивая "
                    "страницу в поисках кнопки"
                ),
            ),
            BacklogItem(
                task="Пересмотреть состав полей формы и пояснить назначение неочевидных полей",
                zone="Форма",
                priority="средний",
                expected_effect=(
                    "Пользователь меньше сомневается, стоит ли продолжать "
                    "заполнение формы"
                ),
            ),
            BacklogItem(
                task="Сделать контактные данные в футере более заметными",
                zone="Футер",
                priority="низкий",
                expected_effect=(
                    "Пользователю проще убедиться, кто стоит за страницей, перед "
                    "тем как оставить заявку"
                ),
            ),
        ],
    )


_MOCK_RESULT = build_mock_llm_result()


class MockAgentClient(AgentClient):
    async def analyze(self, page_data: PageData) -> LlmAgentResult:
        return _MOCK_RESULT
