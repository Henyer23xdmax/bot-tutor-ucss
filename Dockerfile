FROM python:3.11-slim

# Evita que Python guarde logs en buffer
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo el código del bot
COPY . .

# Comando para arrancar el bot
CMD ["python", "main.py"]
