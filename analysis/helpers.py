import streamlit as st
import pandas as pd
from collections import Counter

COLORS = [
    "#6366f1", "#8b5cf6", "#06b6d4", "#10b981", "#f59e0b",
    "#ef4444", "#ec4899", "#14b8a6", "#f97316", "#3b82f6",
]

PLOTLY_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#e2e8f0"),
    margin=dict(l=40, r=40, t=50, b=40),
)

EXP_BAND_ORDER = [
    "Fresher (0–2 yrs)",
    "Junior (2–5 yrs)",
    "Mid-Level (5–8 yrs)",
    "Senior (8–12 yrs)",
    "Lead (12+ yrs)",
    "Not Specified",
]

def get_experience_band(min_exp):
    if pd.isna(min_exp):
        return "Not Specified"
    min_exp = int(min_exp)
    if min_exp <= 2:
        return "Fresher (0–2 yrs)"
    elif min_exp <= 5:
        return "Junior (2–5 yrs)"
    elif min_exp <= 8:
        return "Mid-Level (5–8 yrs)"
    elif min_exp <= 12:
        return "Senior (8–12 yrs)"
    else:
        return "Lead (12+ yrs)"

def explode_skills(df) -> pd.DataFrame:
    rows = []
    for _, row in df.iterrows():
        skills = row.get("standardized_skills")
        if isinstance(skills, list):
            for s in skills:
                rows.append({"skill": s, "job_id": row.get("fingerprint")})
    return pd.DataFrame(rows)

def skill_counter(df: pd.DataFrame, top_n: int = 20):
    all_skills = []
    for skills in df["standardized_skills"].dropna():
        if isinstance(skills, list):
            all_skills.extend(skills)
    return Counter(all_skills).most_common(top_n)

def kpi_card(label: str, value, icon: str = "", sub: str = ""):
    sub_html = f'<div style="font-size: 0.85rem; color: #94a3b8; margin-top: 4px;">{sub}</div>' if sub else ""
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-value">{icon} {value}</div>
        <div class="kpi-label">{label}</div>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)
