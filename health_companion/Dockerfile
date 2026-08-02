FROM python:3.12-slim

WORKDIR /app

# Install deps first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The SQLite DB lives here; mount a volume to persist it (see docker-compose.yml).
ENV DATABASE_PATH=/data/health_companion.db
VOLUME ["/data"]

CMD ["python", "bot.py"]
