from google import genai
from backend.config import settings

client = genai.Client(api_key=settings.gemini_api_key)
for m in client.models.list():
    print(m.name, "-", getattr(m, "supported_actions", ""))