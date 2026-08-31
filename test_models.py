import os
from dotenv import load_dotenv
load_dotenv()

from google import genai
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

candidate_models = [
    'gemini-3.5-flash',
    'gemini-3.5-flash-lite',
    'gemini-2.5-flash',
    'gemini-flash-latest',
]

for model_name in candidate_models:
    try:
        print(f"Testing model: {model_name}...")
        response = client.models.generate_content(
            model=model_name,
            contents='Hola, responde con la palabra: OK'
        )
        print(f" ✅ Success with {model_name}! Response: {response.text.strip()}")
        break
    except Exception as e:
        print(f" ❌ Failed for {model_name}: {e}\n")
