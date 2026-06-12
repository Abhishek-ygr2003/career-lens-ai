"""
CareerLens AI — analysis/market_overview.py
============================================
Market Overview tab: KPIs + high-level distribution charts.

Fixes applied (v2):
  Bugs:
    1. width="stretch"  (was invalid width='stretch')
    2. kpi_card receives str safely for non-numeric KPIs
    3. Per-chart empty-state guards (source / work_mode may be all-Unknown)
    4. Work-mode palette cycles COLORS instead of hardcoded 3-item list

  Performance:
    5. All value_counts() computed once at the top, not inline per chart
    6. Removed unused skill_counter import

  UI:
    7. Section divider + label between KPI row and charts
    8. City bar uses brand gradient colour scale instead of Viridis
    9. Work mode switched from donut → horizontal bar (avoids duplicate pie style)
   10. Chart subtitles show live counts (e.g. "14 categories · 1 248 jobs")
   11. Consistent chart height (360px) and margin via PLOTLY_LAYOUT extension
   12. Top-city and top-category KPI cards show count as sub-label
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from analysis.helpers import COLORS, PLOTLY_LAYOUT, EXP_BAND_ORDER, kpi_card


# ── Chart height shared across all visuals in this tab ───────
_H = 360


def _chart_layout(**overrides) -> dict:
    """Merge PLOTLY_LAYOUT with tab-specific defaults."""
    base = {**PLOTLY_LAYOUT, "height": _H, "margin": {"t": 48, "b": 32, "l": 16, "r": 16}}
    base.update(overrides)
    return base


def render_market_overview(df: pd.DataFrame) -> None:
    """Market Overview — KPIs and high-level distribution charts."""

    total = len(df)
    if total == 0:
        st.info("No jobs match your current filters.")
        return

    # ── Pre-compute aggregates once  (Fix 5) ─────────────────
    unique_companies = df["company"].nunique()

    city_series  = df[df["city"] != "Unknown"]["city"]
    top_city_val = city_series.mode().iloc[0] if not city_series.empty else "N/A"
    top_city_n   = int((city_series == top_city_val).sum()) if top_city_val != "N/A" else 0

    # Use job_field for top-level grouping if available, else job_category
    cat_col = "job_field" if "job_field" in df.columns and df["job_field"].nunique() > 1 else "job_category"
    top_cat_val  = df[cat_col].mode().iloc[0] if not df[cat_col].empty else "N/A"
    top_cat_n    = int((df[cat_col] == top_cat_val).sum()) if top_cat_val != "N/A" else 0

    cat_counts  = df[cat_col].value_counts().reset_index()
    cat_counts.columns = ["Category", "Count"]

    src_counts  = df["source"].value_counts().reset_index()
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
        # Fix 2: pass string safely; show how many jobs in that city
        kpi_card("Top City", top_city_val, "📍", sub=f"{top_city_n:,} jobs")
    with c4:
        kpi_card("Top Category", top_cat_val, "🏷️", sub=f"{top_cat_n:,} jobs")

    # ── Section divider  (Fix 7) ──────────────────────────────
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-header'>📊 Distribution Overview</div>",
        unsafe_allow_html=True,
    )

    # ── Row 1: Category bar · Source donut ────────────────────
    col1, col2 = st.columns(2)

    with col1:
        if cat_counts.empty:
            st.info("No category data available.")
        else:
            n_cats = len(cat_counts)
            fig = px.bar(
                cat_counts,
                x="Count", y="Category",
                orientation="h",
                color="Category",
                color_discrete_sequence=COLORS,
                title=f"Jobs by Category  <sup style='font-size:11px;color:#64748b'>"
                      f"{n_cats} categories · {total:,} jobs</sup>",
            )
            fig.update_layout(**_chart_layout(showlegend=False))
            fig.update_traces(
                texttemplate="%{x:,}",
                textposition="outside",
                textfont_size=11,
                cliponaxis=False,
            )
            # Fix 1: width="stretch"
            st.plotly_chart(fig, width="stretch")

    with col2:
        # Fix 3: guard against empty source data
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

    # ── Row 2: City bar · Work-mode bar ───────────────────────
    col3, col4 = st.columns(2)

    with col3:
        if city_counts.empty:
            st.info("No city data available.")
        else:
            # Fix 8: brand-aligned sequential palette instead of Viridis
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

    with col4:
        # Fix 3: guard against empty / all-Unknown work mode
        mode_known = mode_counts[mode_counts["Work Mode"] != "Unknown"]
        if mode_known.empty:
            st.info("No work-mode data available.")
        else:
            # Fix 9: horizontal bar instead of second donut — more readable,
            #        avoids visual monotony with the Source donut above
            # Fix 4: COLORS cycles dynamically, not a hardcoded 3-item list
            fig = px.bar(
                mode_known.sort_values("Count"),
                x="Count", y="Work Mode",
                orientation="h",
                color="Work Mode",
                color_discrete_sequence=COLORS,
                title=f"Work Mode Distribution  <sup style='font-size:11px;"
                      f"color:#64748b'>{len(mode_known)} modes</sup>",
            )
            fig.update_layout(**_chart_layout(showlegend=False))
            fig.update_traces(
                texttemplate="%{x:,}",
                textposition="outside",
                textfont_size=11,
                cliponaxis=False,
            )
            st.plotly_chart(fig, width="stretch")
