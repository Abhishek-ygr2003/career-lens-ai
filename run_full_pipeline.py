"""
CareerLens AI — run_full_pipeline.py
======================================
Orchestrator to clear all tables in Supabase and ingest/clean job market data 
for major fields in India sequentially (domain-by-domain).
"""

import os
import sys
import time
import subprocess
import argparse
from dotenv import load_dotenv

# Force UTF-8 output on Windows so emojis and symbols display correctly
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Target Domains and their query keywords
DOMAINS = {
    "Data Science & AI": [
        "data scientist",
        "machine learning engineer",
        "data engineer",
        "generative ai engineer"
    ],
    "Cybersecurity": [
        "cybersecurity analyst",
        "information security engineer",
        "penetration tester"
    ],
    "Software Engineering": [
        "software engineer",
        "full stack developer",
        "devops engineer",
        "frontend developer",
        "backend developer"
    ],
    "Healthcare": [
        "doctor",
        "nurse",
        "medical officer"
    ],
    "Sales & Marketing": [
        "sales executive",
        "business development associate",
        "digital marketing specialist"
    ]
}

def clear_supabase_tables():
    """Clear all records from Supabase tables to ensure a clean slate."""
    print("\n" + "="*60)
    print("  CLEARING DATABASE TABLES (Supabase)")
    print("="*60)
    
    # Add project root to python path to import database modules
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    try:
        from database.supabase_client import get_supabase_client
        client = get_supabase_client()
    except Exception as e:
        print(f"[!] Error initializing Supabase client: {e}")
        print("Please check your .env file credentials.")
        sys.exit(1)
        
    tables = [
        "jobs_analytics", "jobs", "collection_runs", "job_skills", 
        "skill_demand_history", "skill_gap_analysis", "salary_insights", 
        "location_insights", "company_hiring_stats"
    ]
    
    for table in tables:
        print(f"Clearing table '{table}'...")
        try:
            # Delete filter matches all UUIDs except a dummy zero UUID
            res = client.table(table).delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            deleted = len(getattr(res, "data", []) or [])
            print(f"  ✓ Cleared '{table}'. Deleted {deleted} records.")
        except Exception as e:
            print(f"  [!] Failed to clear table '{table}': {e}")
            print("Continuing pipeline...")
            
    print("="*60)
    print("  Database clearing step completed.")
    print("="*60 + "\n")

def run_keyword_pipeline(keyword: str, source: str, max_pages: int, keep_raw: bool, dry_run: bool):
    """Run main.py collection + cleaning for a specific keyword in a separate process."""
    cmd = [
        sys.executable,
        "main.py",
        "--source", source,
        "--keyword", keyword
    ]
    if max_pages:
        cmd.extend(["--max-pages", str(max_pages)])
    if keep_raw:
        cmd.append("--keep-raw")
    if dry_run:
        cmd.append("--dry-run")
        
    print(f"\n[EXEC] Running pipeline for keyword: '{keyword}'...")
    print(f"Command: {' '.join(cmd)}")
    
    # Run process and stream stdout to console
    try:
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            print(f"[!] WARNING: Pipeline for '{keyword}' failed with exit code {result.returncode}.")
            return False
        print(f"✓ Pipeline for '{keyword}' finished successfully.")
        return True
    except Exception as e:
        print(f"[!] ERROR executing pipeline for '{keyword}': {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="CareerLens AI — Multi-Domain Job Market Ingestion Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--source",
        choices=["foundit", "naukri", "adzuna", "both", "all"],
        default="all",
        help="Job board source to collect from (foundit | naukri | adzuna | both | all, default: all)."
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=3,
        help="Max pages to fetch per keyword per source (default: 3, which is ~120 jobs per keyword)."
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Skip clearing database tables before starting the ingestion."
    )
    parser.add_argument(
        "--keep-raw",
        action="store_true",
        help="Keep raw JSONB data in the jobs table (default: False)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run collection and cleaning but do not commit/upload to Supabase."
    )
    parser.add_argument(
        "--cooldown",
        type=int,
        default=5,
        help="Seconds to wait between keywords to prevent rate limiting (default: 5)."
    )
    parser.add_argument(
        "--domains",
        default=None,
        help="Comma-separated list of domains to run (e.g. 'Healthcare,Sales & Marketing'). Defaults to all domains."
    )
    args = parser.parse_args()

    # Load environmental vars
    load_dotenv()
    
    print("\n" + "="*60)
    print("       CareerLens AI — Sequential Multi-Domain Pipeline")
    print("="*60)
    print(f"  Ingestion Source     : {args.source}")
    print(f"  Max pages per search : {args.max_pages}")
    print(f"  Clear Database       : {not args.no_clear}")
    print(f"  Dry Run mode         : {args.dry_run}")
    print(f"  Cooldown delay       : {args.cooldown}s")
    print("="*60 + "\n")

    # Step 1: Clear Database if requested and not in dry-run mode
    if not args.no_clear and not args.dry_run:
        clear_supabase_tables()
    elif args.dry_run and not args.no_clear:
        print("Dry run active — skipping database clearing.")

    # Determine which domains to process
    target_domains = list(DOMAINS.keys())
    if args.domains:
        specified = [d.strip() for d in args.domains.split(",")]
        target_domains = [d for d in target_domains if d in specified]
        
    print(f"Target domains to process: {', '.join(target_domains)}\n")

    # Tracking metrics
    stats = {}
    
    # Step 2: Sequential Domain Execution
    for domain in target_domains:
        print("\n" + "#"*60)
        print(f"  STARTING DOMAIN: {domain.upper()}")
        print("#"*60 + "\n")
        
        keywords = DOMAINS[domain]
        stats[domain] = {"success": [], "failed": []}
        
        for idx, keyword in enumerate(keywords):
            if idx > 0 and args.cooldown > 0:
                print(f"Sleeping for {args.cooldown} seconds to prevent rate limits...")
                time.sleep(args.cooldown)
                
            success = run_keyword_pipeline(
                keyword=keyword,
                source=args.source,
                max_pages=args.max_pages,
                keep_raw=args.keep_raw,
                dry_run=args.dry_run
            )
            
            if success:
                stats[domain]["success"].append(keyword)
            else:
                stats[domain]["failed"].append(keyword)
                
        print(f"\nCompleted domain '{domain}'. Results: "
              f"{len(stats[domain]['success'])} succeeded, "
              f"{len(stats[domain]['failed'])} failed.")

    # Print Final Summary
    print("\n" + "="*60)
    print("               FINAL PIPELINE SUMMARY")
    print("="*60)
    for domain, res in stats.items():
        print(f"\n{domain}:")
        if res["success"]:
            print(f"  ✓ Succeeded: {', '.join(res['success'])}")
        if res["failed"]:
            print(f"  [!] Failed  : {', '.join(res['failed'])}")
    print("="*60)
    print("Sequential multi-domain pipeline completed.")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
