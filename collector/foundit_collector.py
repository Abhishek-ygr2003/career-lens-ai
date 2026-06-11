import os
import json
import requests
from datetime import datetime

def fetch_jobs():
    url = "https://www.foundit.in/home/api/searchResultsPage"
    params = {
        "start": 0,
        "limit": 20,
        "query": "ai engineer",
        "queryDerived": "true",
        "countries": "India"
    }
    
    # We use a user-agent header to avoid being blocked by simple bot detection
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print("Fetching jobs...")
    response = requests.get(url, params=params, headers=headers)
    response.raise_for_status()
    return response.json()

def save_raw_data(data):
    print("Saving raw data...")

    date_str = datetime.now().strftime("%Y_%m_%d")
    
    filename = f"foundit_ai_engineer_{date_str}.json"
    
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
    try:
        data = fetch_jobs()
        
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
