import subprocess
import os
import sys

def configure_git_user():
    user_name = os.getenv("GIT_USER_NAME", "Your Name")
    user_email = os.getenv("GIT_USER_EMAIL", "you@example.com")

    try:
        subprocess.run(["git", "config", "--global", "user.name", user_name], check=True)
        subprocess.run(["git", "config", "--global", "user.email", user_email], check=True)
        #print(f"✅ Git user configured: {user_name} <{user_email}>")
        print("✅ Git user configured")
    except subprocess.CalledProcessError as e:
        print("❌ Failed to configure Git user:", e)
        sys.exit(1)

def store_git_credentials():
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("❌ GITHUB_TOKEN environment variable not set.")
        sys.exit(1)

    # You can also take GitHub username from an env variable if needed
    username = os.getenv("GIT_USER_NAME", "git")

    try:
        # Enable the credential store
        subprocess.run(["git", "config", "--global", "credential.helper", "store"], check=True)

        # Write credentials directly to the store file
        credentials_path = os.path.expanduser("~/.git-credentials")
        with open(credentials_path, "w") as f:
            f.write(f"https://{username}:{token}@github.com\n")

       # print("✅ Git credentials stored in ~/.git-credentials")
    except Exception as e:
        print("❌ Failed to store Git credentials:", e)
        sys.exit(1)

def setup_git():
    configure_git_user()
    store_git_credentials()
