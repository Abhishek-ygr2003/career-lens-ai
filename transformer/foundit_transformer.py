from datetime import datetime, timezone

def clean_location(loc_dict):
    """
    Format a single location dict into a human-readable city/state/country string.
    """
    parts = []
    city = loc_dict.get("city")
    state = loc_dict.get("state")
    country = loc_dict.get("country")
    
    if city:
        parts.append(city)
    if state and state != city:
        parts.append(state)
    if country:
        parts.append(country)
        
    return ", ".join(parts) if parts else "Unknown Location"

def transform_single_job(job_dict):
    """
    Transform a single raw job dict from Foundit API into the standardized CareerLens schema format.
    """
    # 1. Base details
    # Use id or jobId as the unique source identifier
    source_job_id = str(job_dict.get("id") or job_dict.get("jobId", ""))
    if not source_job_id:
        # Fallback if neither is present
        source_job_id = f"unknown_{hash(job_dict.get('title', ''))}"

    title = job_dict.get("title", "Unknown Title")
    company = job_dict.get("companyName", "Unknown Company")
    
    # 2. Locations mapping (extract city/state/country strings)
    raw_locations = job_dict.get("locations") or []
    locations = [clean_location(loc) for loc in raw_locations if isinstance(loc, dict)]
    if not locations:
        locations = ["India"] # Default fallback since query targets India
        
    # 3. Skills mapping (extract skills array)
    raw_skills = job_dict.get("skills") or []
    skills = [skill.get("text") for skill in raw_skills if isinstance(skill, dict) and skill.get("text")]
    
    # 4. Qualifications mapping
    raw_quals = job_dict.get("qualifications") or []
    qualifications = [q for q in raw_quals if isinstance(q, str)]
    
    # 5. Company logo URL
    company_logo_url = job_dict.get("companyLogoUrl")
    
    # 6. Experience ranges
    min_exp_data = job_dict.get("minimumExperience") or {}
    max_exp_data = job_dict.get("maximumExperience") or {}
    
    min_experience = min_exp_data.get("years") if isinstance(min_exp_data, dict) else None
    max_experience = max_exp_data.get("years") if isinstance(max_exp_data, dict) else None
    
    # 7. Salary range
    min_salary_data = job_dict.get("minimumSalary") or {}
    max_salary_data = job_dict.get("maximumSalary") or {}
    
    # Safely get min salary
    min_val = min_salary_data.get("absoluteValue") if isinstance(min_salary_data, dict) else 0
    if not min_val and isinstance(min_salary_data, dict):
        min_val = min_salary_data.get("absoluteMonthlyValue", 0)
    min_salary = float(min_val) if min_val and min_val > 0 else None
        
    # Safely get max salary
    max_val = max_salary_data.get("absoluteValue") if isinstance(max_salary_data, dict) else 0
    if not max_val and isinstance(max_salary_data, dict):
        max_val = max_salary_data.get("absoluteMonthlyValue", 0)
    max_salary = float(max_val) if max_val and max_val > 0 else None
    
    # Salary Currency
    salary_currency = job_dict.get("currencyCode") or min_salary_data.get("currency") if isinstance(min_salary_data, dict) else None
    
    # 8. Description and URL
    description = job_dict.get("description")
    job_url = job_dict.get("jdUrl")
    
    # 9. Date parsing (postedAt timestamp from ms to ISO TIMESTAMPTZ string)
    posted_at_ms = job_dict.get("postedAt")
    posted_at = None
    if isinstance(posted_at_ms, (int, float)):
        try:
            posted_at = datetime.fromtimestamp(posted_at_ms / 1000.0, tz=timezone.utc).isoformat()
        except Exception:
            pass
            
    # Standardized record
    return {
        "source": "foundit",
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
        "raw_data": job_dict,  # Stripped by main.py unless --keep-raw
    }

def transform_jobs(raw_response):
    """
    Process raw JSON payload (either dict containing 'data' list, or direct list)
    and return list of transformed job records.
    """
    jobs = []
    if isinstance(raw_response, dict):
        jobs = raw_response.get("data", [])
    elif isinstance(raw_response, list):
        jobs = raw_response
        
    transformed = []
    for job in jobs:
        if isinstance(job, dict):
            transformed.append(transform_single_job(job))
            
    return transformed
