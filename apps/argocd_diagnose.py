
import subprocess
import yaml
import langchain

from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnableBranch

# === Initialize the LLM ===
llm = ChatOpenAI(model="gpt-4o", temperature=0)

# === Diagnosis prompt for degraded apps ===
diagnose_prompt = PromptTemplate.from_template("""
The following is the YAML output of an Argo CD application which is not fully synced or healthy:

```yaml
{app_yaml}
```
Be concise.
Summarize the source and d estination of the cluster.
Please analyze this and explain two possible reasons for the degraded state or out-of-sync status. Be concise. Then list the Kubernetes resources that may be affected.
""")

# === Resource analysis prompt ===
resource_analysis_prompt = PromptTemplate.from_template("""
The following Kubernetes manifest may be causing the application to be degraded or out of sync:

```yaml
{resource_yaml}
```
Be concise.
Explain why this resource might be causing issues and suggest two possible remediations.
""")

def handle_known_app(result: dict) -> str:
    
    try:
        app_output = yaml.safe_load(result["app_output"])

        sync_status = app_output.get("status", {}).get("sync", {}).get("status", "")
        health_status = app_output.get("status", {}).get("health", {}).get("status", "")

        if sync_status == "Synced" and health_status == "Healthy":
            summary = f"✅ Application **{result['app_name']}** is working as expected."
            return f"{summary}\n\n```yaml\n{result['app_output']}\n```"
        else:
            summary = (
                f"⚠️ Application **{result['app_name']}** is not fully healthy or synced.\n"
                f"- Sync Status: {sync_status or 'Unknown'}\n"
                f"- Health Status: {health_status or 'Unknown'}"
            )

            explain_prompt = diagnose_prompt.format(app_yaml=result["app_output"])
            explanation = llm.invoke(explain_prompt)

            # Get manifests using argocd app manifests
            try:
                manifest_result = subprocess.run(
                    ["argocd", "app", "manifests", result["app_name"]],
                    capture_output=True,
                    text=True,
                    check=True
                )
                manifests = manifest_result.stdout.strip()
                manifest_docs = [doc.strip() for doc in manifests.split("---") if doc.strip()]

                # Analyze each manifest with LLM
                analysis_results = []
                for doc in manifest_docs:
                    try:
                        parsed = yaml.safe_load(doc)
                        kind = parsed.get("kind")
                        name = parsed.get("metadata", {}).get("name")
                        namespace = parsed.get("metadata", {}).get("namespace", "default")

                        resource_yaml = f"# Resource: {kind}/{name} in {namespace}\n---\n{doc}"
                        detail_prompt = resource_analysis_prompt.format(resource_yaml=resource_yaml)
                        response = llm.invoke(detail_prompt)

                        explanation_block = (
                            f"### {kind}/{name} in {namespace}\n"
                            f"```yaml\n{doc}\n```\n"
                            f"\n🧠 Explanation:\n{response.content.strip()}"
                        )

                        analysis_results.append(explanation_block)
                    except Exception:
                        continue

                analysis_summary = "\n\n".join(analysis_results)
            except subprocess.CalledProcessError as e:
                manifests = f"Failed to retrieve manifests: {e.stderr.strip()}"
                analysis_summary = "Could not analyze manifests."

            return (
                f"{summary}\n\n"
                f"🤖 Diagnosis:\n{explanation.content.strip()}\n\n"
                f"---\n\n"
                f"📊 Affected Resources Analysis:\n{analysis_summary}\n\n"
                # f"---\n\n"
                # f"📆 Full App YAML:\n```yaml\n{result['app_output']}\n```"
                )

    except Exception as e:
        return f"⚠️ Failed to parse YAML output for app **{result['app_name']}**.\nError: {str(e)}\n\n```text\n{result['app_output']}\n```"

def handle_unknown_app(result: dict) -> str:
    return "BADAPP"

def make_branch_chain():
    extract_app_prompt = PromptTemplate.from_template("""
You are a helpful assistant. Extract the Argo CD application name from this user input.

User prompt: "{user_input}"

If you find an app name, return just that name. Otherwise return "None".
""")

    def validate_app_and_get_output(app_name: str) -> dict:
        app_name = app_name.strip()
        if not app_name or app_name.strip().lower() == "none":
            #print( app_name could not be resolved)
            return None

        try:
            result = subprocess.run(
                ["argocd", "app", "get", "-o", "yaml", app_name],
                capture_output=True,
                text=True,
                check=True
            )
            return {"app_name": app_name, "app_output": result.stdout.strip()}
        except subprocess.CalledProcessError:
            return "BADAPP"

    return (
        RunnableLambda(lambda user_input: {"user_input": user_input})
        | extract_app_prompt
        | llm
        | StrOutputParser()
        | RunnableLambda(validate_app_and_get_output)
        | RunnableBranch(
            (lambda res: res is None, RunnableLambda(lambda _: None)),
            (lambda res: res == "BADAPP", RunnableLambda(handle_unknown_app)),
            (lambda res: isinstance(res, dict) and res.get("app_output") is not None, RunnableLambda(handle_known_app)),
            RunnableLambda(lambda _: "UNKNOWN")
            )

        )



# === Callable function ===
def run_diagnosis(user_prompt: str) -> str:
    chain = make_branch_chain()
    return chain.invoke(user_prompt)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python argocd_diagnose.py '<user prompt>'")
        sys.exit(1)
    user_prompt = sys.argv[1]
    print(run_diagnosis(user_prompt))
