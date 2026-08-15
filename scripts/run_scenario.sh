#!/usr/bin/env bash
# Run one graded live-VLM experiment and stop only the processes started here.

set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

MODE="${1:-}"
shift || true
FALSE_DISTANCE="${FALSE_DISTANCE:-6.0}"
DURATION="${DURATION:-130}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --false-distance) FALSE_DISTANCE="$2"; shift ;;
    --duration) DURATION="$2"; shift ;;
    *) die "unknown option: $1" ;;
  esac
  shift
done

case "${MODE}" in
  baseline|attack|secure|secure-attack|grad-vision-baseline|grad-vision-attack|grad-vision-secure) ;;
  *) die "usage: scripts/run_scenario.sh {baseline|attack|secure|secure-attack|grad-vision-baseline|grad-vision-attack|grad-vision-secure}" ;;
esac

iscps_refuse_login_node
iscps_source_ros || exit 1
iscps_source_overlay || exit 1
iscps_setup_domain
LIVE_VLM_REQUIRED=1
if [[ "${MODE}" == secure-attack || "${MODE}" == grad-vision-secure ]]; then
  LIVE_VLM_REQUIRED=0
else
  "${PY}" "${ISCPS_LAB_ROOT}/scripts/vlm_check.py" --quick
fi

RUN_DIR="$(iscps_new_run_dir "${MODE//-/_}")"
export ISCPS_RUN_DIR="${RUN_DIR}"
printf '%s\n' "${RUN_DIR}" > "${ISCPS_RUNTIME_DIR}/last_run"
mkdir -p "${ISCPS_RUNTIME_DIR}/pids/$$"
ISCPS_PID_DIR="${ISCPS_RUNTIME_DIR}/pids/$$"
export ISCPS_PID_DIR
AUTH_STARTED=0

finish() {
  local status=$?
  trap - EXIT INT TERM
  iscps_cleanup || true
  if (( AUTH_STARTED )); then
    "${ISCPS_LAB_ROOT}/sst/scripts/start_auth.sh" --stop || true
  fi
  exit "${status}"
}
trap finish EXIT INT TERM

"${PY}" - \
  "${RUN_DIR}/manifest.json" \
  "${MODE}" \
  "${FALSE_DISTANCE}" \
  "${LIVE_VLM_REQUIRED}" <<'PY'
import json
import os
from pathlib import Path
import sys
import time

Path(sys.argv[1]).write_text(json.dumps({
    "mode": sys.argv[2],
    "false_distance_m": float(sys.argv[3]),
    "live_vlm_required": bool(int(sys.argv[4])),
    "model": os.environ.get("VLM_MODEL", "qwen2.5vl:3b"),
    "ollama_host": os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
    "started_at": time.time(),
}, indent=2) + "\n")
PY

if [[ "${MODE}" == secure || "${MODE}" == secure-attack \
  || "${MODE}" == grad-vision-secure ]]; then
  if ! "${ISCPS_LAB_ROOT}/sst/scripts/start_auth.sh" --status >/dev/null 2>&1; then
    "${ISCPS_LAB_ROOT}/sst/scripts/start_auth.sh"
    AUTH_STARTED=1
  fi
fi

iscps_banner "${MODE}" "${RUN_DIR}"
iscps_spawn ros_launch "${RUN_DIR}/terminal.log" -- \
  ros2 launch lab lab.launch.py \
    "mode:=${MODE}" "false_distance:=${FALSE_DISTANCE}"

if ! iscps_wait_for_log \
  "${RUN_DIR}/cart_simulator.jsonl" '"kind": "action_executed"' \
  "${DURATION}" "executed cart action"; then
  exit 2
fi
iscps_stop ros_launch
# Ground truth is loaded only now, after ROS and the cart have stopped.
"${PY}" "${ISCPS_LAB_ROOT}/scripts/evaluate_run.py" --run-dir "${RUN_DIR}"
