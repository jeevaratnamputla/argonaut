#!/bin/bash

# Define the ArgoCD server URL
ARGOCD_SERVER="https://argocd.sandbox.opsmx.net"

# Function to check if logged in to ArgoCD
check_login() {
  if ! argocd context &> /dev/null; then
    echo "Not logged in to ArgoCD. Please log in and try again."
    exit 1
  fi
}

recommend_similar_apps() {
  local app_name=$1
  local similar_apps

  echo "Application '$app_name' does not exist in ArgoCD. Searching for similar applications..."

  # Try to find similar applications
  similar_apps=$(argocd app list -o name | grep -i "$app_name" | head -n 5)

  # If no similar applications found, start removing characters
  while [ -z "$similar_apps" ] && [ ${#app_name} -gt 3 ]; do
    # Remove the last character and try again
    app_name=${app_name%?}
    similar_apps=$(argocd app list -o name | grep -i "$app_name" | head -n 5)

    # If still no results, remove the first character and try again
    if [ -z "$similar_apps" ]; then
      app_name=${app_name#?}
      similar_apps=$(argocd app list -o name | grep -i "$app_name" | head -n 5)
    fi
  done

  # Print the similar applications found
  if [ -n "$similar_apps" ]; then
    echo "Here are some similar applications:"
    echo "$similar_apps"
  else
    echo "No similar applications found."
  fi
}


# Function to check if application exists
check_application_exists() {
  local app_name=$1
  if ! argocd app get "$app_name" &> /dev/null; then
    echo "Application '$app_name' does not exist in ArgoCD."
    recommend_similar_apps "$app_name"
    exit 1
  fi
}

# Function to get application JSON, remove .metadata.managedFields, compress it, and print character and token count
get_application_json() {
  local app_name=$1
  local json_output
  json_output=$(argocd app get "$app_name" -o json | jq 'del(.metadata.managedFields)' | jq -c)
  
  # Print the compressed JSON
  echo "$json_output"
  
  # Print the number of characters
  echo "Number of characters: $(echo -n "$json_output" | wc -c)"
  
  # Print the number of tokens
  #echo "Number of tokens: $(echo "$json_output" | jq -c 'paths | length' | wc -l)"
}

# Main script execution
main() {
  # Check if logged in to ArgoCD
  check_login

  # Check if application name is provided
  if [ -z "$1" ]; then
    echo "Please provide an application name."
    exit 1
  fi

  # Check if application exists
  check_application_exists "$1"

  # Get application JSON, remove .metadata.managedFields, compress it, and print character and token count
  get_application_json "$1"
}

# Run the main function with the first argument as the application name
main "$1"
