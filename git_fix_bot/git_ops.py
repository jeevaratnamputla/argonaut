import os
import subprocess
import uuid

def run_command(command: str, cwd=None) -> str:
    result = subprocess.run(command, shell=True, text=True, capture_output=True, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"Error running `{command}`:\n{result.stderr}")
    return result.stdout.strip()

def prepare_repo(repo_url: str, source_branch: str) -> tuple[str, str]:
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    repo_dir = f"/tmp/{repo_name}"
    if os.path.exists(repo_dir):
        run_command(f"rm -rf {repo_dir}")

    run_command(f"git clone {repo_url} {repo_dir}")
    run_command(f"git checkout {source_branch}", cwd=repo_dir)

    new_branch = f"fix-{uuid.uuid4().hex[:8]}"
    run_command(f"git checkout -b {new_branch}", cwd=repo_dir)
    return repo_dir, new_branch

def commit_push_create_pr(repo_dir, branch, fix_msg):
    run_command("git add .", cwd=repo_dir)
    run_command(f'git commit -m "fix: {fix_msg}"', cwd=repo_dir)
    run_command(f"git push origin {branch}", cwd=repo_dir)
    pr = run_command(f'gh pr create --title "Fix: {fix_msg}" --body "Automated fix for: {fix_msg}" --head {branch} --base main', cwd=repo_dir)
    return pr