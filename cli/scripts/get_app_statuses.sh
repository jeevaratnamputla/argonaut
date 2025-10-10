#!/bin/bash

# Usage function to display help
usage() {
  echo "Usage: $0 [OPTION]"
  echo "Fetch and display ArgoCD application statuses."
  echo
  echo "Options:"
  echo "  --not-synced-healthy   Display only applications that are not in Synced or Healthy state"
  echo "  -o yaml                Output the results in YAML format"
  echo "  -o table               Output the results in table format"
  echo "  --help                 Display this help message"
  echo
  echo "If no option is provided, all applications with their sync and health status will be displayed in JSON format."
}

# Check for help option
if [ "$1" == "--help" ]; then
  usage
  exit 0
fi

# Determine output format
output_format="json"
if [ "$2" == "-o" ]; then
  if [ "$3" == "yaml" ]; then
    output_format="yaml"
  elif [ "$3" == "table" ]; then
    output_format="table"
  fi
fi

# Function to output in the desired format
output() {
  case "$output_format" in
    yaml)
      yq eval -P
      ;;
    table)
      jq -r '.[] | "\(.name)\t\(.syncStatus)\t\(.healthStatus)"' | column -t -s $'\t'
      ;;
    *)
      jq .
      ;;
  esac
}

# Check if the user wants to filter for applications that are not Synced or not Healthy
if [ "$1" == "--not-synced-healthy" ]; then
  # Fetch and print only applications that are not Synced or not Healthy
  argocd app list -o json | jq '[.[] | select(.status.sync.status != "Synced" or .status.health.status != "Healthy") | {name: .metadata.name, syncStatus: .status.sync.status, healthStatus: .status.health.status}]' | output
else
  # Fetch and print all applications with their sync and health status
  #
-------------------------------------------------

  # Fetch and print all applications with their sync and health status
  argocd app list -o json | jq '[.[] | {name: .metadata.name, syncStatus: .status.sync.status, healthStatus: .status.health.status}]' | output
fi



