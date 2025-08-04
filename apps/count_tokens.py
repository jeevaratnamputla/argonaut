# count_tokens.py
import os
import sys
import json
import tiktoken

def count_tokens(messages, model):
    #encoding = tiktoken.encoding_for_model(model)
    encoding = tiktoken.get_encoding("cl100k_base")

    if model.startswith("gpt-3.5") or model.startswith("gpt-4"):
        tokens_per_message = 3
        tokens_per_name = 1
    else:
        raise NotImplementedError(f"Token counting not supported for model {model}")

    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
            if key == "name":
                num_tokens += tokens_per_name
    num_tokens += 3  # for assistant reply primer
    return num_tokens

def main():
    model = os.environ.get("MODEL_NAME")
    if not model:
        print("MODEL_NAME environment variable not set", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage: count_tokens.py '<messages_json>'", file=sys.stderr)
        sys.exit(1)

    try:
        messages = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(f"Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)

    count = count_tokens(messages, model)
    print(count)

if __name__ == "__main__":
    main()
