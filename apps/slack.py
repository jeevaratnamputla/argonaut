import os
import time  # ✅ This line is required
import hmac
import hashlib
import logging
import requests
from flask import jsonify


SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_POST_URL = os.getenv("slack_post_url")
SLACK_AUTH_URL = os.getenv("slack_auth_url")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

def _slack_headers():
    """Return common headers for Slack API requests."""
    return {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json"
    }

def post_message_to_slack(channel, text, thread_ts=None):
    """Posts a message to a Slack channel (optionally in a thread)."""
    payload = {
        "channel": channel,
        "text": text,
        "thread_ts": thread_ts
    }

    response = requests.post(SLACK_POST_URL, headers=_slack_headers(), json=payload)
    
    if response.status_code != 200 or not response.json().get("ok"):
        logging.error("Failed to send message to Slack: %s", response.text)
    else:
        logging.info("Message sent to Slack channel %s", channel)

def get_bot_user_id():
    """Fetches and returns the bot's user ID from Slack."""
    response = requests.post(SLACK_AUTH_URL, headers=_slack_headers())

    if response.status_code == 200:
        return response.json().get("user_id")
    else:
        logging.error("Error fetching bot user ID: %s", response.text)
        return None
def verify_slack_request(req, logger):
    """Verify that the Slack request is authentic and not a replay."""
    if req.content_type != 'application/json':
        logger.info("Received non-JSON content type")
        return False, jsonify({"error": "Invalid content type"}), 400

    slack_signature = req.headers.get('X-Slack-Signature')
    slack_retry_num = req.headers.get('X-Slack-Retry-Num')
    logger.info(f"Slack Retry Number: {slack_retry_num}")

    if slack_retry_num:
        logger.info("Ignoring retry request")
        return False, jsonify({"status": "Ignored retry"}), 200

    timestamp = req.headers.get("X-Slack-Request-Timestamp")
    if not timestamp or not slack_signature:
        logger.info("Missing Slack headers")
        return False, jsonify({"error": "Missing Slack headers"}), 400

    if abs(time.time() - float(timestamp)) > 60 * 5:
        logger.info("Timestamp too old")
        return False, jsonify({"error": "Request timestamp too old"}), 400

    sig_basestring = f"v0:{timestamp}:{req.get_data(as_text=True)}"
    my_signature = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()

    is_valid = hmac.compare_digest(my_signature, slack_signature)
    return (is_valid, None, None) if is_valid else (False, jsonify({"error": "Invalid signature"}), 400)


def get_thread_ts_from_reaction(event, logger=None):
    try:
        channel = event["item"]["channel"]
        message_ts = event["item"]["ts"]

        url = "https://slack.com/api/conversations.replies"
        headers = {
            "Authorization": f"Bearer {SLACK_BOT_TOKEN}"
        }
        params = {
            "channel": channel,
            "ts": message_ts
        }

        response = requests.get(url, headers=headers, params=params)
        data = response.json()

        if logger:
            logger.debug(f"Slack API response: {data}")

        if data.get("ok") and data.get("messages"):
            parent = data["messages"][0]
            return parent.get("thread_ts", parent["ts"])
        else:
            if logger:
                logger.error("Failed to get thread_ts: Slack API returned error or no messages")
            return None

    except Exception as e:
        if logger:
            logger.exception(f"Error in get_thread_ts_from_reaction: {e}")
        return None

