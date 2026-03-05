import requests
import time
import os

def download_social_sciences_netherlands():
    # The portal-search URL is different from the standard API
    base_url = "https://services.openaire.eu/portal-search/researchProducts/fetchCsv"
    output_file = "openaire_social_sciences_netherlands.csv"
    
    # Range of years to cover the 200k results
    years = range(2026, 1989, -1)
    
    print(f"Starting extraction to {output_file}...")

    if os.path.exists(output_file):
        os.remove(output_file)

    first_write_ever = True

    try:
        with open(output_file, 'a', encoding='utf-8') as f:
            for year in years:
                print(f"\n--- Harvesting Year: {year} ---")
                page = 0  # This specific endpoint starts at 0
                has_more_in_year = True
                
                while has_more_in_year:
                    # Exact parameter names used by the portal-search service
                    params = {
                        'fosLabel': '("05 social sciences||social sciences")',
                        'relCommunityId': '("netherlands")',
                        'fromDateAccepted': f'{year}-01-01',
                        'toDateAccepted': f'{year}-12-31',
                        'size': '500', # Larger size is faster
                        'page': str(page)
                    }
                    
                    try:
                        response = requests.get(base_url, params=params, timeout=60)
                        
                        if response.status_code != 200:
                            print(f"Server returned {response.status_code}. Moving to next year.")
                            break

                        csv_text = response.text.strip()
                        lines = csv_text.splitlines()

                        # If response is empty or just a header on page > 0, we're done with this year
                        if not lines or (page > 0 and len(lines) <= 1):
                            has_more_in_year = False
                            continue

                        # Header Handling
                        if not first_write_ever:
                            lines.pop(0) # Strip header
                        
                        if lines:
                            f.write("\n".join(lines) + "\n")
                            first_write_ever = False
                            print(f"Year {year} | Page {page}: Received {len(lines)} rows.")

                        # If we received fewer than 'size' records, it's the end of the year
                        if len(lines) < 500:
                            has_more_in_year = False
                        else:
                            page += 1
                        
                        time.sleep(1) # Be gentle with the portal service

                    except Exception as e:
                        print(f"Request failed: {e}. Retrying...")
                        time.sleep(5)
                        continue

        print(f"\nDone! All data saved to {output_file}")

    except Exception as e:
        print(f"Critical error: {e}")

if __name__ == "__main__":
    download_social_sciences_netherlands()