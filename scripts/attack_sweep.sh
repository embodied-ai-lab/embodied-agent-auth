#!/usr/bin/env bash
# Repeat the malicious-distance run over several values and retain every result.

set -u
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

iscps_refuse_login_node
REPETITIONS="${REPETITIONS:-3}"
DISTANCES="${DISTANCES:-0.6 1.0 1.5 2.0 4.0 6.0 10.0}"
SWEEP_DIR="$(iscps_new_run_dir attack_sweep)"
CSV="${SWEEP_DIR}/trials.csv"
SUMMARY="${SWEEP_DIR}/summary.json"
printf '%s\n' \
  'distance_m,repetition,status,execution_valid,expected_action_observed,action,cart_state,safe,latency_ms,run_dir,errors' \
  > "${CSV}"
FAILED_TRIALS=0

for distance in ${DISTANCES}; do
  for repetition in $(seq 1 "${REPETITIONS}"); do
    : > "${ISCPS_RUNTIME_DIR}/last_run"
    trial_status=0
    FALSE_DISTANCE="${distance}" \
      "${ISCPS_LAB_ROOT}/scripts/run_scenario.sh" attack \
      --false-distance "${distance}" || trial_status=$?
    run_dir="$(tr -d '\r\n' < "${ISCPS_RUNTIME_DIR}/last_run" 2>/dev/null || true)"
    if [[ -n "${run_dir}" ]]; then
      summary_path="${run_dir}/summary.json"
    else
      summary_path="${SWEEP_DIR}/missing-${distance}-${repetition}/summary.json"
    fi
    if ! "${PY}" "${ISCPS_LAB_ROOT}/scripts/sweep_summary.py" record \
      "${summary_path}" \
      "${CSV}" \
      "${distance}" \
      "${repetition}" \
      "${trial_status}"; then
      FAILED_TRIALS=$((FAILED_TRIALS + 1))
      log_err "sweep trial ${distance}/${repetition} was execution-invalid"
    fi
  done
done

report_status=0
"${PY}" "${ISCPS_LAB_ROOT}/scripts/sweep_summary.py" report \
  "${CSV}" "${SUMMARY}" || report_status=$?
if [[ -f "${SUMMARY}" ]]; then
  "${PY}" "${ISCPS_LAB_ROOT}/scripts/plot_sweep.py" --sweep-dir "${SWEEP_DIR}" \
    || log_warn "could not render sweep.png"
fi
log_ok "sweep evidence: ${CSV}"
if (( FAILED_TRIALS > 0 || report_status != 0 )); then
  die "${FAILED_TRIALS} sweep trial(s) were execution-invalid"
fi
