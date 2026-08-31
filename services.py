import json
import logging
import re
from pypdf import PdfReader
from groq import Groq
from config import GROQ_API_KEY

# Inicializar cliente Groq
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Modelos compatibles en orden de preferencia
CANDIDATE_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "groq/compound",
    "qwen/qwen3.6-27b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

def extract_text_from_pdf(pdf_path, max_pages=50):
    reader = PdfReader(pdf_path)
    extracted_text = ""
    for page in reader.pages[:max_pages]:
        text = page.extract_text()
        if text:
            extracted_text += text + "\n"
    return extracted_text

def _call_groq_completion(messages, temperature=0.3):
    global client
    from config import GROQ_API_KEY
    if not client and GROQ_API_KEY:
        client = Groq(api_key=GROQ_API_KEY)
        
    if not client:
        raise ValueError("GROQ_API_KEY no está disponible o no se ha configurado.")
        
    last_error = None
    
    for model in CANDIDATE_MODELS:
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
            )
            return completion.choices[0].message.content
        except Exception as e:
            logging.warning(f"Fallo al consultar modelo {model} en Groq: {e}. Intentando alternativa...")
            last_error = e
            
    raise last_error

def generate_quiz_from_text(text):
    system_prompt = (
        "Actúa como un profesor universitario. Con base en el texto provisto, "
        "genera un cuestionario de exactamente 3 preguntas de opción múltiple. "
        "Responde ÚNICAMENTE con un arreglo JSON válido (sin explicaciones adicionales, sin markdown extra) "
        "con esta estructura exacta:\n"
        "[\n"
        "  {\n"
        '    "question": "Texto de la pregunta (máximo 250 caracteres)",\n'
        '    "options": ["Opción 1", "Opción 2", "Opción 3", "Opción 4"],\n'
        '    "correct_option_id": 0,\n'
        '    "explanation": "Explicación breve (máximo 200 caracteres)"\n'
        "  }\n"
        "]"
    )
    
    user_prompt = f"Texto de estudio:\n{text[:80000]}"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    response_text = _call_groq_completion(messages, temperature=0.2)
    
    # Limpiar posibles bloques de código markdown ```json ... ```
    cleaned = re.sub(r"^```json\s*", "", response_text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    
    # Extraer el bloque JSON de corchetes si hubiera texto adicional
    json_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if json_match:
        cleaned = json_match.group(0)
        
    return json.loads(cleaned)

def answer_question_from_context(question, context=None):
    if context:
        system_prompt = (
            "Actúa como un tutor académico paciente y experto. "
            "El estudiante está estudiando un documento con el siguiente texto de contexto:\n"
            f"---\n{context[:80000]}\n---\n"
            "Responde a la pregunta del estudiante basándote en el contexto anterior. "
            "Si la pregunta no se relaciona con el contexto, responde de forma general aclarando brevemente "
            "que no estaba en el texto original, pero proporciona una respuesta completa y educativa.\n"
            "INSTRUCCIONES CLAVE: Sé muy conciso, directo y claro. Usa formato markdown limpio."
        )
    else:
        system_prompt = (
            "Actúa como un tutor académico paciente y experto. "
            "Responde a la pregunta del estudiante de forma educativa, estructurada y muy clara.\n"
            "INSTRUCCIONES CLAVE: Sé muy conciso, directo y claro. Usa formato markdown limpio."
        )
        
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Pregunta del estudiante: {question}"}
    ]
    
    return _call_groq_completion(messages, temperature=0.4)