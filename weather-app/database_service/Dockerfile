# Usa un'immagine più leggera di Python
FROM python:3.8-slim

# Imposta il working directory
WORKDIR /app

#Copia solo il file requirements.txt inizialmente
COPY requirements.txt .

# Installa le dipendenze necessarie
RUN pip install --no-cache-dir -r requirements.txt

# Copia tutto il resto dei file
COPY . .

#CMD originale per eseguire l'applicazione
CMD ["python", "app.py"]

