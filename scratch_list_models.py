"""Lista los modelos Gemini disponibles para esta API key."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
API_KEY = os.getenv("GEMINI_API_KEY", "")

from google import genai
client = genai.Client(api_key=API_KEY)

print("Modelos disponibles:\n")
for m in client.models.list():
    print(f"  {m.name}")
