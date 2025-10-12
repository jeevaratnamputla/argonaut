import os
import re
import html
import json
import subprocess

def execute_run_command(command, logger):
    # Check if execution is enabled via environment variable
    execute_enabled = os.environ.get("EXECUTE_RUN_COMMAND_ENABLED", "false").lower() == "true"
    if not execute_enabled:
        logger.warning("Command execution is disabled by environment variable.")
        return {
            "stdout": "",
            "stderr": "Command execution is disabled.",
            "returncode": 1
        }

    command = html.unescape(command) 
    command = re.sub(r'<(https?://[^ >]+)>', r'\1', command)
    logger.info("Running command: %s", command)
    REPO_BASE = os.path.dirname(__file__)  # points to /tmp/slack-chatgpt-argocd
    script_path = os.path.join(REPO_BASE, 'run-command.py')
    args = ['python3', script_path, command]
    result = subprocess.run(args, capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
           "stdout": result.stdout,
           "stderr": result.stderr or "Not valid JSON output",
           "returncode": result.returncode
        }
