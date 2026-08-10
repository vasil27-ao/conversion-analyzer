"""Этап 5: проверка ошибок недоступной страницы и сбоя агента."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agent.errors import AgentApiError
from app.agent.interface import AgentClient
from app.core.status import AnalysisStatus
from app.page_collector.models import PageData
from app.services.orchestrator import AnalysisOrchestrator
from app.storage.sqlite_repository import SqliteAnalysisRepository

BASE = "http://127.0.0.1:8000"
OUT = BACKEND_ROOT / "data" / "stage5_results"


def poll_until_terminal(analysis_id: str, timeout_s: int = 120) -> dict:
    import time

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        with urllib.request.urlopen(BASE + f"/api/analyses/{analysis_id}", timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if payload["status"] in {"done", "failed"}:
            return payload
        time.sleep(2)
    raise TimeoutError(f"analysis {analysis_id} did not finish")


def test_unavailable_page() -> dict:
    body = json.dumps(
        {"url": "https://this-domain-definitely-does-not-exist-12345.invalid/"}
    ).encode("utf-8")
    request = urllib.request.Request(
        BASE + "/api/analyses",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as resp:
        created = json.loads(resp.read().decode("utf-8"))
    payload = poll_until_terminal(created["id"], timeout_s=90)
    return {
        "case": "unavailable_page",
        "status": payload["status"],
        "error_message": payload.get("error_message"),
        "analysis_id": created["id"],
    }


class FailingAgent(AgentClient):
    async def analyze(self, page_data: PageData):  # type: ignore[override]
        raise AgentApiError("Симуляция сбоя агента: LLM API недоступен.")


async def test_agent_failure() -> dict:
    # ignore_cleanup_errors: на Windows SQLite может коротко удерживать файл.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = SqliteAnalysisRepository(Path(tmp) / "test.db")
        orchestrator = AnalysisOrchestrator(repository=repo, agent=FailingAgent())

        async def fake_collect(url: str) -> PageData:
            return PageData(
                url=url,
                html="<html><body>ok</body></html>",
                visible_text="ok",
                layout_desktop={"viewport": {"width": 1280, "height": 800}},
                layout_mobile={"viewport": {"width": 390, "height": 844}},
            )

        orchestrator._collect = fake_collect  # type: ignore[method-assign]
        analysis = await orchestrator.run("https://example.com")
        return {
            "case": "agent_failure",
            "status": analysis.status.value if hasattr(analysis.status, "value") else str(analysis.status),
            "error_message": analysis.error_message,
            "service_alive": analysis.status == AnalysisStatus.FAILED,
        }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    results = {
        "unavailable_page": test_unavailable_page(),
        "agent_failure": asyncio.run(test_agent_failure()),
    }
    (OUT / "errors.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(results, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
