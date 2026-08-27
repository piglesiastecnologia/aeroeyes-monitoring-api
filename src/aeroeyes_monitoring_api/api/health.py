from fastapi import APIRouter

router = APIRouter()


@router.get("/health", summary="Check service liveness")
def get_health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "aeroeyes-monitoring-api",
    }
