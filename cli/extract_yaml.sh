#!/usr/bin/env bash
# extract_between.sh — print the first block between markers from STDIN
# Defaults: begin="```bash", end="```"
# Exit codes: 0=success, 2=no block found, 64=usage error
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage:
  producer | ./extract_between.sh [BEGIN_MARKER [END_MARKER]]

Description:
  Reads from standard input and prints the first block of text found between
  the BEGIN_MARKER line and the END_MARKER line (exclusive). If markers are
  not provided, defaults to:
    BEGIN_MARKER = ```bash
    END_MARKER   = ```

Options:
  -h, --help   Show this help and exit.

Examples:
  # Default markers (```bash ... ```)
  ./naut.sh wait | ./extract_between.sh > snippet.txt

  # Custom begin only (end defaults to ```)
  ./naut.sh wait | ./extract_between.sh '```yaml' > myyaml.yaml

  # Custom begin and end markers
  ./naut.sh wait | ./extract_between.sh 'START' 'END' > chunk.txt

Notes:
  • Matching is exact and line-based.
  • Carriage returns (CR) are stripped to handle CRLF inputs.
  • Prints nothing and exits with code 2 if no block is found.
USAGE
}

# Handle help flag
if [[ "${1-}" == "-h" || "${1-}" == "--help" ]]; then
  usage
  exit 0
fi

# Validate arg count
if (( $# > 2 )); then
  echo "Error: too many arguments." >&2
  usage
  exit 64
fi

begin=${1:-'```bash'}
end=${2:-'```'}

awk -v begin="$begin" -v end="$end" '
BEGIN { inblk = 0; found = 0 }
{
  line = $0
  sub(/\r$/, "", line)            # strip CR for CRLF inputs
}
(inblk == 0) && (line == begin)   { inblk = 1; next }
(inblk == 1) && (line == end)     { found = 1; exit 0 }
(inblk == 1)                      { print line }
END {
  if (found == 0) exit 2          # no block found -> nonzero exit
}
'
