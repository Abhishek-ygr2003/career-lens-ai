import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from analysis.helpers import COLORS, PLOTLY_LAYOUT, EXP_BAND_ORDER, kpi_card, skill_counter

WORK_MODE_COLORS = {
    "Remote":  "#22c55e",
    "Hybrid":  "#6366f1",
    "Onsite":  "#f43f5e",
    "On-site": "#f43f5e",
}

def render_experience_analysis(df: pd.DataFrame) -> None:
    st.markdown("### 🎓 Experience Requirements")
    if df.empty:
        st.info("No data available.")
        return

    # ── KPI Cards Section ──
    c1, c2, c3, c4 = st.columns(4)
    
    # 1. Entry-Level Index (% of jobs for 0-2 yrs)
    total_jobs = len(df)
    entry_jobs = df["exp_band"].isin(["Fresher (0–2 yrs)"]).sum()
    entry_pct = (entry_jobs / total_jobs * 100) if total_jobs > 0 else 0.0
    
    # 2. Senior Leadership Index (% of jobs with min_exp >= 8)
    valid_min_exp = df["min_exp"].dropna()
    senior_jobs = (valid_min_exp >= 8).sum()
    senior_pct = (senior_jobs / len(valid_min_exp) * 100) if not valid_min_exp.empty else 0.0
    
    # 3. Avg Min Experience
    avg_min_exp = valid_min_exp.mean() if not valid_min_exp.empty else 0.0
    
    # 4. Specified vs Not Specified
    specified = df["min_exp"].notna().sum()
    not_specified = df["min_exp"].isna().sum()
    
    with c1:
        kpi_card("Entry-Level Share", f"{entry_pct:.1f}%", "🌱", f"{entry_jobs} Fresher jobs")
    with c2:
        kpi_card("Senior Share", f"{senior_pct:.1f}%", "🚀", f"{senior_jobs} roles (8+ yrs)")
    with c3:
        kpi_card("Avg Min Experience", f"{avg_min_exp:.1f} yrs", "📅", "Required on average")
    with c4:
        kpi_card("Exp Specified", f"{specified:,}", "🔎", f"{not_specified:,} not specified")

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-header'>📊 Experience Distribution & Market Trends</div>", unsafe_allow_html=True)

    # ── Chart 1: Experience Band Distribution ──
    view_as = st.radio("View distribution as", ["Count", "Percentage"], horizontal=True, key="exp_dist_view")
    
    exp_counts = df['exp_band'].value_counts().reindex(EXP_BAND_ORDER).fillna(0).reset_index()
    exp_counts.columns = ['Experience Level', 'Count']
    
    if view_as == "Percentage":
        total = exp_counts['Count'].sum()
        if total > 0:
            exp_counts['Count'] = (exp_counts['Count'] / total) * 100

    fig_dist = px.bar(
        exp_counts, 
        x='Experience Level', y='Count',
        color='Experience Level',
        color_discrete_sequence=COLORS,
        title="Jobs by Experience Level",
        labels={"Count": "% of Jobs" if view_as == "Percentage" else "Job Count"}
    )
    if view_as == "Percentage":
        fig_dist.update_traces(texttemplate='%{y:.1f}%', textposition='outside')
    else:
        fig_dist.update_traces(texttemplate='%{y}', textposition='outside')
        
    fig_dist.update_layout(**PLOTLY_LAYOUT)
    fig_dist.update_layout(showlegend=False, margin=dict(t=50))
    st.plotly_chart(fig_dist, width="stretch")

    # ── Chart 2: Experience vs Salary Box Plot ──
    salary_df = df[df["min_salary"].notna() | df["max_salary"].notna()]
    if len(salary_df) >= 30:
        st.markdown("<div class='section-header'>💸 Salary Progression by Experience</div>", unsafe_allow_html=True)
        # We plot min_salary and max_salary as two box plots grouped by exp_band
        # To do this cleanly in px.box:
        fig_box = px.box(
            salary_df,
            x="exp_band",
            y=["min_salary", "max_salary"],
            title="Salary Ranges by Experience Level (LPA / INR)",
            labels={"value": "Salary (LPA)", "variable": "Salary Type", "exp_band": "Experience Level"},
            category_orders={"exp_band": EXP_BAND_ORDER},
            color_discrete_sequence=["#6366f1", "#06b6d4"]
        )
        fig_box.update_layout(**PLOTLY_LAYOUT)
        st.plotly_chart(fig_box, width="stretch")
    else:
        st.info("Not enough salary data (minimum 30 records required) to display Salary Box Plot.")

    # ── Chart 3: Category × Experience Heatmap ──
    if "job_category" in df.columns:
        st.markdown("<div class='section-header'>📂 Category × Experience Mix</div>", unsafe_allow_html=True)
        top_cats = df["job_category"].value_counts().head(8).index.tolist()
        cat_df = df[df["job_category"].isin(top_cats)]
        
        if not cat_df.empty:
            pivot = pd.crosstab(cat_df["job_category"], cat_df["exp_band"], normalize="index") * 100
            # Ensure order of columns matches EXP_BAND_ORDER
            present_cols = [b for b in EXP_BAND_ORDER if b in pivot.columns]
            pivot = pivot.reindex(columns=present_cols).fillna(0)
            
            fig_heat = px.imshow(
                pivot,
                labels=dict(x="Experience Band", y="Job Category", color="Percentage (%)"),
                x=pivot.columns,
                y=pivot.index,
                color_continuous_scale="RdPu",
                text_auto=".0f",
                title="Job Category vs Experience Band Distribution (Row Normalized %)"
            )
            fig_heat.update_layout(**PLOTLY_LAYOUT)
            st.plotly_chart(fig_heat, width="stretch")
        else:
            st.info("Not enough category data to show heatmap.")

    # ── Section 4: Skills by Experience Level (Drill-down) ──
    st.markdown("<div class='section-header'>🔧 Top Skills by Experience Level</div>", unsafe_allow_html=True)
    available_bands = [b for b in EXP_BAND_ORDER if b in df["exp_band"].unique() and b != "Not Specified"]
    
    if available_bands:
        selected_band = st.selectbox(
            "Select an experience band to analyze skill demand:",
            options=available_bands,
            key="exp_band_select"
        )
        
        band_df = df[df["exp_band"] == selected_band]
        top_skills = skill_counter(band_df, 10)
        
        if top_skills:
            skills_bar_df = pd.DataFrame(top_skills, columns=["Skill", "Count"])
            skills_bar_df = skills_bar_df.sort_values("Count", ascending=True)
            
            fig_skills = px.bar(
                skills_bar_df,
                x="Count",
                y="Skill",
                orientation="h",
                color="Count",
                color_continuous_scale=["#1e3a5f", "#6366f1", "#06b6d4"],
                title=f"Top 10 Demanded Skills for {selected_band}",
                labels={"Count": "Job Count"}
            )
            fig_skills.update_layout(**PLOTLY_LAYOUT)
            fig_skills.update_coloraxes(showscale=False)
            st.plotly_chart(fig_skills, width="stretch")
            
            # Auto-insight
            overall_skills = skill_counter(df, 1)
            if overall_skills:
                overall_top = overall_skills[0][0]
                band_top = skills_bar_df.iloc[-1]["Skill"]
                if band_top != overall_top:
                    st.caption(f"💡 **Insight:** For {selected_band} roles, **{band_top}** becomes the primary skill demand, overtaking the overall market leader **{overall_top}**.")
                else:
                    st.caption(f"💡 **Insight:** For {selected_band} roles, **{band_top}** continues to lead the market demand, aligned with general trends.")
        else:
            st.info("No skill data available for this experience level.")
    else:
        st.info("No experience band data available to analyze skills.")
