#!/bin/bash

# Usage function to display help
usage() {
  echo "Usage: $0 [--help]"
  echo "Run 'argocd app diff' for each application listed in the input JSON."
  echo
  echo "Options:"
  echo "  --help                 Display this help message"
}

# Check for help option
if [ "$1" == "--help" ]; then
  usage
  exit 0
fi

# Read JSON input from stdin
input=$(cat)

# Iterate over each application and run the diff command
echo "$input" | jq -c '.[]' | while read -r app; do
  app_name=$(echo "$app" | jq -r '.application')
  echo "Running diff for application: $app_name" >&2
  argocd app diff "$app_name"
done
