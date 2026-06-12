"""
CareerLens AI - collector/naukri_collector.py
==============================================
Fetches jobs from Naukri's internal search API with fully automatic
session management:

  1. On startup, load cached nkparam + Cookie from .env (if present).
  2. If the API returns 406 (anti-bot challenge), automatically launch
     a stealth Playwright browser to capture fresh headers, then retry.
  3. The auto-refresh loop runs up to MAX_AUTO_REFRESHES times before
     giving up, so long-running collection jobs are uninterrupted.

No manual cookie copying is ever required.
"""

import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv
from curl_cffi import requests as cffi_requests
from collector.exceptions import SessionExpiredError

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv()

MAX_AUTO_REFRESHES  = 2   # how many times we'll auto-refresh headers per run
REQUEST_RETRIES     = 3   # retries per page on transient errors
PAGE_DELAY_SECS     = 1.5 # polite delay between pages


# ---------------------------------------------------------------------------
# System status helpers
# ---------------------------------------------------------------------------

def _status_file_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "system_status.json"
    )


def update_system_status(source: str, is_expired: bool):
    """Persist credential health to data/system_status.json."""
    status_file = _status_file_path()
    status: dict = {}

    if os.path.exists(status_file):
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                status = json.load(f)
        except Exception:
            pass

    status.setdefault(source, {})
    status[source]["credential_expired"] = is_expired
    status[source]["last_updated"]       = datetime.now().isoformat()

    os.makedirs(os.path.dirname(status_file), exist_ok=True)
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)


# ---------------------------------------------------------------------------
# Header helpers
# ---------------------------------------------------------------------------

def _load_session_headers() -> tuple[str, str]:
    """Return (nkparam, cookie) from environment (may be empty strings)."""
    # Re-read env so we pick up values written by playwright_stealth
    load_dotenv(override=True)
    return (
        os.getenv("NAUKRI_NKPARAM", ""),
        os.getenv("NAUKRI_COOKIE",  ""),
    )


def _build_headers(keyword: str, nkparam: str, cookie: str) -> dict:
    kw_slug = keyword.lower().strip().replace(" ", "-")
    seo_key = f"{kw_slug}-jobs"
    referer = f"https://www.naukri.com/{seo_key}?k={keyword.replace(' ', '%20')}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "appid":      "109",
        "systemid":   "Naukri",
        "clientid":   "d3skt0p",
        "gid":        "LOCATION,INDUSTRY,EDUCATION,FAREA_ROLE",
        "Accept":     "application/json",
        "referer":    referer,
    }
    if nkparam:
        headers["nkparam"] = nkparam
    if cookie:
        headers["Cookie"] = cookie

    return headers


def _auto_refresh_headers() -> tuple[str, str]:
    """
    Run the Playwright stealth browser, write fresh headers to .env,
    and return (nkparam, cookie).
    """
    from collector.playwright_stealth import refresh_naukri_headers
    result = refresh_naukri_headers()
    if result:
        return result["nkparam"], result["cookie"]
    return "", ""


# ---------------------------------------------------------------------------
# Core fetch
# ---------------------------------------------------------------------------

def fetch_jobs(keyword: str = "ai ml engineer", max_pages: int | None = None) -> dict:
    """
    Fetch jobs from Naukri for the given keyword.

    Args:
        keyword:   Search keyword, e.g. 'data scientist', 'mlops engineer'.
        max_pages: Hard cap on pages to fetch.
                   None = dynamic (auto-detect from total, capped at 100).

    Returns:
        dict with keys: jobDetails, keyword, collectedJobs, totalJobsAvailable
    """
    url = "https://www.naukri.com/jobapi/v3/search"

    # ------------------------------------------------------------------
    # Initial headers - try from .env first; if missing, auto-refresh now
    # ------------------------------------------------------------------
    nkparam, cookie = _load_session_headers()
    if not nkparam:
        print("No cached nkparam found. Fetching fresh headers via browser...")
        nkparam, cookie = _auto_refresh_headers()

    kw_slug = keyword.lower().strip().replace(" ", "-")
    seo_key = f"{kw_slug}-jobs"

    params = {
        "noOfResults": 20,
        "urlType":     "search_by_keyword",
        "searchType":  "adv",
        "keyword":     keyword,
        "pageNo":      1,
        "k":           keyword,
        "seoKey":      seo_key,
        "src":         "directSearch",
    }

    all_jobs:     list  = []
    page:         int   = 1
    total_jobs:   int   = 0
    refreshes:    int   = 0          # how many auto-refreshes we've done
    max_pages_to_fetch = 1_000 if max_pages is None else max_pages

    session = cffi_requests.Session()

    # Warm up session with a homepage visit (helps cookie propagation)
    print("Initializing session on Naukri homepage...")
    try:
        session.get(
            "https://www.naukri.com/",
            headers={"User-Agent": _build_headers(keyword, "", "")["User-Agent"]},
            impersonate="chrome124",
            timeout=15,
        )
    except Exception as warm_err:
        print(f"  [!] Homepage warm-up skipped: {warm_err}")

    # ------------------------------------------------------------------
    # Pagination loop
    # ------------------------------------------------------------------
    while page <= max_pages_to_fetch:
        print(
            f"Fetching Naukri jobs [{keyword!r}] - "
            f"Page {page}/{max_pages_to_fetch if max_pages is not None else 'dynamic'}..."
        )
        params["pageNo"] = page
        headers = _build_headers(keyword, nkparam, cookie)

        data       = None
        got_406    = False

        # ---- Retry loop per page ----
        for attempt in range(REQUEST_RETRIES):
            try:
                response = session.get(
                    url,
                    params=params,
                    headers=headers,
                    impersonate="chrome124",
                    timeout=20,
                )

                # ---- Anti-bot blocked ----
                if response.status_code == 406:
                    got_406 = True
                    update_system_status("naukri", is_expired=True)
                    break  # exit retry loop; handle below

                response.raise_for_status()
                update_system_status("naukri", is_expired=False)
                data = response.json()
                break  # success

            except Exception as req_err:
                if attempt < REQUEST_RETRIES - 1:
                    wait = 2 ** attempt
                    print(f"  Request error: {req_err}. Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    if page == 1:
                        raise
                    print(f"  [!] Page {page} failed after {REQUEST_RETRIES} attempts - skipping.")

        # ---- Handle 406: auto-refresh and retry the same page ----
        if got_406:
            if refreshes >= MAX_AUTO_REFRESHES:
                update_system_status("naukri", is_expired=True)
                raise SessionExpiredError(
                    f"Naukri blocked the request (406) after {refreshes} auto-refresh attempts. "
                    "Try running the pipeline again later."
                )

            print(
                f"\n[!] Naukri returned 406 (anti-bot). "
                f"Auto-refreshing headers (attempt {refreshes + 1}/{MAX_AUTO_REFRESHES})..."
            )
            nkparam, cookie = _auto_refresh_headers()
            refreshes += 1

            if not nkparam:
                raise SessionExpiredError(
                    "Auto-refresh failed to capture fresh headers. "
                    "Check your internet connection and try again."
                )

            print("  [OK] Headers refreshed. Retrying page...")
            continue  # retry same page with new headers

        # ---- No data after retries ----
        if data is None:
            print(f"  Skipping page {page} - returning jobs collected so far.")
            break

        # ---- Dynamic page count on first page ----
        if page == 1 and max_pages is None:
            total_jobs         = data.get("noOfJobs", 0)
            limit              = params.get("noOfResults", 20)
            calculated_pages   = (total_jobs + limit - 1) // limit
            max_pages_to_fetch = min(calculated_pages, 100)
            print(f"  Total jobs available: {total_jobs}. Fetching up to {max_pages_to_fetch} pages.")

        jobs = data.get("jobDetails", [])
        if not jobs:
            print(f"  No jobs on page {page}. Ending pagination.")
            break

        print(f"  [OK] Page {page}: {len(jobs)} jobs.")
        all_jobs.extend(jobs)

        if len(jobs) < params["noOfResults"]:
            print("  Fewer results than limit - assuming last page.")
            break

        if page < max_pages_to_fetch:
            time.sleep(PAGE_DELAY_SECS)

        page += 1

    return {
        "jobDetails":          all_jobs,
        "keyword":             keyword,
        "collectedJobs":       len(all_jobs),
        "totalJobsAvailable":  total_jobs if total_jobs > 0 else len(all_jobs),
    }


# ---------------------------------------------------------------------------
# Save raw data
# ---------------------------------------------------------------------------

def save_raw_data(data: dict, keyword: str = "ai_ml_engineer") -> str:
    """
    Save raw API response to data/raw/naukri_<slug>_<date>.json.
    Returns the file path.
    """
    print("Saving raw Naukri data...")
    date_str = datetime.now().strftime("%Y_%m_%d")

    kw      = data.get("keyword", keyword)
    kw_slug = kw.lower().strip().replace(" ", "_").replace("/", "_")
    filename = f"naukri_{kw_slug}_{date_str}.json"

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_dir      = os.path.join(project_root, "data", "raw")
    os.makedirs(raw_dir, exist_ok=True)

    filepath = os.path.join(raw_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    print(f"  [OK] Raw data saved -> {filepath}")
    return filepath


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Naukri standalone collector")
    parser.add_argument(
        "--keyword", default="ai ml engineer",
        help="Search keyword (default: 'ai ml engineer')"
    )
    parser.add_argument(
        "--max-pages", type=int, default=None,
        help="Max pages to fetch (default: dynamic)"
    )
    parser.add_argument(
        "--refresh-headers", action="store_true",
        help="Force a browser-based header refresh before collecting."
    )
    args = parser.parse_args()

    if args.refresh_headers:
        print("Forcing header refresh...")
        _auto_refresh_headers()

    try:
        data     = fetch_jobs(keyword=args.keyword, max_pages=args.max_pages)
        jobs     = data.get("jobDetails", [])
        num_jobs = len(jobs)
        print(f"\nFound {num_jobs} jobs in total.")

        filepath = save_raw_data(data)

        print(f"\nSummary:")
        print(f"  Jobs collected : {num_jobs}")
        print(f"  Raw file       : {filepath}")

        if jobs:
            first = jobs[0]
            print("\nFirst job:")
            print(f"  Title   : {first.get('title')}")
            print(f"  Company : {first.get('companyName')}")
            print(f"  Skills  : {first.get('tagsAndSkills')}")

            # Save schema keys
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            docs_dir     = os.path.join(project_root, "docs")
            os.makedirs(docs_dir, exist_ok=True)
            schema_path  = os.path.join(docs_dir, "naukri_schema.txt")
            with open(schema_path, "w", encoding="utf-8") as f:
                for key in sorted(first.keys()):
                    f.write(f"{key}\n")
            print(f"  Schema  : {schema_path}")

    except SessionExpiredError as e:
        print(f"\n[!] Session error: {e}")
    except Exception as e:
        print(f"\n[!] An error occurred: {e}")
        raise


if __name__ == "__main__":
    main()
