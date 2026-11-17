from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/version")
def get_version() -> dict[str, str]:
    return {"version": "0.1.0"}
