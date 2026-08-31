import os
import csv
import psutil
import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import SessionLocal, User, ActivePoll
from services import extract_text_from_pdf, generate_quiz_from_text, answer_question_from_pdf, ask_general_ai

def get_or_create_user(db, telegram_id: int, first_name: str = "Estudiante") -> User:
    user = db.query(User).filter_by(telegram_id=telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id, first_name=first_name or "Estudiante")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "Estudiante"
    
    db = SessionLocal()
    user = get_or_create_user(db, user_id, first_name)
    user.first_name = first_name
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
    user = get_or_create_user(db, update.effective_user.id, update.effective_user.first_name)
    total = user.correct_answers + user.wrong_answers
    await update.message.reply_text(
        f"📊 *Tus Estadísticas Académicas*\n\n"
        f"✅ Respuestas correctas: {user.correct_answers}\n"
        f"❌ Respuestas incorrectas: {user.wrong_answers}\n"
        f"📈 Total respondidas: {total}",
        parse_mode="Markdown"
    )
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
    safe_filename = "".join(c for c in doc.file_name if c.isalnum() or c in "._-")
    pdf_path = f"temp_{update.effective_user.id}_{safe_filename}"
    await file.download_to_drive(pdf_path)

    try:
        text = extract_text_from_pdf(pdf_path)
        if len(text.strip()) < 50:
            await status_msg.edit_text("❌ No se pudo extraer suficiente texto del PDF. Puede ser un PDF escaneado o un formulario con imágenes.")
            return
            
        # Guardar el texto extraído como el último contexto de estudio del usuario
        db = SessionLocal()
        user = get_or_create_user(db, update.effective_user.id, update.effective_user.first_name)
        user.last_context = text
        db.commit()
        db.close()
        
        keyboard = [
            [
                InlineKeyboardButton("🎯 Generar Cuestionario", callback_data="btn_quiz"),
                InlineKeyboardButton("💬 Resolver una Duda del PDF", callback_data="btn_duda"),
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
    user_record = get_or_create_user(db, user_id, answer.user.first_name)

    is_correct = False
    if poll_record and user_record:
        if selected_option == poll_record.correct_option_id:
            user_record.correct_answers += 1
            is_correct = True
        else:
            user_record.wrong_answers += 1
        db.commit()
    db.close()

    # Rastrear progreso del cuestionario para enviar los botones al terminar las 5 preguntas
    quiz_data = context.user_data.get("active_quiz")
    if quiz_data and poll_id in quiz_data.get("poll_ids", set()):
        if poll_id not in quiz_data["answered_polls"]:
            quiz_data["answered_polls"].add(poll_id)
            if is_correct:
                quiz_data["score_correct"] += 1
            else:
                quiz_data["score_wrong"] += 1

        # Cuando el usuario responde las 5 preguntas del cuestionario
        if len(quiz_data["answered_polls"]) >= quiz_data["total_polls"]:
            correctas = quiz_data["score_correct"]
            total = quiz_data["total_polls"]
            
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Generar 5 Preguntas Nuevas", callback_data="btn_quiz"),
                    InlineKeyboardButton("💬 Resolver una Duda del PDF", callback_data="btn_duda"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=quiz_data["chat_id"],
                text=(
                    f"🎉 *¡Has completado el cuestionario!*\n\n"
                    f"📊 *Tu puntaje en esta ronda:*\n"
                    f"✅ Aciertos: *{correctas}/{total}*\n"
                    f"❌ Errores: *{total - correctas}/{total}*\n\n"
                    f"🔄 ¿Qué deseas hacer a continuación con este documento?"
                ),
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            # Resetear quiz activo
            context.user_data["active_quiz"] = None

import re

def format_for_telegram(text: str) -> str:
    """Convierte el formato Markdown estándar de la IA al formato compatible con Telegram."""
    if not text:
        return ""
    
    # 1. Convertir encabezados Markdown (### Titulo, ## Titulo, # Titulo) a negritas (*Titulo*)
    text = re.sub(r"^(#{1,6})\s*(.+)$", r"*\2*", text, flags=re.MULTILINE)
    
    # 2. Convertir triple asterisco (***texto***) a asterisco simple (*texto*)
    text = re.sub(r"\*{3,}(.+?)\*{3,}", r"*\1*", text)
    
    # 3. Convertir doble asterisco (**texto**) a asterisco simple (*texto*) para Telegram Markdown
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    
    # 4. Convertir doble guion bajo (__texto__) a asterisco simple (*texto*)
    text = re.sub(r"__(.+?)__", r"*\1*", text)
    
    return text

def split_message(text: str, max_length: int = 4000) -> list[str]:
    """Divide un texto largo en bloques de tamaño máximo respetando saltos de línea."""
    if not text or not str(text).strip():
        return ["⚠️ No se obtuvo una respuesta de la IA. Por favor, intenta de nuevo."]
    
    text = str(text).strip()
    if len(text) <= max_length:
        return [text]
    
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
        
        chunk = remaining[:split_idx].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_idx:].strip()
    return chunks if chunks else ["⚠️ No se obtuvo una respuesta válida."]

async def send_formatted_message(status_msg, update, text: str):
    """Envía o edita mensajes asegurando formato Markdown compatible con Telegram."""
    chunks = split_message(text, max_length=4000)
    
    # Primer bloque edita el mensaje de carga
    first_chunk = chunks[0]
    formatted_first = format_for_telegram(first_chunk)
    try:
        await status_msg.edit_text(formatted_first, parse_mode="Markdown")
    except Exception as parse_err:
        logging.warning(f"Error parseando Markdown en primer bloque: {parse_err}")
        await status_msg.edit_text(first_chunk)
        
    # Bloques siguientes se envían como mensajes nuevos
    for chunk in chunks[1:]:
        formatted_chunk = format_for_telegram(chunk)
        try:
            await update.message.reply_text(formatted_chunk, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(chunk)

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
    user = get_or_create_user(db, user_id, update.effective_user.first_name)
    contexto = user.last_context
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
        await send_formatted_message(status_msg, update, respuesta)
            
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
        await send_formatted_message(status_msg, update, respuesta)
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
    user = get_or_create_user(db, user_id, query.from_user.first_name)
    contexto = user.last_context
    
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
                
            poll_ids = set()
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
                poll_ids.add(message.poll.id)
                poll_record = ActivePoll(poll_id=message.poll.id, correct_option_id=int(q["correct_option_id"]))
                db.add(poll_record)
            db.commit()
            
            # Guardar sesión de cuestionario activo para avisar al completar las 5 preguntas
            context.user_data["active_quiz"] = {
                "chat_id": query.message.chat_id,
                "total_polls": len(quizzes),
                "poll_ids": poll_ids,
                "answered_polls": set(),
                "score_correct": 0,
                "score_wrong": 0
            }
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