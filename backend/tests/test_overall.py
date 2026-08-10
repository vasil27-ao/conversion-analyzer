"""Тесты детерминированного расчёта overall и block score."""

import pytest

from app.agent.mock_client import build_mock_llm_result
from app.agent.overall import (
    OverallCalculationError,
    assemble_agent_result,
    compute_block_score,
    compute_overall,
    level_from_score,
)


def test_level_boundaries():
    assert level_from_score(49.9) == "низкий"
    assert level_from_score(50) == "средний"
    assert level_from_score(74.9) == "средний"
    assert level_from_score(75) == "высокий"


def test_ordinary_case_without_na():
    result = compute_overall([2, 2, 2, 0])
    assert result.score == 75.0
    assert result.level == "высокий"
    assert result.applicable_count == 4
    assert result.na_count == 0


def test_with_na_excluded_from_calculation():
    result = compute_overall([2, "N/A", 0])
    assert result.score == 50.0
    assert result.level == "средний"
    assert result.applicable_count == 2
    assert result.na_count == 1


def test_all_scores_are_two():
    result = compute_overall([2] * 20)
    assert result.score == 100.0
    assert result.level == "высокий"
    assert result.applicable_count == 20
    assert result.na_count == 0


def test_all_scores_are_zero():
    result = compute_overall([0] * 20)
    assert result.score == 0.0
    assert result.level == "низкий"
    assert result.applicable_count == 20
    assert result.na_count == 0


def test_applicable_count_zero_raises():
    with pytest.raises(OverallCalculationError, match="applicable_count == 0"):
        compute_overall(["N/A", "N/A"])


def test_score_rounds_to_one_decimal():
    result = compute_overall([1, 0, 0])
    assert result.score == 16.7


def test_boundary_levels_via_achievable_scores():
    assert compute_overall([1] * 19 + [0]).score == 47.5
    assert compute_overall([1] * 19 + [0]).level == "низкий"
    assert compute_overall([1] * 20).score == 50.0
    assert compute_overall([1] * 20).level == "средний"
    assert compute_overall([2] * 9 + [1] * 11).score == 72.5
    assert compute_overall([2] * 9 + [1] * 11).level == "средний"
    assert compute_overall([2] * 10 + [1] * 10).score == 75.0
    assert compute_overall([2] * 10 + [1] * 10).level == "высокий"


def test_compute_block_score_ordinary_and_with_na():
    assert compute_block_score([2, 0]) == 50.0
    assert compute_block_score([2, "N/A"]) == 100.0


def test_compute_block_score_all_na_returns_none():
    assert compute_block_score(["N/A", "N/A"]) is None


def test_assemble_agent_result_merges_summary_block_analytics_and_scores():
    llm = build_mock_llm_result()
    result = assemble_agent_result(llm)

    assert result.overall.summary == llm.overall.summary
    assert len(result.blocks) == 6
    assert result.blocks[0].what_is_wrong
    assert result.blocks[0].why_it_matters
    assert result.blocks[0].score is not None

    # Блок 3 содержит N/A (3.1) и оценки — score должен быть числом.
    trust_block = next(b for b in result.blocks if b.block_id == "3")
    assert trust_block.score is not None

    expected = compute_overall([c.score for b in llm.blocks for c in b.criteria])
    assert result.overall.score == expected.score
    assert result.overall.level == expected.level
    assert result.overall.applicable_count == expected.applicable_count
    assert result.overall.na_count == expected.na_count
