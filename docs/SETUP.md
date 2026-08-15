# Environment setup

[README.md](../README.md) is the runnable quick start. This page explains what
persists between ASU Sol sessions and gives local alternatives.

## Sol rules

Use `sol-login*` only for cloning, editing, Git, and Slurm submission. Use an
allocation for container builds, Ollama, model downloads, ROS, Auth, tests, and
experiments.

| State | Repeat? |
|---|---|
| repository and initialized IoTAuth submodule | check each session |
| Apptainer SIF | rebuild only when the definition changes |
| model under `/scratch/$USER/ollama-models` | download once while it exists |
| allocation, modules, Ollama process, environment, `lab` function | every new allocation |
| `.venv` and ROS build | rebuild after relevant source changes or cleaning |

`/scratch` is temporary and not backed up. Keep your work in the group's
private repository.

## CPU allocation: container image

```bash
interactive -A class_cse494598fall2026 -p public -q public -t 60 -c 4 --mem=16G
module load apptainer/1.4.5 squashfs-4.6.1-gcc-11.2.0
cd /scratch/$USER/<PRIVATE_REPOSITORY>
apptainer build /scratch/$USER/embodied-agent-auth.sif containers/Apptainer.def
```

Use an instructor-provided SIF if available. Never move this build to a login
node if site policy blocks it; ask the instructor instead.

## GPU allocation: Ollama and project

```bash
interactive -A class_cse494598fall2026 -p htc -q public -t 240 -c 8 --mem=32G \
    --gres=gpu:a100.20gb=1
module load apptainer/1.4.5 ollama/0.30.3
cd /scratch/$USER/<PRIVATE_REPOSITORY>

export OLLAMA_MODELS=/scratch/$USER/ollama-models
export OLLAMA_HOST=http://127.0.0.1:11434
export VLM_MODEL=qwen2.5vl:3b
export VLM_TIMEOUT_S=90
mkdir -p "$OLLAMA_MODELS"

ollama serve > /scratch/$USER/ollama-serve.log 2>&1 &
OLLAMA_PID=$!
trap 'kill "$OLLAMA_PID" 2>/dev/null || true' EXIT
curl "$OLLAMA_HOST/api/version"
```

Wait for the version endpoint. If the model is not already staged, run once on
the host compute node:

```bash
make model-setup
```

Then define the container wrapper:

```bash
export SIF=/scratch/$USER/embodied-agent-auth.sif
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export ROS_DOMAIN_ID=$((1 + SLURM_JOB_ID % 101))
export APPTAINERENV_OLLAMA_HOST="$OLLAMA_HOST"
export APPTAINERENV_VLM_MODEL="$VLM_MODEL"
export APPTAINERENV_VLM_TIMEOUT_S="$VLM_TIMEOUT_S"
export APPTAINERENV_ROS_AUTOMATIC_DISCOVERY_RANGE="$ROS_AUTOMATIC_DISCOVERY_RANGE"
export APPTAINERENV_ROS_DOMAIN_ID="$ROS_DOMAIN_ID"
lab() { apptainer exec --pwd "$PWD" "$SIF" "$@"; }
```

`ROS_DOMAIN_ID` reduces accidental discovery between jobs; it is not an
authentication boundary. If the repository is not visible in the container,
add `--bind /scratch/$USER:/scratch/$USER` to `lab`.

Run at the start of graded work and after relevant changes:

```bash
lab make setup
lab make doctor
lab make build
lab make test-offline
lab make vlm-check
```

`lab make setup` creates `.venv` with access to the container's ROS installation
and installs SST from `third_party/iotauth/entity/python`.

### Course-provided Ollama endpoint

If the instructor provides an endpoint, skip `ollama serve` and `make
model-setup`. A CPU allocation is enough because inference happens elsewhere:

```bash
export OLLAMA_HOST=http://<COURSE_OLLAMA_HOST>:<PORT>
export VLM_MODEL=qwen2.5vl:3b
export VLM_TIMEOUT_S=90
curl "${OLLAMA_HOST%/}/api/version"
```

Define the same `APPTAINERENV_` variables and `lab` wrapper afterward.

## Batch alternative

The batch script starts and stops Ollama but never downloads a model. Stage the
model and build the SIF first. The default runs Parts 0-4; CSE 598 groups enable
Part 5 explicitly:

```bash
sbatch slurm/run_experiments.sbatch
sbatch --export=ALL,RUN_GRAD_EXTENSION=1 slurm/run_experiments.sbatch
squeue -u "$USER"
```

Results go under `results/`; Slurm output uses `results/slurm-<jobid>.out`.
Interactive work is still required for the ROS graph captures in
[ASSIGNMENT.md](../ASSIGNMENT.md#ros-graph-capture).

## Optional local Linux

Ubuntu 24.04 with ROS 2 Jazzy and Python 3.10-3.12 is supported; WSL2 works as a
Linux environment. Install ROS using its official Jazzy instructions, plus
Git, make, Java 17, Maven, Node/npm, and OpenSSL. Then:

```bash
git submodule update --init third_party/iotauth
source /opt/ros/jazzy/setup.bash
make setup
make doctor
make build
make test-offline
make vlm-check
```

Use a local GPU-backed Ollama server or the course endpoint. Personal Linux
users omit `lab`; local inference timing may differ from Sol.

### Docker

The Docker image contains ROS and SST tooling, not model weights or credentials:

```bash
git submodule update --init third_party/iotauth
docker build -t embodied-agent-auth -f containers/Dockerfile .
docker run --rm -it --network host \
  -e OLLAMA_HOST=http://127.0.0.1:11434 \
  embodied-agent-auth
```

## Finish safely

Build and inspect the submission before cleaning:

```bash
lab make auth-stop
lab python3 scripts/check_cleanup.py
lab python3 scripts/check_ros_cleanup.py
lab make submission GROUPID=<groupid>
unzip -l submission/group<groupid>_embodied-agent-auth.zip
lab make clean
```

Cleaning removes build output, runtime state, results, and caches. Continue with
[ASSIGNMENT.md](../ASSIGNMENT.md).
