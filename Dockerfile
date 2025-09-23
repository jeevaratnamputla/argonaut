FROM golang:1.20.3-slim-bookworm AS builder
FROM python:3.11.9-slim-bookworm

# Install dependencies and cve's
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      libexpat1 \
      libkrb5-3 \
      libgssapi-krb5-2 \
      libk5crypto3 \
      libkrb5support0 \
      krb5-user \
      curl \
      git \
      jq \
      gnupg \
      unzip \
      && apt-get install -y --only-upgrade libexpat1 \
      && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | tee /usr/share/keyrings/githubcli-archive-keyring.gpg > /dev/null && \
    echo "deb [signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] \
      https://cli.github.com/packages stable main" \
      | tee /etc/apt/sources.list.d/github-cli.list > /dev/null && \
    apt-get update && apt-get install -y gh && \
    rm -rf /var/lib/apt/lists/*
    
# Install kubectl
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && \
    install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl && \
    rm kubectl

# Install Argo CD CLI
RUN curl -sSL -o /usr/local/bin/argocd https://github.com/argoproj/argo-cd/releases/download/v2.13.6/argocd-linux-amd64 && \
    chmod +x /usr/local/bin/argocd

# Install yq
RUN curl -sSL -o /usr/local/bin/yq https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 && \
    chmod +x /usr/local/bin/yq


RUN curl -sSL -o /usr/local/bin/spin https://storage.googleapis.com/spinnaker-artifacts/spin/$(curl -s https://storage.googleapis.com/spinnaker-artifacts/spin/latest)/linux/amd64/spin && \
 chmod +x /usr/local/bin/spin


# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY apps/*.py /app

# Expose port
EXPOSE 5000

# Run the application
CMD ["python", "flask_runner.py"]

