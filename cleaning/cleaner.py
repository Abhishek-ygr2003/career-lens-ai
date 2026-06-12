"""
CareerLens AI — cleaning/cleaner.py
====================================
Generic data cleaning and standardization module.
Source-agnostic: works on any job records loaded from the `jobs` table.

Responsibilities:
  1. Fingerprint (stable MD5 deduplication across sources)
  2. Location standardization (raw preserved + structured hierarchy + fallback)
  3. Experience parsing (raw preserved + min_exp / max_exp)
  4. Skill normalization (raw preserved + standardized_skills)
  5. HTML & entity stripping from descriptions
  6. Two-level job classification (job_field + job_sub_field, keyword-based)
  7. Local file export to data/processed/
"""

import hashlib
import re
import json
import csv
import os
from datetime import date, datetime

# ─────────────────────────────────────────────────────────────
# 1. FINGERPRINT
# ─────────────────────────────────────────────────────────────

def make_fingerprint(title: str, company: str, city: str, source_job_id: str = "") -> str:
    """
    Stable MD5 fingerprint for cross-source deduplication.
    Includes source_job_id to prevent collisions when two different companies
    post identical titles in the same city.
    """
    text = (
        title.lower().strip() +
        company.lower().strip() +
        (city or "").lower().strip() +
        (source_job_id or "").strip()
    )
    return hashlib.md5(text.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────
# 2. LOCATION STANDARDIZATION
# ─────────────────────────────────────────────────────────────

# Map of lowercase aliases → canonical city name
CITY_MAP = {
    # Bangalore variants
    "bengaluru": "Bangalore",
    "bangalore": "Bangalore",
    "bangalore urban": "Bangalore",
    "bengaluru urban": "Bangalore",
    "bengaluru, karnataka": "Bangalore",
    "bangalore, karnataka": "Bangalore",
    "bengaluru/bangalore": "Bangalore",
    "bangalore/bengaluru": "Bangalore",
    "bengaluru karnataka": "Bangalore",

    # Delhi NCR variants
    "delhi": "Delhi NCR",
    "new delhi": "Delhi NCR",
    "gurgaon": "Delhi NCR",
    "gurugram": "Delhi NCR",
    "noida": "Delhi NCR",
    "greater noida": "Delhi NCR",
    "faridabad": "Delhi NCR",
    "ghaziabad": "Delhi NCR",
    "ncr": "Delhi NCR",
    "delhi ncr": "Delhi NCR",

    # Mumbai variants
    "mumbai": "Mumbai",
    "navi mumbai": "Mumbai",
    "thane": "Mumbai",
    "mumbai metropolitan region": "Mumbai",

    # Other major cities
    "pune": "Pune",
    "hyderabad": "Hyderabad",
    "secunderabad": "Hyderabad",
    "chennai": "Chennai",
    "madras": "Chennai",
    "kolkata": "Kolkata",
    "calcutta": "Kolkata",
    "ahmedabad": "Ahmedabad",
    "coimbatore": "Coimbatore",
    "jaipur": "Jaipur",
    "kochi": "Kochi",
    "cochin": "Kochi",
    "chandigarh": "Chandigarh",
    "bhubaneswar": "Bhubaneswar",
    "indore": "Indore",
    "nagpur": "Nagpur",
    "surat": "Surat",
    "vizag": "Visakhapatnam",
    "visakhapatnam": "Visakhapatnam",

    # ── Expanded: additional Indian cities ────────────────────
    "thiruvananthapuram": "Thiruvananthapuram",
    "trivandrum": "Thiruvananthapuram",
    "mangalore": "Mangalore",
    "mangaluru": "Mangalore",
    "mysore": "Mysore",
    "mysuru": "Mysore",
    "lucknow": "Lucknow",
    "patna": "Patna",
    "vadodara": "Vadodara",
    "baroda": "Vadodara",
    "rajkot": "Rajkot",
    "kanpur": "Kanpur",
    "nagpur": "Nagpur",
    "ludhiana": "Ludhiana",
    "agra": "Agra",
    "nashik": "Nashik",
    "ranchi": "Ranchi",
    "bhopal": "Bhopal",
    "dehradun": "Dehradun",
    "guwahati": "Guwahati",
    "vijayawada": "Vijayawada",
    "madurai": "Madurai",
    "varanasi": "Varanasi",
    "hubli": "Hubli",
    "trichy": "Tiruchirappalli",
    "tiruchirappalli": "Tiruchirappalli",
    "jodhpur": "Jodhpur",
    "raipur": "Raipur",
    "amritsar": "Amritsar",
    "aurangabad": "Aurangabad",
    "goa": "Goa",
    "panaji": "Goa",
    "pondicherry": "Pondicherry",
    "puducherry": "Pondicherry",
    "shimla": "Shimla",
    "mohali": "Mohali",
    "panchkula": "Panchkula",

    # Pan-India / generic
    "india": "Pan India",
    "pan india": "Pan India",
    "anywhere in india": "Pan India",
    "multiple cities": "Pan India",
    "multiple locations": "Pan India",
}

# State mapping for known cities
CITY_TO_STATE = {
    "Bangalore": "Karnataka",
    "Hyderabad": "Telangana",
    "Chennai": "Tamil Nadu",
    "Mumbai": "Maharashtra",
    "Pune": "Maharashtra",
    "Delhi NCR": "Delhi",
    "Kolkata": "West Bengal",
    "Ahmedabad": "Gujarat",
    "Coimbatore": "Tamil Nadu",
    "Jaipur": "Rajasthan",
    "Kochi": "Kerala",
    "Chandigarh": "Punjab",
    "Bhubaneswar": "Odisha",
    "Indore": "Madhya Pradesh",
    "Nagpur": "Maharashtra",
    "Surat": "Gujarat",
    "Visakhapatnam": "Andhra Pradesh",
    # Expanded
    "Thiruvananthapuram": "Kerala",
    "Mangalore": "Karnataka",
    "Mysore": "Karnataka",
    "Lucknow": "Uttar Pradesh",
    "Patna": "Bihar",
    "Vadodara": "Gujarat",
    "Rajkot": "Gujarat",
    "Kanpur": "Uttar Pradesh",
    "Ludhiana": "Punjab",
    "Agra": "Uttar Pradesh",
    "Nashik": "Maharashtra",
    "Ranchi": "Jharkhand",
    "Bhopal": "Madhya Pradesh",
    "Dehradun": "Uttarakhand",
    "Guwahati": "Assam",
    "Vijayawada": "Andhra Pradesh",
    "Madurai": "Tamil Nadu",
    "Varanasi": "Uttar Pradesh",
    "Hubli": "Karnataka",
    "Tiruchirappalli": "Tamil Nadu",
    "Jodhpur": "Rajasthan",
    "Raipur": "Chhattisgarh",
    "Amritsar": "Punjab",
    "Aurangabad": "Maharashtra",
    "Goa": "Goa",
    "Pondicherry": "Puducherry",
    "Shimla": "Himachal Pradesh",
    "Mohali": "Punjab",
    "Panchkula": "Haryana",
}

REMOTE_KEYWORDS = ["remote", "work from home", "wfh", "fully remote", "telecommute", "anywhere"]
HYBRID_KEYWORDS = ["hybrid", "hybrid work", "hybrid model"]


def standardize_location(locations_list: list) -> dict:
    """
    Takes a list of raw location strings (from the `locations` TEXT[] column)
    and returns a structured location dict with raw + hierarchy.

    Falls back to the cleaned raw city name (title-cased) when no canonical
    mapping exists — so new cities auto-appear in dashboard filters instead
    of being lumped into "Unknown".

    Returns:
        {
          "raw_location": str,        # Original joined string
          "work_mode": str,           # 'Remote' | 'Hybrid' | 'Onsite'
          "city": str | None,
          "state": str | None,
          "country": str,
        }
    """
    if not locations_list:
        return {
            "raw_location": None,
            "work_mode": "Onsite",
            "city": None,
            "state": None,
            "country": "India",
        }

    raw_location = ", ".join(str(loc) for loc in locations_list if loc)
    raw_lower = raw_location.lower()

    # Detect work mode first
    work_mode = "Onsite"
    if any(kw in raw_lower for kw in REMOTE_KEYWORDS):
        work_mode = "Remote"
    elif any(kw in raw_lower for kw in HYBRID_KEYWORDS):
        work_mode = "Hybrid"

    # Try to find a canonical city
    city = None
    for part in locations_list:
        part_str = str(part).strip()
        # Try full string first, then just the first segment (before comma)
        candidates = [part_str, part_str.split(",")[0].strip()]
        for candidate in candidates:
            canonical = CITY_MAP.get(candidate.lower())
            if canonical and canonical != "Pan India":
                city = canonical
                break
        if city:
            break

    # Fallback: scan raw string for any city alias
    if not city:
        for alias, canonical in CITY_MAP.items():
            if alias in raw_lower and canonical != "Pan India":
                city = canonical
                break

    # ── NEW: Graceful fallback for unmapped cities ────────────
    # If no canonical mapping found, use the first location part
    # (title-cased) as an unmapped city rather than returning None.
    # This ensures new cities auto-appear in dashboard filters.
    if not city:
        for part in locations_list:
            candidate = str(part).split(",")[0].strip().title()
            if candidate and candidate.lower() not in (
                "india", "pan india", "remote", "work from home",
                "wfh", "anywhere", "multiple locations", "multiple cities",
                "unknown location",
            ):
                city = candidate
                break

    state = CITY_TO_STATE.get(city) if city else None

    return {
        "raw_location": raw_location,
        "work_mode": work_mode,
        "city": city,
        "state": state,
        "country": "India",
    }


# ─────────────────────────────────────────────────────────────
# 3. EXPERIENCE PARSING
# ─────────────────────────────────────────────────────────────

def parse_experience(min_raw, max_raw) -> dict:
    """
    Converts raw experience values (int, str, or None) into:
    { "raw_experience": str | None, "min_exp": int | None, "max_exp": int | None }

    Handles patterns like: "0-3 Yrs", "5+ years", "2-5", integers, None.
    """
    def _to_int(val):
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return int(val)
        val_str = str(val).strip().lower()
        # Remove common suffixes
        val_str = re.sub(r'(yrs?|years?|\+)', '', val_str).strip()
        # Try parsing a range like "2-5"
        range_match = re.match(r'^(\d+)\s*[-–]\s*(\d+)$', val_str)
        if range_match:
            return int(range_match.group(1)), int(range_match.group(2))
        # Single number
        num_match = re.match(r'^(\d+)$', val_str)
        if num_match:
            return int(num_match.group(1))
        return None

    # Build a raw experience string for display
    if min_raw is not None and max_raw is not None:
        raw_experience = f"{min_raw}-{max_raw} Yrs"
    elif min_raw is not None:
        raw_experience = f"{min_raw}+ Yrs"
    elif max_raw is not None:
        raw_experience = f"Up to {max_raw} Yrs"
    else:
        raw_experience = None

    # Parse to int
    min_result = _to_int(min_raw)
    max_result = _to_int(max_raw)

    # Handle tuple returns from range strings
    if isinstance(min_result, tuple):
        min_result, max_result = min_result
    if isinstance(max_result, tuple):
        _, max_result = max_result

    # Clamp negatives
    if isinstance(min_result, int) and min_result < 0:
        min_result = 0
    if isinstance(max_result, int) and max_result < 0:
        max_result = None

    return {
        "raw_experience": raw_experience,
        "min_exp": min_result,
        "max_exp": max_result,
    }


# ─────────────────────────────────────────────────────────────
# 4. SKILL NORMALIZATION
# ─────────────────────────────────────────────────────────────

# Alias map: lowercase variant → canonical form
SKILL_ALIASES = {
    # Python
    "python programming": "python",
    "python3": "python",
    "py": "python",
    "python scripting": "python",
    # Machine Learning
    "ml": "machine learning",
    "machine-learning": "machine learning",
    "applied machine learning": "machine learning",
    # Deep Learning
    "dl": "deep learning",
    "deep-learning": "deep learning",
    # AI / GenAI
    "artificial intelligence": "ai",
    "generative ai": "gen ai",
    "genai": "gen ai",
    "llm": "large language models",
    "large language model": "large language models",
    "llms": "large language models",
    "rag": "retrieval augmented generation",
    "langchain": "langchain",
    "lang chain": "langchain",
    # NLP
    "natural language processing": "nlp",
    "natural-language-processing": "nlp",
    # Databases / SQL
    "postgresql": "sql",
    "postgres": "sql",
    "mysql": "sql",
    "microsoft sql server": "sql",
    "t-sql": "sql",
    "pl/sql": "sql",
    "structured query language": "sql",
    # Cloud
    "amazon web services": "aws",
    "google cloud platform": "gcp",
    "google cloud": "gcp",
    "microsoft azure": "azure",
    # Data tools
    "apache spark": "spark",
    "apache kafka": "kafka",
    "apache airflow": "airflow",
    # DevOps / MLOps
    "devops": "devops",
    "ml ops": "mlops",
    "ml-ops": "mlops",
    # BI tools
    "power bi": "power bi",
    "powerbi": "power bi",
    "tableau software": "tableau",
    # Stats / Data Science
    "r programming": "r",
    "statistics": "statistics",
    "statistical analysis": "statistics",
    # Computer Vision
    "cv": "computer vision",
    "image processing": "computer vision",
    # TensorFlow / PyTorch
    "tensorflow": "tensorflow",
    "tf": "tensorflow",
    "pytorch": "pytorch",
    "torch": "pytorch",
    # Containers
    "docker": "docker",
    "kubernetes": "kubernetes",
    "k8s": "kubernetes",

    # ── Expanded: modern AI/ML tools ─────────────────────────
    "hugging face": "huggingface",
    "huggingface": "huggingface",
    "openai": "openai",
    "open ai": "openai",
    "anthropic": "anthropic",
    "gemini": "gemini",
    "vertex ai": "vertex ai",
    "vertexai": "vertex ai",
    "mistral": "mistral",
    "ollama": "ollama",
    "llamaindex": "llamaindex",
    "llama index": "llamaindex",
    "pinecone": "pinecone",
    "chromadb": "chromadb",
    "chroma db": "chromadb",
    "weaviate": "weaviate",
    "vector database": "vector databases",
    "vector db": "vector databases",
    "prompt engineering": "prompt engineering",
    "fine tuning": "fine-tuning",
    "fine-tuning": "fine-tuning",
    "finetuning": "fine-tuning",
    "mlflow": "mlflow",
    "dvc": "dvc",
    "wandb": "wandb",
    "weights and biases": "wandb",
    "fastapi": "fastapi",
    "flask": "flask",
    "django": "django",
    "streamlit": "streamlit",
    "gradio": "gradio",
    "databricks": "databricks",
    "snowflake": "snowflake",
    "dbt": "dbt",
    "data build tool": "dbt",
    "great expectations": "great expectations",
    "pandas": "pandas",
    "numpy": "numpy",
    "scikit learn": "scikit-learn",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "matplotlib": "matplotlib",
    "seaborn": "seaborn",
    "plotly": "plotly",
    "git": "git",
    "github": "github",
    "ci cd": "ci/cd",
    "ci/cd": "ci/cd",
    "jenkins": "jenkins",
    "terraform": "terraform",
    "ansible": "ansible",
    "linux": "linux",
    "java": "java",
    "scala": "scala",
    "golang": "go",
    "go lang": "go",
    "rust": "rust",
    "c++": "c++",
    "cpp": "c++",
    "javascript": "javascript",
    "typescript": "typescript",
    "react": "react",
    "angular": "angular",
    "node js": "node.js",
    "nodejs": "node.js",
    "mongodb": "mongodb",
    "redis": "redis",
    "elasticsearch": "elasticsearch",
    "neo4j": "neo4j",
    "graphql": "graphql",
    "rest api": "rest api",
    "restful api": "rest api",
    "api development": "rest api",
    "excel": "excel",
    "ms excel": "excel",
    "microsoft excel": "excel",
    "salesforce": "salesforce",
    "sap": "sap",
    "crm": "crm",
    "erp": "erp",
    "jira": "jira",
    "agile": "agile",
    "scrum": "scrum",
}

def normalize_skill(skill: str) -> str:
    """
    Normalize a single skill string:
    lowercase → strip → alias lookup → clean punctuation.
    """
    if not skill:
        return ""
    cleaned = skill.lower().strip()
    # Remove excess whitespace and common noise chars
    cleaned = re.sub(r'[\-_/\\]+', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return SKILL_ALIASES.get(cleaned, cleaned)


def standardize_skills(raw_skills: list) -> dict:
    """
    Takes a raw skills list (TEXT[] from DB) and returns:
    {
      "raw_skills": [...],           # original list, unchanged
      "standardized_skills": [...]   # deduplicated, normalized list
    }
    """
    if not raw_skills:
        return {"raw_skills": [], "standardized_skills": []}

    raw = [str(s).strip() for s in raw_skills if s and str(s).strip()]
    normalized = []
    seen = set()
    for skill in raw:
        norm = normalize_skill(skill)
        if norm and norm not in seen:
            seen.add(norm)
            normalized.append(norm)

    return {
        "raw_skills": raw,
        "standardized_skills": normalized,
    }


# ─────────────────────────────────────────────────────────────
# 5. HTML STRIPPING
# ─────────────────────────────────────────────────────────────

# HTML entities to decode
HTML_ENTITIES = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&nbsp;": " ",
    "&quot;": '"',
    "&#39;": "'",
    "&apos;": "'",
    "&mdash;": "—",
    "&ndash;": "–",
    "&bull;": "•",
    "&hellip;": "…",
}

def strip_html(html_text: str) -> str:
    """
    Convert HTML job description to clean plain text.
    Uses regex-based approach (no extra dependency needed).
    """
    if not html_text:
        return ""

    text = html_text

    # Remove script and style blocks entirely
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.IGNORECASE | re.DOTALL)

    # Replace block elements with newlines for readability
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(p|div|li|tr|h[1-6]|section|article)[^>]*>', '\n', text, flags=re.IGNORECASE)

    # Replace list items with bullet points
    text = re.sub(r'<li[^>]*>', '• ', text, flags=re.IGNORECASE)

    # Strip all remaining tags
    text = re.sub(r'<[^>]+>', '', text)

    # Decode HTML entities
    for entity, char in HTML_ENTITIES.items():
        text = text.replace(entity, char)

    # Try stdlib html.unescape for any missed entities
    try:
        from html import unescape
        text = unescape(text)
    except Exception:
        pass

    # Collapse multiple newlines and spaces
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = text.strip()

    return text


# ─────────────────────────────────────────────────────────────
# 6. TWO-LEVEL JOB CLASSIFICATION
# ─────────────────────────────────────────────────────────────

# Two-level rules: (top_level_field, sub_field, [keywords])
# Priority-ordered: first match wins.
CATEGORY_RULES = [
    # AI / ML
    ("AI / ML",             "Generative AI",        ["genai", "gen ai", "generative ai", "llm", "large language", "langchain", "rag", "gpt", "diffusion", "prompt engineer"]),
    ("AI / ML",             "MLOps / Platform",     ["mlops", "ml platform", "model deployment", "kubeflow", "ml engineer", "ml ops", "ai platform", "ai infrastructure"]),
    ("AI / ML",             "Machine Learning",     ["machine learning", "deep learning", "ai engineer", "computer vision", "nlp engineer", "research scientist", "ai research"]),
    # Data
    ("Data",                "Data Science",         ["data scientist", "data science"]),
    ("Data",                "Data Engineering",     ["data engineer", "etl", "data pipeline", "big data", "spark engineer", "kafka", "airflow engineer", "data platform"]),
    ("Data",                "Data Analytics",       ["data analyst", "analytics engineer", "business analyst", "product analyst", "marketing analyst"]),
    ("Data",                "Business Intelligence",["bi developer", "bi analyst", "business intelligence", "tableau developer", "power bi", "looker"]),
    # Software
    ("Software",            "Software Engineering", ["software engineer", "sde", "backend engineer", "frontend engineer", "full stack", "python developer", "java developer", "web developer", "mobile developer"]),
    ("Software",            "DevOps / Cloud",       ["devops", "site reliability", "sre", "cloud engineer", "infrastructure engineer", "platform engineer"]),
    ("Software",            "QA / Testing",         ["qa engineer", "test engineer", "quality assurance", "sdet", "automation testing"]),
    # Business
    ("Sales & Marketing",   "Sales & BD",           ["sales", "business development", "bde", "account manager", "account executive", "client success", "customer success"]),
    ("Sales & Marketing",   "Marketing",            ["marketing", "seo", "digital marketing", "growth hacker", "social media", "content writer", "content creator", "brand manager"]),
    # Management
    ("Management",          "Product Management",   ["product manager", "product owner", "scrum master", "agile coach", "project manager"]),
    ("Management",          "Engineering Manager",  ["engineering manager", "tech lead", "technical lead", "vp engineering", "cto", "director of engineering"]),
    # Support
    ("Human Resources",     "Human Resources",      ["hr", "human resources", "recruiter", "talent acquisition", "people operations"]),
    ("Finance",             "Finance",              ["finance", "accountant", "financial analyst", "auditor", "controller", "cfo"]),
    ("Design",              "Design",               ["ui designer", "ux designer", "graphic designer", "visual designer", "interaction designer", "product designer"]),
]

# Legacy flat category rules for backward compatibility (job_category column)
LEGACY_CATEGORY_RULES = [
    ("Generative AI",       ["genai", "gen ai", "generative ai", "llm", "large language", "langchain", "rag", "gpt", "diffusion"]),
    ("MLOps / Platform",    ["mlops", "ml platform", "model deployment", "kubeflow", "ml engineer", "ml ops", "ai platform"]),
    ("Machine Learning",    ["machine learning", "deep learning", "ai engineer", "computer vision", "nlp engineer", "research scientist"]),
    ("Data Science",        ["data scientist", "data science"]),
    ("Data Engineering",    ["data engineer", "etl", "data pipeline", "big data", "spark engineer", "kafka", "airflow engineer"]),
    ("Data Analytics",      ["data analyst", "analytics engineer", "business analyst", "product analyst", "marketing analyst"]),
    ("Business Intelligence", ["bi developer", "bi analyst", "business intelligence", "tableau developer", "power bi", "looker"]),
    ("Software Engineering",["software engineer", "sde", "backend engineer", "frontend engineer", "full stack", "python developer", "java developer"]),
    ("Sales & Development", ["sales", "business development", "bde", "account manager", "account executive", "client success", "customer success"]),
    ("Marketing",           ["marketing", "seo", "digital marketing", "growth hacker", "social media", "content writer", "content creator"]),
    ("Product Management",  ["product manager", "product owner", "scrum master", "agile coach", "project manager"]),
    ("Human Resources",     ["hr", "human resources", "recruiter", "talent acquisition"]),
    ("Finance",             ["finance", "accountant", "financial analyst", "auditor"]),
]


def classify_job(title: str, description: str = "") -> dict:
    """
    Classify a job into a two-level hierarchy:
      - job_field (top-level): 'AI / ML', 'Data', 'Software', etc.
      - job_sub_field: 'Generative AI', 'Data Science', etc.
      - job_category (legacy flat): 'Data Science', 'Machine Learning', etc.

    Uses title first, then falls back to description keywords (first 500 chars).
    Returns dict with all three keys.
    """
    title_lower = (title or "").lower().strip()
    desc_lower = (description or "").lower()[:500]

    job_field = "Other"
    job_sub_field = "Other"

    # Two-level classification: try title first, then description
    for field, sub_field, keywords in CATEGORY_RULES:
        for kw in keywords:
            if kw in title_lower:
                job_field = field
                job_sub_field = sub_field
                break
        if job_field != "Other":
            break

    # Fallback to description if title didn't match
    if job_field == "Other" and desc_lower:
        for field, sub_field, keywords in CATEGORY_RULES:
            for kw in keywords:
                if kw in desc_lower:
                    job_field = field
                    job_sub_field = sub_field
                    break
            if job_field != "Other":
                break

    # Legacy flat category
    job_category = "Other"
    for category, keywords in LEGACY_CATEGORY_RULES:
        for kw in keywords:
            if kw in title_lower:
                job_category = category
                break
        if job_category != "Other":
            break

    # Fallback to description for legacy category too
    if job_category == "Other" and desc_lower:
        for category, keywords in LEGACY_CATEGORY_RULES:
            for kw in keywords:
                if kw in desc_lower:
                    job_category = category
                    break
            if job_category != "Other":
                break

    return {
        "job_field": job_field,
        "job_sub_field": job_sub_field,
        "job_category": job_category,
    }


# ─────────────────────────────────────────────────────────────
# 7. MAIN CLEANING PIPELINE
# ─────────────────────────────────────────────────────────────

def clean_job(raw_job: dict, search_keyword: str | None = None) -> dict:
    """
    Takes a single raw job record (from the `jobs` table) and returns
    a cleaned, standardized record ready for `jobs_analytics`.

    Args:
        raw_job: dict from the `jobs` table (all columns included)
        search_keyword: the keyword used during collection (for tagging)

    Returns:
        dict suitable for upserting into `jobs_analytics`
    """
    # ── Location ──────────────────────────────────────────────
    locations_list = raw_job.get("locations") or []
    location_data = standardize_location(locations_list)

    # ── Experience ────────────────────────────────────────────
    exp_data = parse_experience(
        raw_job.get("min_experience"),
        raw_job.get("max_experience"),
    )

    # ── Skills ────────────────────────────────────────────────
    skills_data = standardize_skills(raw_job.get("skills") or [])

    # ── Description ───────────────────────────────────────────
    description_raw = raw_job.get("description") or ""
    description_clean = strip_html(description_raw)

    # ── Category (two-level + legacy) ─────────────────────────
    title = raw_job.get("title") or ""
    category_data = classify_job(title, description_clean)

    # ── Fingerprint (includes source_job_id to avoid collisions) ──
    company = raw_job.get("company") or ""
    city = location_data.get("city") or ""
    source_job_id = raw_job.get("source_job_id") or ""
    fingerprint = make_fingerprint(title, company, city, source_job_id)

    # ── Collected date ────────────────────────────────────────
    # Use posted_at date if available, otherwise today
    posted_at = raw_job.get("posted_at")
    collected_at = date.today().isoformat()
    if posted_at:
        try:
            collected_at = datetime.fromisoformat(str(posted_at)).date().isoformat()
        except Exception:
            pass

    # ── Search keywords ───────────────────────────────────────
    search_keywords = []
    if search_keyword:
        search_keywords = [search_keyword.lower().strip()]

    return {
        "fingerprint": fingerprint,
        "source": raw_job.get("source"),
        "source_job_id": source_job_id,
        "collected_at": collected_at,
        "title": title,
        "company": company,
        # Two-level category
        "job_field": category_data["job_field"],
        "job_sub_field": category_data["job_sub_field"],
        "job_category": category_data["job_category"],
        # Location
        "raw_location": location_data["raw_location"],
        "work_mode": location_data["work_mode"],
        "city": location_data["city"],
        "state": location_data["state"],
        "country": location_data["country"],
        # Experience
        "raw_experience": exp_data["raw_experience"],
        "min_exp": exp_data["min_exp"],
        "max_exp": exp_data["max_exp"],
        # Skills
        "raw_skills": skills_data["raw_skills"],
        "standardized_skills": skills_data["standardized_skills"],
        # Description
        "description_raw": description_raw if description_raw else None,
        "description": description_clean if description_clean else None,
        # Salary (pass through unchanged)
        "min_salary": raw_job.get("min_salary"),
        "max_salary": raw_job.get("max_salary"),
        "salary_currency": raw_job.get("salary_currency") or "INR",
        # Links
        "job_url": raw_job.get("job_url"),
        "company_logo_url": raw_job.get("company_logo_url"),
        "posted_at": raw_job.get("posted_at"),
        # Staleness tracking
        "is_active": True,
        "last_seen_at": raw_job.get("last_seen_at"),
        # Search keyword tag
        "search_keywords": search_keywords,
    }


def clean_jobs(raw_jobs: list, search_keyword: str | None = None) -> list:
    """
    Clean a list of raw job records.
    Deduplicates by fingerprint (last occurrence wins if there are duplicates
    within the same batch, which is fine since they represent the same posting).

    Args:
        raw_jobs: list of dicts from the `jobs` table
        search_keyword: the keyword used during collection

    Returns:
        list of cleaned, deduplicated dicts for `jobs_analytics`
    """
    print(f"Cleaning {len(raw_jobs)} raw job records...")
    seen_fingerprints = {}

    for job in raw_jobs:
        try:
            cleaned = clean_job(job, search_keyword=search_keyword)
            fp = cleaned["fingerprint"]
            # If duplicate, keep the one with the most recent posted_at
            if fp in seen_fingerprints:
                existing = seen_fingerprints[fp]
                if cleaned.get("posted_at") and existing.get("posted_at"):
                    if str(cleaned["posted_at"]) > str(existing["posted_at"]):
                        seen_fingerprints[fp] = cleaned
            else:
                seen_fingerprints[fp] = cleaned
        except Exception as e:
            print(f"  Warning: Failed to clean job '{job.get('title', 'Unknown')}': {e}")

    cleaned_list = list(seen_fingerprints.values())
    duplicates_removed = len(raw_jobs) - len(cleaned_list)
    print(f"  ✓ Cleaned {len(cleaned_list)} unique jobs ({duplicates_removed} duplicates removed)")
    return cleaned_list


# ─────────────────────────────────────────────────────────────
# 8. LOCAL FILE EXPORT
# ─────────────────────────────────────────────────────────────

PROCESSED_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "processed")

def export_to_files(cleaned_jobs: list) -> dict:
    """
    Export cleaned jobs to local files:
      - data/processed/jobs_analytics.csv
      - data/processed/jobs_analytics.json

    Returns dict with file paths.
    """
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    csv_path = os.path.join(PROCESSED_DIR, "jobs_analytics.csv")
    json_path = os.path.join(PROCESSED_DIR, "jobs_analytics.json")

    if not cleaned_jobs:
        print("No cleaned jobs to export.")
        return {"csv": csv_path, "json": json_path}

    # ── JSON export ─────────────────────────────────────────
    # Convert list fields to JSON-serializable format
    json_safe = []
    for job in cleaned_jobs:
        row = dict(job)
        # Arrays become JSON arrays naturally
        # Dates/timestamps may need string conversion
        for key in ("posted_at", "collected_at", "last_seen_at"):
            if row.get(key) and not isinstance(row[key], str):
                row[key] = str(row[key])
        json_safe.append(row)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_safe, f, ensure_ascii=False, indent=2, default=str)
    print(f"  ✓ JSON exported → {json_path}")

    # ── CSV export ──────────────────────────────────────────
    # Flatten array columns to semicolon-separated strings for CSV
    if cleaned_jobs:
        fieldnames = list(cleaned_jobs[0].keys())
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for job in cleaned_jobs:
                row = dict(job)
                # Flatten list fields
                for key in ("raw_skills", "standardized_skills", "search_keywords"):
                    if isinstance(row.get(key), list):
                        row[key] = ";".join(str(s) for s in row[key])
                # Convert timestamps
                for key in ("posted_at", "collected_at", "last_seen_at"):
                    if row.get(key) and not isinstance(row[key], str):
                        row[key] = str(row[key])
                writer.writerow(row)
        print(f"  ✓ CSV exported → {csv_path}")

    return {"csv": csv_path, "json": json_path}
