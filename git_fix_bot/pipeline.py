from langchain_core.runnables import RunnableLambda, RunnableMap
from extract_repo_info import extract_repo_metadata
from git_ops import prepare_repo, commit_push_create_pr
from fix_with_llm import fix_files_with_llm

# Step 1: Extract metadata from conversation
extract_step = RunnableLambda(lambda messages: extract_repo_metadata(messages))

# Step 2: Prepare values for fixing
prepare_step = RunnableMap({
    "repo_dir_branch": RunnableLambda(lambda d: prepare_repo(d["repo_url"], d["source_branch"])),
    "fix_instruction": RunnableLambda(lambda d: d["fix_instruction"]),
    "repo_path": RunnableLambda(lambda d: d.get("repo_path")),
})

# Step 3: Run the LLM fixer
fix_step = RunnableLambda(lambda d: {
    "changed_file": fix_files_with_llm(d["repo_dir_branch"][0], d["fix_instruction"], d["repo_path"]),
    "repo_dir": d["repo_dir_branch"][0],
    "branch": d["repo_dir_branch"][1],
    "instruction": d["fix_instruction"]
})

# Step 4: Commit and push PR
commit_step = RunnableLambda(lambda d: commit_push_create_pr(d["repo_dir"], d["branch"], d["instruction"]))

# Final pipeline using `|`
run_pipeline = extract_step | prepare_step | fix_step | commit_step
