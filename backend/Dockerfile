# Browsers in the image must match the installed playwright package version.
# pip may pull a newer playwright than an outdated image tag → "Executable doesn't exist".
FROM mcr.microsoft.com/playwright/python:v1.62.0-jammy

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    SQLITE_PATH=/app/data/analyses.db \
    PORT=8000 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install chromium

COPY app ./app
COPY .env.example ./.env.example

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
