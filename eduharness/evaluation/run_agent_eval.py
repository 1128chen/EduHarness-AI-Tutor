from __future__ import annotations

import csv
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
CASES_PATH = ROOT / "cases.jsonl"
REPORT_DIR = ROOT / "reports"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            cases.append(json.loads(line))
    return cases


def format_value(value: Any, variables: dict[str, str]) -> Any:
    if isinstance(value, str):
        return value.format(**variables)
    if isinstance(value, list):
        return [format_value(item, variables) for item in value]
    if isinstance(value, dict):
        return {
            key: format_value(item, variables)
            for key, item in value.items()
        }
    return value


def nested_values(value: Any, keys: set[str]) -> list[Any]:
    found: list[Any] = []

    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys:
                found.append(item)
            found.extend(nested_values(item, keys))

    elif isinstance(value, list):
        for item in value:
            found.extend(nested_values(item, keys))

    return found


def first_nested_text(value: Any, keys: set[str]) -> str:
    for item in nested_values(value, keys):
        if isinstance(item, str):
            return item
    return ""


def percentile(values: list[float], percent: float) -> float | None:
    if not values:
        return None

    ordered = sorted(values)
    index = max(0, math.ceil(percent * len(ordered)) - 1)
    return ordered[index]


def create_resource(
    client: httpx.Client,
    base_url: str,
    spec: dict[str, Any],
    variables: dict[str, str],
) -> str:
    path = spec["path"].format(**variables)
    payload = format_value(spec.get("payload", {}), variables)

    response = client.post(base_url + path, json=payload)
    response.raise_for_status()

    body = response.json()
    field = spec.get("id_field", "id")

    if field not in body:
        raise RuntimeError(
            f"Response from {path} does not contain field {field}: {body}"
        )

    return str(body[field])


def parse_sse(
    client: httpx.Client,
    url: str,
    stream_timeout: float,
    require_approval: bool,
) -> tuple[list[dict[str, Any]], float | None, float, str]:
    started_at = time.perf_counter()
    first_token_seconds: float | None = None
    answer_parts: list[str] = []
    records: list[dict[str, Any]] = []

    event_name = "message"
    data_lines: list[str] = []

    timeout = httpx.Timeout(
        connect=10,
        read=stream_timeout,
        write=30,
        pool=10,
    )

    def dispatch() -> bool:
        nonlocal event_name
        nonlocal data_lines
        nonlocal first_token_seconds

        if not data_lines:
            event_name = "message"
            return False

        raw_data = "\n".join(data_lines)
        try:
            payload: Any = json.loads(raw_data)
        except json.JSONDecodeError:
            payload = {"raw": raw_data}

        actual_type = event_name
        if actual_type == "message" and isinstance(payload, dict):
            actual_type = str(
                payload.get("type")
                or payload.get("event")
                or payload.get("event_type")
                or "message"
            )

        record = {
            "event": actual_type,
            "payload": payload,
            "received_seconds": time.perf_counter() - started_at,
        }
        records.append(record)

        lower_type = actual_type.lower()

        if "model.delta" in lower_type or lower_type.endswith("delta"):
            text = first_nested_text(
                payload,
                {"text", "delta", "content"},
            )
            if text:
                if first_token_seconds is None:
                    first_token_seconds = time.perf_counter() - started_at
                answer_parts.append(text)

        event_name = "message"
        data_lines = []

        if require_approval and "approval.required" in lower_type:
            return True

        return (
            "turn.completed" in lower_type
            or "turn.failed" in lower_type
            or "turn.cancelled" in lower_type
        )

    with client.stream("GET", url, timeout=timeout) as response:
        response.raise_for_status()

        for line in response.iter_lines():
            if line == "":
                if dispatch():
                    break
                continue

            if line.startswith(":"):
                continue

            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())

        if data_lines:
            dispatch()

    duration = time.perf_counter() - started_at
    return records, first_token_seconds, duration, "".join(answer_parts)


def extract_tool_names(records: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []

    for record in records:
        event_type = str(record["event"]).lower()
        if "tool" not in event_type:
            continue

        payload = record["payload"]
        candidates = nested_values(
            payload,
            {"tool_name", "name", "tool"},
        )

        for candidate in candidates:
            if isinstance(candidate, str) and candidate not in names:
                names.append(candidate)

    return names


def has_event(records: list[dict[str, Any]], expected: str) -> bool:
    expected = expected.lower()
    return any(
        expected in str(record["event"]).lower()
        for record in records
    )


def tool_matches(actual: list[str], expected: str) -> bool:
    expected_lower = expected.lower()
    return any(expected_lower in name.lower() for name in actual)


def run_case(
    client: httpx.Client,
    config: dict[str, Any],
    variables: dict[str, str],
    case: dict[str, Any],
) -> dict[str, Any]:
    base_url = config["base_url"].rstrip("/")
    turn_spec = config["turn"]

    create_path = turn_spec["create_path"].format(**variables)
    payload_field = turn_spec.get("payload_field", "content")
    payload = {payload_field: case["input"]}

    started_at = time.perf_counter()
    response = client.post(base_url + create_path, json=payload)
    create_seconds = time.perf_counter() - started_at
    response.raise_for_status()

    body = response.json()
    turn_id = str(body[turn_spec.get("id_field", "id")])

    local_variables = dict(variables)
    local_variables["turn_id"] = turn_id

    events_path = turn_spec["events_path"].format(**local_variables)
    require_approval = bool(case.get("require_approval", False))

    records, ttft, stream_seconds, answer = parse_sse(
        client,
        base_url + events_path,
        float(config.get("stream_timeout_seconds", 120)),
        require_approval,
    )

    tool_names = extract_tool_names(records)
    expected_tools = case.get("expected_tools", [])
    forbidden_tools = case.get("forbidden_tools", [])
    expected_keywords = case.get("expected_keywords", [])

    expected_tools_ok = all(
        tool_matches(tool_names, tool)
        for tool in expected_tools
    )
    forbidden_tools_ok = all(
        not tool_matches(tool_names, tool)
        for tool in forbidden_tools
    )
    keywords_ok = all(
        keyword.lower() in answer.lower()
        for keyword in expected_keywords
    )

    if require_approval:
        terminal_ok = has_event(records, "approval.required")
    else:
        terminal_ok = has_event(records, "turn.completed")

    tool_started = sum(
        "tool.started" in str(item["event"]).lower()
        for item in records
    )
    tool_completed = sum(
        "tool.completed" in str(item["event"]).lower()
        for item in records
    )
    tool_failed = sum(
        "tool.failed" in str(item["event"]).lower()
        or "tool.error" in str(item["event"]).lower()
        for item in records
    )

    passed = (
        terminal_ok
        and expected_tools_ok
        and forbidden_tools_ok
        and keywords_ok
    )

    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "turn_id": turn_id,
        "passed": passed,
        "terminal_ok": terminal_ok,
        "expected_tools_ok": expected_tools_ok,
        "forbidden_tools_ok": forbidden_tools_ok,
        "keywords_ok": keywords_ok,
        "tools": "|".join(tool_names),
        "tool_started": tool_started,
        "tool_completed": tool_completed,
        "tool_failed": tool_failed,
        "create_seconds": round(create_seconds, 3),
        "ttft_seconds": round(ttft, 3) if ttft is not None else "",
        "stream_seconds": round(stream_seconds, 3),
        "answer": answer,
        "event_count": len(records),
    }


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(bool(item["passed"]) for item in results)

    ttfts = [
        float(item["ttft_seconds"])
        for item in results
        if item["ttft_seconds"] != ""
    ]
    durations = [float(item["stream_seconds"]) for item in results]

    tool_started = sum(int(item["tool_started"]) for item in results)
    tool_completed = sum(int(item["tool_completed"]) for item in results)
    tool_failed = sum(int(item["tool_failed"]) for item in results)

    return {
        "total_cases": total,
        "passed_cases": passed,
        "task_pass_rate": passed / total if total else 0,
        "terminal_event_rate": (
            sum(bool(item["terminal_ok"]) for item in results) / total
            if total else 0
        ),
        "tool_selection_rate": (
            sum(bool(item["expected_tools_ok"]) for item in results) / total
            if total else 0
        ),
        "forbidden_tool_safety_rate": (
            sum(bool(item["forbidden_tools_ok"]) for item in results) / total
            if total else 0
        ),
        "tool_started": tool_started,
        "tool_completed": tool_completed,
        "tool_failed": tool_failed,
        "tool_completion_rate": (
            tool_completed / tool_started if tool_started else None
        ),
        "ttft_p50_seconds": (
            statistics.median(ttfts) if ttfts else None
        ),
        "ttft_p95_seconds": percentile(ttfts, 0.95),
        "duration_p50_seconds": (
            statistics.median(durations) if durations else None
        ),
        "duration_p95_seconds": percentile(durations, 0.95),
    }


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    config = load_json(CONFIG_PATH)
    cases = load_cases(CASES_PATH)
    timeout = float(config.get("request_timeout_seconds", 30))

    with httpx.Client(timeout=timeout) as client:
        variables: dict[str, str] = {}


        session_id = create_resource(
            client,
            config["base_url"].rstrip("/"),
            config["session"],
            variables,
        )
        variables["session_id"] = session_id


        print(f"session_id={session_id}")

        results: list[dict[str, Any]] = []

        for index, case in enumerate(cases, start=1):
            print(f"[{index}/{len(cases)}] {case['case_id']}")
            try:
                # 每个用例独立 session，规避"同一会话只能一个 turn"的 409
                session = client.post(
                    config["base_url"].rstrip("/") + config["session"]["path"],
                    json=format_value(config["session"]["payload"], variables),
                )
                session.raise_for_status()
                session_body = session.json()
                variables["session_id"] = session_body["id"]
                variables["student_id"] = session_body["student_id"]
                result = run_case(client, config, variables, case)
            except Exception as exc:
                result = {
                    "case_id": case["case_id"],
                    "category": case["category"],
                    "turn_id": "",
                    "passed": False,
                    "terminal_ok": False,
                    "expected_tools_ok": False,
                    "forbidden_tools_ok": False,
                    "keywords_ok": False,
                    "tools": "",
                    "tool_started": 0,
                    "tool_completed": 0,
                    "tool_failed": 0,
                    "create_seconds": "",
                    "ttft_seconds": "",
                    "stream_seconds": "",
                    "answer": "",
                    "event_count": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                }

            results.append(result)
            print(
                f"  passed={result['passed']} "
                f"tools={result['tools']} "
                f"ttft={result['ttft_seconds']}"
            )
    durations = [
        float(item["stream_seconds"])
        for item in results
        if item["stream_seconds"] != ""
    ]

    field_names = sorted(
        {key for result in results for key in result.keys()}
    )

    csv_path = REPORT_DIR / "agent_results.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=field_names)
        writer.writeheader()
        writer.writerows(results)

    summary = build_summary(results)
    summary_path = REPORT_DIR / "agent_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"CSV report: {csv_path}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()