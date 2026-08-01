from __future__ import annotations

import subprocess


def test_no_secret_or_runtime_material_is_tracked(repo_root):
    files = subprocess.check_output(
        ["git", "ls-files"], cwd=repo_root, text=True
    ).splitlines()
    secret_suffixes = (
        ".pem",
        ".key",
        ".p12",
        ".pfx",
        ".jks",
        ".keystore",
        ".db",
        ".sqlite",
        ".gguf",
        ".safetensors",
    )
    offenders = [
        path
        for path in files
        if path.lower().endswith(secret_suffixes)
        or path.startswith("runtime/")
        or path.startswith(".deps/")
    ]
    assert offenders == []
