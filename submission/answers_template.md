# ISCPS Project: Securing Multimodal Perception for a ROS 2 VLM-Based Embodied Agent

## Group information

- Group ID:
- Group members (all names):
- Course: CSE 494 / CSE 598 (delete one)
- Date:
- Platform used (Sol / local Linux / both):
- Node or machine, and allocation if on Sol:
- Ollama deployment (self-hosted on the allocated node, or course endpoint):
- Model tag and Ollama server version:

> Copy this file to `submission/answers.md`, fill it in, then build the ZIP:
> `python3 scripts/make_submission.py --groupid <your_groupid>`.
> The ZIP also contains your code and the required results.
> Keep answers short. Cite result files by path where asked.

## 0. Baseline (ungraded but required)

Command used:

| reported distance | signal | path assessment | action | latency (ms) | cart state | safe |
|---|---|---|---|---:|---|---|
|  |  |  |  |  |  |  |

Run directory (`results/baseline-...`):

One line on anything unusual about your setup, or "nothing unusual":

## 1. ROS 2 publisher impersonation (1 pt)

**1.1 Which ROS-visible attributes the malicious publisher copies, and where:**

| attribute | legitimate value | file and line in your implementation |
|---|---|---|
| node name |  |  |
| topic |  |  |
| message type |  |  |
| QoS profile |  |  |
| frame ID |  |  |

**1.2 Baseline versus attack ROS graph** (from `results/ros_graph_baseline.txt`
and `results/ros_graph_attack.txt`). What can and cannot a subscriber
distinguish from this output alone?

**1.3 Why copying those attributes is not authentication when DDS Security and
SROS2 are not enabled. Name the missing property:**

## 2. Unsafe embodied action (1 pt)

Command used:

| reported distance | actual simulated distance | distance assessment | signal | path assessment | action | reason | latency (ms) |
|---|---|---|---|---|---|---|---:|
|  |  |  |  |  |  |  |  |

Physical outcome (`cart_state`, `safe`, `reason` from `summary.json`):

Run directory (`results/attack-...`):

**Two or three sentences from the false input to the model decision to the
physical outcome. Name the file and field behind each number:**

## 3. Reported-distance sweep (0.5 pt)

Command used:

Sweep directory (`results/attack_sweep-...`):

| reported distance (m) | trials | STOP | PROCEED | invalid | median latency (ms) |
|---:|---:|---:|---:|---:|---:|
| 0.6 |  |  |  |  |  |
| 1.0 |  |  |  |  |  |
| 1.5 |  |  |  |  |  |
| 2.0 |  |  |  |  |  |
| 4.0 |  |  |  |  |  |
| 6.0 |  |  |  |  |  |
| 10.0 |  |  |  |  |  |

Figure: `results/attack_sweep-<stamp>-<id>/sweep.png`

**Where does the action change, and what variability did you observe? Were any
trials execution-invalid?**

## 4. Authenticated inputs with SST (1.5 pt)

Commands used:

**4.1 Both legitimate inputs authenticated in `make secure`:**

| input | authenticated | source entity | Auth group | evidence (file and field) |
|---|---|---|---|---|
| distance |  |  |  |  |
| camera |  |  |  |  |

Run directory (`results/secure-...`):

**4.2 Rejection evidence from `make secure-attack`:**

| item | value | evidence (file and field) |
|---|---|---|
| malicious server bound the port |  |  |
| agent connection attempts |  |  |
| client failed attempts |  |  |
| recorded client error |  |  |
| `ever_authenticated` |  |  |
| protected messages received |  |  |

Run directory (`results/secure_attack-...`):

**4.3 Evidence that the rejected value never reached the model
(`vlm_called`, latency):**

**4.4 Fail-closed behavior. Agent failure code, resulting action, and the four
input conditions that cause `STOP`:**

**4.5 What SST guarantees here and what embodied-AI risk remains (2-3
sentences):**

## 5. CSE 598 extension: malicious camera source (1 pt, CSE 598 only)

**5.1 Hypothesis (one sentence, written before running):**

**5.2 What you implemented (files and lines):**

**5.3 Controlled baseline (same scenario with the legitimate camera):**

| scene shown to the model | true signal | actual distance (m) | action | cart state | safe |
|---|---|---:|---|---|---|
|  |  |  |  |  |  |

**5.4 ROS-only camera replacement, three trials:**

| trial | signal reported by model | path assessment | action | latency (ms) | cart state | safe | run directory |
|---:|---|---|---|---:|---|---|---|
| 1 |  |  |  |  |  |  |  |
| 2 |  |  |  |  |  |  |  |
| 3 |  |  |  |  |  |  |  |

**5.5 SST-protected result (unregistered camera):**

| item | value | evidence (file and field) |
|---|---|---|
| camera authenticated |  |  |
| protected images received |  |  |
| `vlm_called` |  |  |
| agent failure code |  |  |
| action and cart state |  |  |

Run directory (`results/grad_vision_secure-...`):

**5.6 Validity limitation (2-3 sentences). Why can SST not detect a misleading
image from a compromised but correctly authenticated camera?**
