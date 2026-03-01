import requests
import csv
import time

# API Endpoint (based on the f-uji.net service)
API_URL = "https://www.f-uji.net/inc_result.php"

# List of Zenodo URLs to evaluate
pids = [
    "https://zenodo.org/records/17457075",
    "https://zenodo.org/records/13860149",
    "https://zenodo.org/records/18246267"
]

def evaluate_pid(pid):
    params = {
        "pid": pid,
        "service_url": "",
        "service_type": "oai_pmh",
        "use_datacite": "true",
        "enable_cache": "false",
        "metric_id": "metrics_v0.8"
    }
    
    print(f"Evaluating: {pid}...")
    try:
        # We use a GET request as per the structure of the URL provided
        response = requests.get(API_URL, params=params, timeout=60)
        
        # F-UJI usually returns HTML/Text for the browser view or JSON for data.
        # If the endpoint is inc_result.php, it often returns a summary.
        # We attempt to parse basic results. 
        # Note: If this is the public web-tool, the output is often formatted for display.
        return {
            "URL": pid,
            "Status Code": response.status_code,
            "Success": response.ok,
            "Response Length": len(response.text)
        }
    except Exception as e:
        return {"URL": pid, "Error": str(e)}

def save_to_csv(results, filename="fair_metrics_results.csv"):
    if not results:
        return
    
    keys = results[0].keys()
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        dict_writer = csv.DictWriter(f, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(results)
    print(f"Results saved to {filename}")

if __name__ == "__main__":
    all_results = []
    for pid in pids:
        res = evaluate_pid(pid)
        all_results.append(res)
        # Adding a small sleep to be respectful to the server
        time.sleep(2)
    
    save_to_csv(all_results)