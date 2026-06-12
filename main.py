"""
CareerLens AI — main.py
========================
Pipeline orchestrator with support for:
  - Incremental cleaning (only process new/dirty jobs)
  - Parallel collection for --source both
  - Stale job detection & sweep
  - Raw file cleanup (retention policy)
  - Collection run logging
  - Pre-filter known job IDs before upsert
"""

import argparse
import json
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

# Force UTF-8 output on Windows so Unicode chars (checkmarks, arrows) print correctly
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from database.supabase_client import (
    upsert_jobs,
    fetch_all_jobs,
    fetch_uncleaned_jobs,
    mark_jobs_cleaned,
    mark_stale_jobs,
    fetch_known_job_ids,
    fetch_all_analytics,
    upsert_analytics,
    log_collection_run,
    update_collection_run,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="CareerLens AI — Job Market Analytics Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --source foundit                  Collect, transform, load, then auto-clean (incremental)
  python main.py --source naukri                   Same for Naukri
  python main.py --source both --keyword "sales"   Collect from both sources in parallel
  python main.py --source foundit --dry-run        Show output without uploading to Supabase
  python main.py --clean-only                      Re-run incremental cleaning on dirty jobs in DB
  python main.py --clean-only --full-clean          Force re-clean ALL jobs (not just dirty ones)
        """,
    )
    parser.add_argument(
        "--source",
        choices=["foundit", "naukri", "both"],
        default=None,
        help="Job board source to collect from (foundit | naukri | both).",
    )
    parser.add_argument(
        "--keyword",
        default=None,
        help=(
            "Search keyword to collect (e.g. 'data scientist', 'mlops engineer'). "
            "Defaults to 'ai engineer' for foundit and 'ai ml engineer' for naukri."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and transform but print to console instead of uploading.",
    )
    parser.add_argument(
        "--clean-only",
        action="store_true",
        help="Skip collection. Re-run cleaning pipeline on dirty jobs in the DB.",
    )
    parser.add_argument(
        "--full-clean",
        action="store_true",
        help="Used with --clean-only: re-clean ALL jobs, not just dirty/new ones.",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Skip the auto-clean step after collection (useful for faster iteration).",
    )
    parser.add_argument(
        "--keep-raw",
        action="store_true",
        help="Keep raw_data JSONB in the jobs table (default: strip to save storage).",
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=14,
        help="Days since last_seen_at before marking a job as inactive (default: 14).",
    )
    parser.add_argument(
        "--raw-retention-days",
        type=int,
        default=7,
        help="Delete raw JSON files older than N days (default: 7).",
    )
    return parser.parse_args()


# ═════════════════════════════════════════════════════════════
#  RAW FILE CLEANUP
# ═════════════════════════════════════════════════════════════

def cleanup_old_raw_files(keep_days: int = 7) -> int:
    """
    Delete raw JSON files older than `keep_days` from data/raw/.
    Returns count of deleted files.
    """
    raw_dir = Path(__file__).parent / "data" / "raw"
    if not raw_dir.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=keep_days)
    deleted = 0
    for f in raw_dir.glob("*.json"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
                deleted += 1
        except Exception:
            pass

    if deleted > 0:
        print(f"  ✓ Cleaned up {deleted} raw files older than {keep_days} days.")
    return deleted


# ═════════════════════════════════════════════════════════════
#  COLLECTION
# ═════════════════════════════════════════════════════════════

def run_collection(source: str, keyword: str, dry_run: bool, keep_raw: bool = False) -> tuple:
    """Collect → Transform → Load raw jobs into the `jobs` table.

    Returns:
        (transformed_jobs: list, dry_run: bool, jobs_new: int)
    """
    print(f"\n{'='*60}")
    print(f"  STEP 1 & 2: Collect & Transform [{source.upper()}] keyword={keyword!r}")
    print(f"{'='*60}")

    # Log collection run
    run_id = log_collection_run(keyword, source)

    try:
        if source == "foundit":
            from collector.foundit_collector import fetch_jobs, save_raw_data
            from transformer.foundit_transformer import transform_jobs
        elif source == "naukri":
            from collector.naukri_collector import fetch_jobs, save_raw_data
            from transformer.naukri_transformer import transform_jobs
        else:
            raise ValueError(f"Unknown source: {source}")

        # Fetch
        raw_data = fetch_jobs(keyword=keyword)
        print("Raw data payload fetched successfully.")

        # Save raw snapshot
        saved_path = save_raw_data(raw_data)
        print(f"Raw snapshot saved -> {saved_path}")

        # Transform
        print("\nTransforming jobs to standardized CareerLens schema...")
        transformed_jobs = transform_jobs(raw_data)
        total_transformed = len(transformed_jobs)
        print(f"Transformed {total_transformed} jobs.")

        # ── Strip raw_data to save Supabase storage ──────────
        if not keep_raw:
            for job in transformed_jobs:
                job.pop("raw_data", None)

        # ── Pre-filter: skip already-known job IDs ────────────
        jobs_new = total_transformed
        if not dry_run:
            known_ids = fetch_known_job_ids(source)
            if known_ids:
                new_jobs = [j for j in transformed_jobs if j.get("source_job_id") not in known_ids]
                existing_jobs = [j for j in transformed_jobs if j.get("source_job_id") in known_ids]
                jobs_new = len(new_jobs)
                print(f"  Pre-filter: {jobs_new} new jobs, {len(existing_jobs)} already known.")

                # Still upsert all to update last_seen_at, but log the split
            else:
                print("  Pre-filter: no existing jobs found (fresh DB or new source).")

        # Load or dry-run
        if dry_run:
            print(f"\n{'='*60}")
            print("  DRY RUN — Standardized Job Samples (First 2)")
            print(f"{'='*60}")
            for idx, job in enumerate(transformed_jobs[:2]):
                print(f"\n--- Job Sample #{idx + 1} ---")
                display_job = {k: v for k, v in job.items() if k != "raw_data"}
                print(json.dumps(display_job, indent=2, default=str))
            print("\nDry run complete. Nothing uploaded to Supabase.")
        else:
            print(f"\n{'='*60}")
            print("  STEP 3: Load into jobs table")
            print(f"{'='*60}")
            upserted = upsert_jobs(transformed_jobs)
            print(f"Loaded/updated {len(upserted)} jobs in the `jobs` table.")

        # Update collection run
        update_collection_run(
            run_id,
            status="success",
            jobs_collected=total_transformed,
            jobs_new=jobs_new,
        )

        return transformed_jobs, dry_run, jobs_new

    except Exception as e:
        print(f"\n[!] WARNING: Collection failed for source '{source}'. Error: {e}")
        print(f"[!] Skipping {source} and continuing pipeline...\n")
        update_collection_run(run_id, status="failed", error_text=str(e))
        return [], dry_run, 0


def run_collection_parallel(keyword: str, dry_run: bool, keep_raw: bool = False) -> tuple:
    """Run collection for both sources in parallel using ThreadPoolExecutor."""
    print(f"\n{'='*60}")
    print(f"  PARALLEL COLLECTION: foundit + naukri, keyword={keyword!r}")
    print(f"{'='*60}")

    all_jobs = []
    total_new = 0

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(run_collection, "foundit", keyword, dry_run, keep_raw): "foundit",
            pool.submit(run_collection, "naukri", keyword, dry_run, keep_raw): "naukri",
        }
        for future in as_completed(futures):
            source = futures[future]
            try:
                jobs, _, jobs_new = future.result()
                all_jobs.extend(jobs)
                total_new += jobs_new
                print(f"  [{source}] collected {len(jobs)} jobs ({jobs_new} new).")
            except Exception as e:
                print(f"  [{source}] failed: {e}")

    return all_jobs, dry_run, total_new


# ═════════════════════════════════════════════════════════════
#  CLEANING
# ═════════════════════════════════════════════════════════════

def run_cleaning(
    dry_run: bool = False,
    incremental: bool = True,
    keyword: str | None = None,
):
    """Fetch dirty jobs → Clean → Upsert into jobs_analytics → Export files."""
    print(f"\n{'='*60}")
    mode = "INCREMENTAL" if incremental else "FULL"
    print(f"  STEP 4: Clean & Standardize → jobs_analytics [{mode}]")
    print(f"{'='*60}")

    from cleaning.cleaner import clean_jobs, export_to_files

    # Fetch raw jobs — incremental (only dirty) or full
    if incremental:
        raw_jobs = fetch_uncleaned_jobs()
    else:
        raw_jobs = fetch_all_jobs()

    if not raw_jobs:
        if incremental:
            print("All jobs already cleaned. Nothing to do.")
        else:
            print("No raw jobs found in the `jobs` table. Run collection first.")
        return

    # Clean and deduplicate
    cleaned = clean_jobs(raw_jobs, search_keyword=keyword)

    # Show sample in dry-run mode
    if dry_run:
        print(f"\n{'='*60}")
        print("  DRY RUN — Cleaned Job Samples (First 2)")
        print(f"{'='*60}")
        for idx, job in enumerate(cleaned[:2]):
            print(f"\n--- Cleaned Job Sample #{idx + 1} ---")
            display = {k: v for k, v in job.items() if k not in ("description_raw",)}
            print(json.dumps(display, indent=2, default=str))
        print("\nDry run — skipping Supabase upsert and file export.")
        return

    # Upsert to jobs_analytics
    print(f"\n{'='*60}")
    print("  STEP 5: Upsert into jobs_analytics")
    print(f"{'='*60}")
    total = upsert_analytics(cleaned)

    # Mark source jobs as cleaned (only for incremental mode)
    if incremental:
        job_ids = [j["id"] for j in raw_jobs if j.get("id")]
        mark_jobs_cleaned(job_ids)

    # Export: rebuild full export from jobs_analytics
    print(f"\n{'='*60}")
    print("  STEP 6: Export to data/processed/")
    print(f"{'='*60}")
    # Fetch complete analytics for file export
    all_analytics = fetch_all_analytics()
    if all_analytics:
        paths = export_to_files(all_analytics)
        print(f"  CSV  -> {paths['csv']}")
        print(f"  JSON -> {paths['json']}")
    else:
        # Fallback: export just the current batch
        paths = export_to_files(cleaned)
        print(f"  CSV  -> {paths['csv']}")
        print(f"  JSON -> {paths['json']}")

    print(f"\n{'='*60}")
    print(f"  ✓ Analytics warehouse updated: {total} jobs processed this run")
    print(f"{'='*60}")


# ═════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════

def main():
    args = parse_args()

    if not args.source and not args.clean_only:
        print("Error: You must specify --source [foundit|naukri|both] or --clean-only.")
        print("Run `python main.py --help` for usage.")
        sys.exit(1)

    # Resolve default keyword per source
    if args.keyword:
        keyword = args.keyword
    elif args.source == "naukri":
        keyword = "ai ml engineer"
    else:
        keyword = "ai engineer"

    print(f"\n{'='*60}")
    print("       CareerLens AI — Job Market Analytics Pipeline")
    print(f"{'='*60}")

    try:
        if args.clean_only:
            # Only run the cleaning step against what's already in the DB
            run_cleaning(
                dry_run=args.dry_run,
                incremental=not args.full_clean,
                keyword=keyword,
            )
        else:
            # Full pipeline: collect → transform → load → clean
            if args.source == "both":
                run_collection_parallel(keyword, dry_run=args.dry_run, keep_raw=args.keep_raw)
            else:
                run_collection(args.source, keyword=keyword, dry_run=args.dry_run, keep_raw=args.keep_raw)

            if not args.no_clean and not args.dry_run:
                run_cleaning(dry_run=False, incremental=True, keyword=keyword)
            elif args.dry_run:
                # Also show cleaned sample in dry-run mode
                run_cleaning(dry_run=True, keyword=keyword)

        # ── Post-pipeline: staleness sweep ────────────────────
        if not args.dry_run and not args.clean_only:
            print(f"\n{'='*60}")
            print(f"  STEP 7: Stale Job Sweep (>{args.stale_days} days unseen)")
            print(f"{'='*60}")
            mark_stale_jobs(stale_days=args.stale_days)

        # ── Post-pipeline: raw file cleanup ───────────────────
        if not args.dry_run:
            cleanup_old_raw_files(keep_days=args.raw_retention_days)

        print(f"\n{'='*60}")
        print("  Pipeline completed successfully.")
        print(f"{'='*60}\n")

    except Exception as e:
        print(f"\nPipeline failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
