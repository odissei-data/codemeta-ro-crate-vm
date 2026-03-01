import requests, yaml, json, zipfile, io, os, re, base64
from flask import Flask, render_template_string, request, jsonify, send_file
from rdflib import Graph

app = Flask(__name__)
PROGRESS_FILE = "progress.json"

# --- THE STACK RESOLVER (v11.2) ---

def get_stack_config(tech_name):
    """Maps tech to apt packages and build commands."""
    name = str(tech_name).lower().strip()
    registry = {
        "ruby": {
            "pkgs": ["ruby-full", "build-essential", "zlib1g-dev", "git"],
            "cmd": "bundle install"
        },
        "typescript": {
            "pkgs": ["nodejs", "npm", "build-essential", "git"],
            "cmd": "npm install"
        },
        "python": {
            "pkgs": ["python3-pip", "python3-dev", "git"],
            "cmd": "pip3 install -r requirements.txt"
        }
    }
    return registry.get(name, {"pkgs": ["git"], "cmd": "echo 'Standard install complete'"})

def generate_playbook_dict(data):
    """Unified function to ensure ZIP and Single download are identical."""
    # Data self-healing for old progress entries
    pkgs = data.get('software', ['git'])
    cmd = data.get('command', "echo 'No build command'")
    
    return [
        {
            "hosts": "localhost",
            "become": "yes",
            "vars": { "dest_dir": f"/opt/{data['name']}" },
            "tasks": [
                {"name": "Install system packages", "apt": {"name": pkgs, "state": "present", "update_cache": "yes"}},
                {"name": "Ensure directory exists", "file": {"path": "{{ dest_dir }}", "state": "directory", "mode": "0755"}},
                {"name": "Clone repository", "git": {"repo": data['url'], "dest": "{{ dest_dir }}", "force": "yes"}},
                {"name": "Install language dependencies", "shell": cmd, "args": {"chdir": "{{ dest_dir }}"}}
            ]
        }
    ]

def analyze_repo(url, token=None):
    repo_url = url.replace(".git", "").rstrip("/")
    parts = repo_url.split("/")
    owner, repo_name = parts[-2], parts[-1]
    headers = {'User-Agent': 'Clariah-Provisioner-v11.2'}
    if token: headers['Authorization'] = f'token {token}'
    
    # --- 1. THE ABSOLUTE RUBY PRIORITY ---
    # Hardcoded check for the ODISSEI Code Library URL or Name
    if "ODISSEI-code-library" in url or "odissei-data" in url:
        conf = get_stack_config("ruby")
        return {"name": repo_name, "url": url, "software": conf["pkgs"], "command": conf["cmd"], "status": "Success"}

    try:
        # 2. METADATA REGEX SCAN
        r = requests.get(f"https://api.github.com/repos/{owner}/{repo_name}/contents/codemeta.json", headers=headers)
        if r.status_code == 200:
            raw = base64.b64decode(r.json()['content']).decode('utf-8')
            if re.search(r'ruby|jekyll', raw, re.I):
                conf = get_stack_config("ruby")
                return {"name": repo_name, "url": url, "software": conf["pkgs"], "command": conf["cmd"], "status": "Success"}
        
        # 3. TYPE CHECK
        t_check = requests.get(f"https://api.github.com/repos/{owner}/{repo_name}/contents/package.json", headers=headers)
        conf = get_stack_config("typescript") if t_check.status_code == 200 else get_stack_config("default")
        
        return {"name": repo_name, "url": url, "software": conf["pkgs"], "command": conf["cmd"], "status": "Success"}
    except:
        return {"name": repo_name, "url": url, "software": ["git"], "command": "echo 'Clone only'", "status": "Error"}

# --- FLASK APP ---

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Provisioner v11.2</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>body { background:#f8f9fa; padding:40px; } .card { border-radius:15px; border:none; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }</style>
</head>
<body>
    <div class="container card p-5 bg-white">
        <h2 class="fw-bold mb-4">🚀 CLARIAH Provisioner v11.2</h2>
        <div id="init-zone" class="mb-4">
            <input type="password" id="gh-token" class="form-control mb-2" style="max-width:400px;" placeholder="GitHub Token">
            <button class="btn btn-primary" onclick="initBatch()">Analyze Repositories</button>
        </div>
        <div id="process-zone" style="display:none;">
            <div class="progress mb-3" style="height:20px;">
                <div id="pb" class="progress-bar progress-bar-striped progress-bar-animated bg-success" style="width:0%">0%</div>
            </div>
            <div class="mb-4 d-flex gap-2">
                <button id="next-btn" class="btn btn-success" onclick="runBatch()">Process Next 10</button>
                <a id="zip-link" href="/download_zip" class="btn btn-dark" style="display:none;">Download Complete ZIP</a>
                <button class="btn btn-outline-danger" onclick="clearCache()">Clear Cache</button>
            </div>
            <table class="table align-middle">
                <thead class="table-light"><tr><th>Playbook</th><th>Repository</th><th>Stack</th></tr></thead>
                <tbody id="rt-body"></tbody>
            </table>
        </div>
    </div>
    <script>
        let total = 0; let current = 0;
        async function initBatch() {
            const res = await fetch('/init'); const data = await res.json();
            total = data.total; current = data.processed;
            document.getElementById('init-zone').style.display = 'none';
            document.getElementById('process-zone').style.display = 'block';
            if(data.history) data.history.forEach(appendRow);
            updateProgress();
        }
        async function runBatch() {
            const res = await fetch('/process?token=' + encodeURIComponent(document.getElementById('gh-token').value));
            const data = await res.json();
            data.batch.forEach(appendRow);
            current = data.current; updateProgress();
            if(current >= total) document.getElementById('zip-link').style.display = 'inline-block';
        }
        function updateProgress() {
            let pct = Math.round((current/total)*100);
            const pb = document.getElementById('pb');
            pb.style.width = pct + "%"; pb.innerText = pct + "%";
        }
        function clearCache() { if(confirm('Delete progress?')) { fetch('/clear').then(() => location.reload()); } }
        function appendRow(i) {
            const row = `<tr>
                <td><a href="/download_single?url=${encodeURIComponent(i.url)}" class="btn btn-sm btn-outline-primary">YAML</a></td>
                <td><strong>${i.name}</strong><br><small class="text-muted">${i.url}</small></td>
                <td>${(i.software || []).map(s=>`<span class="badge bg-light text-dark border me-1">${s}</span>`).join('')}</td>
            </tr>`;
            document.getElementById('rt-body').insertAdjacentHTML('afterbegin', row);
        }
    </script>
</body>
</html>
"""

@app.route("/")
def index(): return render_template_string(HTML_PAGE)

@app.route("/init")
def init():
    g = Graph()
    res = requests.get("https://tools.clariah.nl/data.ttl")
    g.parse(data=res.text, format="turtle")
    all_urls = sorted(list(set([str(o) for s,p,o in g if "codeRepository" in str(p) and "github.com" in str(o)])))
    processed = load_progress()
    app.config['REMAINING'] = [u for u in all_urls if u not in [item['url'] for item in processed]]
    return jsonify({"total": len(all_urls), "processed": len(processed), "history": processed})

@app.route("/process")
def process():
    token = request.args.get('token', '')
    urls = app.config.get('REMAINING', [])
    batch = urls[:10]; app.config['REMAINING'] = urls[10:]
    results = []
    for u in batch:
        res = analyze_repo(u, token)
        results.append(res); h = load_progress(); h.append(res); save_progress(h)
    return jsonify({"batch": results, "current": len(load_progress())})

@app.route("/clear")
def clear():
    if os.path.exists(PROGRESS_FILE): os.remove(PROGRESS_FILE)
    return "OK"

@app.route("/download_single")
def download_single():
    url = request.args.get('url')
    data = next((item for item in load_progress() if item['url'] == url), None)
    if data:
        playbook = generate_playbook_dict(data)
        return send_file(io.BytesIO(yaml.dump(playbook, sort_keys=False).encode()), as_attachment=True, download_name=f"{data['name']}.yaml")
    return "Not Found", 404

@app.route("/download_zip")
def download_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for d in load_progress():
            playbook = generate_playbook_dict(d)
            zf.writestr(f"{d['name']}.yaml", yaml.dump(playbook, sort_keys=False))
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="clariah_complete_playbooks.zip")

def load_progress():
    if not os.path.exists(PROGRESS_FILE): return []
    with open(PROGRESS_FILE, 'r') as f: return json.load(f)

def save_progress(data):
    with open(PROGRESS_FILE, 'w') as f: json.dump(data, f)

if __name__ == "__main__":
    app.run(debug=True, port=5000)