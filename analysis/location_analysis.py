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

def render_location_analysis(df: pd.DataFrame) -> None:
    st.markdown("### 📍 Location Analysis")
    if df.empty:
        st.info("No data available.")
        return

    # Pre-filter at top of function
    df_known = df[df["city"].notna() & (df["city"] != "Unknown")].copy()
    if df_known.empty:
        st.info("No jobs with known city data. Try removing location filters.")
        return

    total_jobs = len(df_known)

    # ── KPI Section ──
    # 1. Top Hiring City
    top_city = df_known["city"].value_counts().idxmax()
    top_city_count = df_known["city"].value_counts().max()

    # 2. Remote-Friendliest City (among cities with >= 20 jobs, or >= 5 if none)
    city_counts = df_known["city"].value_counts()
    threshold = 20
    cities_above_thresh = city_counts[city_counts >= threshold].index
    if cities_above_thresh.empty:
        threshold = 5
        cities_above_thresh = city_counts[city_counts >= threshold].index

    if not cities_above_thresh.empty:
        df_thresh = df_known[df_known["city"].isin(cities_above_thresh)]
        remote_by_city = df_thresh.groupby("city")["work_mode"].apply(
            lambda x: x.isin(["Remote", "Hybrid"]).sum() / len(x) * 100
        )
        remote_friendliest = remote_by_city.idxmax()
        remote_friendliest_val = remote_by_city.max()
    else:
        remote_friendliest = "N/A"
        remote_friendliest_val = 0.0

    # 3. High-Salary Hub (among cities with >= 10 salary rows)
    high_salary_city = "N/A"
    high_salary_val = 0.0
    if "max_salary" in df_known.columns:
        sal_df = df_known[df_known["max_salary"].notna()]
        sal_city_counts = sal_df["city"].value_counts()
        eligible_sal_cities = sal_city_counts[sal_city_counts >= 10].index
        if not eligible_sal_cities.empty:
            sal_city_means = sal_df[sal_df["city"].isin(eligible_sal_cities)].groupby("city")["max_salary"].mean()
            high_salary_city = sal_city_means.idxmax()
            high_salary_val = sal_city_means.max()

    # 4. Talent Maturity Index (highest median min_exp)
    talent_mature_city = "N/A"
    talent_mature_val = 0.0
    if "min_exp" in df_known.columns and df_known["min_exp"].notna().sum() > 0:
        exp_df = df_known[df_known["min_exp"].notna()]
        exp_city_counts = exp_df["city"].value_counts()
        eligible_exp_cities = exp_city_counts[exp_city_counts >= 5].index
        if not eligible_exp_cities.empty:
            exp_city_medians = exp_df[exp_df["city"].isin(eligible_exp_cities)].groupby("city")["min_exp"].median()
            talent_mature_city = exp_city_medians.idxmax()
            talent_mature_val = exp_city_medians.max()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Top Hiring City", top_city, "📍", f"{top_city_count} jobs ({top_city_count/total_jobs*100:.1f}%)")
    with c2:
        kpi_card("Remote-Friendliest Hub", remote_friendliest, "🌐", f"{remote_friendliest_val:.1f}% Remote/Hybrid (min {threshold} jobs)")
    with c3:
        if high_salary_city != "N/A":
            kpi_card("High-Salary Hub", high_salary_city, "💸", f"Avg Max Salary: {high_salary_val:.1f} LPA")
        else:
            kpi_card("High-Salary Hub", "N/A", "💸", "Insufficient salary data")
    with c4:
        if talent_mature_city != "N/A":
            kpi_card("Talent Maturity Index", talent_mature_city, "🎓", f"Median Min Exp: {talent_mature_val:.1f} yrs")
        else:
            kpi_card("Talent Maturity Index", "N/A", "🎓", "Insufficient experience data")

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-header'>📊 Geographical & Work Mode Distribution</div>", unsafe_allow_html=True)

    # ── Multi-Tab Insights ──
    tab_geo, tab_work_mode, tab_skills = st.tabs(["🌍 Geo Distribution", "📈 Work Mode Mix", "🔧 City × Skill Heatmap"])

    with tab_geo:
        # Bar Chart of Top Cities
        top_n = st.slider("Number of Cities to display", 5, 30, 15, key="loc_top_n")
        city_counts_bar = df_known["city"].value_counts().head(top_n).reset_index()
        city_counts_bar.columns = ["City", "Job Count"]

        fig_bar = px.bar(
            city_counts_bar,
            x="City",
            y="Job Count",
            color="Job Count",
            color_continuous_scale=["#1e3a5f", "#6366f1", "#06b6d4"],
            title=f"Top {top_n} Cities for Job Openings"
        )
        fig_bar.update_layout(**PLOTLY_LAYOUT, xaxis_tickangle=-45)
        fig_bar.update_coloraxes(showscale=False)
        st.plotly_chart(fig_bar, width="stretch")

        # Treemap mapping State -> City (if state column exists)
        if "state" in df_known.columns and df_known["state"].nunique() > 1:
            st.markdown("#### State → City Hierarchy")
            tree_df = df_known.groupby(["state", "city"]).size().reset_index(name="count")
            fig_tree = px.treemap(
                tree_df,
                path=["state", "city"],
                values="count",
                color="count",
                color_continuous_scale="Blues",
                title="Job Distribution by State and City"
            )
            fig_tree.update_layout(**PLOTLY_LAYOUT)
            st.plotly_chart(fig_tree, width="stretch")

    with tab_work_mode:
        # Stacked horizontal bar for top 12 cities
        top_12_cities = df_known["city"].value_counts().head(12).index.tolist()
        df_top_12 = df_known[df_known["city"].isin(top_12_cities) & (df_known["work_mode"] != "Unknown")]
        
        if not df_top_12.empty:
            mode_counts = df_top_12.groupby(["city", "work_mode"]).size().reset_index(name="count")
            pivot_mode = mode_counts.pivot(index="city", columns="work_mode", values="count").fillna(0)
            pivot_mode_pct = pivot_mode.div(pivot_mode.sum(axis=1), axis=0) * 100
            pivot_mode_pct = pivot_mode_pct.reset_index()
            melted_mode = pivot_mode_pct.melt(id_vars="city", value_name="Percentage", var_name="Work Mode")
            
            fig_mode = px.bar(
                melted_mode,
                x="Percentage",
                y="city",
                color="Work Mode",
                orientation="h",
                barmode="stack",
                category_orders={"city": top_12_cities},
                color_discrete_map=WORK_MODE_COLORS,
                title="Work Mode Distribution within Top 12 Cities (100% Stacked)",
                labels={"Percentage": "Percentage (%)", "city": "City"}
            )
            fig_mode.update_layout(**PLOTLY_LAYOUT)
            st.plotly_chart(fig_mode, width="stretch")
            
            # Auto-insight
            remote_cols = [c for c in ["Remote", "Hybrid"] if c in pivot_mode.columns]
            if remote_cols:
                pivot_mode["remote_hybrid_pct"] = pivot_mode[remote_cols].sum(axis=1) / pivot_mode.sum(axis=1) * 100
                most_remote_city = pivot_mode["remote_hybrid_pct"].idxmax()
                pct = pivot_mode["remote_hybrid_pct"].max()
                st.caption(f"💡 **Insight:** **{most_remote_city}** has the highest remote/hybrid share at **{pct:.0f}%** among top hiring hubs.")
        else:
            st.info("No work mode data available.")

    with tab_skills:
        # Heatmap of City x Skill
        if "standardized_skills" in df_known.columns:
            skills_long = _explode_skills(df_known)
            top_10_cities = df_known["city"].value_counts().head(10).index.tolist()
            top_10_skills = [s for s, _ in skill_counter(df_known, 10)]
            
            skills_long_filtered = skills_long[skills_long["city"].isin(top_10_cities) & skills_long["skill"].isin(top_10_skills)]
            
            if not skills_long_filtered.empty:
                pivot = skills_long_filtered.pivot_table(index="city", columns="skill", aggfunc="size", fill_value=0)
                city_job_counts = df_known["city"].value_counts().reindex(pivot.index)
                pivot_pct = pivot.div(city_job_counts, axis=0) * 100
                
                # Reindex for alignment
                pivot_pct = pivot_pct.reindex(index=top_10_cities, columns=top_10_skills).fillna(0)
                
                fig_heat = px.imshow(
                    pivot_pct,
                    labels=dict(x="Skill", y="City", color="Share (%)"),
                    x=pivot_pct.columns,
                    y=pivot_pct.index,
                    color_continuous_scale="RdPu",
                    text_auto=".0f",
                    title="Top Cities × Top Skills Matrix (% of local jobs requiring skill)"
                )
                fig_heat.update_layout(**PLOTLY_LAYOUT)
                st.plotly_chart(fig_heat, width="stretch")
            else:
                st.info("Not enough skill matches to display heatmap.")
        else:
            st.info("No skill data available.")

    # ── City Drill-Down Profile ──
    st.markdown("<div class='section-header'>🔍 City Drill-Down Profile Directory</div>", unsafe_allow_html=True)
    top_30_cities = df_known["city"].value_counts().head(30).index.tolist()
    
    if top_30_cities:
        selected_city = st.selectbox("Select a city to inspect:", top_30_cities, key="loc_city_drill")
        city_df = df_known[df_known["city"] == selected_city].copy()
        
        if len(city_df) < 5:
            st.warning("⚠️ Too few listings for a reliable statistical profile in this city.")
            
        col_a, col_b = st.columns(2)
        
        with col_a:
            st.markdown(f"#### 🏙️ {selected_city} Overview")
            
            # City KPIs
            city_jobs = len(city_df)
            
            # Top category
            cat_col = "job_field" if "job_field" in city_df.columns and city_df["job_field"].nunique() > 0 else "job_category"
            city_cat_series = city_df[city_df[cat_col].notna() & (city_df[cat_col] != "Other")][cat_col]
            top_cat = city_cat_series.mode().iloc[0] if not city_cat_series.empty else "N/A"
            
            # Remote share
            city_rem_hybrid = city_df["work_mode"].isin(["Remote", "Hybrid"]).sum()
            city_rem_pct = (city_rem_hybrid / city_jobs * 100) if city_jobs > 0 else 0
            
            cc1, cc2, cc3 = st.columns(3)
            with cc1:
                kpi_card("Job Volume", f"{city_jobs}", "📊")
            with cc2:
                kpi_card("Top Category", top_cat, "🏷️")
            with cc3:
                kpi_card("Remote/Hybrid", f"{city_rem_pct:.0f}%", "🌐")
                
            # Top 5 companies
            top_companies = city_df[city_df["company"] != "Unknown"]["company"].value_counts().head(5).reset_index()
            top_companies.columns = ["Company", "Job Count"]
            
            fig_co = px.bar(
                top_companies,
                x="Job Count",
                y="Company",
                orientation="h",
                color="Job Count",
                color_continuous_scale=["#1e3a5f", "#6366f1"],
                title="Top Hiring Employers"
            )
            fig_co.update_layout(**PLOTLY_LAYOUT)
            fig_co.update_layout(yaxis={"categoryorder": "total ascending"})
            fig_co.update_coloraxes(showscale=False)
            st.plotly_chart(fig_co, width="stretch")
            
        with col_b:
            # Category breakdown
            cat_breakdown = city_df["job_category"].value_counts().head(5).reset_index()
            cat_breakdown.columns = ["Category", "Job Count"]
            
            fig_cat = px.bar(
                cat_breakdown,
                x="Job Count",
                y="Category",
                orientation="h",
                color="Category",
                color_discrete_sequence=COLORS,
                title="Top Categories hiring"
            )
            fig_cat.update_layout(**PLOTLY_LAYOUT)
            fig_cat.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig_cat, width="stretch")

        # Top 10 skills
        st.markdown(f"#### Top 10 Required Skills in {selected_city}")
        city_skills = skill_counter(city_df, 10)
        
        if city_skills:
            max_count = city_skills[0][1]
            skill_cols = st.columns(2)
            
            for idx, (skill, count) in enumerate(city_skills):
                col_idx = idx % 2
                progress_val = count / max_count if max_count > 0 else 0.0
                
                with skill_cols[col_idx]:
                    st.markdown(f"**{skill}** — {count} jobs")
                    st.progress(progress_val)
        else:
            st.info("No skill data available for this city.")
    else:
        st.info("No city data available for drill-down.")
