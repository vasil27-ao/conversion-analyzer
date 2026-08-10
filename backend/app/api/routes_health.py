from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """Простая проверка, что сервис запущен и отвечает."""
    return {"status": "ok"}
