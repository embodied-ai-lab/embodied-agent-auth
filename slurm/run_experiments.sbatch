#!/bin/bash
# Run the common CSE 494/598 experiment commands as one GPU batch job on ASU Sol.
#
# Submit this from the repository root after the SIF exists and the model has
# been staged once with `make model-setup` inside an allocation:
#
#     sbatch slurm/run_experiments.sbatch
#     squeue -u "$USER"
#
# The default runs only the common CSE 494/598 experiments. CSE 598 groups run
# Part 5 in the same job with:
#
#     sbatch --export=ALL,RUN_GRAD_EXTENSION=1 \
#         slurm/run_experiments.sbatch
#
# Part 5 remains in the same final ZIP. No second Canvas upload is required.
#
# Change --account if your group uses a different allocation. Results land in
# results/ and the job log lands in results/slurm-<jobid>.out.

#SBATCH --job-name=embodied-agent-auth
#SBATCH --account=class_cse494598fall2026
#SBATCH --partition=public
#SBATCH --qos=public
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH -G a100.20gb:1
#SBATCH --time=0-04:00:00
#SBATCH --output=results/slurm-%j.out
#SBATCH --error=results/slurm-%j.err

set -euo pipefail

[[ "$(hostname -s)" != *login* ]] || {
  echo "Refusing to run on a login node." >&2
  exit 2
}

PROJECT_ROOT="${SLURM_SUBMIT_DIR:-$PWD}"
cd "${PROJECT_ROOT}"

SIF="${SIF:-/scratch/${USER}/embodied-agent-auth.sif}"
[[ -f "${SIF}" ]] || {
  echo "Missing container image: ${SIF}" >&2
  echo "Build it first in a CPU allocation. See README.md." >&2
  exit 2
}

module load apptainer/1.4.5
module load ollama/0.30.3

export OLLAMA_MODELS="${OLLAMA_MODELS:-/scratch/${USER}/ollama-models}"
export OLLAMA_HOST=http://127.0.0.1:11434
export VLM_MODEL=qwen2.5vl:3b
export VLM_TIMEOUT_S=90
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export ROS_DOMAIN_ID=$((1 + SLURM_JOB_ID % 101))
export APPTAINERENV_OLLAMA_HOST="${OLLAMA_HOST}"
export APPTAINERENV_VLM_MODEL="${VLM_MODEL}"
export APPTAINERENV_VLM_TIMEOUT_S="${VLM_TIMEOUT_S}"
export APPTAINERENV_ROS_AUTOMATIC_DISCOVERY_RANGE="${ROS_AUTOMATIC_DISCOVERY_RANGE}"
export APPTAINERENV_ROS_DOMAIN_ID="${ROS_DOMAIN_ID}"

mkdir -p "${OLLAMA_MODELS}"

OLLAMA_PID=""
cleanup() {
  local status=$?
  trap - EXIT INT TERM
  set +e
  apptainer exec --pwd "${PROJECT_ROOT}" "${SIF}" \
    "${PROJECT_ROOT}/sst/scripts/start_auth.sh" --stop
  if [[ -n "${OLLAMA_PID}" ]] && kill -0 "${OLLAMA_PID}" 2>/dev/null; then
    kill -TERM "${OLLAMA_PID}"
    wait "${OLLAMA_PID}" || true
  fi
  exit "${status}"
}
trap cleanup EXIT INT TERM

ollama serve >"results/ollama-${SLURM_JOB_ID}.log" 2>&1 &
OLLAMA_PID=$!
for _ in $(seq 1 90); do
  curl -fsS "${OLLAMA_HOST}/api/version" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS "${OLLAMA_HOST}/api/version"

# This job never downloads a model. Stage it once with `make model-setup`.
ollama show "${VLM_MODEL}" >/dev/null || {
  echo "Model ${VLM_MODEL} is not staged in ${OLLAMA_MODELS}." >&2
  echo "Run 'make model-setup' once inside an interactive allocation." >&2
  exit 2
}

lab() { apptainer exec --pwd "${PROJECT_ROOT}" "${SIF}" "$@"; }

lab make setup
lab make doctor
lab make build
lab make test-offline
lab make vlm-check

lab make baseline
lab make attack FALSE_DISTANCE=6.0
lab make attack-sweep REPETITIONS="${REPETITIONS:-3}"

lab make build-auth
lab make generate
lab make secure
lab make secure-attack

# CSE 598 extension. The common CSE 494/598 job skips Part 5 by default.
if [[ "${RUN_GRAD_EXTENSION:-0}" == "1" ]]; then
  for _ in 1 2 3; do
    lab make grad-vision-attack
  done
  lab make grad-vision-secure
fi

lab python3 scripts/check_cleanup.py
echo "All experiments finished. Results are under results/."
