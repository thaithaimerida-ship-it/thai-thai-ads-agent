FROM python:3.11.9-slim-bullseye

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

RUN groupadd --system appuser \
    && useradd --system --gid appuser --home-dir /app --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data \
    && chown appuser:appuser /app/data

# Cloud Run injects PORT — default 8080
ENV PORT=8080

USER appuser

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
