# Frontend — Анализатор конверсионности страниц

Frontend MVP (этап 4): форма URL → ожидание → отчёт → скачивание HTML.

Стек: Vite, React, TypeScript. Без UI-библиотек.

## Запуск

Нужен запущенный backend на `http://127.0.0.1:8000`.

```bash
npm install
npm run dev
```

Открыть: `http://127.0.0.1:5173`.

Dev-сервер проксирует `/api` на backend. CORS на backend также разрешён для портов 5173/4173.

Опционально: скопируйте `.env.example` → `.env` и задайте `VITE_API_BASE=http://127.0.0.1:8000` для прямых запросов без proxy.

## Деплой на Vercel

1. Импортируйте репозиторий в Vercel.
2. Root Directory: `frontend`.
3. Framework Preset: Vite (или оставьте авто).
4. Environment Variable: `VITE_API_BASE` = URL production backend без завершающего `/` (например `https://....up.railway.app`).
5. Deploy. После первого деплоя добавьте URL Vercel в `CORS_ORIGINS` на backend.

## Сценарий

1. Ввод публичного URL и базовая валидация.
2. `POST /api/analyses` → polling `GET /api/analyses/{id}` каждые 2 с.
3. Экран отчёта: overall, 6 блоков, problems, backlog.
4. Скачивание standalone HTML-отчёта (из уже сохранённого результата).
5. «Новый анализ» возвращает к форме.
