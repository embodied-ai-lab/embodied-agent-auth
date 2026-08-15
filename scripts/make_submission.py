#!/usr/bin/env python3
"""Build the group submission archive for Canvas.

Usage:
    python3 scripts/make_submission.py --groupid <groupid> \
        [--zip submission/group<groupid>_embodied-agent-auth.zip] \
        [--allow-missing-results]

Included:
- submission/answers.md, stored as answers.md at the archive root
- every student-editable file under assets/, configs/, containers/,
  ros2_ws/src/, scripts/, slurm/, sst/, and tests/, plus Makefile,
  pyproject.toml, and dependency-lock.json
- results/ros_graph_baseline.txt and results/ros_graph_attack.txt
- from each results/ run directory: manifest.json, summary.json, summary.csv,
  trials.csv, every *.jsonl log, terminal.log, and every figure
- the CSE 598 extension results when they are present

Never included: generated SST credentials and keys, Auth databases, runtime
state, model weights, virtual environments, build output, container images,
caches, prior submission archives, instructor material, or any single file
above 20 MB.

Git is not used. Files are included whether they are committed, modified, or
untracked.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MAX_FILE_BYTES = 20 * 1024 * 1024

PROJECT_DIRECTORIES = (
    "assets",
    "configs",
    "containers",
    "ros2_ws/src",
    "scripts",
    "slurm",
    "sst",
    "tests",
)
PROJECT_FILES = (
    "Makefile",
    "dependency-lock.json",
    "pyproject.toml",
)

# Student work that must exist before a submission is worth building.
REQUIRED_SOURCE_FILES = (
    "configs/ground_truth.yaml",
    "configs/scenario.yaml",
    "configs/sst.yaml",
    "configs/topics.yaml",
    "configs/vlm.yaml",
    "ros2_ws/src/lab/malicious_distance_sensor_node.py",
    "ros2_ws/src/lab/malicious_vision_node.py",
    "ros2_ws/src/lab/sst_link.py",
    "ros2_ws/src/lab/vlm.py",
    "ros2_ws/src/lab/validation.py",
)

# Standalone result files the assignment asks for by name.
REQUIRED_RESULT_FILES = (
    "results/ros_graph_attack.txt",
    "results/ros_graph_baseline.txt",
)

# Run directories required for the common 4-point work, as glob prefixes.
REQUIRED_RUN_GLOBS = (
    "attack-*",
    "attack_sweep-*",
    "baseline-*",
    "secure-*",
    "secure_attack-*",
)

# CSE 598 extension runs. Absence is reported but never fatal.
EXTENSION_RUN_GLOBS = (
    "grad_vision_baseline-*",
    "grad_vision_attack-*",
    "grad_vision_secure-*",
)

# Files collected from inside a results/ run directory.
RESULT_PATTERNS = (
    "*.jsonl",
    "*.png",
    "*.svg",
    "manifest.json",
    "summary.csv",
    "summary.json",
    "terminal.log",
    "trials.csv",
)

EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        ".cache",
        ".git",
        ".github",
        ".idea",
        ".ipynb_checkpoints",
        ".mypy_cache",
        ".nox",
        ".ollama",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        ".vscode",
        "__pycache__",
        "build",
        "install",
        "instructor",
        "log",
        "node_modules",
        "ollama",
        "runtime",
        "third_party",
        "venv",
    }
)

# Credentials and generated key material. These must never be packaged, even if
# a student copies one into an otherwise allowed directory.
SECRET_SUFFIXES = frozenset(
    {
        ".crt",
        ".csr",
        ".der",
        ".jks",
        ".key",
        ".keystore",
        ".mv.db",
        ".p12",
        ".pem",
        ".pfx",
        ".srl",
        ".trace.db",
    }
)
SECRET_NAME_FRAGMENTS = ("auth_password", "credential", "privatekey", "private_key")

EXCLUDED_SUFFIXES = frozenset(
    {
        ".7z",
        ".bz2",
        ".ckpt",
        ".db",
        ".gguf",
        ".gz",
        ".onnx",
        ".pt",
        ".pth",
        ".pyc",
        ".pyo",
        ".rar",
        ".safetensors",
        ".sif",
        ".simg",
        ".sqlite",
        ".sqlite3",
        ".swo",
        ".swp",
        ".tar",
        ".tgz",
        ".tmp",
        ".xz",
        ".zip",
        ".zst",
    }
)

# .log files are excluded except for the per-run launch log.
ALLOWED_LOG_NAMES = frozenset({"terminal.log"})

SUBMISSION_BUILDER = REPO / "scripts" / "make_submission.py"


def _is_inside_repo(path: Path) -> bool:
    try:
        path.relative_to(REPO)
    except ValueError:
        return False
    return True


def _secret_reason(path: Path) -> str | None:
    lowered = path.name.lower()
    if path.suffix.lower() in SECRET_SUFFIXES:
        return f"credential material ({path.suffix.lower()})"
    for fragment in SECRET_NAME_FRAGMENTS:
        if fragment in lowered:
            return f"credential material ({fragment})"
    return None


def _inspect_file(path: Path) -> tuple[Path | None, str | None]:
    """Return a safe regular file and no reason, or a concise skip reason."""
    reason = _secret_reason(path)
    if reason:
        return None, reason
    try:
        resolved = path.resolve(strict=True)
    except (FileNotFoundError, OSError, RuntimeError):
        return None, "cannot be resolved"
    if not _is_inside_repo(resolved):
        return None, "resolves outside the repository"
    if not resolved.is_file():
        return None, "not a regular file"
    reason = _secret_reason(resolved)
    if reason:
        return None, reason
    suffixes = {path.suffix.lower(), resolved.suffix.lower()}
    excluded = sorted(suffixes & EXCLUDED_SUFFIXES)
    if excluded:
        return None, f"excluded type ({excluded[0]})"
    if ".log" in suffixes and path.name not in ALLOWED_LOG_NAMES:
        return None, "excluded type (.log)"
    try:
        size = resolved.stat().st_size
    except OSError:
        return None, "cannot be read"
    if size > MAX_FILE_BYTES:
        return None, f"over {MAX_FILE_BYTES // (1024 * 1024)} MB"
    return resolved, None


def _walk(root: Path) -> list[Path]:
    """Return every regular file under root, skipping excluded directories."""
    if not root.is_dir():
        return []
    found: list[Path] = []
    for path in root.rglob("*"):
        relative = path.relative_to(REPO)
        if any(part in EXCLUDED_DIRECTORY_NAMES for part in relative.parts[:-1]):
            continue
        if path.is_dir() or path.is_symlink():
            continue
        found.append(path)
    return found


def _project_candidates() -> list[Path]:
    candidates: list[Path] = []
    for name in PROJECT_DIRECTORIES:
        candidates.extend(_walk(REPO / name))
    for name in PROJECT_FILES:
        path = REPO / name
        if path.is_file():
            candidates.append(path)
    return sorted(candidates, key=lambda path: path.relative_to(REPO).as_posix())


def _run_directories() -> list[Path]:
    results = REPO / "results"
    if not results.is_dir():
        return []
    return sorted(
        (path for path in results.iterdir() if path.is_dir() and not path.is_symlink()),
        key=lambda path: path.name,
    )


def _matching_runs(directories: list[Path], pattern: str) -> list[Path]:
    return [path for path in directories if fnmatch.fnmatch(path.name, pattern)]


def _result_candidates(directory: Path) -> list[Path]:
    matches: dict[str, Path] = {}
    for pattern in RESULT_PATTERNS:
        for path in directory.rglob(pattern):
            if path.is_dir() or path.is_symlink():
                continue
            matches[path.relative_to(REPO).as_posix()] = path
    return [matches[name] for name in sorted(matches)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groupid", required=True, help="your group ID; names the ZIP")
    parser.add_argument("--zip", type=Path, default=None, help="output ZIP path")
    parser.add_argument(
        "--allow-missing-results",
        action="store_true",
        help="report missing required results as warnings instead of failing",
    )
    args = parser.parse_args()

    group = str(args.groupid).strip()
    if not group:
        print("ERROR: --groupid must not be empty.", file=sys.stderr)
        return 2

    out_zip = args.zip or REPO / "submission" / f"group{group}_embodied-agent-auth.zip"
    if not out_zip.is_absolute():
        out_zip = REPO / out_zip

    answers = REPO / "submission" / "answers.md"
    if not answers.is_file():
        print(
            "ERROR: submission/answers.md not found.\n"
            "Copy submission/answers_template.md to submission/answers.md and "
            "fill it in.",
            file=sys.stderr,
        )
        return 2

    selected: dict[str, tuple[Path, str]] = {}
    skipped: dict[str, str] = {}
    problems: list[str] = []
    warnings: list[str] = []

    def add_file(path: Path, arcname: str, category: str) -> bool:
        resolved, reason = _inspect_file(path)
        if reason:
            skipped.setdefault(arcname, reason)
            return False
        assert resolved is not None
        selected.setdefault(arcname, (resolved, category))
        return True

    if not add_file(answers, "answers.md", "answers"):
        print(
            f"ERROR: submission/answers.md cannot be included: "
            f"{skipped['answers.md']}",
            file=sys.stderr,
        )
        return 2

    for path in _project_candidates():
        arcname = path.relative_to(REPO).as_posix()
        if path == SUBMISSION_BUILDER:
            skipped.setdefault(arcname, "submission builder excluded")
            continue
        add_file(path, arcname, "project")

    for relative in REQUIRED_SOURCE_FILES:
        if relative not in selected:
            problems.append(f"required source file is missing: {relative}")

    for relative in REQUIRED_RESULT_FILES:
        path = REPO / relative
        if path.is_file():
            add_file(path, relative, "result")
        else:
            problems.append(f"required result file is missing: {relative}")

    directories = _run_directories()
    for pattern in REQUIRED_RUN_GLOBS:
        if not _matching_runs(directories, pattern):
            problems.append(f"no results/{pattern} run directory was found")
    for pattern in EXTENSION_RUN_GLOBS:
        if not _matching_runs(directories, pattern):
            warnings.append(
                f"no results/{pattern} run directory was found "
                "(required only for the CSE 598 extension)"
            )

    for directory in directories:
        for path in _result_candidates(directory):
            arcname = path.relative_to(REPO).as_posix()
            resolved, reason = _inspect_file(path)
            if reason:
                skipped.setdefault(arcname, reason)
            else:
                assert resolved is not None
                selected.setdefault(arcname, (resolved, "result"))

    if problems:
        for problem in problems:
            print(f"ERROR: {problem}", file=sys.stderr)
        if not args.allow_missing_results:
            print(
                "\nRerun the missing experiments, or pass --allow-missing-results "
                "to build an incomplete archive on purpose.",
                file=sys.stderr,
            )
            return 2
        warnings.extend(problems)

    try:
        out_resolved = out_zip.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        print(f"ERROR: cannot resolve output ZIP path: {exc}", file=sys.stderr)
        return 2
    for arcname, (source, _) in selected.items():
        if out_resolved == source:
            print(
                f"ERROR: output ZIP would overwrite an input file: {arcname}",
                file=sys.stderr,
            )
            return 2

    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for arcname in sorted(selected):
            source, _ = selected[arcname]
            archive.write(source, arcname)

    counts = {"answers": 0, "project": 0, "result": 0}
    for _, category in selected.values():
        counts[category] += 1
    total_bytes = sum(source.stat().st_size for source, _ in selected.values())

    print(f"Output ZIP: {out_zip}")
    print(f"Archive size: {out_zip.stat().st_size / 1024:.1f} KiB")
    print(f"Total files included: {len(selected)} ({total_bytes / 1024:.1f} KiB raw)")
    print(f"  answers: {counts['answers']} file (answers.md)")
    print(f"  project: {counts['project']} files")
    print(f"  results: {counts['result']} files")
    print("Excluded: credentials, runtime state, model weights, build output, caches")
    print(f"Skipped files: {len(skipped)}")
    for arcname, reason in sorted(skipped.items()):
        print(f"  {arcname}: {reason}")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  {warning}")
    print("\nInspect the archive before uploading it to Canvas:")
    print(f"  unzip -l {out_zip.relative_to(REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
