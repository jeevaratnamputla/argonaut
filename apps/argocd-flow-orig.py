# argocd_flow.py

import os
import openai
import subprocess
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def chat_completion(messages):
    response = client.chat.completions.create(
            messages=messages,
            model=os.getenv("model", "gpt-4.1"),
            max_tokens=os.getenv("max_response_tokens", 500),
            temperature=os.getenv("temperature", 0.9),
            top_p=float(os.getenv("top_p", 0.5))
        )
    return response.choices[0].message.content.strip()

def extract_application_name(prompt):
    messages = [
        {"role": "system", "content": "Extract the application name from the prompt. Only return the name, if there is no application name return, None. Do not explain."},
        {"role": "user", "content": prompt}
    ]
    return chat_completion(messages)

def get_application_list():
    cmd = "argocd app list | awk '{print $1}' | sed 's#/# #' | awk '{print $2}'"
    return subprocess.getoutput(cmd).splitlines()

def app_exists(app_name, app_list):
    return app_name in app_list

def get_app_output(app_name):
    return subprocess.getoutput(f"argocd app get {app_name}")

def extract_error_message(app_output):
    messages = [
        {"role": "system", "content": "Extract error message and return it otherwise return None, Do not explain"},
        {"role": "user", "content": app_output}
    ]
    return chat_completion(messages)

def generalize_error_message(error_msg):
    messages = [
        {"role": "system", "content": "Preserve as much of text as possible and remove specifics and generalize this error, do not explain"},
        {"role": "user", "content": error_msg}
    ]
    return chat_completion(messages)

def post_to_slack(message):
    print(f"SLACK: {message}")  # Replace with real Slack API call

def check_history_for_error(error_msg):
    # TODO: Replace with real vector or semantic search
    return False, None

def process_prompt(prompt):
    app_name = extract_application_name(prompt)
    if app_name == "None":
        sys_msg = (
            "You are an expert in argocd, kubernetes, github and your primary focus is to provide accurate, reliable, "
            "and fact-checked information. Please provide the reference URLs for the answers and If you're unsure of an "
            "answer be transparent about it."
        )
        messages = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": prompt}
        ]
        response = chat_completion(messages)
        post_to_slack(response)
        return

    app_list = get_application_list()
    if not app_exists(app_name, app_list):
        post_to_slack(f"Application `{app_name}` does not exist.")
        return

    app_output = get_app_output(app_name)
    error_msg = extract_error_message(app_output)

    if error_msg == "None":
        post_to_slack("No error message found in application output.")
        return
    else:
        post_to_slack(f"Error message: {error_msg}")

    similar, past_command = check_history_for_error(error_msg)
    if similar and past_command:
        past_output = subprocess.getoutput(past_command)
        post_to_slack(past_output)
    else:
        generalized = generalize_error_message(error_msg)
        post_to_slack(generalized)

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python argocd_flow.py 'your prompt here'")
        sys.exit(1)

    prompt = sys.argv[1]
    process_prompt(prompt)
