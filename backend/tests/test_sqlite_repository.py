"""Unit-тесты SQLite AnalysisRepository: save/get для pending, done, failed."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from app.agent.mock_client import build_mock_llm_result
from app.agent.overall import assemble_agent_result
from app.core.models import Analysis
from app.core.status import AnalysisStatus
from app.storage.sqlite_repository import SqliteAnalysisRepository


def _repo(tmp_path: Path) -> SqliteAnalysisRepository:
    return SqliteAnalysisRepository(tmp_path / "analyses.db")


def test_save_and_get_pending_analysis(tmp_path: Path):
    repo = _repo(tmp_path)
    analysis = Analysis(
        id="a-pending",
        url="https://example.com/landing",
        status=AnalysisStatus.PENDING,
        created_at=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
        result=None,
        error_message=None,
    )

    asyncio.run(repo.save(analysis))
    loaded = asyncio.run(repo.get("a-pending"))

    assert loaded is not None
    assert loaded.id == "a-pending"
    assert str(loaded.url) == "https://example.com/landing"
    assert loaded.status == AnalysisStatus.PENDING
    assert loaded.result is None
    assert loaded.error_message is None
    assert loaded.created_at == analysis.created_at


def test_save_and_get_done_analysis_with_agent_result(tmp_path: Path):
    repo = _repo(tmp_path)
    result = assemble_agent_result(build_mock_llm_result())
    analysis = Analysis(
        id="a-done",
        url="https://example.com/done",
        status=AnalysisStatus.DONE,
        created_at=datetime(2026, 8, 10, 13, 0, tzinfo=timezone.utc),
        result=result,
        error_message=None,
    )

    asyncio.run(repo.save(analysis))
    loaded = asyncio.run(repo.get("a-done"))

    assert loaded is not None
    assert loaded.status == AnalysisStatus.DONE
    assert loaded.error_message is None
    assert loaded.result is not None
    assert loaded.result.overall.score == result.overall.score
    assert loaded.result.overall.level == result.overall.level
    assert loaded.result.overall.summary == result.overall.summary
    assert len(loaded.result.blocks) == len(result.blocks)
    assert loaded.result.blocks[0].block_id == result.blocks[0].block_id
    assert loaded.result.blocks[0].score == result.blocks[0].score
    assert loaded.result.problems == result.problems
    assert loaded.result.backlog == result.backlog


def test_save_and_get_failed_analysis(tmp_path: Path):
    repo = _repo(tmp_path)
    analysis = Analysis(
        id="a-failed",
        url="https://example.com/missing",
        status=AnalysisStatus.FAILED,
        created_at=datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc),
        result=None,
        error_message="Страница недоступна (HTTP 404)",
    )

    asyncio.run(repo.save(analysis))
    loaded = asyncio.run(repo.get("a-failed"))

    assert loaded is not None
    assert loaded.status == AnalysisStatus.FAILED
    assert loaded.result is None
    assert loaded.error_message == "Страница недоступна (HTTP 404)"


def test_get_unknown_id_returns_none(tmp_path: Path):
    repo = _repo(tmp_path)
    assert asyncio.run(repo.get("no-such-id")) is None


def test_save_updates_existing_analysis(tmp_path: Path):
    repo = _repo(tmp_path)
    created = datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc)
    pending = Analysis(
        id="a-update",
        url="https://example.com/update",
        status=AnalysisStatus.PENDING,
        created_at=created,
    )
    asyncio.run(repo.save(pending))

    result = assemble_agent_result(build_mock_llm_result())
    done = pending.model_copy(
        update={"status": AnalysisStatus.DONE, "result": result}
    )
    asyncio.run(repo.save(done))

    loaded = asyncio.run(repo.get("a-update"))
    assert loaded is not None
    assert loaded.status == AnalysisStatus.DONE
    assert loaded.result is not None
    assert loaded.result.overall.score == result.overall.score
