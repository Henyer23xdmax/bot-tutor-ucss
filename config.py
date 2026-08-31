import os
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

def get_env_clean(key: str, default=None):
    val = os.getenv(key, default)
    if val:
        val = val.strip().strip("'\"")
    return val

TELEGRAM_TOKEN = get_env_clean("TELEGRAM_TOKEN")
GROQ_API_KEY = get_env_clean("GROQ_API_KEY")
GEMINI_API_KEY = get_env_clean("GEMINI_API_KEY")
DATABASE_URL = get_env_clean("DATABASE_URL", "sqlite:///bot_database.db")
