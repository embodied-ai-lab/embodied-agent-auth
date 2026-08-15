"""Checks for the group submission builder and the sweep figure.

These exercise the module against a synthetic repository tree so no artifact is
written into the real project.
"""

from __future__ import annotations

import csv
import importlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

RUN_MODES = (
    ("baseline-20260801T120000Z-a1", "baseline", "STOP", True, 909.0),
    ("attack-20260801T121000Z-b2", "attack", "PROCEED", True, 1155.1),
    ("secure-20260801T122000Z-c3", "secure", "STOP", True, 909.5),
    ("secure_attack-20260801T123000Z-d4", "secure-attack", "STOP", False, None),
)
EXTENSION_MODES = (
    ("grad_vision_baseline-20260801T123500Z-e0", "grad-vision-baseline", "STOP", True, 900.0),
    ("grad_vision_attack-20260801T124000Z-e5", "grad-vision-attack", "PROCEED", True, 987.8),
    ("grad_vision_secure-20260801T125000Z-f6", "grad-vision-secure", "STOP", False, None),
)
SWEEP_DIR = "attack_sweep-20260801T130000Z-99"
SWEEP_FIELDS = (
    "distance_m",
    "repetition",
    "status",
    "execution_valid",
    "expected_action_observed",
    "action",
    "cart_state",
    "safe",
    "latency_ms",
    "run_dir",
    "errors",
)


def _write_run(results: Path, name: str, mode: str, action: str, called: bool, latency):
    run = results / name
    run.mkdir(parents=True)
    (run / "manifest.json").write_text(json.dumps({"mode": mode}), encoding="utf-8")
    (run / "summary.json").write_text(
        json.dumps(
            {
                "mode": mode,
                "action": action,
                "vlm_called": called,
                "latency_ms": latency,
                "execution_valid": True,
            }
        ),
        encoding="utf-8",
    )
    (run / "summary.csv").write_text("mode,action\n" + f"{mode},{action}\n", encoding="utf-8")
    (run / "vlm_agent.jsonl").write_text(
        json.dumps({"kind": "vlm_decision", "action": action}) + "\n", encoding="utf-8"
    )
    (run / "cart_simulator.jsonl").write_text(
        json.dumps(
            {
                "kind": "action_executed",
                "decision_id": "decision-1",
                "action_executed": action,
                "cart_state": "STOPPED" if action == "STOP" else "MOVING",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (run / "evaluation.jsonl").write_text(
        json.dumps(
            {
                "kind": "physical_outcome",
                "decision_id": "decision-1",
                "action_evaluated": action,
                "safe": action == "STOP",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (run / "terminal.log").write_text("[INFO] launch\n", encoding="utf-8")


def _write_sweep(results: Path) -> Path:
    sweep = results / SWEEP_DIR
    sweep.mkdir(parents=True)
    rows = []
    for distance in ("0.6", "1.0", "1.5", "2.0", "4.0", "6.0", "10.0"):
        for repetition in (1, 2, 3):
            action = "PROCEED" if distance in {"1.5", "6.0"} else "STOP"
            rows.append(
                {
                    "distance_m": distance,
                    "repetition": repetition,
                    "status": "VALID",
                    "execution_valid": "True",
                    "expected_action_observed": "True",
                    "action": action,
                    "cart_state": "COLLISION" if action == "PROCEED" else "STOPPED",
                    "safe": str(action == "STOP"),
                    "latency_ms": 950.0,
                    "run_dir": str(sweep),
                    "errors": "",
                }
            )
    with (sweep / "trials.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(SWEEP_FIELDS))
        writer.writeheader()
        writer.writerows(rows)
    return sweep


@pytest.fixture
def project(tmp_path, repo_root) -> Path:
    """A minimal copy of the project laid out the way a student would have it."""
    root = tmp_path / "project"
    for name in ("configs", "scripts", "sst", "slurm", "containers"):
        shutil.copytree(repo_root / name, root / name)
    package = "ros2_ws/src/lab"
    shutil.copytree(repo_root / package, root / package)
    shutil.copytree(repo_root / "assets", root / "assets")
    for name in ("Makefile", "pyproject.toml", "dependency-lock.json"):
        shutil.copy2(repo_root / name, root / name)
    (root / "submission").mkdir()
    (root / "tests").mkdir()
    (root / "tests" / "conftest.py").write_text("", encoding="utf-8")

    results = root / "results"
    results.mkdir()
    (results / "ros_graph_baseline.txt").write_text("/vlm_agent_node\n", encoding="utf-8")
    (results / "ros_graph_attack.txt").write_text("/vlm_agent_node\n", encoding="utf-8")
    for name, mode, action, called, latency in RUN_MODES:
        _write_run(results, name, mode, action, called, latency)
    _write_sweep(results)
    return root


def _load_builder(project_root: Path):
    """Import make_submission with REPO pointing at the synthetic project."""
    sys.modules.pop("make_submission", None)
    module = importlib.import_module("make_submission")
    module.REPO = project_root
    module.SUBMISSION_BUILDER = project_root / "scripts" / "make_submission.py"
    return module


def _build(module, project_root: Path, *args: str) -> int:
    argv = sys.argv
    sys.argv = ["make_submission.py", *args]
    try:
        return module.main()
    finally:
        sys.argv = argv
        sys.modules.pop("make_submission", None)


def test_missing_answers_fails_clearly(project, capsys):
    module = _load_builder(project)
    assert _build(module, project, "--groupid", "07") == 2
    assert "answers.md not found" in capsys.readouterr().err


def test_missing_required_results_fails_clearly(project, capsys):
    (project / "submission" / "answers.md").write_text("# answers\n", encoding="utf-8")
    shutil.rmtree(project / "results" / SWEEP_DIR)
    module = _load_builder(project)
    assert _build(module, project, "--groupid", "07") == 2
    assert "attack_sweep-*" in capsys.readouterr().err


def test_missing_evaluator_truth_fails_clearly(project, capsys):
    (project / "submission" / "answers.md").write_text("# answers\n", encoding="utf-8")
    (project / "configs" / "ground_truth.yaml").unlink()
    module = _load_builder(project)
    assert _build(module, project, "--groupid", "07") == 2
    assert "configs/ground_truth.yaml" in capsys.readouterr().err


def test_archive_contains_answers_code_and_results(project, capsys):
    (project / "submission" / "answers.md").write_text("# answers\n", encoding="utf-8")
    module = _load_builder(project)
    assert _build(module, project, "--groupid", "07") == 0

    archive = project / "submission" / "group07_embodied-agent-auth.zip"
    assert archive.is_file()
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
    assert names == sorted(names), "entries must be deterministically sorted"
    assert len(names) == len(set(names)), "entries must not repeat"

    assert "answers.md" in names
    assert "Makefile" in names
    assert "configs/ground_truth.yaml" in names
    assert "configs/scenario.yaml" in names
    assert "ros2_ws/src/lab/sst_link.py" in names
    assert "results/ros_graph_baseline.txt" in names
    assert f"results/{SWEEP_DIR}/trials.csv" in names
    for name, *_ in RUN_MODES:
        assert f"results/{name}/summary.json" in names
        assert f"results/{name}/evaluation.jsonl" in names
        assert f"results/{name}/terminal.log" in names

    out = capsys.readouterr().out
    assert "Total files included" in out
    assert "unzip -l" in out


def test_archive_excludes_secrets_runtime_and_build_output(project):
    (project / "submission" / "answers.md").write_text("# answers\n", encoding="utf-8")
    (project / "runtime" / "sst" / "credentials").mkdir(parents=True)
    (project / "runtime" / "sst" / "credentials" / "a.key").write_text("k", encoding="utf-8")
    (project / "configs" / "leaked.pem").write_text("secret", encoding="utf-8")
    (project / "configs" / "weights.gguf").write_text("weights", encoding="utf-8")
    for name in (".venv", "build", "install", "log", "__pycache__"):
        directory = project / "scripts" / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "junk.txt").write_text("junk", encoding="utf-8")

    module = _load_builder(project)
    assert _build(module, project, "--groupid", "07") == 0
    with zipfile.ZipFile(project / "submission" / "group07_embodied-agent-auth.zip") as zf:
        names = zf.namelist()

    for forbidden in (".pem", ".key", ".gguf", "runtime/", ".venv", "/build/", "__pycache__"):
        assert not any(forbidden in name for name in names), forbidden
    assert not any(name.startswith("instructor/") for name in names)
    assert "scripts/make_submission.py" not in names


def test_extension_results_are_optional_but_included(project, capsys):
    (project / "submission" / "answers.md").write_text("# answers\n", encoding="utf-8")
    module = _load_builder(project)
    assert _build(module, project, "--groupid", "07") == 0
    assert "grad_vision_attack-*" in capsys.readouterr().out

    for name, mode, action, called, latency in EXTENSION_MODES:
        _write_run(project / "results", name, mode, action, called, latency)
    module = _load_builder(project)
    assert _build(module, project, "--groupid", "07") == 0
    with zipfile.ZipFile(project / "submission" / "group07_embodied-agent-auth.zip") as zf:
        names = zf.namelist()
    for name, *_ in EXTENSION_MODES:
        assert f"results/{name}/summary.json" in names


def test_zip_name_carries_the_group_id(project):
    (project / "submission" / "answers.md").write_text("# answers\n", encoding="utf-8")
    module = _load_builder(project)
    assert _build(module, project, "--groupid", "team-12") == 0
    assert (project / "submission" / "groupteam-12_embodied-agent-auth.zip").is_file()


def test_sweep_figure_is_rendered_from_the_summary(project):
    sweep = project / "results" / SWEEP_DIR
    with (sweep / "trials.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    import plot_sweep
    from sweep_summary import summarize

    summary = summarize(rows)
    assert summary["invalid_trials"] == 0
    assert summary["distances"]["6.0"]["proceed"] == 3
    (sweep / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

    figure = plot_sweep.render(summary, sweep / "sweep.png")
    assert figure.is_file()
    assert figure.stat().st_size > 1000

    from PIL import Image

    with Image.open(figure) as image:
        assert image.format == "PNG"
        assert image.width == plot_sweep.WIDTH
        assert image.height > plot_sweep.TOP


def test_sweep_figure_handles_an_empty_summary(tmp_path):
    import plot_sweep

    figure = plot_sweep.render({"distances": {}, "total_trials": 0}, tmp_path / "s.png")
    assert figure.is_file()
