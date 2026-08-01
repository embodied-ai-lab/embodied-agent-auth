#!/usr/bin/env bash
# Start or stop the local SST Auth server.
# It serves loopback endpoints and authorizes only the entities registered in
# sst/configs/warehouse_cart.graph.
#
# The keystore password is read from runtime/sst/auth_password and passed with
# --password for non-interactive startup. The upstream warning is expected for
# throwaway lab credentials; this setup is not suitable for deployment.

set -euo pipefail

# shellcheck source=../../scripts/lib.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../scripts" && pwd)/lib.sh"

AUTH_SERVER_DIR="${ISCPS_IOTAUTH_DIR}/auth/auth-server"
JAR="${AUTH_SERVER_DIR}/target/auth-server-jar-with-dependencies.jar"
PASSWORD_FILE="${ISCPS_RUNTIME_DIR}/sst/auth_password"
GRAPH="${ISCPS_LAB_ROOT}/sst/configs/warehouse_cart.graph"

LOG_FILE="${ISCPS_RUNTIME_DIR}/sst/logs/auth.log"
PID_FILE="${ISCPS_RUNTIME_DIR}/sst/auth.pid"
FIFO_FILE="${ISCPS_RUNTIME_DIR}/sst/auth.stdin"
TIMEOUT=90
ACTION=start

usage() {
  cat <<'USAGE'
Usage: sst/scripts/start_auth.sh [options]

  --stop              Stop the Auth server started by a previous invocation.
  --status            Report whether Auth is running and listening.
  --log FILE          Auth log file (default: runtime/sst/auth.log).
  --pid-file FILE     PID file (default: runtime/sst/auth.pid).
  --timeout SECONDS   How long to wait for readiness (default: 90).
  -h, --help          Show this help.

Only the process recorded in the PID file is ever signaled. This script will
not kill an Auth or Java process it did not start.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stop)     ACTION=stop ;;
    --status)   ACTION=status ;;
    --log)      LOG_FILE="$2"; shift ;;
    --pid-file) PID_FILE="$2"; shift ;;
    --timeout)  TIMEOUT="$2"; shift ;;
    -h|--help)  usage; exit 0 ;;
    *) die "unknown option: $1 (try --help)" ;;
  esac
  shift
done

read_graph() {
  "${PY}" - "${GRAPH}" "$1" <<'EOF'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    auth = json.load(handle)["authList"][0]
print(auth[sys.argv[2]])
EOF
}

AUTH_ID="$(read_graph id)"
AUTH_TCP_PORT="$(read_graph tcpPort)"
PROPERTIES="${ISCPS_RUNTIME_DIR}/sst/auth/auth${AUTH_ID}.properties"

# Stop and status actions

auth_pid() { [[ -f "${PID_FILE}" ]] && tr -d '\r\n' < "${PID_FILE}"; }

case "${ACTION}" in
  stop)
    pid="$(auth_pid || true)"
    if [[ -z "${pid}" ]]; then
      log "no PID file at ${PID_FILE}; nothing to stop"
      exit 0
    fi
    if ! kill -0 "${pid}" 2>/dev/null; then
      log "Auth (pid ${pid}) is not running; removing the stale PID file"
      rm -f "${PID_FILE}" "${FIFO_FILE}"
      exit 0
    fi
    log "stopping Auth (pid ${pid})"
    kill -TERM "${pid}" 2>/dev/null || true
    waited=0
    while kill -0 "${pid}" 2>/dev/null && (( waited < 100 )); do
      sleep 0.1; waited=$(( waited + 1 ))
    done
    if kill -0 "${pid}" 2>/dev/null; then
      log_warn "Auth did not exit on SIGTERM; sending SIGKILL"
      kill -KILL "${pid}" 2>/dev/null || true
    fi
    rm -f "${PID_FILE}" "${FIFO_FILE}"
    log_ok "Auth stopped"
    exit 0
    ;;
  status)
    pid="$(auth_pid || true)"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      log_ok "Auth ${AUTH_ID} is running (pid ${pid})"
      iscps_port_free "${AUTH_TCP_PORT}" \
        && log_warn "but nothing is listening on ${AUTH_TCP_PORT}" \
        || log_ok "listening on 127.0.0.1:${AUTH_TCP_PORT}"
      exit 0
    fi
    log "Auth is not running"
    exit 1
    ;;
esac

# Start

log_step "Starting SST Auth ${AUTH_ID}"

iscps_refuse_login_node
[[ -f "${JAR}" ]] \
  || die "Auth jar not found. Run: make build-auth"
[[ -f "${PROPERTIES}" ]] \
  || die "Auth properties not found. Run: make generate"
[[ -f "${ISCPS_RUNTIME_DIR}/sst/database/auth${AUTH_ID}/auth.db" ]] \
  || die "Auth database not found. Run: make generate"
[[ -f "${PASSWORD_FILE}" ]] \
  || die "missing ${PASSWORD_FILE}. Run: make generate"

existing="$(auth_pid || true)"
if [[ -n "${existing}" ]] && kill -0 "${existing}" 2>/dev/null; then
  log_ok "Auth is already running (pid ${existing})"
  exit 0
fi
rm -f "${PID_FILE}"

if ! iscps_port_free "${AUTH_TCP_PORT}"; then
  die "port ${AUTH_TCP_PORT} is already in use. Another Auth may be running.
This script will not kill a process it did not start. Stop it, or change
authList[0].tcpPort in sst/configs/warehouse_cart.graph and re-run 'make generate'."
fi

AUTH_PASSWORD="$(tr -d '\r\n' < "${PASSWORD_FILE}")"

mkdir -p "$(dirname "${LOG_FILE}")"
: > "${LOG_FILE}"

# Auth exits when its interactive stdin reaches EOF. A FIFO keeps stdin open
# and lets an instructor send `show re` or `show cp`.
rm -f "${FIFO_FILE}"
mkfifo -m 600 "${FIFO_FILE}"
exec 9<>"${FIFO_FILE}"

log "properties: runtime/sst/auth/auth${AUTH_ID}.properties"
log "database:   runtime/sst/database/auth${AUTH_ID}/auth.db"
log "entity TCP port: ${AUTH_TCP_PORT} (loopback)"
log "log file:   ${LOG_FILE}"

(
  cd "${ISCPS_RUNTIME_DIR}/sst/auth"
  exec java -jar "${JAR}" -p "${PROPERTIES}" --password "${AUTH_PASSWORD}"
) <"${FIFO_FILE}" >>"${LOG_FILE}" 2>&1 &

AUTH_PID=$!
printf '%s\n' "${AUTH_PID}" > "${PID_FILE}"
log "Auth pid ${AUTH_PID} (recorded in ${PID_FILE})"

# Readiness needs both signals. The command prompt can appear before the entity
# TCP port is actually bound, so waiting only for the prompt races the first
# session-key request.
if ! iscps_wait_for_log "${LOG_FILE}" "Enter command" "${TIMEOUT}" "Auth ${AUTH_ID}"; then
  kill -TERM "${AUTH_PID}" 2>/dev/null || true
  rm -f "${PID_FILE}"
  die "Auth did not become ready within ${TIMEOUT}s"
fi
if ! iscps_wait_for_port 127.0.0.1 "${AUTH_TCP_PORT}" 30 "Auth ${AUTH_ID} entity service"; then
  kill -TERM "${AUTH_PID}" 2>/dev/null || true
  rm -f "${PID_FILE}"
  die "Auth started but never bound port ${AUTH_TCP_PORT}"
fi

if grep -qE '^Auth server information' "${LOG_FILE}"; then
  grep -E '^Auth server information' "${LOG_FILE}" | head -1 | sed 's/^/[lab] /'
fi

log_ok "Auth ${AUTH_ID} is ready"
log "Stop it with: sst/scripts/start_auth.sh --stop"
