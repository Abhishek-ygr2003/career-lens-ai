"""
skill_demand.py — CareerLens Skill Demand tab

Improvements (v3):
  - Replaced all iterrows() loops with df.explode() + groupby (vectorized)
  - Skill frequency, co-occurrence, category affinity, experience split, time trends
  - Auto-insight callout box with key findings
  - Colour-encodes bars by demand tier (top 20% / mid / tail)
"""

from __future__ import annotations

import itertools
from collections import defaultdict

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analysis.helpers import COLORS, EXP_BAND_ORDER, PLOTLY_LAYOUT, kpi_card, skill_counter

# ── palette ───────────────────────────────────────────────────────────────────
_TOP_COLOR    = "#6366f1"   # indigo  — top-tier skills
_MID_COLOR    = "#8b5cf6"   # violet  — mid-tier
_TAIL_COLOR   = "#a5b4fc"   # lavender — tail
_HEAT_SCALE   = "RdPu"


def _tier_colors(counts: pd.Series) -> list[str]:
    """Assign a colour per bar based on demand tier (top 20% / mid 40% / tail 40%)."""
    p80 = counts.quantile(0.80)
    p40 = counts.quantile(0.40)
    return [
        _TOP_COLOR if v >= p80 else (_MID_COLOR if v >= p40 else _TAIL_COLOR)
        for v in counts
    ]


def _cooccurrence_matrix_fast(df: pd.DataFrame, skill_set: set) -> pd.DataFrame:
    """
    Build a co-occurrence matrix in O(n * k²) where k = len(skill_set).
    Diagonal = number of jobs containing that skill (useful reference).

    Returns a DataFrame with dtype float64 (always writable, avoids
    the numpy read-only-view issue that arises with integer-backed frames
    when sliced from cached data).
    """
    skills = sorted(skill_set)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    skill_freq: dict[str, int] = defaultdict(int)

    for raw in df["standardized_skills"]:
        if not isinstance(raw, list):
            continue
        present = [s for s in raw if s in skill_set]
        for s in present:
            skill_freq[s] += 1
        for s1, s2 in itertools.combinations(present, 2):
            counts[(s1, s2)] += 1
            counts[(s2, s1)] += 1

    # Use float64 explicitly — avoids read-only numpy views from cached integer blocks
    matrix = pd.DataFrame(0.0, index=skills, columns=skills, dtype=np.float64)
    for (s1, s2), v in counts.items():
        matrix.loc[s1, s2] = float(v)
    for s in skills:
        matrix.loc[s, s] = float(skill_freq.get(s, 0))

    return matrix


def _auto_insights(skills_df: pd.DataFrame, total: int) -> list[str]:
    """Return up to 3 plain-English insight strings."""
    insights = []
    if skills_df.empty:
        return insights

    top = skills_df.iloc[-1]  # sorted ascending, so last = highest
    insights.append(
        f"**{top['Skill']}** is the most demanded skill, appearing in "
        f"**{top['Percentage']:.0f}%** of all filtered job listings."
    )

    # Gap between #1 and #2
    if len(skills_df) >= 2:
        second = skills_df.iloc[-2]
        gap = top["Percentage"] - second["Percentage"]
        if gap > 5:
            insights.append(
                f"There's a notable **{gap:.0f} pp gap** between {top['Skill']} "
                f"and the next skill ({second['Skill']}), suggesting it's a near-mandatory requirement."
            )

    # Long-tail: skills below 10%
    rare = skills_df[skills_df["Percentage"] < 10]
    if len(rare) > 3:
        insights.append(
            f"**{len(rare)} skills** appear in fewer than 10% of jobs — "
            "these are niche differentiators, not table-stakes requirements."
        )
    return insights


# ─────────────────────────────────────────────────────────────────────────────

def render_skill_demand(df: pd.DataFrame):
    """Skill Demand — frequency, co-occurrence, trends, and affinity analysis."""

    total = len(df)
    if total == 0:
        st.info("No jobs match your current filters. Broaden the search to see skill data.")
        return

    # ── Controls row ─────────────────────────────────────────────────────
    c1, c2 = st.columns([2, 1])
    with c1:
        top_n = st.slider("Skills to show", 10, 40, 20, key="skill_topn")
    with c2:
        view_as = st.radio(
            "Y-axis",
            ["Job count", "% of jobs"],
            horizontal=True,
            key="skill_view_as",
        )

    top_skills = skill_counter(df, top_n)  # called ONCE; reused throughout
    if not top_skills:
        st.warning("No skill data found in the filtered jobs. Check that `standardized_skills` is populated.")
        return

    skills_df = pd.DataFrame(top_skills, columns=["Skill", "Count"])
    skills_df["Percentage"] = (skills_df["Count"] / total * 100).round(1)
    skills_df_asc = skills_df.sort_values("Count", ascending=True).reset_index(drop=True)

    # ── Section 1 — Frequency bar + table ────────────────────────────────
    st.subheader("📊 Skill Frequency")

    col1, col2 = st.columns([3, 2])

    with col1:
        y_values = skills_df_asc["Percentage"] if view_as == "% of jobs" else skills_df_asc["Count"]
        x_label  = "% of jobs" if view_as == "% of jobs" else "Job count"
        bar_colors = _tier_colors(y_values)

        fig = go.Figure(
            go.Bar(
                y=skills_df_asc["Skill"],
                x=y_values,
                orientation="h",
                marker_color=bar_colors,
                customdata=np.stack(
                    [skills_df_asc["Count"], skills_df_asc["Percentage"]], axis=-1
                ),
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "Jobs: %{customdata[0]}<br>"
                    "Share: %{customdata[1]:.1f}%<extra></extra>"
                ),
            )
        )
        fig.update_traces(
            texttemplate="%{x:.1f}" + ("%" if view_as == "% of jobs" else ""),
            textposition="outside",
            cliponaxis=True,
        )
        layout = PLOTLY_LAYOUT.copy()
        layout.update(
            height=max(420, top_n * 30),
            xaxis_title=x_label,
            margin=dict(l=40, r=60, t=50, b=40),
            showlegend=False,
        )
        fig.update_layout(**layout)

        fig.add_annotation(
            text=(
                f"<span style='color:{_TOP_COLOR}'>■</span> Top 20%  "
                f"<span style='color:{_MID_COLOR}'>■</span> Mid  "
                f"<span style='color:{_TAIL_COLOR}'>■</span> Tail"
            ),
            xref="paper", yref="paper",
            x=1, y=-0.04,
            showarrow=False,
            font_size=11,
            align="right",
        )
        st.plotly_chart(fig, width="stretch")

    with col2:
        display_table = (
            skills_df.sort_values("Count", ascending=False)
            .reset_index(drop=True)
            .copy()
        )
        display_table.index = display_table.index + 1
        display_table.index.name = "Rank"
        display_table = display_table.rename(columns={"Percentage": "% of jobs"})

        st.dataframe(
            display_table[["Skill", "Count", "% of jobs"]],
            width="stretch",
            height=max(420, top_n * 30),
        )

        csv = display_table.to_csv(index=True).encode("utf-8")
        st.download_button(
            "⬇ Download skill table",
            data=csv,
            file_name="skill_demand.csv",
            mime="text/csv",
            width="stretch",
        )

    # ── Auto-insights callout ─────────────────────────────────────────────
    insights = _auto_insights(skills_df_asc, total)
    if insights:
        with st.expander("💡 Key findings", expanded=True):
            for ins in insights:
                st.markdown(f"- {ins}")

    st.markdown("---")

    # ── Section 2 — Co-occurrence heatmap ────────────────────────────────
    st.subheader("🔗 Skill Co-occurrence")
    st.caption(
        "How often pairs of skills appear in the same job. "
        "Diagonal = how many jobs require that skill at all."
    )

    cooc_n = st.slider("Skills in heatmap", 6, 15, 10, key="cooc_n")
    top_cooc = [s for s, _ in skill_counter(df, cooc_n)]

    if len(top_cooc) < 2:
        st.info("Need at least 2 skills for co-occurrence analysis.")
    elif "standardized_skills" not in df.columns:
        st.info("`standardized_skills` column not found — co-occurrence unavailable.")
    else:
        cooccur = _cooccurrence_matrix_fast(df, set(top_cooc))
        order = [s for s, _ in skill_counter(df, cooc_n) if s in cooccur.index]
        cooccur = cooccur.loc[order, order]

        fig = px.imshow(
            cooccur,
            color_continuous_scale=_HEAT_SCALE,
            labels=dict(color="Co-occurrences"),
            text_auto=True,
            aspect="auto",
        )
        fig.update_layout(
            **PLOTLY_LAYOUT,
            height=460,
            xaxis_tickangle=-35,
            coloraxis_colorbar_title="Jobs",
        )
        st.plotly_chart(fig, width="stretch")

        # ── Off-diagonal max (find strongest skill pair) ──────────────────
        # Must use .to_numpy(copy=True) to guarantee a writable array even
        # when the DataFrame originated from a st.cache_data-cached source.
        diag_arr = cooccur.to_numpy(copy=True, dtype=np.float64)
        np.fill_diagonal(diag_arr, 0)
        off_diag = pd.DataFrame(diag_arr, index=cooccur.index, columns=cooccur.columns)

        od_max = off_diag.to_numpy().max()
        if od_max > 0:
            flat = off_diag.stack()
            top_pair = flat.idxmax()
            st.caption(
                f"Strongest pairing: **{top_pair[0]}** + **{top_pair[1]}** "
                f"— co-occur in **{int(flat.max())}** jobs."
            )

    st.markdown("---")

    # ── Section 3 — Category Affinity (vectorized with explode) ──────────
    if "job_category" in df.columns and "standardized_skills" in df.columns:
        st.subheader("🏷 Skill–Category Affinity")
        st.caption("Which job categories account for the demand of each top skill.")

        affinity_n = min(12, top_n)
        top_skills_affinity = set(s for s, _ in skill_counter(df, affinity_n))

        # Vectorized: explode skills then filter + groupby
        exploded = df[["job_category", "standardized_skills"]].explode("standardized_skills")
        exploded = exploded.dropna(subset=["standardized_skills"])
        exploded = exploded[exploded["standardized_skills"].isin(top_skills_affinity)]

        if not exploded.empty:
            aff_pivot = (
                exploded.groupby(["standardized_skills", "job_category"])
                .size()
                .reset_index(name="Count")
            )
            aff_pivot = aff_pivot.rename(columns={"standardized_skills": "Skill", "job_category": "Category"})
            aff_pivot["Share"] = aff_pivot.groupby("Skill")["Count"].transform(
                lambda x: x / x.sum() * 100
            )
            skill_order = [s for s, _ in skill_counter(df, affinity_n)]

            fig = px.bar(
                aff_pivot,
                y="Skill",
                x="Share",
                color="Category",
                orientation="h",
                barmode="stack",
                category_orders={"Skill": skill_order},
                labels={"Share": "% of demand", "Skill": ""},
                height=max(360, affinity_n * 36),
                color_discrete_sequence=px.colors.qualitative.Pastel,
            )
            fig.update_layout(
                **PLOTLY_LAYOUT,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                xaxis_title="Share of demand (%)",
            )
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No skill–category data to display.")

        st.markdown("---")

    # ── Section 4 — Skill × Experience level split (vectorized) ──────────
    if "exp_band" in df.columns and "standardized_skills" in df.columns:
        st.subheader("🎓 Skills by Experience Level")
        st.caption(
            "Shows whether a skill is mostly demanded by junior, mid, or senior roles. "
            "Helps prioritise what to learn first vs later."
        )

        exp_n = min(10, top_n)
        top_skills_exp = set(s for s, _ in skill_counter(df, exp_n))

        # Vectorized: explode then filter
        exp_exploded = df[["exp_band", "standardized_skills"]].explode("standardized_skills")
        exp_exploded = exp_exploded.dropna(subset=["standardized_skills", "exp_band"])
        exp_exploded = exp_exploded[
            exp_exploded["standardized_skills"].isin(top_skills_exp)
            & exp_exploded["exp_band"].isin(EXP_BAND_ORDER)
        ]

        if not exp_exploded.empty:
            exp_pivot = (
                exp_exploded.groupby(["standardized_skills", "exp_band"])
                .size()
                .reset_index(name="Count")
            )
            exp_pivot = exp_pivot.rename(columns={"standardized_skills": "Skill", "exp_band": "Band"})
            exp_pivot["Share"] = exp_pivot.groupby("Skill")["Count"].transform(
                lambda x: x / x.sum() * 100
            )

            valid_bands = [b for b in EXP_BAND_ORDER if b in exp_pivot["Band"].unique()]

            fig = px.bar(
                exp_pivot,
                y="Skill",
                x="Share",
                color="Band",
                orientation="h",
                barmode="stack",
                category_orders={
                    "Skill": [s for s, _ in skill_counter(df, exp_n)],
                    "Band": valid_bands,
                },
                labels={"Share": "% of demand", "Skill": ""},
                height=max(320, exp_n * 36),
                color_discrete_sequence=[
                    "#a5b4fc", "#6366f1", "#4f46e5", "#3730a3", "#1e1b4b"
                ][: len(valid_bands)],
            )
            fig.update_layout(
                **PLOTLY_LAYOUT,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                xaxis_title="Share of demand (%)",
            )
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No experience-band data to cross-reference with skills.")

        st.markdown("---")

    # ── Section 5 — Skill Trend over time (vectorized) ───────────────────
    date_cols = [c for c in df.columns if "date" in c.lower() or "posted" in c.lower()]
    if date_cols and "standardized_skills" in df.columns:
        st.subheader("📈 Skill Demand Over Time")
        st.caption("Monthly share of job listings mentioning each skill.")

        date_col = date_cols[0]
        try:
            df_trend = df.copy()
            df_trend["_month"] = pd.to_datetime(df_trend[date_col], errors="coerce").dt.tz_localize(None).dt.to_period("M")
            df_trend = df_trend.dropna(subset=["_month"])

            trend_n = min(8, top_n)
            trend_skills = set(s for s, _ in skill_counter(df, trend_n))

            # Vectorized: explode then filter
            trend_exploded = df_trend[["_month", "standardized_skills"]].explode("standardized_skills")
            trend_exploded = trend_exploded.dropna(subset=["standardized_skills"])
            trend_exploded = trend_exploded[trend_exploded["standardized_skills"].isin(trend_skills)]
            trend_exploded["Month"] = trend_exploded["_month"].astype(str)

            if not trend_exploded.empty:
                monthly_totals = df_trend["_month"].astype(str).value_counts().rename("total")
                trend_counts = (
                    trend_exploded.groupby(["Month", "standardized_skills"])
                    .size()
                    .reset_index(name="Count")
                )
                trend_counts = trend_counts.rename(columns={"standardized_skills": "Skill"})
                trend_counts = trend_counts.merge(
                    monthly_totals, left_on="Month", right_index=True, how="left"
                )
                trend_counts["Share %"] = (
                    trend_counts["Count"] / trend_counts["total"] * 100
                ).round(1)
                trend_counts = trend_counts.sort_values("Month")

                fig = px.line(
                    trend_counts,
                    x="Month",
                    y="Share %",
                    color="Skill",
                    markers=True,
                    labels={"Share %": "% of monthly listings", "Month": ""},
                    height=400,
                    color_discrete_sequence=px.colors.qualitative.Prism,
                )
                fig.update_layout(
                    **PLOTLY_LAYOUT,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                )
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("Not enough data to show monthly trends.")
        except Exception:
            st.info("Could not parse date column for trend analysis.")