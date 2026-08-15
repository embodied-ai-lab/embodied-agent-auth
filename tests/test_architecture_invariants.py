from __future__ import annotations

import ast
import os
import subprocess


def test_no_deterministic_image_classifier_in_agent_path(repo_root):
    agent_files = [
        repo_root / "ros2_ws/src/lab/vlm.py",
    ]
    text = "\n".join(path.read_text() for path in agent_files)
    forbidden = (
        "vision_decode",
        "classify_signal",
        "RuleDecisionBackend",
        "ReplayVLMBackend",
        "SafetyEvaluator",
    )
    for name in forbidden:
        assert name not in text
    for path in agent_files:
        ast.parse(path.read_text())


def test_removed_general_transport_and_endpoint_protocol(repo_root):
    package = repo_root / "ros2_ws/src/lab"
    assert not (package / "sst_transport.py").exists()
    assert not (package / "endpoint_announcement.py").exists()
    assert (package / "sst_link.py").exists()


def test_graded_commands_have_no_backend_selector(repo_root):
    makefile = (repo_root / "Makefile").read_text()
    config = (repo_root / "configs/vlm.yaml").read_text()
    launches = (repo_root / "ros2_ws/src/lab/launch/lab.launch.py").read_text()
    assert "BACKEND" not in makefile
    assert "backend:" not in config
    assert "RuleDecisionBackend" not in launches
    for target in ("baseline", "attack", "attack-sweep", "secure", "secure-attack"):
        assert f"{target}:" in makefile
    assert "scripts/vlm_check.py" in (
        repo_root / "scripts/run_scenario.sh"
    ).read_text()


def test_cart_is_ground_truth_free_and_evaluation_is_offline(repo_root):
    package = repo_root / "ros2_ws/src/lab"
    cart = (package / "cart_simulator_node.py").read_text(encoding="utf-8")
    launch = (package / "launch/lab.launch.py").read_text(encoding="utf-8")
    evaluator = (repo_root / "scripts/evaluate_run.py").read_text(encoding="utf-8")
    runner = (repo_root / "scripts/run_scenario.sh").read_text(encoding="utf-8")

    assert not (package / "ground_truth.py").exists()
    for forbidden in ("ground_truth", "judge_action", "physical_outcome"):
        assert forbidden not in cart
    assert "ground_truth" not in launch
    assert '"action_executed"' in cart
    assert "load_truth" in evaluator
    assert 'configs" / "ground_truth.yaml"' in evaluator
    assert '"kind": "physical_outcome"' in evaluator
    assert runner.index("iscps_stop ros_launch") < runner.index("evaluate_run.py")

    scenario = (repo_root / "configs/scenario.yaml").read_text(encoding="utf-8")
    truth = (repo_root / "configs/ground_truth.yaml").read_text(encoding="utf-8")
    assert "ground_truth" not in scenario
    assert "ground_truth_distance_m" not in scenario
    assert "ground_truth_signal" not in scenario
    assert "obstacle_distance_m" in truth


def test_obsolete_mock_command_is_removed(repo_root):
    assert "baseline-mock" not in (repo_root / "Makefile").read_text()
    assert not (repo_root / "scripts/baseline_mock.py").exists()


def test_new_run_dir_initializes_runtime_directory(repo_root, tmp_path):
    subprocess.run(
        [
            "bash",
            "-c",
            """
set -euo pipefail
. "${REPO_ROOT}/scripts/lib.sh"
iscps_new_run_dir smoke >/dev/null
test -d "${ISCPS_RUNTIME_DIR}"
""",
        ],
        check=True,
        env={
            **os.environ,
            "ISCPS_LAB_ROOT": str(tmp_path),
            "REPO_ROOT": str(repo_root),
        },
    )
