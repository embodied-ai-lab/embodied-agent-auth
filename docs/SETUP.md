# Environment setup

ASU Sol is the default platform. A personal Linux workstation is an optional
alternative. In both cases you need the pinned `third_party/iotauth` submodule
and a live Ollama endpoint serving `qwen2.5vl:3b`.

[README.md](../README.md) has the short linear Sol path. This document is the
reference: what each step does, which environment it belongs to, and what must
be repeated in a new session.

Session tags used below:

- **[LOGIN NODE]** Safe on a `sol-login*` host.
- **[CPU ALLOCATION]** Needs a CPU compute allocation.
- **[GPU ALLOCATION]** Needs a GPU compute allocation.
- **[REPEAT]** Rerun in every new shell or allocation.
- **[PERSISTS]** Survives between sessions.
- **[CHECK]** Check existing state before repeating.

## What must never run on a login node

Never run any of these on a `sol-login*` host:

- Ollama, model downloads, or VLM inference
- ROS 2 nodes, `ros2 launch`, or `colcon build`
- Auth, the SST authentication and authorization service
- `apptainer build`
- any `make` target that starts a process or compiles code

`scripts/lib.sh` refuses to start a scenario when the hostname looks like a
login node, and the batch script refuses as well. Login nodes are for cloning,
editing, and submitting jobs.

## ASU Sol

These instructions follow the ASU Research Computing
[resource-request](https://docs.rc.asu.edu/requesting-resources/),
[Ollama](https://docs.rc.asu.edu/ollama/), and
[Apptainer](https://docs.rc.asu.edu/apptainer/) documentation. Site modules and
scheduler policy change over time. Confirm the account, partition, and QoS your
section is given, and use `module avail` to confirm a module version before
loading it.

### 1. Clone [LOGIN NODE] [PERSISTS]

```bash
cd /scratch/$USER
git clone --recurse-submodules git@github.com:<OWNER>/<PRIVATE_REPOSITORY>.git
cd <PRIVATE_REPOSITORY>
git submodule update --init third_party/iotauth
```

> **[CHECK]** `/scratch` is temporary and is not backed up. Confirm your files
> still exist at the start of each session, and keep your work pushed to your
> private GitHub repository.

### 2. Build the container image [CPU ALLOCATION] [PERSISTS]

```bash
interactive -A class_cse494598fall2026 -p public -q public -t 60 -c 4 --mem=16G
module load apptainer/1.4.5 squashfs-4.6.1-gcc-11.2.0
cd /scratch/$USER/<PRIVATE_REPOSITORY>
apptainer build /scratch/$USER/embodied-agent-auth.sif containers/Apptainer.def
```

The image contains ROS 2 Jazzy, colcon, the SST toolchain (Java, Maven, Node,
OpenSSL), and curl. It contains no model weights and no credentials. If your
instructor provides a prebuilt SIF, use that path and skip the build. If site
policy blocks `apptainer build` in your allocation, ask for the instructor SIF.
Do not fall back to building on a login node.

Exit the CPU allocation when the image exists.

### 3. Start Ollama [GPU ALLOCATION] [REPEAT]

The ROS nodes, Auth, and the model all use `127.0.0.1`, so the Ollama server
must run on the same allocated node as the experiments.

```bash
interactive -A class_cse494598fall2026 -p htc -q public -t 240 -c 8 --mem=32G \
    --gres=gpu:a100.20gb=1
module load apptainer/1.4.5 ollama/0.30.3
cd /scratch/$USER/<PRIVATE_REPOSITORY>

hostname
echo "$SLURM_JOB_ID"
nvidia-smi
ollama --version

export OLLAMA_MODELS=/scratch/$USER/ollama-models
export OLLAMA_HOST=http://127.0.0.1:11434
export VLM_MODEL=qwen2.5vl:3b
export VLM_TIMEOUT_S=90
mkdir -p "$OLLAMA_MODELS"

ollama serve > /scratch/$USER/ollama-serve.log 2>&1 &
OLLAMA_PID=$!
printf 'Ollama PID: %s\n' "$OLLAMA_PID"
curl "$OLLAMA_HOST/api/version"
```

Server startup is asynchronous. Wait for `/api/version` to answer before
running anything else. Before `ollama serve` starts, `ollama --version` may warn
that it cannot reach a server; the client version it prints is still the value
to record.

`module avail ollama` lists the available versions. Any version at 0.7.0 or
newer works. `ollama/0.30.3` is the version this project was validated against.

> **[REPEAT]** Load the module, export the variables, and start the server in
> every new allocation.
>
> **[CHECK]** If you reconnect to an allocation that is still running, check
> `/api/version` before starting a second server.
>
> Record `OLLAMA_PID`. Stop only that process. Never select one by name or port.

Download the model once. This is the only command in the project that downloads
a model:

```bash
make model-setup
```

> **[PERSISTS]** Do not download it again while it remains in
> `/scratch/$USER/ollama-models`.

At the end of the allocation, stop only the server you recorded:

```bash
kill -TERM "$OLLAMA_PID"
wait "$OLLAMA_PID"
```

### Alternative: a course-provided Ollama endpoint

If your instructor provides a shared endpoint, a CPU allocation is sufficient
because inference happens elsewhere. Skip `ollama serve` and `make model-setup`,
and set:

```bash
export OLLAMA_HOST=http://<COURSE_OLLAMA_HOST>:<PORT>
export VLM_MODEL=qwen2.5vl:3b
export VLM_TIMEOUT_S=90
curl "${OLLAMA_HOST%/}/api/version"
```

### 4. Run project commands inside the image [GPU ALLOCATION] [REPEAT]

Apptainer does not forward arbitrary environment variables. Export the
`APPTAINERENV_` copies so the container sees them:

```bash
export SIF=/scratch/$USER/embodied-agent-auth.sif
export APPTAINERENV_OLLAMA_HOST="$OLLAMA_HOST"
export APPTAINERENV_VLM_MODEL="$VLM_MODEL"
export APPTAINERENV_VLM_TIMEOUT_S="$VLM_TIMEOUT_S"
export APPTAINERENV_ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export APPTAINERENV_ROS_DOMAIN_ID=$((1 + SLURM_JOB_ID % 101))
lab() { apptainer exec --pwd "$PWD" "$SIF" "$@"; }

test -f "$SIF" || { echo "missing SIF: $SIF" >&2; }
lab curl "${OLLAMA_HOST%/}/api/version"
```

Deriving `ROS_DOMAIN_ID` from the job ID keeps concurrent groups on one node
from discovering each other's nodes. A domain ID is an isolation convenience,
not an authentication boundary. That is precisely the premise of Parts 1
through 3.

If `/scratch` or the repository path is not visible inside the container, add
explicit binds: `--bind /scratch/$USER:/scratch/$USER`.

```bash
lab make setup
lab make doctor
lab make build
lab make test-offline
lab make vlm-check
```

> **[PERSISTS]** `.venv` and the ROS workspace survive between sessions. Rerun
> setup or the build after source changes or `make clean`.
>
> **[REPEAT]** Run `make doctor` and `make vlm-check` in every new allocation or
> after changing the endpoint.

`make setup` creates `.venv` with `--system-site-packages` using the interpreter
that can import the installed ROS 2 `rclpy`, then installs pydantic, Pillow,
PyYAML, pytest, Ruff, and the SST Python API from
`third_party/iotauth/entity/python`. There is no separate `.deps` copy.

### 5. Batch alternative

`slurm/run_experiments.sbatch` runs the whole experiment set as one GPU job. It
starts and stops its own Ollama server, refuses login nodes, and never downloads
a model:

```bash
sbatch slurm/run_experiments.sbatch
squeue -u "$USER"
```

Results land under `results/` and the job log under `results/slurm-<jobid>.out`.
Edit `--account` if your group uses a different allocation.

### 6. Transfer the submission

Build the ZIP inside the allocation, then copy it from your own machine:

```bash
scp <asurite>@sol.asu.edu:/scratch/<asurite>/<PRIVATE_REPOSITORY>/submission/group<groupid>_embodied-agent-auth.zip .
```

## Optional: Linux workstation

Target Ubuntu 24.04 with ROS 2 Jazzy and either a local GPU-backed Ollama server
or a reachable course endpoint. WSL2 works as a Linux environment.

1. Install ROS 2 Jazzy using the
   [official instructions](https://docs.ros.org/en/jazzy/).
2. Install Git, Python 3.10 through 3.12, Java 11 or newer, Maven, Node and npm,
   OpenSSL, and make.
3. Clone and build:

```bash
git clone --recurse-submodules git@github.com:<OWNER>/<PRIVATE_REPOSITORY>.git
cd <PRIVATE_REPOSITORY>
git submodule update --init third_party/iotauth
source /opt/ros/jazzy/setup.bash
make setup
make doctor
make build
```

To host the model locally, install Ollama 0.7.0 or newer, start the server, and
then run:

```bash
export OLLAMA_HOST=http://127.0.0.1:11434
make model-setup
make vlm-check
```

For a course endpoint, set `OLLAMA_HOST` and run `make vlm-check` only. Do not
run `make model-setup`.

Inference latency depends on the machine, so local timings will not match Sol.

### Docker

The Docker image contains ROS 2 and the SST toolchain, but no model weights and
no runtime credentials:

```bash
git submodule update --init third_party/iotauth
docker build -t embodied-agent-auth -f containers/Dockerfile .
docker run --rm -it --network host \
  -e OLLAMA_HOST=http://127.0.0.1:11434 \
  embodied-agent-auth
```

Host networking gives the container local ROS discovery and the host Ollama
endpoint. Generate SST runtime state only after the container starts.

## Cleaning up

```bash
make auth-stop                        # stop only the Auth process this project started
python3 scripts/check_cleanup.py      # no stale PID files; ports 21900, 22101, 22102 free
python3 scripts/check_ros_cleanup.py  # no ROS nodes left in this domain
make clean                            # remove build output, runtime state, results, caches
```

`make clean` deletes generated results. Build your submission ZIP first.

Continue with the graded work in [ASSIGNMENT.md](../ASSIGNMENT.md).
