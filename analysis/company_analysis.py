import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from analysis.helpers import COLORS, PLOTLY_LAYOUT, kpi_card, skill_counter

WORK_MODE_COLORS = {
    "Remote":  "#22c55e",
    "Hybrid":  "#6366f1",
    "Onsite":  "#f43f5e",
    "On-site": "#f43f5e",
}

def _explode_skills(df: pd.DataFrame) -> pd.DataFrame:
    """Return a long-form DataFrame with one row per (job, skill)."""
    mask = df["standardized_skills"].apply(lambda x: isinstance(x, list))
    return (
        df[mask]
        .explode("standardized_skills")
        .rename(columns={"standardized_skills": "skill"})
        .dropna(subset=["skill"])
    )

def render_company_analysis(df: pd.DataFrame) -> None:
    st.markdown("### 🏢 Company Analysis")
    if df.empty:
        st.info("No data available.")
        return

    # Extra per-tab pruning (in addition to global sidebar filters)
    with st.expander("🧹 Further prune (within Companies tab)", expanded=False):
        city_options = sorted(df["city"].dropna().unique().tolist()) if "city" in df.columns else []
        mode_options = sorted(df["work_mode"].dropna().unique().tolist()) if "work_mode" in df.columns else []

        selected_cities = st.multiselect(
            "Cities",
            city_options,
            default=[],
            label_visibility="collapsed",
            placeholder="All cities",
        )
        selected_modes = st.multiselect(
            "Work modes",
            mode_options,
            default=[],
            label_visibility="collapsed",
            placeholder="All work modes",
        )

        df = df.copy()
        if selected_cities:
            df = df[df["city"].isin(selected_cities)]
        if selected_modes:
            df = df[df["work_mode"].isin(selected_modes)]

        if df.empty:
            st.info("No data left after applying the Companies-tab filters.")
            return

    # Exclude 'Unknown' company for aggregates
    df_known = df[df["company"].notna() & (df["company"] != "Unknown")].copy()
    if df_known.empty:
        st.info("No jobs with known company data. Try broadening your filters.")
        return

    total_jobs = len(df)

    # ── KPI Section ──
    # 1. Top Employer
    top_employer = df_known["company"].value_counts().idxmax()
    top_employer_count = df_known["company"].value_counts().max()
    
    # 2. Skill-Heavy Recruiter (min 10 jobs)
    company_counts = df_known["company"].value_counts()
    companies_ge_10 = company_counts[company_counts >= 10].index
    if not companies_ge_10.empty:
        df_known["_skill_count"] = df_known["standardized_skills"].apply(
            lambda x: len(x) if isinstance(x, list) else 0
        )
        skill_heavy_company = df_known[df_known["company"].isin(companies_ge_10)].groupby("company")["_skill_count"].mean().idxmax()
        skill_heavy_val = df_known[df_known["company"].isin(companies_ge_10)].groupby("company")["_skill_count"].mean().max()
    else:
        skill_heavy_company = "N/A"
        skill_heavy_val = 0.0

    # 3. Geographically Diverse Recruiter (min 5 jobs)
    df_geo = df_known[(df_known["city"].notna()) & (df_known["city"] != "Unknown")]
    geo_counts = df_geo["company"].value_counts()
    companies_ge_5 = geo_counts[geo_counts >= 5].index
    if not companies_ge_5.empty:
        diverse_company = df_geo[df_geo["company"].isin(companies_ge_5)].groupby("company")["city"].nunique().idxmax()
        diverse_val = df_geo[df_geo["company"].isin(companies_ge_5)].groupby("company")["city"].nunique().max()
    else:
        diverse_company = "N/A"
        diverse_val = 0

    c1, c2, c3 = st.columns(3)
    with c1:
        kpi_card("Top Employer", top_employer, "🏢", f"{top_employer_count} job listings")
    with c2:
        kpi_card("Skill-Heavy Recruiter", skill_heavy_company, "🔧", f"Avg {skill_heavy_val:.1f} skills/job (min 10 jobs)")
    with c3:
        kpi_card("Geographically Diverse", diverse_company, "🌍", f"Hiring in {diverse_val} cities (min 5 jobs)")

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-header'>📊 Hiring Leaderboard & Focus Areas</div>", unsafe_allow_html=True)

    # ── Top 15 Hiring Companies Bar Chart ──
    top_15_counts = df_known["company"].value_counts().head(15).reset_index()
    top_15_counts.columns = ["Company", "Job Count"]
    top_15_counts["Percentage"] = (top_15_counts["Job Count"] / total_jobs * 100)
    top_15_counts = top_15_counts.sort_values("Job Count", ascending=True)

    fig_leaderboard = px.bar(
        top_15_counts,
        x="Job Count",
        y="Company",
        orientation="h",
        color="Job Count",
        color_continuous_scale=["#1e3a5f", "#6366f1", "#06b6d4"],
        title="Top 15 Hiring Companies by Job Openings"
    )
    fig_leaderboard.update_traces(
        customdata=top_15_counts[["Percentage"]],
        texttemplate="%{x} (%{customdata[0]:.1f}%)",
        textposition="outside"
    )
    fig_leaderboard.update_layout(**PLOTLY_LAYOUT)
    fig_leaderboard.update_layout(yaxis={"categoryorder": "total ascending"})
    fig_leaderboard.update_coloraxes(showscale=False)
    st.plotly_chart(fig_leaderboard, width="stretch")

    # Auto-insight
    lead_company = top_15_counts.iloc[-1]["Company"]
    lead_pct = top_15_counts.iloc[-1]["Percentage"]
    st.caption(f"💡 **Insight:** **{lead_company}** accounts for **{lead_pct:.1f}%** of all listings in the filtered set.")

    # ── Hiring Focus Sunburst Chart ──
    if "job_category" in df_known.columns:
        top_10_companies = df_known["company"].value_counts().head(10).index.tolist()
        focus_df = df_known[df_known["company"].isin(top_10_companies)].groupby(["company", "job_category"]).size().reset_index(name="count")
        
        # Guard: check if sunburst has enough data
        if len(focus_df["company"].unique()) >= 2:
            st.markdown("<div class='section-header'>🏷️ Employer Focus Hierarchy</div>", unsafe_allow_html=True)
            fig_sunburst = px.sunburst(
                focus_df,
                path=["company", "job_category"],
                values="count",
                title="Hiring Focus of Top 10 Companies by Job Category",
                color="count",
                color_continuous_scale="RdPu"
            )
            fig_sunburst.update_layout(**PLOTLY_LAYOUT)
            st.plotly_chart(fig_sunburst, width="stretch")

    # ── Company Directory Drill-Down ──
    st.markdown("<div class='section-header'>🔍 Company Drill-Down & Profile Directory</div>", unsafe_allow_html=True)
    
    companies_list = df_known["company"].value_counts()
    eligible_companies = sorted(companies_list[companies_list >= 3].index.tolist())
    
    if eligible_companies:
        selected_company = st.selectbox("Search & select a company to inspect:", eligible_companies, key="co_company_select")
        co_df = df_known[df_known["company"] == selected_company].copy()
        
        if len(co_df) < 5:
            st.warning(f"⚠️ Only {len(co_df)} listings found for {selected_company}. Results may not be fully representative of overall company patterns.")
            
        col_a, col_b = st.columns([1, 1])
        
        with col_a:
            # Stats Cards
            st.markdown(f"#### 🏢 {selected_company} Profile")
            c_jobs = len(co_df)
            c_cities = co_df["city"].nunique()
            
            # Remote share
            remote_hybrid = co_df["work_mode"].isin(["Remote", "Hybrid"]).sum()
            remote_pct = (remote_hybrid / c_jobs * 100) if c_jobs > 0 else 0
            
            c_col1, c_col2, c_col3 = st.columns(3)
            with c_col1:
                kpi_card("Total Jobs", f"{c_jobs}", "📊")
            with c_col2:
                kpi_card("Cities Hubs", f"{c_cities}", "📍")
            with c_col3:
                kpi_card("Remote/Hybrid", f"{remote_pct:.0f}%", "🌐")
                
            # Work Mode Donut Chart (max 3 slices)
            mode_counts = co_df["work_mode"].value_counts().reset_index()
            mode_counts.columns = ["work_mode", "count"]
            
            # Map work mode color map to match WORK_MODE_COLORS
            fig_donut = px.pie(
                mode_counts,
                values="count",
                names="work_mode",
                hole=0.5,
                color="work_mode",
                color_discrete_map=WORK_MODE_COLORS,
                title="Work Mode Distribution"
            )
            fig_donut.update_layout(**PLOTLY_LAYOUT)
            st.plotly_chart(fig_donut, width="stretch")
            
        with col_b:
            # City Distribution
            city_dist = co_df["city"].value_counts().head(5).reset_index()
            city_dist.columns = ["City", "Job Count"]
            
            fig_city = px.bar(
                city_dist,
                x="Job Count",
                y="City",
                orientation="h",
                color="Job Count",
                color_continuous_scale=["#1e3a5f", "#6366f1"],
                title="Top Hiring Hubs"
            )
            fig_city.update_layout(**PLOTLY_LAYOUT)
            fig_city.update_layout(yaxis={"categoryorder": "total ascending"})
            fig_city.update_coloraxes(showscale=False)
            st.plotly_chart(fig_city, width="stretch")
            
        # Tech Stack / Skill Profile
        co_skills = skill_counter(co_df, 10)
        if co_skills:
            co_skills_df = pd.DataFrame(co_skills, columns=["Skill", "Count"])
            co_skills_df = co_skills_df.sort_values("Count", ascending=True)
            
            fig_co_skills = px.bar(
                co_skills_df,
                x="Count",
                y="Skill",
                orientation="h",
                color="Count",
                color_continuous_scale=["#1e3a5f", "#8b5cf6"],
                title=f"{selected_company} — Required Tech Stack (Top 10)"
            )
            fig_co_skills.update_layout(**PLOTLY_LAYOUT)
            fig_co_skills.update_coloraxes(showscale=False)
            st.plotly_chart(fig_co_skills, width="stretch")

        # Category Breakdown
        if "job_category" in co_df.columns:
            cat_dist = co_df["job_category"].value_counts().reset_index()
            cat_dist.columns = ["Category", "Job Count"]
            fig_cat = px.bar(
                cat_dist,
                x="Job Count",
                y="Category",
                orientation="h",
                color="Category",
                color_discrete_sequence=COLORS,
                title=f"{selected_company} — Job Category Breakdown"
            )
            fig_cat.update_layout(**PLOTLY_LAYOUT)
            fig_cat.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig_cat, width="stretch")

        # Job URLs Table
        st.markdown(f"#### Active Job Postings at {selected_company}")
        url_col = "job_url" if "job_url" in co_df.columns else ("url" if "url" in co_df.columns else None)
        
        display_cols = ["title", "city", "work_mode"]
        if url_col:
            display_cols.append(url_col)
            
        active_listings = co_df[display_cols].dropna(subset=["title"])
        
        if not active_listings.empty:
            if url_col:
                st.dataframe(
                    active_listings,
                    column_config={
                        url_col: st.column_config.LinkColumn("Job Link")
                    },
                    width="stretch"
                )
            else:
                st.dataframe(active_listings, width="stretch")
        else:
            st.info("No active listings with links available.")
    else:
        st.info("No companies with at least 3 job listings available for drill-down.")
