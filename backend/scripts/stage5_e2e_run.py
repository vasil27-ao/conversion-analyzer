"""Этап 5: прогон трёх тестовых страниц через живой API (Gemini)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8000"
PAGES = [
    ("weak", "https://example.com"),
    ("medium", "https://www.w3schools.com/"),
    ("strong", "https://stripe.com/"),
]
OUT = Path(__file__).resolve().parents[1] / "data" / "stage5_results"
POLL_SECONDS = 5
TIMEOUT_SECONDS = 900


def req(method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    with urllib.request.urlopen(BASE + "/api/health", timeout=10) as resp:
        print("health", resp.read().decode())

    ids: dict[str, dict] = {}
    for label, url in PAGES:
        created = req("POST", "/api/analyses", {"url": url})
        ids[label] = {"id": created["id"], "url": url, "status": created["status"]}
        print("created", label, created["id"], url)

    deadline = time.time() + TIMEOUT_SECONDS
    pending = set(ids)
    while pending and time.time() < deadline:
        done_now: list[str] = []
        for label in list(pending):
            payload = req("GET", f"/api/analyses/{ids[label]['id']}")
            status = payload["status"]
            print(f"poll {label}: {status}")
            if status in {"done", "failed"}:
                ids[label]["status"] = status
                ids[label]["payload"] = payload
                (OUT / f"{label}.json").write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                done_now.append(label)
        for label in done_now:
            pending.discard(label)
        if pending:
            time.sleep(POLL_SECONDS)

    summary: dict[str, dict] = {}
    for label, meta in ids.items():
        payload = meta.get("payload")
        if not payload:
            summary[label] = {"status": "timeout", "url": meta["url"]}
            continue
        if payload["status"] == "failed":
            summary[label] = {
                "status": "failed",
                "error": payload.get("error_message"),
                "url": meta["url"],
                "analysis_id": meta["id"],
            }
            continue

        result = payload["result"]
        overall = result["overall"]
        blocks = [
            {
                "id": b["block_id"],
                "name": b["block_name"],
                "score": b.get("score"),
                "criteria": len(b.get("criteria") or []),
            }
            for b in result.get("blocks") or []
        ]
        criteria_scores = []
        texts = [overall.get("summary") or ""]
        for block in result.get("blocks") or []:
            texts.extend([block.get("what_is_wrong") or "", block.get("why_it_matters") or ""])
            for criterion in block.get("criteria") or []:
                criteria_scores.append({"id": criterion["id"], "score": criterion["score"]})
                texts.extend(
                    [
                        criterion.get("justification") or "",
                        criterion.get("recommendation") or "",
                    ]
                )
        for item in result.get("problems") or []:
            texts.extend([item.get("description") or "", item.get("location") or ""])
        for item in result.get("backlog") or []:
            texts.extend(
                [
                    item.get("task") or "",
                    item.get("zone") or "",
                    item.get("expected_effect") or "",
                ]
            )
        blob = "\n".join(texts).lower()
        tech_hits = [token for token in ("mock", "layout", "html", "backlog", "dom") if token in blob]
        summary[label] = {
            "status": "done",
            "url": meta["url"],
            "score": overall.get("score"),
            "level": overall.get("level"),
            "applicable_count": overall.get("applicable_count"),
            "na_count": overall.get("na_count"),
            "blocks_count": len(result.get("blocks") or []),
            "criteria_count": len(criteria_scores),
            "problems_count": len(result.get("problems") or []),
            "backlog_count": len(result.get("backlog") or []),
            "criteria_scores": criteria_scores,
            "block_scores": blocks,
            "summary": overall.get("summary"),
            "tech_hits_raw": tech_hits,
            "analysis_id": meta["id"],
        }

    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
