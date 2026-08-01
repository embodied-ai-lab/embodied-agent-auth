#!/usr/bin/env bash
#
# colcon build the ROS 2 package. Needs a sourced ROS 2 Jazzy environment.

set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

log_step "Building the ROS 2 workspace"

if ! iscps_source_ros; then
  die "ROS 2 is not available. Install ROS 2 Jazzy and source it, or set ISCPS_ROS_DISTRO.
See docs/SETUP.md."
fi
cd "${ISCPS_LAB_ROOT}/ros2_ws"
if "${PY}" -m colcon --help >/dev/null 2>&1; then
  log "${PY} -m colcon build --symlink-install"
  "${PY}" -m colcon build --symlink-install --event-handlers console_direct+
else
  need_cmd colcon
  log "colcon build --symlink-install"
  colcon build --symlink-install --event-handlers console_direct+
fi
log_ok "workspace built"
log "Source the overlay with: source ros2_ws/install/setup.bash"
