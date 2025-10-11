import os
import re
import html
import json
import subprocess
def execute_run_command(command, logger):
    command = html.unescape(command) 
    command = re.sub(r'<(https?://[^ >]+)>', r'\1', command)
    logger.info("Running command: %s", command)
    #args = ['python3', 'run-command.py'] + shlex.split(command)
    REPO_BASE = os.path.dirname(__file__)  # points to /tmp/slack-chatgpt-argocd
    script_path = os.path.join(REPO_BASE, 'run-command.py')
    args = ['python3', script_path, command]
    #args = ['python3', 'run-command.py', command]
    result = subprocess.run(args, capture_output=True, text=True)
    #result = subprocess.run(['python', 'run-command.py', command], capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
           "stdout": result.stdout,
           "stderr": result.stderr or "Not valid JSON output",
           "returncode": result.returncode
              }
 