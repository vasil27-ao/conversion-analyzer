# Анализатор конверсионности страниц

Сервис принимает URL страницы, собирает данные через Playwright, оценивает конверсионность AI-агентом (Gemini) по зафиксированной методике и показывает отчёт с беклогом задач.

Статус: этапы 1–5 по ТЗ выполнены. Контекст — `PROJECT_CONTEXT.md`, решения — `docs/decisions.md`.

## Структура

- `backend/` — FastAPI, Playwright, SQLite, Gemini
- `frontend/` — Vite + React + TypeScript
- `docs/` — ТЗ (копия), методика, решения

## Локальный запуск

### Backend

```bash
cd backend
python -m venv .venv

# Windows PowerShell:
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env
# заполнить GEMINI_API_KEY
# для реального агента: AGENT_IMPL=gemini

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Проверка: `http://127.0.0.1:8000/api/health` → `{"status":"ok"}`.

### Frontend

В другом терминале:

```bash
cd frontend
npm install
npm run dev
```

Открыть: `http://127.0.0.1:5173`.

Dev-сервер проксирует `/api` на backend. Для прямых запросов можно задать `VITE_API_BASE=http://127.0.0.1:8000` в `frontend/.env` (см. `frontend/.env.example`).

## Переменные окружения

### Backend (`backend/.env`, не коммитить)

| Переменная | Назначение |
|---|---|
| `GEMINI_API_KEY` | ключ Gemini (секрет) |
| `AGENT_IMPL` | `gemini` или `mock` |
| `GEMINI_MODEL` | опционально, по умолчанию `gemini-3.6-flash` |
| `SQLITE_PATH` | путь к SQLite |
| `CORS_ORIGINS` | origins через запятую (локальный Vite + URL Vercel) |
| `APP_ENV` | `development` / `production` |

Шаблон: `backend/.env.example`.

### Frontend

| Переменная | Назначение |
|---|---|
| `VITE_API_BASE` | базовый URL backend без `/` в конце; локально можно пустым (proxy) |

## Деплой

- **Frontend** → [Vercel](https://vercel.com): Root Directory = `frontend`, переменная `VITE_API_BASE` = URL production backend.
- **Backend** → [Railway](https://railway.app) (Docker + Playwright Chromium). Vercel для backend не подходит: нужен долгоживущий Python-процесс и Chromium.

Подробности запуска backend на Railway и связки CORS — в `backend/README.md`.

## Тесты backend

```bash
cd backend
.\.venv\Scripts\Activate.ps1
pytest
```
