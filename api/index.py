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

_ptb_initialized = False


def _get_ptb_app():
    """Crea (una sola vez) y devuelve la aplicación de Telegram."""
    global _ptb_initialized
    if "ptb_app" not in globals():
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("stats", stats))
        app.add_handler(CommandHandler("sysinfo", sysinfo))
        app.add_handler(CommandHandler("exportar", exportar))
        app.add_handler(CommandHandler("ping", ping))
        app.add_handler(CommandHandler("duda", duda))
        app.add_handler(CommandHandler("ia", ia))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        app.add_handler(PollAnswerHandler(handle_poll_answer))
        app.add_handler(CallbackQueryHandler(handle_callback))
        globals()["ptb_app"] = app
    return globals()["ptb_app"]


@app.get("/")
async def home():
    """Health check"""
    return {"message": "Bot Tutor UCSS activo en Vercel", "status": "running", "bot": "ok"}


async def _process_webhook(data) -> None:
    """Inicializa (si hace falta) y procesa un update de Telegram."""
    import asyncio
    application = _get_ptb_app()
    if not _ptb_initialized:
        await application.initialize()
        globals()["_ptb_initialized"] = True
    update = Update.de_json(data, application.bot)
    await application.process_update(update)


@app.post("/api/index")
async def telegram_webhook(request: Request):
    """Webhook de Telegram"""
    try:
        data = await request.json()
        await _process_webhook(data)
        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        logger.error(f"Error procesando webhook: {e}", exc_info=True)
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