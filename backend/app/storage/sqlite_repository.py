"""
SQLite-реализация AnalysisRepository для MVP.

Без ORM и миграций: одна таблица, CREATE IF NOT EXISTS при инициализации.
Доменная модель — существующий `Analysis` / `AgentResult`.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Optional

from app.agent.schemas import AgentResult
from app.core.models import Analysis
from app.core.status import AnalysisStatus
from app.storage.repository import AnalysisRepository

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    result_json TEXT,
    error_message TEXT
);
"""

_UPSERT_SQL = """
INSERT INTO analyses (id, url, status, created_at, result_json, error_message)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    url = excluded.url,
    status = excluded.status,
    created_at = excluded.created_at,
    result_json = excluded.result_json,
    error_message = excluded.error_message;
"""

_GET_SQL = """
SELECT id, url, status, created_at, result_json, error_message
FROM analyses
WHERE id = ?;
"""


class SqliteAnalysisRepository(AnalysisRepository):
    """Хранит Analysis в локальном SQLite-файле."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE_SQL)
            conn.commit()

    def _serialize_result(self, result: Optional[AgentResult]) -> Optional[str]:
        if result is None:
            return None
        return result.model_dump_json()

    def _deserialize_result(self, raw: Optional[str]) -> Optional[AgentResult]:
        if raw is None:
            return None
        return AgentResult.model_validate_json(raw)

    def _row_to_analysis(self, row: sqlite3.Row) -> Analysis:
        return Analysis(
            id=row["id"],
            url=row["url"],
            status=AnalysisStatus(row["status"]),
            created_at=row["created_at"],
            result=self._deserialize_result(row["result_json"]),
            error_message=row["error_message"],
        )

    def _save_sync(self, analysis: Analysis) -> None:
        with self._connect() as conn:
            conn.execute(
                _UPSERT_SQL,
                (
                    analysis.id,
                    str(analysis.url),
                    analysis.status.value,
                    analysis.created_at.isoformat(),
                    self._serialize_result(analysis.result),
                    analysis.error_message,
                ),
            )
            conn.commit()

    def _get_sync(self, analysis_id: str) -> Optional[Analysis]:
        with self._connect() as conn:
            row = conn.execute(_GET_SQL, (analysis_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_analysis(row)

    async def save(self, analysis: Analysis) -> None:
        await asyncio.to_thread(self._save_sync, analysis)

    async def get(self, analysis_id: str) -> Optional[Analysis]:
        return await asyncio.to_thread(self._get_sync, analysis_id)
