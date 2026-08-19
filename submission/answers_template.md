# Embodied AI Lab: Securing an Embodied Agent with Authentication

## Group information

- Group ID:
- Group members:
- Course: CSE 494 / CSE 598 (delete one)
- Date:
- Platform and Sol allocation or local machine:
- Ollama deployment, model tag, and server version:

> Copy this file to `submission/answers.md`. Keep answers short, cite evidence
> by path and field, then run `lab make submission GROUPID=<groupid>`.

## 0. Baseline (required, ungraded)

Command and run directory (`results/baseline-...`):

| reported distance | signal | path assessment | VLM action | action executed | execution state | physical outcome | safe | latency (ms) |
|---|---|---|---|---|---|---|---|---:|
|  |  |  |  |  |  |  |  |  |

Anything unusual about the setup, or "nothing unusual":

## 1. ROS 2 publisher impersonation (1 pt)

**1.1 Copied ROS-visible attributes:**

| attribute | legitimate value | implementation file and line |
|---|---|---|
| node name |  |  |
| topic |  |  |
| message type |  |  |
| QoS |  |  |
| frame ID |  |  |

**1.2 Compare `results/ros_graph_baseline.txt` and
`results/ros_graph_attack.txt`. What can and cannot a subscriber distinguish?**

**1.3 Why is this not authentication when the default ROS 2 configuration is
used without DDS Security? Name the missing property.**

## 2. Unsafe embodied action (1 pt)

**2.1, 2.2, and 2.3 Fill in answers and table cells below.**

Command and run directory (`results/attack-...`):

| reported distance | ground-truth distance | distance assessment | signal | path assessment | VLM action | action executed | reason | latency (ms) |
|---|---|---|---|---|---|---|---|---:|
|  |  |  |  |  |  |  |  |  |

Cart execution (`action_executed`, state, and decision ID from
`cart_simulator.jsonl`):

Independent outcome (`physical_outcome` from `evaluation.jsonl`; outcome,
`safe`, and reason from `summary.json`):

**Connect the false input, VLM decision, cart execution, and independent
outcome in 2-3 sentences. Cite every value.**

## 3. Reported-distance sweep (0.5 pt)

Command and sweep directory (`results/attack_sweep-...`):

| distance (m) | trials | STOP | PROCEED | invalid | median latency (ms) |
|---:|---:|---:|---:|---:|---:|
| 0.6 |  |  |  |  |  |
| 1.0 |  |  |  |  |  |
| 1.5 |  |  |  |  |  |
| 2.0 |  |  |  |  |  |
| 4.0 |  |  |  |  |  |
| 6.0 |  |  |  |  |  |
| 10.0 |  |  |  |  |  |

Figure path:

**Where does the action change? What variability and invalid trials did you
observe?**

## 4. Authenticated inputs with SST (1.5 pt)

**4.1 Legitimate authentication:**

Commands and secure run directory (`results/secure-...`):

| input | authenticated | source entity | Auth group | evidence path and field |
|---|---|---|---|---|
| distance |  |  |  |  |
| camera |  |  |  |  |

**4.2 Rejection in `lab make secure-attack`:**

Secure-attack run directory (`results/secure_attack-...`):

| item | value | evidence path and field |
|---|---|---|
| malicious server bound port |  |  |
| agent connection attempts |  |  |
| client failed attempts |  |  |
| recorded error |  |  |
| `ever_authenticated` |  |  |
| protected messages received |  |  |

**4.3 Prove the rejected value never reached the model (`vlm_called` and
latency).**

**4.4 Give the failure code, action, and four conditions that fail closed.**

**4.5 State SST's guarantees and one remaining embodied-AI risk (2-3
sentences).**

## 5. CSE 598 extension: malicious camera (1 pt)

**5.1 Hypothesis written before running:**

**5.2 Implementation files and lines:**

**5.3 Controlled baseline (`lab make grad-vision-baseline`):**

| scene | ground-truth signal | ground-truth distance | VLM action | action executed | physical outcome | safe | run directory |
|---|---|---:|---|---|---|---|---|
|  |  |  |  |  |  |  |  |

**5.4 ROS-only replacement (`lab make grad-vision-attack`, three trials):**

| trial | reported signal | path assessment | VLM action | action executed | latency (ms) | physical outcome | safe | run directory |
|---:|---|---|---|---|---:|---|---|---|
| 1 |  |  |  |  |  |  |  |  |
| 2 |  |  |  |  |  |  |  |  |
| 3 |  |  |  |  |  |  |  |  |

**5.5 Rejection of an attack against SST-protected nodes (`lab make
grad-vision-secure`):**

Run directory (`results/grad_vision_secure-...`):

| item | value | evidence path and field |
|---|---|---|
| camera authenticated |  |  |
| protected images received |  |  |
| `vlm_called` |  |  |
| failure code |  |  |
| action and execution state |  |  |
| independent outcome |  |  |

**5.6 Why can SST not detect a misleading image from a compromised but
correctly authenticated camera? (2-3 sentences)**
