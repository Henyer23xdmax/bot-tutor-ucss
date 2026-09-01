import os
import sys
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    PollAnswerHandler, CallbackQueryHandler, filters
)

# Agregar el directorio raíz al path para importar módulos del bot (Vercel usa /var/task)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import TELEGRAM_TOKEN
from handlers import (
    start, stats, sysinfo, exportar, ping, duda, ia,
    handle_document, handle_poll_answer, handle_callback
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Bot Tutor UCSS",
    version="1.0.0",
    description="Bot de tutor académico para Telegram desplegado en Vercel"
)

# Inicializar la aplicación de Telegram (una sola vez por cold start)
ptb_app = Application.builder().token(TELEGRAM_TOKEN).build()

# Registrar handlers
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CommandHandler("stats", stats))
ptb_app.add_handler(CommandHandler("sysinfo", sysinfo))
ptb_app.add_handler(CommandHandler("exportar", exportar))
ptb_app.add_handler(CommandHandler("ping", ping))
ptb_app.add_handler(CommandHandler("duda", duda))
ptb_app.add_handler(CommandHandler("ia", ia))
ptb_app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
ptb_app.add_handler(PollAnswerHandler(handle_poll_answer))
ptb_app.add_handler(CallbackQueryHandler(handle_callback))


@app.get("/")
async def home():
    """Health check"""
    return {"message": "Bot Tutor UCSS activo en Vercel", "status": "running", "bot": "ok"}


@app.post("/api/index")
async def telegram_webhook(request: Request):
    """Webhook de Telegram"""
    try:
        data = await request.json()
        update = Update.de_json(data, ptb_app.bot)
        await ptb_app.process_update(update)
        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        logger.error(f"Error procesando webhook: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.get("/api/index")
async def webhook_info():
    """Información del webhook"""
    return {
        "bot": "Tutor UCSS",
        "status": "active",
        "endpoints": {
            "webhook": "/api/index",
            "health": "/"
        }
    }