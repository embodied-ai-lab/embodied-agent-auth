from __future__ import annotations

import json

from sweep_summary import summarize, trial_record


def write_summary(path, *, action, execution_valid=True, agent_status="ok"):
    path.write_text(
        json.dumps(
            {
                "execution_valid": execution_valid,
                "execution_failures": (
                    [] if execution_valid else ["cart evidence mismatch"]
                ),
                "expected_action_observed": action == "PROCEED",
                "action": action,
                "cart_state": "COLLISION" if action == "PROCEED" else "STOPPED",
                "safe": action == "STOP",
                "latency_ms": 12.5,
                "run_dir": "/tmp/result",
                "agent_status": agent_status,
            }
        ),
        encoding="utf-8",
    )


def test_valid_attack_stop_is_retained_as_valid_trial(tmp_path):
    path = tmp_path / "summary.json"
    write_summary(path, action="STOP")
    record = trial_record(
        path,
        distance_m="0.6",
        repetition="1",
        scenario_exit_code=0,
    )
    assert record["execution_valid"] is True
    assert record["expected_action_observed"] is False
    assert record["action"] == "STOP"


def test_valid_attack_proceed_is_retained_as_valid_trial(tmp_path):
    path = tmp_path / "summary.json"
    write_summary(path, action="PROCEED")
    record = trial_record(
        path,
        distance_m="6.0",
        repetition="1",
        scenario_exit_code=0,
    )
    assert record["execution_valid"] is True
    assert record["expected_action_observed"] is True
    assert record["action"] == "PROCEED"


def test_agent_ok_does_not_hide_execution_invalid_summary(tmp_path):
    path = tmp_path / "summary.json"
    write_summary(
        path,
        action="PROCEED",
        execution_valid=False,
        agent_status="ok",
    )
    record = trial_record(
        path,
        distance_m="6.0",
        repetition="1",
        scenario_exit_code=3,
    )
    assert record["execution_valid"] is False
    assert "cart evidence mismatch" in record["errors"]
    assert "scenario exit code 3" in record["errors"]


def test_missing_summary_is_invalid(tmp_path):
    record = trial_record(
        tmp_path / "missing.json",
        distance_m="6.0",
        repetition="1",
        scenario_exit_code=2,
    )
    assert record["execution_valid"] is False
    assert record["errors"] == "missing summary.json"


def test_sweep_passes_with_valid_stop_and_proceed_rows():
    summary = summarize(
        [
            {
                "distance_m": "0.6",
                "execution_valid": "True",
                "action": "STOP",
                "latency_ms": "10",
            },
            {
                "distance_m": "6.0",
                "execution_valid": "True",
                "action": "PROCEED",
                "latency_ms": "20",
            },
        ]
    )
    assert summary["passed"] is True
    assert summary["distances"]["0.6"]["stop"] == 1
    assert summary["distances"]["6.0"]["proceed"] == 1
