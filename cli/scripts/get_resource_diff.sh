#!/bin/bash

# Usage function to display help
usage() {
  echo "Usage: $0 [--help]"
  echo "Run 'argocd app diff' for each application listed in the input JSON and print the source details and application URL."
  echo
  echo "Options:"
  echo "  --help                 Display this help message"
}

# Check for help option
if [ "$1" == "--help" ]; then
  usage
  exit 0
fi

# Get the current ArgoCD context
argocd_dns=$(argocd context | awk '/\*/ {print $2}')

# Read JSON input from stdin
input=$(cat)

# Iterate over each application and run the diff command
echo "$input" | jq -c '.[]' | while read -r app; do
  app_name=$(echo "$app" | jq -r '.application')
  echo "Running diff for application: $app_name" >&2
  
  # Construct the application URL
  app_url="https://${argocd_dns}/applications/${app_name}"
  echo "Application URL: $app_url" >&2
  
  # Get application details to extract source information
  app_details=$(argocd app get "$app_name" -o json)
  
  # Check if the application has multiple sources
  if echo "$app_details" | jq -e '.spec.sources' > /dev/null; then
    # Iterate over each source
    echo "$app_details" | jq -c '.spec.sources[]' | while read -r source; do
      repo_url=$(echo "$source" | jq -r '.repoURL // "N/A"')
      target_revision=$(echo "$source" | jq -r '.targetRevision // "N/A"')
      path=$(echo "$source" | jq -r '.path // "N/A"')
      chart=$(echo "$source" | jq -r '.chart // empty')
      chart_version=$(echo "$source" | jq -r '.targetRevision // "N/A"')
      
      if [ -n "$chart" ]; then
        # Print Helm source details with chart version
        echo "Helm Source: Chart=$chart, Version=$chart_version, RepoURL=$repo_url" >&2
      else
        # Remove .git suffix if present
        repo_url_no_git="${repo_url%.git}"
        # Construct the full URL, omitting the path if it's "N/A"
        if [ "$path" == "N/A" ]; then
          full_url="${repo_url_no_git}/tree/${target_revision}"
        else
          full_url="${repo_url_no_git}/tree/${target_revision}/${path}"
        fi
        echo "GitHub Source: $full_url" >&2
      fi
    done
  else
    # Handle single source case
    repo_url=$(echo "$app_details" | jq -r '.spec.source.repoURL // "N/A"')
    target_revision=$(echo "$app_details" | jq -r '.spec.source.targetRevision // "N/A"')
    path=$(echo "$app_details" | jq -r '.spec.source.path // "N/A"')
    chart=$(echo "$app_details" | jq -r '.spec.source.chart // empty')
    chart_version=$(echo "$app_details" | jq -r '.spec.source.targetRevision // "N/A"')
    
    if [ -n "$chart" ]; then
      # Print Helm source details with chart version
      echo "Helm Source: Chart=$chart, Version=$chart_version, RepoURL=$repo_url" >&2
    else
      # Remove .git suffix if present
      repo_url_no_git="${repo_url%.git}"
      # Construct the full URL, omitting the path if it's "N/A"
      if [ "$path" == "N/A" ]; then
        full_url="${repo_url_no_git}/tree/${target_revision}"
      else
        full_url="${repo_url_no_git}/tree/${target_revision}/${path}"
      fi
      echo "GitHub Source: $full_url" >&2
    fi
  fi
  
  # Run the diff command
  argocd app diff "$app_name"
done
