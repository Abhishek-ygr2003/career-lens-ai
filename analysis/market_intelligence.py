import streamlit as st
import pandas as pd

def render_market_intelligence(df: pd.DataFrame):
    st.markdown("### 🧠 Market Intelligence")
    if df.empty:
        st.info("No data available.")
        return
        
    st.write("Cross-tabulation of Experience Level by Work Mode")
    pivot = pd.crosstab(df['exp_band'], df['work_mode'])
    st.dataframe(pivot, width="stretch")
