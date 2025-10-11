#!/bin/bash

# Usage function to display help
usage() {
  echo "Usage: $0 <repo_url> <revision1> <revision2>"
  echo "Get the changes for each file between two revisions in a GitHub repository, including commit details."
  echo
  echo "Options:"
  echo "  --help                 Display this help message"
  echo
  echo "Arguments:"
  echo "  <repo_url>             The full GitHub repository URL (e.g., https://github.com/OpsMx/cdaas)"
  echo "  <revision1>            The base commit SHA"
  echo "  <revision2>            The head commit SHA"
}

# Check for help option
if [ "$1" == "--help" ]; then
  usage
  exit 0
fi

# Check for the correct number of arguments
if [ "$#" -ne 3 ]; then
  echo "Error: Invalid number of arguments"
  usage
  exit 1
fi

# Assign arguments to variables
full_repo_url="$1"
base_commit="$2"
head_commit="$3"

# Extract owner/repo from the full URL
# Remove protocol and domain, then remove .git suffix if present
repo_owner_name="${full_repo_url#https://github.com/}"
repo_owner_name="${repo_owner_name%.git}" # This will be like "OpsMx/cdaas"

# Cleaned base URL for clickable links (without .git)
cleaned_base_url="${full_repo_url%.git}"

# List of files to get diffs for
files=("apps/argocd/dora-metrics/application.yaml" "argocd/values-override.yaml" "kube-prometheus-stack/values-override.yaml")

# Iterate over each file and get the diff
for file in "${files[@]}"; do
  echo "Changes for $file:"
  # Use repo_owner_name for gh api calls
  gh api repos/$repo_owner_name/compare/$base_commit...$head_commit --jq ".files[] | select(.filename == \"$file\") | .patch"
  
  # Construct the GitHub URL for the file diff using the cleaned_base_url
  file_url="${cleaned_base_url}/compare/${base_commit}...${head_commit}#diff-$(echo -n "$file" | sha256sum | cut -d' ' -f1)"
  echo "GitHub Diff URL: $file_url"
  echo
done

# Get commit details
echo "Commit Details:"
for commit in "$base_commit" "$head_commit"; do
  echo "Commit: $commit"
  # Use repo_owner_name for gh api calls
  gh api repos/$repo_owner_name/commits/$commit --jq '{author: .commit.author.name, message: .commit.message}'
  echo
done
