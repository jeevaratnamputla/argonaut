FROM python:3.11.3-slim

# Install curl, jq, yq, gh, git, kubectl, and argocd CLI
#RUN snap install yq
#RUN apt update && apt install gh -y
RUN apt-get update && apt-get install -y git curl jq && \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | tee /usr/share/keyrings/githubcli-archive-keyring.gpg > /dev/null && \
    echo "deb [signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null && \
    apt-get update && apt-get install -y gh
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && \
    install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
RUN curl -sSL -o /usr/local/bin/argocd https://github.com/argoproj/argo-cd/releases/download/v2.13.6/argocd-linux-amd64 && \
    chmod +x /usr/local/bin/argocd
RUN curl -sSL -o /usr/local/bin/yq https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 && \
    chmod +x /usr/local/bin/yq



# Set the working directory in the container
WORKDIR apps/ /app

# Copy the requirements.txt file into the container
COPY requirements.txt .

# Install the dependencies specified in requirements.txt
RUN pip install -r requirements.txt


# Expose the port that the application will run on
EXPOSE 5000

# Copy the rest of the application code into the container
#COPY . .

# Run the command to start the application when the container launches
CMD ["python", "apps/flask_runner.py"]
