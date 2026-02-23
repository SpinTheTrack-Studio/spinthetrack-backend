# 1. Image de base
FROM python:3.13-slim

WORKDIR /app

# 2. Installation des dépendances de base
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 3. Installation des dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Création des dossiers data
RUN mkdir -p /app/data/games /app/data/sessions

# 6. Copie du code
COPY . .

# 7. Setup environnement
ENV PYTHONPATH=/app
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]