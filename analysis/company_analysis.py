import streamlit as st
import pandas as pd
import plotly.express as px
from analysis.helpers import COLORS, PLOTLY_LAYOUT

def render_company_analysis(df: pd.DataFrame):
    st.markdown("### 🏢 Company Analysis")
    if df.empty:
        st.info("No data available.")
        return
        
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        top_n = st.slider("Top Companies", 5, 50, 15, key="comp_top_n")
    with c2:
        sort_by = st.radio("Sort by", ["Job Count", "Alphabetical"], horizontal=True, key="comp_sort")
    with c3:
        view_as = st.radio("View as", ["Count", "Percentage"], horizontal=True, key="comp_view")

    comp_counts = df[df['company'] != 'Unknown']['company'].value_counts().reset_index()
    comp_counts.columns = ['Company', 'Count']
    
    if sort_by == "Alphabetical":
        comp_counts = comp_counts.sort_values('Company')
        
    comp_counts = comp_counts.head(top_n)
    
    if view_as == "Percentage":
        total_known = len(df[df['company'] != 'Unknown'])
        if total_known > 0:
            comp_counts['Count'] = (comp_counts['Count'] / total_known) * 100

    fig = px.bar(
        comp_counts, 
        x='Count', y='Company', 
        orientation='h',
        color='Company',
        color_discrete_sequence=COLORS,
        title=f"Top {top_n} Hiring Companies",
        labels={"Count": "% of Jobs" if view_as == "Percentage" else "Job Count"}
    )
    if sort_by == "Job Count":
        fig.update_layout(yaxis={'categoryorder':'total ascending'})
    else:
        fig.update_layout(yaxis={'categoryorder':'category descending'})
        
    if view_as == "Percentage":
        fig.update_traces(texttemplate='%{x:.1f}%', textposition='outside')
    else:
        fig.update_traces(texttemplate='%{x}', textposition='outside')
        
    fig.update_layout(**PLOTLY_LAYOUT)
    fig.update_layout(showlegend=False, height=max(400, top_n * 25), margin=dict(r=50))
    st.plotly_chart(fig, width="stretch")
