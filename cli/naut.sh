#!/usr/bin/env bash
set -euo pipefail

# =========================
# naut — Argonaut CLI (bash)
# =========================
# Requirements: bash, curl
# Optional: jq (pretty/robust JSON handling)
#
# State layout (default NAUT_HOME=~/.naut):
#   ~/.naut/config                (key=value: ARGONAUT_URL, ARGONAUT_TOKEN, ARGONAUT_USER)
#   ~/.naut/current_thread        (string: active thread_ts)
#   ~/.naut/threads/<thread_fs>/
#       last_command              (plain text)
#       last_run.json             (JSON with command, exit_code, stdout, stderr)
#       history.log               (append-only text)
#
# Threading:
#   channel: "cli"
#   thread_ts: "cli-${ARGONAUT_USER}-${epoch}"
#   We use a filesystem-safe dir name by replacing '/' in user with '__'.
#
# Endpoints (adjust paths if your server differs):
#   POST $ARGONAUT_URL/webhook   (type: "message")
#   POST $ARGONAUT_URL/v1/analyze     (type: "analysis")
#   GET  $ARGONAUT_URL/v1/ping        (login check; optional)

VERSION="0.1"

# ---------- Config & paths ----------
NAUT_HOME="${NAUT_HOME:-$HOME/.naut}"
CONFIG_FILE="$NAUT_HOME/config"
CURRENT_THREAD_FILE="$NAUT_HOME/current_thread"
THREADS_DIR="$NAUT_HOME/threads"

ARGONAUT_URL="${ARGONAUT_URL:-}"
ARGONAUT_TOKEN="${ARGONAUT_TOKEN:-}"
ARGONAUT_USER="${ARGONAUT_USER:-}"

CHANNEL="cli"
NAUT_MAX_PAYLOAD_BYTES="${NAUT_MAX_PAYLOAD_BYTES:-65536}"  # 64KB
NAUT_CONFIRM_RISKY="${NAUT_CONFIRM_RISKY:-true}"

mkdir -p "$NAUT_HOME" "$THREADS_DIR"

NAUT_HTTP_CONNECT_TIMEOUT="${NAUT_HTTP_CONNECT_TIMEOUT:-10}" # seconds to establish TCP
NAUT_HTTP_MAX_TIME="${NAUT_HTTP_MAX_TIME:-0}"               # 0 = no overall limit (wait forever)

ARGONAUT_THREADS_PATH="${ARGONAUT_THREADS_PATH:-/threads}"


# ---------- Helpers ----------
err() { printf '[naut] %s\n' "$*" >&2; }
die() { err "$*"; exit 1; }

have_jq() { command -v jq >/dev/null 2>&1; }

load_config() {
  if [[ -f "$CONFIG_FILE" ]]; then
    # shellcheck disable=SC1090
    . "$CONFIG_FILE"
  fi
  # env vars override file
  : "${ARGONAUT_URL:=${ARGONAUT_URL}}"
  : "${ARGONAUT_TOKEN:=${ARGONAUT_TOKEN}}"
  : "${ARGONAUT_USER:=${ARGONAUT_USER}}"
}

save_config() {
  umask 077
  cat >"$CONFIG_FILE" <<EOF
ARGONAUT_URL=$ARGONAUT_URL
ARGONAUT_TOKEN=$ARGONAUT_TOKEN
ARGONAUT_USER=$ARGONAUT_USER
EOF
}

# Remove leading "users/" and all slashes from the user for thread_ts
sanitize_user_for_thread() {
  local u="$ARGONAUT_USER"
  u="${u#users/}"         # drop leading users/
  u="${u//\//}"           # remove any remaining slashes
  printf '%s' "$u"
}

# Remove *all* slashes from an arbitrary thread_ts (for user-provided values)
sanitize_thread_ts() {
  local t="$1"
  t="${t//\//}"           # remove all '/'
  printf '%s' "$t"
}


require_config() {
  [[ -n "${ARGONAUT_URL:-}" ]]   || die "Argonaut URL not set. Run: naut login --url https://..."
  [[ -n "${ARGONAUT_TOKEN:-}" ]] || die "Argonaut token not set. Run: naut login --token <token> ..."
  [[ -n "${ARGONAUT_USER:-}" ]]  || die "Argonaut user not set. Run: naut login --user users/123..."
}

fs_safe() {
  # Make a string safe for filesystem (replace '/' with '__')
  printf '%s' "$1" | sed 's|/|__|g'
}

now_epoch() { date +%s; }

current_thread_get() {
  if [[ -f "$CURRENT_THREAD_FILE" ]]; then
    cat "$CURRENT_THREAD_FILE"
  else
    echo ""
  fi
}

current_thread_set() {
  printf '%s' "$1" >"$CURRENT_THREAD_FILE"
}

thread_dir() {
  local thread_ts="$1"
  local user_fs
  user_fs="$(fs_safe "$ARGONAUT_USER")"
  # Expecting thread_ts format "cli-${ARGONAUT_USER}-${epoch}" but we only need a stable fs dir:
  printf '%s/%s' "$THREADS_DIR" "$(fs_safe "$thread_ts")"
}

ensure_thread() {
  local thread_ts="$1"
  local dir
  thread_ts="$(sanitize_thread_ts "$thread_ts")"
  dir="$(thread_dir "$thread_ts")"
  mkdir -p "$dir"
}
new_thread_ts() {
  local ts; ts="$(now_epoch)"
  local u;  u="$(sanitize_user_for_thread)"
  printf 'cli-%s-%s' "$u" "$ts"
}


json_escape() {
  # Escapes a raw string for JSON string context (no surrounding quotes)
  # Replaces backslash, quote, tab, CR, LF
  sed -e 's/\\/\\\\/g' \
      -e 's/"/\\"/g' \
      -e $'s/\t/\\t/g' \
      -e $'s/\r/\\r/g' \
      -e $'s/\n/\\n/g'
}

truncate_blob() {
  # Reads stdin, truncates to NAUT_MAX_PAYLOAD_BYTES, appends marker if truncated.
  local max="$NAUT_MAX_PAYLOAD_BYTES"
  # Use dd for byte-accurate truncation
  local data truncated=false
  if data="$(dd bs="$max" count=1 status=none)"; then
    if [[ "$(printf '%s' "$data" | wc -c | tr -d ' ')" -ge "$max" ]]; then
      truncated=true
    fi
    printf '%s' "$data"
    $truncated && printf '%s' "[TRUNCATED]"
  else
    cat
  fi
}

# parse_fenced_command() {
#   # Input: full server response on stdin
#   # Output: first fenced code block content on stdout (trimmed), or empty if not found
#   awk '
#     BEGIN { inblock=0 }
#     /^```[[:space:]]*$/ { if(inblock==0){inblock=1; next} else {inblock=0; exit} }
#     { if(inblock==1){ print } }
#   ' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
# }

parse_fenced_command() {
  # Read full input first
  local text; text="$(cat)"; text="$(printf '%s' "$text" | tr -d '\r')"

  # 1) Try single-line inline fence: ... ``` <cmd> ```
  #    (grab the first occurrence on any line)
  local inline
  inline="$(printf '%s\n' "$text" \
    | sed -n 's/.*```[[:space:]]*\([^`][^`]*\)[[:space:]]*```.*$/\1/p' \
    | head -n1)"
  if [[ -n "$inline" ]]; then
    printf '%s' "$inline" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
    return 0
  fi

  # 2) Fallback to block fence:
  #    ```
  #    <cmd possibly multi-line>
  #    ```
  printf '%s\n' "$text" | awk '
    BEGIN { inblock=0 }
    /^```[[:space:]]*$/ { if(inblock==0){inblock=1; next} else {inblock=0; exit} }
    { if(inblock==1){ print } }
  ' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}


is_risky_command() {
  local cmd="$1"
  # Simple heuristics; expand as needed
  [[ "$cmd" =~ rm[[:space:]]+-rf[[:space:]]+/?.* ]] && return 0
  [[ "$cmd" =~ kubectl[[:space:]]+delete($|[[:space:]]) ]] && return 0
  [[ "$cmd" =~ helm[[:space:]]+uninstall($|[[:space:]]) ]] && return 0
  [[ "$cmd" =~ argocd[[:space:]]+app[[:space:]]+delete($|[[:space:]]) ]] && return 0
  return 1
}

confirm_if_risky() {
  local cmd="$1"
  if [[ "${NAUT_CONFIRM_RISKY}" == "true" ]] && is_risky_command "$cmd"; then
    read -r -p "[naut] This looks destructive. Proceed? [y/N]: " ans
    case "${ans:-}" in
      y|Y|yes|YES) return 0 ;;
      *) echo "[naut] Aborted."; exit 0 ;;
    esac
  fi
}

log_history() {
  local thread_ts="$1"; shift
  thread_ts="$(sanitize_thread_ts "$thread_ts")"
  local dir; dir="$(thread_dir "$thread_ts")"
  printf '[%(%Y-%m-%d %H:%M:%S)T] %s\n' -1 "$*" >> "$dir/history.log"
}

post_json() {
  # $1 = path (e.g., /v1/recommend), body on stdin
  local path="$1"
  local tmp resp_code resp_body
  tmp="$(mktemp)"
  #echo abracadabra
  #echo url is in post_json "${ARGONAUT_URL%/}${path}" >&2

  # Capture both body and HTTP code (do NOT use -f, which hides body on errors)
  # resp_code=$(curl -sS -w '%{http_code}' \
  #   -H "Authorization: Bearer ${ARGONAUT_TOKEN}" \
  #   -H "Content-Type: application/json" \
  #   --data-binary @- \
  #   -o "$tmp" \
  #   "${ARGONAUT_URL%}${path}" \
  # )
  resp_code=$(curl -sS -w '%{http_code}' \
  --connect-timeout "$NAUT_HTTP_CONNECT_TIMEOUT" \
  --max-time "$NAUT_HTTP_MAX_TIME" \
  -H "Authorization: Bearer ${ARGONAUT_TOKEN}" \
  -H "Content-Type: application/json" \
  --data-binary @- \
  -o "$tmp" \
  "${ARGONAUT_URL%}${path}" \
)
}
get_url() {
  local path="$1"
  echo "path is ${path}" > 2
  local tmp resp_code resp_body
  tmp="$(mktemp)"

  #echo "URL is "${ARGONAUT_URL%}${path}" in get_url" >&2
  
  resp_code=$(curl -sS -w '%{http_code}' \
    --connect-timeout "${NAUT_HTTP_CONNECT_TIMEOUT:-10}" \
    --max-time "${NAUT_HTTP_MAX_TIME:-0}" \
    -H "Authorization: Bearer ${ARGONAUT_TOKEN}" \
    -o "$tmp" \
    "${ARGONAUT_URL%}${path}" )
  resp_body="$(cat "$tmp")"; rm -f "$tmp"

  if [[ "$resp_code" -ge 400 ]]; then
    printf '[naut] HTTP %s GET %s\n' "$resp_code" "$path" >&2
    if command -v jq >/dev/null 2>&1; then
      echo "$resp_body" | jq . 2>/dev/null || echo "$resp_body"
    else
      echo "$resp_body"
    fi
    return 1
  fi

  printf '%s' "$resp_body"
}



get_last_assistant_message() {
  local thread_ts="$1"

  # Fetch the thread JSON
  #>&2 echo "thread_ts is ${thread_ts} in get_last_assistant_message"
  #>&2 echo "URL is ${ARGONAUT_THREADS_PATH}/${thread_ts} in get_last_assistant_message"

  local resp
  resp="$(get_url "${ARGONAUT_THREADS_PATH}/${thread_ts}")" || return 1

  if command -v jq >/dev/null 2>&1; then
    # Take last .messages[] where role == "assistant" (case-insensitive)
    printf '%s' "$resp" | jq -r '
      (.messages // [])
      | map(select((.role|tostring|ascii_downcase)=="assistant"))
      | last
      | (.content // empty)
    '
  else
    # Naive fallback without jq
    echo "$resp" | awk '
      BEGIN{last_line=""}
      /"role"[[:space:]]*:[[:space:]]*"assistant"/{assistant=1; next}
      assistant && /"content"[[:space:]]*:/{
        match($0, /"content"[[:space:]]*:[[:space:]]*"(.*)"/, m);
        if(m[1]!=""){ last_line=m[1]; assistant=0 }
      }
      END{ print last_line }
    '
  fi
}





# ---------- Commands ----------
cmd_login() {
  local url="" token="" user=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --url) url="$2"; shift 2 ;;
      --token) token="$2"; shift 2 ;;
      --user) user="$2"; shift 2 ;;
      *) die "Unknown flag for login: $1" ;;
    esac
  done




  load_config
  [[ -n "$url" ]]   && ARGONAUT_URL="$url"
  [[ -n "$token" ]] && ARGONAUT_TOKEN="$token"
  [[ -n "$user" ]]  && ARGONAUT_USER="$user"

  # Prompt if still empty
  if [[ -z "${ARGONAUT_URL}" ]]; then
    read -r -p "Argonaut URL (e.g., https://argonaut.example.com): " ARGONAUT_URL
  fi
  if [[ -z "${ARGONAUT_TOKEN}" ]]; then
    read -r -p "API token: " ARGONAUT_TOKEN
  fi
  if [[ -z "${ARGONAUT_USER}" ]]; then
    read -r -p "User (e.g., users/1050375203...): " ARGONAUT_USER
  fi

  save_config

  # Optional ping
  if ! curl -sS -H "Authorization: Bearer ${ARGONAUT_TOKEN}" \
        "${ARGONAUT_URL%/}/v1/ping" >/dev/null; then
    err "Warning: ping failed; credentials saved anyway."
  fi

  echo "[naut] Login saved to $CONFIG_FILE"
}

cmd_logout() {
  if [[ -f "$CONFIG_FILE" ]]; then
    rm -f "$CONFIG_FILE"
    echo "[naut] Logged out (config removed)."
  else
    echo "[naut] Already logged out."
  fi
}

cmd_status() {
  load_config
  printf "naut v%s\n" "$VERSION"
  printf "Argonaut URL : %s\n" "${ARGONAUT_URL:-<unset>}"
  printf "Argonaut User: %s\n" "${ARGONAUT_USER:-<unset>}"
  local t; t="$(current_thread_get)"
  printf "Current thread: %s\n" "${t:-<none>}"
  if [[ -n "${t}" ]]; then
    local lc="$(thread_dir "$t")/last_command"
    if [[ -f "$lc" ]]; then
      printf "Last command: %s\n" "$(tr -d '\n' < "$lc")"
    fi
  fi
}

cmd_thread_ls() {
  load_config
  shopt -s nullglob
  for d in "$THREADS_DIR"/*; do
    [[ -d "$d" ]] || continue
    local name; name="$(basename "$d")"
    local t_raw="$name"
    # Display fs-safe back to raw (reverse replacement of '__' -> '/')
    local t_disp="${t_raw//__/\/}"
    printf "%s\n" "$t_disp"
  done
}

cmd_thread_use() {
  load_config
  local t="${1:-}"; [[ -n "$t" ]] || die "Usage: naut thread use <thread_ts>"
  current_thread_set "$t"
  echo "[naut] Active thread -> $t"
}

cmd_recommend() {
  load_config; require_config

  local text="" file="" thread_ts="" new_thread=false
  local is_first=false

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -c|--context) text="$2"; shift 2 ;;
      -f|--file) file="$2"; shift 2 ;;
      --thread-ts) thread_ts="$2"; shift 2 ;;
      --new-thread) new_thread=true; shift ;;
      *) die "Unknown flag for recommend: $1" ;;
    esac
  done

  if [[ -n "$file" ]]; then
    text="$(cat "$file")"
  elif [[ -z "$text" ]]; then
    if [ -t 0 ]; then
      die "Provide -c TEXT, -f FILE, or pipe stdin."
    else
      text="$(cat)"
    fi
  fi

  if [[ -n "$thread_ts" ]]; then
    is_first=false
  else
    local cur; cur="$(current_thread_get)"
    if $new_thread || [[ -z "$cur" ]]; then
      thread_ts="$(new_thread_ts)"
      is_first=true
      current_thread_set "$thread_ts"
      ensure_thread "$thread_ts"
    else
      thread_ts="$cur"
      is_first=false
    fi
  fi

  ensure_thread "$thread_ts"
  local dir; dir="$(thread_dir "$thread_ts")"

  # Build JSON payload
  if have_jq; then
    payload="$(jq -n \
      --arg user "$ARGONAUT_USER" \
      --arg thread "$thread_ts" \
      --arg channel "$CHANNEL" \
      --arg text "$text" \
      --arg io "command_line" \
      --argjson first "$is_first" \
      '{user:$user,type:"message",thread_ts:$thread,channel:$channel,text:$text,IO_type:$io,isFirstMessage:$first}')"
  else
    esc_text="$(printf '%s' "$text" | json_escape)"
    payload=$(cat <<EOF
{"user":"$ARGONAUT_USER","type":"message","thread_ts":"$thread_ts","channel":"$CHANNEL","text":"$esc_text","IO_type":"command_line","isFirstMessage":$($is_first && echo true || echo false)}
EOF
)
  fi

  # Send
  echo sending for recommendation "$payload"
  resp="$(printf '%s' "$payload" | post_json "/webhook" )"
  if [[ -z "$resp" ]]; then
    die "Waiting for Argonaut to respond. to check for a new response try ./naut.sh wait "
  fi

  # Show server reply verbatim
  printf '%s\n' "$resp"

  # Extract fenced command
  cmd="$(printf '%s' "$resp" | parse_fenced_command)"
  if [[ -n "$cmd" ]]; then
    printf '%s\n' "$cmd" > "$dir/last_command"
    log_history "$thread_ts" "recommend -> $(printf '%s' "$cmd")"
  else
    err "No fenced command found in response; not updating last_command."
  fi
}

cmd_run() {
  load_config; require_config

  local thread_ts; thread_ts="$(current_thread_get)"
  [[ -n "$thread_ts" ]] || die "No active thread. Run 'naut recommend --new-thread -c \"...\"' first."

  local dir; dir="$(thread_dir "$thread_ts")"
  local cmd=""

  # --- parse args ---
  if [[ $# -gt 0 ]]; then
    if [[ "$1" == "-c" ]]; then
      shift
      [[ $# -gt 0 ]] || die "RUN -c requires a command string"
      # Use the exact string the user provided (best for pipes/redirs)
      cmd="$1"
      shift
    else
      # Reconstruct a shell-safe command string from tokens.
      # This preserves spaces in args like "my app" by adding quotes/escapes.
      printf -v cmd '%q ' "$@"
      cmd="${cmd% }"
    fi
  else
    [[ -f "$dir/last_command" ]] || die "No last command stored. Use 'naut recommend' or pass a command: naut RUN -c \"...\""
    cmd="$(cat "$dir/last_command")"
  fi

  # Normalize CR (Windows)
  cmd="${cmd//$'\r'/}"
  echo "[naut] RUN -> $cmd" >&2

  confirm_if_risky "$cmd"
  echo "[naut] $cmd is not risky" >&2

  # Execute
  set +e
  stdout_file="$(mktemp)"; stderr_file="$(mktemp)"
  bash -lc "$cmd" >"$stdout_file" 2>"$stderr_file"
  exit_code=$?
  set -e

  echo "Exit code: $exit_code" >&2

  # Read outputs (keep raw files only if you want; currently we inline+delete)
  stdout_raw="$(cat "$stdout_file")"
  stderr_raw="$(cat "$stderr_file")"
  rm -f "$stdout_file" "$stderr_file"

  # Truncate for send/storage
  stdout_trunc="$(printf '%s' "$stdout_raw" | head -c 4000)"
  stderr_trunc="$(printf '%s' "$stderr_raw" | head -c 4000)"

  # Prepare last_run.json (contract for cmd_analyze)
  if have_jq; then
    last_run_json="$(jq -n \
      --arg cmd "$cmd" \
      --argjson code "$exit_code" \
      --arg out "$stdout_trunc" \
      --arg err "$stderr_trunc" \
      '{command:$cmd,exit_code:$code,stdout:$out,stderr:$err}')"
  else
    esc_out="$(printf '%s' "$stdout_trunc" | json_escape)"
    esc_err="$(printf '%s' "$stderr_trunc" | json_escape)"
    esc_cmd="$(printf '%s' "$cmd" | json_escape)"
    last_run_json='{"command":"'"$esc_cmd"'","exit_code":'"$exit_code"',"stdout":"'"$esc_out"'","stderr":"'"$esc_err"'"}'
  fi

  printf '%s' "$last_run_json" > "$dir/last_run.json"

  # Echo outputs to user
  printf '%s' "$stdout_raw"
  [[ -n "$stderr_raw" ]] && printf '%s' "$stderr_raw" >&2

  log_history "$thread_ts" "run ($exit_code): $cmd"
  return "$exit_code"
}


cmd_analyze() {
  load_config; require_config

  local user="${ARGONAUT_USER:-users/gopaljayanthi}"
  local channel="${ARGONAUT_CHANNEL:-cli}"
  local is_first=false
  local limit="${ANALYZE_LIMIT:-12000}"
  local thread_ts="${ARGONAUT_THREAD_TS:-}"

  # flags (no command here; we only read cmd_run's artifacts)
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --user)    user="$2"; shift 2;;
      --channel) channel="$2"; shift 2;;
      --thread)  thread_ts="$2"; shift 2;;
      --first)   is_first=true; shift;;
      --limit)   limit="$2"; shift 2;;
      *) die "cmd_analyze: unknown option: $1";;
    esac
  done

  [[ -n "$thread_ts" ]] || thread_ts="$(current_thread_get)" \
    || die "No active thread. Run 'naut recommend --new-thread -c \"...\"' first."

  local dir; dir="$(thread_dir "$thread_ts")"
  local last_json="$dir/last_run.json"
  [[ -f "$last_json" ]] || die "No $last_json. Run 'naut run -- ...' first."
  have_jq || die "'jq' is required"
  type post_json >/dev/null 2>&1 || die "'post_json' function not found"

  # Pull what cmd_run saved (cmd, exit_code, stdout, stderr)
  local cmd exit_code stdout_raw stderr_raw
  cmd="$(jq -r '.command // ""'   "$last_json")"
  exit_code="$(jq -r '.exit_code // 0' "$last_json")"
  stdout_raw="$(jq -r '.stdout  // ""' "$last_json")"
  stderr_raw="$(jq -r '.stderr  // ""' "$last_json")"

  # Normalize CRLF and (optionally) re-truncate for posting
  stdout_raw="${stdout_raw//$'\r'/}"
  stderr_raw="${stderr_raw//$'\r'/}"
  if [[ "$limit" -gt 0 ]]; then
    local s="${#stdout_raw}" e="${#stderr_raw}"
    stdout_raw="${stdout_raw:0:limit}"; (( s > limit )) && stdout_raw+=$'\n[...stdout truncated]'
    stderr_raw="${stderr_raw:0:limit}"; (( e > limit )) && stderr_raw+=$'\n[...stderr truncated]'
  fi

  # Compose the Argonaut "message" text
  local TEXT
  TEXT=$(
    printf '[IO_type]: command_line\n'
    printf '[command]: %s\n' "$cmd"
    printf '[exit_code]: %s\n' "$exit_code"
    printf '[source]: %s\n' "$last_json"
    printf '\n----- STDOUT -----\n%s\n' "$stdout_raw"
    printf '\n----- STDERR -----\n%s\n' "$stderr_raw"
  )

  # JSON boolean for isFirstMessage
  local is_first_bool; $is_first && is_first_bool=true || is_first_bool=false

  # Build payload (Argonaut “message” schema)
  local payload
  payload="$(jq -n \
    --arg user "$user" \
    --arg type "message" \
    --arg thread_ts "$thread_ts" \
    --arg channel "$channel" \
    --arg text "$TEXT" \
    --arg io "command_line" \
    --argjson isFirstMessage "$is_first_bool" \
    '{user:$user,type:$type,thread_ts:$thread_ts,channel:$channel,text:$text,IO_type:$io,isFirstMessage:$isFirstMessage}'
  )"

echo "[naut] sending output of $cmd to Argonaut" >&2
echo
  # IMPORTANT: post_json reads body from stdin and wants a *path*
  printf '%s' "$payload" | post_json "/webhook" \
    || die "post_json failed"
echo
echo "[naut] successfully sent output of $cmd to Argonaut. to see the response try ./naut.sh wait" >&2
echo
  log_history "$thread_ts" "analyze: $cmd"
  return "$exit_code"
}


cmd_wait() {
  load_config; require_config
  local thread_ts; thread_ts="$(current_thread_get)"
  [[ -n "$thread_ts" ]] || die "No active thread. Start with: naut recommend --new-thread -c \"...\""

#echo "thread ls: using thread_ts='$thread_ts'" >&2


  echo "[naut] Checking thread $thread_ts ..."
  echo ---------------------------------------------
  local msg; msg="$(get_last_assistant_message "$thread_ts")" || {
    err "Failed to fetch thread or parse response."
    return 1
  }

  if [[ -z "$msg" ]]; then
    err "No Assistant message found yet."
    return 1
  fi

  # Show the assistant message verbatim
  echo
  printf '%s\n' "$msg"

  # If it contains a fenced command, store it as last_command
  local dir; dir="$(thread_dir "$thread_ts")"
  local cmd; cmd="$(printf '%s' "$msg" | parse_fenced_command)"
  if [[ -n "$cmd" ]]; then
    printf '%s\n' "$cmd" > "$dir/last_command"
    log_history "$thread_ts" "wait -> $(printf '%s' "$cmd")"
  else
    echo -------------------------------------------------
    err "Argonaut did not recommend any further commands."
  fi
}

usage() {
  cat <<EOF
naut v$VERSION — Argonaut CLI (bash)

Usage:
  naut login [--url URL] [--token TOKEN] [--user USER]
  naut logout
  naut status

  naut recommend [-c TEXT | -f FILE | (stdin)] [--thread-ts THREAD] [--new-thread]
  naut RUN ["SOME_COMMAND_HERE"]
  naut analyze

  naut thread ls
  naut thread use <thread_ts>
  naut wait
EOF
}

# ---------- Entry ----------
main() {
  local cmd="${1:-}"; shift || true
  case "$cmd" in
    -h|--help|help|"") usage ;;
    login)     cmd_login "$@" ;;
    logout)    cmd_logout "$@" ;;
    status)    cmd_status "$@" ;;
    recommend) cmd_recommend "$@" ;;
    RUN)       cmd_run "$@" ;;
    analyze)   cmd_analyze "$@" ;;
    thread)
      local sub="${1:-}"; shift || true
      case "$sub" in
        ls)  cmd_thread_ls "$@" ;;
        use) cmd_thread_use "$@" ;;
        *)   die "Unknown thread subcommand. Use: naut thread ls|use <thread_ts>" ;;
      esac
      ;;
    wait)      cmd_wait "$@" ;;
    *) die "Unknown command: $cmd (use --help)" ;;
  esac
}

main "$@"

