import requests
import json
import csv

def run_fuji_authenticated(target_doi, session, api_url):
    """
    Evaluates a DOI and extracts total earned points from the results list.
    """
    payload = {
        "object_identifier": target_doi,
        "test_debug": True,
        "use_datacite": True
    }

    try:
        response = session.post(api_url, json=payload, timeout=90)
        response.raise_for_status()
        data = response.json()
        
        # 1. Get the general summary
        summary = data.get('summary', {})
        
        # 2. Calculate "score_earned" by summing up all individual metric scores
        # F-UJI returns a list of 'results', each with a 'score' -> 'earned'
        total_earned = 0
        metrics_list = data.get('results', [])
        for metric in metrics_list:
            earned = metric.get('score', {}).get('earned', 0)
            total_earned += earned

        return {
            "identifier": target_doi,
            "fair_level": summary.get('fair_level'),
            "fair_score_pct": summary.get('fair_score_pct'),
            "total_score_earned": total_earned,
            "status": "Success"
        }
    except Exception as e:
        return {
            "identifier": target_doi,
            "fair_level": "N/A",
            "fair_score_pct": 0,
            "total_score_earned": 0,
            "status": f"Error: {str(e)}"
        }

if __name__ == "__main__":
    # --- CONFIGURATION ---
    API_URL = "http://localhost:1071/fuji/api/v1/evaluate"
    USERNAME = "admin"
    PASSWORD = "admin1234"
    CSV_FILE = "fuji_earned_scores.csv"

    datasets = [
        "https://zenodo.org/records/17457075",
        "https://doi.org/10.1594/PANGAEA.902845",
        "https://doi.org/10.6084/m9.figshare.14917407.v1"
    ]

    # Initialize Session
    session = requests.Session()
    session.auth = (USERNAME, PASSWORD)
    session.headers.update({'Content-Type': 'application/json', 'Accept': 'application/json'})

    results_list = []

    print(f"🚀 Starting evaluation and extracting 'score_earned'...")
    print("-" * 60)

    for doi in datasets:
        row = run_fuji_authenticated(doi, session, API_URL)
        results_list.append(row)
        
        # Immediate console print for each dataset
        if row['status'] == "Success":
            print(f"✅ {doi}")
            print(f"   Score Earned: {row['total_score_earned']} points ({row['fair_score_pct']}%)")
        else:
            print(f"❌ {doi} - {row['status']}")

    # --- CSV EXPORT ---
    fieldnames = ["identifier", "fair_level", "fair_score_pct", "total_score_earned", "status"]

    with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results_list)

    print("-" * 60)
    print(f"Done! Results written to {CSV_FILE}")