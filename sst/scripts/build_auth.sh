#!/usr/bin/env bash
#
# Build Auth directly from the pinned third_party/iotauth submodule.

set -euo pipefail

# shellcheck source=../../scripts/lib.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../scripts" && pwd)/lib.sh"

AUTH_DIR="${ISCPS_IOTAUTH_DIR}/auth"
JAR="${AUTH_DIR}/auth-server/target/auth-server-jar-with-dependencies.jar"
FORCE=0
OFFLINE=0

usage() {
  cat <<'USAGE'
Usage: sst/scripts/build_auth.sh [--force] [--offline]

  --force     Rebuild even when the jar already exists.
  --offline   Pass -o to Maven (use only when the local repository is warm).

Requires Java 11 or newer and Maven. The first build downloads Maven
dependencies and needs network access.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)   FORCE=1 ;;
    --offline) OFFLINE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1 (try --help)" ;;
  esac
  shift
done

log_step "Building the Java Auth server"

[[ -d "${AUTH_DIR}" ]] || die "iotauth submodule is missing. Run: make submodules"
need_cmd java
need_cmd mvn

JAVA_VERSION="$(java -version 2>&1 | head -1)"
log "java:  ${JAVA_VERSION}"
log "maven: $(mvn -version 2>&1 | head -1)"

if [[ -f "${JAR}" ]] && (( ! FORCE )); then
  log_ok "Auth jar already built: $(basename "${JAR}")"
  log "Pass --force to rebuild."
  exit 0
fi

MVN_ARGS=(-B -q package -DskipTests)
(( OFFLINE )) && MVN_ARGS+=(-o)

BUILD_LOG="${ISCPS_RUNTIME_DIR}/sst/logs/build_auth.log"
mkdir -p "$(dirname "${BUILD_LOG}")"

log "running: mvn ${MVN_ARGS[*]} --file auth/pom.xml"
log "first build downloads Maven dependencies; this can take several minutes"
if ! mvn "${MVN_ARGS[@]}" --file "${AUTH_DIR}/pom.xml" >"${BUILD_LOG}" 2>&1; then
  log_err "Maven build failed; last 40 lines of ${BUILD_LOG}:"
  tail -n 40 "${BUILD_LOG}" >&2
  die "Auth build failed"
fi

[[ -f "${JAR}" ]] || die "Maven reported success but ${JAR} is missing"

log_ok "built $(basename "${JAR}") ($(du -h "${JAR}" | cut -f1))"
log "full log: runtime/sst/logs/build_auth.log"
