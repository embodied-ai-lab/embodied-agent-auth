# Security and threat model

## Scope

This is a loopback-only educational security exercise. Use the malicious nodes
only against this repository's own processes on a machine you are authorized to
use. Do not point them at another student's processes, another host, or any
production system. Auth is the Secure Swarm Toolkit (SST) authentication and
authorization service. Run ROS, Auth, and live VLM inference only on a
workstation or an allocated compute node, never on a Sol login node.

## Project safeguards

- Runtime credentials, keys, databases, passwords, and generated configs stay
  under gitignored `runtime/sst/`.
- Run scripts signal only their recorded process groups and Auth PID. They
  never terminate processes by name or port owner.
- Graded commands preflight the live model. They never download a model or
  substitute a mock.
- Model failure and missing authenticated input both stop the cart. Only model
  failure marks the VLM experiment failed.

## Protected assets

The protected assets are:

- The numerical distance delivered to the VLM
- The camera bytes delivered to the VLM
- The VLM-selected cart action
- JSONL logs that correlate inputs, inference, actions, and simulated physical
  outcomes

## Trust assumptions

The cart, sensors, VLM agent, Auth, and Ollama server run on one trusted
workstation or allocated compute node for this teaching exercise. The attacker
does not compromise the operating system, Auth, the Ollama server, the VLM
agent, the cart simulator, or a legitimate sensor process.

## Attacker capabilities

The attacker can run a local ROS 2 node in the same domain, inspect discovery,
copy the legitimate publisher's ROS-visible attributes, stop a legitimate
source during the experiment, and bind a localhost sensor port when the
legitimate SST server is absent. The attacker has no legitimate SST credentials
and is not registered with Auth. Denial of service is observable but not
prevented.

## Security properties

In ROS-only mode with DDS Security disabled, the application accepts matching
ROS messages without authenticating the publisher. ROS 2 provides DDS Security
and SROS2, but the initial configuration used here does not enable them.

In SST-protected mode, SST:

- Authenticates registered entities through an Auth-authorized session key
- Protects message confidentiality and integrity
- Rejects an unregistered replacement that cannot establish an authenticated
  SST channel
- Prevents unauthenticated distance or image data from reaching the VLM

The agent fails closed: if a required input is missing, invalid, stale, or
unauthenticated, it selects `STOP`.

## Out of scope

SST does not prove that an authenticated sensor is truthful, make VLM reasoning
correct, detect adversarial pixels from a compromised legitimate camera,
protect a compromised host, or authorize the semantic safety of an action.
Source authentication, message confidentiality, and message integrity are
necessary controls, not a complete embodied-AI safety argument.

The current VLM emits one discrete high-level action. It is not a VLA model and
does not produce motor trajectories.
