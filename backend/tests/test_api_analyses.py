"""Минимальные API-тесты analyses (mock agent, без реального Playwright/LLM)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl

from app.config import Settings, get_settings
from app.main import create_app
from app.page_collector.errors import PageUnavailableError
from app.page_collector.models import LayoutSnapshot, PageData, ViewportSize


def _sample_page(url: str) -> PageData:
    return PageData(
        url=HttpUrl(url),
        html="<html><body><h1>Demo</h1></body></html>",
        visible_text="Demo landing",
        layout_desktop=LayoutSnapshot(viewport=ViewportSize(width=1280, height=800)),
        layout_mobile=LayoutSnapshot(viewport=ViewportSize(width=390, height=844)),
    )


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_IMPL", "mock")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "api_analyses.db"))
    get_settings.cache_clear()

    settings = Settings(
        app_env="test",
        agent_impl="mock",
        sqlite_path=str(tmp_path / "api_analyses.db"),
    )
    application = create_app(settings)

    async def fake_collect(url: str) -> PageData:
        return _sample_page(url)

    application.state.orchestrator._collect = fake_collect

    with TestClient(application) as client:
        yield client

    get_settings.cache_clear()


def test_create_analysis_returns_pending_then_done(api_client: TestClient):
    create = api_client.post(
        "/api/analyses",
        json={"url": "https://example.com/landing"},
    )
    assert create.status_code == 202
    body = create.json()
    assert "id" in body
    assert body["status"] == "pending"

    # BackgroundTasks отрабатывает до возврата из TestClient.post.
    status = api_client.get(f"/api/analyses/{body['id']}")
    assert status.status_code == 200
    payload = status.json()
    assert payload["id"] == body["id"]
    assert payload["url"] == "https://example.com/landing"
    assert payload["status"] == "done"
    assert payload["error_message"] is None
    assert payload["result"] is not None
    assert "score" in payload["result"]["overall"]
    assert payload["result"]["overall"]["level"] in {"низкий", "средний", "высокий"}
    assert len(payload["result"]["blocks"]) == 6


def test_get_analysis_unknown_id_returns_404(api_client: TestClient):
    response = api_client.get("/api/analyses/does-not-exist")
    assert response.status_code == 404
    assert "не найден" in response.json()["detail"].lower()


def test_create_analysis_collector_failure_sets_failed(
    api_client: TestClient,
):
    async def failing_collect(url: str) -> PageData:
        raise PageUnavailableError("Страница недоступна (HTTP 404)")

    # Переопределяем collect на том же app, что использует fixture client.
    app = api_client.app
    app.state.orchestrator._collect = failing_collect

    create = api_client.post(
        "/api/analyses",
        json={"url": "https://example.com/missing"},
    )
    assert create.status_code == 202
    analysis_id = create.json()["id"]

    status = api_client.get(f"/api/analyses/{analysis_id}")
    assert status.status_code == 200
    payload = status.json()
    assert payload["status"] == "failed"
    assert payload["result"] is None
    assert "404" in (payload["error_message"] or "")
