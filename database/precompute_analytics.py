import sys
import os
import json
import pandas as pd
import numpy as np
from datetime import date, datetime
from dotenv import load_dotenv

# Force UTF-8 output on Windows so Unicode chars print correctly
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure project root is in python path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

load_dotenv()

SUPPLY_DATA = {
    "communication": {"display": "Communication", "supply": 75, "streams": ["all", "biz", "fin", "design"], "db_keys": ["communication"]},
    "excel": {"display": "Excel", "supply": 68, "streams": ["all", "biz", "fin", "cs"], "db_keys": ["excel"]},
    "python": {"display": "Python", "supply": 45, "streams": ["all", "cs", "data", "elec"], "db_keys": ["python"]},
    "sql": {"display": "SQL", "supply": 42, "streams": ["all", "cs", "data", "fin"], "db_keys": ["sql"]},
    "javascript": {"display": "JavaScript", "supply": 48, "streams": ["all", "cs", "design"], "db_keys": ["javascript", "typescript"]},
    "java": {"display": "Java", "supply": 40, "streams": ["all", "cs"], "db_keys": ["java"]},
    "machine learning": {"display": "Machine Learning", "supply": 18, "streams": ["all", "cs", "data", "elec"], "db_keys": ["machine learning", "deep learning", "tensorflow", "pytorch"]},
    "aws / cloud": {"display": "AWS / Cloud", "supply": 22, "streams": ["all", "cs", "data", "elec"], "db_keys": ["aws", "azure", "gcp"]},
    "devops / docker": {"display": "DevOps / Docker", "supply": 15, "streams": ["all", "cs"], "db_keys": ["devops", "docker", "kubernetes", "ci/cd"]},
    "generative ai": {"display": "Generative AI", "supply": 6, "streams": ["all", "cs", "data", "biz", "design"], "db_keys": ["gen ai", "large language models", "retrieval augmented generation", "langchain", "prompt engineering"]},
    "cybersecurity": {"display": "Cybersecurity", "supply": 10, "streams": ["all", "cs", "elec"], "db_keys": ["cybersecurity"]},
    "statistics": {"display": "Statistics", "supply": 25, "streams": ["all", "data", "fin"], "db_keys": ["statistics"]},
    "project management": {"display": "Project Management", "supply": 32, "streams": ["all", "biz", "cs"], "db_keys": ["project management", "agile", "scrum"]},
    "ui/ux design": {"display": "UI/UX Design", "supply": 14, "streams": ["all", "design", "biz"], "db_keys": ["ui/ux design", "figma"]},
    "c / c++": {"display": "C / C++", "supply": 35, "streams": ["all", "cs", "elec"], "db_keys": ["c++"]},
    "embedded systems": {"display": "Embedded Systems", "supply": 12, "streams": ["all", "elec"], "db_keys": ["embedded systems"]},
    "data engineering": {"display": "Data Engineering", "supply": 16, "streams": ["all", "data", "cs"], "db_keys": ["data engineering"]},
    "tableau / powerbi": {"display": "Tableau / PowerBI", "supply": 20, "streams": ["all", "biz", "fin", "data"], "db_keys": ["tableau", "power bi"]}
}


def load_supply_data():
    """Load taxonomy from the database, falling back to static config."""
    try:
        from database.supabase_client import get_supabase_client
        client = get_supabase_client()
        res = client.table("skill_taxonomy").select("*").execute()
        data = getattr(res, "data", []) or []
        if not data:
            return SUPPLY_DATA
        
        db_supply = {}
        for row in data:
            skill_name = row["skill_name"]
            key = skill_name.lower().strip()
            db_supply[key] = {
                "display": skill_name,
                "supply": float(row["supply_score"]),
                "streams": [row["stream"]] if isinstance(row["stream"], str) else row["stream"],
                "db_keys": [a.lower().strip() for a in (row.get("aliases") or [skill_name])]
            }
        return db_supply
    except Exception as e:
        print(f"  [Info] Could not query skill_taxonomy table: {e}. Using local dictionary.")
        return SUPPLY_DATA


def get_experience_band_simple(min_exp):
    if pd.isna(min_exp):
        return "Unknown"
    min_exp = int(min_exp)
    if min_exp <= 2:
        return "Fresher"
    elif min_exp <= 5:
        return "Junior"
    elif min_exp <= 8:
        return "Mid"
    else:
        return "Senior"


def run_precomputation():
    """
    Orchestrate analytics precomputations. Prioritizes database-side PL/pgSQL RPC
    for speed and memory safety. Falls back to Pandas calculations for local/offline execution.
    """
    print("Precalculating labor market intelligence metrics...")
    
    from database.supabase_client import get_supabase_client
    
    # ── Attempt Supabase RPC (Priority 3) ─────────────────────────
    try:
        client = get_supabase_client()
        print("  Triggering PL/pgSQL database precomputations (RPC)...")
        client.rpc("run_precompute_analytics", {}).execute()
        print("  ✓ Stored procedure executed successfully inside PostgreSQL.")
        
        # Pull generated data to update the local fallback backup files
        print("  Updating local backup files from database tables...")
        sdh = client.table("skill_demand_history").select("*").order("date").execute()
        sga = client.table("skill_gap_analysis").select("*").order("date").execute()
        sal = client.table("salary_insights").select("*").order("date").execute()
        loc = client.table("location_insights").select("*").order("date").execute()
        comp = client.table("company_hiring_stats").select("*").order("date").execute()
        
        # Get count of active jobs in database
        active_res = client.table("jobs_analytics").select("id", count="exact").eq("is_active", True).limit(1).execute()
        total_jobs = getattr(active_res, "count", 0) or 0
        
        today_str = date.today().isoformat()
        local_data = {
            "skill_demand_history": getattr(sdh, "data", []) or [],
            "skill_gap_analysis": getattr(sga, "data", []) or [],
            "salary_insights": getattr(sal, "data", []) or [],
            "location_insights": getattr(loc, "data", []) or [],
            "company_hiring_stats": getattr(comp, "data", []) or [],
            "freshness": {
                "total_jobs": total_jobs,
                "unique_companies": len(set(c.get("company") for c in (getattr(comp, "data", []) or []))),
                "sources": ["naukri", "foundit", "adzuna"],
                "last_collected": today_str,
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        }
        
        save_local_fallback(local_data)
        return
        
    except Exception as e:
        print(f"  [Warning] Database precomputation failed/unavailable: {e}")
        print("  Falling back to in-memory Pandas calculations...")

    # ── Fallback Pandas aggregations (local execution) ───────────
    from database.supabase_client import fetch_all_analytics
    
    raw_analytics = []
    try:
        raw_analytics = fetch_all_analytics()
    except Exception as e:
        print(f"Supabase fetch failed: {e}")
        
    if not raw_analytics:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        local_path = os.path.join(project_root, "data", "processed", "jobs_analytics.json")
        print(f"Supabase fetch returned no records. Trying local fallback: {local_path}")
        if os.path.exists(local_path):
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    raw_analytics = json.load(f)
                print(f"Successfully loaded {len(raw_analytics)} records from local fallback.")
            except Exception as err:
                print(f"Failed to read local fallback file: {err}")
                
    if not raw_analytics:
        print("[Warning] No records found. Skipping precomputations.")
        return
        
    df = pd.DataFrame(raw_analytics)
    taxonomy = load_supply_data()
    
    # Coerce fields
    df["min_salary"] = pd.to_numeric(df["min_salary"], errors="coerce")
    df["max_salary"] = pd.to_numeric(df["max_salary"], errors="coerce")
    df["min_exp"] = pd.to_numeric(df["min_exp"], errors="coerce")
    df["collected_at"] = pd.to_datetime(df["collected_at"]).dt.date
    
    # Salary metric: mid point
    df["salary_mid"] = df.apply(
        lambda r: r["min_salary"] if pd.isna(r["max_salary"]) else (
            r["max_salary"] if pd.isna(r["min_salary"]) else (r["min_salary"] + r["max_salary"]) / 2
        ), axis=1
    )
    
    today_str = date.today().isoformat()
    
    # ── 1. Skill Demand History ───────────────────────────────────
    print("  Calculating skill demand history (Pandas)...")
    sdh_records = []
    for dt, group in df.groupby("collected_at"):
        total_jobs = len(group)
        if total_jobs == 0:
            continue
        for skill_key, info in taxonomy.items():
            matches = 0
            for _, row in group.iterrows():
                std_skills = [s.lower().strip() for s in (row.get("standardized_skills") or [])]
                if any(k in std_skills for k in info["db_keys"]):
                    matches += 1
            demand_pct = round((matches / total_jobs) * 100, 1)
            sdh_records.append({
                "skill_name": info["display"],
                "demand_percentage": demand_pct,
                "date": dt.isoformat()
            })
            
    # ── 2. Skill Gap Analysis ─────────────────────────────────────
    print("  Calculating skill gap scores (Pandas)...")
    sga_records = []
    for dt, group in df.groupby("collected_at"):
        total_jobs = len(group)
        if total_jobs == 0:
            continue
        for skill_key, info in taxonomy.items():
            matches = 0
            for _, row in group.iterrows():
                std_skills = [s.lower().strip() for s in (row.get("standardized_skills") or [])]
                if any(k in std_skills for k in info["db_keys"]):
                    matches += 1
            demand_pct = round((matches / total_jobs) * 100, 1)
            for stream in info["streams"]:
                sga_records.append({
                    "skill_name": info["display"],
                    "stream": stream,
                    "supply_pct": info["supply"],
                    "demand_pct": demand_pct,
                    "gap_score": round(demand_pct - info["supply"], 1),
                    "date": dt.isoformat()
                })
                
    # ── 3. Salary Insights ────────────────────────────────────────
    print("  Calculating salary insights (Pandas)...")
    sal_records = []
    sal_df = df[df["salary_mid"].notna() & (df["salary_mid"] > 0)]
    
    if not sal_df.empty:
        # By Skill
        for skill_key, info in taxonomy.items():
            skill_jobs = []
            for _, row in sal_df.iterrows():
                std_skills = [s.lower().strip() for s in (row.get("standardized_skills") or [])]
                if any(k in std_skills for k in info["db_keys"]):
                    skill_jobs.append(row["salary_mid"])
            if skill_jobs:
                sal_records.append({
                    "skill_name": info["display"],
                    "job_field": "",
                    "city": "",
                    "exp_level": "",
                    "median_salary": float(np.median(skill_jobs)),
                    "date": today_str
                })
                
        # By Job Field
        for field, group in sal_df.groupby("job_field"):
            if field and field != 'Other':
                sal_records.append({
                    "skill_name": "",
                    "job_field": field,
                    "city": "",
                    "exp_level": "",
                    "median_salary": float(group["salary_mid"].median()),
                    "date": today_str
                })
            
        # By City
        for city, group in sal_df.groupby("city"):
            if city:
                sal_records.append({
                    "skill_name": "",
                    "job_field": "",
                    "city": city,
                    "exp_level": "",
                    "median_salary": float(group["salary_mid"].median()),
                    "date": today_str
                })
            
        # By Experience
        sal_df = sal_df.copy()
        sal_df["exp_band"] = sal_df["min_exp"].apply(get_experience_band_simple)
        for band, group in sal_df.groupby("exp_band"):
            sal_records.append({
                "skill_name": "",
                "job_field": "",
                "city": "",
                "exp_level": band,
                "median_salary": float(group["salary_mid"].median()),
                "date": today_str
            })
            
    # ── 4. Location Insights ──────────────────────────────────────
    print("  Calculating location insights (Pandas)...")
    loc_records = []
    for city, group in df.groupby("city"):
        if city:
            avg_sal = group["salary_mid"].mean()
            loc_records.append({
                "city": city,
                "job_count": len(group),
                "avg_salary": float(avg_sal) if not pd.isna(avg_sal) else None,
                "date": today_str
            })
        
    # ── 5. Company Hiring Stats ───────────────────────────────────
    print("  Calculating company hiring statistics (Pandas)...")
    comp_records = []
    for comp, group in df.groupby("company"):
        if comp and comp != "Unknown":
            comp_records.append({
                "company": comp,
                "job_count": len(group),
                "date": today_str
            })
            
    local_data = {
        "skill_demand_history": sdh_records,
        "skill_gap_analysis": sga_records,
        "salary_insights": sal_records,
        "location_insights": loc_records,
        "company_hiring_stats": comp_records,
        "freshness": {
            "total_jobs": len(df),
            "unique_companies": df["company"].nunique(),
            "sources": df["source"].unique().tolist(),
            "last_collected": df["collected_at"].max().isoformat() if not df["collected_at"].isna().all() else today_str,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    }
    
    save_local_fallback(local_data)
    
    # Try uploading to Supabase
    try:
        client = get_supabase_client()
        print("  Uploading local aggregates to Supabase...")
        
        if sdh_records:
            client.table("skill_demand_history").upsert(sdh_records, on_conflict="skill_name,date").execute()
        if sga_records:
            client.table("skill_gap_analysis").upsert(sga_records, on_conflict="skill_name,stream,date").execute()
        if sal_records:
            # Drop entries for today first to resolve potential constraint conflict in standard tables
            client.table("salary_insights").delete().eq("date", today_str).execute()
            client.table("salary_insights").upsert(sal_records, on_conflict="skill_name,job_field,city,exp_level,date").execute()
        if loc_records:
            client.table("location_insights").upsert(loc_records, on_conflict="city,date").execute()
        if comp_records:
            client.table("company_hiring_stats").upsert(comp_records, on_conflict="company,date").execute()
            
        print("  ✓ Successfully synchronized Pandas aggregates with Supabase.")
    except Exception as e:
        print(f"  [Warning] Could not upload aggregates to Supabase: {e}")


def save_local_fallback(data):
    """Save fallback backup snapshot locally."""
    fallback_path = os.path.join(PROJECT_ROOT, "data", "processed", "precomputed_analytics.json")
    os.makedirs(os.path.dirname(fallback_path), exist_ok=True)
    try:
        with open(fallback_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, default=str)
        print(f"  ✓ Local precomputed fallback saved to {fallback_path}")
    except Exception as e:
        print(f"  [Error] Failed to write local fallback file: {e}")


if __name__ == "__main__":
    run_precomputation()
