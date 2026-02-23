# 1. Utilisation d'une image Python légère
FROM python:3.11-slim

# 2. Définition du répertoire de travail
WORKDIR /

# 3. Installation des dépendances système nécessaires (si tu utilises curl_cffi ou des outils de build)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    librandr2 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 2. Installer Chromium via Playwright
RUN playwright install chromium
RUN playwright install-deps chromium

# 4. Copie des fichiers de dépendances en premier (optimisation du cache Docker)
COPY requirements.txt .

# 5. Installation des dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# 6. Création du dossier data pour la persistance des parties
# Comme vu dans ton code, le backend écrit des fichiers .json
RUN mkdir -p /app/data/games
RUN mkdir -p /app/data/sessions

# 7. Copie de l'intégralité du code source
COPY . /backend

# 8. Exposition du port utilisé par FastAPI (par défaut 8000)
EXPOSE 8000

WORKDIR /backend

ENV PYTHONPATH=/backend
# 9. Commande de lancement avec Uvicorn
# On utilise 0.0.0.0 pour que le container soit accessible depuis le proxy Nginx
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]