"""Несколько повторных анализов одной страницы: сравнение scores и 0↔N/A."""

from __future__ import annotations

import json
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

BASE = "http://127.0.0.1:8000"
URL = "https://example.com/"
RUNS = 4
OUT = Path(__file__).resolve().parents[1] / "data" / "stage5_results"


def req(method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wait_done(analysis_id: str, timeout_s: int = 600) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        payload = req("GET", f"/api/analyses/{analysis_id}")
        if payload["status"] in {"done", "failed"}:
            return payload
        time.sleep(4)
    raise TimeoutError(analysis_id)


def extract_scores(payload: dict) -> dict[str, object]:
    scores: dict[str, object] = {}
    for block in payload["result"]["blocks"]:
        for criterion in block["criteria"]:
            scores[criterion["id"]] = criterion["score"]
    return scores


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    runs: list[dict] = []

    # Создаём все сразу, затем ждём — как пользовательские параллельные запуски.
    created_ids: list[str] = []
    for i in range(RUNS):
        created = req("POST", "/api/analyses", {"url": URL})
        created_ids.append(created["id"])
        print(f"created run{i + 1} {created['id']}")

    for i, analysis_id in enumerate(created_ids, start=1):
        payload = wait_done(analysis_id)
        if payload["status"] != "done":
            print(f"run{i} failed: {payload.get('error_message')}")
            runs.append({"run": i, "status": "failed", "error": payload.get("error_message")})
            continue
        scores = extract_scores(payload)
        overall = payload["result"]["overall"]
        runs.append(
            {
                "run": i,
                "status": "done",
                "analysis_id": analysis_id,
                "score": overall["score"],
                "level": overall["level"],
                "applicable_count": overall["applicable_count"],
                "na_count": overall["na_count"],
                "scores": scores,
            }
        )
        print(
            f"run{i} done score={overall['score']} level={overall['level']} "
            f"na={overall['na_count']}"
        )
        (OUT / f"stability_example_run{i}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    done_runs = [r for r in runs if r.get("status") == "done"]
    by_criterion: dict[str, list[object]] = defaultdict(list)
    for run in done_runs:
        for cid, score in run["scores"].items():
            by_criterion[cid].append(score)

    flips_0_na: list[dict] = []
    other_changes: list[dict] = []
    for cid, values in sorted(by_criterion.items()):
        unique = []
        for value in values:
            if value not in unique:
                unique.append(value)
        if len(unique) <= 1:
            continue
        entry = {"id": cid, "values": values, "unique": unique}
        as_set = {json.dumps(v, ensure_ascii=False) for v in unique}
        if "0" in as_set and '"N/A"' in as_set:
            flips_0_na.append(entry)
        else:
            other_changes.append(entry)

    report = {
        "url": URL,
        "runs": [
            {
                "run": r["run"],
                "status": r["status"],
                "score": r.get("score"),
                "level": r.get("level"),
                "na_count": r.get("na_count"),
                "applicable_count": r.get("applicable_count"),
                "analysis_id": r.get("analysis_id"),
                "error": r.get("error"),
            }
            for r in runs
        ],
        "flips_0_na": flips_0_na,
        "other_score_changes": other_changes,
        "overall_scores": [r.get("score") for r in done_runs],
    }
    (OUT / "stability_example_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
