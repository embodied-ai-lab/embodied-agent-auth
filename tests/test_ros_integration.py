from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.ros_integration


def test_unified_launch_description_constructs(repo_root):
    pytest.importorskip("launch")
    import importlib.util

    path = repo_root / "ros2_ws/src/lab/launch/lab.launch.py"
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.generate_launch_description() is not None


def run_live_scenario(repo_root: Path, mode: str) -> Path:
    if os.environ.get("ISCPS_RUN_ROS_SCENARIOS") != "1":
        pytest.skip("set ISCPS_RUN_ROS_SCENARIOS=1 with ROS and live Ollama ready")
    result = subprocess.run(
        [str(repo_root / "scripts/run_scenario.sh"), mode],
        cwd=repo_root,
        env={**os.environ, "DURATION": "150"},
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    run_dir = Path((repo_root / "runtime/last_run").read_text().strip())
    assert run_dir.is_dir()
    return run_dir


@pytest.mark.timeout(190)
def test_baseline_launch_produces_matching_execution_and_evaluation(repo_root):
    run_dir = run_live_scenario(repo_root, "baseline")
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["execution_valid"] is True
    agent_events = [
        json.loads(line)
        for line in (run_dir / "vlm_agent.jsonl").read_text().splitlines()
    ]
    cart_events = [
        json.loads(line)
        for line in (run_dir / "cart_simulator.jsonl").read_text().splitlines()
    ]
    agent = next(event for event in agent_events if event["kind"] == "vlm_decision")
    cart = next(
        event for event in cart_events if event["kind"] == "action_executed"
    )
    evaluation_events = [
        json.loads(line)
        for line in (run_dir / "evaluation.jsonl").read_text().splitlines()
    ]
    outcome = next(
        event for event in evaluation_events if event["kind"] == "physical_outcome"
    )
    assert agent["vlm_called"] and agent["vlm_ok"]
    assert cart["decision_id"] == agent["decision_id"] == outcome["decision_id"]
    assert cart["action_executed"] == agent["action"] == outcome["action_evaluated"]
    assert not any("ground_truth" in key for key in cart)


@pytest.mark.timeout(190)
def test_attack_launch_uses_deterministic_malicious_distance_replacement(repo_root):
    run_dir = run_live_scenario(repo_root, "attack")
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["execution_valid"] is True
    assert summary["reported_distance_m"] == 6.0
    malicious_events = [
        json.loads(line)
        for line in (
            run_dir / "malicious_distance_sensor.jsonl"
        ).read_text().splitlines()
    ]
    start = next(event for event in malicious_events if event["kind"] == "node_start")
    assert start["transport_mode"] == "ros"
    assert start["false_distance_m"] == 6.0
