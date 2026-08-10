from enum import Enum


class AnalysisStatus(str, Enum):
    """Статусы одной задачи анализа."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
