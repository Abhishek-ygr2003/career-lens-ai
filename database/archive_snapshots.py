"""
CareerLens AI — database/archive_snapshots.py
============================================
Compiles static historical snapshots (job field, city share, skill demand) 
at the end of each month and upserts them to `monthly_snapshots` in Supabase.
Supports backfilling past months via CLI arguments.
"""

import sys
import os
import argparse
import pandas as pd
from datetime import datetime, date
from dotenv import load_dotenv

# Ensure project root is in Python path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

load_dotenv()

from database.supabase_client import get_supabase_client


def archive_month(target_month_str: str = None) -> None:
    """
    Query jobs_analytics within target_month and compile stats.
    Saves results to the monthly_snapshots table.
    """
    # Determine target month start date
    if target_month_str:
        try:
            target_date = datetime.strptime(target_month_str, "%Y-%m").date().replace(day=1)
        except ValueError:
            print(f"[!] Error: Invalid month format '{target_month_str}'. Use YYYY-MM.")
            sys.exit(1)
    else:
        target_date = date.today().replace(day=1)

    start_date = target_date.isoformat()
    
    # Calculate end of target month (exclusive)
    if target_date.month == 12:
        end_date = date(target_date.year + 1, 1, 1).isoformat()
    else:
        end_date = date(target_date.year, target_date.month + 1, 1).isoformat()

    print(f"\n============================================================")
    print(f"  ARCHIVING MONTHLY SNAPSHOT: {target_date.strftime('%B %Y')}")
    print(f"  Date Range: {start_date} to {end_date} (exclusive)")
    print(f"============================================================")

    client = get_supabase_client()

    # Fetch all records collected in target month
    print("Fetching listings from jobs_analytics...")
    try:
        response = (
            client.table("jobs_analytics")
            .select("job_field,city,standardized_skills,min_salary,max_salary")
            .gte("collected_at", start_date)
            .lt("collected_at", end_date)
            .execute()
        )
        data = getattr(response, "data", []) or []
    except Exception as e:
        print(f"[!] Database error fetching listings: {e}")
        sys.exit(1)

    if not data:
        print(f"[!] No listings found for the period {start_date} to {end_date}.")
        print("Skipping monthly snapshot archiving.")
        return

    print(f"Loaded {len(data)} job listings. Processing metrics...")
    df = pd.DataFrame(data)

    # Coerce salary and compute midpoint
    df["min_salary"] = pd.to_numeric(df["min_salary"], errors="coerce")
    df["max_salary"] = pd.to_numeric(df["max_salary"], errors="coerce")
    df["salary_mid"] = df.apply(
        lambda r: r["min_salary"] if pd.isna(r["max_salary"]) else (
            r["max_salary"] if pd.isna(r["min_salary"]) else (r["min_salary"] + r["max_salary"]) / 2
        ), axis=1
    )

    snapshot_records = []

    # 1. Job Field Share
    if "job_field" in df.columns:
        field_groups = df.groupby("job_field")
        for field, grp in field_groups:
            if not field or field.strip().lower() == "other":
                continue
            count = len(grp)
            avg_sal = grp["salary_mid"].mean()
            snapshot_records.append({
                "month": start_date,
                "metric_type": "field_share",
                "metric_name": field.strip(),
                "job_count": count,
                "avg_salary": float(avg_sal) if not pd.isna(avg_sal) else None
            })

    # 2. City Share
    if "city" in df.columns:
        city_groups = df.groupby("city")
        for city, grp in city_groups:
            if not city or city.strip().lower() == "unknown":
                continue
            count = len(grp)
            avg_sal = grp["salary_mid"].mean()
            snapshot_records.append({
                "month": start_date,
                "metric_type": "city_share",
                "metric_name": city.strip(),
                "job_count": count,
                "avg_salary": float(avg_sal) if not pd.isna(avg_sal) else None
            })

    # 3. Skill Demand
    if "standardized_skills" in df.columns:
        # Explode list-like skills
        exploded = df.explode("standardized_skills").dropna(subset=["standardized_skills"])
        if not exploded.empty:
            skill_groups = exploded.groupby("standardized_skills")
            for skill, grp in skill_groups:
                count = len(grp)
                avg_sal = grp["salary_mid"].mean()
                snapshot_records.append({
                    "month": start_date,
                    "metric_type": "skill_demand",
                    "metric_name": skill.strip(),
                    "job_count": count,
                    "avg_salary": float(avg_sal) if not pd.isna(avg_sal) else None
                })

    if not snapshot_records:
        print("[!] No metrics computed. Skipping upload.")
        return

    print(f"Upserting {len(snapshot_records)} snapshot metrics into `monthly_snapshots`...")
    try:
        # Split into batches of 1000 for safe insertion
        batch_size = 1000
        for i in range(0, len(snapshot_records), batch_size):
            batch = snapshot_records[i : i + batch_size]
            client.table("monthly_snapshots").upsert(
                batch,
                on_conflict="month,metric_type,metric_name"
            ).execute()
        print(f"✓ Successfully archived monthly snapshot metrics for {target_date.strftime('%B %Y')}.")
    except Exception as e:
        print(f"[!] Error uploading snapshots: {e}")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CareerLens AI — Monthly Analytics Snapshot Archiver",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--month",
        type=str,
        default=None,
        help="Target month to archive in YYYY-MM format (default: current month)."
    )
    args = parser.parse_args()

    archive_month(args.month)


if __name__ == "__main__":
    main()
