FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# L'API tourne sans droits root (uid 1000 = l'utilisateur habituel sur Ubuntu : il peut lire secrets/).
RUN useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin wallet
USER 1000

EXPOSE 8000
# Applique les migrations puis démarre l'API.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-server-header"]
