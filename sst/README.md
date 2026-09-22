# SST support files

This directory contains the tracked configuration and helper scripts used to
protect the distance and camera inputs with the Secure Swarm Toolkit (SST).
The upstream SST/IoTAuth source is pinned separately in
[`third_party/iotauth`](../third_party/README.md), and the application-side
transport is implemented in
[`ros2_ws/src/lab/sst_link.py`](../ros2_ws/src/lab/sst_link.py).

Nothing under `sst/` is a generated credential. Generated private keys,
databases, passwords, entity configurations, process files, and logs belong
under the gitignored `runtime/sst/` directory.

## Directory map

| Path | Purpose |
|---|---|
| [`configs/warehouse_cart.graph`](configs/warehouse_cart.graph) | IoTAuth deployment graph: registered entities, groups, Auth settings, and communication policies. The file is JSON despite its `.graph` suffix. |
| [`scripts/build_auth.sh`](scripts/build_auth.sh) | Builds the Java Auth server from the pinned IoTAuth submodule. |
| [`scripts/generate_runtime.sh`](scripts/generate_runtime.sh) | Runs the upstream generators in a disposable work tree, copies only the required artifacts to `runtime/sst/`, and validates the generated entity configurations. |
| [`scripts/write_entity_configs.py`](scripts/write_entity_configs.py) | Renders the three Python entity configuration files from the root SST and scenario configuration. |
| [`scripts/start_auth.sh`](scripts/start_auth.sh) | Starts, reports the status of, or stops the project-owned Auth process using its PID file. |

Related repository-level configuration lives in
[`configs/sst.yaml`](../configs/sst.yaml), which defines runtime endpoints and
generated config paths, and
[`configs/scenario.yaml`](../configs/scenario.yaml), which defines entity
names used by the ROS nodes.

## Registered topology

| Role | Entity or group | Endpoint |
|---|---|---|
| Auth | ID `101` | `127.0.0.1:21900` |
| VLM agent | `net1.vlm_agent` in `Agents` | Connects to both sensor servers |
| Distance source | `net1.distance_sensor` in `DistanceSensors` | `127.0.0.1:22101` |
| Camera source | `net1.vision_sensor` in `VisionSensors` | `127.0.0.1:22102` |

Each sensor group has exactly one registered member. The attack identities
`unregistered.rogue_distance` and `unregistered.rogue_vision` are deliberately
absent from the graph and receive no credentials. Do not register them: their
rejection is part of the lab.

The graph, `configs/sst.yaml`, and the `identities` section of
`configs/scenario.yaml` repeat some entity and endpoint values because they are
consumed by different tools. If a legitimate identity or fixed port changes,
update all applicable files together and rerun `make generate`.

## Normal workflow

On ASU Sol, run project commands through the `lab` wrapper documented in the
root [`README.md`](../README.md). Personal Linux users can omit that prefix.

In the student template, complete the Part 4 TODOs before running `secure`
and `secure-attack`, then rerun `lab make build` to install the edited ROS
code. Building Auth and generating credentials do not complete those TODOs.
See the root [README's failure guidance](../README.md#expected-failures-before-completing-the-todos).

```bash
git submodule update --init third_party/iotauth
lab make setup
lab make build-auth
lab make generate
lab make secure
lab make secure-attack
lab make auth-stop
```

The secure scenario targets start Auth when needed. If a scenario starts Auth,
it also stops that same process during cleanup. For explicit lifecycle checks:

```bash
lab make auth-start
lab sst/scripts/start_auth.sh --status
lab make auth-stop
```

`make generate` creates a fresh password when needed and writes retained state
under `runtime/sst/`:

```text
runtime/sst/
├── auth/
├── auth_password
├── configs/
├── credentials/
├── database/
└── logs/
```

The upstream generator runs from the temporary
`runtime/iotauth-generation/` tree so it does not write generated material into
the submodule. Never commit or submit anything from `runtime/`. Run
`make clean` only after building and inspecting the submission ZIP, because it
also removes result evidence.

## Security boundary

SST authenticates registered entities and protects the confidentiality and
integrity of messages on these two sensor links. It does not prove that an
authenticated sensor reports physical truth, make a VLM decision safe, or
provide availability. The ROS action link from the VLM agent to the cart is
outside this SST topology and is not authenticated here. Loopback binding and
`ROS_DOMAIN_ID` reduce accidental interference but are not authentication
mechanisms.

## Troubleshooting

- If the submodule is empty, run `git submodule update --init
  third_party/iotauth`.
- If the Auth JAR is missing, run `lab make build-auth`. If generated Auth
  properties or entity configs are missing, run `lab make generate`.
- If the Auth JAR already exists, the build is skipped. Force a rebuild with
  `lab sst/scripts/build_auth.sh --force` (omit `lab` on local Linux).
  Passing `--force` to `make build-auth` does not forward it to the script.
- Auth logs are written to `runtime/sst/logs/auth.log`. The fixed ports are
  `21900`, `22101`, and `22102`.
- `lab make auth-stop` signals the PID recorded in `runtime/sst/auth.pid`. If
  that file may be stale or was edited manually, inspect it before stopping.
- After a run, use `lab python3 scripts/check_cleanup.py` and
  `lab python3 scripts/check_ros_cleanup.py` to find stale project processes,
  occupied ports, or remaining ROS nodes.

See [`ASSIGNMENT.md`](../ASSIGNMENT.md) for the required experiments and
evidence.
