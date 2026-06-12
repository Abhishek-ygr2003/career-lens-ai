import streamlit as st
import pandas as pd

def render_job_explorer(df: pd.DataFrame):
    st.markdown("### 🔎 Job Explorer")
    if df.empty:
        st.info("No data available.")
        return
        
    c1, c2 = st.columns([2, 1])
    with c1:
        local_search = st.text_input("Filter within results", key="explorer_search", placeholder="e.g. Senior Data Scientist")
    with c2:
        default_cols = ['title', 'company', 'city', 'min_exp', 'job_category', 'posted_at']
        available_cols = [c for c in default_cols if c in df.columns]
        selected_cols = st.multiselect("Columns to display", df.columns.tolist(), default=available_cols, key="explorer_cols")
        
    display_df = df.copy()
    if local_search:
        mask = display_df.astype(str).apply(lambda x: x.str.contains(local_search, case=False, na=False)).any(axis=1)
        display_df = display_df[mask]
        
    if not selected_cols:
        st.warning("Please select at least one column to display.")
        return
        
    st.dataframe(display_df[selected_cols], width="stretch", height=600)
