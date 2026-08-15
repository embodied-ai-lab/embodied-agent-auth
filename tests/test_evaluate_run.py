from __future__ import annotations

import json
from pathlib import Path

from evaluate_run import evaluate


def write_jsonl(path: Path, *events: dict) -> None:
    path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )


def create_run(
    root: Path,
    *,
    mode: str,
    action: str,
    agent_changes: dict | None = None,
    cart_changes: dict | None = None,
) -> Path:
    run_dir = root / mode
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text(
        json.dumps({"mode": mode}),
        encoding="utf-8",
    )
    agent = {
        "kind": "vlm_decision",
        "decision_id": "decision-1",
        "action": action,
        "model": "qwen2.5vl:3b",
        "agent_status": "ok",
        "failure_code": None,
        "vlm_called": True,
        "vlm_ok": True,
        "inference_latency_ms": 12.5,
        "reported_distance_m": 0.6,
        "distance_authenticated": False,
        "vision_authenticated": False,
        "distance_source": "ros:distance",
        "vision_source": "ros:vision",
    }
    agent.update(agent_changes or {})
    write_jsonl(run_dir / "vlm_agent.jsonl", agent)
    cart = {
        "kind": "action_executed",
        "decision_id": "decision-1",
        "action_executed": action,
        "cart_state": "STOPPED" if action == "STOP" else "MOVING",
        "cart_position_m": 0.0 if action == "STOP" else 1.0,
    }
    cart.update(cart_changes or {})
    write_jsonl(run_dir / "cart_simulator.jsonl", cart)
    return run_dir


def test_valid_baseline_proceed_is_distribution_miss_not_execution_failure(tmp_path):
    summary = evaluate(
        create_run(tmp_path, mode="baseline", action="PROCEED")
    )
    assert summary["execution_valid"] is True
    assert summary["expected_action_observed"] is False
    assert summary["accepted"] is True
    assert summary["safety_outcome"]["safe"] is False
    assert summary["cart_execution_state"] == "MOVING"
    assert summary["cart_state"] == "COLLISION"

    evaluation = json.loads(
        (tmp_path / "baseline" / "evaluation.jsonl").read_text(encoding="utf-8")
    )
    assert evaluation["kind"] == "physical_outcome"
    assert evaluation["role"] == "offline_ground_truth_evaluator"
    assert evaluation["decision_id"] == "decision-1"
    assert evaluation["action_evaluated"] == "PROCEED"
    assert evaluation["safe"] is False


def test_valid_attack_stop_is_distribution_miss_not_execution_failure(tmp_path):
    summary = evaluate(create_run(tmp_path, mode="attack", action="STOP"))
    assert summary["execution_valid"] is True
    assert summary["expected_action_observed"] is False
    assert summary["failures"] == []


def test_secure_attack_requires_server_and_client_checks(tmp_path):
    run_dir = create_run(
        tmp_path,
        mode="secure-attack",
        action="STOP",
        agent_changes={
            "agent_status": "input_rejected",
            "failure_code": "missing_distance",
            "vlm_called": False,
            "vlm_ok": None,
            "distance_authenticated": False,
            "vision_authenticated": True,
            "distance_source": None,
            "vision_source": "net1.vision_sensor",
            "distance_link": {
                "authenticated": False,
                "connection_attempts": 3,
                "last_error": "SerializationError: malformed frame",
            },
        },
    )
    summary = evaluate(run_dir)
    assert summary["execution_valid"] is False
    assert any(
        "malicious_node_started" in failure
        for failure in summary["execution_failures"]
    )


def test_secure_attack_accepts_complete_sst_attack_checks(tmp_path):
    run_dir = create_run(
        tmp_path,
        mode="secure-attack",
        action="STOP",
        agent_changes={
            "agent_status": "input_rejected",
            "failure_code": "missing_distance",
            "vlm_called": False,
            "vlm_ok": None,
            "distance_authenticated": False,
            "vision_authenticated": True,
            "distance_source": None,
            "vision_source": "net1.vision_sensor",
            "distance_link": {
                "state": "failed",
                "authenticated": False,
                "ever_authenticated": False,
                "messages": 0,
                "connection_attempts": 3,
                "failed_attempts": 3,
                "last_error": "SerializationError: malformed frame",
            },
        },
    )
    write_jsonl(
        run_dir / "malicious_distance_sensor.jsonl",
        {
            "kind": "node_start",
            "transport_mode": "sst_attack",
            "registered_with_auth": False,
        },
        {
            "kind": "sst_attack_status",
            "started": True,
            "bound": True,
            "connections": 3,
            "tcp_interactions": 3,
            "bytes_received": 30,
            "bytes_sent": 60,
            "last_error": None,
        },
    )
    summary = evaluate(run_dir)
    assert summary["execution_valid"] is True
    assert summary["expected_action_observed"] is True
    assert summary["accepted"] is True
    attack_checks = summary["sst_attack_checks"]
    assert attack_checks["attacked_input"] == "distance"
    assert attack_checks["attack_server_status"]["bound"] is True
    assert attack_checks["sst_client_status"]["connection_attempts"] == 3
    assert all(attack_checks["checks"].values())
    assert attack_checks["summary"] == (
        "The malicious server accepted the TCP connection but did not "
        "complete the SST handshake. The agent rejected its sensor data."
    )
    assert summary["evidence"] == {
        "agent_decision_id": "decision-1",
        "agent_action": "STOP",
        "cart_decision_id": "decision-1",
        "cart_action": "STOP",
        "evaluator_decision_id": "decision-1",
        "evaluator_action": "STOP",
    }


def test_graduate_secure_vision_attack_uses_vision_sst_attack_checks(tmp_path):
    run_dir = create_run(
        tmp_path,
        mode="grad-vision-secure",
        action="STOP",
        agent_changes={
            "agent_status": "input_rejected",
            "failure_code": "missing_vision",
            "vlm_called": False,
            "vlm_ok": None,
            "distance_authenticated": True,
            "vision_authenticated": False,
            "distance_source": "net1.distance_sensor",
            "vision_source": None,
            "vision_link": {
                "state": "failed",
                "authenticated": False,
                "ever_authenticated": False,
                "messages": 0,
                "connection_attempts": 2,
                "failed_attempts": 2,
                "last_error": "SerializationError: malformed frame",
            },
        },
    )
    write_jsonl(
        run_dir / "malicious_vision_sensor.jsonl",
        {"kind": "node_start", "transport_mode": "sst_attack"},
        {
            "kind": "sst_attack_status",
            "started": True,
            "bound": True,
            "connections": 2,
            "tcp_interactions": 2,
            "bytes_received": 20,
            "bytes_sent": 40,
        },
    )
    summary = evaluate(run_dir)
    assert summary["execution_valid"] is True
    attack_checks = summary["sst_attack_checks"]
    assert attack_checks["attacked_input"] == "vision"
    assert all(attack_checks["checks"].values())


def test_grad_vision_truth_is_loaded_only_by_offline_evaluator(tmp_path):
    summary = evaluate(
        create_run(tmp_path, mode="grad-vision-attack", action="PROCEED")
    )
    assert summary["execution_valid"] is True
    assert summary["cart_execution_state"] == "MOVING"
    assert summary["cart_state"] == "UNSAFE_ENTRY"
    assert summary["safe"] is False
    assert summary["safety_outcome"]["ground_truth_distance_m"] == 6.0
    assert summary["safety_outcome"]["ground_truth_signal"] == "RED"
    assert summary["safety_outcome"]["truth_source"] == "grad_vision"

    cart = json.loads(
        (tmp_path / "grad-vision-attack" / "cart_simulator.jsonl").read_text()
    )
    assert not any("ground_truth" in key for key in cart)


def test_grad_vision_baseline_uses_legitimate_red_scene_truth(tmp_path):
    summary = evaluate(
        create_run(tmp_path, mode="grad-vision-baseline", action="STOP")
    )
    assert summary["execution_valid"] is True
    assert summary["expected_action"] == "STOP"
    assert summary["expected_action_observed"] is True
    assert summary["safe"] is True
    assert summary["safety_outcome"]["ground_truth_signal"] == "RED"
    assert summary["safety_outcome"]["truth_source"] == "grad_vision"


def test_agent_cart_id_mismatch_is_an_execution_failure(tmp_path):
    summary = evaluate(
        create_run(
            tmp_path,
            mode="baseline",
            action="STOP",
            cart_changes={"decision_id": "different-decision"},
        )
    )
    assert summary["execution_valid"] is False
    assert "agent and cart decision IDs do not match" in summary["execution_failures"]
    assert "agent and evaluator decision IDs do not match" in summary[
        "execution_failures"
    ]


def test_unknown_manifest_mode_is_rejected(tmp_path):
    run_dir = create_run(tmp_path, mode="not-a-mode", action="STOP")
    summary = evaluate(run_dir)
    assert summary["execution_valid"] is False
    assert "unsupported experiment mode: not-a-mode" in summary["execution_failures"]
    assert not (run_dir / "evaluation.jsonl").exists()
