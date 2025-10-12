import requests
import subprocess
import sys
import os
from threading import Thread
from argocd_auth import authenticate_with_argocd # to keep the argocd token fresh
from slack import post_message_to_slack, get_bot_user_id, verify_slack_request, get_thread_ts_from_reaction
#from elastic import ensure_index_exists, get_es_client, update_elasticsearch, set_summary_index_es, get_thread_messages, update_reaction
from generic_storage import ensure_index_exists, update_message, set_summary_index, get_thread_messages, update_reaction
#from chatgpt import get_chatgpt_response
from call_llm import get_llm_response
from count_tokens import count_tokens
from create_system_text import create_system_text
def send_email_to_user(thread_ts, response, logger):
    """
    Send payload to n8n webhook /reply-mail with body and thread_ts.

    Parameters:
        payload (dict): Must contain 'thread_ts' and 'response'.
        logger (optional): Logger instance for logging.
    
    Returns:
        dict: Response from n8n webhook or error details.
    """
    url = "http://n8n:5678/webhook/reply-mail"

    logger.info("response as found in send_email_to_user: %s", response)

    data = {
        "thread_ts": thread_ts,
        "response": response
    }

    try:
        n8n_webhook_response = requests.post(url, json=data)
        n8n_webhook_response.raise_for_status()

        if logger:
            logger.info("Sent to n8n send-mail: %s", data)

        return

    except requests.exceptions.RequestException as e:
        if logger:
            logger.exception("Failed to send to n8n webhook: %s", e)

        return {
            "status": "error",
            "error": str(e)
        }
    
def send_response(payload, thread_ts, response, logger):
    io_type = payload.get("IO_type")

    match io_type:
        case "slack":
            channel_id = payload.get("channel")
            if not channel_id:
                logger.warning("Slack IO_type but no channel_id in payload")
                return
            post_message_to_slack(channel_id, response, thread_ts)
        case "email":
            send_email_to_user(thread_ts, response, logger)
        case "google_chat":
            # ---------------- Config ----------------
            POSTER_SCRIPT = os.getenv("POSTER_SCRIPT", "/app/post_google_chat_message.py")
            poster = os.getenv("POSTER_SCRIPT", POSTER_SCRIPT)
            channel_id = payload.get("channel")
            space_name = payload.get("channel")
            reply = response
            thread_name = f"{space_name}/threads/{thread_ts}"
            args = [sys.executable, poster, "--space", space_name or "", "--text", reply]
            if thread_name:
               args += ["--thread", thread_name]
               logger.warning("POSTER_SCRIPT=%r", poster)
               logger.warning("Spawning post_message.py with args: %r", args)

            try:
               subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
               log.error("Failed to spawn post_message.py: %s", e)
                #post_message_to_google_chat(channel_id, response, thread_ts, logger)            
        case _:
            logger.warning(f"Unknown IO_type '{io_type}' — cannot send response.")
