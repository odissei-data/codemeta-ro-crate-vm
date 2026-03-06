import requests
import json
import getpass

def run_fuji_authenticated(target_doi):
    # --- CONFIGURATION ---
    # Ensure this is the /evaluate endpoint
    api_url = "http://localhost:1071/fuji/api/v1/evaluate"
    
    # Update these with your actual credentials
    # If you are at VU/NFDI, use your provided service account details
    username = "admin" 
    password = "admin"

    # Use a Session to persist headers and auth
    session = requests.Session()
    session.auth = (username, password)
    session.headers.update({
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    })

    payload = {
  "object_identifier": target_doi,
  "test_debug": True,
  "metadata_service_endpoint": "http://ws.pangaea.de/oai/provider",
  "metadata_service_type": "oai_pmh",
  "use_datacite": True,
  "use_github": False,
  "metric_version": "metrics_v0.8"
}

    try:
        print(f"📡 Authenticating as '{username}'...")
        response = session.post(api_url, json=payload, timeout=60)
        
        # This will catch the 401 and print a helpful message
        response.raise_for_status()
        
        data = response.json()
        print("\n✅ Access Granted! FAIR Evaluation Results:")
        print(f"Score: {data.get('summary', {}).get('fair_score_pct')}%")
        return data

    except requests.exceptions.HTTPError as err:
        if err.response.status_code == 401:
            print("❌ 401 Unauthorized: The username or password was rejected.")
            print("Tip: If you are running this locally, check your 'docker run' environment variables.")
        else:
            print(f"❌ HTTP Error: {err}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    doi = "https://zenodo.org/records/17457075"
    run_fuji_authenticated(doi)