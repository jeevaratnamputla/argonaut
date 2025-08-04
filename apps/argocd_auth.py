# argocd_auth.py
import subprocess
import logging
import os
import sys

def authenticate_with_argocd():
    argocdUrl = os.environ.get("argocdUrl")
    argocd_username = os.environ.get("argocdUsername", "admin")  # default to "admin"
    argocd_password = os.environ.get("argocdPassword")

    if not argocdUrl or not argocd_password:
        logging.error("Missing argocdUrl or ARGOCD_PASSWORD in environment variables")
        sys.exit(1)

    try:
        logging.basicConfig(level=logging.INFO)
        logging.info("Attempting to log into Argo CD...")
        result = subprocess.run(
            ['argocd', 'login', argocdUrl, '--username', argocd_username, '--password', argocd_password],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            logging.info("Logged into Argo CD successfully")
        else:
            logging.error(f"Argo CD login failed: {result.stderr}")
    except subprocess.TimeoutExpired:
        logging.error("Timeout exceeded while logging into Argo CD")

if __name__ == "__main__":
    authenticate_with_argocd()
