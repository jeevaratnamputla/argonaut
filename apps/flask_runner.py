import subprocess
import sys
import logging
import json
import os
import time
import threading
#from flask import Flask, request, jsonify  # Import again after installation
from flask import Flask, request, Response, jsonify, abort
from argocd_auth import authenticate_with_argocd # to keep the argocd token fresh
import git_config
from new_webhook_handler import webhook_handler
#from argocd_flow import process_prompt

app = Flask(__name__)

for handler in list(app.logger.handlers):
    app.logger.removeHandler(handler)
log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
# Map string to actual logging level
log_levels = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL
}
log_level = log_levels.get(log_level_str, logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
handler.setFormatter(formatter)
handler.setLevel(log_level)

app.logger.addHandler(handler)
app.logger.setLevel(log_level)
app.logger.propagate = False

def auth_loop():
    while True:
        logging.info("Running Argo CD login...")
        authenticate_with_argocd()
        time.sleep(86400)
        
if os.getenv("GIT_USER_EMAIL"):
    git_config.setup_git()

# Return 400 for any other route
@app.errorhandler(404)
def page_not_found(e):
    return jsonify({"error": "Bad Request"}), 400

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    app.logger.info("Received POST data in flask_runner: %s", data)
    app.logger.info("Received POST data in flask_runner:")
    return webhook_handler(request, app.logger)


@app.route('/run-command', methods=['POST'])
def run_command_endpoint():
    app.logger.info("🔔 /run-command endpoint hit")

    # Parse and validate JSON
    try:
        data = request.get_json(force=True)
        app.logger.info(f"📥 Parsed JSON body: {data}")
    except BadRequest:
        app.logger.error("❌ Invalid JSON received")
        return jsonify({"error": "Invalid JSON in request body"}), 400

    if not data or 'command' not in data:
        app.logger.warning("⚠️ Missing 'command' field in request")
        return jsonify({"error": "Missing 'command' in request body"}), 400

    command = data['command'].strip()
    if not command:
        app.logger.warning("⚠️ Command field is empty")
        return jsonify({"error": "Command field is empty"}), 400

    wrapper_cmd = ['python', 'run-command.py', command]
    app.logger.info(f"🛠️ Executing: {' '.join(wrapper_cmd)}")

    try:
        result = subprocess.run(
            wrapper_cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        app.logger.info(f"✅ Return code: {result.returncode}")
        app.logger.info(f"📤 STDOUT: {result.stdout.strip()}")
        app.logger.info(f"📥 STDERR: {result.stderr.strip()}")

        return jsonify({
            "input_command": command,
            "wrapped_command": f"python run-command.py \"{command}\"",
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip()
        }), 200

    except subprocess.TimeoutExpired:
        app.logger.error("⏱️ Command timed out")
        return jsonify({"error": "Command timed out"}), 504

    except Exception as e:
        app.logger.exception(f"🔥 Exception occurred: {str(e)}")
        return jsonify({"error": str(e)}), 500

FS_INDEX = os.getenv("FS_INDEX", "/argonaut/file_storage")


@app.route("/threads", methods=["GET"])
def list_threads():
    """Return a list of available thread_ts documents (filenames without extension)."""
    try:
        threads = [f.removesuffix(".json") for f in os.listdir(FS_INDEX) if f.endswith(".json")]
        return jsonify({"threads": threads})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/threads/<thread_ts>", methods=["GET"])
def get_thread(thread_ts):
    """Return the JSON content of a specific thread."""
    file_path = os.path.join(FS_INDEX, f"{thread_ts}.json")
    if not os.path.exists(file_path):
        abort(404, description=f"Thread {thread_ts} not found")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    os.makedirs(FS_INDEX, exist_ok=True)
    auth_thread = threading.Thread(target=auth_loop, daemon=True)
    auth_thread.start()
    app.run(host='0.0.0.0', port=5000, debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true')

