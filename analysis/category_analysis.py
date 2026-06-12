import streamlit as st
import pandas as pd
import plotly.express as px
from analysis.helpers import PLOTLY_LAYOUT

def render_category_analysis(df: pd.DataFrame):
    st.markdown("### 📂 Category Analysis")
    if df.empty:
        st.info("No data available.")
        return

    # ── Two-level category view ──────────────────────────────
    has_field = "job_field" in df.columns and df["job_field"].nunique() > 1

    if has_field:
        view_level = st.radio(
            "Group by",
            ["Field (top-level)", "Sub-field", "Legacy category"],
            horizontal=True,
            key="cat_view_level",
        )
        if view_level == "Field (top-level)":
            cat_col = "job_field"
        elif view_level == "Sub-field":
            cat_col = "job_sub_field" if "job_sub_field" in df.columns else "job_category"
        else:
            cat_col = "job_category"
            
        sort_order = st.radio("Sort categories", ["Count", "Alphabetical"], horizontal=True, key="cat_sort")
    else:
        cat_col = "job_category"
        sort_order = "Count"

    cat_counts = df[cat_col].value_counts().reset_index()
    cat_counts.columns = ['Category', 'Count']
    
    if sort_order == "Alphabetical":
        cat_counts = cat_counts.sort_values('Category')

    fig = px.treemap(
        cat_counts,
        path=['Category'],
        values='Count',
        color='Count',
        color_continuous_scale='Blues',
        title=f"Job Distribution by {cat_col.replace('_', ' ').title()}"
    )
    fig.update_layout(**PLOTLY_LAYOUT, height=500)
    st.plotly_chart(fig, width="stretch")

    # ── Field → Sub-field breakdown (if two-level data exists) ──
    if has_field and "job_sub_field" in df.columns:
        st.markdown("---")
        st.markdown("#### Field → Sub-field Breakdown")
        breakdown = (
            df.groupby(["job_field", "job_sub_field"])
            .size()
            .reset_index(name="Count")
            .sort_values("Count", ascending=False)
        )
        if not breakdown.empty:
            fig2 = px.sunburst(
                breakdown,
                path=["job_field", "job_sub_field"],
                values="Count",
                color="Count",
                color_continuous_scale="Blues",
                title="Field → Sub-field Hierarchy",
            )
            fig2.update_layout(**PLOTLY_LAYOUT, height=500)
            st.plotly_chart(fig2, width="stretch")
