from __future__ import annotations


def test_flat_ros_package_installs_unified_launch(repo_root):
    package = repo_root / "ros2_ws/src/lab"
    setup_text = (package / "setup.py").read_text(encoding="utf-8")
    assert 'PACKAGE_NAME = "lab"' in setup_text
    assert 'package_dir={PACKAGE_NAME: "."}' in setup_text
    assert '["launch/lab.launch.py"]' in setup_text
    assert (package / "launch/lab.launch.py").is_file()
    assert (package / "resource/lab").is_file()
    assert (package / "vlm.py").is_file()
    assert (package / "validation.py").is_file()
    for module in (
        "cart.py",
        "distance_sensor.py",
        "malicious_distance_sensor.py",
        "malicious_vision.py",
        "vision.py",
    ):
        assert (package / module).is_file()
    for removed in (
        "agent_core.py",
        "cart_simulator_node.py",
        "decision_schema.py",
        "distance_sensor_node.py",
        "image_validation.py",
        "malicious_distance_sensor_node.py",
        "malicious_vision_node.py",
        "sensor_payloads.py",
        "vision_node.py",
        "vlm_agent_node.py",
    ):
        assert not (package / removed).exists()
    assert not (package / "lab").exists()


def test_flat_package_uses_normal_colcon_install(repo_root):
    build_script = (repo_root / "scripts/build.sh").read_text(encoding="utf-8")
    assert "colcon build" in build_script
    assert "--symlink-install" not in build_script
