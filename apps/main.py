import os
import subprocess
import time
import signal
import git_config

REPO_URL = "https://github.com/gopaljayanthi/slack-chatgpt-argocd"
CLONE_DIR = "/tmp/slack-chatgpt-argocd"
FLASK_SCRIPT = os.path.join(CLONE_DIR, "flask_runner.py")


def clone_repo():
    if not os.path.exists(CLONE_DIR):
        git_config.setup_git()
        subprocess.run(["git", "clone", REPO_URL, CLONE_DIR], check=True)
    else:
        print(f"{CLONE_DIR} already exists.")


def start_flask_app():
    return subprocess.Popen(["python", FLASK_SCRIPT])


def check_for_updates():
    result = subprocess.run(
        ["git", "pull"],
        cwd=CLONE_DIR,
        capture_output=True,
        text=True
    )
    full_output = result.stdout + result.stderr
    print("Argonaut is Already up to date")
    return "Already up to date" not in full_output

def main():
    clone_repo()
    flask_process = start_flask_app()

    try:
        while True:
            time.sleep(60)
            if check_for_updates():
                print("Changes detected. Restarting flask app...")
                flask_process.send_signal(signal.SIGTERM)
                flask_process.wait()
                flask_process = start_flask_app()
            else:
                print("No changes detected.")
    except KeyboardInterrupt:
        print("Shutting down.")
        flask_process.send_signal(signal.SIGTERM)
        flask_process.wait()


if __name__ == "__main__":
    main()
