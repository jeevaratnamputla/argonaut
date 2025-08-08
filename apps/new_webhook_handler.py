import requests
import subprocess
import sys
import logging
import json
import os
import time
import threading
from threading import Thread
from argocd_auth import authenticate_with_argocd # to keep the argocd token fresh
import git_config
from slack import post_message_to_slack, get_bot_user_id, verify_slack_request, get_thread_ts_from_reaction
#from elastic import ensure_index_exists, get_es_client, update_elasticsearch, set_summary_index_es, get_thread_messages, update_reaction
from generic_storage import ensure_index_exists, update_message, set_summary_index, get_thread_messages, update_reaction
from chatgpt import get_chatgpt_response
import html
import re
from count_tokens import count_tokens
from argocd_diagnose import run_diagnosis
from summarize_text import summarize_text
from selfdiagnose import diagnose_system
from create_system_text import create_system_text
#from argocd_flow import process_prompt

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
 
AUTO_RUN = os.getenv("AUTO_RUN", "false").lower() == "true"


MAX_USER_INPUT_TOKENS = int(os.environ.get("MAX_USER_INPUT_TOKENS", 6000))
CONVERSATION_URL = os.getenv("CONVERSATION_URL")
model=os.getenv("model", "gpt-4.1")
max_response_tokens = os.getenv("max_response_tokens", 200)
max_response_tokens = int(max_response_tokens)  # Ensure it's an integer
temperature = os.getenv("temperature", 0.0)
temperature = float(temperature)  # Ensure it's a float
help_message = """This assistant, Spinnaut produces commands, each with a comment. Does not produce a lot of text.
USE CAUTION! and your own judgement to run these commands while using AUTORUN=false
Context is preserved in threads NOT in channel.
Each new thread has a new context and will not be related to other threads.
use RUN to run a command example: RUN kubectl get pods, using just RUN will run the last command suggested by the bot.
only kubectl commands are allowed
use SUMMARIZE to get a summary of the conversation so far, example: SUMMARIZE
"""

MOSIMPORTANT = """
            Always make the response be brief.
            You either recommend the command in the correct format or provide a brief answer to the user or ask user for more information.
            # This is a single line comment
            ``` This is a command ```
            example:
            # To get the application status json    
            ``` kubectl get sts -o json | jq -r '.status' | jq -c ```
    """
#summary_report = diagnose_system()
system_text = create_system_text()
#system_text += summary_report

es_index = os.getenv("es_index")
ES_EXT_URL = os.getenv("ES_EXT_URL")
# Elasticsearch endpoint with authentication
#s = get_es_client()
#ensure_index_exists(logger)

def summarize_conversation(es, thread_ts, max_response_tokens, temperature, logger):
    role = "user"
    content = (
        "Summarize this conversation and preserve critical information"
    )

    update_message( thread_ts, role, content, logger=logger)

    messages = get_thread_messages( thread_ts, logger=logger)
    logger.debug("Summarizing: %s", json.dumps(messages))
    logger.info("Summarizing...........................................................................")

    response = get_chatgpt_response( thread_ts, max_response_tokens, temperature, logger=logger)
    role = "assistant"
    content = response
    update_message( thread_ts, role, content, logger=logger)
    set_summary_index(es,thread_ts,logger=logger)
    return response


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
        case _:
            logger.warning(f"Unknown IO_type '{io_type}' — cannot send response.")

def handle_event_text(payload, logger):
    event_text = payload.get("text")    
    thread_ts = payload.get("thread_ts")
    if event_text is None:
        logger.warning("event_text is None — take a look at payload: %s", payload)
        return {"reponse": "No event_text in payload"} 
    if event_text == "HELP":
            response = help_message
            response = "NAUT " + response
            send_response(payload, thread_ts, response, logger)
            logger.info("Sent the HELP text ...")
            return {"reponse": "Sent the HELP text ..."}
    
    if event_text.startswith("NAUT"):
            logger.info("Message not meant for Argonaut")
            return {"reponse": "Message not meant for Argonaut"} 

    isFirstMessage = payload.get("isFirstMessage")
    if isFirstMessage == "true":
        logger.warning("isFirstMessage is true")
        #response = "NAUT Follow the conversation here %s/%s/_doc/%s?pretty=true" % (ES_EXT_URL, es_index, thread_ts)
        response = "NAUT Follow the conversation here https://CONVERSATION_URL/threads/%s" % (thread_ts)
        send_response(payload, thread_ts, response, logger)
        role = "system"
        content = system_text
        logger.info("Updating ES: thread_ts=%s, role=%s, content=%s", thread_ts, role, content)
        update_message( thread_ts, role, content, logger=logger)
        role = "user"
        content = event_text + MOSIMPORTANT
        update_message( thread_ts, role, content, logger=logger)
        response = get_chatgpt_response( thread_ts, max_response_tokens, temperature, logger=logger)
        role = "assistant"
        content = response
        update_message( thread_ts, role, content, logger=logger)
        if AUTO_RUN:
            newpayload = payload
            newpayload["text"] = "RUN"
            handle_event_text(newpayload, logger)
        else:
            response = "NAUT " + response
            send_response(payload, thread_ts, response, logger)
        payload["isFirstMessage"] = "false"
        return
    #logger.info("thread_ts in handle_event_text is: %s", thread_ts) # this is the thread_ts in handle_event_text 
    match event_text:
        #This should be moved to n8n
        case _ if event_text.startswith("TOOL"):
            role = "user"
            command_output_handler_text = "Be brief. Less than 25 words. Analyze this command output, if there are errors, try to fix them. Use the command with --help to get more info to fix the errors, example: ```argocd app manifests --help```. Recommend a new command if you can fix the errors, otherwise ask user for help. Summarize with a focus on which Problem Resources are not in Synced or Healthy state. We will later investigate those manifests of Problem Resources."
            content = command_output_handler_text + "\n" + event_text
            update_message( thread_ts, role, content, logger=logger)
            response = get_chatgpt_response( thread_ts, max_response_tokens, temperature, logger=logger)
            role = "assistant"
            content = response
            update_message( thread_ts, role, content, logger=logger)
            response = "NAUT " + response
            send_response(payload, thread_ts, response, logger)
            logger.info("Analyzed output from the command-runner")
            return {"response": "Analyzed output from the command-runner"} 
        
        case "RUN":
            logger.info("Running the requested command...")
            messages = get_thread_messages( thread_ts, logger=logger)
            last_content = messages[-1]["content"]
# Extract the command which is line after three backticks from slack
            lines = last_content.splitlines()
            command = None
            for idx, line in enumerate(lines):
                stripped = line.strip()

                if stripped.startswith("```"):
                    if stripped.startswith("```yaml"):
                        continue
                    # Case 1: backticks and command on the same line
                    if stripped.startswith("```bash"):
                        if len(stripped) > 7:
                            command = stripped[7:].strip("` ").strip()
                            break
                    if len(stripped) > 3:
                        command = stripped[3:].strip("` ").strip()
                        break

                    # Case 2: command is on the next line
                    if idx + 1 < len(lines):
                        command_candidate = lines[idx + 1].strip()
                        # Optional: confirm next-next line is closing ```
                        if idx + 2 < len(lines) and lines[idx + 2].strip().startswith("```"):
                            command = command_candidate
                            break
            if not command:
                logger.info("No command found after code block — using fallback response")
                role = "user"
                anything_more_text = "Are you sure you cannot think of any further ways to help the user, the info you are asking for, can you get it yourself with the available tools. If you think user has all the information, do not recommend any commands."
                content = anything_more_text 
                update_message( thread_ts, role, content, logger=logger)
                response = get_chatgpt_response( thread_ts, max_response_tokens, temperature, logger=logger)
                role = "assistant"
                
                content = response
                update_message( thread_ts, role, content, logger=logger)
                response = "NAUT " + response
                send_response(payload, thread_ts, response, logger)

                response = "AI resolved the issue or further user input needed, type just  HELP, all caps, for more opitons"
                response = "NAUT " + response
                send_response(payload, thread_ts, response, logger) 
                logger.info("No command found after code block — using fallback response")
                return {"reponse": "No command found after code block — using fallback response"} 
            else:
                output = execute_run_command(command, logger) 
                logger.info("Command: %s | Command Output: %s | Command Error: %s | Return Code: %s ", command, output["stdout"], output["stderr"], output["returncode"])
                
                response = f"TOOL Command: {command}\nCommand Output:\n{output['stdout']}\nCommand Error:\n{output['stderr']}\nReturn Code:\n{output['returncode']}"
                send_response(payload, thread_ts, response, logger)

        case "SUMMARIZE":
                response = summarize_conversation(
                    es=es,
                    thread_ts=thread_ts,
                    max_response_tokens=max_response_tokens,
                    temperature=temperature,
                    logger=logger
                )
                response = "NAUT " + response
                send_response(payload, thread_ts, response, logger)
                return response
        case _ if event_text.startswith("GIT-FIX"):
            logger.info("Handling GIT-FIX logic...")
            if event_text == "GIT-FIX":
                response = "Please provide more info what file you want to fix"
                response = "NAUT " + response
                send_response(payload, thread_ts, response, logger)
                return
            event_text = event_text.replace("GIT-FIX", "").strip()

            event_text = event_text + ", recommend one command at a time for the following tasks first clone the repo, checkout the target branch, from this branch checkout a new branch whose name reflects the fix, update the file(s). Do not recommend commands starting with bash, no newline characters in the command, follow the FORMAT in system message exactly. Make no assumptions about the file names. In the end recommend git --no-pager diff --minimal command so that user can review changes, in the response include the output of this command git --no-pager diff --minimal"
            role = "user"
            content = event_text 
            update_message( thread_ts, role, content, logger=logger)            
            response = get_chatgpt_response( thread_ts, max_response_tokens, temperature, logger=logger)
            role = "assistant"
            content = response
            update_message( thread_ts, role, content, logger=logger)           
            if AUTO_RUN:
                newpayload = payload
                newpayload["text"] = "RUN"
                handle_event_text(newpayload, logger)
            else:
                #response = "``` " + response + " ```"
                response = "NAUT type RUN all caps to run this command" + response
                send_response(payload, thread_ts, response, logger) 
            return response
            # your GIT-FIX logic here
        case "GIT-PR":
            logger.info("Running the requested command...")
            
            event_text = "do not clone, do not delete the git repo clone folder. recommend one command at a time for the following tasks , cd to the git repo clone folder and confirm the new branch name, git add , git commit, git push to the new branch in remote repository, create a PR using gh commands from the current branch to the target branch. Return to the user the newly created PR's URL. Do not recommend commands starting with bash, no newline characters in the command, follow the FORMAT in system message exactly."
            role = "user"
            content = event_text 
            update_message( thread_ts, role, content, logger=logger)            
            response = get_chatgpt_response( thread_ts, max_response_tokens, temperature, logger=logger)
            role = "assistant"
            content = response
            update_message( thread_ts, role, content, logger=logger)
            #post_message_to_slack(channel_id, response, thread_ts)
            if AUTO_RUN:
                newpayload = payload
                newpayload["text"] = "RUN"
                handle_event_text(newpayload, logger)
            else:
                #response = "``` " + response + " ```"
                response = "NAUT type RUN all caps to run this command" + response
                send_response(payload, thread_ts, response, logger) 
            return response
        case "GIT-MERGE":
            logger.info("Merging to Target branch...")
            event_text = "Merge the newly created PR using gh command, and sync the application"
            role = "user"
            content = event_text 
            update_message( thread_ts, role, content, logger=logger)            
            response = get_chatgpt_response( thread_ts, max_response_tokens, temperature, logger=logger)
            role = "assistant"
            content = response
            update_message( thread_ts, role, content, logger=logger)
            #post_message_to_slack(channel_id, response, thread_ts)
            if AUTO_RUN:
                    newpayload = payload
                    newpayload["text"] = "RUN"
                    handle_event_text(newpayload, logger)
            else:
                #response = "``` " + response + " ```"
                #response = "NAUT type RUN all caps to run this command" + response
                response = "NAUT " + " to run the command if supplied type RUN" + response
                send_response(payload, thread_ts, response, logger)
            return response
            # your run logic here
        case _ if event_text.startswith("RUN"):
            command = event_text[4:] # Extract the command after "RUN "
            output = execute_run_command(command, logger) 
            logger.info("Command: %s | Command output: %s | Command Error: %s | Return Code: %s ", command, output["stdout"], output["stderr"], output["returncode"])
            response = f"Command: {command}\nCommand Output:\n{output['stdout']}\nCommand Error:\n{output['stderr']}\nReturn Code:\n{output['returncode']}"
            send_response(payload, thread_ts, response, logger)
            logger.info("Running the suggested commands...")
            return response

        case _:
            role = "user"
            content = event_text
            update_message( thread_ts, role, content, logger=logger)            
            response = get_chatgpt_response( thread_ts, max_response_tokens, temperature, logger=logger)
            role = "assistant"
            content = response
            update_message( thread_ts, role, content, logger=logger)
    
            if AUTO_RUN:
                logger.info("AUTO_RUN set to True so running using command-runner %s", response)
                newpayload = payload
                newpayload["text"] = "RUN"
                handle_event_text(newpayload, logger)
            else:
                logger.info("AUTO_RUN set to to False so asking user to issue RUN Keyword %s", response)
                #response = "``` " + response + " ```"
                response = "NAUT type RUN all caps to run this command, if supplied  " + response
                send_response(payload, thread_ts, response, logger)

def route_source(request, logger):
    """
    Determines the source of the request (Slack or Email) based on payload structure.
    Calls the appropriate handler function.
    """
    payload = request.get_json()
    # pre-process event_text
    return handle_event_text(payload, logger)

def webhook_handler(request, logger):

    logger.info("Webhook endpoint hit inside webhook_handler")
    ensure_index_exists(logger)
    payload = request.get_json()
    logger.debug("webhook_handler, data: %s", payload)
    logger.info("inside webhook_handler")
    if not payload:
        return {"error": "Invalid payload"}, 400
    try:
        result = route_source(request, logger)
        return {"status": "ok", "result": result}, 200
    except Exception as e:
        logger.exception("Error handling webhook")
        return {"error": str(e)}, 500


