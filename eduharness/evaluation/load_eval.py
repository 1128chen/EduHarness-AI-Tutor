from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import time
from typing import Any

import httpx


TERMINAL_STATUSES = {
    "completed",
    "failed",
    "cancelled",
}


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, int(len(ordered) * fraction + 0.999) - 1)
    return ordered[index]


def run_turn(
    base_url: str,
    session_id: str,
    index: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    started_at = time.perf_counter()

    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                (
                    f"{base_url}/api/v1/sessions/"
                    f"{session_id}/turns"
                ),
                json={
                    "content": (
                        f"测试请求{index}：请用两句话解释什么是函数。"
                    )
                },
            )
            response.raise_for_status()
            turn_id = str(response.json()["id"])

            deadline = time.monotonic() + timeout_seconds
            status = "unknown"

            while time.monotonic() < deadline:
                detail = client.get(
                    f"{base_url}/api/v1/turns/{turn_id}"
                )
                detail.raise_for_status()
                status = str(detail.json()["status"]).lower()

                if status in TERMINAL_STATUSES:
                    break

                time.sleep(0.5)

            duration = time.perf_counter() - started_at

            return {
                "index": index,
                "turn_id": turn_id,
                "status": status,
                "success": status == "completed",
                "duration_seconds": duration,
                "error": "",
            }

    except Exception as exc:
        return {
            "index": index,
            "turn_id": "",
            "status": "exception",
            "success": False,
            "duration_seconds": time.perf_counter() - started_at,
            "error": f"{type(exc).__name__}: {exc}",
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--requests", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
    )
    args = parser.parse_args()

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.concurrency
    ) as executor:
        futures = [
            executor.submit(
                run_turn,
                args.base_url.rstrip("/"),
                args.session_id,
                index,
                args.timeout,
            )
            for index in range(1, args.requests + 1)
        ]

        results = [
            future.result()
            for future in concurrent.futures.as_completed(futures)
        ]

    durations = [
        float(item["duration_seconds"])
        for item in results
    ]
    successes = sum(bool(item["success"]) for item in results)

    summary = {
        "requests": len(results),
        "concurrency": args.concurrency,
        "successes": successes,
        "success_rate": successes / len(results),
        "duration_p50_seconds": statistics.median(durations),
        "duration_p95_seconds": percentile(durations, 0.95),
        "results": sorted(results, key=lambda item: item["index"]),
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()