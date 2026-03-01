import csv, requests, yaml, json, zipfile, io, os, time, math, re, base64
from flask import Flask, render_template_string, request, jsonify, send_file, redirect, url_for
from rdflib import Graph

app = Flask(__name__)
PROGRESS_FILE = "progress.json"

# --- CORE UTILITIES ---

def extract_from_codemeta(content):
    found = []
    try:
        data = json.loads(content)
        reqs = data.get("softwareRequirements", [])
        if isinstance(reqs, list):
            for r in reqs:
                if isinstance(r, str): found.append(r)
                elif isinstance(r, dict): found.append(r.get("name", ""))
        elif isinstance(reqs, str): found.append(reqs)
    except:
        matches = re.findall(r'"softwareRequirements"\s*:\s*\[([^\]]+)\]', content)
        for m in matches:
            items = re.findall(r'"([^"]+)"', m)
            found.extend(items)
    return [f.strip() for f in found if f]

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except: return []
    return []

def save_progress(data):
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def generate_ansible_dict(name, software):
    """Standardized Ansible playbook structure."""
    return [{
        "hosts": "localhost",
        "become": True,
        "tasks": [
            {"name": "Update Apt Cache", "apt": {"update_cache": True}},
            {"name": f"Install Dependencies for {name}", "apt": {"name": software, "state": "present"}}
        ]
    }]

def analyze_repo(url, token=None):
    repo_url = url.replace(".git", "").rstrip("/")
    parts = repo_url.split("/")
    if len(parts) < 2: return {"name": url, "url": url, "status": "Failed", "error": "Invalid URL"}
    
    owner, repo_name = parts[-2], parts[-1]
    headers = {'User-Agent': 'Clariah-Provisioner-v8.7'}
    if token and token.strip():
        headers['Authorization'] = f'token {token.strip()}'
    
    try:
        limit_res = requests.get("https://api.github.com/rate_limit", headers=headers, timeout=5)
        rate = limit_res.json().get('resources', {}).get('core', {})
        if rate.get('remaining', 0) < 5:
            return {"name": repo_name, "url": url, "status": "Failed", "error": "Rate Limit Hit"}

        tree_url = f"https://api.github.com/repos/{owner}/{repo_name}/git/trees/main?recursive=1"
        r = requests.get(tree_url, timeout=10, headers=headers)
        if r.status_code != 200:
            r = requests.get(tree_url.replace("main", "master"), timeout=10, headers=headers)
        
        if r.status_code == 200:
            tree_data = r.json().get("tree", [])
            tree_paths = {f.get("path").lower(): f.get("url") for f in tree_data}
            found_sw, langs = ["git"], []
            mapping = {
                ".java": (["openjdk-17-jdk", "maven"], "Java"),
                "pom.xml": (["openjdk-17-jdk", "maven"], "Java"),
                ".py": (["python3-pip"], "Python"),
                "requirements.txt": (["python3-pip"], "Python"),
                ".pl": (["swi-prolog"], "Prolog"),
                "package.json": (["nodejs", "npm"], "Node")
            }
            for path in tree_paths:
                for key, (pkgs, lang) in mapping.items():
                    if key in path:
                        found_sw.extend(pkgs)
                        if lang not in langs: langs.append(lang)

            if "codemeta.json" in tree_paths:
                blob_res = requests.get(tree_paths["codemeta.json"], headers=headers)
                if blob_res.status_code == 200:
                    raw_content = base64.b64decode(blob_res.json()['content']).decode('utf-8')
                    found_sw.extend(extract_from_codemeta(raw_content))

            return {
                "name": repo_name, "url": url, "software": sorted(list(set(found_sw))),
                "langs": sorted(list(set(langs))), "status": "Success", "error": ""
            }
        return {"name": repo_name, "url": url, "status": "Failed", "error": f"GH {r.status_code}"}
    except Exception as e:
        return {"name": repo_name, "url": url, "status": "Failed", "error": str(e)}

# --- UI TEMPLATE ---

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>CLARIAH Provisioner v8.7</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: #f8f9fa; padding: 40px; }
        .card { border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); border: none; }
        .log-box { background: #212529; color: #00ff00; height: 160px; overflow-y: scroll; padding: 15px; font-family: monospace; font-size: 12px; border-radius: 8px; }
        .btn-dl { font-size: 0.75rem; padding: 2px 8px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card p-5">
            <h2 class="fw-bold mb-4">?? CLARIAH DevOps Hub <small class="text-muted">v8.7</small></h2>
            
            <div id="init-zone" class="mb-4">
                <input type="password" id="gh-token" class="form-control mb-2" style="max-width: 400px;" placeholder="GitHub Token (Optional)">
                <button class="btn btn-primary btn-lg" onclick="initBatch()">Initialize</button>
            </div>

            <div id="process-zone" style="display:none;">
                <div class="progress mb-3" style="height: 20px;"><div id="pb" class="progress-bar bg-success" style="width: 0%"></div></div>
                <div class="log-box mb-4" id="log">Ready...</div>
                <div class="d-flex gap-2 mb-4">
                    <button id="next-btn" class="btn btn-success" onclick="runBatch()">Process Next 10</button>
                    <button id="bulk-retry-btn" class="btn btn-warning" style="display:none;" onclick="bulkRetry()">Retry All Failed</button>
                    <a id="zip-link" href="/download/zip" class="btn btn-dark" style="display:none;">Download Full ZIP</a>
                </div>
            </div>

            <div id="report-zone" class="mt-4" style="display:none;">
                <table class="table table-hover align-middle border">
                    <thead class="table-light"><tr><th>Script</th><th>Repo</th><th>Status</th><th>Detected Tech</th></tr></thead>
                    <tbody id="rt-body"></tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        let total = 0; let current = 0;

        async function initBatch() {
            const res = await fetch('/init');
            const data = await res.json();
            total = data.total; current = data.processed;
            document.getElementById('init-zone').style.display = 'none';
            document.getElementById('process-zone').style.display = 'block';
            updateProgressBar();
            if(data.history) data.history.forEach(appendRow);
            if(data.history && data.history.some(i => i.status === 'Failed')) document.getElementById('bulk-retry-btn').style.display = 'inline-block';
        }

        async function runBatch() {
            const btn = document.getElementById('next-btn');
            const token = document.getElementById('gh-token').value;
            btn.disabled = true;
            const res = await fetch('/process?token=' + encodeURIComponent(token));
            const data = await res.json();
            current = data.current;
            updateProgressBar();
            data.batch.forEach(item => appendRow(item));
            btn.disabled = false;
            if(current >= total) { btn.style.display='none'; document.getElementById('zip-link').style.display='inline-block'; }
        }

        async function bulkRetry() {
            const token = document.getElementById('gh-token').value;
            await fetch('/retry_all?token=' + encodeURIComponent(token));
            location.reload();
        }

        function updateProgressBar() { document.getElementById('pb').style.width = (current/total*100) + "%"; }
        
        function renderRowHtml(i) {
            const id = "row-" + btoa(i.url).replace(/=/g, "");
            const dlBtn = i.status === 'Success' ? 
                `<a href="/download_single?url=${encodeURIComponent(i.url)}" class="btn btn-outline-primary btn-dl">YAML</a>` : 
                `<button class="btn btn-outline-secondary btn-dl" disabled>N/A</button>`;
            return `<tr id="${id}">
                <td>${dlBtn}</td>
                <td><strong>${i.name}</strong></td>
                <td><span class="badge ${i.status==='Success'?'bg-success':'bg-danger'}">${i.status}</span></td>
                <td><small>${(i.software || []).join(', ')}</small></td>
            </tr>`;
        }

        function appendRow(i) {
            document.getElementById('report-zone').style.display = 'block';
            document.getElementById('rt-body').insertAdjacentHTML('afterbegin', renderRowHtml(i));
        }
    </script>
</body>
</html>
"""

# --- ROUTES ---

@app.route("/")
def index(): return render_template_string(HTML_PAGE)

@app.route("/init")
def init():
    g = Graph()
    res = requests.get("https://tools.clariah.nl/data.ttl")
    g.parse(data=res.text, format="turtle")
    all_urls = sorted(list(set([str(o) for s,p,o in g if "codeRepository" in str(p) and "github.com" in str(o)])))
    history = load_progress()
    processed_urls = [item.get('url') for item in history if isinstance(item, dict) and 'url' in item]
    app.config['REMAINING_URLS'] = [u for u in all_urls if u not in processed_urls]
    return jsonify({"total": len(all_urls), "processed": len(history), "history": history})

@app.route("/process")
def process():
    token = request.args.get('token', '')
    urls_to_do = app.config.get('REMAINING_URLS', [])
    batch = urls_to_do[:10]
    app.config['REMAINING_URLS'] = urls_to_do[10:]
    results = []
    for url in batch:
        data = analyze_repo(url, token); results.append(data)
        h = load_progress(); h.append(data); save_progress(h)
    return jsonify({"current": len(load_progress()), "batch": results})

@app.route("/download_single")
def download_single():
    url = request.args.get('url')
    history = load_progress()
    entry = next((item for item in history if item.get('url') == url), None)
    if entry and entry.get('status') == 'Success':
        playbook = generate_ansible_dict(entry['name'], entry['software'])
        output = yaml.dump(playbook, default_flow_style=False, sort_keys=False)
        return send_file(io.BytesIO(output.encode()), mimetype="text/yaml", as_attachment=True, download_name=f"deploy_{entry['name']}.yaml")
    return "Not Found", 404

@app.route("/download/zip")
def download_zip():
    history = load_progress()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "a", zipfile.ZIP_DEFLATED) as zf:
        for d in history:
            if d.get("status") == "Success":
                playbook = generate_ansible_dict(d['name'], d['software'])
                zf.writestr(f"deploy_{d['name']}.yaml", yaml.dump(playbook, default_flow_style=False))
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name="clariah_all_playbooks.zip")

@app.route("/retry_all")
def retry_all():
    token = request.args.get('token', ''); history = load_progress()
    for idx, item in enumerate(history):
        if item.get("status") == "Failed":
            history[idx] = analyze_repo(item['url'], token); save_progress(history); time.sleep(1)
    return jsonify({"status": "done"})

@app.route("/clear")
def clear():
    if os.path.exists(PROGRESS_FILE): os.remove(PROGRESS_FILE)
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run(debug=True, port=5000)