from __future__ import annotations


def test_student_batch_script_runs_every_required_experiment(repo_root):
    script = (repo_root / "slurm/run_experiments.sbatch").read_text(encoding="utf-8")
    assert "set -euo pipefail" in script
    for target in (
        "make setup",
        "make doctor",
        "make build",
        "make test-offline",
        "make vlm-check",
        "make baseline",
        "make attack FALSE_DISTANCE=6.0",
        "make attack-sweep",
        "make build-auth",
        "make generate",
        "make secure",
        "make secure-attack",
        "make grad-vision-baseline",
        "make grad-vision-attack",
        "make grad-vision-secure",
        "scripts/check_cleanup.py",
    ):
        assert target in script
    assert '${RUN_GRAD_EXTENSION:-0}' in script


def test_student_batch_script_never_pulls_a_model_and_refuses_login_nodes(repo_root):
    script = (repo_root / "slurm/run_experiments.sbatch").read_text(encoding="utf-8")
    assert "ollama pull" not in script
    assert "*login*" in script
    assert "Refusing to run on a login node." in script


def test_student_batch_restores_model_store_after_module_load(repo_root):
    script = (repo_root / "slurm/run_experiments.sbatch").read_text(encoding="utf-8")
    capture = 'LAB_MODEL_STORE="${OLLAMA_MODELS:-/scratch/${USER}/ollama-models}"'
    restore = 'export OLLAMA_MODELS="${LAB_MODEL_STORE}"'
    assert capture in script and restore in script
    assert script.index(capture) < script.index("module load ollama") < script.index(restore)


def test_student_batch_script_stops_only_its_recorded_ollama_pid(repo_root):
    script = (repo_root / "slurm/run_experiments.sbatch").read_text(encoding="utf-8")
    assert "OLLAMA_PID=$!" in script
    assert 'kill -TERM "${OLLAMA_PID}"' in script
    assert "pkill" not in script
    assert "killall" not in script
