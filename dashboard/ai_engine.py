import os
from dotenv import load_dotenv

load_dotenv()

def get_gemini_api_key() -> str | None:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    return key if key and key != "your-gemini-api-key" else None

def is_ai_available() -> bool:
    return get_gemini_api_key() is not None

def generate_market_context(df) -> str:
    if df is None or df.empty:
        return "No data."
    
    total = len(df)
    cities = df['city'].value_counts().head(3).to_dict()
    categories = df['job_category'].value_counts().head(3).to_dict()
    
    return f"Total jobs: {total}. Top cities: {cities}. Top categories: {categories}."

def get_gemini_insight(context: str) -> str:
    from google import genai
    key = get_gemini_api_key()
    if not key:
        return "API key missing."
    try:
        client = genai.Client(api_key=key)
        prompt = f"Analyze the following job market data and provide 3 key insights:\n{context}"
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return response.text
    except Exception as e:
        return f"Error generating insights: {e}"
