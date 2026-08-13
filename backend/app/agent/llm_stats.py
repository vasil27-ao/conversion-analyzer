"""Статистика последнего LLM-вызова (retry/fallback/провайдер/время)."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class LlmCallStats:
    success_provider: str | None = None
    providers_tried: list[str] = field(default_factory=list)
    retry_count: int = 0
    fallback_used: bool = False
    had_429: bool = False
    had_503: bool = False
    status_codes_seen: list[int] = field(default_factory=list)
    llm_elapsed_s: float = 0.0
    success_call_s: float = 0.0

    def mark_status(self, status_code: int | None) -> None:
        if status_code is None:
            return
        self.status_codes_seen.append(status_code)
        if status_code == 429:
            self.had_429 = True
        elif status_code == 503:
            self.had_503 = True


_current: ContextVar[LlmCallStats | None] = ContextVar("llm_call_stats", default=None)


def reset_llm_stats() -> LlmCallStats:
    stats = LlmCallStats()
    _current.set(stats)
    return stats


def get_llm_stats() -> LlmCallStats | None:
    return _current.get()
