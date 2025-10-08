#!/usr/bin/env bash
set -Eeuo pipefail

# --- locate naut.sh ---
naut="${NAUT_SH:-}"
if [[ -z "$naut" ]]; then
  SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
  if   [[ -x "$SCRIPT_DIR/naut.sh" ]]; then naut="$SCRIPT_DIR/naut.sh"
  elif [[ -x "./naut.sh" ]]; then           naut="./naut.sh"
  elif command -v naut.sh >/dev/null 2>&1; then naut="$(command -v naut.sh)"
  else
    echo "n_R_a_w.sh: cannot find executable naut.sh (set NAUT_SH or place naut.sh next to this script)" >&2
    exit 127
  fi
fi

# --- config ---
delay="${N_R_A_W_DELAY:-5}"                          # seconds before 'wait'
[[ "${1:-}" == "--delay" ]] && { shift; delay="${1:-5}"; shift || true; }
[[ "$delay" =~ ^[0-9]+$ ]] || { echo "n_R_a_w.sh: invalid delay '$delay'"; exit 2; }

# Optional output controls (defaults: show RUN output; hide analyze stdout)
run_stdout_sink="${N_R_A_W_RUN_STDOUT:-}"            # e.g., /tmp/run.out (empty = print to screen)
silence_run_stderr="${N_R_A_W_SILENCE_RUN_STDERR:-0}"

analyze_stdout_sink="${N_R_A_W_ANALYZE_STDOUT:-/dev/null}"
silence_analyze_stderr="${N_R_A_W_SILENCE_ANALYZE_STDERR:-0}"

# Stop early on failures?
stop_on_run_fail="${N_R_A_W_STOP_ON_RUN_FAIL:-0}"
stop_on_analyze_fail="${N_R_A_W_STOP_ON_ANALYZE_FAIL:-0}"

# --- 1) RUN (with the same args passed to this wrapper) ---
set +e
if [[ -n "$run_stdout_sink" ]]; then
  if [[ "$silence_run_stderr" == "1" ]]; then
    "$naut" RUN "$@" >"$run_stdout_sink" 2>/dev/null
  else
    "$naut" RUN "$@" >"$run_stdout_sink"
  fi
else
  if [[ "$silence_run_stderr" == "1" ]]; then
    "$naut" RUN "$@" 2>/dev/null
  else
    "$naut" RUN "$@"
  fi
fi
rc_run=$?
set -e
if (( rc_run != 0 )) && [[ "$stop_on_run_fail" == "1" ]]; then exit "$rc_run"; fi

# --- 2) ANALYZE (reads last_run.json from RUN) ---
set +e
if [[ "$silence_analyze_stderr" == "1" ]]; then
  "$naut" analyze >"$analyze_stdout_sink" 2>/dev/null
else
  "$naut" analyze >"$analyze_stdout_sink"
fi
rc_analyze=$?
set -e
if (( rc_analyze != 0 )) && [[ "$stop_on_analyze_fail" == "1" ]]; then exit "$rc_analyze"; fi

# --- 3) WAIT ---
sleep "$delay"
exec "$naut" wait
