import os
import json
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableSequence
import re
from pathlib import Path


# Prompt Template
source_classification_prompt = PromptTemplate.from_template("""
You are an AI assistant that classifies the source of a list of JSON payloads.

Each item in the list is an event or message.

Your task is to determine whether the list is most likely from:
- Slack
- Email
- or Unknown

Also, list the specific field names (across the items) that helped you decide.
If you are unable to find out give the failure reason in detail.

### Input:
A list of JSON objects representing the payload:
```json
{payload}
```
### Respond in this exact JSON format:
{{
  "source": "...",
  "confidence_reason": [ ... ]
  "failure_reason": "..."
}}
""")

# LangChain Chain
llm = ChatOpenAI(
    model=os.getenv("model", "gpt-4o"),
    temperature=0,
    max_tokens=300
)

# classification_chain = RunnableSequence([
#     source_classification_prompt,
#     llm,
#     StrOutputParser()
# ])
classification_chain = source_classification_prompt | llm | StrOutputParser()


# def classify_payload_source(payload):
#     """Classifies the source of the given payload using the LLM chain."""
#     print(f"json.load: {payload}")
#     formatted_payload = json.dumps(payload, indent=2)
#     print(f"json.load: {payload}")
#     result = classification_chain.invoke({"payload": formatted_payload})
#     print("🔍 Raw LLM output:")
#     print(result)
#     try:
#         return json.loads(result)
#     except json.JSONDecodeError:
#         return {
#             "source": "unknown",
#             "confidence_reason": ["invalid or ambiguous format"]
#         }
def classify_payload_source(payload):
    """Classifies the source of the given payload using the LLM chain."""
    formatted_payload = json.dumps(payload, indent=2)
    result = classification_chain.invoke({"payload": formatted_payload})

    print("🔍 Raw LLM output:")
    print(result)

    # Try to extract JSON between triple backticks
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", result)
    json_block = match.group(1) if match else result.strip()

    # try:
    #     return json.loads(json_block)
    # except json.JSONDecodeError as e:
    #     print("❌ JSON decode error:", e)
    #     return {
    #         "source": "unknown",
    #         "confidence_reason": ["invalid or ambiguous format"],
    #         "raw_output": result
    #     }
    try:
        
        parsed = json.loads(json_block)

        # Write to file if it doesn't already exist
        fields = parsed.get("confidence_reason", [])
        source = parsed.get("source", "unknown").lower()

        if fields and isinstance(fields, list):
            file_path = Path(f"check_{source}_payload_fields.txt")
            if not file_path.exists():
                file_path.write_text("\n".join(fields))
                print(f"✅ Wrote confidence_reason fields to {file_path}")
            else:
                print(f"ℹ️ File already exists: {file_path}")

    except json.JSONDecodeError as e:
            print("❌ JSON decode error:", e)
    return json.loads(json_block)


def load_sample_payload(filename):
    with open(filename, "r", encoding="utf-8") as f:
        #print(f"Loading sample payload from {filename}")
        payload = json.load(f)
        #print(f"json.load: {payload}")
        return payload


if __name__ == "__main__":
    # Example test payloads
    try:
        #email_payload = load_sample_payload("email_sample_payload.json")
        #print(f"json.load: {email_payload}")
        slack_payload = load_sample_payload("slack_sample_payload.json")
    except FileNotFoundError as e:
        print(f"File not found: {e.filename}")
        exit(1)

    slack_payload = {
        "event": {
            "type": "message",
            "ts": "12345.67890",
            "text": "Hello from Slack"
        }
    }

    print("Email Payload Classification:")
    #print(json.dumps(classify_payload_source(email_payload), indent=2))

    #print("\nSlack Payload Classification:")
    print(json.dumps(classify_payload_source(slack_payload), indent=2))
