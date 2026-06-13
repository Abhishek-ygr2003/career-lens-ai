import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import re
import os
from collections import Counter
from analysis.helpers import PLOTLY_LAYOUT, COLORS, get_experience_band
from database.supabase_client import (
    fetch_skill_demand_history,
    fetch_skill_gap_analysis,
    fetch_salary_insights,
    fetch_location_insights,
    fetch_company_hiring_stats,
    load_local_precomputed,
    get_supabase_client
)
from database.precompute_analytics import SUPPLY_DATA

# ═════════════════════════════════════════════════════════════
#  MAIN RENDER FUNCTION
# ═════════════════════════════════════════════════════════════

def render_market_intelligence(df: pd.DataFrame):
    """
    Upgraded Market Intelligence page containing historical trends, precomputed gap analysis,
    salary intelligence, and a dynamic Gemini AI Career Advisor.
    """
    st.markdown("### 🧠 Labor Market Intelligence & AI Career Advisor")
    st.markdown(
        "<p style='color:var(--text-mid);font-size:0.92rem;margin-top:-14px'>"
        "Sourced from daily job board collection (Naukri, Foundit, Adzuna) and precomputed analytics history."
        "</p>",
        unsafe_allow_html=True,
    )

    # Load precomputed metadata / fallback data
    precomputed = load_local_precomputed()
    freshness = precomputed.get("freshness", {})
    
    # Render Sub-tabs
    sub_tabs = st.tabs([
        "📊 Overview & Freshness", 
        "⚖️ Skill Gap Engine", 
        "📈 Tech Trends", 
        "💰 Salary Intel", 
        "🤖 AI Career Advisor"
    ])

    # ─────────────────────────────────────────────────────────
    # SUB-TAB 1: Overview & Freshness
    # ─────────────────────────────────────────────────────────
    # Cache the gap analysis for "all" stream — used in both radar_col3 and the AI Advisor
    if "_gap_records_all" not in st.session_state:
        with st.spinner("Loading skill gap data..."):
            st.session_state["_gap_records_all"] = fetch_skill_gap_analysis("all")
    gap_records_all = st.session_state["_gap_records_all"]

    with sub_tabs[0]:
        st.markdown("#### 📈 Market Data Status & Pipeline Health")
        st.caption("Freshness, sources coverage, and scale of the labor market data lake.")
        
        # Determine stats
        total_jobs = freshness.get("total_jobs", len(df))
        unique_companies = freshness.get("unique_companies", df["company"].nunique() if not df.empty else 0)
        sources = freshness.get("sources", df["source"].unique().tolist() if not df.empty else [])
        last_collected = freshness.get("last_collected", "N/A")
        last_updated = freshness.get("last_updated", "N/A")
        
        # Draw status KPIs
        kcol1, kcol2, kcol3 = st.columns(3)
        with kcol1:
            st.metric("Total Listings Analyzed", f"{total_jobs:,}")
        with kcol2:
            st.metric("Unique Employers", f"{unique_companies:,}")
        with kcol3:
            st.metric("Analytics Last Computed", last_updated.split(" ")[0] if last_updated else "Just Now")
            
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        
        # Source checklist
        st.markdown("##### 🔌 Configured Ingestion Connectors")
        scol1, scol2, scol3 = st.columns(3)
        with scol1:
            st.markdown("🟢 **Naukri Scraper** <br><span style='color:var(--text-mid);font-size:0.8rem;'>Scrapes hourly white-collar listings. Status: ACTIVE</span>", unsafe_allow_html=True)
        with scol2:
            st.markdown("🟢 **Foundit Collector** <br><span style='color:var(--text-mid);font-size:0.8rem;'>JSON API scraper for tech jobs. Status: ACTIVE</span>", unsafe_allow_html=True)
        with scol3:
            adzuna_ok = "adzuna" in sources or os.getenv("ADZUNA_APP_ID")
            status_color = "🟢" if adzuna_ok else "🟡"
            status_desc = "ACTIVE" if adzuna_ok else "MISSING KEYS"
            st.markdown(f"{status_color} **Adzuna API** <br><span style='color:var(--text-mid);font-size:0.8rem;'>Free tier API integrations. Status: {status_desc}</span>", unsafe_allow_html=True)
            
        st.divider()
        st.markdown("##### 📄 Active Ingested Volume by Portal Source")
        if not df.empty:
            source_counts = df["source"].value_counts().reset_index()
            source_counts.columns = ["Source", "Active Postings"]
            fig_source = px.bar(
                source_counts, x="Source", y="Active Postings",
                color="Source", color_discrete_sequence=COLORS[:3],
                height=300
            )
            fig_source.update_layout(**PLOTLY_LAYOUT)
            st.plotly_chart(fig_source, width='stretch')
        else:
            st.info("No active volume metrics computed.")

        st.divider()
        st.markdown("##### 🕸️ Career Path Radar (Field Demand • Common Skills • Future Skills)")

        # Helper: get latest snapshot date from dataframe
        def _latest_snapshot_date(dataframe: pd.DataFrame):
            if dataframe is None or dataframe.empty:
                return None
            for col in ["collected_at", "date"]:
                if col in dataframe.columns:
                    try:
                        s = pd.to_datetime(dataframe[col], errors="coerce")
                        s = s.dropna()
                        if not s.empty:
                            return s.max().date()
                    except Exception:
                        pass
            return None

        # Radar 1: Top job fields demand share (based on job_field from latest snapshot)
        latest_dt = _latest_snapshot_date(df)
        radar_col1, radar_col2, radar_col3 = st.columns(3)

        with radar_col1:
            st.markdown("###### 🏗️ Top Job Fields Demand")
            if (
                latest_dt is not None
                and "job_field" in df.columns
                and "collected_at" in df.columns
                and not df.empty
            ):
                df_tmp = df.copy()
                df_tmp["__collected_at"] = pd.to_datetime(df_tmp["collected_at"], errors="coerce")
                df_tmp = df_tmp[df_tmp["__collected_at"].dt.date == latest_dt]
                if df_tmp["job_field"].notna().any():
                    field_share = (
                        df_tmp["job_field"]
                        .dropna()
                        .value_counts(normalize=True)
                        .head(8)
                        * 100
                    ).round(1)

                    labels = field_share.index.astype(str).tolist()
                    values = field_share.values.tolist()

                    if values:
                        fig_field = go.Figure(
                            data=[
                                go.Scatterpolar(
                                    r=values + [values[0]],
                                    theta=labels + [labels[0]],
                                    fill="toself",
                                    name="Demand share (%)",
                                    marker=dict(color="#3b82f6")
                                )
                            ]
                        )
                        fig_field.update_layout(
                            polar=dict(
                                radialaxis=dict(visible=True, tickformat=".0f", range=[0, max(values) * 1.15])
                            ),
                            showlegend=False,
                            height=360,
                            **PLOTLY_LAYOUT,
                        )
                        fig_field.update_traces(
                            hovertemplate="%{theta}<br>Demand share: %{r}%<extra></extra>"
                        )
                        st.plotly_chart(fig_field, width='stretch')
                    else:
                        st.info("No job_field demand data to plot.")
                else:
                    st.info("No job_field demand data in the latest snapshot.")
            else:
                st.info("Not enough data to compute field demand share.")

        # Radar 2: Top common skills (from skill_demand_history latest)
        with radar_col2:
            st.markdown("###### 💡 Most Common Skills (Current Demand)")
            hist_records = fetch_skill_demand_history()

            labels, values = [], []

            if hist_records:
                # --- Primary path: use precomputed skill_demand_history table ---
                hdf = pd.DataFrame(hist_records)
                if not hdf.empty and {"skill_name", "demand_percentage", "date"}.issubset(set(hdf.columns)):
                    latest_date = pd.to_datetime(hdf["date"], errors="coerce").max()
                    latest_date_str = latest_date.date().isoformat() if pd.notna(latest_date) else None
                    h_latest = hdf.copy()
                    h_latest["__date"] = pd.to_datetime(h_latest["date"], errors="coerce")
                    if latest_date_str:
                        h_latest = h_latest[h_latest["__date"].dt.date == latest_date_str]
                    top_skills = (
                        h_latest.dropna(subset=["skill_name"])
                        .sort_values("demand_percentage", ascending=False)
                        .head(8)
                    )
                    labels = top_skills["skill_name"].astype(str).tolist()
                    values = top_skills["demand_percentage"].astype(float).tolist()

            if not values and not df.empty and "standardized_skills" in df.columns:
                # --- Fallback: compute live from jobs_analytics df ---
                skill_series = df["standardized_skills"].dropna()
                skill_series = skill_series[skill_series.apply(lambda x: isinstance(x, list))]
                if not skill_series.empty:
                    all_skills = [s for sublist in skill_series for s in sublist if s]
                    total_jobs = len(df)
                    skill_counts = pd.Series(all_skills).value_counts().head(8)
                    labels = skill_counts.index.astype(str).tolist()
                    values = (skill_counts.values / total_jobs * 100).round(1).tolist()
                    st.caption("🟡 Live from current data — run precompute for historical tracking")

            if values:
                fig_skill = go.Figure(
                    data=[
                        go.Scatterpolar(
                            r=values + [values[0]],
                            theta=labels + [labels[0]],
                            fill="toself",
                            name="Demand index (%)",
                            marker=dict(color="#8b5cf6")
                        )
                    ]
                )
                fig_skill.update_layout(
                    polar=dict(
                        radialaxis=dict(visible=True, tickformat=".0f", range=[0, max(values) * 1.15])
                    ),
                    showlegend=False,
                    height=360,
                    **{**PLOTLY_LAYOUT, "margin": dict(l=10, r=10, t=20, b=10)},
                )
                fig_skill.update_traces(
                    hovertemplate="%{theta}<br>Demand index: %{r:.1f}%<extra></extra>"
                )
                st.plotly_chart(fig_skill, use_container_width=True)
            else:
                st.info("No skill data available to plot.")

        # Radar 3: Future Skills / Emerging Trends
        with radar_col3:
            st.markdown("###### 🔮 Future Skills & Emerging Trends")
            st.caption("Skills with high talent gaps (demand > supply) & rising demand — signals for next 2-3 years")

            # Reuse cached gap analysis
            gap_records = gap_records_all
            hist_records = fetch_skill_demand_history()

            future_labels = []
            future_values = []

            if gap_records and hist_records:
                # --- Primary path: precomputed gap + history ---
                gap_df = pd.DataFrame(gap_records)
                hist_df = pd.DataFrame(hist_records)

                latest_gap_date = gap_df["date"].max()
                gap_latest = gap_df[gap_df["date"] == latest_gap_date].copy()
                shortage_skills = gap_latest[gap_latest["gap_score"] > 5].sort_values("gap_score", ascending=False)

                if not shortage_skills.empty and not hist_df.empty:
                    skill_trends = {}
                    for skill in shortage_skills["skill_name"].unique():
                        skill_hist = hist_df[hist_df["skill_name"] == skill].sort_values("date")
                        if len(skill_hist) >= 2:
                            first_val = skill_hist.iloc[0]["demand_percentage"]
                            last_val = skill_hist.iloc[-1]["demand_percentage"]
                            if first_val > 0:
                                growth = ((last_val - first_val) / first_val) * 100
                                skill_trends[skill] = growth

                    shortage_skills = shortage_skills.copy()
                    shortage_skills["trend_growth"] = shortage_skills["skill_name"].map(skill_trends).fillna(0)
                    shortage_skills["future_score"] = shortage_skills["gap_score"] + (shortage_skills["trend_growth"].clip(0, 50) * 0.5)

                    top_future = shortage_skills.sort_values("future_score", ascending=False).head(8)
                    future_labels = top_future["skill_name"].astype(str).tolist()
                    future_values = top_future["future_score"].astype(float).tolist()

            if not future_labels and not df.empty and "standardized_skills" in df.columns:
                # --- Fallback: top demanded skills from df as a demand-priority proxy ---
                skill_series = df["standardized_skills"].dropna()
                skill_series = skill_series[skill_series.apply(lambda x: isinstance(x, list))]
                if not skill_series.empty:
                    all_skills = [s for sublist in skill_series for s in sublist if s]
                    total_jobs = len(df)
                    skill_counts = pd.Series(all_skills).value_counts().head(8)
                    future_labels = skill_counts.index.astype(str).tolist()
                    # Express as demand % — honest proxy until precompute runs
                    future_values = (skill_counts.values / total_jobs * 100).round(1).tolist()
                    st.caption("🟡 Showing demand share — run precompute_analytics.py for gap + trend scoring")

            if future_labels and future_values:
                fig_future = go.Figure(
                    data=[
                        go.Scatterpolar(
                            r=future_values + [future_values[0]],
                            theta=future_labels + [future_labels[0]],
                            fill="toself",
                            name="Priority Score",
                            marker=dict(color="#f59e0b")
                        )
                    ]
                )
                fig_future.update_layout(
                    polar=dict(
                        radialaxis=dict(visible=True, tickformat=".0f", range=[0, max(future_values) * 1.15])
                    ),
                    showlegend=False,
                    height=360,
                    **{**PLOTLY_LAYOUT, "margin": dict(l=10, r=10, t=20, b=10)},
                )
                fig_future.update_traces(
                    hovertemplate="%{theta}<br>Score: %{r:.1f}<extra></extra>"
                )
                st.plotly_chart(fig_future, use_container_width=True)
            else:
                st.info("No skill data available to compute this radar.")
                
    # ─────────────────────────────────────────────────────────
    # SUB-TAB 2: Skill Gap Engine
    # ─────────────────────────────────────────────────────────
    with sub_tabs[1]:
        st.markdown("#### ⚖️ Skill Gap Engine (Supply vs Demand)")
        st.caption("Compares India baseline skill supply with live job demand indexes.")

        stream_opt = st.selectbox(
            "Filter by your academic study stream:",
            options=["All Streams", "CS & IT", "Data Science", "Electronics", "Business", "Finance", "Design"],
            index=0
        )
        
        # Map selected stream label to taxonomy stream acronym
        stream_map = {
            "All Streams": "all",
            "CS & IT": "cs",
            "Data Science": "data",
            "Electronics": "elec",
            "Business": "biz",
            "Finance": "fin",
            "Design": "design"
        }
        stream_code = stream_map[stream_opt]
        
        # Load gap records (use cached 'all' result when stream is 'all', otherwise fetch)
        with st.spinner("Loading skill gap data..."):
            gap_records = (
                gap_records_all
                if stream_code == "all"
                else fetch_skill_gap_analysis(stream_code)
            )
        
        if gap_records:
            # Get latest date snapshot
            gap_df = pd.DataFrame(gap_records)
            latest_date = gap_df["date"].max()
            gap_df = gap_df[gap_df["date"] == latest_date]
            
            # Draw shortages & oversupply charts
            col_g1, col_g2 = st.columns(2)
            
            with col_g1:
                st.markdown("🔴 **Top Talent Shortages (Demand > Supply)**")
                shortages = gap_df[gap_df["gap_score"] > 5].sort_values("gap_score", ascending=False).head(5)
                if not shortages.empty:
                    fig_short = px.bar(
                        shortages, x="gap_score", y="skill_name", orientation="h",
                        color_discrete_sequence=["#ef4444"], labels={"gap_score": "Gap Percentage (pp)"},
                        height=250
                    )
                    fig_short.update_layout(**PLOTLY_LAYOUT)
                    fig_short.update_yaxes(autorange="reversed")
                    st.plotly_chart(fig_short, width='stretch')
                else:
                    st.info("No major skill shortages computed.")
                    
            with col_g2:
                st.markdown("🟢 **Saturated/Balanced Skills**")
                surplus = gap_df[gap_df["gap_score"] <= 5].sort_values("gap_score", ascending=True).head(5)
                if not surplus.empty:
                    fig_surp = px.bar(
                        surplus, x="gap_score", y="skill_name", orientation="h",
                        color_discrete_sequence=["#f59e0b"], labels={"gap_score": "Gap Percentage (pp)"},
                        height=250
                    )
                    fig_surp.update_layout(**PLOTLY_LAYOUT)
                    st.plotly_chart(fig_surp, width='stretch')
                else:
                    st.info("No major saturated skills computed.")
                    
            st.divider()
            
            # Full table
            st.markdown("##### 📋 Complete Stream Skill Gap Database")
            
            table_html = """
            <style>
            .badge-red { color:#ef4444; background:rgba(239,68,68,0.1); padding:2px 8px; border-radius:4px; font-weight:bold; }
            .badge-amber { color:#f59e0b; background:rgba(245,158,11,0.1); padding:2px 8px; border-radius:4px; font-weight:bold; }
            .badge-green { color:#10b981; background:rgba(16,185,129,0.1); padding:2px 8px; border-radius:4px; font-weight:bold; }
            .badge-gray { color:#94a3b8; background:rgba(148,163,184,0.1); padding:2px 8px; border-radius:4px; font-weight:bold; }
            </style>
            <table style="width:100%; border-collapse:collapse;">
                <thead>
                    <tr style="border-bottom:1px solid var(--border);">
                        <th style="text-align:left; padding:8px;">Skill</th>
                        <th style="text-align:left; padding:8px;">Baseline Supply %</th>
                        <th style="text-align:left; padding:8px;">Live Job Demand %</th>
                        <th style="text-align:left; padding:8px;">Gap (pp)</th>
                        <th style="text-align:left; padding:8px;">Market Verdict</th>
                    </tr>
                </thead>
                <tbody>
            """
            
            for _, row in gap_df.sort_values("gap_score", ascending=False).iterrows():
                score = row["gap_score"]
                if score > 20:
                    verdict = '<span class="badge-red">Critical Shortage</span>'
                elif score > 5:
                    verdict = '<span class="badge-amber">Shortage</span>'
                elif score < -20:
                    verdict = '<span class="badge-gray">Oversupply</span>'
                elif score < -5:
                    verdict = '<span class="badge-amber">Mild Saturated</span>'
                else:
                    verdict = '<span class="badge-green">Balanced</span>'
                    
                table_html += f"""
                    <tr style="border-bottom:0.5px solid var(--border);">
                        <td style="padding:8px;"><b>{row['skill_name']}</b></td>
                        <td style="padding:8px;">{row['supply_pct']}%</td>
                        <td style="padding:8px;">{row['demand_pct']}%</td>
                        <td style="padding:8px; color:{'#ef4444' if score > 0 else '#10b981'};">{"+" if score > 0 else ""}{score}pp</td>
                        <td style="padding:8px;">{verdict}</td>
                    </tr>
                """
            table_html += "</tbody></table>"
            st.markdown(table_html, unsafe_allow_html=True)
            
        else:
            st.info("Run the ingestion pipeline to compute skill gap analytics.")

    # ─────────────────────────────────────────────────────────
    # SUB-TAB 3: Tech Trends
    # ─────────────────────────────────────────────────────────
    with sub_tabs[2]:
        st.markdown("#### 📈 Emerging Technology Demand Trends")
        st.caption("Track historical skill demand indices to locate emerging/declining tech.")
        
        with st.spinner("Loading demand history..."):
            hist_records = fetch_skill_demand_history()
        
        if hist_records:
            hist_df = pd.DataFrame(hist_records)
            unique_skills = sorted(hist_df["skill_name"].unique())
            
            selected_skills = st.multiselect(
                "Select Technologies to plot:",
                options=unique_skills,
                default=unique_skills[:4] if len(unique_skills) >= 4 else unique_skills
            )
            
            if selected_skills:
                plot_df = hist_df[hist_df["skill_name"].isin(selected_skills)]
                fig_trend = px.line(
                    plot_df, x="date", y="demand_percentage", color="skill_name",
                    labels={"demand_percentage": "Demand Index (Jobs %)", "date": "Date"},
                    height=400, line_shape="spline"
                )
                fig_trend.update_layout(**PLOTLY_LAYOUT)
                st.plotly_chart(fig_trend, width='stretch')
            else:
                st.info("Select one or more technologies to plot trendlines.")
        else:
            st.info("No historical demand history has been computed yet. Run pipeline collection.")

    # ─────────────────────────────────────────────────────────
    # SUB-TAB 4: Salary Intel
    # ─────────────────────────────────────────────────────────
    with sub_tabs[3]:
        st.markdown("#### 💰 Salary Intelligence & Benchmarks")
        st.caption("Precomputed median salary indicators based on active vacancies.")
        
        with st.spinner("Loading salary data..."):
            sal_records = fetch_salary_insights()
        
        if sal_records:
            sal_df = pd.DataFrame(sal_records)
            
            sc1, sc2 = st.columns(2)
            
            with sc1:
                st.markdown("##### Median Salary by Job Field")
                field_sal = sal_df[sal_df["job_field"].notna() & sal_df["median_salary"].notna()]
                if not field_sal.empty:
                    fig_fsal = px.bar(
                        field_sal.sort_values("median_salary", ascending=True),
                        x="median_salary", y="job_field", orientation="h",
                        color_discrete_sequence=["#6366f1"],
                        height=250
                    )
                    fig_fsal.update_layout(**PLOTLY_LAYOUT)
                    st.plotly_chart(fig_fsal, width='stretch')
                else:
                    st.info("No salary insights by job field available.")
                    
            with sc2:
                st.markdown("##### Median Salary by City")
                city_sal = sal_df[sal_df["city"].notna() & sal_df["median_salary"].notna()]
                if not city_sal.empty:
                    fig_csal = px.bar(
                        city_sal.sort_values("median_salary", ascending=True),
                        x="median_salary", y="city", orientation="h",
                        color_discrete_sequence=["#06b6d4"],
                        height=250
                    )
                    fig_csal.update_layout(**PLOTLY_LAYOUT)
                    st.plotly_chart(fig_csal, width='stretch')
                else:
                    st.info("No salary insights by city available.")
                    
            st.divider()
            
            # Salary by skill
            st.markdown("##### Median Salary by Technology Skill")
            skill_sal = sal_df[sal_df["skill_name"].notna() & sal_df["median_salary"].notna()]
            if not skill_sal.empty:
                fig_ssal = px.bar(
                    skill_sal.sort_values("median_salary", ascending=False).head(12),
                    x="skill_name", y="median_salary",
                    color_discrete_sequence=["#8b5cf6"],
                    height=300
                )
                fig_ssal.update_layout(**PLOTLY_LAYOUT)
                st.plotly_chart(fig_ssal, width='stretch')
            else:
                st.info("No salary insights by skill available.")
        else:
            st.info("Ingest salary-disclosing jobs to compute median salary statistics.")

    # ─────────────────────────────────────────────────────────
    # SUB-TAB 5: AI Career Advisor
    # ─────────────────────────────────────────────────────────
    with sub_tabs[4]:
        st.markdown("#### 🤖 Dynamic AI Career Strategy Advisor")
        st.caption("Get tailored career strategy advice driven by real, precomputed market parameters.")
        
        # Check if AI Key is configured
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        custom_key = ""
        
        if not api_key or api_key == "your-gemini-api-key":
            st.warning("⚠️ Google Gemini API Key is not set in `.env` file.")
            custom_key = st.text_input("Please enter a temporary Gemini API Key for this session:", type="password")
            
        selected_key = custom_key.strip() if custom_key else api_key
        
        if not selected_key:
            st.info("Enter a valid Gemini API Key above to unlock the AI Career Advisor.")
        else:
            # Render inputs
            st.markdown("##### 🧑‍🎓 Fill Your Student Profile")
            
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                adv_field = st.selectbox(
                    "Field of Study / Academic Stream:",
                    options=["Computer Science / IT", "Data Science & Statistics", "Electronics & Communication", "Business Administration / MBA", "Commerce & Finance", "Mechanical / Civil Engineering", "Arts, Design & Humanities"]
                )
                adv_year = st.selectbox(
                    "Year of Study / Stage:",
                    options=["1st / 2nd year undergrad", "3rd / final year undergrad", "Post-grad / MBA student", "Recent graduate (0-1 yr exp)", "Early career (1-3 yr exp)"]
                )
            with col_a2:
                adv_skills = st.text_input("Your current skills (comma separated):", placeholder="e.g. Python, SQL, Excel, communication")
                adv_goal = st.text_input("Career Goals or specific question:", placeholder="e.g. I want to secure a product PM role in Bangalore")
                
            # Warn user if market data context is missing before they hit Generate
            _demand_preview = st.session_state.get("_gap_records_all")
            if not _demand_preview:
                st.warning(
                    "⚠️ **Market data not yet computed.** "
                    "The AI advisor will produce general guidance without live market grounding. "
                    "Run the ingestion pipeline first for best results.",
                    icon="⚠️",
                )

            # Show last AI response if it exists (persists across reruns)
            if "_ai_last_response" in st.session_state:
                st.markdown("##### 📋 Last Generated Strategy")
                st.info("ℹ️ This is your last generated response. Hit Generate again to refresh.")
                st.markdown(st.session_state["_ai_last_response"])
                st.divider()

            if st.button("🚀 Generate Personalized Strategy", width='stretch'):
                with st.spinner("Analyzing market data & generating strategy..."):
                    # 1. Gather dynamic labor context
                    # Get top demanded skills from precomputations
                    hist_data = fetch_skill_demand_history()
                    top_demands_str = "None"
                    if hist_data:
                        h_df = pd.DataFrame(hist_data)
                        latest_date = h_df["date"].max()
                        top_demands = h_df[h_df["date"] == latest_date].sort_values("demand_percentage", ascending=False).head(8)
                        top_demands_str = ", ".join([f"{r['skill_name']} ({r['demand_percentage']}% of jobs)" for _, r in top_demands.iterrows()])
                        
                    # Get dynamic shortages (reuse cached result)
                    top_gaps_str = "Not available — run the ingestion pipeline to compute gap data."
                    if gap_records_all:
                        g_df = pd.DataFrame(gap_records_all)
                        latest_date = g_df["date"].max()
                        top_gaps = g_df[(g_df["date"] == latest_date) & (g_df["gap_score"] > 5)].sort_values("gap_score", ascending=False).head(5)
                        if not top_gaps.empty:
                            top_gaps_str = ", ".join([f"{r['skill_name']} (Talent Gap: +{r['gap_score']} pp)" for _, r in top_gaps.iterrows()])
                        
                    # Get top hiring locations
                    loc_data = fetch_location_insights()
                    top_locs_str = "Not available — no location data computed yet."
                    if loc_data:
                        l_df = pd.DataFrame(loc_data)
                        latest_date = l_df["date"].max()
                        top_locs = l_df[l_df["date"] == latest_date].sort_values("job_count", ascending=False).head(5)
                        if not top_locs.empty:
                            top_locs_str = ", ".join([f"{r['city']} ({r['job_count']} listings)" for _, r in top_locs.iterrows()])
                        
                    # Get median salary indicators
                    sal_data = fetch_salary_insights()
                    salary_str = "Not available — no salary data computed yet."
                    if sal_data:
                        s_df = pd.DataFrame(sal_data)
                        skill_sal = s_df[s_df["skill_name"].notna()].sort_values("median_salary", ascending=False).head(3)
                        if not skill_sal.empty:
                            salary_str = "Top paying skills by median salary: " + ", ".join([f"{r['skill_name']} (median: ₹{r['median_salary']/100000:.1f}L)" for _, r in skill_sal.iterrows()])
                            
                    # Construct Gemini Prompt
                    prompt = f"""You are a top-tier labor market analyst and career strategist.
                    Provide a direct, blunt, and highly tailored career development roadmap based on real, live Indian market metrics.

                    STUDENT PROFILE:
                    - Field of Study: {adv_field}
                    - Career Stage: {adv_year}
                    - Current Skills: {adv_skills or "None specified"}
                    - Career Goals: {adv_goal or "Secure a high-paying role"}

                    LIVE INDIAN LABOR MARKET CONTEXT (sourced from pipeline — use only what is available):
                    - Top Demanded Skills: {top_demands_str}
                    - Top Skill Shortages (Demand > Supply): {top_gaps_str}
                    - Top Hiring Locations: {top_locs_str}
                    - Salary Benchmarks: {salary_str}

                    Important: If any data field above says "Not available", do NOT fabricate numbers or cite external reports. Acknowledge the gap and reason from first principles.

                    Provide the following sections:
                    1. **Blunt Market Assessment (1-2 paragraphs)**: Analyze the student's competitive position in their field. Address saturation vs shortages directly.
                    2. **Top 3 Skills to Acquire**: Target the dynamic talent shortages above. Provide justification.
                    3. **6-Month Milestones Plan**: Month-by-month actionable checklist. Suggest free/affordable resources (NPTEL, Kaggle, Coursera audit mode).
                    4. **Realistic Salary Range (INR)**: Benchmark ranges based on available data. If no salary data is available, state that clearly.
                    5. **Contrarian Insight**: One piece of advice most students hear that is actually wrong for this specific market right now.

                    Avoid corporate buzzwords, generic advice, or invented statistics. Speak like a real analyst.
                    """
                    
                    # Invoke Gemini
                    response_text = "Failed to run advisor."
                    try:
                        from google import genai
                        client = genai.Client(api_key=selected_key)
                        response = client.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=prompt
                        )
                        response_text = response.text
                    except Exception as e:
                        response_text = f"Failed to connect to Gemini API: {e}"
                        
                    # Persist response so user can scroll back after reruns
                    st.session_state["_ai_last_response"] = response_text

                    st.markdown("##### 🚀 Your Customized Labor Strategy Roadmap")
                    # Gemini returns markdown — render it natively; no manual HTML escaping needed
                    st.markdown(response_text)
