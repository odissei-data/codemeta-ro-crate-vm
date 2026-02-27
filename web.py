from flask import Flask, render_template_string, request
import requests
import yaml
import json
import math
import multiprocessing

app = Flask(__name__)

# --- CORE LOGIC (Extracted from our previous iterations) ---

def get_repo_metrics(repo_url):
    parts = repo_url.replace(".git", "").rstrip("/").split("/")
    owner, repo = parts[-2], parts[-1]
    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    try:
        r = requests.get(api_url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            size_gb = data.get("size", 0) / (1024 * 1024)
            disk = math.ceil(8 + (size_gb * 4) + 5)
            host_cpus = multiprocessing.cpu_count()
            cpus = min(host_cpus, max(2, 2 + int(size_gb * 2)))
            return max(15, disk), cpus
    except: pass
    return 20, 2

def fetch_raw(repo_url, filename):
    base = repo_url.replace(".git", "").replace("github.com", "raw.githubusercontent.com").rstrip("/")
    for branch in ["main", "master", "develop"]:
        try:
            r = requests.get(f"{base}/{branch}/{filename}", timeout=5)
            if r.status_code == 200: return r.text
        except: continue
    return None

def scan_repo_files(repo_url):
    parts = repo_url.replace(".git", "").rstrip("/").split("/")
    owner, repo = parts[-2], parts[-1]
    api_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/main?recursive=1"
    detected = set()
    try:
        r = requests.get(api_url, timeout=5)
        if r.status_code != 200:
            r = requests.get(api_url.replace("main", "master"), timeout=5)
        if r.status_code == 200:
            tree = r.json().get("tree", [])
            for file in tree:
                path = file.get("path", "").lower()
                if path.endswith(".java"): detected.add("java")
                if path.endswith(".pl") or path.endswith(".pro"): detected.add("prolog")
                if "pom.xml" in path: detected.add("java")
                if "package.json" in path: detected.add("node")
    except: pass
    return detected

def generate_ansible_content(repo_url):
    mapping = {
        "java": ["openjdk-17-jdk", "maven", "default-jre"],
        "prolog": ["swi-prolog", "swi-prolog-nox"],
        "python": ["python3", "python3-pip"],
        "node": ["nodejs", "npm"],
        "javascript": ["nodejs", "npm"],
        "git": ["git"]
    }
    
    found_software = set()
    
    # 1. CodeMeta Parsing
    cm_text = fetch_raw(repo_url, "codemeta.json")
    if cm_text:
        try:
            data = json.loads(cm_text)
            for field in ["programmingLanguage", "softwareRequirements"]:
                val = data.get(field, [])
                items = val if isinstance(val, list) else [val]
                for item in items:
                    name = item.get("name", str(item)) if isinstance(item, dict) else str(item)
                    name_clean = name.lower()
                    if name_clean in mapping: found_software.update(mapping[name_clean])
                    else: found_software.add(name_clean)
        except: pass

    # 2. File Scan Parsing
    languages = scan_repo_files(repo_url)
    for lang in languages:
        if lang in mapping: found_software.update(mapping[lang])

    # 3. Hardware Metrics
    disk_size, cpu_count = get_repo_metrics(repo_url)
    ram_gb = 4 if ("java" in languages or "node" in languages) else 2
    repo_name = repo_url.split("/")[-1].replace(".git", "")

    # 4. Build Playbook Structure
    playbook = [{
        "hosts": "localhost",
        "become": True,
        "vars": {
            "infra_disk": f"{disk_size}GB",
            "infra_mem": f"{ram_gb}GB",
            "infra_cpu": cpu_count
        },
        "tasks": [
            {"name": "Update system cache", "apt": {"update_cache": "yes"}},
            {"name": "Install git", "package": {"name": "git", "state": "present"}}
        ]
    }]

    for sw in sorted(list(found_software)):
        playbook[0]["tasks"].append({
            "name": f"Ensure system software is installed: {sw}",
            "package": {"name": sw, "state": "present"},
            "ignore_errors": True
        })

    playbook[0]["tasks"].append({"name": f"Clone {repo_name}", "git": {"repo": repo_url, "dest": f"/home/ubuntu/{repo_name}"}})

    yaml_header = f"# Specs: CPU: {cpu_count}, RAM: {ram_gb}G, Disk: {disk_size}G\n"
    return yaml_header + yaml.dump(playbook, sort_keys=False)

# --- WEB INTERFACE TEMPLATE ---

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Ansible Deploy Generator</title>
    <style>
        body { font-family: sans-serif; margin: 40px; background: #f4f7f6; }
        .container { max-width: 800px; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        input[type="text"] { width: 80%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; }
        button { padding: 10px 20px; background: #28a745; color: white; border: none; border-radius: 4px; cursor: pointer; }
        pre { background: #272822; color: #f8f8f2; padding: 15px; border-radius: 5px; overflow-x: auto; white-space: pre-wrap; }
        h2 { color: #333; }
    </style>
</head>
<body>
    <div class="container">
        <h2>GitHub to Ansible Generator</h2>
        <form method="POST">
            <input type="text" name="repo_url" placeholder="https://github.com/user/repo" required>
            <button type="submit">Generate YAML</button>
        </form>

        {% if yaml_content %}
        <h3>Generated deploy.yml:</h3>
        <pre>{{ yaml_content }}</pre>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    yaml_content = None
    if request.method == "POST":
        repo_url = request.form.get("repo_url")
        if repo_url:
            yaml_content = generate_ansible_content(repo_url)
    return render_template_string(HTML_TEMPLATE, yaml_content=yaml_content)

if __name__ == "__main__":
    app.run(debug=True, port=5000)