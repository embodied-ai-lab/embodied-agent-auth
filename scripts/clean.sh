#!/usr/bin/env bash
# Remove only repository-generated build, runtime, result, and cache artifacts.

set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

log_step "Cleaning generated lab artifacts"
if [[ -f "${ISCPS_RUNTIME_DIR}/sst/auth.pid" ]]; then
  "${ISCPS_LAB_ROOT}/sst/scripts/start_auth.sh" --stop || true
fi
rm -rf \
  "${ISCPS_LAB_ROOT}/ros2_ws/build" \
  "${ISCPS_LAB_ROOT}/ros2_ws/install" \
  "${ISCPS_LAB_ROOT}/ros2_ws/log" \
  "${ISCPS_RUNTIME_DIR}" \
  "${ISCPS_LAB_ROOT}/.pytest_cache" \
  "${ISCPS_LAB_ROOT}/.ruff_cache"
find "${ISCPS_LAB_ROOT}" \
  -path "${ISCPS_IOTAUTH_DIR}" -prune -o \
  -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "${ISCPS_LAB_ROOT}/results" -mindepth 1 ! -name .gitkeep \
  -exec rm -rf {} + 2>/dev/null || true
log_ok "clean complete; the submodule and .venv were preserved"
