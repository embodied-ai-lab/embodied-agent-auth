from __future__ import annotations

import ast


def test_no_deterministic_image_classifier_in_agent_path(repo_root):
    agent_files = [
        repo_root / "ros2_ws/src/iscps_sst_lab/iscps_sst_lab/agent_core.py",
        repo_root / "ros2_ws/src/iscps_sst_lab/iscps_sst_lab/vlm.py",
        repo_root / "ros2_ws/src/iscps_sst_lab/iscps_sst_lab/vlm_agent_node.py",
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
    package = repo_root / "ros2_ws/src/iscps_sst_lab/iscps_sst_lab"
    assert not (package / "sst_transport.py").exists()
    assert not (package / "endpoint_announcement.py").exists()
    assert (package / "sst_link.py").exists()


def test_graded_commands_have_no_backend_selector(repo_root):
    makefile = (repo_root / "Makefile").read_text()
    config = (repo_root / "configs/vlm.yaml").read_text()
    launches = "\n".join(
        path.read_text()
        for path in (repo_root / "ros2_ws/src/iscps_sst_lab/launch").glob("*.launch.py")
    )
    assert "BACKEND" not in makefile
    assert "backend:" not in config
    assert "RuleDecisionBackend" not in launches
    for target in ("baseline", "attack", "attack-sweep", "secure", "secure-attack"):
        assert f"{target}:" in makefile
    assert "scripts/vlm_check.py" in (
        repo_root / "scripts/run_scenario.sh"
    ).read_text()


def test_mock_is_explicitly_not_graded(repo_root):
    makefile = (repo_root / "Makefile").read_text()
    script = (repo_root / "scripts/baseline_mock.py").read_text()
    assert "baseline-mock:" in makefile
    assert "NOT GRADED" in script
