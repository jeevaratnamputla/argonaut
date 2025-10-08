#!/usr/bin/env bash
set -Eeuo pipefail

# --- locate naut.sh ---
# Order: env NAUT_SH > alongside this script > ./naut.sh (cwd) > PATH
naut="${NAUT_SH:-}"
if [[ -z "$naut" ]]; then
  SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
  if [[ -x "$SCRIPT_DIR/naut.sh" ]]; then
    naut="$SCRIPT_DIR/naut.sh"
  elif [[ -x "./naut.sh" ]]; then
    naut="./naut.sh"
  elif command -v naut.sh >/dev/null 2>&1; then
    naut="$(command -v naut.sh)"
  else
    echo "n_a_w.sh: cannot find executable naut.sh (set NAUT_SH or place naut.sh next to this script)" >&2
    exit 127
  fi
fi

# --- config ---
# Delay before running 'wait' (seconds). Override with env or --delay N.
delay="${N_A_W_DELAY:-5}"
if [[ "${1:-}" == "--delay" ]]; then
  shift
  delay="${1:-5}"
  shift || true
fi
[[ "$delay" =~ ^[0-9]+$ ]] || { echo "n_a_w.sh: invalid delay '$delay'"; exit 2; }

# Where to send 'analyze' stdout (default: discard). Set a file path to log instead.
analyze_stdout_sink="${N_A_W_ANALYZE_STDOUT:-/dev/null}"
# Also silence stderr from 'analyze'? (0/1)
silence_stderr="${N_A_W_SILENCE_STDERR:-0}"
# Stop immediately if 'analyze' fails? (0/1). By default we continue to 'wait'.
stop_on_fail="${N_A_W_STOP_ON_FAIL:-0}"
# Extra args to pass to 'wait' (space-separated string OK)
wait_args=( ${N_A_W_WAIT_ARGS:-} )

# --- run: naut.sh analyze <ALL ORIGINAL ARGS> (suppress stdout) ---
set +e
if [[ "$silence_stderr" == "1" ]]; then
  "$naut" analyze "$@" >"$analyze_stdout_sink" 2>/dev/null
else
  "$naut" analyze "$@" >"$analyze_stdout_sink"
fi
rc=$?
set -e

# Note: 'analyze' commonly returns the original command's exit code (may be non-zero).
if (( rc != 0 )) && [[ "$stop_on_fail" == "1" ]]; then
  exit "$rc"
fi

# --- wait, then run: naut.sh wait ---
sleep "$delay"
exec "$naut" wait "${wait_args[@]}"
