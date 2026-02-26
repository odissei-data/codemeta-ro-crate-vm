import requests
import yaml
import json
import subprocess
import os

# 

def fetch_raw(repo_url, filename):
    base = repo_url.replace(".git", "").replace("github.com", "raw.githubusercontent.com").rstrip("/")
    for branch in ["main", "master", "develop"]:
        try:
            r = requests.get(f"{base}/{branch}/{filename}", timeout=5)
            if r.status_code == 200: return r.text
        except: continue
    return None

def parse_repo(repo_url):
    results = {"system": set(), "pip": False, "maven": False}
    cm = fetch_raw(repo_url, "codemeta.json")
    if cm:
        try:
            data = json.loads(cm)
            for field in ["programmingLanguage", "softwareRequirements"]:
                items = data.get(field, [])
                results["system"].update(items if isinstance(items, list) else [items])
        except: pass

    if fetch_raw(repo_url, "pom.xml"):
        results["maven"] = True
        results["system"].update(["maven", "openjdk-17-jdk"])
    
    if fetch_raw(repo_url, "requirements.txt"):
        results["pip"] = True
    return results

def provision_vm(repo_url):
    vm_name = "build-box"
    repo_name = repo_url.split("/")[-1].replace(".git", "")
    deps = parse_repo(repo_url)

    # 1. Generate Playbook (Simplified: removed Ansible from its own tasks)
    tasks = [
        {"name": "Update apt", "apt": {"update_cache": "yes"}},
        {"name": "Clone Repo", "git": {"repo": repo_url, "dest": f"/home/ubuntu/{repo_name}"}}
    ]
    if deps["system"]:
        tasks.append({"name": "System Deps", "package": {"name": list(deps["system"]), "state": "present"}, "ignore_errors": True})
    if deps["pip"]:
        tasks.append({"name": "Pip Install", "pip": {"requirements": f"/home/ubuntu/{repo_name}/requirements.txt"}})
    if deps["maven"]:
        tasks.append({"name": "Maven Build", "command": "mvn clean install", "args": {"chdir": f"/home/ubuntu/{repo_name}"}})

    with open("deploy.yml", "w") as f:
        yaml.dump([{"hosts": "localhost", "become": True, "tasks": tasks}], f)

    # 2. Multipass Orchestration
    print(f"--- Cleaning up existing '{vm_name}' ---")
    subprocess.run(["multipass", "delete", vm_name, "--purge"], capture_output=True)

    print(f"--- Launching VM (2GB RAM) ---")
    subprocess.run(["multipass", "launch", "--name", vm_name, "--mem", "2G", "22.04"], check=True)

    # BOOTSTRAP STEP: Manual install of Ansible to ensure it's found
    print(f"--- Bootstrapping Ansible inside VM ---")
    subprocess.run(["multipass", "exec", vm_name, "--", "sudo", "apt-get", "update"], check=True)
    subprocess.run(["multipass", "exec", vm_name, "--", "sudo", "apt-get", "install", "-y", "ansible"], check=True)

    print(f"--- Transferring and Running Playbook ---")
    subprocess.run(["multipass", "transfer", "deploy.yml", f"{vm_name}:/home/ubuntu/playbook.yml"], check=True)
    
    # Using full path /usr/bin/ansible-playbook to avoid "command not found"
    subprocess.run([
        "multipass", "exec", vm_name, "--", 
        "sudo", "/usr/bin/ansible-playbook", "/home/ubuntu/playbook.yml", "-c", "local"
    ], check=True)

    print(f"\n🚀 Success! Opening shell in /home/ubuntu/{repo_name}...")
    os.execvp("multipass", ["multipass", "shell", vm_name])

if __name__ == "__main__":
    REPO_URL = "https://github.com/odissei-data/odissei-kg"
    provision_vm(REPO_URL)