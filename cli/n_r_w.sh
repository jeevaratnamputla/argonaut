#!/usr/bin/env bash
set -Eeuo pipefail

# --- locate naut.sh ---
# Order: env NAUT_SH > alongside this script > ./naut.sh (cwd) > PATH
naut="${NAUT_SH:-}"
if [[ -z "${naut}" ]]; then
  SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
  if [[ -x "$SCRIPT_DIR/naut.sh" ]]; then
    naut="$SCRIPT_DIR/naut.sh"
  elif [[ -x "./naut.sh" ]]; then
    naut="./naut.sh"
  elif command -v naut.sh >/dev/null 2>&1; then
    naut="$(command -v naut.sh)"
  else
    echo "n_r_w.sh: cannot find executable naut.sh (set NAUT_SH or place naut.sh next to this script)" >&2
    exit 127
  fi
fi

# --- config ---
delay="${N_R_W_DELAY:-5}"                   # default wait seconds
[[ "${1:-}" == "--delay" ]] && { shift; delay="${1:-5}"; shift || true; }
[[ "$delay" =~ ^[0-9]+$ ]] || { echo "n_r_w.sh: invalid delay '$delay'"; exit 2; }

recommend_stdout_sink="${N_R_W_RECOMMEND_STDOUT:-/dev/null}"  # where to send recommend stdout
silence_stderr="${N_R_W_SILENCE_STDERR:-0}"                   # 1 = also silence stderr
stop_on_fail="${N_R_W_STOP_ON_FAIL:-0}"                       # 1 = don't run wait if recommend fails

# --- run: naut.sh recommend <ALL ORIGINAL ARGS> (suppress stdout) ---
set +e
if [[ "$silence_stderr" == "1" ]]; then
  "$naut" recommend "$@" >"$recommend_stdout_sink" 2>/dev/null
else
  "$naut" recommend "$@" >"$recommend_stdout_sink"
fi
rc=$?
set -e

if (( rc != 0 )) && [[ "$stop_on_fail" == "1" ]]; then
  exit "$rc"
fi

# --- wait, then run: naut.sh wait ---
sleep "$delay"
exec "$naut" wait
