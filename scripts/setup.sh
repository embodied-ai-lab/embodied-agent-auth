#!/usr/bin/env bash
# Create the lab venv and install Python dependencies from their authoritative sources.

set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

[[ -f "${ISCPS_IOTAUTH_DIR}/entity/python/pyproject.toml" ]] \
  || die "iotauth submodule is not initialized. Run: make submodules"

iscps_source_ros \
  || die "ROS 2 Jazzy must be installed and sourced before creating the lab venv"

if [[ ! -x "${ISCPS_LAB_ROOT}/.venv/bin/python3" ]]; then
  setup_python=""
  candidates=(/usr/bin/python3)
  for name in python3.12 python3.11 python3.10 python3; do
    candidate="$(command -v "${name}" 2>/dev/null || true)"
    [[ -n "${candidate}" ]] && candidates+=("${candidate}")
  done
  checked=""
  for candidate in "${candidates[@]}"; do
    [[ -x "${candidate}" ]] || continue
    [[ ":${checked}:" == *":${candidate}:"* ]] && continue
    checked="${checked}:${candidate}"
    if "${candidate}" -c \
      'import sys; raise SystemExit(not ((3, 10) <= sys.version_info[:2] < (3, 13)))' \
      && "${candidate}" -c 'import rclpy'; then
      setup_python="${candidate}"
      break
    fi
  done
  [[ -n "${setup_python}" ]] || die \
    "No Python 3.10-3.12 interpreter can import the installed ROS 2 rclpy package.
ROS 2 Jazzy binary packages must be used with their matching system Python.
Verify first with: /usr/bin/python3 -c 'import rclpy'"
  log "creating .venv with ROS-compatible interpreter: ${setup_python}"
  "${setup_python}" -m venv --system-site-packages "${ISCPS_LAB_ROOT}/.venv"
fi

VENV_PY="${ISCPS_LAB_ROOT}/.venv/bin/python3"
"${VENV_PY}" -c 'import rclpy' \
  || die \
    "The existing .venv cannot import rclpy. It was likely created with a
different Python ABI or without --system-site-packages. Remove only this
repository's .venv, then rerun make setup."
"${VENV_PY}" -m pip install \
  "pydantic>=2" Pillow PyYAML pytest pytest-timeout ruff
"${VENV_PY}" -m pip install "${ISCPS_IOTAUTH_DIR}/entity/python"
"${VENV_PY}" -m pip install -e \
  "${ISCPS_LAB_ROOT}/ros2_ws/src/iscps_sst_lab" --no-deps

log_ok "Python environment ready at .venv"
"${VENV_PY}" -c 'import rclpy; print("ROS rclpy import: OK")'
"${VENV_PY}" -c 'from iotauth import IoTAuthContext, SecureClient, SecureServer, SecureChannel; print("iotauth public API: OK")'
