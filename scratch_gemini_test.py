"""
Prueba cuáles modelos del listado aceptan llamadas reales con JSON schema.
Solo prueba modelos 'flash' (rápidos, bajo costo) que tengan sentido para producción.
"""
import os, json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
API_KEY = os.getenv("GEMINI_API_KEY", "")

from google import genai
from google.genai import types

client = genai.Client(api_key=API_KEY)

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict":    {"type": "string", "enum": ["phishing", "suspicious", "no_indicators"]},
        "level":      {"type": "string", "enum": ["RED", "YELLOW", "GREEN"]},
        "reasons":    {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["verdict", "level", "reasons", "confidence"],
}
SYSTEM = "Eres un auditor de seguridad de correos. Responde SOLO con un JSON valido segun el esquema."
EMAIL  = "<<<EMAIL>>>\nSender: test@uneti.edu.ve\nSubject: Reunion\nBody: Recordatorio reunion jueves 10AM.\n<<<END_EMAIL>>>"

config = types.GenerateContentConfig(
    system_instruction=SYSTEM,
    response_mime_type="application/json",
    response_schema=SCHEMA,
)

# Solo modelos flash/lite — apropiados para producción
CANDIDATES = [
    "models/gemini-3.5-flash",
    "models/gemini-3.5-flash-lite",
    "models/gemini-3.6-flash",
    "models/gemini-3.7-flash",
    "models/gemini-3.8-flash",
    "models/gemini-2.5-flash",
    "models/gemini-2.5-flash-lite",
    "models/gemini-3.1-flash-lite",
]

print(f"Probando {len(CANDIDATES)} modelos...\n")
working = []

for model in CANDIDATES:
    try:
        resp = client.models.generate_content(model=model, contents=EMAIL, config=config)
        data = json.loads(resp.text)
        v = data.get("verdict", "?")
        l = data.get("level", "?")
        c = data.get("confidence", "?")
        print(f"[OK]   {model}")
        print(f"       verdict={v}  level={l}  confidence={c}")
        working.append(model)
    except Exception as e:
        short = str(e)[:100].replace("\n", " ")
        print(f"[FAIL] {model}")
        print(f"       {type(e).__name__}: {short}")
    print()

print("=" * 55)
if working:
    print(f"Modelos funcionales ({len(working)}):")
    for m in working:
        print(f"  → {m}")
    print(f"\nRecomendacion para .env: GEMINI_MODEL={working[0].replace('models/', '')}")
else:
    print("Ningun modelo respondio correctamente.")
