#!/usr/bin/env bash
# Remove only repository-generated build, runtime, result, and cache artifacts.

set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

log_step "Cleaning generated lab artifacts"
if [[ -f "${LAB_RUNTIME_DIR}/sst/auth.pid" ]]; then
  "${LAB_ROOT}/sst/scripts/start_auth.sh" --stop || true
fi
rm -rf \
  "${LAB_ROOT}/ros2_ws/build" \
  "${LAB_ROOT}/ros2_ws/install" \
  "${LAB_ROOT}/ros2_ws/log" \
  "${LAB_RUNTIME_DIR}" \
  "${LAB_ROOT}/.pytest_cache" \
  "${LAB_ROOT}/.ruff_cache"
find "${LAB_ROOT}" \
  -path "${LAB_IOTAUTH_DIR}" -prune -o \
  -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "${LAB_ROOT}/results" -mindepth 1 ! -name .gitkeep \
  -exec rm -rf {} + 2>/dev/null || true
log_ok "clean complete; the submodule and .venv were preserved"
