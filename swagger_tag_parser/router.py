import json
from parser import extract_tags
from tag_matcher import find_best_tag
from api_summary_extractor import get_summaries_for_service
from summary_matcher import find_best_summary
from api_extractor import get_api_by_summary
from crd_payload_builder import build_payload_from_crd
from llm_field_prompter import ask_llm_to_fill

if __name__ == "__main__":
    swagger_path = "service_router/swagger.json"
    crd_path = "service_router/argocd-application-crd-compressed.json"

    user_input = input("Enter user request (e.g., 'sync application'): ")

    tags = get_tags(swagger_path)
    best_tag = find_best_tag(user_input, tags)
    print(json.dumps({"best_tag": best_tag}, indent=2))

    summaries = get_summaries_for_service(swagger_path, best_tag)
    best_summary = find_best_summary(user_input, summaries)
    print(json.dumps({"best_summary": best_summary}, indent=2))

    api = get_api_by_summary(swagger_path, best_summary)
    print(json.dumps({
        "path": api["path"],
        "method": api["method"],
        "operationId": api["operationId"]
    }, indent=2))

    if api["method"] == "GET":
        full_request = {
            "method": api["method"],
            "url": f"https://your-argocd-server{api['path']}"
        }
    else:
        payload = build_payload_from_crd(crd_path)
        full_request = {
            "method": api["method"],
            "url": f"https://your-argocd-server{api['path']}",
            "body": {
                "apiVersion": "argoproj.io/v1alpha1",
                "kind": "Application",
                "metadata": {"name": "<string>"},
                "spec": payload
            }
        }

    print("\nGenerated request:")
    print(json.dumps(full_request, indent=2))

    prompts = ask_llm_to_fill(user_input, full_request)
    print(json.dumps(prompts, indent=2))

    # Simulate user responses (in real case, collect interactively or via UI)
    user_responses = {}
    for prompt in prompts.get("prompts", []):
        print(f"Prompt: {prompt}")
        value = input("Response: ")
        user_responses[prompt] = value

    # Replace <...> placeholders in request with user responses
    def fill_placeholders(obj):
        if isinstance(obj, dict):
            return {k: fill_placeholders(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [fill_placeholders(v) for v in obj]
        elif isinstance(obj, str) and ("<" in obj and ">" in obj):
            for question, response in user_responses.items():
                if response and obj.startswith("<") and obj.endswith(">"):
                    return response
            return obj
        else:
            return obj

    if "body" in full_request:
        full_request["body"] = fill_placeholders(full_request["body"])

    print("\nFinal request with user input:")
    print(json.dumps(full_request, indent=2))