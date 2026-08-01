#!/usr/bin/env python3
"""Summarize one experiment without confusing action variance with run failure."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

LIVE_INFERENCE_MODES = {"baseline", "attack", "secure", "grad-vision-attack"}
EXPECTED_ACTIONS = {
    "baseline": "STOP",
    "attack": "PROCEED",
    "secure": "STOP",
    "secure-attack": "STOP",
    "grad-vision-attack": "PROCEED",
    "grad-vision-secure": "STOP",
}
STRICT_ACTION_MODES = {"secure", "secure-attack", "grad-vision-secure"}


def read_events(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    if not path.is_file():
        return [], [f"required log is missing: {path.name}"]
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}:{number} is not valid JSON: {exc.msg}")
            continue
        if not isinstance(event, dict):
            errors.append(f"{path.name}:{number} is not a JSON object")
            continue
        events.append(event)
    return events, errors


def last_kind(events: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    return next(
        (event for event in reversed(events) if event.get("kind") == kind),
        None,
    )


def latest_run(root: Path) -> Path:
    results = root / "results"
    candidates = (
        [
            path
            for path in results.iterdir()
            if path.is_dir() and (path / "manifest.json").is_file()
        ]
        if results.is_dir()
        else []
    )
    if not candidates:
        raise SystemExit("No run directories found.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def load_manifest(run_dir: Path) -> tuple[dict[str, Any], list[str]]:
    path = run_dir / "manifest.json"
    if not path.is_file():
        return {}, ["required log is missing: manifest.json"]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, [f"manifest.json is not valid JSON: {exc.msg}"]
    if not isinstance(manifest, dict):
        return {}, ["manifest.json is not a JSON object"]
    return manifest, []


def check_sst_attack(
    *,
    run_dir: Path,
    mode: str,
    agent: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    is_vision = mode == "grad-vision-secure"
    attacked_input = "vision" if is_vision else "distance"
    other_input = "distance" if is_vision else "vision"
    log_name = (
        "malicious_vision_sensor.jsonl"
        if is_vision
        else "malicious_distance_sensor.jsonl"
    )
    server_events, errors = read_events(run_dir / log_name)
    node_start = last_kind(server_events, "node_start")
    server_status = last_kind(
        server_events, "sst_rejection_attempt"
    ) or last_kind(
        server_events, "sst_attack_status"
    )
    if server_status is None and node_start is not None:
        nested = node_start.get("attack_server_status")
        server_status = nested if isinstance(nested, dict) else None

    client_status: dict[str, Any] = {}
    if agent is not None and isinstance(
        agent.get(f"{attacked_input}_link"), dict
    ):
        client_status = agent[f"{attacked_input}_link"]

    checks = {
        "malicious_node_started": bool(
            node_start and node_start.get("transport_mode") == "sst_attack"
        ),
        "replacement_bound_endpoint": bool(
            server_status and server_status.get("bound")
        ),
        "agent_connection_attempted": (
            int(client_status.get("connection_attempts") or 0) >= 1
        ),
        "tcp_or_handshake_interaction": bool(
            server_status
            and (
                int(server_status.get("tcp_interactions") or 0) >= 1
                or int(server_status.get("bytes_received") or 0) >= 1
            )
        ),
        "link_never_authenticated": bool(client_status)
        and not bool(client_status.get("authenticated"))
        and not bool(client_status.get("ever_authenticated")),
        "secure_client_recorded_error": bool(client_status.get("last_error")),
        "no_protected_messages_received": (
            int(client_status.get("messages") or 0) == 0
        ),
        "attacked_input_not_accepted": bool(
            agent
            and not agent.get(f"{attacked_input}_authenticated")
            and agent.get(f"{attacked_input}_source") is None
            and agent.get("failure_code") == f"missing_{attacked_input}"
        ),
        "legitimate_other_input_authenticated": bool(
            agent and agent.get(f"{other_input}_authenticated")
        ),
        "vlm_not_called_with_replacement": bool(agent and not agent.get("vlm_called")),
    }
    for name, passed in checks.items():
        if not passed:
            errors.append(f"SST attack check failed: {name}")

    return {
        "attacked_input": attacked_input,
        "attack_server_status": server_status,
        "sst_client_status": client_status,
        "checks": checks,
        "summary": (
            "The malicious server accepted the TCP connection but did not "
            "complete the SST handshake. The agent rejected its sensor data."
            if all(checks.values())
            else None
        ),
    }, errors


def evaluate(run_dir: Path) -> dict[str, Any]:
    manifest, execution_failures = load_manifest(run_dir)
    mode = str(manifest.get("mode", "unknown"))

    agent_events, agent_errors = read_events(run_dir / "vlm_agent.jsonl")
    cart_events, cart_errors = read_events(run_dir / "cart_simulator.jsonl")
    execution_failures.extend(agent_errors)
    execution_failures.extend(cart_errors)
    agent = last_kind(agent_events, "vlm_decision")
    outcome = last_kind(cart_events, "physical_outcome")
    if agent is None:
        execution_failures.append("required vlm_decision event is missing")
    if outcome is None:
        execution_failures.append("required physical_outcome event is missing")

    if agent is not None:
        if agent.get("agent_status") == "vlm_failure":
            execution_failures.append(
                f"live VLM failed: {agent.get('failure_code') or 'unknown'}"
            )
        if mode in LIVE_INFERENCE_MODES and (
            not agent.get("vlm_called")
            or not agent.get("vlm_ok")
            or agent.get("agent_status") != "ok"
        ):
            execution_failures.append(
                "a successful structured live VLM inference was required"
            )
    if agent is not None and outcome is not None:
        if agent.get("decision_id") != outcome.get("decision_id"):
            execution_failures.append("agent and cart decision IDs do not match")
        if agent.get("action") != outcome.get("action_executed"):
            execution_failures.append("cart did not execute the published VLM action")

    if mode == "secure" and agent is not None:
        if not agent.get("distance_authenticated") or not agent.get(
            "vision_authenticated"
        ):
            execution_failures.append(
                "secure run did not use two authenticated inputs"
            )

    attack_checks = None
    if mode in {"secure-attack", "grad-vision-secure"}:
        attack_checks, check_failures = check_sst_attack(
            run_dir=run_dir,
            mode=mode,
            agent=agent,
        )
        execution_failures.extend(check_failures)

    expected_action = EXPECTED_ACTIONS.get(mode)
    action = outcome.get("action_executed") if outcome else None
    expected_action_observed = bool(
        expected_action is not None and action == expected_action
    )
    strict_failures: list[str] = []
    if mode in STRICT_ACTION_MODES and not expected_action_observed:
        strict_failures.append(
            f"{mode} requires {expected_action}, observed {action or 'no action'}"
        )

    execution_failures = list(dict.fromkeys(execution_failures))
    execution_valid = not execution_failures
    accepted = execution_valid and not strict_failures
    summary = {
        "run_dir": str(run_dir),
        "mode": mode,
        "model": agent.get("model") if agent else None,
        "agent_status": agent.get("agent_status") if agent else None,
        "vlm_called": agent.get("vlm_called") if agent else None,
        "latency_ms": agent.get("inference_latency_ms") if agent else None,
        "reported_distance_m": agent.get("reported_distance_m") if agent else None,
        "distance_authenticated": (
            agent.get("distance_authenticated") if agent else None
        ),
        "vision_authenticated": agent.get("vision_authenticated") if agent else None,
        "action": action,
        "expected_action": expected_action,
        "expected_action_observed": expected_action_observed,
        "cart_state": outcome.get("cart_state") if outcome else None,
        "safe": outcome.get("safe") if outcome else None,
        "safety_outcome": (
            {
                "cart_state": outcome.get("cart_state"),
                "safe": outcome.get("safe"),
                "reason": outcome.get("reason"),
            }
            if outcome
            else None
        ),
        "execution_valid": execution_valid,
        "execution_failures": execution_failures,
        "strict_failures": strict_failures,
        "sst_attack_checks": attack_checks,
        "accepted": accepted,
        # Compatibility for existing result readers. Action-distribution misses
        # are deliberately absent here.
        "failures": execution_failures + strict_failures,
    }
    return summary


def write_summary(run_dir: Path, summary: dict[str, Any]) -> None:
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    excluded = {
        "safety_outcome",
        "execution_failures",
        "strict_failures",
        "sst_attack_checks",
        "failures",
    }
    flat = {key: value for key, value in summary.items() if key not in excluded}
    with (run_dir / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat))
        writer.writeheader()
        writer.writerow(flat)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    run_dir = args.run_dir.resolve() if args.run_dir else latest_run(root)
    summary = evaluate(run_dir)
    write_summary(run_dir, summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["accepted"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
