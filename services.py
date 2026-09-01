import json
import logging
import re
from io import BytesIO
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

def extract_text_from_pdf_bytes(data: bytes, max_pages=50):
    """Extrae texto de un PDF a partir de sus bytes (sin tocar disco, ideal para serverless)."""
    reader = PdfReader(BytesIO(data))
    extracted_text = ""
    for page in reader.pages[:max_pages]:
        text = page.extract_text()
        if text:
            extracted_text += text + "\n"
    return extracted_text

def extract_text_from_pdf(pdf_path, max_pages=50):
    reader = PdfReader(pdf_path)
    extracted_text = ""
    for page in reader.pages[:max_pages]:
        text = page.extract_text()
        if text:
            extracted_text += text + "\n"
    return extracted_text

def _clean_reasoning_tags(text: str) -> str:
    if not text:
        return ""
    # Remover bloques <think>...</think>
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip()

def _call_groq_completion(messages, temperature=0.3, max_tokens=None):
    global client
    from config import GROQ_API_KEY
    if not client and GROQ_API_KEY:
        client = Groq(api_key=GROQ_API_KEY)
        
    if not client:
        raise ValueError("GROQ_API_KEY no está disponible o no se ha configurado.")
        
    last_error = None
    
    for model in CANDIDATE_MODELS:
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
            if max_tokens:
                kwargs["max_tokens"] = max_tokens
                
            completion = client.chat.completions.create(**kwargs)
            raw_content = completion.choices[0].message.content or ""
            content = _clean_reasoning_tags(raw_content)
            
            if content.strip():
                return content
            else:
                logging.warning(f"Modelo {model} devolvió contenido vacío. Intentando alternativa...")
        except Exception as e:
            logging.warning(f"Fallo al consultar modelo {model} en Groq: {e}. Intentando alternativa...")
            last_error = e
            
    if last_error:
        raise last_error
    raise ValueError("Ningún modelo de IA devolvió una respuesta válida.")

def generate_quiz_from_text(text):
    system_prompt = (
        "Actúa como un profesor universitario riguroso y pedagógico. Con base en el texto provisto, "
        "genera un cuestionario de EXACTAMENTE 5 preguntas de opción múltiple variadas y educativas. "
        "Cada pregunta debe tener exactamente 4 opciones y una única respuesta correcta.\n"
        "Responde ÚNICAMENTE con un arreglo JSON válido (sin explicaciones adicionales, sin markdown extra) "
        "con esta estructura exacta:\n"
        "[\n"
        "  {\n"
        '    "question": "Texto de la pregunta (máximo 250 caracteres)",\n'
        '    "options": ["Opción 1", "Opción 2", "Opción 3", "Opción 4"],\n'
        '    "correct_option_id": 0,\n'
        '    "explanation": "Explicación breve de la respuesta correcta (máximo 200 caracteres)"\n'
        "  }\n"
        "]"
    )
    
    user_prompt = f"Texto de estudio:\n{text[:80000]}"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    response_text = _call_groq_completion(messages, temperature=0.5, max_tokens=1500)
    
    # Limpiar posibles bloques de código markdown ```json ... ```
    cleaned = re.sub(r"^```json\s*", "", response_text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    
    # Extraer el bloque JSON de corchetes si hubiera texto adicional
    json_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if json_match:
        cleaned = json_match.group(0)
        
    return json.loads(cleaned)

def answer_question_from_pdf(question: str, context: str):
    """Responde preguntas estrictamente basadas en el documento PDF proporcionado."""
    system_prompt = (
        "Actúa como un tutor académico experto. El estudiante te hace una pregunta EXCLUSIVAMENTE sobre "
        "el documento PDF que ha subido. El contenido del documento es el siguiente:\n"
        f"---\n{context[:80000]}\n---\n"
        "REGLAS ESTRICTAS:\n"
        "1. Responde basándote ÚNICA Y EXCLUSIVAMENTE en la información explícita del documento anterior.\n"
        "2. Si la respuesta no se encuentra en el documento, indícalo de forma clara y directa:\n"
        "   '⚠️ Esta información no se encuentra en el PDF que subiste. Si deseas consultar sobre temas generales fuera del documento, usa el comando /ia.'\n"
        "3. Sé conciso, directo, didáctico y usa formato markdown limpio. Concluye siempre tus oraciones y secciones de forma completa."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Pregunta sobre el PDF: {question}"}
    ]
    return _call_groq_completion(messages, temperature=0.2, max_tokens=1500)

def ask_general_ai(question: str):
    """Responde cualquier duda general o académica sin requerir un PDF previo."""
    system_prompt = (
        "Actúa como un asistente académico y tutor inteligente experto, didáctico y servicial. "
        "Responde a la duda o tema formulado por el estudiante de forma clara, estructurada y pedagógica.\n"
        "INSTRUCCIONES CLAVE:\n"
        "1. ESTRUCTURA: Ve directo al grano con explicaciones claras y didácticas.\n"
        "2. CIERRE COMPLETO: Asegúrate de finalizar y cerrar siempre tus oraciones y secciones de forma completa y natural. Nunca dejes una idea a medias.\n"
        "3. FORMATO: Usa listas y viñetas ordenadas (ej: • **Título:** Detalle) en lugar de tablas Markdown complejas para que sea fácil y cómodo de leer en la app móvil de Telegram."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Pregunta: {question}"}
    ]
    return _call_groq_completion(messages, temperature=0.5, max_tokens=1500)

# Compatibilidad con llamadas previas
def answer_question_from_context(question, context=None):
    if context:
        return answer_question_from_pdf(question, context)
    return ask_general_ai(question)