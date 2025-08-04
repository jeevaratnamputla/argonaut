import json
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o", temperature=0)

EXTRACTION_TEMPLATE = """
You are a dev assistant. From the following conversation (a list of messages), extract:
- GitHub repo URL
- Target branch (targetRevision)
- Directory path (optional)

Return JSON like:
{{
  "repo_url": "...",
  "source_branch": "...",
  "repo_path": "..."
}}

Conversation:
{conversation}
"""

def extract_repo_metadata(messages: list[dict]) -> dict:
    text = json.dumps(messages, indent=2)

    prompt = ChatPromptTemplate.from_template(EXTRACTION_TEMPLATE)
    chain = prompt | llm | StrOutputParser()

    result = chain.invoke({"conversation": text}).strip()

    if not result:
        raise ValueError("❌ LLM returned empty result during metadata extraction")

    print("🔍 LLM raw output:\n", result)

    # Strip markdown code block formatting if present
    if result.startswith("```json"):
        result = result.removeprefix("```json").strip()
    if result.endswith("```"):
        result = result.removesuffix("```").strip()

    metadata = json.loads(result)

    # Always extract fix_instruction from the last user message that starts with GIT-FIX
    fix_instruction = None
    for msg in reversed(messages):
        if msg["role"] == "user" and msg["content"].lower().startswith("git-fix"):
            fix_instruction = msg["content"][8:].strip()
            break

    if not fix_instruction:
        raise ValueError("❌ No GIT-FIX instruction found in user messages.")

    metadata["fix_instruction"] = fix_instruction
    return metadata