# Backend — Анализатор конверсионности страниц

Стек: Python, FastAPI, Playwright (DOM/layout без скриншотов), SQLite, Gemini.

## API

- `GET /api/health`
- `POST /api/analyses` — тело `{"url":"https://..."}`
- `GET /api/analyses/{id}` — статус и результат (`url` в ответе)

## Локальный запуск

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env
# заполнить GEMINI_API_KEY; AGENT_IMPL=gemini

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

CORS по умолчанию разрешён для локального Vite (`5173` / `4173`). Список задаётся `CORS_ORIGINS`.

## Деплой на Railway (рекомендуется)

Почему не Vercel: Playwright Chromium и длительный анализ не укладываются в serverless-модель Vercel. Railway запускает Docker-образ с уже установленным Chromium (`mcr.microsoft.com/playwright/python`), даёт достаточно RAM и простой деплой из GitHub.

1. Создайте проект на [railway.app](https://railway.app), подключите этот GitHub-репозиторий.
2. Root Directory / service path: `backend` (рядом лежат `Dockerfile` и `railway.toml`).
3. Задайте переменные окружения:
   - `GEMINI_API_KEY` — секрет
   - `AGENT_IMPL=gemini`
   - `APP_ENV=production`
   - `CORS_ORIGINS` — локальные origins + `https://<ваш-frontend>.vercel.app`
   - `SQLITE_PATH=/app/data/analyses.db` (уже в Dockerfile)
4. Включите публичный HTTP-домен сервиса (Generate Domain).
5. Проверьте `GET https://<backend>/api/health`.

После появления URL Vercel добавьте его в `CORS_ORIGINS` и перезапустите сервис.

## Тесты

```bash
pytest
```
