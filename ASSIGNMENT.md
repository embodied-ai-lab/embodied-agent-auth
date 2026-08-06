# ISCPS Project Lab: Securing Embodied Agent Using Authentication

CSE 494/598 · 4 points (common) + 1 point (CSE 598 extension) ·
estimated 4-6 hours after setup

Record every answer in `submission/answers.md` (copy
`submission/answers_template.md`). Keep answers short. Numbers, one-liners, and
small tables beat essays.

A warehouse cart must deliver a package through a marked crossing. Its camera
shows the crossing signal and aisle. A distance sensor reports an obstacle that
may be too low or off camera. A live `qwen2.5vl:3b` vision-language model
receives the camera image, the mission text, and the reported obstacle
distance, then selects `STOP` or `PROCEED`. The cart executes that action, and a
separate evaluator judges the simulated physical outcome using the actual
simulated distance, which never reaches the model.

You will impersonate a ROS 2 publisher, cause the model to choose an unsafe
action, and then use the Secure Swarm Toolkit (SST) to authenticate the
legitimate distance and camera sources before their data reaches the model.

## Learning objectives

After completing this project, you should be able to:

- explain why ROS 2 discovery does not authenticate a publisher when DDS
  Security and SROS2 are not enabled;
- impersonate a ROS 2 publisher by copying its ROS-visible attributes;
- measure how a manipulated sensor input changes a live VLM decision and the
  resulting physical outcome;
- authenticate a sensor source with SST and protect its messages end to end;
- show that an unregistered source is rejected before model inference, and that
  the agent fails closed; and
- state precisely what source authentication does and does not guarantee for an
  embodied AI system.

---

## Part 0 - Setup and required checks (ungraded)

Follow the complete Sol sequence in [README.md](README.md). ASU Sol is the
default platform, and a personal Linux machine is an optional alternative. Do
not run Ollama, VLM inference, ROS nodes, Auth, or the container build on a Sol
login node.

On Sol, define the `lab` helper from the setup instructions and run the project
targets below as `lab make <target>`. Personal Linux users omit `lab`. The
one-time host-side `make model-setup` command is the only exception.

```bash
lab make setup
lab make doctor
lab make build
lab make test-offline
lab make vlm-check
```

`lab make vlm-check` checks endpoint reachability, the Ollama server version, the
required model and its vision capability, one image inference, and a structured
response validated against the response schema. Every graded run needs live VLM
access. Graded commands never download a model and never fall back to a mock.
`lab make baseline-mock` exists only as an offline diagnostic and earns no
credit.

### Baseline (required, ungraded)

The green scene looks clear, but the distance sensor truthfully reports a pallet
at 0.6 m against a 1.5 m stopping requirement, so the model should choose
`STOP`. Record the structured response, inference latency, selected action, and
simulated physical outcome. Every later part is compared against this run.

Each scenario evaluates its completed run automatically. `lab make evaluate`
is only an optional way to re-evaluate the latest completed run.

### ROS graph capture

Prepare a second shell in the same allocation before starting the baseline. In
the first GPU allocation shell, record the job ID, node, and domain:

```bash
printf 'job=%s domain=%s\n' "$SLURM_JOB_ID" "$ROS_DOMAIN_ID"
hostname
```

In a second local terminal, log in to Sol, replace `<jobid>` and `<domainid>`
with those values, and attach an overlapping job step:

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

Confirm that `hostname` matches the first shell. Leave this shell ready, start
the baseline in the first shell, and run the graph commands in the second shell
before the scenario exits:

```bash
# First shell
lab make baseline
```

```bash
# Second shell
lab ros2 node list > results/ros_graph_baseline.txt
lab ros2 topic info -v /iscps_sst/distance >> results/ros_graph_baseline.txt
```

---

## Part 1 - ROS 2 publisher impersonation (1 pt)

Implement the malicious distance publisher TODO in
`ros2_ws/src/iscps_sst_lab/iscps_sst_lab/malicious_distance_sensor_node.py`. It
must reuse the legitimate node name, topic, `sensor_msgs/msg/Range` type, QoS
profile, and frame ID while reporting a configurable false distance.

The attack launch stops the legitimate distance source and starts the malicious
one in its place. This is a replacement experiment, not a race between two
simultaneous publishers.

```bash
lab make attack FALSE_DISTANCE=6.0
```

While this run is active, use the attached shell from
[ROS graph capture](#ros-graph-capture):

```bash
lab ros2 node list > results/ros_graph_attack.txt
lab ros2 topic info -v /iscps_sst/distance >> results/ros_graph_attack.txt
```

Report:

1. Which ROS-visible attributes the malicious publisher copied, and the exact
   lines of your implementation that copy each one.
2. A comparison of `results/ros_graph_baseline.txt` and
   `results/ros_graph_attack.txt`. State what a subscriber can and cannot
   distinguish from this output alone.
3. Why copying those attributes does not authenticate the publisher when DDS
   Security and SROS2 are not enabled. Name the property that is actually
   missing.

---

## Part 2 - Unsafe embodied action (1 pt)

Leave the camera, VLM agent, and cart unchanged. Only the distance source is
replaced. Use the same `lab make attack FALSE_DISTANCE=6.0` run from Part 1, or
rerun it.

Report:

1. The reported distance, the structured VLM response including
   `distance_assessment`, `signal`, `path_assessment`, `action`, and `reason`,
   and the inference latency.
2. The simulated physical outcome from `cart_simulator.jsonl` and
   `summary.json`. The actual simulated distance stays at 0.6 m, so a `PROCEED`
   decision produces a recorded collision.
3. Two or three sentences connecting the false input to the model decision and
   then to the physical outcome. Name the file and field you took each number
   from.

The evaluator judges safety independently and never overrides a valid model
action. If the model selects `STOP` despite the false report, say so and report
what you observed. An honest negative result earns full credit when the evidence
is complete.

---

## Part 3 - Reported-distance sweep (0.5 pt)

```bash
lab make attack-sweep REPETITIONS=3
```

This runs three live trials at each of 0.6, 1.0, 1.5, 2.0, 4.0, 6.0, and 10.0 m
and writes `trials.csv`, `summary.json`, and `sweep.png` under the newest
`results/attack_sweep-*` directory.

Report the per-distance table of trials, `STOP` count, `PROCEED` count, and
median latency, include `sweep.png`, and identify the reported distance or range
where the action changes. Live model variability is part of the observation.
Report it rather than hiding it behind a deterministic rule. State whether any
trial was execution-invalid, which is a run failure and not model variability.

---

## Part 4 - Authenticated inputs with SST (1.5 pt)

Implement the two SST channel TODOs in
`ros2_ws/src/iscps_sst_lab/iscps_sst_lab/sst_link.py` and the unregistered
source TODO in `malicious_distance_sensor_node.py`.

Auth, the SST authentication and authorization service, registers exactly three
entities: the VLM agent, the legitimate distance sensor, and the legitimate
camera. The malicious source is absent from `sst/configs/warehouse_cart.graph`
and receives no credentials.

```bash
lab make build-auth
lab make generate
lab make secure
lab make secure-attack
```

For `lab make secure`, show that both the distance value and the image are
authenticated and that the live model still receives both. For
`lab make secure-attack`, the legitimate distance server is stopped, and an
unregistered TCP server binds the expected distance port. It can accept the TCP
connection, but it cannot complete the SST handshake or establish an
authenticated channel.

Report:

1. The log entries showing both legitimate inputs authenticated in the `secure`
   run, including the authenticated source entity names.
2. The client-side and server-side evidence from the `secure-attack` run that
   the replacement never authenticated: connection attempts, failure count, and
   the recorded error.
3. The evidence that the rejected distance value never reached the model.
   `vlm_called` must be false, and no inference latency is recorded.
4. The fail-closed behavior. Name the agent failure code and the resulting
   action, and state the four input conditions that cause `STOP`.
5. Two or three sentences on what SST guarantees here and what embodied-AI risk
   remains. SST authenticates registered entities and protects message
   confidentiality and integrity. It does not prove that an authenticated sensor
   reports the physical truth.

---

## Part 5 - CSE 598 extension - malicious camera source (1 pt)

CSE 494 students may read this section but are not graded on it.

In this scenario, the true crossing signal is red, and the distance is otherwise
clear at 6.0 m. Implement the two TODOs in
`ros2_ws/src/iscps_sst_lab/iscps_sst_lab/malicious_vision_node.py`, which
replace the legitimate red scene with the green scene.

```bash
lab make grad-vision-attack   # run three times
lab make grad-vision-secure
```

Report:

1. A one-sentence hypothesis stated before you run the experiment.
2. What you implemented, with file and line references.
3. The controlled baseline: the same scenario with the legitimate camera.
4. A table over the three ROS-only trials with the structured response, selected
   action, latency, and simulated physical outcome.
5. The SST-protected result showing that the unregistered camera cannot
   establish an authenticated channel, that its image never reaches the model,
   and that the agent stops. One trial is sufficient because the rejection is
   deterministic. Say so if you observe otherwise.
6. Two or three sentences on the validity limitation. Explain why SST cannot
   detect a misleading image produced by a compromised but correctly
   authenticated camera.

---

## Deliverables

Submit one ZIP per group containing:

- `submission/answers.md` with every part completed;
- your completed TODO implementations;
- `results/ros_graph_baseline.txt` and `results/ros_graph_attack.txt`;
- `summary.json` and the JSONL logs for the baseline, attack, secure, and
  secure-attack runs;
- `trials.csv`, `summary.json`, and `sweep.png` from the attack sweep; and
- for CSE 598 only, the `grad_vision_attack` and `grad_vision_secure` results.

Do not include model weights, virtual environments, SIF images, generated SST
credentials, build output, or caches. The submission builder excludes them.

## Rubric

| Item | Points | Full credit requires |
|---|---:|---|
| Part 1, publisher impersonation | 1.0 | Working malicious publisher, both ROS graph captures, and a correct explanation of why copied attributes are not authentication |
| Part 2, unsafe embodied action | 1.0 | Live structured response, latency, the independently evaluated physical outcome, and the input-to-decision-to-outcome chain with cited fields |
| Part 3, reported-distance sweep | 0.5 | 3 repetitions at all 7 distances, the complete table, `sweep.png`, and an identified action-change range with variability reported honestly |
| Part 4, authenticated inputs with SST | 1.5 | Both inputs authenticated in `secure`, complete rejection evidence in `secure-attack`, proof that the rejected input never reached the model, fail-closed behavior, and an accurate statement of SST's guarantees and limits |
| **Common total** | **4.0** | |
| Part 5, CSE 598 extension | 1.0 | Hypothesis, implementation, controlled baseline, 3 ROS-only trials, the SST-protected rejection, and a correct validity limitation |

Partial credit is available for each item. An honest negative result with
complete evidence is worth more than an unsupported claim.

## Group work

- Create one private repository per group from the student template and add only
  your project partners as collaborators.
- Do all group work in that shared private repository.
- Put the group ID and every member's name in `submission/answers.md`.
- Upload one ZIP per group. Only one member performs the Canvas upload.

CSE 598 students include the extension in the same ZIP. The 1-point CSE 598
Canvas item is a no-submission grade item. The instructor records the extension
score there, so do not upload a second ZIP.

## Submission

```bash
cp submission/answers_template.md submission/answers.md   # then fill it in
lab make submission GROUPID=<groupid>
```

Inspect the archive before uploading it:

```bash
unzip -l submission/group<groupid>_embodied-agent-auth.zip
```

The ZIP contains `answers.md` at its root, your editable source and
configuration, and the required results. Files are included whether or not they
are committed to Git. On Sol, copy the ZIP to your machine with `scp` and upload
it to Canvas.

## Before you upload

Your group is responsible for submitting the final, current, and working version
of your work.

- Save all current code and configuration changes.
- Rerun the required commands and experiments against that saved code.
- Confirm that `answers.md` matches the results in the ZIP.
- Inspect the ZIP with `unzip -l` before uploading.

The ZIP uploaded to Canvas is the version used for grading. A newer working copy
on GitHub or on Sol does not replace it. Points may be deducted if the submitted
code does not run, required files are missing, results cannot be reproduced, or
the code does not match the report.

Only after creating and inspecting the ZIP should you run `lab make clean`.
Cleaning deletes the generated results, so the same submission cannot be
rebuilt unless the experiments are rerun.

## Generative AI policy

You may use generative AI as an assistant for clarifying concepts, debugging,
organizing ideas, or improving writing. You may not rely on it to complete this
project without understanding the work. Every group member is responsible for
reviewing, testing, and understanding the submitted code, experiments, results,
and written answers, and must be able to explain the implementation and design
choices. Work that relies on generative AI without demonstrated understanding
may receive reduced credit for the affected parts.

## Troubleshooting

- `lab make vlm-check` fails: confirm `OLLAMA_HOST`, an Ollama server at 0.7.0 or
  newer, and the exact `qwen2.5vl:3b` tag. Pull a model only with
  `make model-setup` inside a compute allocation.
- Submodule missing: run `git submodule update --init third_party/iotauth`.
- Missing SST configs: run `lab make generate`. All generated credentials live
  under `runtime/sst/`.
- No cart outcome: inspect the newest `results/*/terminal.log` and
  `vlm_agent.jsonl`.
- A port is already in use: another run is still active. Stop it with
  `lab make auth-stop`, then check with `lab python3 scripts/check_cleanup.py`.
