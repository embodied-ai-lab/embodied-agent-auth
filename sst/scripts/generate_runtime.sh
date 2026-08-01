#!/usr/bin/env bash
# Generate credentials and databases outside the tracked iotauth submodule.

set -euo pipefail
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../scripts" && pwd)/lib.sh"

iscps_refuse_login_node
GRAPH="${ISCPS_LAB_ROOT}/sst/configs/warehouse_cart.graph"
WORK="${ISCPS_RUNTIME_DIR}/iotauth-generation"
SOURCE="${WORK}/source"
SST_RUNTIME="${ISCPS_RUNTIME_DIR}/sst"
PASSWORD_FILE="${SST_RUNTIME}/auth_password"
KEEP_WORK="${KEEP_GENERATION_WORK:-0}"

[[ -f "${ISCPS_IOTAUTH_DIR}/examples/generateAll.sh" ]] \
  || die "iotauth submodule is not initialized. Run: make submodules"
for command in git tar node npm mvn java openssl; do
  need_cmd "${command}"
done

mkdir -p "${SST_RUNTIME}/logs"
chmod 700 "${ISCPS_RUNTIME_DIR}" "${SST_RUNTIME}" 2>/dev/null || true
if [[ ! -f "${PASSWORD_FILE}" ]]; then
  umask 077
  "${PY}" -c 'import secrets; print(secrets.token_urlsafe(24))' > "${PASSWORD_FILE}"
fi
PASSWORD="$(tr -d '\r\n' < "${PASSWORD_FILE}")"

rm -rf "${WORK}"
mkdir -p "${SOURCE}"
cleanup_generation_work() {
  if [[ "${KEEP_WORK}" != "1" ]]; then
    rm -rf "${WORK}"
  fi
}
trap cleanup_generation_work EXIT

log_step "Creating disposable generator work tree from the pinned submodule"
git -C "${ISCPS_IOTAUTH_DIR}" archive HEAD | tar -x -C "${SOURCE}"
install -m 0644 "${GRAPH}" "${SOURCE}/examples/configs/warehouse_cart.graph"

GEN_LOG="${SST_RUNTIME}/logs/generate_iotauth.log"
if ! (
  cd "${SOURCE}/examples"
  ./generateAll.sh -g configs/warehouse_cart.graph -p "${PASSWORD}"
) >"${GEN_LOG}" 2>&1; then
  tail -n 50 "${GEN_LOG}" >&2
  die "upstream iotauth generation failed"
fi

log_step "Copying only required runtime artifacts"
rm -rf \
  "${SST_RUNTIME}/auth" \
  "${SST_RUNTIME}/configs" \
  "${SST_RUNTIME}/credentials" \
  "${SST_RUNTIME}/database"
mkdir -p \
  "${SST_RUNTIME}/auth" \
  "${SST_RUNTIME}/credentials/auth" \
  "${SST_RUNTIME}/credentials/entities" \
  "${SST_RUNTIME}/database"

install -m 0600 \
  "${SOURCE}/auth/credentials/ca/CACert.pem" \
  "${SST_RUNTIME}/credentials/auth/CACert.pem"
cp -a \
  "${SOURCE}/entity/auth_certs" \
  "${SST_RUNTIME}/credentials/entities/auth_certs"
mkdir -p "${SST_RUNTIME}/credentials/entities/keys"
cp -a \
  "${SOURCE}/entity/credentials/keys/net1" \
  "${SST_RUNTIME}/credentials/entities/keys/net1"
cp -a \
  "${SOURCE}/auth/databases/auth101" \
  "${SST_RUNTIME}/database/auth101"

"${PY}" - \
  "${SOURCE}/auth/properties/exampleAuth101.properties" \
  "${SST_RUNTIME}/auth/auth101.properties" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text(encoding="utf-8")
replacements = {
    "../databases/auth101": "../database/auth101",
    "../credentials/ca/CACert.pem": "../credentials/auth/CACert.pem",
}
for old, new in replacements.items():
    source = source.replace(old, new)
Path(sys.argv[2]).write_text(source, encoding="utf-8")
PY

"${PY}" "${ISCPS_LAB_ROOT}/sst/scripts/write_entity_configs.py" \
  --runtime-dir "${SST_RUNTIME}"

log_step "Validating runtime artifacts"
for path in \
  "${SST_RUNTIME}/auth/auth101.properties" \
  "${SST_RUNTIME}/database/auth101/auth.db" \
  "${SST_RUNTIME}/credentials/entities/auth_certs/Auth101EntityCert.pem" \
  "${SST_RUNTIME}/credentials/entities/keys/net1/Net1.VLMAgentKey.pem" \
  "${SST_RUNTIME}/credentials/entities/keys/net1/Net1.DistanceSensorKey.pem" \
  "${SST_RUNTIME}/credentials/entities/keys/net1/Net1.VisionSensorKey.pem"; do
  [[ -f "${path}" ]] || die "generator did not produce ${path}"
done

"${PY}" - "${SST_RUNTIME}/configs" <<'PY'
from pathlib import Path
import sys
from iotauth import IoTAuthContext

paths = sorted(Path(sys.argv[1]).glob("*.config"))
if len(paths) != 3:
    raise SystemExit(f"expected 3 entity configs, found {len(paths)}")
for path in paths:
    IoTAuthContext.from_config(path)
    print(f"OK {path.name}")
PY

chmod -R go-rwx "${SST_RUNTIME}/credentials" "${SST_RUNTIME}/database"
log_ok "SST state generated under runtime/sst; no generated file touched the submodule"
