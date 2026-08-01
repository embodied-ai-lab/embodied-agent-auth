# Shared helpers for root discovery, logging, ROS domains, process cleanup, and
# ports. Signal only PIDs recorded by the current run; shared hosts may contain
# another student's ROS, Auth, or Java processes.

# shellcheck shell=bash

if [[ -n "${_ISCPS_LIB_SOURCED:-}" ]]; then
  return 0
fi
_ISCPS_LIB_SOURCED=1

# Repository root

iscps_find_root() {
  local dir="${BASH_SOURCE[0]%/*}"
  dir="$(cd "${dir}/.." && pwd)"
  while [[ "${dir}" != "/" ]]; do
    if [[ -f "${dir}/configs/scenario.yaml" ]]; then
      printf '%s\n' "${dir}"
      return 0
    fi
    dir="$(dirname "${dir}")"
  done
  printf 'ERROR: could not locate the lab root (no configs/scenario.yaml found)\n' >&2
  return 1
}

ISCPS_LAB_ROOT="${ISCPS_LAB_ROOT:-$(iscps_find_root)}"
export ISCPS_LAB_ROOT
readonly ISCPS_LAB_ROOT

ISCPS_PKG_DIR="${ISCPS_LAB_ROOT}/ros2_ws/src/iscps_sst_lab"
ISCPS_RUNTIME_DIR="${ISCPS_LAB_ROOT}/runtime"
ISCPS_IOTAUTH_DIR="${ISCPS_LAB_ROOT}/third_party/iotauth"
export ISCPS_PKG_DIR ISCPS_RUNTIME_DIR ISCPS_IOTAUTH_DIR

# Logging

if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
  _C_RESET=$'\033[0m'; _C_BOLD=$'\033[1m'; _C_RED=$'\033[31m'
  _C_GREEN=$'\033[32m'; _C_YELLOW=$'\033[33m'; _C_BLUE=$'\033[34m'
else
  _C_RESET=""; _C_BOLD=""; _C_RED=""; _C_GREEN=""; _C_YELLOW=""; _C_BLUE=""
fi

log()      { printf '%s[lab]%s %s\n'  "${_C_BLUE}"   "${_C_RESET}" "$*"; }
log_ok()   { printf '%s[ ok ]%s %s\n' "${_C_GREEN}"  "${_C_RESET}" "$*"; }
log_warn() { printf '%s[warn]%s %s\n' "${_C_YELLOW}" "${_C_RESET}" "$*" >&2; }
log_err()  { printf '%s[FAIL]%s %s\n' "${_C_RED}"    "${_C_RESET}" "$*" >&2; }
log_step() { printf '\n%s==> %s%s\n'  "${_C_BOLD}"   "$*" "${_C_RESET}"; }

die() { log_err "$*"; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1${2:+ ($2)}"
}

# Python interpreter
# ROS 2 Jazzy binaries are built against the Ubuntu system interpreter, so that
# is the default. A virtual environment is only used when it was created with
# --system-site-packages, otherwise `import rclpy` would fail inside it.

iscps_python() {
  if [[ -n "${ISCPS_PYTHON:-}" ]]; then
    printf '%s\n' "${ISCPS_PYTHON}"
  elif [[ -x "${ISCPS_LAB_ROOT}/.venv/bin/python3" ]]; then
    printf '%s\n' "${ISCPS_LAB_ROOT}/.venv/bin/python3"
  elif [[ -x /usr/bin/python3 ]]; then
    printf '%s\n' /usr/bin/python3
  else
    command -v python3
  fi
}

PY="$(iscps_python)"
export PY
if [[ "${PY}" == "${ISCPS_LAB_ROOT}/.venv/"* ]]; then
  export PATH="${ISCPS_LAB_ROOT}/.venv/bin:${PATH}"
fi

iscps_refuse_login_node() {
  local host
  host="$(hostname -s 2>/dev/null || hostname)"
  if [[ "${host}" =~ (^|-)login[0-9]*($|-) ]] || [[ "${host}" =~ ^sol-login ]]; then
    die "Refusing to run ROS, Auth, or model work on login node ${host}. Start a compute-node allocation first."
  fi
}

# ROS 2 discovery configuration
# ROS 2 uses decentralized automatic discovery. We restrict its range to
# LOCALHOST and pin a domain ID so that concurrent student teams on one machine
# do not see each other's nodes.
#
# A domain ID is NOT an authentication boundary. Anyone who can run a process
# on this machine can join this domain. That is the premise of Parts 1-3.

iscps_setup_domain() {
  if [[ -z "${ROS_DOMAIN_ID:-}" ]]; then
    ROS_DOMAIN_ID="$("${PY}" "${ISCPS_LAB_ROOT}/scripts/choose_domain_id.py" --quiet)" \
      || die "could not select a ROS domain ID"
  fi
  export ROS_DOMAIN_ID
  export ROS_AUTOMATIC_DISCOVERY_RANGE="${ROS_AUTOMATIC_DISCOVERY_RANGE:-LOCALHOST}"
  log "ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
  log "ROS_AUTOMATIC_DISCOVERY_RANGE=${ROS_AUTOMATIC_DISCOVERY_RANGE}"
  log "RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-<default>}"
}

iscps_source_ros() {
  if [[ -n "${ROS_DISTRO:-}" ]]; then
    return 0
  fi
  local candidate="/opt/ros/${ISCPS_ROS_DISTRO:-jazzy}/setup.bash"
  if [[ -f "${candidate}" ]]; then
    # shellcheck disable=SC1090
    set +u; . "${candidate}"; set -u
    log "sourced ${candidate}"
  else
    log_warn "ROS 2 environment not found at ${candidate}; ROS nodes will not run."
    log_warn "Install ROS 2 Jazzy or set ISCPS_ROS_DISTRO. See docs/SETUP.md."
    return 1
  fi
}

iscps_source_overlay() {
  local overlay="${ISCPS_LAB_ROOT}/ros2_ws/install/setup.bash"
  if [[ -f "${overlay}" ]]; then
    # shellcheck disable=SC1090
    set +u; . "${overlay}"; set -u
    log "sourced workspace overlay"
  else
    log_warn "workspace overlay missing; run 'make build' first"
    return 1
  fi
}

# Run directories

iscps_new_run_dir() {
  local mode="$1"
  local stamp run_id dir
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  run_id="$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"
  dir="${ISCPS_LAB_ROOT}/results/${mode}-${stamp}-${run_id}"
  mkdir -p "${dir}"
  printf '%s\n' "${dir}"
}

# Run-scoped process registry
# Every child we start is recorded in ${ISCPS_PID_DIR}. Commands launched with
# iscps_spawn get a fresh session/process group. On exit we signal only that
# recorded group, so grandchildren such as the nodes created by `ros2 launch`
# cannot survive while unrelated jobs remain untouched.

iscps_init_pids() {
  ISCPS_PID_DIR="${1:-${ISCPS_RUNTIME_DIR}/pids/$$}"
  mkdir -p "${ISCPS_PID_DIR}"
  export ISCPS_PID_DIR
  trap iscps_cleanup EXIT INT TERM
}

# iscps_track <label> <pid> [group]
iscps_track() {
  local label="$1" pid="$2" scope="${3:-process}"
  printf '%s\n' "${pid}" > "${ISCPS_PID_DIR}/${label}.pid"
  if [[ "${scope}" == "group" ]]; then
    : > "${ISCPS_PID_DIR}/${label}.group"
  fi
  log "started ${label} (pid ${pid})"
}

# iscps_spawn <label> <logfile> -- <command...>
iscps_spawn() {
  local label="$1" logfile="$2"
  shift 2
  [[ "$1" == "--" ]] && shift
  need_cmd setsid
  mkdir -p "$(dirname "${logfile}")"
  setsid "$@" >>"${logfile}" 2>&1 &
  iscps_track "${label}" "$!" group
}

iscps_pid_of() {
  local label="$1" file="${ISCPS_PID_DIR}/${label}.pid"
  [[ -f "${file}" ]] && cat "${file}"
}

iscps_is_alive() {
  local pid="$1"
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null
}

iscps_group_is_alive() {
  local pgid="$1"
  [[ -n "${pgid}" ]] && kill -0 -- "-${pgid}" 2>/dev/null
}

# iscps_stop <label> [signal] -- graceful TERM, then KILL after a grace period.
iscps_stop() {
  local label="$1" sig="${2:-TERM}" pid group_file target
  pid="$(iscps_pid_of "${label}" || true)"
  group_file="${ISCPS_PID_DIR}/${label}.group"
  if [[ -f "${group_file}" ]]; then
    target="-${pid}"
    if ! iscps_group_is_alive "${pid}"; then
      rm -f "${ISCPS_PID_DIR}/${label}.pid" "${group_file}"
      return 0
    fi
  else
    target="${pid}"
    if ! iscps_is_alive "${pid}"; then
      rm -f "${ISCPS_PID_DIR}/${label}.pid"
      return 0
    fi
  fi
  if [[ -z "${pid}" ]]; then
    return 0
  fi
  if [[ -f "${group_file}" ]]; then
    log "stopping ${label} (process group ${pid})"
  else
    log "stopping ${label} (pid ${pid})"
  fi
  kill -"${sig}" -- "${target}" 2>/dev/null || true
  local waited=0
  while { [[ -f "${group_file}" ]] && iscps_group_is_alive "${pid}"; } \
    || { [[ ! -f "${group_file}" ]] && iscps_is_alive "${pid}"; }; do
    (( waited >= 50 )) && break
    sleep 0.1
    waited=$(( waited + 1 ))
  done
  if { [[ -f "${group_file}" ]] && iscps_group_is_alive "${pid}"; } \
    || { [[ ! -f "${group_file}" ]] && iscps_is_alive "${pid}"; }; then
    log_warn "${label} did not exit on SIG${sig}; sending SIGKILL"
    kill -KILL -- "${target}" 2>/dev/null || true
  fi
  wait "${pid}" 2>/dev/null || true
  rm -f "${ISCPS_PID_DIR}/${label}.pid" "${group_file}"
}

iscps_cleanup() {
  local status=$?
  trap - EXIT INT TERM
  if [[ -n "${ISCPS_PID_DIR:-}" ]] && [[ -d "${ISCPS_PID_DIR}" ]]; then
    local file label
    # Reverse order so clients die before the servers they talk to.
    while IFS= read -r file; do
      label="$(basename "${file}" .pid)"
      iscps_stop "${label}" TERM
    done < <(ls -1t "${ISCPS_PID_DIR}"/*.pid 2>/dev/null || true)
    rmdir "${ISCPS_PID_DIR}" 2>/dev/null || true
  fi
  return "${status}"
}

# Waiting helpers

# iscps_wait_for_port <host> <port> <timeout_s> <label>
iscps_wait_for_port() {
  local host="$1" port="$2" timeout="$3" label="${4:-${1}:${2}}"
  local deadline=$(( SECONDS + timeout ))
  while (( SECONDS < deadline )); do
    if "${PY}" - "$host" "$port" <<'EOF' 2>/dev/null
import socket, sys
s = socket.socket()
s.settimeout(0.5)
sys.exit(0 if s.connect_ex((sys.argv[1], int(sys.argv[2]))) == 0 else 1)
EOF
    then
      log_ok "${label} is accepting connections on ${host}:${port}"
      return 0
    fi
    sleep 0.25
  done
  log_err "timed out after ${timeout}s waiting for ${label} on ${host}:${port}"
  return 1
}

# iscps_wait_for_log <file> <pattern> <timeout_s> <label>
iscps_wait_for_log() {
  local file="$1" pattern="$2" timeout="$3" label="${4:-$2}"
  local deadline=$(( SECONDS + timeout ))
  while (( SECONDS < deadline )); do
    if [[ -f "${file}" ]] && grep -qF -- "${pattern}" "${file}" 2>/dev/null; then
      log_ok "${label}: saw '${pattern}'"
      return 0
    fi
    sleep 0.25
  done
  log_err "timed out after ${timeout}s waiting for '${pattern}' in ${file}"
  [[ -f "${file}" ]] && tail -n 30 "${file}" >&2
  return 1
}

# iscps_port_free <port> -- true when nothing is listening.
iscps_port_free() {
  ! "${PY}" - "$1" <<'EOF' 2>/dev/null
import socket, sys
s = socket.socket()
s.settimeout(0.3)
sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
EOF
}

# iscps_require_ports_free <port...> -- refuse to start on top of something else.
# We report the conflict and exit; we never kill the other process, because on a
# shared machine it belongs to somebody else.
iscps_require_ports_free() {
  local port conflicts=()
  for port in "$@"; do
    iscps_port_free "${port}" || conflicts+=("${port}")
  done
  if (( ${#conflicts[@]} > 0 )); then
    log_err "these lab ports are already in use: ${conflicts[*]}"
    log_err "Another run may still be active. Stop it, or change the ports in configs/scenario.yaml."
    log_err "This script will not kill processes it did not start."
    return 1
  fi
  return 0
}

iscps_banner() {
  local mode="$1" outdir="$2"
  log_step "ISCPS embodied-agent-auth -- mode: ${mode}"
  log "project root:     ${ISCPS_LAB_ROOT}"
  log "output directory: ${outdir}"
  log "python:           ${PY}"
}
