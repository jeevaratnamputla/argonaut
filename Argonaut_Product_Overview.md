# 🧭 Argonaut — AI Command & Control for GitOps

## Overview
**Argonaut** (often referred to as **“Naut”** in CLI form) is an **AI-powered DevOps command and control system** designed to operate across **Argo CD, Kubernetes, Git, Helm, and CI/CD pipelines**, integrating deeply with **Slack, Google Chat, Gmail, and n8n workflows**.  
It acts as an **intelligent co-pilot** that understands infrastructure and GitOps operations conversationally and operationally — capable of *recommending, validating, and executing* DevOps actions in real-time.

---

## 🧩 Core Capabilities

### 1. Argo CD Intelligence Layer
- Uses the **Argo CD CLI** and **ApplicationSet APIs** to:
  - Analyze app health (`argocd app get`, `argocd app manifests`, etc.)
  - Automate syncs, rollbacks, and comparisons.
  - Detect and explain `ComparisonError`, `SyncError`, and CRD mismatches.
- Can generate and execute Argo CD commands autonomously or upon approval.

### 2. Kubernetes Control
- Understands and interacts with clusters (`kubectl`, Helm, KEDA, VPA).
- Supports **multi-cluster setups** on **AWS EKS**, **Rackspace**, and **kind**.
- Manages resources via **Helm**, **Ingress**, **cert-manager**, and **StorageClasses**.
- Handles secrets (Vault → Kubernetes Secrets migration), persistent volumes, and service disruptions intelligently.

### 3. GitOps Integration
- Interfaces with **GitHub**, **Bitbucket**, and **Azure DevOps Repos**.
- Uses **GitHub CLI (gh)** for automated PRs and fixes (via “GIT-FIX” and similar commands).
- Supports **repository_dispatch events** for dynamic workflow triggers.

---

## 🧠 AI and Memory Architecture

### 1. LLM Abstraction Layer
- Supports **OpenAI GPT-4o**, **Google Gemini**, **Anthropic Claude (via Bedrock)**, and local **Llama-compatible** APIs.
- `call_llm.py` routes requests based on environment (API key or Bedrock client).
- Bedrock integrations use AWS IAM roles instead of API keys.

### 2. Multi-Level Memory System
| Memory Type | Description | Storage |
|--------------|--------------|----------|
| **Long-term** | Docs, CRDs, Argo CD help JSONs | GitHub / Filesystem |
| **Medium-term** | Application YAMLs, thread data | Local JSON until thread ends |
| **Short-term** | Conversation context | LLM session memory |

- Used in **Argonaut AI Agents** (n8n workflows) to summarize or recall context.

### 3. Knowledge Graph / RAG System
- Extracts CRD schemas (e.g., `Application`, `Workflow`) into **Neo4j**.
- Builds semantic relationships between fields (`Spec → Source → RepoURL`, etc.).
- Uses vector stores (Qdrant / local embeddings) for contextual recall.

---

## ⚙️ Infrastructure & Components

### 1. Slack / Google Chat / Gmail Integrations
- Flask-based webhook receiver (`receive_chat_messages.py`).
- Posts responses using service-account-based scripts (`post_chat_messages.py`).
- Handles multi-threaded conversations (`thread_ts`, `channel`, `IO_type`).
- Avoids infinite loops (bot messages responding to themselves).

### 2. Command Lifecycle
```
User message → Naut CLI / Slack → Argonaut API
→ LLM (recommend command)
→ Argonaut executes (argocd/kubectl/helm)
→ Results logged + filtered → Response posted back
```

### 3. Privacy and Encryption
- A **privacy-filter microservice** encrypts JSON paths or URLs before LLM transmission and decrypts responses using symmetric keys.
- Supports `ENCRYPTION_ENABLED=true` flag and `SECRET_KEY_B64` from Kubernetes Secret.

### 4. Helm & Deployment Model
- Argonaut is packaged as a **Helm chart** with:
  - Flask API
  - Background processor (Gunicorn workers)
  - ConfigMaps for logic modules (e.g., `call_llm.py`, `claude_chat.py`)
  - Ingress with **Let’s Encrypt / cert-manager** TLS
- Deployable on AWS EKS, local k3s, or vcluster environments.

---

## 💬 User Interfaces

### 1. Naut CLI
- Lightweight bash client that manages:
  - Threads (`~/.naut/threads`)
  - State (`last_run.json`, `history.log`)
- Commands:  
  - `naut run "argocd app get app1"`
  - `naut recommend`
  - `naut wait`
  - `naut analyze`
- Communicates with Argonaut via webhook APIs.

### 2. Slack / ChatOps
- Executes commands via message prefix:  
  ```
  RUN argocd app sync myapp
  ```
- Responses include command results, YAML manifests, or summaries.

---

## 🔒 Security and Compliance
- Vault → Kubernetes secrets migration complete.
- Encrypted JSON filters for outbound LLM requests.
- Trivy/Aqua scans for Docker base images (Bookworm, Trixie).
- Focused on **enterprise compliance and on-prem deployments**.

---

## 🧠 Vision
Argonaut’s mission is to become the **“AI brain for GitOps”** —  
an extensible, multi-modal control plane that:
- Understands infrastructure state like a human expert.
- Can reason, explain, and act safely.
- Bridges the gap between **human DevOps intuition** and **automated AI orchestration**.
