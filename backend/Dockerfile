# Official Playwright Python image: Chromium and system deps included.
# Pin major.minor close to requirements.txt (playwright>=1.45,<2.0).
FROM mcr.microsoft.com/playwright/python:v1.51.0-jammy

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    SQLITE_PATH=/app/data/analyses.db \
    PORT=8000

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY .env.example ./.env.example

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
