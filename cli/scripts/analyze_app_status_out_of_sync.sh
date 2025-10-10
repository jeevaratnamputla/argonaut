#!/bin/bash

# Read JSON input from stdin
input=$(cat)

# Iterate over each application
echo "$input" | jq -c '.[]' | while read -r app; do
  # Extract application name and sync status
  app_name=$(echo "$app" | jq -r '.name')
  sync_status=$(echo "$app" | jq -r '.syncStatus')

  # Check if the application is OutOfSync
  if [ "$sync_status" == "OutOfSync" ]; then
    echo "Application: $app_name is OutOfSync. Checking resources..."

    # Use argocd to get details of the application and find OutOfSync resources
    argocd app get "$app_name" -o json | jq -r '.status.resources[] | select(.status == "OutOfSync") | "\(.kind) \(.name)"'
  fi
done
