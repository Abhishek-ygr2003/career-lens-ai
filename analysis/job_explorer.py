import streamlit as st
import pandas as pd
import math
import re
from analysis.helpers import skill_counter

def render_job_explorer(df: pd.DataFrame) -> None:
    st.markdown("### 🔎 Job Explorer")
    if df.empty:
        st.info("No data available.")
        return

    # Initialize pagination page in session state
    if "jx_page" not in st.session_state:
        st.session_state["jx_page"] = 1

    # ── Section 1: Declare Filters First (CRITICAL for Streamlit correctness) ──
    col_f1, col_f2 = st.columns(2)
    
    with col_f1:
        query = st.text_input(
            "Search within results (title, company, description):",
            key="jx_search",
            placeholder="e.g. Senior Data Scientist"
        )
        
        # Populate Category Filter
        cats_list = sorted(df["job_category"].dropna().unique().tolist())
        selected_cats = st.multiselect(
            "Filter by Job Category:",
            cats_list,
            key="jx_categories",
            placeholder="All Categories"
        )
        
        # Populate City Filter
        cities_list = sorted(df["city"].dropna().unique().tolist())
        selected_cities = st.multiselect(
            "Filter by City:",
            cities_list,
            key="jx_cities",
            placeholder="All Cities"
        )

    with col_f2:
        # Populate Work Mode Filter
        modes_list = sorted(df["work_mode"].dropna().unique().tolist())
        selected_modes = st.multiselect(
            "Filter by Work Mode:",
            modes_list,
            key="jx_work_modes",
            placeholder="All Work Modes"
        )
        
        # Populate Skills Filter
        all_skills = []
        for s_list in df["standardized_skills"].dropna():
            if isinstance(s_list, list):
                all_skills.extend(s_list)
        unique_skills = sorted(list(set(all_skills)))
        
        selected_skills = st.multiselect(
            "Filter by Required Skills:",
            unique_skills,
            key="jx_skills",
            placeholder="All Skills"
        )
        
        salary_only = st.checkbox(
            "Only show postings with salary disclosed",
            key="jx_salary_only"
        )
        
        # Sort Options (check column existence)
        sort_opts = {}
        if "posted_at" in df.columns:
            sort_opts["Newest Posted"] = ("posted_at", False)
        if "min_exp" in df.columns:
            sort_opts["Experience (Low to High)"] = ("min_exp", True)
            sort_opts["Experience (High to Low)"] = ("min_exp", False)
        if "max_salary" in df.columns:
            sort_opts["Salary (High to Low)"] = ("max_salary", False)
            
        sort_choice = st.selectbox(
            "Sort Order:",
            options=list(sort_opts.keys()),
            key="jx_sort"
        )

    # ── Section 2: Reset Pagination on Filter Change ──
    current_filters = (query, tuple(selected_cats), tuple(selected_cities), tuple(selected_modes), tuple(selected_skills), salary_only, sort_choice)
    if "jx_prev_filters" not in st.session_state or st.session_state["jx_prev_filters"] != current_filters:
        st.session_state["jx_page"] = 1
        st.session_state["jx_prev_filters"] = current_filters

    # ── Section 3: Apply Filters Sequentially ──
    filtered_df = df.copy()
    
    # 1. Search Query
    if query:
        query_lower = query.lower()
        mask = (
            filtered_df["title"].str.lower().str.contains(query_lower, na=False)
            | filtered_df["company"].str.lower().str.contains(query_lower, na=False)
        )
        if "description" in filtered_df.columns:
            mask |= filtered_df["description"].str.lower().str.contains(query_lower, na=False)
        filtered_df = filtered_df[mask]

    # 2. Category Filter
    if selected_cats:
        filtered_df = filtered_df[filtered_df["job_category"].isin(selected_cats)]

    # 3. City Filter
    if selected_cities:
        filtered_df = filtered_df[filtered_df["city"].isin(selected_cities)]

    # 4. Work Mode Filter
    if selected_modes:
        filtered_df = filtered_df[filtered_df["work_mode"].isin(selected_modes)]

    # 5. Skills Filter
    if selected_skills:
        def _has_all_skills(skill_list):
            if not isinstance(skill_list, list):
                return False
            return all(s in skill_list for s in selected_skills)
        filtered_df = filtered_df[
            filtered_df["standardized_skills"].apply(_has_all_skills)
        ]

    # 6. Salary Filter
    if salary_only:
        filtered_df = filtered_df[filtered_df["min_salary"].notna() | filtered_df["max_salary"].notna()]

    # 7. Sorting
    if sort_choice in sort_opts:
        sort_col, sort_asc = sort_opts[sort_choice]
        filtered_df = filtered_df.sort_values(sort_col, ascending=sort_asc)

    # ── Section 4: Render View Toggles ──
    col_t1, col_t2 = st.columns([4, 1])
    with col_t2:
        view = st.radio("View as", ["Cards", "Table"], horizontal=True, key="jx_view")
    
    if filtered_df.empty:
        st.info("No job postings match the filter criteria.")
        return

    # ── Section 5: Table View ──
    if view == "Table":
        all_cols = ["title", "company", "city", "work_mode", "exp_band", "min_salary", "max_salary", "job_url"]
        visible_cols = [c for c in all_cols if c in filtered_df.columns]
        
        st.markdown(f"**Displaying {len(filtered_df):,} job listings:**")
        url_col = "job_url" if "job_url" in filtered_df.columns else ("url" if "url" in filtered_df.columns else None)
        
        if url_col:
            st.dataframe(
                filtered_df[visible_cols],
                column_config={
                    url_col: st.column_config.LinkColumn("Job Link")
                },
                width="stretch",
                height=600
            )
        else:
            st.dataframe(filtered_df[visible_cols], width="stretch", height=600)
        return

    # ── Section 6: Cards View with Pagination ──
    PAGE_SIZE = 12
    total_pages = max(1, math.ceil(len(filtered_df) / PAGE_SIZE))
    page = st.session_state["jx_page"]
    
    # Boundary correction
    if page > total_pages:
        page = total_pages
        st.session_state["jx_page"] = page
    if page < 1:
        page = 1
        st.session_state["jx_page"] = page

    # Render Pagination Controls
    col_prev, col_info, col_next = st.columns([1, 3, 1])
    with col_prev:
        if st.button("← Prev", key="jx_prev", disabled=(page == 1)):
            st.session_state["jx_page"] -= 1
            st.rerun()
    with col_info:
        st.markdown(f"<div style='text-align: center; padding-top: 8px;'>Page <b>{page}</b> of <b>{total_pages}</b> — <b>{len(filtered_df):,}</b> jobs</div>",
                    unsafe_allow_html=True)
    with col_next:
        if st.button("Next →", key="jx_next", disabled=(page == total_pages)):
            st.session_state["jx_page"] += 1
            st.rerun()

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # Slice page jobs
    page_df = filtered_df.iloc[(page-1)*PAGE_SIZE : page*PAGE_SIZE]
    
    # Render Cards
    for idx, (_, row) in enumerate(page_df.iterrows()):
        title = row.get("title", "No Title")
        company = row.get("company", "Unknown Company")
        city = row.get("city", "Unknown City")
        work_mode = row.get("work_mode", "Unknown Mode")
        exp_band = row.get("exp_band", "Not Specified")
        min_salary = row.get("min_salary")
        max_salary = row.get("max_salary")
        skills = row.get("standardized_skills", [])
        source = row.get("source", "Unknown Source")
        job_url = row.get("job_url", row.get("url"))
        logo_url = row.get("company_logo_url")
        desc = row.get("description", "No description available.")

        # Card container
        with st.container(border=True):
            # Header Row (Logo + Title)
            col_l, col_r = st.columns([1, 12])
            with col_l:
                if logo_url and isinstance(logo_url, str) and logo_url.strip() != "":
                    st.image(logo_url, width=42)
                else:
                    st.markdown("<h3>🏢</h3>", unsafe_allow_html=True)
            with col_r:
                st.markdown(f"**{title}**")
                st.markdown(
                    f"<span style='color:var(--accent-1);font-weight:600;'>{company}</span> | "
                    f"<span style='color:var(--text-mid);'>{city}</span> | "
                    f"<span style='color:var(--text-mid);'>{work_mode}</span>",
                    unsafe_allow_html=True
                )
            
            # Badges Row (Experience + Salary)
            sal_text = "Salary not disclosed"
            if pd.notna(min_salary) or pd.notna(max_salary):
                if pd.notna(min_salary) and pd.notna(max_salary):
                    sal_text = f"💰 {min_salary:.1f} - {max_salary:.1f} LPA"
                elif pd.notna(min_salary):
                    sal_text = f"💰 {min_salary:.1f}+ LPA"
                else:
                    sal_text = f"💰 Up to {max_salary:.1f} LPA"
                    
            st.markdown(
                f"<span style='display:inline-block;background:rgba(99,102,241,0.1);color:#a5b4fc;padding:2px 8px;border-radius:4px;font-size:0.78rem;margin-right:8px;font-weight:600;'>🎓 {exp_band}</span>"
                f"<span style='display:inline-block;background:rgba(6,182,212,0.1);color:#67e8f9;padding:2px 8px;border-radius:4px;font-size:0.78rem;font-weight:600;'>{sal_text}</span>",
                unsafe_allow_html=True
            )

            # Skills Pills
            if isinstance(skills, list) and skills:
                pills_html = " ".join([f'<span class="skill-tag">{s}</span>' for s in skills])
                st.markdown(
                    f"<div style='margin-top:8px;'>{pills_html}</div>",
                    unsafe_allow_html=True
                )

            # Expander View Details
            with st.expander("View Job Details", expanded=False):
                st.markdown("**Description Preview:**")
                st.write(desc)
                
                st.markdown("---")
                st.markdown(f"**Source Portal:** {source.capitalize()}")
                if job_url:
                    st.link_button("Apply on original website", job_url)
