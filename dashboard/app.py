"""
CareerLens AI — dashboard/app.py
=================================
Interactive Job Market Intelligence Dashboard.

Run with:
    streamlit run dashboard/app.py

Improvements (v3):
  Pipeline:
    1. Data loads directly from Supabase (JSON file as fallback)
    2. Dynamic filters auto-update with new cities/categories/fields
    3. Two-level category filter (job_field + job_sub_field)
    4. is_active toggle for stale job filtering
    5. Collection cooldown check before re-fetching
    6. Vectorized keyword search (no row-by-row apply)

  UI:
    7. Filter defaults: blank multiselect = show all (standard UX)
    8. Live collection monitor with log streaming
    9. Data freshness badge with safe date formatting
"""

import os
import re
import sys
import json
import time
import subprocess
import threading
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# ── Ensure project root is importable ────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ── Page Configuration (MUST be first st command) ────────────
st.set_page_config(
    page_title="CareerLens AI — Job Market Intelligence",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Lazy-import analysis modules (keeps startup fast) ─────────
from analysis.helpers import get_experience_band  # noqa: E402
from analysis.market_overview import render_market_overview
from analysis.job_explorer import render_job_explorer
from analysis.skill_demand import render_skill_demand
from analysis.location_analysis import render_location_analysis
from analysis.experience_analysis import render_experience_analysis
from analysis.category_analysis import render_category_analysis
from analysis.company_analysis import render_company_analysis
from analysis.market_intelligence import render_market_intelligence
# from analysis.ai_insights import render_ai_insights

# ═════════════════════════════════════════════════════════════
#  CONSTANTS
# ═════════════════════════════════════════════════════════════

DATA_PATH = os.path.join(PROJECT_ROOT, "data", "processed", "jobs_analytics.json")

# Columns that MUST exist; filled with sensible defaults if absent
REQUIRED_COLUMNS: dict[str, object] = {
    "min_exp": float("nan"),
    "max_exp": float("nan"),
    "min_salary": float("nan"),
    "max_salary": float("nan"),
    "posted_at": pd.NaT,
    "collected_at": pd.NaT,
    "city": "Unknown",
    "job_category": "Other",
    "job_field": "Other",
    "job_sub_field": "Other",
    "work_mode": "Unknown",
    "source": "Unknown",
    "company": "Unknown",
    "title": "",
    "is_active": True,
    "standardized_skills": None,   # handled specially below
    "search_keywords": None,
}

# ═════════════════════════════════════════════════════════════
#  GLOBAL CSS
# ═════════════════════════════════════════════════════════════

st.markdown("""
<style>
/* ── Design Tokens ─────────────────────────────────────────── */
:root {
    --bg-base:    #0a0f1e;
    --bg-surface: #111827;
    --bg-card:    #1a2236;
    --bg-hover:   #1e2d45;
    --border:     #1e3a5f;
    --border-hi:  #3b5bdb;
    --accent-1:   #6366f1;   /* indigo  */
    --accent-2:   #06b6d4;   /* cyan    */
    --accent-3:   #8b5cf6;   /* violet  */
    --text-hi:    #f1f5f9;
    --text-mid:   #94a3b8;
    --text-lo:    #475569;
    --success:    #22c55e;
    --warning:    #f59e0b;
    --danger:     #ef4444;
    --radius-sm:  8px;
    --radius-md:  12px;
    --radius-lg:  16px;
    --shadow:     0 4px 24px rgba(0,0,0,0.45);
}

/* ── Base ──────────────────────────────────────────────────── */
.stApp {
    background-color: var(--bg-base);
    color: var(--text-hi);
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
}
.main .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }

/* ── Sidebar ───────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background-color: var(--bg-surface);
    border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] .stMarkdown h2 {
    background: linear-gradient(90deg, var(--accent-1), var(--accent-2));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 1.3rem;
    font-weight: 800;
    letter-spacing: -0.02em;
}
/* Sidebar expander */
[data-testid="stSidebar"] details > summary {
    color: var(--text-mid);
    font-size: 0.82rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.07em;
}

/* ── KPI Cards ─────────────────────────────────────────────── */
.kpi-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 14px; margin-bottom: 1.5rem; }
.kpi-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-top: 3px solid var(--accent-1);
    border-radius: var(--radius-md);
    padding: 18px 20px;
    transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
    box-shadow: var(--shadow);
}
.kpi-card:hover {
    transform: translateY(-3px);
    border-color: var(--border-hi);
    box-shadow: 0 8px 32px rgba(99,102,241,0.18);
}
.kpi-value {
    font-size: 2rem;
    font-weight: 800;
    color: var(--text-hi);
    line-height: 1.1;
    margin-bottom: 4px;
    letter-spacing: -0.03em;
}
.kpi-label {
    font-size: 0.78rem;
    color: var(--text-mid);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
}
.kpi-delta { font-size: 0.75rem; color: var(--success); margin-top: 4px; }

/* ── Section Headers ───────────────────────────────────────── */
.section-header {
    font-size: 1.05rem;
    font-weight: 700;
    color: var(--accent-3);
    margin: 1.8rem 0 0.8rem;
    padding-bottom: 0.45rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 8px;
}

/* ── Tabs ──────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid var(--border); }
.stTabs [data-baseweb="tab"] {
    height: 44px;
    background-color: transparent;
    border-radius: var(--radius-sm) var(--radius-sm) 0 0;
    padding: 8px 16px;
    color: var(--text-mid);
    font-weight: 500;
    font-size: 0.88rem;
    transition: color 0.15s, background 0.15s;
}
.stTabs [data-baseweb="tab"]:hover { color: var(--text-hi); background: var(--bg-card); }
.stTabs [aria-selected="true"] {
    background-color: var(--bg-card) !important;
    color: var(--text-hi) !important;
    border-bottom: 2px solid var(--accent-1) !important;
    font-weight: 700;
}

/* ── Job Cards ─────────────────────────────────────────────── */
.job-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent-1);
    border-radius: var(--radius-md);
    padding: 16px 18px;
    margin-bottom: 10px;
    transition: border-color 0.15s, transform 0.15s;
}
.job-card:hover { border-left-color: var(--accent-2); transform: translateX(2px); }
.job-title  { font-size: 1rem;  font-weight: 700; color: var(--text-hi); }
.job-company{ font-size: 0.88rem; color: var(--accent-1); font-weight: 600; }
.job-meta   { font-size: 0.78rem; color: var(--text-mid); margin-top: 5px; }
.skill-tag  {
    display: inline-block;
    background: rgba(99,102,241,0.12);
    color: #a5b4fc;
    border: 1px solid rgba(99,102,241,0.25);
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    margin: 2px 3px 2px 0;
    font-weight: 500;
}

/* ── AI Chat ───────────────────────────────────────────────── */
.ai-response {
    background: linear-gradient(135deg, #0d1b3e 0%, var(--bg-card) 100%);
    border: 1px solid var(--border-hi);
    border-radius: var(--radius-lg);
    padding: 22px 24px;
    line-height: 1.75;
    box-shadow: 0 0 40px rgba(99,102,241,0.1);
}

/* ── Market Intel Compare Cards ────────────────────────────── */
.compare-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-top: 3px solid var(--accent-1);
    border-radius: var(--radius-md);
    padding: 14px 16px;
    margin-bottom: 14px;
}
.compare-title { font-size: 1rem; font-weight: 700; color: var(--text-hi); margin-bottom: 10px; padding-bottom: 5px; border-bottom: 1px solid var(--border); }
.compare-stat  { display: flex; justify-content: space-between; padding: 3px 0; }
.compare-stat-label { color: var(--text-mid); font-size: 0.87rem; }
.compare-stat-value { color: var(--text-hi);  font-size: 0.87rem; font-weight: 700; }

/* ── Collection Log ────────────────────────────────────────── */
.log-box {
    background: #050c18;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 14px 16px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 0.78rem;
    color: #4ade80;
    max-height: 220px;
    overflow-y: auto;
    line-height: 1.65;
}

/* ── Progress / Filter Count ───────────────────────────────── */
.filter-bar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    background: var(--bg-card);
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    margin-top: 8px;
    font-size: 0.82rem;
    color: var(--text-mid);
}
.filter-count { font-weight: 700; color: var(--text-hi); }
.filter-progress {
    flex: 1;
    height: 4px;
    background: var(--border);
    border-radius: 2px;
    overflow: hidden;
}
.filter-progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--accent-1), var(--accent-2));
    border-radius: 2px;
    transition: width 0.3s ease;
}

/* ── Alerts ────────────────────────────────────────────────── */
[data-testid="stAlert"] {
    border-radius: var(--radius-md) !important;
    border-left-width: 3px !important;
}

/* ── Scrollbar ─────────────────────────────────────────────── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: var(--bg-base); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--accent-1); }
</style>
""", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
#  DATA LOADING — Supabase first, JSON file fallback
# ═════════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def load_data() -> pd.DataFrame:
    """Load, validate, deduplicate and enrich the job dataset.

    Trigger cache invalidate: v2

    Priority:
      1. Supabase direct (always fresh)
      2. Local JSON file (fallback if Supabase is unavailable)
    """
    raw = []

    # ── Try Supabase first ───────────────────────────────────
    try:
        from database.supabase_client import fetch_analytics_for_dashboard
        raw = fetch_analytics_for_dashboard(active_only=True)
        if raw:
            print(f"  Dashboard: loaded {len(raw)} rows from Supabase.")
    except Exception as e:
        print(f"  Dashboard: Supabase unavailable ({e}), falling back to JSON file.")

    # ── Fallback: local JSON file ────────────────────────────
    if not raw and os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            print(f"  Dashboard: loaded {len(raw)} rows from local JSON file.")
        except Exception as e:
            print(f"  Dashboard: JSON file load failed: {e}")

    if not raw:
        return pd.DataFrame()

    df = pd.DataFrame(raw)

    # ── Missing-column protection ────────────────────────────
    for col, default in REQUIRED_COLUMNS.items():
        if col not in df.columns:
            df[col] = default

    # Numeric coercion
    for col in ("min_exp", "max_exp", "min_salary", "max_salary"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # ── Safe date parsing ────────────────────────────────────
    for col in ("posted_at", "collected_at"):
        df[col] = pd.to_datetime(df[col], errors="coerce")

    # ── Duplicate handling ───────────────────────────────────
    # Priority 1: dedup on fingerprint
    if "fingerprint" in df.columns:
        df = df.drop_duplicates(subset=["fingerprint"], keep="last")
    # Priority 2: fallback — title + company + city composite key
    natural_key = ["title", "company", "city"]
    if all(c in df.columns for c in natural_key):
        df = df.drop_duplicates(subset=natural_key, keep="last")

    # ── Feature engineering ──────────────────────────────────
    df["exp_band"] = df["min_exp"].apply(get_experience_band)

    df["city"]          = df["city"].fillna("Unknown")
    df["job_category"]  = df["job_category"].fillna("Other")
    df["job_field"]     = df["job_field"].fillna("Other")
    df["job_sub_field"] = df["job_sub_field"].fillna("Other")
    df["work_mode"]     = df["work_mode"].fillna("Unknown")
    df["source"]        = df["source"].fillna("Unknown")
    df["company"]       = df["company"].fillna("Unknown")

    # ── Pre-compute frozensets for O(1) skill lookup ─────────
    def _to_frozenset(x):
        if isinstance(x, list):
            return frozenset(s.lower() for s in x)
        return frozenset()

    df["_skill_set"] = df["standardized_skills"].apply(_to_frozenset)

    return df


# ═════════════════════════════════════════════════════════════
#  SAFE DATE HELPER
# ═════════════════════════════════════════════════════════════

def _safe_date_str(series: pd.Series, fmt: str = "%Y-%m-%d") -> str:
    """Return formatted max date, or 'N/A' if all values are NaT."""
    valid = series.dropna()
    if valid.empty:
        return "N/A"
    return valid.max().strftime(fmt)


# ═════════════════════════════════════════════════════════════
#  BACKGROUND COLLECTION
# ═════════════════════════════════════════════════════════════

# Session-state key for the running process handle
_PROC_KEY  = "_collection_proc"
_LOGS_KEY  = "_collection_logs"
_STAGE_KEY = "_collection_stage"


def _stream_logs(proc: subprocess.Popen, logs: list[str]) -> None:
    """Background thread: read proc stdout line-by-line into `logs`."""
    try:
        for line in iter(proc.stdout.readline, ""):
            logs.append(line.rstrip())
        proc.stdout.close()
    except Exception:
        pass


def start_collection(keyword: str) -> None:
    """
    Launch data collection in the background (non-blocking Popen).
    Stores the process handle and a shared log list in session state.
    """
    if st.session_state.get(_PROC_KEY) is not None:
        st.warning("A collection job is already running.")
        return

    logs: list[str] = [f"[{datetime.now():%H:%M:%S}] Starting collection for '{keyword}' …"]
    st.session_state[_LOGS_KEY]  = logs
    st.session_state[_STAGE_KEY] = 0

    # Build the command list; one combined run that handles both sources
    cmd = [
        sys.executable, "main.py",
        "--source", "both",
        "--keyword", keyword,
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        st.session_state[_PROC_KEY] = proc

        # Spin up a daemon thread to drain stdout without blocking Streamlit
        t = threading.Thread(target=_stream_logs, args=(proc, logs), daemon=True)
        t.start()

    except FileNotFoundError:
        logs.append("[ERROR] main.py not found — check PROJECT_ROOT.")
        st.session_state[_PROC_KEY] = None


def render_collection_monitor() -> None:
    """
    Show live log output and handle process completion / return-code check.
    Call this every rerun so the UI stays fresh.
    """
    proc: subprocess.Popen | None = st.session_state.get(_PROC_KEY)
    if proc is None:
        return

    logs: list[str] = st.session_state.get(_LOGS_KEY, [])

    with st.sidebar:
        st.markdown("---")
        st.markdown("##### 🔄 Live Collection Monitor")

        ret = proc.poll()   # None → still running

        if ret is None:
            st.info("Collection in progress…")
        elif ret == 0:
            st.success("✅ Collection finished successfully!")
            st.session_state[_PROC_KEY] = None
            st.cache_data.clear()
        else:
            st.error(f"❌ Collector exited with code {ret}. Check logs below.")
            st.session_state[_PROC_KEY] = None

        # Render scrollable log box
        log_html = "<br>".join(
            f'<span style="opacity:.55">[{i+1:03d}]</span> {line}'
            for i, line in enumerate(logs[-40:])   # tail last 40 lines
        )
        st.markdown(
            f'<div class="log-box">{log_html or "Waiting for output…"}</div>',
            unsafe_allow_html=True,
        )

        if ret is not None and st.button("🔁 Reload Dashboard"):
            st.rerun()

        # Rerun logic moved to the bottom of main() so the page fully renders.


# ═════════════════════════════════════════════════════════════
#  DYNAMIC FILTER HELPERS — cache by unique values, not shape
# ═════════════════════════════════════════════════════════════

def _filter_hash(df: pd.DataFrame) -> int:
    """Compute a hash that changes when filter-relevant columns change."""
    parts = [df.shape]
    for col in ("city", "job_category", "job_field", "job_sub_field", "work_mode", "source"):
        if col in df.columns:
            parts.append(tuple(sorted(df[col].dropna().unique())))
    return hash(tuple(parts))


@st.cache_data(hash_funcs={pd.DataFrame: _filter_hash})
def _get_filter_options(df: pd.DataFrame) -> dict:
    """
    Pre-compute every sidebar dropdown's option list.
    Cache key includes unique values of filter columns, so options
    auto-refresh when new cities/categories appear in the data.
    """
    return {
        "fields":      sorted(df["job_field"].dropna().unique().tolist()),
        "sub_fields":  sorted(df["job_sub_field"].dropna().unique().tolist()),
        "categories":  sorted(df["job_category"].dropna().unique().tolist()),
        "cities":      sorted(df["city"].dropna().unique().tolist()),
        "modes":       sorted(df["work_mode"].dropna().unique().tolist()),
        "sources":     sorted(df["source"].dropna().unique().tolist()),
        "exp_min":     int(df["min_exp"].min()) if df["min_exp"].notna().any() else 0,
        "exp_max":     int(df["min_exp"].max()) if df["min_exp"].notna().any() else 20,
    }


# ═════════════════════════════════════════════════════════════
#  SIDEBAR — GLOBAL FILTERS
# ═════════════════════════════════════════════════════════════

def render_sidebar(df: pd.DataFrame) -> pd.DataFrame:
    with st.sidebar:
        st.markdown("## 🔍 CareerLens AI")
        st.markdown(
            "<p style='color:var(--text-mid);font-size:0.82rem;margin-top:-8px'>"
            "Job Market Intelligence</p>",
            unsafe_allow_html=True,
        )
        st.divider()

        # ── Keyword search ───────────────────────────────────
        keyword = st.text_input(
            "Search jobs",
            placeholder="e.g. Data Science, MLOps, Python…",
            label_visibility="collapsed",
        )
        if keyword:
            try:
                re.compile(keyword)
            except re.error:
                st.caption("⚠️ Invalid regex — treated as plain text.")
                keyword = re.escape(keyword)

        st.divider()

        # ── Dynamic filter options ───────────────────────────
        opts = _get_filter_options(df)
        exp_min, exp_max = opts["exp_min"], opts["exp_max"]
        if exp_min == exp_max:
            exp_max = exp_min + 1

        # ── Two-level category filter ────────────────────────
        with st.expander("🏷 Field & Category", expanded=True):
            selected_fields = st.multiselect(
                "Job Field", opts["fields"],
                default=[],  # blank = show all
                label_visibility="collapsed",
                placeholder="All fields",
            )
            # Filter sub-fields based on selected fields
            available_sub_fields = opts["sub_fields"]
            if selected_fields and "job_field" in df.columns:
                available_sub_fields = sorted(
                    df[df["job_field"].isin(selected_fields)]["job_sub_field"]
                    .dropna().unique().tolist()
                )
            selected_sub_fields = st.multiselect(
                "Sub-field", available_sub_fields,
                default=[],
                label_visibility="collapsed",
                placeholder="All sub-fields",
            )

        with st.expander("📍 Location & Mode", expanded=False):
            selected_cities = st.multiselect(
                "cities", opts["cities"],
                default=[],
                label_visibility="collapsed",
                placeholder="All cities",
            )
            selected_modes = st.multiselect(
                "work mode", opts["modes"],
                default=[],
                label_visibility="collapsed",
                placeholder="All modes",
            )

        with st.expander("🎓 Experience & Source", expanded=False):
            exp_range = st.slider(
                "Min experience (yrs)", exp_min, exp_max, (exp_min, exp_max)
            )
            selected_sources = st.multiselect(
                "source", opts["sources"],
                default=[],
                label_visibility="collapsed",
                placeholder="All sources",
            )

        # ── Apply filters (blank multiselect = no filter = show all) ──
        filtered = df.copy()

        if selected_fields:
            filtered = filtered[filtered["job_field"].isin(selected_fields)]
        if selected_sub_fields:
            filtered = filtered[filtered["job_sub_field"].isin(selected_sub_fields)]
        if selected_cities:
            filtered = filtered[filtered["city"].isin(selected_cities)]
        if selected_modes:
            filtered = filtered[filtered["work_mode"].isin(selected_modes)]
        if selected_sources:
            filtered = filtered[filtered["source"].isin(selected_sources)]

        # Experience filter always applies
        filtered = filtered[
            filtered["min_exp"].isna()
            | (
                (filtered["min_exp"] >= exp_range[0])
                & (filtered["min_exp"] <= exp_range[1])
            )
        ]

        # ── Vectorized keyword search ────────────────────────
        if keyword:
            pattern = re.compile(keyword, re.IGNORECASE)

            # Vectorized string matching on main columns
            mask = (
                filtered["title"].str.contains(keyword, case=False, na=False, regex=True)
                | filtered["company"].str.contains(keyword, case=False, na=False, regex=True)
                | filtered["job_category"].str.contains(keyword, case=False, na=False, regex=True)
                | filtered["job_field"].str.contains(keyword, case=False, na=False, regex=True)
                | filtered["job_sub_field"].str.contains(keyword, case=False, na=False, regex=True)
            )
            # Skills still need frozenset approach
            mask = mask | filtered["_skill_set"].apply(
                lambda s: any(pattern.search(x) for x in s)
            )
            filtered = filtered[mask]

            st.divider()
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(
                    f"<div style='font-size:0.8rem;color:var(--text-mid)'>"
                    f"Results for <b style='color:var(--text-hi)'>{keyword}</b></div>",
                    unsafe_allow_html=True,
                )
            with col_b:
                if st.button("🚀 Fetch Live", width="stretch"):
                    start_collection(keyword)
                    st.rerun()

        # ── Filter count bar ─────────────────────────────────
        ratio = len(filtered) / max(len(df), 1)
        pct   = int(ratio * 100)
        st.markdown(
            f"""
            <div class="filter-bar">
              <span class="filter-count">{len(filtered):,}</span>
              <span>/ {len(df):,} jobs</span>
              <div class="filter-progress">
                <div class="filter-progress-fill" style="width:{pct}%"></div>
              </div>
              <span style="color:var(--accent-2);font-weight:700">{pct}%</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if len(filtered) < len(df):
            st.caption("All charts reflect the current filter selection.")

    return filtered


# ═════════════════════════════════════════════════════════════
#  MAIN APP ORCHESTRATION
# ═════════════════════════════════════════════════════════════

def main():
    df = load_data()

    # Check system status for expired credentials
    status_file = os.path.join(PROJECT_ROOT, "data", "system_status.json")
    if os.path.exists(status_file):
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                status = json.load(f)
                if status.get("naukri", {}).get("credential_expired"):
                    st.warning("⚠ **Naukri session expired.** The dashboard is currently showing data from other sources. Please refresh your Naukri `nkparam` and `Cookie` in the `.env` file to fetch live Naukri jobs.", icon="⚠️")
        except Exception:
            pass

    # ── Background monitor (renders every rerun) ─────────────
    render_collection_monitor()

    if df.empty:
        st.markdown(
            """
            <div style="
                background:#0d1b3e;border:1px solid #1e3a5f;border-radius:12px;
                padding:36px;text-align:center;max-width:540px;margin:80px auto;
            ">
              <div style="font-size:2.5rem;margin-bottom:12px">📭</div>
              <div style="font-size:1.2rem;font-weight:700;color:#f1f5f9;margin-bottom:8px">
                No data yet
              </div>
              <div style="color:#94a3b8;font-size:0.9rem;line-height:1.6">
                Run the collector to populate the dashboard:<br>
                <code style="background:#111827;padding:4px 10px;border-radius:6px;
                             color:#6366f1;font-size:0.88rem">
                  python main.py --source foundit --keyword "Data Engineer"
                </code>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    filtered_df = render_sidebar(df)

    # ── Header ───────────────────────────────────────────────
    hcol1, hcol2 = st.columns([4, 1])
    with hcol1:
        st.markdown(
            """
            <h1 style="
                font-size:1.75rem;font-weight:900;letter-spacing:-0.04em;
                background:linear-gradient(90deg,#6366f1,#06b6d4);
                -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                margin-bottom:0;
            ">CareerLens AI</h1>
            <p style="color:#475569;font-size:0.88rem;margin-top:2px">
              Real-time insights from the Indian job market
            </p>
            """,
            unsafe_allow_html=True,
        )
    with hcol2:
        freshness = _safe_date_str(df["collected_at"])
        st.markdown(
            f"""
            <div style="
                text-align:right;padding-top:14px;
                font-size:0.78rem;color:#475569;
            ">
              <span style="
                  background:#1a2236;border:1px solid #1e3a5f;
                  border-radius:6px;padding:4px 10px;
              ">📅 Data as of <b style="color:#94a3b8">{freshness}</b></span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # ── Tabs ─────────────────────────────────────────────────
    tabs = st.tabs([
        "📊 Overview",
        "🔎 Explorer",
        "🔧 Skills",
        "📍 Location",
        "🎓 Experience",
        "📂 Category",
        "🏢 Companies",
        "🧠 Market Intel",
    ])

    with tabs[0]: render_market_overview(filtered_df)
    with tabs[1]: render_job_explorer(filtered_df)
    with tabs[2]: render_skill_demand(filtered_df)
    with tabs[3]: render_location_analysis(filtered_df)
    with tabs[4]: render_experience_analysis(filtered_df)
    with tabs[5]: render_category_analysis(filtered_df)
    with tabs[6]: render_company_analysis(filtered_df)
    with tabs[7]:
        # Render the upgraded labor market intelligence module
        render_market_intelligence(filtered_df)

    # ── Auto-rerun loop if collection is running ──────────────
    proc = st.session_state.get(_PROC_KEY)
    if proc is not None and proc.poll() is None:
        time.sleep(2)
        st.rerun()


if __name__ == "__main__":
    main()
