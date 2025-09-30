# post_google_chat_message.py
"""
Posts a message to Google Chat, replying in-thread when --thread is provided.

Usage:
  python post_google_chat_message.py --space spaces/AAA... --text "hi" [--thread spaces/AAA.../threads/TTT...]

Auth:
  Uses Google Application Default Credentials with scope:
    https://www.googleapis.com/auth/chat.bot

Works with:
  - Workload Identity on GKE (recommended), or
  - A JSON key via GOOGLE_APPLICATION_CREDENTIALS env.
"""
import argparse, os, sys, json, requests
from google.auth import default as google_auth_default
from google.auth.transport.requests import Request as GARequest

def get_access_token() -> str:
    creds, _ = google_auth_default(scopes=["https://www.googleapis.com/auth/chat.bot"])
    if not creds.valid:
        creds.refresh(GARequest())
    return creds.token

def post_message(space: str, text: str, thread: str | None):
    if not space:
        print("post_message.py: missing --space", file=sys.stderr)
        return 2

    token = get_access_token()
    url = f"https://chat.googleapis.com/v1/{space}/messages"
    params = {}
    if thread:
        # Force reply to the given thread; if thread is wrong, the API will fail
        params["messageReplyOption"] = "REPLY_MESSAGE_OR_FAIL"

    body = {"text": text or ""}
    if thread:
        body["thread"] = {"name": thread}

    resp = requests.post(
        url, params=params, json=body,
        headers={"Authorization": f"Bearer {token}"},
        timeout=15
    )
    ok = 200 <= resp.status_code < 300
    print(f"Chat API status={resp.status_code} ok={ok}", file=sys.stderr)
    if not ok:
        print(f"Resp: {resp.text}", file=sys.stderr)
        return 1
    # Optional pretty print
    try:
        print(json.dumps(resp.json(), indent=2))
    except Exception:
        print(resp.text)
    return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", required=True, help="spaces/<id>")
    ap.add_argument("--text", required=True, help="message text")
    ap.add_argument("--thread", help="spaces/<id>/threads/<threadId>")
    args = ap.parse_args()
    sys.exit(post_message(args.space, args.text, args.thread))

if __name__ == "__main__":
    main()
