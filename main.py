import argparse
import json
import sys
from collector.foundit_collector import fetch_jobs, save_raw_data
from transformer.foundit_transformer import transform_jobs
from database.supabase_client import upsert_jobs

def parse_args():
    parser = argparse.ArgumentParser(description="CareerLens AI Job Pipeline Orchestrator")
    parser.add_argument(
        "--dry-run", 
        action="store_true", 
        help="Run fetch and transform steps, but output standardized schemas to console instead of uploading to Supabase."
    )
    return parser.parse_args()

def main():
    args = parse_args()
    
    print("=== CareerLens AI Job Pipeline Started ===")
    
    try:
        # Step 1: Fetch
        raw_data = fetch_jobs()
        print(f"Fetched raw data payload successfully.")
        
        # Save raw snapshot
        saved_path = save_raw_data(raw_data)
        print(f"Raw snapshot stored at: {saved_path}")
        
        # Step 2: Transform
        print("Transforming jobs to standardized CareerLens schema...")
        transformed_jobs = transform_jobs(raw_data)
        num_transformed = len(transformed_jobs)
        print(f"Successfully transformed {num_transformed} jobs.")
        
        # Step 3: Load (or print if dry run)
        if args.dry_run:
            print("\n=== DRY RUN MODE: Standardized Job Samples (First 2) ===")
            if transformed_jobs:
                for idx, job in enumerate(transformed_jobs[:2]):
                    print(f"\n--- Job Sample #{idx + 1} ---")
                    # Exclude printing full raw_data dict for cleaner terminal output
                    display_job = {k: v for k, v in job.items() if k != "raw_data"}
                    print(json.dumps(display_job, indent=2))
            else:
                print("No jobs transformed to display.")
            print("\nDry run completed successfully. No data was pushed to Supabase.")
        else:
            print("Connecting to Supabase and uploading...")
            upserted_records = upsert_jobs(transformed_jobs)
            print(f"Pipeline finished! Successfully loaded/updated {len(upserted_records)} jobs in Supabase.")
            
    except Exception as e:
        print(f"\nPipeline execution failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
