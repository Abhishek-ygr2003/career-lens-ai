import os
from dotenv import load_dotenv

# Load env variables
load_dotenv()

_supabase_client = None

def get_supabase_client():
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url or not key or "dummy" in url or "your-project" in url:
        raise ValueError(
            "Supabase credentials not configured correctly. "
            "Please update SUPABASE_URL and SUPABASE_KEY in your .env file."
        )

    try:
        from supabase import create_client
        _supabase_client = create_client(url, key)
        return _supabase_client
    except ImportError:
        raise ImportError(
            "The 'supabase' library is not installed. Please run 'pip install -r requirements.txt'"
        )
    except Exception as e:
        raise ConnectionError(f"Failed to initialize Supabase client: {e}")

def upsert_jobs(jobs_list):
    """
    Upsert a list of standardized job dicts into Supabase 'jobs' table.
    Ensures idempotency using the (source, source_job_id) constraint.
    """
    if not jobs_list:
        print("No jobs to insert.")
        return []

    client = get_supabase_client()
    try:
        print(f"Uploading {len(jobs_list)} jobs to Supabase...")
        # PostgREST upsert with conflict columns specified
        response = client.table("jobs").upsert(
            jobs_list, 
            on_conflict="source,source_job_id"
        ).execute()
        
        # Check if response has data
        data = getattr(response, "data", [])
        print(f"Successfully upserted {len(data)} records in Supabase.")
        return data
    except Exception as e:
        print(f"Error upserting jobs into Supabase: {e}")
        raise e
