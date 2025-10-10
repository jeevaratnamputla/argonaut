#!/bin/bash

# List all applications
apps=$(argocd app list -o name)

# Initialize variables to track the application with the most resources
max_resources=0
max_app=""

# Loop through each application
for app in $apps; do
  # Get the application details and count the resources
  resource_count=$(argocd app get $app -o json | jq '.status.resources | length')
  echo "Application: $app, Resource Count: $resource_count"
  
  # Update the application with the most resources
  if [ "$resource_count" -gt "$max_resources" ]; then
    max_resources=$resource_count
    max_app=$app
  fi
done

# Print the application with the most resources
echo "Application with the most resources: $max_app, Resource Count: $max_resources"
