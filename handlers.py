import os
import csv
import psutil
import logging
import time
from telegram import Update
from telegram.ext import ContextTypes
from database import SessionLocal, User, ActivePoll
from services import extract_text_from_pdf, generate_quiz_from_text, answer_question_from_context

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    
    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=user_id).first()
    if not user:
        user = User(telegram_id=user_id, first_name=first_name)
        db.add(user)
        db.commit()
    db.close()
    
    await update.message.reply_text(
        f"👋 ¡Hola {first_name}! He guardado tu perfil en la base de datos.\n\n"
        "✨ *Comandos disponibles:*\n"
        "📖 /start - Mostrar este mensaje de bienvenida\n"
        "📊 /stats - Ver tus estadísticas académicas\n"
        "🖥️ /sysinfo - Ver estado del servidor (CPU/RAM)\n"
        "📁 /exportar - Exportar base de datos a CSV\n"
        "⚡ /ping - Medir la latencia del bot con el servidor\n"
        "💬 /duda [pregunta] - Resuelve tus dudas académicas sobre el PDF enviado o en general\n\n"
        "📚 *¿Cómo empezar?*\n"
        "Envíame un archivo **PDF** (máximo 5MB) de estudio y yo generaré un cuestionario de 3 preguntas de opción múltiple para evaluar tu conocimiento.",
        parse_mode="Markdown"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=update.effective_user.id).first()
    if user:
        total = user.correct_answers + user.wrong_answers
        await update.message.reply_text(
            f"📊 *Tus Estadísticas Académicas*\n\n"
            f"✅ Respuestas correctas: {user.correct_answers}\n"
            f"❌ Respuestas incorrectas: {user.wrong_answers}\n"
            f"📈 Total respondidas: {total}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("Aún no tienes estadísticas registradas. ¡Inicia con /start!")
    db.close()

# NUEVA FUNCIÓN: Monitoreo de servidor
async def sysinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory().percent
    await update.message.reply_text(
        f"🖥️ *Estado del Servidor de Producción*\n\n"
        f"⚡ Uso de CPU: {cpu}%\n"
        f"🧠 Uso de RAM: {ram}%\n"
        f"🟢 Estado del servicio: Activo",
        parse_mode="Markdown"
    )

# NUEVA FUNCIÓN: Medir latencia
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start_time = time.time()
    message = await update.message.reply_text("⚡ Calculando latencia...")
    latency = (time.time() - start_time) * 1000
    await message.edit_text(f"🏓 *Pong!*\n\n⏱️ Latencia: {latency:.2f} ms", parse_mode="Markdown")

# NUEVA FUNCIÓN: Exportar base de datos a CSV
async def exportar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    users = db.query(User).all()
    
    csv_filename = "reporte_notas.csv"
    with open(csv_filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["ID Telegram", "Nombre", "Correctas", "Incorrectas"])
        for u in users:
            writer.writerow([u.telegram_id, u.first_name, u.correct_answers, u.wrong_answers])
    db.close()
    
    await update.message.reply_document(
        document=open(csv_filename, "rb"), 
        filename="Reporte_Estudiantes.csv",
        caption="📁 Aquí tienes el respaldo de la base de datos."
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if doc.mime_type != 'application/pdf' or not doc.file_name.lower().endswith(".pdf"):
        await update.message.reply_text("⚠️ Por seguridad, solo proceso archivos PDF.")
        return
        
    if doc.file_size > 5 * 1024 * 1024:
        await update.message.reply_text("⚠️ El archivo es demasiado pesado. Límite: 5MB.")
        return

    status_msg = await update.message.reply_text("⏳ Procesando documento...")
    file = await context.bot.get_file(doc.file_id)
    pdf_path = f"temp_{doc.file_name}"
    await file.download_to_drive(pdf_path)

    try:
        text = extract_text_from_pdf(pdf_path)
        if len(text.strip()) < 50:
            await status_msg.edit_text("❌ No se pudo extraer texto. Puede ser un PDF escaneado.")
            return
            
        await status_msg.edit_text("🧠 Analizando con Inteligencia Artificial...")
        quizzes = generate_quiz_from_text(text)
        
        await status_msg.edit_text("🎯 ¡Quiz generado! Responde para sumar puntos:")
        
        db = SessionLocal()
        
        # Guardar el texto extraído como el último contexto de estudio del usuario
        user = db.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if user:
            user.last_context = text
            
        for q in quizzes:
            message = await context.bot.send_poll(
                chat_id=update.effective_chat.id,
                question=q["question"][:255],
                options=[opt[:100] for opt in q["options"][:4]],
                type="quiz",
                correct_option_id=int(q["correct_option_id"]),
                explanation=q.get("explanation", "")[:200],
                is_anonymous=False 
            )
            poll_record = ActivePoll(poll_id=message.poll.id, correct_option_id=int(q["correct_option_id"]))
            db.add(poll_record)
        db.commit()
        db.close()

    except Exception as e:
        logging.error(f"Error procesando PDF: {e}")
        await status_msg.edit_text("⚠️ Ocurrió un error en el procesamiento. Revisa los logs de la terminal.")
    finally:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = answer.poll_id
    selected_option = answer.option_ids[0]
    user_id = answer.user.id

    db = SessionLocal()
    poll_record = db.query(ActivePoll).filter_by(poll_id=poll_id).first()
    user_record = db.query(User).filter_by(telegram_id=user_id).first()

    if poll_record and user_record:
        if selected_option == poll_record.correct_option_id:
            user_record.correct_answers += 1
        else:
            user_record.wrong_answers += 1
        db.commit()
    db.close()

# NUEVA FUNCIÓN: Responder dudas académicas
async def duda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Verificar si el usuario ingresó una pregunta
    if not context.args:
        await update.message.reply_text(
            "⚠️ *Uso incorrecto del comando*\n\n"
            "Por favor escribe tu duda académica después de `/duda`.\n"
            "Ejemplo: `/duda ¿qué es la fotosíntesis?`", 
            parse_mode="Markdown"
        )
        return
        
    pregunta = " ".join(context.args)
    status_msg = await update.message.reply_text("🤔 Analizando tu duda y consultando al tutor...")
    
    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=user_id).first()
    contexto = user.last_context if user else None
    db.close()
    
    try:
        respuesta = answer_question_from_context(pregunta, contexto)
        await status_msg.edit_text(respuesta, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error en el comando /duda: {e}")
        await status_msg.edit_text("⚠️ Ocurrió un error al procesar tu duda. Por favor, intenta de nuevo.")