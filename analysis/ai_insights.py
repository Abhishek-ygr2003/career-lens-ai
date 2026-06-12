import streamlit as st
import pandas as pd
from dashboard.ai_engine import is_ai_available, generate_market_context, get_gemini_insight

def render_ai_insights(df: pd.DataFrame):
    st.markdown("### ✨ AI Insights")
    if df.empty:
        st.info("No data available.")
        return
        
    if not is_ai_available():
        st.warning("Gemini API key is not configured. Please set GEMINI_API_KEY in your .env file.")
        return
        
    if st.button("Generate Insights with Gemini"):
        with st.spinner("Analyzing market data..."):
            context = generate_market_context(df)
            insight = get_gemini_insight(context)
            st.markdown(f"<div class='ai-response'>{insight}</div>", unsafe_allow_html=True)
