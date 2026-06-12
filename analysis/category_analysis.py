import streamlit as st
import pandas as pd
import plotly.express as px
from analysis.helpers import COLORS, PLOTLY_LAYOUT, kpi_card, skill_counter

WORK_MODE_COLORS = {
    "Remote":  "#22c55e",
    "Hybrid":  "#6366f1",
    "Onsite":  "#f43f5e",
    "On-site": "#f43f5e",
}

def render_category_analysis(df: pd.DataFrame) -> None:
    st.markdown("### 📂 Category Analysis")
    if df.empty:
        st.info("No data available.")
        return

    # Filter out Unknown / missing categories for standard views
    df_known = df[df["job_category"].notna() & (df["job_category"] != "Other")].copy()
    if df_known.empty:
        df_known = df.copy()

    # ── KPI Cards Section ──
    # 1. Highest-Paying Category
    sal_df = df_known[df_known["max_salary"].notna()]
    cat_sal_counts = sal_df["job_category"].value_counts()
    eligible_sal_cats = cat_sal_counts[cat_sal_counts >= 10].index
    if not eligible_sal_cats.empty:
        highest_paying = sal_df[sal_df["job_category"].isin(eligible_sal_cats)].groupby("job_category")["max_salary"].mean().idxmax()
        highest_paying_val = sal_df[sal_df["job_category"].isin(eligible_sal_cats)].groupby("job_category")["max_salary"].mean().max()
    else:
        highest_paying = "N/A"
        highest_paying_val = 0.0

    # 2. Remote-Friendliest Category
    mode_df = df_known[df_known["work_mode"] != "Unknown"]
    if not mode_df.empty:
        # Calculate Remote + Hybrid share per category
        mode_counts = mode_df.groupby(["job_category", "work_mode"]).size().reset_index(name="count")
        pivot_mode = mode_counts.pivot(index="job_category", columns="work_mode", values="count").fillna(0)
        
        # Ensure we have Remote / Hybrid columns
        remote_cols = [c for c in ["Remote", "Hybrid"] if c in pivot_mode.columns]
        if remote_cols:
            pivot_mode["remote_hybrid_pct"] = pivot_mode[remote_cols].sum(axis=1) / pivot_mode.sum(axis=1) * 100
            remote_friendliest = pivot_mode["remote_hybrid_pct"].idxmax()
            remote_friendliest_val = pivot_mode["remote_hybrid_pct"].max()
        else:
            remote_friendliest = "N/A"
            remote_friendliest_val = 0.0
    else:
        remote_friendliest = "N/A"
        remote_friendliest_val = 0.0

    # 3. Skill Density (average standardized skills per job)
    if "standardized_skills" in df_known.columns:
        df_known["_skill_count"] = df_known["standardized_skills"].apply(
            lambda x: len(x) if isinstance(x, list) else 0
        )
        density = df_known.groupby("job_category")["_skill_count"].mean()
        max_density_cat = density.idxmax()
        max_density_val = density.max()
    else:
        max_density_cat = "N/A"
        max_density_val = 0.0

    c1, c2, c3 = st.columns(3)
    with c1:
        kpi_card("Highest-Paying Category", highest_paying, "💸", f"Avg Max Salary: {highest_paying_val:.1f} LPA")
    with c2:
        kpi_card("Remote-Friendliest", remote_friendliest, "🌐", f"{remote_friendliest_val:.1f}% Remote/Hybrid")
    with c3:
        kpi_card("Highest Skill Density", max_density_cat, "🔧", f"Avg {max_density_val:.1f} skills/job")

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-header'>📊 Fields & Categories Breakdown</div>", unsafe_allow_html=True)

    # ── Job Fields Hierarchy (Sunburst) ──
    # Check if job_field and job_sub_field exist
    path_cols = []
    if "job_field" in df_known.columns and df_known["job_field"].nunique() > 1:
        path_cols.append("job_field")
    if "job_sub_field" in df_known.columns and df_known["job_sub_field"].nunique() > 1:
        path_cols.append("job_sub_field")
    
    if not path_cols:
        path_cols = ["job_category"]

    # Sunburst requires at least 2 distinct values in the root level to look meaningful
    if df_known[path_cols[0]].nunique() >= 2:
        sun_df = df_known.groupby(path_cols).size().reset_index(name="count")
        fig_sunburst = px.sunburst(
            sun_df,
            path=path_cols,
            values="count",
            color="count",
            color_continuous_scale="RdPu",
            title="Field → Sub-field Category Hierarchy"
        )
        fig_sunburst.update_layout(**PLOTLY_LAYOUT)
        st.plotly_chart(fig_sunburst, width="stretch")
    else:
        st.info("Not enough distinct categories/fields to display Sunburst hierarchy.")

    # ── Salary Ranges by Category (Box Plot) ──
    sal_box_df = df_known[df_known["max_salary"].notna()].copy()
    if len(sal_box_df) >= 30:
        st.markdown("<div class='section-header'>💸 Salary Distribution by Category</div>", unsafe_allow_html=True)
        cat_order = sal_box_df.groupby("job_category")["max_salary"].median().sort_values(ascending=False).index.tolist()
        fig_box = px.box(
            sal_box_df,
            x="job_category",
            y="max_salary",
            category_orders={"job_category": cat_order},
            title="Max Salary Distribution by Job Category (LPA)",
            labels={"job_category": "Job Category", "max_salary": "Max Salary (LPA)"},
            color="job_category",
            color_discrete_sequence=COLORS
        )
        fig_box.update_layout(**PLOTLY_LAYOUT)
        fig_box.update_xaxes(tickangle=-30)
        st.plotly_chart(fig_box, width="stretch")
    else:
        st.info("Not enough salary data (minimum 30 records required) to display Category Box Plot.")

    # ── Category × Work Mode Stacked Bar Chart ──
    st.markdown("<div class='section-header'>🌐 Work Mode Breakdown by Category</div>", unsafe_allow_html=True)
    mode_counts_df = df_known[df_known["work_mode"] != "Unknown"].copy()
    
    if not mode_counts_df.empty:
        mode_counts = mode_counts_df.groupby(["job_category", "work_mode"]).size().reset_index(name="count")
        pivot_mode = mode_counts.pivot(index="job_category", columns="work_mode", values="count").fillna(0)
        pivot_mode_pct = pivot_mode.div(pivot_mode.sum(axis=1), axis=0) * 100
        pivot_mode_pct = pivot_mode_pct.reset_index()
        melted_mode = pivot_mode_pct.melt(id_vars="job_category", value_name="Percentage", var_name="Work Mode")
        
        cat_order = df_known["job_category"].value_counts().index.tolist()
        
        fig_mode = px.bar(
            melted_mode,
            x="Percentage",
            y="job_category",
            color="Work Mode",
            orientation="h",
            barmode="stack",
            category_orders={"job_category": cat_order},
            color_discrete_map=WORK_MODE_COLORS,
            title="Work Mode Distribution within Job Categories (100% Stacked)",
            labels={"Percentage": "Percentage (%)", "job_category": "Job Category"}
        )
        fig_mode.update_layout(**PLOTLY_LAYOUT)
        st.plotly_chart(fig_mode, width="stretch")
    else:
        st.info("No work mode data available.")

    # ── Side-by-Side Category Comparison Tool ──
    st.markdown("<div class='section-header'>⚖️ Side-by-Side Category Comparison</div>", unsafe_allow_html=True)
    categories = sorted(df_known["job_category"].dropna().unique().tolist())
    
    if len(categories) >= 2:
        col_select_a, col_select_b = st.columns(2)
        with col_select_a:
            cat_a = st.selectbox("Compare Category A:", categories, index=0, key="cat_compare_a")
        with col_select_b:
            # Select second item as default if available
            default_b_idx = min(1, len(categories) - 1)
            cat_b = st.selectbox("With Category B:", categories, index=default_b_idx, key="cat_compare_b")

        if cat_a == cat_b:
            st.warning("Please select two different categories to compare.")
        else:
            df_a = df_known[df_known["job_category"] == cat_a]
            df_b = df_known[df_known["job_category"] == cat_b]

            # 1. Comparison KPIs side-by-side
            st.markdown(f"#### Comparison Overview: {cat_a} vs {cat_b}")
            
            jobs_a, jobs_b = len(df_a), len(df_b)
            exp_a = df_a["min_exp"].median()
            exp_b = df_b["min_exp"].median()
            
            sal_a = df_a["max_salary"].median()
            sal_b = df_b["max_salary"].median()
            
            # Remote share
            rem_a = df_a["work_mode"].isin(["Remote", "Hybrid"]).sum() / jobs_a * 100 if jobs_a > 0 else 0
            rem_b = df_b["work_mode"].isin(["Remote", "Hybrid"]).sum() / jobs_b * 100 if jobs_b > 0 else 0
            
            # Cities
            city_a_series = df_a[df_a["city"] != "Unknown"]["city"]
            city_a = city_a_series.mode().iloc[0] if not city_a_series.empty else "N/A"
            
            city_b_series = df_b[df_b["city"] != "Unknown"]["city"]
            city_b = city_b_series.mode().iloc[0] if not city_b_series.empty else "N/A"
            
            # Employers
            emp_a_series = df_a[df_a["company"] != "Unknown"]["company"]
            emp_a = emp_a_series.mode().iloc[0] if not emp_a_series.empty else "N/A"
            
            emp_b_series = df_b[df_b["company"] != "Unknown"]["company"]
            emp_b = emp_b_series.mode().iloc[0] if not emp_b_series.empty else "N/A"

            # Create side-by-side display using cards
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"**Category: {cat_a}**")
                kpi_col1, kpi_col2 = st.columns(2)
                with kpi_col1:
                    kpi_card("Job Volume", f"{jobs_a}", "📊")
                    kpi_card("Median Max Salary", f"{sal_a:.1f} LPA" if pd.notna(sal_a) else "N/A", "💸")
                    kpi_card("Top City Hub", city_a, "📍")
                with kpi_col2:
                    kpi_card("Median Min Exp", f"{exp_a:.1f} yrs" if pd.notna(exp_a) else "N/A", "📅")
                    kpi_card("Remote/Hybrid Share", f"{rem_a:.0f}%", "🌐")
                    kpi_card("Top Employer", emp_a, "🏢")

            with col_b:
                st.markdown(f"**Category: {cat_b}**")
                kpi_col1, kpi_col2 = st.columns(2)
                with kpi_col1:
                    kpi_card("Job Volume", f"{jobs_b}", "📊")
                    kpi_card("Median Max Salary", f"{sal_b:.1f} LPA" if pd.notna(sal_b) else "N/A", "💸")
                    kpi_card("Top City Hub", city_b, "📍")
                with kpi_col2:
                    kpi_card("Median Min Exp", f"{exp_b:.1f} yrs" if pd.notna(exp_b) else "N/A", "📅")
                    kpi_card("Remote/Hybrid Share", f"{rem_b:.0f}%", "🌐")
                    kpi_card("Top Employer", emp_b, "🏢")

            # 2. Skills comparison grouped bar
            skills_a = skill_counter(df_a, 5)
            skills_b = skill_counter(df_b, 5)
            
            if skills_a or skills_b:
                dict_a = {s: count for s, count in skills_a}
                dict_b = {s: count for s, count in skills_b}
                all_skills = list(set(dict_a.keys()) | set(dict_b.keys()))
                
                comp_skills_list = []
                for s in all_skills:
                    comp_skills_list.append({
                        "Skill": s,
                        f"{cat_a}": dict_a.get(s, 0) / jobs_a * 100 if jobs_a > 0 else 0,
                        f"{cat_b}": dict_b.get(s, 0) / jobs_b * 100 if jobs_b > 0 else 0
                    })
                comp_skills_df = pd.DataFrame(comp_skills_list)
                comp_skills_melted = comp_skills_df.melt(id_vars="Skill", value_name="Share (%)", var_name="Category")
                
                fig_comp_skills = px.bar(
                    comp_skills_melted,
                    x="Share (%)",
                    y="Skill",
                    color="Category",
                    barmode="group",
                    orientation="h",
                    title="Top Skills Demand Comparison (% Share of Jobs)",
                    color_discrete_sequence=["#6366f1", "#06b6d4"]
                )
                fig_comp_skills.update_layout(**PLOTLY_LAYOUT)
                st.plotly_chart(fig_comp_skills, width="stretch")
    else:
        st.info("Not enough distinct categories available to run side-by-side comparison.")
