# argocd_auth.py
import subprocess
import logging
import os
import sys


def authenticate_with_argocd():
    logging.basicConfig(level=logging.INFO)

    argocdUrl = os.environ.get("argocdUrl")
    argocd_username = os.environ.get("argocdUsername", "admin")  # default to "admin"
    argocd_password = os.environ.get("argocdPassword")

    def login_with_core():
        """Fallback: use in-cluster/core login."""
        try:
            logging.info("argocdUrl or argocdPassword missing, trying core login: 'argocd login argocd-server --core'...")
            result = subprocess.run(
                ["argocd", "login", "argocd-server", "--core"],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                logging.info("Logged into Argo CD successfully using core mode")
                return True
            else:
                logging.error(f"Argo CD core login failed: {result.stderr.strip()}")
                return False
        except subprocess.TimeoutExpired:
            logging.error("Timeout exceeded while logging into Argo CD using core mode")
            return False
        except Exception as e:
            logging.error(f"Unexpected error during Argo CD core login: {e}")
            return False

    # If URL or password is missing, skip normal login and try core login.
    if not argocdUrl or not argocd_password:
        success = login_with_core()
        if not success:
            logging.error(
                "Unable to authenticate with Argo CD: "
                "missing argocdUrl/argocdPassword and core login failed."
            )
            sys.exit(1)
        return

    # Normal login using URL/username/password
    try:
        logging.info(f"Attempting to log into Argo CD at {argocdUrl} as {argocd_username}...")
        result = subprocess.run(
            [
                "argocd",
                "login",
                argocdUrl,
                "--username",
                argocd_username,
                "--password",
                argocd_password,
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            logging.info("Logged into Argo CD successfully with username/password")
        else:
            logging.error(f"Argo CD login failed: {result.stderr.strip()}")
            sys.exit(result.returncode)
    except subprocess.TimeoutExpired:
        logging.error("Timeout exceeded while logging into Argo CD")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Unexpected error during Argo CD login: {e}")
        sys.exit(1)


if __name__ == "__main__":
    authenticate_with_argocd()
