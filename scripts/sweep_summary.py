#!/usr/bin/env python3
"""Record and summarize empirical attack-sweep trials."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

FIELDS = (
    "distance_m",
    "repetition",
    "status",
    "execution_valid",
    "expected_action_observed",
    "action",
    "cart_state",
    "safe",
    "latency_ms",
    "run_dir",
    "errors",
)


def trial_record(
    summary_path: Path,
    *,
    distance_m: str,
    repetition: str,
    scenario_exit_code: int,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "distance_m": distance_m,
        "repetition": repetition,
        "status": "INVALID",
        "execution_valid": False,
        "expected_action_observed": False,
        "action": None,
        "cart_state": None,
        "safe": None,
        "latency_ms": None,
        "run_dir": None,
        "errors": "",
    }
    errors: list[str] = []
    if not summary_path.is_file():
        errors.append("missing summary.json")
        record["errors"] = "|".join(errors)
        return record
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"unreadable summary.json: {exc}")
        record["errors"] = "|".join(errors)
        return record
    if not isinstance(summary, dict):
        errors.append("summary.json is not an object")
        record["errors"] = "|".join(errors)
        return record

    record.update(
        {
            "expected_action_observed": bool(
                summary.get("expected_action_observed")
            ),
            "action": summary.get("action"),
            "cart_state": summary.get("cart_state"),
            "safe": summary.get("safe"),
            "latency_ms": summary.get("latency_ms"),
            "run_dir": summary.get("run_dir"),
        }
    )
    if summary.get("execution_valid") is not True:
        errors.extend(summary.get("execution_failures") or ["execution_invalid"])
    if scenario_exit_code != 0:
        errors.append(f"scenario exit code {scenario_exit_code}")
    record["execution_valid"] = not errors
    record["status"] = "VALID" if not errors else "INVALID"
    record["errors"] = "|".join(str(error) for error in errors)
    return record


def summarize(rows: list[dict[str, str]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["distance_m"]].append(row)
    distances: dict[str, dict[str, Any]] = {}
    for distance, items in grouped.items():
        valid = [
            item for item in items if item["execution_valid"].lower() == "true"
        ]
        latency = [
            float(item["latency_ms"])
            for item in valid
            if item["latency_ms"] not in {"", "None"}
        ]
        distances[distance] = {
            "trials": len(items),
            "valid": len(valid),
            "invalid": len(items) - len(valid),
            "stop": sum(item["action"] == "STOP" for item in valid),
            "proceed": sum(item["action"] == "PROCEED" for item in valid),
            "median_latency_ms": statistics.median(latency) if latency else None,
        }
    invalid_trials = sum(
        row["execution_valid"].lower() != "true" for row in rows
    )
    return {
        "distances": distances,
        "total_trials": len(rows),
        "invalid_trials": invalid_trials,
        "passed": bool(rows) and invalid_trials == 0,
    }


def append_record(csv_path: Path, record: dict[str, Any]) -> None:
    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=FIELDS).writerow(record)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    record_parser = subparsers.add_parser("record")
    record_parser.add_argument("summary_path", type=Path)
    record_parser.add_argument("csv_path", type=Path)
    record_parser.add_argument("distance_m")
    record_parser.add_argument("repetition")
    record_parser.add_argument("scenario_exit_code", type=int)
    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("csv_path", type=Path)
    report_parser.add_argument("summary_path", type=Path)
    args = parser.parse_args()

    if args.command == "record":
        record = trial_record(
            args.summary_path,
            distance_m=args.distance_m,
            repetition=args.repetition,
            scenario_exit_code=args.scenario_exit_code,
        )
        append_record(args.csv_path, record)
        return 0 if record["execution_valid"] else 3

    with args.csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    summary = summarize(rows)
    args.summary_path.write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print("distance  VALID  STOP  PROCEED  ERROR  median_latency_ms")
    for distance, result in summary["distances"].items():
        median = result["median_latency_ms"]
        rendered_median = f"{median:.1f}" if median is not None else "n/a"
        print(
            f"{distance:>8}  {result['valid']:>5}  {result['stop']:>4}  "
            f"{result['proceed']:>7}  {result['invalid']:>5}  {rendered_median}"
        )
    return 0 if summary["passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
