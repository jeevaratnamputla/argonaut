from pipeline import run_pipeline
import json

with open("conversation.json") as f:
    chat = json.load(f)

pr_url = run_pipeline.invoke(chat["messages"])
print("✅ PR created:", pr_url)