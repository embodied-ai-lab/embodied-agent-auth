from __future__ import annotations


def test_ros_package_installs_shared_launch_helper(repo_root):
    package = repo_root / "ros2_ws/src/iscps_sst_lab"
    setup_text = (package / "setup.py").read_text(encoding="utf-8")
    assert 'glob("launch/*.py")' in setup_text
    assert (package / "launch/_common.py").is_file()
