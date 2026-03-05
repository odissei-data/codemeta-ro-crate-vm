import requests
import json
import csv
import time

def get_fuji_metrics(target_doi, session, api_url):
    """
    Evaluates a DOI and returns a dictionary of {metric_id: (name, earned, percent)}.
    """
    payload = {
        "object_identifier": target_doi,
        "test_debug": True,
        "use_datacite": True
    }
    try:
        response = session.post(api_url, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        
        metric_results = {}
        for metric in data.get('results', []):
            m_id = metric.get('metric_identifier')
            m_name = metric.get('metric_name', "")
            score_data = metric.get('score', {})
            
            earned = score_data.get('earned', 0)
            percent = score_data.get('score_percent', 0)
            
            # Store name, earned points, and the percentage for this specific metric
            metric_results[m_id] = (m_name, earned, percent)
            
        return metric_results
    except Exception as e:
        print(f"⚠️ Error evaluating {target_doi}: {e}")
        return None

if __name__ == "__main__":
    # --- CONFIGURATION ---
    API_URL = "http://localhost:1071/fuji/api/v1/evaluate"
    USERNAME = "admin"
    PASSWORD = "admin1234"
    CSV_OUTPUT_FILE = "fuji_21_datasets_percent_matrix.csv"

    datasets = [
        "https://doi.org/10.5281/zenodo.17457076",
        "https://hdl.handle.net/10622/OHM48J",
        "https://hdl.handle.net/10622/DTQKI6",
        "https://hdl.handle.net/10622/MMAYDK",
        "https://hdl.handle.net/10622/XMCZLZ",
        "https://github.com/globalise-huygens/nlp-event-lexical-approach",
        "https://hdl.handle.net/10622/LVOQTG",
        "https://hdl.handle.net/10622/5LRS03",
        "https://hdl.handle.net/10622/WYVERW",
        "https://hdl.handle.net/10622/XDI7DD",
        "https://hdl.handle.net/10622/DITM0Z",
        "https://github.com/StellaVerkijk/VarDial2024",
        "https://hdl.handle.net/10622/SOS0KC",
        "https://hdl.handle.net/10622/MDNVH5",
        "https://hdl.handle.net/10622/QJZKZ2",
        "https://hdl.handle.net/10622/75DURG",
        "https://hdl.handle.net/10622/LVXSBW",
        "https://hdl.handle.net/10622/YAWDOV",
        "https://hdl.handle.net/10622/JCTCJ2",
        "https://hdl.handle.net/10622/BHKMWE",
        "https://portal.odissei.nl/dataset.xhtml?persistentId=doi:10.34894/9XPECM"
    ]
    
    ds_labels = [f"DS{i+1}" for i in range(len(datasets))]
    session = requests.Session()
    session.auth = (USERNAME, PASSWORD)
    session.headers.update({'Content-Type': 'application/json', 'Accept': 'application/json'})

    results_map = {} 
    metric_id_to_name = {}
    all_metric_ids = []

    print(f"🚀 Processing 21 datasets. Extracting 'score_percent'...")

    for i, doi in enumerate(datasets):
        label = ds_labels[i]
        print(f"📡 [{i+1}/21] {label}...")
        metrics = get_fuji_metrics(doi, session, API_URL)
        
        if metrics:
            results_map[label] = metrics
            for m_id, (m_name, earned, percent) in metrics.items():
                if m_id not in all_metric_ids:
                    all_metric_ids.append(m_id)
                    metric_id_to_name[m_id] = m_name
        time.sleep(0.5)

    all_metric_ids.sort()

    # --- CSV GENERATION ---
    # We will save two values per cell (Points | Percent) to keep it in one table, 
    # or you can modify this to just save the percent.
    with open(CSV_OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        header = ["Metric ID", "Description"] + ds_labels
        writer.writerow(header)

        for m_id in all_metric_ids:
            # Row format: ID, Description, Score1, Score2...
            row = [m_id, metric_id_to_name.get(m_id, "")]
            for label in ds_labels:
                data = results_map.get(label, {}).get(m_id)
                if data:
                    # Formatting as "Points (Percent%)"
                    row.append(f"{data[1]} ({data[2]}%)")
                else:
                    row.append("0 (0%)")
            writer.writerow(row)

    print("\n✅ Done! Matrix saved with percentages to:", CSV_OUTPUT_FILE)