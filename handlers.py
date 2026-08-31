import os
import csv
import psutil
import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import SessionLocal, User, ActivePoll
from services import extract_text_from_pdf, generate_quiz_from_text, answer_question_from_pdf, ask_general_ai

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
        "📄 /duda [pregunta] - Resolver dudas exclusivas sobre tu PDF subido\n"
        "🤖 /ia [pregunta] - Consultar a la IA sobre cualquier tema o duda general\n"
        "📊 /stats - Ver tus estadísticas académicas\n"
        "🖥️ /sysinfo - Ver estado del servidor (CPU/RAM)\n"
        "📁 /exportar - Exportar base de datos a CSV\n"
        "⚡ /ping - Medir la latencia del bot con el servidor\n\n"
        "📚 *¿Cómo empezar?*\n"
        "1. Envíame un archivo **PDF** (máximo 5MB) para generar cuestionarios o hacerle preguntas con `/duda`.\n"
        "2. O escribe `/ia [pregunta]` para consultar cualquier duda académica libre.",
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
            
        # Guardar el texto extraído como el último contexto de estudio del usuario
        db = SessionLocal()
        user = db.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if user:
            user.last_context = text
        db.commit()
        db.close()
        
        keyboard = [
            [
                InlineKeyboardButton("🎯 Generar Cuestionario", callback_data="btn_quiz"),
                InlineKeyboardButton("💬 Resolver una Duda", callback_data="btn_duda"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await status_msg.edit_text(
            "📄 *¡PDF procesado con éxito!*\n\n"
            "He guardado el contenido en tu sesión de estudio. ¿Qué te gustaría hacer ahora?",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

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

def split_message(text: str, max_length: int = 4000) -> list[str]:
    """Divide un texto largo en bloques de tamaño máximo respetando saltos de línea."""
    if not text or len(text) <= max_length:
        return [text] if text else [""]
    
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break
        split_idx = remaining.rfind('\n', 0, max_length)
        if split_idx == -1 or split_idx < 100:
            split_idx = remaining.rfind(' ', 0, max_length)
        if split_idx == -1 or split_idx < 100:
            split_idx = max_length
        
        chunks.append(remaining[:split_idx].strip())
        remaining = remaining[split_idx:].strip()
    return chunks

# FUNCIÓN: Responder dudas exclusivas sobre el PDF
async def duda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Validación 1: Verificar si el usuario ingresó una pregunta
    if not context.args:
        await update.message.reply_text(
            "⚠️ *Uso incorrecto del comando*\n\n"
            "Por favor escribe tu duda sobre el PDF después de `/duda`.\n"
            "Ejemplo: `/duda ¿cuáles son los conceptos principales?`\n\n"
            "💡 *Tip:* Si quieres hacer una pregunta general sobre cualquier otro tema, usa `/ia [pregunta]`.", 
            parse_mode="Markdown"
        )
        return
        
    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=user_id).first()
    contexto = user.last_context if user else None
    db.close()
    
    # Validación 2: Verificar que el usuario tenga un PDF activo en su sesión
    if not contexto or len(contexto.strip()) < 50:
        await update.message.reply_text(
            "⚠️ *No tienes un archivo PDF cargado*\n\n"
            "El comando `/duda` responde preguntas **únicamente sobre el PDF** que hayas subido.\n\n"
            "👉 Por favor envía un archivo **PDF** primero.\n"
            "👉 O si quieres hacer una pregunta general sin PDF, usa: `/ia [tu pregunta]`",
            parse_mode="Markdown"
        )
        return
        
    pregunta = " ".join(context.args)
    status_msg = await update.message.reply_text("📖 Buscando en el contenido del PDF y consultando al tutor...")
    
    try:
        respuesta = answer_question_from_pdf(pregunta, contexto)
        chunks = split_message(respuesta, max_length=4000)
        
        first_chunk = chunks[0] if chunks else "No se obtuvo respuesta."
        try:
            await status_msg.edit_text(first_chunk, parse_mode="Markdown")
        except Exception as parse_err:
            logging.warning(f"Error parseando Markdown, enviando como texto plano: {parse_err}")
            await status_msg.edit_text(first_chunk)
            
        for chunk in chunks[1:]:
            try:
                await update.message.reply_text(chunk, parse_mode="Markdown")
            except Exception:
                await update.message.reply_text(chunk)
            
        # Ofrecer nuevamente el menú de opciones del documento
        keyboard = [
            [
                InlineKeyboardButton("🎯 Generar Cuestionario", callback_data="btn_quiz"),
                InlineKeyboardButton("💬 Resolver otra Duda del PDF", callback_data="btn_duda"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🔄 ¿Qué deseas hacer a continuación con este documento?",
            reply_markup=reply_markup
        )
    except Exception as e:
        logging.error(f"Error en el comando /duda: {e}")
        await status_msg.edit_text("⚠️ Ocurrió un error al procesar tu duda sobre el PDF. Por favor, intenta de nuevo.")

# NUEVA FUNCIÓN: Responder consultas generales a la IA sin requerir PDF
async def ia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Validación: Verificar si el usuario ingresó una pregunta
    if not context.args:
        await update.message.reply_text(
            "🤖 *Asistente IA General*\n\n"
            "Puedes preguntarme sobre cualquier tema, materia o concepto académico.\n"
            "Ejemplo: `/ia ¿qué es la fotosíntesis?`\n"
            "Ejemplo: `/ia resuelve esta ecuación paso a paso: 2x + 5 = 15`\n\n"
            "💡 *Tip:* Si deseas hacer preguntas sobre un PDF que subiste, usa `/duda [pregunta]`.",
            parse_mode="Markdown"
        )
        return
        
    pregunta = " ".join(context.args)
    status_msg = await update.message.reply_text("🤖 Consultando a la Inteligencia Artificial...")
    
    try:
        respuesta = ask_general_ai(pregunta)
        chunks = split_message(respuesta, max_length=4000)
        
        first_chunk = chunks[0] if chunks else "No se obtuvo respuesta."
        try:
            await status_msg.edit_text(first_chunk, parse_mode="Markdown")
        except Exception as parse_err:
            logging.warning(f"Error parseando Markdown, enviando como texto plano: {parse_err}")
            await status_msg.edit_text(first_chunk)
            
        for chunk in chunks[1:]:
            try:
                await update.message.reply_text(chunk, parse_mode="Markdown")
            except Exception:
                await update.message.reply_text(chunk)
    except Exception as e:
        logging.error(f"Error en el comando /ia: {e}")
        await status_msg.edit_text("⚠️ Ocurrió un error al consultar a la IA. Por favor, intenta de nuevo.")

# FUNCIÓN: Manejar clics de los botones interactivos
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=user_id).first()
    contexto = user.last_context if user else None
    
    # Validación 1: Verificar que el usuario tenga un PDF activo en base de datos
    if not contexto or len(contexto.strip()) < 50:
        await query.edit_message_text(
            "⚠️ *Sesión de estudio vencida o vacía*\n\n"
            "No tienes ningún archivo PDF activo. Por favor, envía un documento PDF válido primero.",
            parse_mode="Markdown"
        )
        db.close()
        return

    if data == "btn_quiz":
        # Deshabilitar botones editando el mensaje para evitar doble clic o re-generación
        await query.edit_message_text("🧠 *Generando cuestionario con Inteligencia Artificial...*\nPor favor, espera unos segundos.", parse_mode="Markdown")
        
        try:
            quizzes = generate_quiz_from_text(contexto)
            
            # Validación 2: Verificar que se hayan recibido preguntas válidas
            if not quizzes or not isinstance(quizzes, list):
                raise ValueError("La respuesta de la IA no contiene una lista de cuestionarios válida.")
                
            # Enviar las encuestas correspondientes
            for q in quizzes:
                message = await context.bot.send_poll(
                    chat_id=query.message.chat_id,
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
            
            # Confirmar éxito
            await query.message.reply_text("🎯 ¡Quiz generado con éxito! Responde las preguntas arriba para acumular puntos.")
        except Exception as e:
            logging.error(f"Error generando quiz desde callback: {e}")
            # Si falla, restaurar botones para permitir volver a intentarlo
            keyboard = [
                [
                    InlineKeyboardButton("🎯 Intentar Generar de nuevo", callback_data="btn_quiz"),
                    InlineKeyboardButton("💬 Resolver una Duda del PDF", callback_data="btn_duda"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "❌ *Error al generar el cuestionario*\n\n"
                "Hubo un problema al contactar con la IA o formatear las preguntas. ¿Deseas reintentar?",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            
    elif data == "btn_duda":
        # Mostrar instrucciones para /duda y quitar botones
        await query.edit_message_text(
            "💬 *Resolver dudas sobre este PDF*\n\n"
            "Escribe tu pregunta utilizando el comando `/duda` seguido de tu pregunta.\n\n"
            "Ejemplo:\n"
            "`/duda resume las conclusiones principales del documento`\n"
            "`/duda ¿qué conceptos clave se mencionan en la página 1?`\n\n"
            "💡 *Nota:* Para preguntas generales no relacionadas al PDF, usa `/ia [pregunta]`.",
            parse_mode="Markdown"
        )
        
    db.close()