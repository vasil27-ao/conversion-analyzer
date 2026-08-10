"""
Фиксированный состав методики для валидации ответа агента.

Источник: docs/cro-methodology.md (6 блоков, 20 критериев).
"""

from typing import Dict, List, Tuple

# (block_id, block_name, criterion_ids)
METHODOLOGY_BLOCKS: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("1", "Первый экран и оффер", ("1.1", "1.2", "1.3", "1.4")),
    ("2", "Понятность ценности продукта", ("2.1", "2.2", "2.3", "2.4")),
    ("3", "Доверие", ("3.1", "3.2", "3.3", "3.4", "3.5")),
    ("4", "Форма / целевое действие", ("4.1", "4.2", "4.3", "4.4")),
    ("5", "Мобильная версия", ("5.1", "5.2")),
    ("6", "Отвлекающие элементы", ("6.1",)),
)

EXPECTED_BLOCK_IDS: Tuple[str, ...] = tuple(block_id for block_id, _, _ in METHODOLOGY_BLOCKS)

EXPECTED_CRITERION_IDS: Tuple[str, ...] = tuple(
    criterion_id
    for _, _, criterion_ids in METHODOLOGY_BLOCKS
    for criterion_id in criterion_ids
)

BLOCK_NAME_BY_ID: Dict[str, str] = {
    block_id: block_name for block_id, block_name, _ in METHODOLOGY_BLOCKS
}

CRITERION_IDS_BY_BLOCK: Dict[str, List[str]] = {
    block_id: list(criterion_ids) for block_id, _, criterion_ids in METHODOLOGY_BLOCKS
}

assert len(EXPECTED_BLOCK_IDS) == 6
assert len(EXPECTED_CRITERION_IDS) == 20
assert len(set(EXPECTED_CRITERION_IDS)) == 20
