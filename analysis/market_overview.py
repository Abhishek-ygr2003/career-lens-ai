"""
CareerLens AI — analysis/market_overview.py
============================================
Market Overview tab: KPIs + high-level distribution charts.

v3 improvements:
  - "Other" category is separated from the main chart to avoid skewing visuals
  - New sub-field distribution chart for finer-grained category breakdown
  - Callout explains what "Other" means when it's large
  - Top-category KPI excludes "Other" to show the real leading category
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analysis.helpers import COLORS, PLOTLY_LAYOUT, EXP_BAND_ORDER, kpi_card


_H = 360


def _chart_layout(**overrides) -> dict:
    base = {**PLOTLY_LAYOUT, "height": _H, "margin": {"t": 48, "b": 32, "l": 16, "r": 16}}
    base.update(overrides)
    return base


def _bar_with_counts(df, x_col, y_col, title, height=None, color_seq=None, top_n=None):
    """Reusable horizontal bar chart with count labels."""
    if top_n:
        df = df.head(top_n)
    fig = px.bar(
        df, x=x_col, y=y_col,
        orientation="h",
        color=y_col,
        color_discrete_sequence=color_seq or COLORS,
        title=title,
    )
    layout_kw = _chart_layout(showlegend=False)
    if height:
        layout_kw["height"] = height
    fig.update_layout(**layout_kw)
    fig.update_traces(
        texttemplate="%{x:,}",
        textposition="outside",
        textfont_size=11,
        cliponaxis=False,
    )
    return fig


def render_market_overview(df: pd.DataFrame) -> None:
    """Market Overview — KPIs and high-level distribution charts."""

    total = len(df)
    if total == 0:
        st.info("No jobs match your current filters.")
        return

    # ── Pre-compute aggregates ────────────────────────────────
    unique_companies = df["company"].nunique()

    city_series = df[df["city"] != "Unknown"]["city"]
    top_city_val = city_series.mode().iloc[0] if not city_series.empty else "N/A"
    top_city_n = int((city_series == top_city_val).sum()) if top_city_val != "N/A" else 0

    cat_col = "job_field" if "job_field" in df.columns and df["job_field"].nunique() > 1 else "job_category"

    # For the KPI, skip "Other" to show the real leading category
    cat_no_other = df[df[cat_col] != "Other"]
    if not cat_no_other.empty:
        top_cat_val = cat_no_other[cat_col].mode().iloc[0]
        top_cat_n = int((cat_no_other[cat_col] == top_cat_val).sum())
    else:
        top_cat_val = "N/A"
        top_cat_n = 0

    # Category counts — split known vs Other
    cat_all_counts = df[cat_col].value_counts().reset_index()
    cat_all_counts.columns = ["Category", "Count"]
    cat_known = cat_all_counts[cat_all_counts["Category"] != "Other"]
    cat_other = cat_all_counts[cat_all_counts["Category"] == "Other"]
    other_count = int(cat_other["Count"].sum()) if not cat_other.empty else 0
    other_pct = (other_count / total * 100) if total > 0 else 0

    # Sub-field counts (excluding Other)
    sub_col = "job_sub_field"
    if sub_col in df.columns:
        sub_known = df[df[sub_col] != "Other"][sub_col].value_counts().reset_index()
        sub_known.columns = ["Sub-Field", "Count"]
    else:
        sub_known = pd.DataFrame(columns=["Sub-Field", "Count"])

    src_counts = df["source"].value_counts().reset_index()
    src_counts.columns = ["Source", "Count"]

    city_counts = (
        df[df["city"] != "Unknown"]["city"]
        .value_counts()
        .head(10)
        .reset_index()
    )
    city_counts.columns = ["City", "Count"]

    mode_counts = df["work_mode"].value_counts().reset_index()
    mode_counts.columns = ["Work Mode", "Count"]

    # ── KPI row ───────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Total Jobs", f"{total:,}", "📊")
    with c2:
        kpi_card("Companies", f"{unique_companies:,}", "🏢")
    with c3:
        kpi_card("Top City", top_city_val, "📍", sub=f"{top_city_n:,} jobs")
    with c4:
        kpi_card("Top Category", top_cat_val, "🏷️", sub=f"{top_cat_n:,} jobs")

    # ── Section divider ───────────────────────────────────────
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-header'>📊 Distribution Overview</div>",
        unsafe_allow_html=True,
    )

    # ── Row 1: Category bar · Source donut ────────────────────
    col1, col2 = st.columns(2)

    with col1:
        if cat_known.empty:
            st.info("No category data available.")
        else:
            n_cats = len(cat_known)
            fig = _bar_with_counts(
                cat_known.sort_values("Count"),
                "Count", "Category",
                title=f"Jobs by Category  <sup style='font-size:11px;color:#64748b'>"
                      f"{n_cats} categories · {total - other_count:,} classified jobs</sup>",
            )
            st.plotly_chart(fig, width="stretch")

    with col2:
        src_known = src_counts[src_counts["Source"] != "Unknown"]
        if src_known.empty:
            st.info("No source data available.")
        else:
            fig = px.pie(
                src_known,
                values="Count",
                names="Source",
                title=f"Jobs by Source  <sup style='font-size:11px;color:#64748b'>"
                      f"{len(src_known)} sources</sup>",
                color_discrete_sequence=COLORS,
                hole=0.48,
            )
            fig.update_layout(**_chart_layout())
            fig.update_traces(
                textinfo="label+percent",
                textfont_size=12,
                pull=[0.03] * len(src_known),
            )
            st.plotly_chart(fig, width="stretch")

    # ── "Other" callout (if significant) ──────────────────────
    if other_pct >= 5:
        st.info(
            f"ℹ️ **\"Other\" category ({other_count:,} jobs · {other_pct:.0f}%):** "
            f"These jobs didn't match any classification keyword in the title or description. "
            f"This usually means the job title is too generic (e.g. \"Executive Assistant\", \"Office Boy\") "
            f"or belongs to a field not yet covered by the classifier (e.g. legal, education, logistics). "
            f"Run the pipeline again after updating `cleaner.py` to re-classify these."
        )

    # ── Row 2: Sub-field bar · City bar ──────────────────────
    col3, col4 = st.columns(2)

    with col3:
        if sub_known.empty:
            st.info("No sub-field data available.")
        else:
            fig = _bar_with_counts(
                sub_known.sort_values("Count"),
                "Count", "Sub-Field",
                title=f"Jobs by Sub-Field  <sup style='font-size:11px;color:#64748b'>"
                      f"top specializations</sup>",
                top_n=12,
            )
            st.plotly_chart(fig, width="stretch")

    with col4:
        if city_counts.empty:
            st.info("No city data available.")
        else:
            fig = px.bar(
                city_counts,
                x="City", y="Count",
                title=f"Top {len(city_counts)} Cities  <sup style='font-size:11px;"
                      f"color:#64748b'>by job count</sup>",
                color="Count",
                color_continuous_scale=["#1e3a5f", "#6366f1", "#06b6d4"],
            )
            fig.update_layout(
                **_chart_layout(coloraxis_showscale=False),
                xaxis_tickangle=-35,
            )
            fig.update_traces(
                texttemplate="%{y:,}",
                textposition="outside",
                textfont_size=10,
                cliponaxis=False,
            )
            st.plotly_chart(fig, width="stretch")

    # ── Row 3: Work-mode bar ─────────────────────────────────
    mode_known = mode_counts[mode_counts["Work Mode"] != "Unknown"]
    if not mode_known.empty:
        fig = _bar_with_counts(
            mode_known.sort_values("Count"),
            "Count", "Work Mode",
            title=f"Work Mode Distribution  <sup style='font-size:11px;"
                  f"color:#64748b'>{len(mode_known)} modes</sup>",
        )
        st.plotly_chart(fig, width="stretch")
