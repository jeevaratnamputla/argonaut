import requests
import subprocess
import sys
import logging
import json
import os
import time
import threading
from threading import Thread
#from argocd_auth import authenticate_with_argocd # to keep the argocd token fresh
import git_config
#from slack import post_message_to_slack, get_bot_user_id, verify_slack_request, get_thread_ts_from_reaction
#from elastic import ensure_index_exists, get_es_client, update_elasticsearch, set_summary_index_es, get_thread_messages, update_reaction
from generic_storage import ensure_index_exists, update_message, set_summary_index, get_thread_messages, update_reaction
#from chatgpt import get_chatgpt_response
from call_llm import get_llm_response
import html
import re
#from count_tokens import count_tokens
#from argocd_diagnose import run_diagnosis
#from summarize_text import summarize_text
#from selfdiagnose import diagnose_system
from create_system_text import create_system_text
#from argocd_flow import process_prompt
from execute_run_command import execute_run_command
from summarize_conversation import summarize_conversation
from send_response import send_response
from test_review_command import run_review

AUTO_RUN = os.getenv("AUTO_RUN", "false").lower() == "true"
MAX_USER_INPUT_TOKENS = int(os.environ.get("MAX_USER_INPUT_TOKENS", 6000))
CONVERSATION_URL = os.getenv("CONVERSATION_URL")
model=os.getenv("model", "gpt-4.1")
max_response_tokens = os.getenv("max_response_tokens", 200)
max_response_tokens = int(max_response_tokens)  # Ensure it's an integer
temperature = os.getenv("temperature", 0.0)
temperature = float(temperature)  # Ensure it's a float
help_message = """This assistant, Argonaut, produces commands, each with a comment. Does not produce a lot of text.
USE CAUTION! and your own judgement to run these commands while using AUTORUN=false
Context is preserved in threads NOT in channel.
Each new thread has a new context and will not be related to other threads.
use RUN to run a command example: RUN kubectl get pods, using just RUN will run the last command suggested by the bot.
only kubectl commands are allowed
use SUMMARIZE to get a summary of the conversation so for, example: SUMMARIZE
type HELP for this message
"""

#whatfi we can custom first message through this variable
MOST_IMPORTANT = """
            Always make the response be brief.
            or provide a brief answer to the user or ask user for more information.
            You either recommend a command or a script  or both or neither.
            You  recommend the command in the correct format 
            # This is a single line comment
            ``` This is a command ```
            example:
            # To get the application status json    
            ``` argocd app get appName -o json | jq -r '.status' | jq -c ```
            If you dont know the exact subcommands or flags recommend argocd --help
            If you know the subcommand but want to get more info then you can also recommend argocd <subcommand> --help
            example: argocd app -help.
            Recommend only one command at a time.
    """
#summary_report = diagnose_system()
system_text = create_system_text()
#system_text += summary_report

es_index = os.getenv("es_index")
ES_EXT_URL = os.getenv("ES_EXT_URL")
# Elasticsearch endpoint with authentication
#s = get_es_client()
#ensure_index_exists(logger)

def handle_event_text(payload, logger):
    event_text = payload.get("text").strip()    
    thread_ts = payload.get("thread_ts")
    if event_text is None:
        logger.warning("event_text is None — take a look at payload: %s", payload)
        return {"reponse": "No event_text in payload"} 
    if event_text.strip().upper() == "HELP":
            response = help_message
            response = "NAUT " + response
            send_response(payload, thread_ts, response, logger)
            logger.info("Sent the HELP text ...")
            return {"reponse": "Sent the HELP text ..."}
    
    if event_text.startswith("NAUT"):
            logger.info("Message not meant for Argonaut")
            return {"reponse": "Message not meant for Argonaut"} 

    isFirstMessage = payload.get("isFirstMessage")
    if str(isFirstMessage).lower() == "true":
        logger.warning("isFirstMessage is true")
        response = "Follow the conversation here https://%s/threads/%s" % (CONVERSATION_URL, thread_ts)
        response = "NAUT " + response + "\n" + help_message
        send_response(payload, thread_ts, response, logger)
        role = "system"
        content = system_text
        logger.info("Updating ES: thread_ts=%s, role=%s, content=%s", thread_ts, role, content)
        update_message( thread_ts, role, content, logger=logger)
        role = "user"
        content = event_text + MOST_IMPORTANT
        update_message( thread_ts, role, content, logger=logger)
       
        payload["isFirstMessage"] = "false"
        newpayload = payload
        handle_event_text(newpayload, logger)
        return
    #logger.info("thread_ts in handle_event_text is: %s", thread_ts) # this is the thread_ts in handle_event_text 
    match event_text:
        #This should be moved to n8n
        case _ if event_text.startswith("TOOL"):
            role = "user"
            command_output_handler_text = "Be brief. Less than 75 words. Analyze this command output, if there are errors, try to fix them. Use the command with --help to get more info to fix the errors, example: ```argocd app manifests --help```. Recommend a new command if you can fix the errors, otherwise ask user for help. Summarize with a focus on which Problem Resources are not in Synced or Healthy state. We will later investigate those manifests of Problem Resources."
            content = command_output_handler_text + "\n" + event_text
            update_message( thread_ts, role, content, logger=logger)
            response = get_llm_response( thread_ts, max_response_tokens, temperature, logger=logger)
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
                response = get_llm_response( thread_ts, max_response_tokens, temperature, logger=logger)
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
                test_review = run_review(command, logger=logger)
                if not test_review.get("valid", False):
                    bad_command_handler_text = (
                        "I have reviewed the command and found these issues:\n"
                        + json.dumps(test_review, ensure_ascii=False, indent=2)
                    )
                    role = "user"
                   #prior_response = response if "response" in locals() and isinstance(response, str) else ""
                    #content = bad_command_handler_text + (("\n" + prior_response) if prior_response else "")
                    content = bad_command_handler_text
                    update_message(thread_ts, role, content, logger=logger)

                    response = get_llm_response(thread_ts, max_response_tokens, temperature, logger=logger)
                    role = "assistant"
                    update_message(thread_ts, role, response, logger=logger)
                    response = "NAUT " + response
                    send_response(payload, thread_ts, response, logger)
                    logger.info("Sent the bad command for analysis ...")
                else:
                    output = execute_run_command(command, logger=logger) 
                    logger.info("Command: %s | Command Output: %s | Command Error: %s | Return Code: %s ", command, output["stdout"], output["stderr"], output["returncode"])
                    #whatif the return code is not 0?
                    # we need to log the error and the resolution in a persisten location thread agnostic
                    response = f"TOOL Command: {command}\nCommand Output:\n{output['stdout']}\nCommand Error:\n{output['stderr']}\nReturn Code:\n{output['returncode']}"
                    #whatif the response is too long
                    command_output_handler_text = "Be brief. Less than 75 words. Analyze this command output, if there are errors, try to fix them. Use the command with --help to get more info to fix the errors, example: ```argocd app manifests --help```. Recommend a new command if you can fix the errors, otherwise ask user for help. Summarize with a focus on which Problem Resources are not in Synced or Healthy state. We will later investigate those manifests of Problem Resources. Offer command options too"
                    role = "user"
                    content = command_output_handler_text + "\n" + response
                    update_message( thread_ts, role, content, logger=logger)
                    response = get_llm_response( thread_ts, max_response_tokens, temperature, logger=logger)
                    role = "assistant"
                    content = response
                    response = "NAUT " + response
                    update_message( thread_ts, role, content, logger=logger)
                    send_response(payload, thread_ts, response, logger)
                return response

        case "SUMMARIZE":
                response = summarize_conversation(
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
            response = get_llm_response( thread_ts, max_response_tokens, temperature, logger=logger)
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
            response = get_llm_response( thread_ts, max_response_tokens, temperature, logger=logger)
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
            response = get_llm_response( thread_ts, max_response_tokens, temperature, logger=logger)
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
            test_review = run_review(command, logger=logger)
            if not test_review.get("valid", False):
                    bad_command_handler_text = (
                        "I have reviewed the command and found these issues:\n"
                        + json.dumps(test_review, ensure_ascii=False, indent=2)
                    )
                    role = "user"
                   #prior_response = response if "response" in locals() and isinstance(response, str) else ""
                    #content = bad_command_handler_text + (("\n" + prior_response) if prior_response else "")
                    content = bad_command_handler_text
                    update_message(thread_ts, role, content, logger=logger)

                    response = get_llm_response(thread_ts, max_response_tokens, temperature, logger=logger)
                    role = "assistant"
                    update_message(thread_ts, role, response, logger=logger)
                    response = "NAUT " + response
                    send_response(payload, thread_ts, response, logger)
                    logger.info("Sent the bad command for analysis ...")
            else:
                logger.info("Running the suggested commands...")

                output = execute_run_command(command, logger=logger) 
                
                logger.info("Command: %s | Command output: %s | Command Error: %s | Return Code: %s ", command, output["stdout"], output["stderr"], output["returncode"])
                response = f"Command: {command}\nCommand Output:\n{output['stdout']}\nCommand Error:\n{output['stderr']}\nReturn Code:\n{output['returncode']}"
                #whatif response is too big?
                command_output_handler_text = "Be brief. Less than 75 words. Analyze this command output, if there are errors, try to fix them. Use the command with --help to get more info to fix the errors, example: ```argocd app manifests --help```. Recommend a new command if you can fix the errors, otherwise ask user for help. Summarize with a focus on which Problem Resources are not in Synced or Healthy state. We will later investigate those manifests of Problem Resources."
                role = "user"
                content = command_output_handler_text + "\n" + response
                update_message( thread_ts, role, content, logger=logger)
                response = "NAUT " + response
                send_response(payload, thread_ts, response, logger)
                response = get_llm_response( thread_ts, max_response_tokens, temperature, logger=logger)
                role = "assistant"
                content = response
                update_message( thread_ts, role, content, logger=logger)
                response = "NAUT " + response
                send_response(payload, thread_ts, response, logger)
            return response

        case _:
            role = "user"
            content = event_text
            update_message( thread_ts, role, content, logger=logger)            
            response = get_llm_response( thread_ts, max_response_tokens, temperature, logger=logger)
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
                response = "NAUT " + response + " type RUN all caps to run the command supplied OR type RUN your-own-command here to run your own"  
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


