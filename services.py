import json
import logging
from pypdf import PdfReader
from google import genai
from config import GEMINI_API_KEY

# Inicializar el nuevo cliente oficial
client = genai.Client(api_key=GEMINI_API_KEY)

def extract_text_from_pdf(pdf_path, max_pages=10):
    reader = PdfReader(pdf_path)
    extracted_text = ""
    for page in reader.pages[:max_pages]:
        text = page.extract_text()
        if text:
            extracted_text += text + "\n"
    return extracted_text

def generate_quiz_from_text(text):
    prompt = f"""
    Actúa como un profesor universitario. Con base en el siguiente texto, genera un cuestionario de exactamente 3 preguntas de opción múltiple.
    Responde ÚNICAMENTE con un arreglo JSON válido (sin etiquetas markdown) con esta estructura exacta:
    [
      {{
        "question": "Texto de la pregunta (máximo 250 caracteres)",
        "options": ["Opción 1", "Opción 2", "Opción 3", "Opción 4"],
        "correct_option_id": 0,
        "explanation": "Explicación breve (máximo 200 caracteres)"
      }}
    ]
    Texto de estudio:
    {text[:4000]}
    """
    
    # Nueva sintaxis de la librería oficial
    response = client.models.generate_content(
        model='gemini-3.5-flash',
        contents=prompt
    )
    
    raw_text = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(raw_text)