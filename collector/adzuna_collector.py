import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv
import requests

load_dotenv()

def fetch_jobs(keyword: str = "ai engineer", location: str = "", experience_level: str = "", page_limit: int = None):
    """
    Fetch jobs from Adzuna India API for the given query parameters.
    
    Args:
        keyword:          Search keywords (e.g. 'ai engineer', 'data scientist')
        location:         Search city/region (e.g. 'bangalore', 'mumbai')
        experience_level: Experience band or min salary proxy
        page_limit:       Max pages to fetch (default: None, which fetches up to 10 pages)
    """
    app_id = os.getenv("ADZUNA_APP_ID", "").strip()
    app_key = os.getenv("ADZUNA_APP_KEY", "").strip()
    
    if not app_id or not app_key:
        print("[Warning] Adzuna API credentials (ADZUNA_APP_ID/ADZUNA_APP_KEY) are not set in .env. Skipping Adzuna collection.")
        return {
            "data": [],
            "keyword": keyword,
            "collectedJobs": 0,
            "totalJobsAvailable": 0
        }
        
    limit = 20
    page = 1
    max_pages_to_fetch = 10 if page_limit is None else page_limit
    all_jobs = []
    total_jobs = 0
    
    # Map experience level to salary min proxy (Adzuna lacks native experience filters)
    salary_min = None
    if experience_level:
        exp_lower = experience_level.lower()
        if "fresher" in exp_lower or "0" in exp_lower:
            salary_min = 300000
        elif "mid" in exp_lower or "junior" in exp_lower or "3" in exp_lower:
            salary_min = 600000
        elif "senior" in exp_lower or "6" in exp_lower:
            salary_min = 1200000
        elif "lead" in exp_lower or "10" in exp_lower:
            salary_min = 2000000
            
    session = requests.Session()
    
    while page <= max_pages_to_fetch:
        print(f"Fetching Adzuna jobs [{keyword!r}] - Page {page} of {max_pages_to_fetch}...")
        
        # Build query parameters
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": limit,
            "what": keyword
        }
        if location:
            params["where"] = location
        if salary_min:
            params["salary_min"] = salary_min
            
        url = f"https://api.adzuna.com/v1/api/jobs/in/search/{page}"
        
        res_json = None
        for attempt in range(3):
            try:
                response = session.get(url, params=params, timeout=15)
                response.raise_for_status()
                res_json = response.json()
                break
            except Exception as req_err:
                if attempt == 2:
                    print(f"[Warning] Failed to fetch Adzuna page {page} after 3 attempts: {req_err}")
                    break
                wait_time = 2 ** attempt
                print(f"Adzuna request failed: {req_err}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                
        if res_json is None:
            break
            
        if page == 1:
            total_jobs = res_json.get("count", 0)
            print(f"Total Adzuna jobs available: {total_jobs}")
            
        results = res_json.get("results", [])
        if not results:
            print(f"No more jobs found on Page {page}. Ending Adzuna pagination.")
            break
            
        print(f"Successfully fetched {len(results)} jobs from Adzuna Page {page}.")
        all_jobs.extend(results)
        
        if len(results) < limit:
            break
            
        # Adzuna free tier has rate limits (25-50 calls/min). Add small sleep.
        time.sleep(3.0)
        page += 1
        
    return {
        "data": all_jobs,
        "keyword": keyword,
        "collectedJobs": len(all_jobs),
        "totalJobsAvailable": total_jobs if total_jobs > 0 else len(all_jobs)
    }

def save_raw_data(data, keyword: str = "ai_engineer"):
    """
    Save raw API response to data/raw/adzuna_<slug>_<date>.json.
    """
    print("Saving Adzuna raw data...")
    date_str = datetime.now().strftime("%Y_%m_%d")
    kw = data.get("keyword", keyword)
    kw_slug = kw.lower().strip().replace(" ", "_").replace("/", "_")
    filename = f"adzuna_{kw_slug}_{date_str}.json"
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    raw_dir = os.path.join(project_root, "data", "raw")
    os.makedirs(raw_dir, exist_ok=True)
    
    filepath = os.path.join(raw_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
        
    print(f"Raw Adzuna data saved -> {filepath}")
    return filepath
