#!/bin/bash

# Usage function to display help
usage() {
  echo "Usage: $0 [--help]"
  echo "Print the last two versions from the status history for each application, the length of the history, and the changes in revisions."
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

# Iterate over each application and process the status history
echo "$input" | jq -c '.[]' | while read -r app; do
  app_name=$(echo "$app" | jq -r '.application')
  
  # Get application details to extract status history
  app_details=$(argocd app get "$app_name" -o json)
  
  # Check if status history exists
  if echo "$app_details" | jq -e '.status.history' > /dev/null; then
    # Get the length of the history
    history_length=$(echo "$app_details" | jq '.status.history | length')
    echo "History Length for $app_name: $history_length"
    
    # Get the last two history items if they exist
    last_two=$(echo "$app_details" | jq -c '.status.history | sort_by(.deployedAt) | reverse | .[:2]')
    
    # Extract revisions from the last two history items
    rev1=$(echo "$last_two" | jq -r '.[0] | (.revisions // [.revision]) | join(",")')
    rev2=$(echo "$last_two" | jq -r '.[1] | (.revisions // [.revision]) | join(",")')
    
    echo "Last Revision: $rev1"
    echo "Previous Revision: $rev2"
    
    # Compare revisions
    if [ "$rev1" != "$rev2" ]; then
      echo "Revisions changed between the last two versions for $app_name."
      
      # Iterate over sources to find GitHub repo
      echo "$app_details" | jq -c '.spec.sources[]' | while read -r source; do
        repo_url=$(echo "$source" | jq -r '.repoURL // empty')
        if [[ "$repo_url" == *"github.com"* ]]; then
          # Remove .git suffix if present
          repo_url_no_git="${repo_url%.git}"
          
          # Extract the specific revisions for this source
          source_rev1=$(echo "$rev1" | awk -F, '{print $2}')
          source_rev2=$(echo "$rev2" | awk -F, '{print $2}')
          
          # Construct the GitHub diff URL
          if [ -n "$source_rev1" ] && [ -n "$source_rev2" ]; then
            diff_url="${repo_url_no_git}/compare/${source_rev2}...${source_rev1}"
            ./scripts/iterate_over_files.sh $repo_url_no_git ${source_rev2} ${source_rev1}
            echo "GitHub Diff URL: $diff_url"
          else
            echo "Revisions not found for GitHub repo: $repo_url"
          fi
        fi
      done
    else
      echo "No revision changes between the last two versions for $app_name."
    fi
  else
    echo "No status history available for application: $app_name"
  fi
done
