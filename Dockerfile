#FROM python:3.11.9-slim-bookworm
FROM python:3.11-slim-trixie


# Install dependencies
RUN apt-get update && apt-get upgrade -y &&\
    apt-get install -y curl git jq gnupg unzip && \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | tee /usr/share/keyrings/githubcli-archive-keyring.gpg > /dev/null && \
    echo "deb [signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null && \
    apt-get update && \
    apt-get install -y gh
# fix vulnerability CVE-2024-45491
RUN set -eux; \
    apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends libexpat1; \
    rm -rf /var/lib/apt/lists/*

# Install kubectl
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && \
    install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl && \
    rm kubectl


# Install Argo CD CLI
#RUN curl -sSL -o /usr/local/bin/argocd https://github.com/argoproj/argo-cd/releases/download/v2.13.6/argocd-linux-amd64 && \
#    chmod +x /usr/local/bin/argocd
# Fixed for CVE-2025-47933
ARG ARGOCD_VERSION=v2.13.9
RUN set -eux; \
  curl -fSLo /usr/local/bin/argocd \
    "https://github.com/argoproj/argo-cd/releases/download/${ARGOCD_VERSION}/argocd-linux-amd64" && \
  chmod +x /usr/local/bin/argocd && \
  /usr/local/bin/argocd version --client


# Install yq
RUN curl -sSL -o /usr/local/bin/yq https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 && \
    chmod +x /usr/local/bin/yq


#RUN curl -sSL -o /usr/local/bin/spin https://storage.googleapis.com/spinnaker-artifacts/spin/$(curl -s https://storage.googleapis.com/spinnaker-artifacts/spin/latest)/linux/amd64/spin && \
# chmod +x /usr/local/bin/spin

RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
RUN unzip awscliv2.zip

RUN ./aws/install
RUN ln -s /usr/local/bin/aws /usr/bin/


# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY apps/*.py /app

# Expose port
EXPOSE 5000

# Create a non-root user and switch to it
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

# Run the application
CMD ["python", "flask_runner.py"]

