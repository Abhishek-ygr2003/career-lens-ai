from dotenv import load_dotenv
import os

load_dotenv()

print("KEY FOUND:", bool(os.getenv("GEMINI_API_KEY")))

from google import genai

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Reply with exactly OK"
)

print(response.text)