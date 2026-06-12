from datetime import datetime

def transform_single_job(job_dict):
    """
    Transform a single raw job dict from Adzuna API into the standardized raw schema format.
    """
    source_job_id = str(job_dict.get("id") or "")
    if not source_job_id:
        source_job_id = f"adzuna_{hash(job_dict.get('title', ''))}"
        
    title = job_dict.get("title", "Unknown Title")
    
    # Extract company name safely
    company_data = job_dict.get("company") or {}
    company = company_data.get("display_name", "Unknown Company") if isinstance(company_data, dict) else "Unknown Company"
    
    # Extract location safely
    location_data = job_dict.get("location") or {}
    locations = []
    if isinstance(location_data, dict):
        loc_name = location_data.get("display_name")
        if loc_name:
            locations.append(loc_name)
        # Extract area breakdown if present
        area_list = location_data.get("area") or []
        for area in area_list:
            if area and area not in locations:
                locations.append(str(area))
    if not locations:
        locations = ["India"]
        
    # Adzuna doesn't supply explicit skills array, we will extract them during cleaning
    skills = []
    qualifications = []
    company_logo_url = None
    
    # Adzuna doesn't supply experience ranges directly
    min_experience = None
    max_experience = None
    
    # Salary mapping
    min_salary = job_dict.get("salary_min")
    max_salary = job_dict.get("salary_max")
    salary_currency = "INR"  # Adzuna 'in' searches are always in INR
    
    description = job_dict.get("description", "")
    job_url = job_dict.get("redirect_url", "")
    
    # Date parsing
    posted_at_raw = job_dict.get("created")
    posted_at = None
    if posted_at_raw:
        try:
            # Try ISO format
            posted_at = datetime.fromisoformat(posted_at_raw.replace("Z", "+00:00")).isoformat()
        except Exception:
            try:
                # Try common formats
                posted_at = datetime.strptime(posted_at_raw, "%Y-%m-%dT%H:%M:%SZ").isoformat()
            except Exception:
                posted_at = posted_at_raw
                
    return {
        "source": "adzuna",
        "source_job_id": source_job_id,
        "title": title,
        "company": company,
        "locations": locations,
        "skills": skills,
        "qualifications": qualifications,
        "company_logo_url": company_logo_url,
        "min_experience": min_experience,
        "max_experience": max_experience,
        "min_salary": min_salary,
        "max_salary": max_salary,
        "salary_currency": salary_currency,
        "description": description,
        "job_url": job_url,
        "posted_at": posted_at,
        "raw_data": job_dict
    }

def transform_jobs(raw_response):
    """
    Process raw JSON payload (either dict containing 'results' list, or direct list)
    and return list of transformed job records.
    """
    jobs = []
    if isinstance(raw_response, dict):
        jobs = raw_response.get("results", []) or raw_response.get("data", []) or []
    elif isinstance(raw_response, list):
        jobs = raw_response
        
    transformed = []
    for job in jobs:
        if isinstance(job, dict):
            transformed.append(transform_single_job(job))
            
    return transformed
