"""List files that belong to a checkout or unpacked source archive.

Git is authoritative in a clone. Release archives do not contain ``.git``, so
callers fall back to scanning the archive while excluding tool-generated
working directories and the separately versioned third-party tree. Runtime
files are intentionally not excluded: if a source archive accidentally
contains credentials, the release checks must see them.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

GENERATED_DIRECTORIES = {
    ".deps",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "install",
    "log",
    "node_modules",
    "third_party",
}


def _git_files(root: Path) -> list[str] | None:
    """Return Git-tracked files, or ``None`` when Git metadata is unavailable."""

    try:
        top_level = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if top_level.returncode != 0:
            return None
        if Path(top_level.stdout.strip()).resolve() != root.resolve():
            return None
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return [line for line in result.stdout.splitlines() if line]


def repository_files(
    root: Path,
    *,
    include: Callable[[Path], bool] | None = None,
    allow_git: bool = True,
) -> list[str]:
    """Return repository-relative POSIX paths from a clone or source archive.

    Set ``allow_git=False`` to scan the filesystem only. Callers use that for
    directories where running Git is not permitted, such as the exported
    student template that the instructor commits by hand.
    """

    root = root.resolve()
    git_files = _git_files(root) if allow_git else None
    if git_files is not None:
        paths = [path for path in git_files if (root / path).is_file()]
    else:
        paths = []
        for current, directory_names, file_names in os.walk(root):
            directory_names[:] = sorted(
                name
                for name in directory_names
                if name not in GENERATED_DIRECTORIES
            )
            current_path = Path(current)
            for name in sorted(file_names):
                paths.append((current_path / name).relative_to(root).as_posix())

    if include is not None:
        paths = [path for path in paths if include(Path(path))]
    return sorted(paths)
