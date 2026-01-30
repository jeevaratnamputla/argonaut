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
from elastic import ensure_index_exists, get_es_client, update_elasticsearch, set_summary_index_es, get_thread_messages, update_reaction
from chatgpt import get_chatgpt_response
import html
import re
from count_tokens import count_tokens
from argocd_diagnose import run_diagnosis
from summarize_text import summarize_text
from selfdiagnose import diagnose_system
from create_system_text import create_system_text
#from argocd_flow import process_prompt

 
AUTO_RUN = os.getenv("AUTO_RUN", "false").lower() == "true"

BOT_USER_ID = get_bot_user_id()
if BOT_USER_ID:
    print("Bot user ID:", BOT_USER_ID)
else:
    print("Failed to fetch bot user ID")
    exit(1)

MAX_USER_INPUT_TOKENS = int(os.environ.get("MAX_USER_INPUT_TOKENS", 6000))

model=os.getenv("model", "gpt-4.1")
max_response_tokens = os.getenv("max_response_tokens", 200)
max_response_tokens = int(max_response_tokens)  # Ensure it's an integer
temperature = os.getenv("temperature", 0.0)
temperature = float(temperature)  # Ensure it's a float
help_message = """This assistant, Argonaut produces commands, each with a comment. Does not produce a lot of text.
USE CAUTION! and your own judgement to run these commands while using AUTORUN=false
Context is preserved in threads NOT in channel.
Each new thread has a new context and will not be related to other threads.
use RUN to run a command example: RUN kubectl get pods, using just RUN will run the last command suggested by the bot.
only kubectl, argocd and gh commands are allowed
use SUMMARIZE to get a summary of the conversation so far, example: SUMMARIZE
"""

summary_report = diagnose_system()
system_text = create_system_text()
system_text += summary_report

es_index = os.getenv("es_index")
ES_EXT_URL = os.getenv("ES_EXT_URL")
# Elasticsearch endpoint with authentication
es = get_es_client()
#ensure_index_exists(logger)

def summarize_conversation(es, thread_ts, max_response_tokens, temperature, logger):
    role = "user"
    content = (
        "Summarize this conversation and preserve critical information, the application url "
        "including cluster, namespace, repo, branch and path where relevant, "
        "for further use. Do not omit any information; rephrase and combine "
        "if needed, but preserve all facts. Show output starting with SUMMARY:"
        "give the user the argocd application url example https://argocd-server/applications/applicationNAme, not the kubernetes cluster url. give the user a github URL that includes the branch and path example https://github.com/opsmx-cnoe/naveen/tree/branch/path-from "
    )

    update_elasticsearch(es, thread_ts, role, content, logger=logger)

    messages = get_thread_messages(es, thread_ts, logger=logger)
    logger.debug("Summarizing: %s", json.dumps(messages))
    logger.info("Summarizing")

    response = get_chatgpt_response(es, thread_ts, max_response_tokens, temperature, logger=logger)
    role = "assistant"
    content = response
    update_elasticsearch(es, thread_ts, role, content, logger=logger)
    set_summary_index_es(es,thread_ts,logger=logger)
    return response

def execute_run_command(command, logger):
    command = html.unescape(command) 
    command = re.sub(r'<(https?://[^ >]+)>', r'\1', command)
    logger.info("Running command: %s", command)
    #args = ['python3', 'run-command.py'] + shlex.split(command)
    args = ['python3', 'run-command.py', command]
    result = subprocess.run(args, capture_output=True, text=True)
    #result = subprocess.run(['python', 'run-command.py', command], capture_output=True, text=True)
    try:
        output_data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"stdout": "", "stderr": "Failed to parse run-command.py output", "returncode": 1}

    return output_data
def route_source(request, logger):
    """
    Determines the source of the request (Slack or Email) based on payload structure.
    Calls the appropriate handler function.
    """
    payload = request.get_json()
    if isinstance(payload, dict) and "event" in payload and "ts" in payload.get("event", {}):
        # Slack payload
        logger.info("Received slack message in route_source: %s")
        return process_slack_event(request, payload, logger)
    else:
        # Email payload
        logger.info("Received email data in route_source: %s")
       # return process_email_request(request, payload, logger)
        return process_slack_event(request, payload, logger)

# Return 400 for any other route
def process_in_background( data, logger):

    event = data.get("event", {})
# Process "event_callback" type which indicates a reaction event
    if data.get("type") == "event_callback" and event['type'] == 'reaction_added':
        reaction = event['reaction']
        if reaction in ("+1", "-1"):
            thread_ts = get_thread_ts_from_reaction(event, logger=logger)
            if thread_ts:
                logger.info("Received reaction_added event for thread_ts: %s, reaction: %s", thread_ts, reaction)
                update_reaction(es, es_index, thread_ts, reaction, logger=logger)
        else:
            logger.info("Ignoring reaction: %s", reaction)
# Process "event_callback" type which indicates a message event
    if data.get("type") == "event_callback" and event['type'] == 'message':
        event_text = event["text"].strip()
        user_id = event["user"]
        channel_id = event["channel"]

                # Define the thread ID and if it is th first message
        if 'thread_ts' in event:
            thread_ts = event['thread_ts']
        else:
            thread_ts = event.get("ts")
            #process_prompt(event_text)
            role = "system"
            content = system_text 
            update_elasticsearch(es, thread_ts, role, content, logger=logger)
            response = "Follow the conversation here %s/%s/_doc/%s?pretty=true" % (ES_EXT_URL, es_index, thread_ts)
            post_message_to_slack(channel_id, response, thread_ts)
            result = run_diagnosis(event_text)
            if result is None:
                logger.info("No Argo CD app name could be resolved from the user input.")
            elif result == "BADAPP":
                logger.info("App name was found, but `argocd app get` failed.")
                role = "user"
                content = event_text + result
                update_elasticsearch(es, thread_ts, role, content, logger=logger)
                response = "App name was not found, because `argocd app get` failed."
                post_message_to_slack(channel_id, response, thread_ts)
                return
            else:
                logger.info("Diagnosis succeeded, posting result to Slack.")
                role = "user"
                content = event_text
                update_elasticsearch(es, thread_ts, role, content, logger=logger)
                role = "assistant"
                content = result
                update_elasticsearch(es, thread_ts, role, content, logger=logger)
                response = summarize_conversation(
                    es=es,
                    thread_ts=thread_ts,
                    max_response_tokens=max_response_tokens,
                    temperature=temperature,
                    logger=logger
                )
                post_message_to_slack(channel_id, response, thread_ts)
                ##response = result
                #post_message_to_slack(channel_id, response, thread_ts)  
                return

        if event_text == "HELP":
            response = help_message
            post_message_to_slack(channel_id, response, thread_ts)
            return
        if event_text.startswith("NON"):
            logger.info("Message not meant for Argonaut")
            return
        if event_text.startswith("GIT-FIX"):
            if event_text == "GIT-FIX":
                response = "Please provide more info what file you want to fix"
                post_message_to_slack(channel_id, response, thread_ts)
                return
            event_text = event_text.replace("GIT-FIX", "").strip()

            event_text = event_text + ", recommend one command at a time for the following tasks first clone the repo, checkout the target branch, from this branch checkout a new branch whose name reflects the fix, update the file(s). Do not recommend commands starting with bash, no newline characters in the command, follow the FORMAT in system message exactly. Make no assumptions about the file names. In the end recommend git --no-pager diff --minimal command so that user can review changes, in the response include the output of this command git --no-pager diff --minimal"
            role = "user"
            content = event_text 
            update_elasticsearch(es, thread_ts, role, content, logger=logger)            
            response = get_chatgpt_response(es, thread_ts, max_response_tokens, temperature, logger=logger)
            role = "assistant"
            content = response
            update_elasticsearch(es, thread_ts, role, content, logger=logger)           
            if AUTO_RUN:
                    process_in_background({"type": "event_callback", "event": {"type": "message", "user": BOT_USER_ID, "text": "RUN", "channel": channel_id, "thread_ts": thread_ts}}, logger)
            
            #post_message_to_slack(channel_id, response, thread_ts)
            return
#when Auto_run is true the below usecase is not triggered
        if event_text == "GIT-PR":

            event_text = "do not clone, do not delete the git repo clone folder. recommend one command at a time for the following tasks , cd to the git repo clone folder and confirm the new branch name, git add , git commit, git push to the new branch in remotre repository, create a PR using gh commands from the current branch to the target branch. Return to the user the newly created PR's URL. Do not recommend commands starting with bash, no newline characters in the command, follow the FORMAT in system message exactly."
            role = "user"
            content = event_text 
            update_elasticsearch(es, thread_ts, role, content, logger=logger)            
            response = get_chatgpt_response(es, thread_ts, max_response_tokens, temperature, logger=logger)
            role = "assistant"
            content = response
            update_elasticsearch(es, thread_ts, role, content, logger=logger)
            #post_message_to_slack(channel_id, response, thread_ts)
            if AUTO_RUN:
                process_in_background({"type": "event_callback", "event": {"type": "message", "user": BOT_USER_ID, "text": "RUN", "channel": channel_id, "thread_ts": thread_ts}}, logger)
            return
        if event_text == "GIT-MERGE":

            event_text = "Merge the newly created PR using gh command, and sync the application"
            role = "user"
            content = event_text 
            update_elasticsearch(es, thread_ts, role, content, logger=logger)            
            response = get_chatgpt_response(es, thread_ts, max_response_tokens, temperature, logger=logger)
            role = "assistant"
            content = response
            update_elasticsearch(es, thread_ts, role, content, logger=logger)
            #post_message_to_slack(channel_id, response, thread_ts)
            if AUTO_RUN:
                process_in_background({"type": "event_callback", "event": {"type": "message", "user": BOT_USER_ID, "text": "RUN", "channel": channel_id, "thread_ts": thread_ts}}, logger)
            return
#when Auto_run is true the below usecase is not triggered
        if event_text == "RUN":
            messages = get_thread_messages(es, thread_ts, logger=logger)
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
                role = "user"
                response = last_content
                post_message_to_slack(channel_id, response, thread_ts)
                response = "AI resolved the issue or further user input needed, type just  HELP, all caps, for more opitons"
                post_message_to_slack(channel_id, response, thread_ts)
                logger.info("No command found after code block — using fallback response") 
            else:
                output = execute_run_command(command, logger) 
                logger.info("Command output: %s | Command Error: %s | Return Code: %s | Command used: %s", output["stdout"], output["stderr"], output["returncode"], command)

                response = f"Command: {command}\nCommand Output:\n{output['stdout']}\nCommand Error:\n{output['stderr']}\nReturn Code:\n{output['returncode']}"

                if AUTO_RUN:
                    process_in_background({"type": "event_callback", "event": {"type": "message", "user": BOT_USER_ID, "text": response, "channel": channel_id, "thread_ts": thread_ts}}, logger)
                else:
                   post_message_to_slack(channel_id, response, thread_ts)
            return

          # Check if the event is a message and not from the bot itself

        if event.get('user') != BOT_USER_ID:
                
            if event_text.startswith("RUN"):
                command = event_text[4:] # Extract the command after "RUN "
                output = execute_run_command(command, logger) 
                logger.info("Command output: %s | Command Error: %s | Return Code: %s | Command used: %s", output["stdout"], output["stderr"], output["returncode"], command)

                response = f"Command: {command}\nCommand Output:\n{output['stdout']}\nCommand Error:\n{output['stderr']}\nReturn Code:\n{output['returncode']}"

                post_message_to_slack(channel_id, response, thread_ts)
                return
            elif event_text.startswith("SUMMARIZE"):
                response = summarize_conversation(
                    es=es,
                    thread_ts=thread_ts,
                    max_response_tokens=max_response_tokens,
                    temperature=temperature,
                    logger=logger
                )
                post_message_to_slack(channel_id, response, thread_ts)
            else:
                role = "user"
                content = event_text
                update_elasticsearch(es, thread_ts, role, content, logger=logger)
                messages = get_thread_messages(es, thread_ts, logger=logger)
                logger.debug("Received messages from es: %s", json.dumps(messages))
                logger.info("Received messages from es")
                token_count = count_tokens(messages, model)
                logger.info(f"Token count: {token_count}")
                if token_count > MAX_USER_INPUT_TOKENS:
                    logger.info("Token count exceeded maximum, summarizing")
                    response = summarize_conversation(
                        es=es,
                        thread_ts=thread_ts,
                        max_response_tokens=max_response_tokens,
                        temperature=temperature,
                        logger=logger
                    )
                    post_message_to_slack(channel_id, response, thread_ts)
                    role = "user"
                    content = event_text
                    update_elasticsearch(es, thread_ts, role, content, logger=logger)

                response = get_chatgpt_response(es, thread_ts, max_response_tokens, temperature, logger=logger)
                role = "assistant"
                content = response
                update_elasticsearch(es, thread_ts, role, content, logger=logger)

                if AUTO_RUN:
                    process_in_background({"type": "event_callback", "event": {"type": "message", "user": BOT_USER_ID, "text": "RUN", "channel": channel_id, "thread_ts": thread_ts}}, logger)
                else:
                    post_message_to_slack(channel_id, response, thread_ts)
                return 

        if event.get('user') == BOT_USER_ID:
#            if event_text.startswith("SUMMARY:"):
#                set_summary_index_es(es,thread_ts,logger=logger)
            if event_text.startswith("Command:"):
                role = "user"
                content = event_text
                update_elasticsearch(es, thread_ts, role, content, logger=logger)
                messages = get_thread_messages(es, thread_ts, logger=logger)
                token_count = count_tokens(messages, model)
                logger.info(f"Token count: {token_count}")
                if token_count > MAX_USER_INPUT_TOKENS:
                    logger.info("Token count exceeded maximum, summarizing")
                    response = summarize_conversation(
                        es=es,
                        thread_ts=thread_ts,
                        max_response_tokens=max_response_tokens,
                        temperature=temperature,
                        logger=logger
                    )
                    post_message_to_slack(channel_id, response, thread_ts)
                    role = "user"
                    content = event_text
                    update_elasticsearch(es, thread_ts, role, content, logger=logger)

                response = get_chatgpt_response(es, thread_ts, max_response_tokens, temperature, logger=logger)
                role = "assistant"
                #content = response
                content = "\n".join(
                    line.replace("```bash", "```", 1) if line.lstrip().startswith("```bash") else line
                    for line in response.splitlines()
                )
                update_elasticsearch(es, thread_ts, role, content, logger=logger)
                if AUTO_RUN:
                    process_in_background({"type": "event_callback", "event": {"type": "message", "user": BOT_USER_ID, "text": "RUN", "channel": channel_id, "thread_ts": thread_ts}}, logger)
                else:
                    post_message_to_slack(channel_id, response, thread_ts)
                return
            else:
              logger.info("Message was from the bot, skipping processing")
            return


def process_email_request(request, payload, logger):
    #logger.info("Email event received")
    logger.info("Received email data in process_email_request: %s", payload)
    # Start background thread
    response = process_email_in_background(payload, logger)
    return {
        "response": "response",
        "queued": False,
        "data": payload  # include entire payload back in response
    }


def process_slack_event(request, payload, logger):
    logger.info("slack event received")
    # if not verify_slack_request(request, logger):
    #     print("Verification failed")
    #     return {"error": "Invalid slack payload could not be verified"}, 400 # Forbidden if verification fails


    data = payload
    #logger.info("Received POST data: %s", data)
    logger.info("Received POST data in process_slack_event:")

    # Check if the necessary fields are in the request
    if data and 'challenge' in data and data.get("type") == "url_verification":
        # Return HTTP 200 with the 'challenge' field in the response
        return {"challenge": data['challenge']}, 200
    #Thread(target=process_in_background, args=(data,), logger).start()
    # Thread(target=process_in_background, args=(data, logger)).start()

    # return
    return process_in_background(data, logger)
def process_email_in_background(data, logger):
    def send_email_to_user(thread_ts, response, logger):
        """
        Send payload to n8n webhook /reply-mail with body and thread_ts.

        Parameters:
            payload (dict): Must contain 'thread_ts' and 'response'.
            logger (optional): Logger instance for logging.
        
        Returns:
            dict: Response from n8n webhook or error details.
        """
        url = "https://n8n:5678/webhook/reply-mail"

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
    BOT_USER_ID = "gopal.jayanti@opsmx.io"
    thread_ts = data.get("threadId")
    event_text = data.get("snippet")
    user = data.get("From")
    event_text = data.get("snippet")
    response = "Follow the conversation here %s/%s/_doc/%s?pretty=true" % (ES_EXT_URL, es_index, thread_ts)
    send_email_to_user(thread_ts, response, logger=logger)
    role = "system"
    content = system_text 
    update_elasticsearch(es, thread_ts, role, content, logger=logger)
    logger.info("Before Diagnosis: %s", event_text)
    result = run_diagnosis(event_text)
    logger.info("After Diagnosis: %s", event_text)
    if result is None:
        logger.info("No Argo CD app name could be resolved from the user input.")
    elif result == "BADAPP":
        logger.info("App name was found, but `argocd app get` failed.")
        role = "user"
        content = event_text + result
        update_elasticsearch(es, thread_ts, role, content, logger=logger)
        response = "App name was not found, because `argocd app get` failed."
        send_email_to_user(thread_ts, response, logger=logger)
        return
    else:
        logger.info("Diagnosis succeeded, posting result to Slack.")
        role = "user"
        content = event_text
        update_elasticsearch(es, thread_ts, role, content, logger=logger)
        role = "assistant"
        content = result
        update_elasticsearch(es, thread_ts, role, content, logger=logger)
        response = summarize_conversation(
            es=es,
            thread_ts=thread_ts,
            max_response_tokens=max_response_tokens,
            temperature=temperature,
            logger=logger
        )
        send_email_to_user(thread_ts, response, logger=logger)
        ##response = result
        #post_message_to_slack(channel_id, response, thread_ts)  
        return
    if event_text == "HELP":
            response = help_message
            send_email_to_user(thread_ts, response, logger=logger)
            return
    if event_text.startswith("NON"):
            logger.info("Message not meant for Argonaut")
            return
    if event_text.startswith("GIT-FIX"):
        
            if event_text == "GIT-FIX":
                response = "Please provide more info what file you want to fix"
                send_email_to_user(thread_ts, response, logger=logger)
                return
            event_text = event_text.replace("GIT-FIX", "").strip()

            event_text = event_text + ", recommend one command at a time for the following tasks first clone the repo, checkout the target branch, from this branch checkout a new branch whose name reflects the fix, update the file(s). Do not recommend commands starting with bash, no newline characters in the command, follow the FORMAT in system message exactly. Make no assumptions about the file names. In the end recommend git --no-pager diff --minimal command so that user can review changes, in the response include the output of this command git --no-pager diff --minimal"
            role = "user"
            content = event_text 
            update_elasticsearch(es, thread_ts, role, content, logger=logger)            
            response = get_chatgpt_response(es, thread_ts, max_response_tokens, temperature, logger=logger)
            role = "assistant"
            content = response
            update_elasticsearch(es, thread_ts, role, content, logger=logger)           
            if AUTO_RUN:
                process_email_in_background({ "From": BOT_USER_ID, "snippet": "RUN","thread_ts": thread_ts}, logger)
            
            #post_message_to_slack(channel_id, response, thread_ts)
            return
    if event_text == "GIT-PR":

            event_text = "do not clone, do not delete the git repo clone folder. recommend one command at a time for the following tasks , cd to the git repo clone folder and confirm the new branch name, git add , git commit, git push to the new branch in remotre repository, create a PR using gh commands from the current branch to the target branch. Return to the user the newly created PR's URL. Do not recommend commands starting with bash, no newline characters in the command, follow the FORMAT in system message exactly."
            role = "user"
            content = event_text 
            update_elasticsearch(es, thread_ts, role, content, logger=logger)            
            response = get_chatgpt_response(es, thread_ts, max_response_tokens, temperature, logger=logger)
            role = "assistant"
            content = response
            update_elasticsearch(es, thread_ts, role, content, logger=logger)
            #post_message_to_slack(channel_id, response, thread_ts)
            if AUTO_RUN:
               process_email_in_background({ "From": BOT_USER_ID, "snippet": "RUN","thread_ts": thread_ts}, logger)
            return
    if event_text == "GIT-MERGE":

            event_text = "Merge the newly created PR using gh command, and sync the application"
            role = "user"
            content = event_text 
            update_elasticsearch(es, thread_ts, role, content, logger=logger)            
            response = get_chatgpt_response(es, thread_ts, max_response_tokens, temperature, logger=logger)
            role = "assistant"
            content = response
            update_elasticsearch(es, thread_ts, role, content, logger=logger)
            #post_message_to_slack(channel_id, response, thread_ts)
            if AUTO_RUN:
                process_emal_in_background({"type": "event_callback", "event": {"type": "message", "user": BOT_USER_ID, "text": "RUN", "channel": channel_id, "thread_ts": thread_ts}}, logger)
            return
#when Auto_run is true the below usecase is not triggered
    if event_text == "RUN":
            messages = get_thread_messages(es, thread_ts, logger=logger)
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
                role = "user"
                response = last_content
                post_message_to_slack(channel_id, response, thread_ts)
                response = "AI resolved the issue or further user input needed, type just  HELP, all caps, for more opitons"
                post_message_to_slack(channel_id, response, thread_ts)
                logger.info("No command found after code block — using fallback response") 
            else:
                output = execute_run_command(command, logger) 
                logger.info("Command output: %s | Command Error: %s | Return Code: %s | Command used: %s", output["stdout"], output["stderr"], output["returncode"], command)

                response = f"Command: {command}\nCommand Output:\n{output['stdout']}\nCommand Error:\n{output['stderr']}\nReturn Code:\n{output['returncode']}"

                if AUTO_RUN:
                    process_email_in_background({ "From": BOT_USER_ID, "snippet": "RUN","thread_ts": thread_ts}, logger)
                else:
                   send_email_to_user(thread_ts, response, logger=logger)
            return

          # Check if the event is a message and not from the bot itself

    if BOT_USER_ID in user:
                
            if event_text.startswith("RUN"):
                command = event_text[4:] # Extract the command after "RUN "
                output = execute_run_command(command,logger=logger) 
                logger.info("Command output: %s | Command Error: %s | Return Code: %s | Command used: %s", output["stdout"], output["stderr"], output["returncode"], command)

                response = f"Command: {command}\nCommand Output:\n{output['stdout']}\nCommand Error:\n{output['stderr']}\nReturn Code:\n{output['returncode']}"

                send_email_to_user(thread_ts, response, logger=logger)
                return
            elif event_text.startswith("SUMMARIZE"):
                response = summarize_conversation(
                    es=es,
                    thread_ts=thread_ts,
                    max_response_tokens=max_response_tokens,
                    temperature=temperature,
                    logger=logger
                )
                send_email_to_user(thread_ts, response, logger=logger)
            else:
                role = "user"
                content = event_text
                update_elasticsearch(es, thread_ts, role, content, logger=logger)
                messages = get_thread_messages(es, thread_ts, logger=logger)
                logger.debug("Received messages from es: %s", json.dumps(messages))
                logger.info("Received messages from es")
                token_count = count_tokens(messages, model)
                logger.info(f"Token count: {token_count}")
                if token_count > MAX_USER_INPUT_TOKENS:
                    logger.info("Token count exceeded maximum, summarizing")
                    response = summarize_conversation(
                        es=es,
                        thread_ts=thread_ts,
                        max_response_tokens=max_response_tokens,
                        temperature=temperature,
                        logger=logger
                    )
                    send_email_to_user(thread_ts, response, logger=logger)
                    role = "user"
                    content = event_text
                    update_elasticsearch(es, thread_ts, role, content, logger=logger)

                response = get_chatgpt_response(es, thread_ts, max_response_tokens, temperature, logger=logger)
                role = "assistant"
                content = response
                update_elasticsearch(es, thread_ts, role, content, logger=logger)

                if AUTO_RUN:
                    process_email_in_background({ "From": BOT_USER_ID, "snippet": "RUN","thread_ts": thread_ts}, logger)
                else:
                    send_email_to_user(thread_ts, response, logger=logger)
                return 

    if BOT_USER_ID not in user:
            if event_text.startswith("Command:"):
                role = "user"
                content = event_text
                update_elasticsearch(es, thread_ts, role, content, logger=logger)
                messages = get_thread_messages(es, thread_ts, logger=logger)
                token_count = count_tokens(messages, model)
                logger.info(f"Token count: {token_count}")
                if token_count > MAX_USER_INPUT_TOKENS:
                    logger.info("Token count exceeded maximum, summarizing")
                    response = summarize_conversation(
                        es=es,
                        thread_ts=thread_ts,
                        max_response_tokens=max_response_tokens,
                        temperature=temperature,
                        logger=logger
                    )
                    send_email_to_user(thread_ts, response, logger=logger)
                    role = "user"
                    content = event_text
                    update_elasticsearch(es, thread_ts, role, content, logger=logger)

                    response = get_chatgpt_response(es, thread_ts, max_response_tokens, temperature, logger=logger)
                    role = "assistant"
                    #content = response
                    content = "\n".join(
                        line.replace("```bash", "```", 1) if line.lstrip().startswith("```bash") else line
                        for line in response.splitlines()
                    )
                    update_elasticsearch(es, thread_ts, role, content, logger=logger)
                    if AUTO_RUN:
                        process_email_in_background({ "From": BOT_USER_ID, "snippet": "RUN","thread_ts": thread_ts}, logger)
                    else:
                        send_email_to_user(thread_ts, response, logger=logger)
                    return
                else:
                    logger.info("Message was from the bot, skipping processing")
                    return
    logger.info("from process_email_in_background, data: %s", data)
    logger.info("unique id of this email thread: %s", thread_ts)
    logger.info("the message is %s", event_text)
    logger.info("email event processing in background")
    return response

def webhook_handler(request, logger):

    logger.info("Webhook endpoint hit inside webhook_handler")
    ensure_index_exists(logger)
    payload = request.get_json()
    logger.info("webhook_handler, data: %s", payload)
    if not payload:
        return {"error": "Invalid payload"}, 400
    try:
        result = route_source(request, logger)
        return {"status": "ok", "result": result}, 200
    except Exception as e:
        logger.exception("Error handling webhook")
        return {"error": str(e)}, 500


