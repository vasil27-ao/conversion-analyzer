"""
Проверка сырого ответа LLM на полноту относительно методики.

При ошибке валидации score не рассчитывается — `assemble_agent_result`
сначала вызывает эту проверку.
"""

from collections import Counter
from typing import List

from app.agent.checklist import EXPECTED_BLOCK_IDS, EXPECTED_CRITERION_IDS
from app.agent.schemas import LlmAgentResult


class AgentResponseValidationError(ValueError):
    """Ответ агента не соответствует ожидаемому составу методики."""


def validate_llm_agent_result(llm_result: LlmAgentResult) -> None:
    """
    Проверяет:
    - ровно 6 блоков с ожидаемыми block_id (каждый один раз);
    - ровно 20 критериев;
    - каждый ожидаемый criterion id ровно один раз;
    - нет неизвестных и дублирующихся criterion id.
    """
    errors: List[str] = []

    block_ids = [block.block_id for block in llm_result.blocks]
    if len(block_ids) != len(EXPECTED_BLOCK_IDS):
        errors.append(
            f"Ожидалось {len(EXPECTED_BLOCK_IDS)} блоков, получено {len(block_ids)}."
        )

    block_counts = Counter(block_ids)
    missing_blocks = [bid for bid in EXPECTED_BLOCK_IDS if block_counts[bid] == 0]
    duplicate_blocks = sorted(bid for bid, n in block_counts.items() if n > 1)
    unknown_blocks = sorted(bid for bid in block_counts if bid not in EXPECTED_BLOCK_IDS)

    if missing_blocks:
        errors.append(f"Отсутствуют блоки: {', '.join(missing_blocks)}.")
    if duplicate_blocks:
        errors.append(f"Дублируются block_id: {', '.join(duplicate_blocks)}.")
    if unknown_blocks:
        errors.append(f"Неизвестные block_id: {', '.join(unknown_blocks)}.")

    criterion_ids = [
        criterion.id
        for block in llm_result.blocks
        for criterion in block.criteria
    ]
    criterion_counts = Counter(criterion_ids)

    if len(criterion_ids) != len(EXPECTED_CRITERION_IDS):
        errors.append(
            f"Ожидалось {len(EXPECTED_CRITERION_IDS)} критериев, "
            f"получено {len(criterion_ids)}."
        )

    missing_criteria = [
        cid for cid in EXPECTED_CRITERION_IDS if criterion_counts[cid] == 0
    ]
    duplicate_criteria = sorted(
        cid for cid, n in criterion_counts.items() if n > 1
    )
    unknown_criteria = sorted(
        cid for cid in criterion_counts if cid not in EXPECTED_CRITERION_IDS
    )

    if missing_criteria:
        errors.append(f"Отсутствуют критерии: {', '.join(missing_criteria)}.")
    if duplicate_criteria:
        errors.append(f"Дублируются criterion id: {', '.join(duplicate_criteria)}.")
    if unknown_criteria:
        errors.append(f"Неизвестные criterion id: {', '.join(unknown_criteria)}.")

    if errors:
        raise AgentResponseValidationError(" ".join(errors))
