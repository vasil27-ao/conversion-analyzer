"""Тесты валидации сырого ответа LLM по составу методики."""

from copy import deepcopy

import pytest

from app.agent.checklist import EXPECTED_CRITERION_IDS
from app.agent.mock_client import build_mock_llm_result
from app.agent.overall import assemble_agent_result, compute_overall
from app.agent.schemas import CriterionResult
from app.agent.validation import AgentResponseValidationError, validate_llm_agent_result


def _complete_result():
    return build_mock_llm_result()


def test_validate_correct_response():
    result = _complete_result()
    validate_llm_agent_result(result)  # не бросает


def test_validate_missing_criterion():
    result = _complete_result()
    # Удаляем критерий 1.2 из первого блока.
    result.blocks[0].criteria = [
        c for c in result.blocks[0].criteria if c.id != "1.2"
    ]
    with pytest.raises(AgentResponseValidationError, match="Отсутствуют критерии: 1.2"):
        validate_llm_agent_result(result)


def test_validate_duplicate_criterion():
    result = _complete_result()
    duplicate = deepcopy(result.blocks[0].criteria[0])
    result.blocks[0].criteria.append(duplicate)
    with pytest.raises(AgentResponseValidationError, match="Дублируются criterion id"):
        validate_llm_agent_result(result)


def test_validate_unknown_criterion_id():
    result = _complete_result()
    result.blocks[0].criteria[0] = CriterionResult(
        id="9.9",
        score=2,
        justification="Неизвестный критерий.",
        recommendation=None,
    )
    with pytest.raises(AgentResponseValidationError, match="Неизвестные criterion id: 9.9"):
        validate_llm_agent_result(result)


def test_assemble_does_not_calculate_score_when_validation_fails(monkeypatch):
    result = _complete_result()
    result.blocks[0].criteria = [
        c for c in result.blocks[0].criteria if c.id != "1.4"
    ]

    called = {"compute": False}

    def _boom(*args, **kwargs):
        called["compute"] = True
        raise AssertionError("compute_overall не должен вызываться при ошибке валидации")

    monkeypatch.setattr("app.agent.overall.compute_overall", _boom)

    with pytest.raises(AgentResponseValidationError, match="1.4"):
        assemble_agent_result(result)

    assert called["compute"] is False


def test_assemble_valid_complete_result():
    llm = _complete_result()
    final = assemble_agent_result(llm)
    assert final.overall.summary == llm.overall.summary
    assert len(final.blocks) == 6
    assert sum(len(b.criteria) for b in final.blocks) == len(EXPECTED_CRITERION_IDS)
    # Score посчитан только после успешной валидации.
    expected = compute_overall(
        [c.score for b in llm.blocks for c in b.criteria]
    )
    assert final.overall.score == expected.score
    assert final.overall.level == expected.level
