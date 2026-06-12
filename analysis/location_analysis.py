import streamlit as st
import pandas as pd
import plotly.express as px
from analysis.helpers import PLOTLY_LAYOUT

def render_location_analysis(df: pd.DataFrame):
    st.markdown("### 📍 Location Analysis")
    if df.empty:
        st.info("No data available.")
        return
        
    c1, c2 = st.columns([2, 1])
    with c1:
        top_n = st.slider("Top Cities to show", 5, 50, 20, key="loc_top_n")
    with c2:
        sort_by = st.radio("Sort by", ["Job Count", "Alphabetical"], horizontal=True, key="loc_sort")
        
    city_counts = df[df['city'] != 'Unknown']['city'].value_counts().reset_index()
    city_counts.columns = ['City', 'Count']
    
    if sort_by == "Alphabetical":
        city_counts = city_counts.sort_values('City')
        
    city_counts = city_counts.head(top_n)
    
    fig = px.bar(
        city_counts,
        x='City', y='Count',
        color='Count',
        color_continuous_scale=["#1e3a5f", "#6366f1", "#06b6d4"],
        title=f"Top {top_n} Cities for Jobs"
    )
    fig.update_layout(**PLOTLY_LAYOUT, xaxis_tickangle=-45)
    fig.update_coloraxes(showscale=False)
    st.plotly_chart(fig, width="stretch")
