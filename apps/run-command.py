# run-command.py
import subprocess
import sys
import os
import json
import html
import shlex
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("/tmp/run-command.log"),
        logging.StreamHandler(sys.stderr)  # log to stderr to avoid messing with stdout
    ]
)
logger = logging.getLogger(__name__)


#os.environ.clear()


def run_command(command):
    # sanitized_command = command.split(';')[0].strip()
    #sanitized_command = f"{command} 2>&1"
    logger.debug(f"raw command is: {command}")
    #command = html.unescape(command)
    command = command.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')

    logger.debug(f"after processing command is: {command}")
    #sanitized_command = f"/bin/bash -c $'set -x; {command}'"
    sanitized_command = f"/bin/bash -c $'set -x; {command}'"
    logger.debug(f"sanitized_command is: {sanitized_command}")
    #print("sanitized_command")
    #print(sanitized_command)
    os.environ["GOMAXPROCS"] = str(os.cpu_count()) 
# Define allowed command prefixes
    # allowed_commands = ['kubectl', 'argocd', 'gh', 'git', 'cd','sed']

    # # Check if the sanitized command starts with one of the allowed commands
    # if not any(sanitized_command.startswith(cmd) for cmd in allowed_commands):
    #     print("Error: Only 'kubectl', 'argocd', 'gh', 'cd','sed' and 'git' commands are allowed!")
    #     return

    try:
        #result = subprocess.run(sanitized_command, shell=True, check=False, text=True, capture_output=True)
        result = subprocess.run(
        ["bash", "-c", sanitized_command],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
        output = {
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "returncode": result.returncode
         }
    except subprocess.CalledProcessError as e:
        output = {
        "stdout": "",
        "stderr": e.stderr.strip(),
        "returncode": e.returncode
         }
    print(json.dumps(output))
    logger.debug(f"output is: {output}")
    sys.exit(output["returncode"])

if __name__ == "__main__":
    if len(sys.argv) > 1:
        #command = ' '.join(sys.argv[1:])
        #command = ' '.join(shlex.quote(arg) for arg in sys.argv[1:])
        command = ' '.join(sys.argv[1:])
        #print("command")
        #print(command)
        run_command(command)
    else:
        print("Please provide a command to run.")
