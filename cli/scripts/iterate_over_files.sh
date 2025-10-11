# Define the repository and commit range
repo="OpsMx/cdaas"
base_commit="bdde6a665b2175c11247e2694b5e6f718bf9031a"
head_commit="1c9d5e00b444212cabc98784d27d49ee9c7578cc"

# List of files to get diffs for
files=("apps/argocd/dora-metrics/application.yaml" "argocd/values-override.yaml" "kube-prometheus-stack/values-override.yaml")

# Iterate over each file and get the diff
for file in "${files[@]}"; do
  echo "Changes for $file:"
  gh api repos/$repo/compare/$base_commit...$head_commit --jq ".files[] | select(.filename == \"$file\") | .patch"
  echo
done
