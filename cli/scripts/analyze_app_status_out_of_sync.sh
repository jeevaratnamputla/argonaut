#!/bin/bash

# Usage function to display help
usage() {
  echo "Usage: $0 [OPTION]"
  echo "Analyze ArgoCD applications and find OutOfSync resources."
  echo
  echo "Options:"
  echo "  -o yaml                Output the results in YAML format"
  echo "  -o json                Output the results in JSON format"
  echo "  -o table               Output the results in table format"
  echo "  --help                 Display this help message"
  echo
  echo "If no option is provided, the default output format is JSON."
}

# Check for help option
if [ "$1" == "--help" ]; then
  usage
  exit 0
fi

# Determine output format
output_format="json"
if [ "$1" == "-o" ]; then
  if [ "$2" == "yaml" ]; then
    output_format="yaml"
  elif [ "$2" == "table" ]; then
    output_format="table"
  elif [ "$2" == "json" ]; then
    output_format="json"
  fi
fi

# Read JSON input from stdin
input=$(cat)

# Function to output in the desired format
output() {
  case "$output_format" in
    yaml)
      yq eval -P
      ;;
    table)
      jq -r '.[] | "\(.application)\t\(.resources[] | .kind)\t\(.resources[] | .name)"' | column -t -s $'\t'
      ;;
    *)
      jq .
      ;;
  esac
}

# Collect results
results=$(echo "$input" | jq -c '.[]' | while read -r app; do
  # Extract application name and sync status
  app_name=$(echo "$app" | jq -r '.name')
  sync_status=$(echo "$app" | jq -r '.syncStatus')

  # Check if the application is OutOfSync
  if [ "$sync_status" == "OutOfSync" ]; then
    # Use argocd to get details of the application and find OutOfSync resources
    resources=$(argocd app get "$app_name" -o json | jq -c '[.status.resources[] | select(.status == "OutOfSync") | {kind: .kind, name: .name}]')
    echo "{\"application\": \"$app_name\", \"resources\": $resources}"
  fi
done)

# Output the results as a JSON array
echo "[$(echo "$results" | paste -sd,)]" | output
