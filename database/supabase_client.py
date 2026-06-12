"""
CareerLens AI — database/supabase_client.py
============================================
Supabase database client with support for:
  - Incremental cleaning (fetch only dirty/new jobs)
  - Stale-job detection (mark old jobs inactive)
  - Collection run logging
  - Pre-filter optimisation (skip already-known job IDs)
  - Direct dashboard data loading from Supabase
"""

import os
from datetime import datetime, timedelta, timezone
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


# ═════════════════════════════════════════════════════════════
#  RAW JOBS TABLE — CRUD
# ═════════════════════════════════════════════════════════════

def fetch_all_jobs(page_size: int = 1000) -> list:
    """
    Fetch ALL records from the `jobs` table using pagination.
    Supabase PostgREST caps responses at 1000 rows by default;
    we loop with .range() until we get an empty page.

    Returns:
        List of job dicts from the raw `jobs` table.
    """
    client = get_supabase_client()
    all_jobs = []
    offset = 0

    print("Fetching all jobs from Supabase (paginated)...")
    while True:
        try:
            response = (
                client.table("jobs")
                .select("*")
                .range(offset, offset + page_size - 1)
                .execute()
            )
            batch = getattr(response, "data", []) or []
            if not batch:
                break
            all_jobs.extend(batch)
            print(f"  Fetched {len(all_jobs)} jobs so far...")
            if len(batch) < page_size:
                break  # Last page
            offset += page_size
        except Exception as e:
            print(f"Error fetching jobs batch at offset {offset}: {e}")
            raise e

    print(f"✓ Fetched {len(all_jobs)} total raw jobs from Supabase.")
    return all_jobs


def fetch_uncleaned_jobs(page_size: int = 1000) -> list:
    """
    Fetch only jobs that have never been cleaned (cleaned_at IS NULL)
    or were updated since last clean (updated_at > cleaned_at).

    This is the key function for incremental cleaning — avoids
    re-processing thousands of already-cleaned jobs every run.
    """
    client = get_supabase_client()
    all_jobs = []
    offset = 0

    print("Fetching uncleaned/dirty jobs from Supabase...")
    while True:
        try:
            response = (
                client.table("jobs")
                .select("*")
                .is_("cleaned_at", "null")
                .eq("is_active", True)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            batch = getattr(response, "data", []) or []
            if not batch:
                break
            all_jobs.extend(batch)
            print(f"  Fetched {len(all_jobs)} uncleaned jobs so far...")
            if len(batch) < page_size:
                break
            offset += page_size
        except Exception as e:
            print(f"Error fetching uncleaned jobs at offset {offset}: {e}")
            raise e

    print(f"✓ Fetched {len(all_jobs)} uncleaned/dirty jobs.")
    return all_jobs


def mark_jobs_cleaned(job_ids: list) -> None:
    """
    Stamp cleaned_at = NOW() on the given raw job IDs.
    Called after successful cleaning + analytics upsert.
    """
    if not job_ids:
        return

    client = get_supabase_client()
    now_str = datetime.now(timezone.utc).isoformat()

    # Batch in groups of 500 to stay within URL/body limits
    batch_size = 500
    for i in range(0, len(job_ids), batch_size):
        batch = job_ids[i : i + batch_size]
        try:
            client.table("jobs").update(
                {"cleaned_at": now_str}
            ).in_("id", batch).execute()
        except Exception as e:
            print(f"  Warning: Failed to mark batch {i // batch_size + 1} as cleaned: {e}")

    print(f"✓ Marked {len(job_ids)} jobs as cleaned.")


def fetch_known_job_ids(source: str) -> set:
    """
    Return a set of all source_job_id values already in the jobs table
    for the given source. Used to pre-filter before upserting, avoiding
    unnecessary upsert overhead for already-known jobs.
    """
    client = get_supabase_client()
    all_ids = set()
    offset = 0
    page_size = 1000

    while True:
        try:
            response = (
                client.table("jobs")
                .select("source_job_id")
                .eq("source", source)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            batch = getattr(response, "data", []) or []
            if not batch:
                break
            all_ids.update(row["source_job_id"] for row in batch)
            if len(batch) < page_size:
                break
            offset += page_size
        except Exception as e:
            print(f"  Warning: Could not fetch known IDs for {source}: {e}")
            break

    return all_ids


# ═════════════════════════════════════════════════════════════
#  STALE JOB DETECTION
# ═════════════════════════════════════════════════════════════

def mark_stale_jobs(stale_days: int = 14) -> int:
    """
    Mark jobs not seen in `stale_days` as inactive.
    Returns the count of jobs marked stale.
    """
    client = get_supabase_client()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=stale_days)).isoformat()

    stale_count = 0

    # Mark in jobs table
    try:
        response = (
            client.table("jobs")
            .update({"is_active": False})
            .lt("last_seen_at", cutoff)
            .eq("is_active", True)
            .execute()
        )
        stale_count += len(getattr(response, "data", []) or [])
    except Exception as e:
        print(f"  Warning: Failed to mark stale jobs: {e}")

    # Mark in jobs_analytics table
    try:
        response = (
            client.table("jobs_analytics")
            .update({"is_active": False})
            .lt("last_seen_at", cutoff)
            .eq("is_active", True)
            .execute()
        )
    except Exception as e:
        print(f"  Warning: Failed to mark stale analytics: {e}")

    if stale_count > 0:
        print(f"✓ Marked {stale_count} jobs as inactive (not seen in {stale_days} days).")
    else:
        print(f"  No stale jobs found (all seen within {stale_days} days).")

    return stale_count


# ═════════════════════════════════════════════════════════════
#  UPSERT OPERATIONS
# ═════════════════════════════════════════════════════════════

def upsert_jobs(jobs_list: list) -> list:
    """
    Upsert a list of standardized job dicts into Supabase 'jobs' table.
    Ensures idempotency using the (source, source_job_id) constraint.
    Updates last_seen_at and updated_at on every upsert.
    """
    if not jobs_list:
        print("No jobs to insert.")
        return []

    # Deduplicate within the batch to prevent ON CONFLICT DO UPDATE errors
    unique_jobs = {}
    for job in jobs_list:
        key = (job.get("source"), job.get("source_job_id"))
        unique_jobs[key] = job

    deduped_jobs = list(unique_jobs.values())

    # Add last_seen_at and updated_at to every record
    now_str = datetime.now(timezone.utc).isoformat()
    for job in deduped_jobs:
        job["last_seen_at"] = now_str
        job["updated_at"] = now_str

    client = get_supabase_client()
    try:
        print(f"Uploading {len(deduped_jobs)} unique jobs (from {len(jobs_list)} total) to Supabase...")

        batch_size = 500
        all_data = []
        for i in range(0, len(deduped_jobs), batch_size):
            batch = deduped_jobs[i : i + batch_size]
            response = client.table("jobs").upsert(
                batch,
                on_conflict="source,source_job_id"
            ).execute()
            data = getattr(response, "data", [])
            all_data.extend(data)
            print(f"  Batch {i // batch_size + 1}: upserted {len(data)} records.")

        print(f"Successfully upserted {len(all_data)} records in Supabase.")
        return all_data
    except Exception as e:
        print(f"Error upserting jobs into Supabase: {e}")
        raise e


def upsert_analytics(jobs_list: list, batch_size: int = 500) -> int:
    """
    Batch-upsert cleaned job records into the `jobs_analytics` table.
    Uses `fingerprint` as the conflict column (ON CONFLICT DO UPDATE).
    Processes in batches to avoid request size limits.

    Args:
        jobs_list: List of cleaned job dicts from cleaning/cleaner.py
        batch_size: Number of records per upsert batch (default 500)

    Returns:
        Total number of records upserted.
    """
    if not jobs_list:
        print("No cleaned jobs to upsert into jobs_analytics.")
        return 0

    client = get_supabase_client()
    total_upserted = 0

    print(f"Upserting {len(jobs_list)} cleaned jobs into jobs_analytics (batch size: {batch_size})...")
    for i in range(0, len(jobs_list), batch_size):
        batch = jobs_list[i : i + batch_size]
        try:
            response = (
                client.table("jobs_analytics")
                .upsert(batch, on_conflict="fingerprint")
                .execute()
            )
            data = getattr(response, "data", []) or []
            total_upserted += len(data)
            print(f"  Batch {i // batch_size + 1}: upserted {len(data)} records.")
        except Exception as e:
            print(f"  Error upserting batch {i // batch_size + 1}: {e}")
            raise e

    print(f"✓ Successfully upserted {total_upserted} records into jobs_analytics.")
    return total_upserted


# ═════════════════════════════════════════════════════════════
#  DASHBOARD DATA LOADING (from Supabase directly)
# ═════════════════════════════════════════════════════════════

# Columns the dashboard needs — exclude heavy description_raw
_DASHBOARD_COLUMNS = (
    "id,fingerprint,title,company,job_category,job_field,job_sub_field,"
    "city,state,work_mode,source,min_exp,max_exp,min_salary,max_salary,"
    "salary_currency,standardized_skills,posted_at,collected_at,"
    "is_active,last_seen_at,job_url,company_logo_url,search_keywords,"
    "raw_location,raw_experience"
)


def fetch_analytics_for_dashboard(
    active_only: bool = True,
    page_size: int = 1000,
) -> list:
    """
    Fetch jobs_analytics records for the dashboard.
    Excludes heavy columns (description_raw, description, raw_skills).
    Supports pagination for large datasets.
    """
    client = get_supabase_client()
    all_rows = []
    offset = 0

    while True:
        try:
            query = (
                client.table("jobs_analytics")
                .select(_DASHBOARD_COLUMNS)
            )
            if active_only:
                query = query.eq("is_active", True)

            response = (
                query
                .order("collected_at", desc=True)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            batch = getattr(response, "data", []) or []
            if not batch:
                break
            all_rows.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        except Exception as e:
            print(f"Error fetching dashboard data at offset {offset}: {e}")
            break

    return all_rows


def fetch_all_analytics(page_size: int = 1000) -> list:
    """
    Fetch ALL records from jobs_analytics (for full file export).
    """
    client = get_supabase_client()
    all_rows = []
    offset = 0

    while True:
        try:
            response = (
                client.table("jobs_analytics")
                .select("*")
                .eq("is_active", True)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            batch = getattr(response, "data", []) or []
            if not batch:
                break
            all_rows.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        except Exception as e:
            print(f"Error fetching all analytics at offset {offset}: {e}")
            break

    return all_rows


# ═════════════════════════════════════════════════════════════
#  COLLECTION RUN LOGGING
# ═════════════════════════════════════════════════════════════

def log_collection_run(keyword: str, source: str) -> str | None:
    """
    Insert a new collection_runs row with status='running'.
    Returns the run UUID or None if the table doesn't exist yet.
    """
    client = get_supabase_client()
    try:
        response = (
            client.table("collection_runs")
            .insert({
                "keyword": keyword,
                "source": source,
                "status": "running",
            })
            .execute()
        )
        data = getattr(response, "data", []) or []
        if data:
            return data[0].get("id")
    except Exception as e:
        # Table may not exist yet — silently skip
        print(f"  Note: collection_runs logging skipped: {e}")
    return None


def update_collection_run(
    run_id: str,
    status: str = "success",
    jobs_collected: int = 0,
    jobs_new: int = 0,
    error_text: str | None = None,
) -> None:
    """Update a collection_runs row with final status."""
    if not run_id:
        return
    client = get_supabase_client()
    try:
        update_data = {
            "status": status,
            "jobs_collected": jobs_collected,
            "jobs_new": jobs_new,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        if error_text:
            update_data["error_text"] = error_text
        client.table("collection_runs").update(update_data).eq("id", run_id).execute()
    except Exception as e:
        print(f"  Note: collection_runs update skipped: {e}")


def get_recent_collection(keyword: str, source: str, cooldown_minutes: int = 60) -> dict | None:
    """
    Check if a successful collection was run for this keyword+source
    within the last `cooldown_minutes`. Returns the run dict if found.
    Used by dashboard to prevent redundant back-to-back fetches.
    """
    client = get_supabase_client()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)).isoformat()
    try:
        response = (
            client.table("collection_runs")
            .select("*")
            .eq("keyword", keyword)
            .eq("source", source)
            .eq("status", "success")
            .gte("started_at", cutoff)
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        data = getattr(response, "data", []) or []
        return data[0] if data else None
    except Exception:
        return None
