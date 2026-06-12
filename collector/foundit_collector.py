import os
import json
import time
from curl_cffi import requests
from datetime import datetime

def fetch_jobs(keyword: str = "ai engineer", max_pages=None):
    """
    Fetch jobs from Foundit for the given keyword.

    Args:
        keyword:   Search keyword, e.g. 'data scientist', 'ml engineer' (default: 'ai engineer')
        max_pages: Hard cap on pages to fetch. None = dynamic (auto-detect from total jobs, capped at 100).
    """
    url = "https://www.foundit.in/home/api/searchResultsPage"
    limit = 20
    params = {
        "start": 0,
        "limit": limit,
        "query": keyword,
        "queryDerived": "true",
        "countries": "India"
    }
    
    # We use a user-agent header to avoid being blocked by simple bot detection
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    
    all_jobs = []
    page = 1
    max_pages_to_fetch = 1000 if max_pages is None else max_pages
    total_jobs = 0
    
    session = requests.Session()
    
    # Visit homepage first to establish session and get cookies
    print("Initializing session on Foundit homepage...")
    try:
        session.get(
            "https://www.foundit.in/", 
            headers={"User-Agent": headers["User-Agent"]}, 
            impersonate="chrome124",
            timeout=15
        )
    except Exception as e:
        print(f"Warning: Failed to visit homepage to initialize session cookies: {e}")
        
    while page <= max_pages_to_fetch:
        start_idx = (page - 1) * limit
        print(f"Fetching Foundit jobs [{keyword!r}] - Page {page} of {max_pages_to_fetch if max_pages is not None else 'Dynamic'} (start index: {start_idx})...")
        params["start"] = start_idx
        
        # Retry logic with exponential backoff
        res_json = None
        for attempt in range(3):
            try:
                response = session.get(url, params=params, headers=headers, impersonate="chrome124", timeout=15)
                response.raise_for_status()
                res_json = response.json()
                break
            except Exception as req_err:
                if attempt == 2:
                    if page == 1:
                        print(f"Failed to fetch Page 1 jobs from Foundit: {req_err}")
                        raise req_err
                    else:
                        print(f"Warning: Failed to fetch Page {page} after 3 attempts due to: {req_err}")
                        res_json = None
                        break
                wait_time = 2 ** attempt
                print(f"Request failed: {req_err}. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                
        if res_json is None:
            print(f"Skipping page {page} due to failed requests. Returning previously fetched jobs.")
            break
            
        # Dynamic pages calculation on first page
        if page == 1 and max_pages is None:
            total_jobs = res_json.get("meta", {}).get("paging", {}).get("total", 0)
            calculated_pages = (total_jobs + limit - 1) // limit
            max_pages_to_fetch = min(calculated_pages, 100)  # cap at 100 pages
            print(f"Total jobs available: {total_jobs}. Dynamically fetching up to {max_pages_to_fetch} pages.")
        
        jobs = res_json.get("data", [])
        if not jobs:
            print(f"No more jobs found on Page {page}. Ending pagination.")
            break
            
        print(f"Successfully fetched {len(jobs)} jobs from Page {page}.")
        all_jobs.extend(jobs)
        
        if len(jobs) < limit:
            print("Retrieved fewer jobs than limit; assuming last page. Ending pagination.")
            break
            
        if page < max_pages_to_fetch:
            time.sleep(1.5)
            
        page += 1
                
    return {
        "data": all_jobs,
        "keyword": keyword,
        "collectedJobs": len(all_jobs),
        "totalJobsAvailable": total_jobs if total_jobs > 0 else len(all_jobs)
    }

def save_raw_data(data, keyword: str = "ai_engineer"):
    """
    Save raw API response to data/raw/<slug>_<date>.json.
    The filename is derived from the keyword so different searches
    don't overwrite each other.
    """
    print("Saving raw data...")

    date_str = datetime.now().strftime("%Y_%m_%d")

    # Derive slug from keyword: lowercase, spaces -> underscores
    # Use the keyword embedded in data if available, fallback to param
    kw = data.get("keyword", keyword)
    kw_slug = kw.lower().strip().replace(" ", "_").replace("/", "_")
    filename = f"foundit_{kw_slug}_{date_str}.json"

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    raw_dir = os.path.join(project_root, "data", "raw")
    os.makedirs(raw_dir, exist_ok=True)

    filepath = os.path.join(raw_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    print("Done")
    return filepath

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Foundit standalone collector")
    parser.add_argument("--keyword", default="ai engineer", help="Search keyword (default: 'ai engineer')")
    parser.add_argument("--max-pages", type=int, default=None, help="Max pages to fetch (default: dynamic)")
    args = parser.parse_args()

    try:
        data = fetch_jobs(keyword=args.keyword, max_pages=args.max_pages)
        
        jobs = []
        if isinstance(data, dict):
            # Try typical keys where job list might reside
            for key in ["jobResults", "results", "jobs", "data"]:
                if key in data and isinstance(data[key], list):
                    jobs = data[key]
                    break
            if not jobs and "model" in data and isinstance(data["model"], dict):
                model = data["model"]
                for key in ["jobResults", "results", "jobs"]:
                    if key in model and isinstance(model[key], list):
                        jobs = model[key]
                        break
        
        # Fallback: if jobs is still empty or not structured as expected, let's see if data itself is a list
        if not jobs and isinstance(data, list):
            jobs = data
            
        # If we couldn't find any list of jobs, print keys to help debug
        if not jobs:
            print(f"Warning: Could not automatically detect jobs list in the response. Keys in response: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
            
        num_jobs = len(jobs) if jobs else 0
        print(f"Found {num_jobs} jobs")
        
        # Step 2: Save raw JSON
        filepath = save_raw_data(data)
        
        # Step 3: Print summary
        print(f"\nSummary:")
        print(f"Jobs Found: {num_jobs}")
        
        if jobs:
            first_job = jobs[0]
            print("First Job:")
            print(first_job.get("title"))
            print(first_job.get("companyName"))
            print(first_job.get("locations"))
            print(first_job.get("skills"))
            print(first_job.get("minimumExperience"))
            print(first_job.get("maximumExperience"))
            print(first_job.get("postedAt"))
            
            # Save first job's keys to docs/foundit_schema.txt relative to project root
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(script_dir)
            docs_dir = os.path.join(project_root, "docs")
            os.makedirs(docs_dir, exist_ok=True)
            schema_path = os.path.join(docs_dir, "foundit_schema.txt")
            with open(schema_path, "w", encoding="utf-8") as f:
                # Write each key on a new line
                for key in sorted(first_job.keys()):
                    f.write(f"{key}\n")
            print(f"Saved job schema keys to {schema_path}")
        else:
            print("No jobs found in response to generate schema.")
            
    except Exception as e:
        print(f"An error occurred: {e}")
        # If it failed, let's try to print status/response if possible

if __name__ == "__main__":
    main()
