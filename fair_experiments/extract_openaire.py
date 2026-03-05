import requests
import os

def extract_full_openaire_data():
    # Configuration
    base_url = 'https://services.openaire.eu/portal-search/researchProducts/fetchCsv'
    output_file = 'openaire_results.csv'
    
    # Parameters provided in your URL
    # OpenAIRE supports 'page' and 'size' for pagination
    params = {
        'fosLabel': '("05 social sciences||social sciences")',
        'relCommunityId': '("netherlands")',
        'size': 500  # Number of records per request (max stability)
    }

    current_page = 0
    has_more = True
    is_first_batch = True

    print(f"Starting extraction to {output_file}...")

    # Ensure we start with a fresh file
    if os.path.exists(output_file):
        os.remove(output_file)

    try:
        with open(output_file, 'a', encoding='utf-8') as f:
            while has_more:
                print(f"Fetching page {current_page}...")
                
                # Update parameters with current page index
                request_params = {**params, 'page': current_page}
                
                response = requests.get(base_url, params=request_params, timeout=30)
                response.raise_for_status()

                csv_text = response.text.strip()

                # Check if we received data
                if not csv_text:
                    has_more = False
                    break

                lines = csv_text.splitlines()

                # Logic to handle the CSV header
                if not is_first_batch:
                    # Remove the header line for all pages except the first
                    if len(lines) > 0:
                        lines.pop(0)
                
                if lines:
                    # Join lines back and write to file
                    f.write("\n".join(lines) + "\n")
                    
                    # If we received fewer records than the 'size' requested, we've hit the end
                    if len(lines) < params['size']:
                        has_more = False
                else:
                    has_more = False

                is_first_batch = False
                current_page += 1

                # Safety limit to prevent infinite loops (approx 100k records)
                if current_page > 200:
                    print("Safety limit reached. Stopping.")
                    break

        print(f"Successfully saved all results to {output_file}")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    extract_full_openaire_data()