from datetime import datetime, timezone

def parse_experience(exp_val):
    """
    Safely convert an experience string or number into an integer.
    """
    if exp_val is None:
        return None
    try:
        return int(exp_val)
    except (ValueError, TypeError):
        return None

def clean_location(loc_str):
    """
    Cleans a single location string by stripping whitespaces.
    """
    if not loc_str:
        return "Unknown Location"
    return loc_str.strip()

def transform_single_job(job_dict):
    """
    Transform a single raw job dict from Naukri API into the standardized CareerLens schema format.
    """
    # 1. Base details
    source_job_id = str(job_dict.get("jobId", ""))
    if not source_job_id:
        source_job_id = f"unknown_{hash(job_dict.get('title', ''))}"

    title = job_dict.get("title", "Unknown Title")
    company = job_dict.get("companyName", "Unknown Company")
    
    # 2. Locations mapping (extract from placeholders where type == "location")
    placeholders = job_dict.get("placeholders") or []
    locations = []
    for p in placeholders:
        if isinstance(p, dict) and p.get("type") == "location":
            label = p.get("label", "")
            if label:
                # Naukri locations can be comma-separated, e.g. "Bengaluru, Pune"
                parts = [clean_location(part) for part in label.split(",")]
                locations.extend(parts)
                
    if not locations:
        locations = ["India"] # Default fallback

    # 3. Skills mapping (parse comma-separated tagsAndSkills string)
    tags_and_skills = job_dict.get("tagsAndSkills") or ""
    skills = []
    if tags_and_skills:
        # Split by comma and strip whitespaces
        skills = [s.strip() for s in tags_and_skills.split(",") if s.strip()]

    # 4. Qualifications mapping (none explicitly available in payload, return empty list)
    qualifications = []

    # 5. Company logo URL
    company_logo_url = job_dict.get("logoPathV3") or job_dict.get("logoPath")

    # 6. Experience ranges
    min_experience = parse_experience(job_dict.get("minimumExperience"))
    max_experience = parse_experience(job_dict.get("maximumExperience"))

    # 7. Salary range
    salary_detail = job_dict.get("salaryDetail") or {}
    min_val = salary_detail.get("minimumSalary", 0)
    max_val = salary_detail.get("maximumSalary", 0)
    hide_salary = salary_detail.get("hideSalary", True)

    # Convert to floats if not hidden and valid
    min_salary = float(min_val) if not hide_salary and min_val and min_val > 0 else None
    max_salary = float(max_val) if not hide_salary and max_val and max_val > 0 else None
    salary_currency = job_dict.get("currency") or salary_detail.get("currency")

    # 8. Description and URL
    description = job_dict.get("jobDescription")
    jd_url = job_dict.get("jdURL")
    job_url = f"https://www.naukri.com{jd_url}" if jd_url else None

    # 9. Date parsing (createdDate timestamp from ms to ISO TIMESTAMPTZ string)
    created_date_ms = job_dict.get("createdDate")
    posted_at = None
    if isinstance(created_date_ms, (int, float)):
        try:
            posted_at = datetime.fromtimestamp(created_date_ms / 1000.0, tz=timezone.utc).isoformat()
        except Exception:
            pass

    return {
        "source": "naukri",
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
    Process raw JSON payload (either dict containing 'jobDetails' list, or direct list)
    and return list of transformed job records.
    """
    jobs = []
    if isinstance(raw_response, dict):
        jobs = raw_response.get("jobDetails", [])
    elif isinstance(raw_response, list):
        jobs = raw_response
        
    transformed = []
    for job in jobs:
        if isinstance(job, dict):
            transformed.append(transform_single_job(job))
            
    return transformed
