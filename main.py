import os
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, PollAnswerHandler, CallbackQueryHandler, filters
from config import TELEGRAM_TOKEN, GROQ_API_KEY
from handlers import start, stats, sysinfo, exportar, ping, duda, handle_document, handle_poll_answer, handle_callback

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")
        
    def log_message(self, format, *args):
        # Mute requests log to keep the console clean
        return

def run_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logging.info(f"🏥 Servidor de Health Check activo en el puerto {port}")
    server.serve_forever()

async def post_init(application) -> None:
    commands = [
        BotCommand("start", "Iniciar el tutor y registrarse"),
        BotCommand("stats", "Ver mis estadísticas de aciertos"),
        BotCommand("sysinfo", "Ver estado del servidor (CPU/RAM)"),
        BotCommand("exportar", "Exportar lista de estudiantes a CSV"),
        BotCommand("ping", "Medir la latencia del bot con el servidor"),
        BotCommand("duda", "Resolver dudas académicas con el tutor"),
    ]
    await application.bot.set_my_commands(commands)

if __name__ == '__main__':
    if not TELEGRAM_TOKEN or not GROQ_API_KEY:
        print("❌ ERROR: Faltan las variables TELEGRAM_TOKEN o GROQ_API_KEY en el archivo .env")
        exit(1)
        
    # Iniciar servidor de Health Check en segundo plano para Render
    threading.Thread(target=run_health_check_server, daemon=True).start()
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    # Rutas y controladores principales
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    
    # Nuevas rutas de administración
    app.add_handler(CommandHandler("sysinfo", sysinfo))
    app.add_handler(CommandHandler("exportar", exportar))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("duda", duda))
    
    # Procesamiento de archivos, encuestas y callbacks
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(PollAnswerHandler(handle_poll_answer))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    print("🤖 Servidor Modular iniciado. Esperando mensajes...")
    app.run_polling()