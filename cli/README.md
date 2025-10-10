# 🧭 Argonaut CLI (`naut.sh`)
## pre-requisites
bash, curl jq, argonaut credentials
## Overview

**Argonaut CLI** — known as `naut.sh` — is a lightweight **command-line interface for interacting with the Argonaut AI assistant**.  
It enables developers, DevOps engineers, and SREs to converse with the Argonaut backend from their terminal — seamlessly sending commands, analyzing outputs, and maintaining persistent conversational *threads* across multiple sessions.

In essence, it brings the power of Argonaut’s ChatOps and AI-driven automation to your terminal — no browser required.

---

## 🎯 What Problem Does It Solve?

Modern DevOps workflows often span **Argo CD**, **Kubernetes**, **Helm**, and **GitOps pipelines**, but:
- AI tools like ChatGPT can’t securely access local or cluster-level command outputs.  
- Sharing operational context (e.g., `kubectl`, `argocd app get`, `helm status`) with AI assistants is cumbersome and non-reproducible.  
- There’s no persistent “thread” between CLI actions and AI analysis.

`naut.sh` solves these problems by acting as a **bidirectional bridge** between your local CLI and the Argonaut backend:
- It **posts command results** (stdout/stderr) to Argonaut for analysis or recommendations.  
- It **retrieves AI responses**, including suggested commands enclosed in code fences (` ```command``` `).  
- It maintains a **per-thread local state** with full history and outputs for reproducibility and traceability.  

---

## 🧩 How It Works

Each CLI session runs inside a **“thread”** — a contextual conversation between your terminal and Argonaut.

1. **Start a new conversation:**
   ```bash
   ./naut.sh recommend --new-thread -c "How do I get Argo CD app sync status?"
   ```
   → Argonaut analyzes and replies with a recommended command.

2. **Run the suggested command:**
   ```bash
   ./naut.sh RUN
   ```
   → Executes the last recommended command and records the output locally.

3. **Analyze results:**
   ```bash
   ./naut.sh analyze
   ```
   → Sends command results back to Argonaut for evaluation.

4. **Wait for Argonaut’s response:**
   ```bash
   ./naut.sh wait
   ```
   → Displays the assistant’s next suggestion or analysis.

Each thread stores:
```
~/.naut/threads/<thread_id>/
 ├── last_command
 ├── last_run.json
 ├── history.log
```

---

## ⚙️ Key Features

| Feature | Description |
|----------|--------------|
| **Threaded Context** | Maintains separate conversation threads (`cli-<user>-<timestamp>`). |
| **Offline-safe State** | Stores config, commands, and history under `~/.naut`. |
| **Secure Configuration** | Uses `ARGONAUT_TOKEN` for auth; config stored with restrictive permissions. |
| **Smart Command Parsing** | Extracts commands from fenced code blocks in AI responses. |
| **Risk Confirmation** | Prompts before running destructive operations like `kubectl delete` or `rm -rf`. |
| **JSON-Aware Communication** | Uses `jq` for clean JSON parsing (fallbacks available). |
| **Truncated Payload Safety** | Large command outputs are trimmed before sending to the server. |

---

## 🚀 Advantages of Using `naut.sh`

- **Consistent workflow automation** — easily chain `recommend → run → analyze → wait`.
- **End-to-end visibility** — all inputs and outputs are logged per-thread.
- **AI-augmented DevOps** — get Argo CD or Kubernetes command suggestions directly in CLI form.
- **Air-gapped flexibility** — local execution ensures cluster data never leaves your environment without control.
- **Fast onboarding** — zero dependencies beyond `bash`, `curl`, and optionally `jq`.
- **Universal context** — same CLI works across Slack, Chat, and terminal modes under Argonaut’s thread model.

---

## 🔧 Setup

```bash
# 1. Configure login
./naut.sh login --url https://argonaut.example.com --token <API_TOKEN> --user users/<id>

# 2. Verify status
./naut.sh status

# 3. Start using Argonaut CLI
./naut.sh recommend --new-thread -c "Check my Argo CD apps"
./naut.sh RUN
./naut.sh analyze
./naut.sh wait
```

---

## 📂 File Structure

```
~/.naut/
 ├── config
 ├── current_thread
 └── threads/
     └── cli-user-<epoch>/
         ├── last_command
         ├── last_run.json
         └── history.log
```

---

## 🧠 Example Workflow

```bash
./naut.sh recommend --new-thread -c "List all apps in Argo CD"
./naut.sh RUN
./naut.sh analyze
./naut.sh wait
```

**Argonaut CLI** replies with actionable insights — for example:
```
Use the following command:
```argocd app list```
```
After running and analyzing, Argonaut can automatically suggest fixes, retry commands, or deployment checks.

---

## 💡 Why Argonaut CLI?

> The difference between clicking in a UI and **commanding your infrastructure through intelligence**  
> is the difference between operations and orchestration.

Argonaut CLI turns your terminal into an intelligent, context-aware DevOps assistant — built for real-world, secure, traceable automation.
