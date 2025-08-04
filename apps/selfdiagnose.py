# selfdiagnose.py
import os
import subprocess
import glob
from pathlib import Path
from summarize_text import summarize_text

def run_command(cmd):
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Error running '{cmd}': {e.stderr.strip()}"

def diagnose_system():
    report = []

    # Check ArgoCD version
    report.append("## ArgoCD Version")
    report.append(run_command("argocd version"))
    report.append("## ArgoCD context")
    report.append(run_command("argocd context"))
    #report.append("## ArgoCD repo list")
    # report.append(run_command("argocd repo list"))
    # report.append("## ArgoCD cluster list")
    # report.append(run_command("argocd cluster list"))

    # Check kubectl version for each kubeconfig
    kubeconfig_folder = Path.home() / ".kube/testing"
    kubeconfigs = list(kubeconfig_folder.glob("*"))
    report.append("\n## kubectl Versions for Each Kubeconfig")

    for kc in kubeconfigs:
        if kc.is_file():
            #cmd = f"kubectl version --short --kubeconfig {kc}"
            #print (kc)
            cmd = f"kubectl version --kubeconfig {kc}"
            #print (cmd)
            report.append(f"\n### {kc.name}")
            report.append(run_command(cmd))

    # Check git
    report.append("\n## Git Version")
    report.append(run_command("git --version"))

    report.append("\n## Git Remote Test")
    report.append(run_command("git ls-remote"))

    # Check GitHub CLI
    report.append("\n## GitHub CLI Version")
    report.append(run_command("gh --version"))

    report.append("\n## GitHub CLI Auth Status")
    report.append(run_command("gh auth status"))

    # Check yq
    report.append("\n## yq Version")
    report.append(run_command("yq --version"))


    # Check jq
    report.append("\n## jq Version")
    report.append(run_command("jq --version"))

    #print ("report")
    #return "\n".join(report)
    report="\n".join(report)
    summary_of_report=summarize_text(report,"Only list the commands, without the subcommands, without explanation . Response should start with The following commands can be used")
    return summary_of_report

if __name__ == "__main__":
    print(diagnose_system())