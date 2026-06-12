import streamlit as st
import pandas as pd
import plotly.express as px
from analysis.helpers import COLORS, PLOTLY_LAYOUT, EXP_BAND_ORDER

def render_experience_analysis(df: pd.DataFrame):
    st.markdown("### 🎓 Experience Requirements")
    if df.empty:
        st.info("No data available.")
        return
        
    view_as = st.radio("View as", ["Count", "Percentage"], horizontal=True, key="exp_view")
        
    exp_counts = df['exp_band'].value_counts().reindex(EXP_BAND_ORDER).fillna(0).reset_index()
    exp_counts.columns = ['Experience Level', 'Count']
    
    if view_as == "Percentage":
        total = exp_counts['Count'].sum()
        if total > 0:
            exp_counts['Count'] = (exp_counts['Count'] / total) * 100
    
    fig = px.bar(
        exp_counts, 
        x='Experience Level', y='Count',
        color='Experience Level',
        color_discrete_sequence=COLORS,
        title="Jobs by Experience Level",
        labels={"Count": "% of Jobs" if view_as == "Percentage" else "Job Count"}
    )
    if view_as == "Percentage":
        fig.update_traces(texttemplate='%{y:.1f}%', textposition='outside')
    else:
        fig.update_traces(texttemplate='%{y}', textposition='outside')
        
    fig.update_layout(**PLOTLY_LAYOUT)
    fig.update_layout(showlegend=False, margin=dict(t=50))
    st.plotly_chart(fig, width="stretch")
