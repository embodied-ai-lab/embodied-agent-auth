from __future__ import annotations

import json
import subprocess


def test_submodule_commit_is_superproject_gitlink(repo_root):
    # An uninitialized submodule leaves an empty directory, and `git -C` there
    # silently resolves to the superproject. Check for the checkout first so the
    # failure names the real problem.
    assert (repo_root / "third_party/iotauth/entity/python/pyproject.toml").is_file(), (
        "third_party/iotauth is not initialized. "
        "Run: git submodule update --init third_party/iotauth"
    )
    recorded = subprocess.check_output(
        ["git", "ls-tree", "HEAD", "third_party/iotauth"],
        cwd=repo_root,
        text=True,
    ).split()[2]
    actual = subprocess.check_output(
        ["git", "-C", "third_party/iotauth", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
    ).strip()
    assert actual == recorded


def test_submodule_is_the_only_source_dependency(repo_root):
    assert not (repo_root / ".deps" / "iotauth").exists()
    modules = (repo_root / ".gitmodules").read_text()
    assert "branch =" not in modules
    lock = json.loads((repo_root / "dependency-lock.json").read_text())
    iotauth = lock["dependencies"]["iotauth"]
    assert "commit" not in iotauth
    assert iotauth["submodule_path"] == "third_party/iotauth"
    assert "third_party/iotauth/entity/python" in iotauth["python_package"][
        "install_command"
    ]


def test_generation_uses_disposable_runtime_work_tree(repo_root):
    script = (repo_root / "sst/scripts/generate_runtime.sh").read_text()
    assert "runtime" in script
    assert "iotauth-generation" in script
    assert "git -C" in script and "archive HEAD" in script
    assert ".deps" not in script
