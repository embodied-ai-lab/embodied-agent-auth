# Security and responsible use

This is a loopback-only educational exercise. Run malicious nodes only against
this repository's processes on a machine you are authorized to use. Never
target another student's work, another host, or a production system. On Sol,
run ROS, Auth, and VLM inference only in an allocation—not on a login node.

## Threat model

The attacker can inspect ROS discovery, run a node in the same ROS domain, copy
a legitimate publisher's ROS-visible attributes, replace a legitimate source,
and bind an expected loopback port. The attacker has no valid SST credentials
and is not registered with Auth.

The host, cart, VLM agent, Auth service, Ollama server, and legitimate sensors
are trusted for this lab. Host compromise, credential theft, and denial-of-
service prevention are out of scope.

## Security claims

With DDS Security and SROS2 disabled, matching ROS node, topic, type, QoS, and
frame attributes do not authenticate a publisher.

In protected modes, SST:

- authenticates entities registered through Auth;
- protects message confidentiality and integrity; and
- prevents an unregistered replacement from delivering sensor data to the VLM.

The agent stops on missing, stale, invalid, or unauthenticated input. SST does
not prove that an authenticated sensor is truthful, make VLM reasoning correct,
detect misleading pixels from a compromised camera, protect a compromised
host, or certify an action as safe.

## Runtime safeguards

- Generated credentials, keys, databases, and configs stay under gitignored
  `runtime/sst/` and are excluded from submissions.
- Run scripts stop only process IDs and groups they recorded.
- Graded commands require the live model; they do not download it or substitute
  a mock.
- The cart receives only the VLM action. Ground truth is read solely by the
  independent evaluator after ROS stops.

Report suspected credential exposure or unintended interaction with another
user's processes to the instructor and stop the affected run.
