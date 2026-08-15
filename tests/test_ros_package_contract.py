from __future__ import annotations


def test_flat_ros_package_installs_unified_launch(repo_root):
    package = repo_root / "ros2_ws/src/lab"
    setup_text = (package / "setup.py").read_text(encoding="utf-8")
    assert 'PACKAGE_NAME = "lab"' in setup_text
    assert 'package_dir={PACKAGE_NAME: "."}' in setup_text
    assert '["launch/lab.launch.py"]' in setup_text
    assert (package / "launch/lab.launch.py").is_file()
    assert (package / "resource/lab").is_file()
    assert (package / "agent_core.py").is_file()
    assert not (package / "lab").exists()


def test_flat_package_uses_normal_colcon_install(repo_root):
    build_script = (repo_root / "scripts/build.sh").read_text(encoding="utf-8")
    assert "colcon build" in build_script
    assert "--symlink-install" not in build_script
