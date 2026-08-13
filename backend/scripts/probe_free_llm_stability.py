"""
Три production-прогона бесплатного LLM-стека: простой сайт, тяжёлый лендинг, карточка товара.

Печатает время, провайдер, retry/fallback и были ли 429/503.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path

from app.agent.llm_stats import get_llm_stats
from app.config import Settings, get_settings
from app.dependencies import build_agent_client, build_orchestrator

CASES = [
    ("simple", "https://example.com"),
    ("heavy_landing", "https://svetconsult.ru/"),
    ("product_card", "https://www.allbirds.com/products/womens-strider-rugged-beige"),
]


def _load_dotenv_without_bom() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        os.environ[key.strip().lstrip("\ufeff")] = value.strip().strip('"').strip("'")


class _MemoryLogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


async def _run_case(orchestrator, label: str, url: str) -> dict:
    started = time.perf_counter()
    analysis = await orchestrator.run(url)
    elapsed = time.perf_counter() - started
    stats = getattr(orchestrator._agent, "last_stats", None) or get_llm_stats()
    score = analysis.result.overall.score if analysis.result else None
    level = analysis.result.overall.level if analysis.result else None
    return {
        "label": label,
        "url": url,
        "status": str(analysis.status.value if hasattr(analysis.status, "value") else analysis.status),
        "total_s": round(elapsed, 3),
        "score": score,
        "level": level,
        "error": analysis.error_message,
        "provider": stats.success_provider if stats else None,
        "llm_s": round(stats.llm_elapsed_s, 3) if stats else None,
        "success_call_s": round(stats.success_call_s, 3) if stats else None,
        "retries": stats.retry_count if stats else None,
        "fallback": stats.fallback_used if stats else None,
        "tried": list(stats.providers_tried) if stats else [],
        "codes": list(stats.status_codes_seen) if stats else [],
        "had_429": stats.had_429 if stats else None,
        "had_503": stats.had_503 if stats else None,
    }


async def main() -> None:
    _load_dotenv_without_bom()
    get_settings.cache_clear()

    log_handler = _MemoryLogHandler()
    log_handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, force=True)
    logging.getLogger().addHandler(log_handler)

    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    os.environ["SQLITE_PATH"] = str(Path(tmp.name) / "probe.db")
    get_settings.cache_clear()
    settings = Settings(_env_file=None)
    print(
        "agent_impl=",
        settings.agent_impl,
        "max_concurrent=",
        settings.max_concurrent_analyses,
        "has_gemini=",
        bool(settings.gemini_api_key),
        "has_openrouter=",
        bool(settings.openrouter_api_key),
        "has_groq=",
        bool(settings.groq_api_key),
        flush=True,
    )
    orchestrator = build_orchestrator(settings, agent=build_agent_client(settings))
    rows: list[dict] = []
    try:
        for label, url in CASES:
            print(f"\n=== {label} {url} ===", flush=True)
            row = await _run_case(orchestrator, label, url)
            rows.append(row)
            print(row, flush=True)
    finally:
        tmp.cleanup()

    print("\n=== SUMMARY ===", flush=True)
    for row in rows:
        print(
            f"{row['label']}: status={row['status']} total_s={row['total_s']} "
            f"provider={row['provider']} retries={row['retries']} "
            f"fallback={row['fallback']} had_429={row['had_429']} "
            f"had_503={row['had_503']} codes={row['codes']} "
            f"score={row['score']} error={row['error']}",
            flush=True,
        )
    failed = [row for row in rows if row["status"] != "done"]
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
