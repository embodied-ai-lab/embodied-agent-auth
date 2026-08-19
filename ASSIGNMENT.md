# Embodied AI Lab: Securing an Embodied Agent with Authentication

CSE 494/598 · 4 common points + 1 CSE 598 extension point · approximately
4-6 hours after setup

Copy `submission/answers_template.md` to `submission/answers.md`. Keep answers
short and cite the result file and field behind each claim.

A live `qwen2.5vl:3b` model selects `STOP` or `PROCEED` from a camera image,
mission, and reported obstacle distance. The cart receives only that action.
After ROS stops, an independent evaluator uses ground truth to judge the
recorded execution; neither the cart nor VLM receives ground truth.

You will impersonate ROS 2 sensor publishers, measure the effect on the VLM,
and use SST to authenticate legitimate sources.

## ROS nodes and source files

### Default nodes

The default experiment graph uses these nodes:

| Role | ROS node name | Executable | Python source |
|---|---|---|---|
| Distance sensor | `/distance_sensor_node` | `distance_sensor_node` | [`distance_sensor.py`](ros2_ws/src/lab/distance_sensor.py) |
| Camera | `/vision_node` | `vision_node` | [`vision.py`](ros2_ws/src/lab/vision.py) |
| VLM agent | `/vlm_agent_node` | `vlm_agent_node` | [`vlm.py`](ros2_ws/src/lab/vlm.py) |
| Cart | `/cart_simulator_node` | `cart_simulator_node` | [`cart.py`](ros2_ws/src/lab/cart.py) |

### Malicious replacement nodes

Attack modes replace one legitimate sensor with one of these executables. The
replacement deliberately uses the legitimate node's ROS name; the executable
and source filename remain distinct.

| Role | ROS node name used | Executable | Python source |
|---|---|---|---|
| Distance replacement | `/distance_sensor_node` | `malicious_distance_sensor_node` | [`malicious_distance_sensor.py`](ros2_ws/src/lab/malicious_distance_sensor.py) |
| Vision replacement | `/vision_node` | `malicious_vision_node` | [`malicious_vision.py`](ros2_ws/src/lab/malicious_vision.py) |

## Part 0 - Setup and baseline (required, ungraded)

Follow [README.md](README.md). On Sol, use the documented `lab` wrapper for
every project command except the one-time host-side model download.

```bash
lab make setup
lab make doctor
lab make build
lab make test-offline
lab make vlm-check
lab make baseline
```

Every graded inference must use the live model. The baseline uses a green scene
and a truthful 0.6 m obstacle report against a 1.5 m stopping requirement.
Record the response, latency, VLM action, cart execution, and physical outcome.
Each scenario evaluates itself only after ROS stops.

### ROS graph capture

Because discovery is limited to localhost, the capture shell must use the same
allocated node and ROS domain as the scenario. In the first GPU-allocation
shell, record:

```bash
printf 'job=%s domain=%s\n' "$SLURM_JOB_ID" "$ROS_DOMAIN_ID"
hostname
```

In a second local terminal, attach to that allocation:

```bash
ssh <asurite>@sol.asu.edu
srun --jobid=<jobid> --overlap --nodes=1 --ntasks=1 --pty bash
hostname
module load apptainer/1.4.5
cd /scratch/$USER/<PRIVATE_REPOSITORY>
export SIF=/scratch/$USER/embodied-agent-auth.sif
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export ROS_DOMAIN_ID=<domainid>
export APPTAINERENV_ROS_AUTOMATIC_DISCOVERY_RANGE="$ROS_AUTOMATIC_DISCOVERY_RANGE"
export APPTAINERENV_ROS_DOMAIN_ID="$ROS_DOMAIN_ID"
lab() { apptainer exec --pwd "$PWD" "$SIF" "$@"; }
```

Confirm both `hostname` outputs match. Start the scenario in the first shell. And
wait until the first shell outputs a message like `[lab] started ros_launch (pid XXX)`,
then run the commands in the second shell to capture its graph before the first shell command exits:

```bash
# First shell
lab make baseline

# Second shell (after seeing [lab] started ros_launch ... in the first shell)
lab ros2 node list > results/ros_graph_baseline.txt
lab ros2 topic info -v /iscps_sst/distance >> results/ros_graph_baseline.txt
```

## Part 1 - ROS 2 publisher impersonation (1 pt)

Complete the TODOs in `ros2_ws/src/lab/malicious_distance_sensor.py`.
Reuse the legitimate node name, topic, `sensor_msgs/msg/Range` type, QoS, and
frame ID while reporting a configurable false distance. The attack replaces
the legitimate source; it is not a publisher race.

```bash
lab make attack FALSE_DISTANCE=6.0
```

While it runs, use the attached shell:

```bash
lab ros2 node list > results/ros_graph_attack.txt
lab ros2 topic info -v /iscps_sst/distance >> results/ros_graph_attack.txt
```

Report:

1. The copied attributes and exact implementation lines.
2. What differs—and what a subscriber cannot distinguish—between the graph
   captures.
3. Why copied discovery attributes are not source authentication when ROS 2's
   default configuration is used without DDS Security. Name the missing
   property.

## Part 2 - Unsafe embodied action (1 pt)

Use the Part 1 run or rerun it. Leave the camera, agent, and cart unchanged.

Report:

1. The reported distance, complete structured response, and latency from
   `vlm_agent.jsonl` or `summary.json`.
2. The cart's `action_executed` event from `cart_simulator.jsonl` and the
   post-run `physical_outcome` from `evaluation.jsonl` or `summary.json`.
3. Two or three sentences linking false input, VLM decision, cart execution,
   and outcome, with references to corresponding files and fields.

The cart executes the valid VLM action unchanged. Only the evaluator sees the
actual 0.6 m distance, so `PROCEED` moves the cart and is separately classified
as a collision. If the model selects `STOP`, report that supported negative
result; do not alter or hide it.

## Part 3 - Reported-distance sweep (0.5 pt)

```bash
lab make attack-sweep REPETITIONS=3
```

This runs three trials at 0.6, 1.0, 1.5, 2.0, 4.0, 6.0, and 10.0 m. Report the
`STOP`, `PROCEED`, and invalid counts plus median latency for every distance;
include `sweep.png`; identify where the action changes; and describe model
variability. An execution-invalid trial is a run failure, not variability.

## Part 4 - Authenticated inputs with SST (1.5 pt)

Complete the SST channel TODOs in `ros2_ws/src/lab/sst_link.py` and the
unregistered-source TODO in
`ros2_ws/src/lab/malicious_distance_sensor.py`. The malicious source has
no credentials and is absent from `sst/configs/warehouse_cart.graph`.

```bash
lab make build-auth
lab make generate
lab make secure
lab make secure-attack
```

Report:

1. Evidence that legitimate distance and camera inputs authenticated, including
   source entity names.
2. Client and server rejection evidence for the replacement: connection
   attempts, failure count, error, authentication status, and protected-message
   count.
3. Evidence the rejected value never reached the model: `vlm_called: false`
   and no inference latency.
4. The failure code, resulting `STOP`, and the four input conditions that fail
   closed: missing, stale, invalid, or unauthenticated.
5. What SST guarantees and what remains. It authenticates registered sources
   and protects confidentiality and integrity; it does not prove sensor truth.

## Part 5 - CSE 598 extension: malicious camera (1 pt)

CSE 494 students are not graded on this part. The true signal is red and the
actual distance is 6.0 m. Complete the TODOs in
`ros2_ws/src/lab/malicious_vision.py` to replace the legitimate red image
with the green image.

```bash
lab make grad-vision-baseline # legitimate camera; run once
lab make grad-vision-attack   # run three times
lab make grad-vision-secure   # run once
```

Report:

1. A one-sentence hypothesis written before running.
2. The implementation with file and line references.
3. The controlled baseline using the same scenario and legitimate camera.
4. Three ROS-only trials with response, action, latency, cart execution, and
   independent outcome.
5. One trial of an attack against SST-protected nodes proving the unregistered
   camera never authenticates, its image never reaches the model, and the
   agent stops.
6. Why SST cannot detect a misleading image from a compromised but correctly
   authenticated camera.

## Deliverables and rubric

Submit one ZIP per group. It must contain `answers.md`, completed TODO sources,
both ROS graph captures, required JSONL logs and summaries for each scenario,
the sweep table and figure, and—for CSE 598—the three vision-mode results. Do
not include credentials, model weights, a SIF, `.venv`, build output, or caches.

| Item | Points | Full credit requires |
|---|---:|---|
| Publisher impersonation | 1.0 | Working publisher, two graph captures, correct authentication explanation |
| Unsafe embodied action | 1.0 | Live response and latency, unchanged cart execution, independent outcome, cited causal chain |
| Distance sweep | 0.5 | 3 trials at all 7 distances, table, figure, change range, honest variability |
| SST protection | 1.5 | Two authenticated inputs, complete rejection/no-inference evidence, fail-closed behavior, correct limits |
| **Common total** | **4.0** | |
| CSE 598 camera extension | 1.0 | Hypothesis, implementation, control, 3 attack trials, protected rejection, validity limit |

Partial credit is available. Evidence-backed negative results receive full
credit when they satisfy the requested analysis.

## Submission

Use one private repository and one Canvas ZIP per group. List every member in
`submission/answers.md`; include CSE 598 work in the same ZIP.

```bash
cp submission/answers_template.md submission/answers.md
# Fill it in, then:
lab make submission GROUPID=<groupid>
unzip -l submission/group<groupid>_embodied-agent-auth.zip
```

The ZIP includes current files whether or not they are committed. Save your
work, rerun the required experiments, check that answers match results, and
inspect the ZIP. Canvas grades the uploaded ZIP; later GitHub or Sol changes do
not replace it.

Only after creating and inspecting the ZIP may you run `lab make clean`.
Cleaning deletes the results needed to rebuild the submission.

## Generative AI policy

You may use generative AI to clarify concepts, debug, organize, or edit prose.
Every group member remains responsible for understanding, testing, and
explaining the submitted code, results, and design choices.

## Troubleshooting

- VLM: verify `OLLAMA_HOST`, Ollama 0.7.0 or newer, and `qwen2.5vl:3b`; only
  host-side `make model-setup` downloads the model.
- Submodule: run `git submodule update --init third_party/iotauth`.
- SST state: run `lab make generate`; generated credentials stay in
  `runtime/sst/`.
- Missing evaluation: inspect the newest `terminal.log`, `vlm_agent.jsonl`, and
  `cart_simulator.jsonl`.
- Busy process or port: run `lab make auth-stop`, then both cleanup checks from
  [README.md](README.md#5-submit-before-cleaning).
