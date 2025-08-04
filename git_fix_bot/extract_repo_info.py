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
- Fix instruction (if any)

Return JSON like:
{{
  "repo_url": "...",
  "source_branch": "...",
  "repo_path": "...",
  "fix_instruction": "..."
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

    # Provide a default if fix_instruction is missing or null
    if metadata.get("fix_instruction") is None:
        metadata["fix_instruction"] = "Fix an issue in the application code"

    return metadata