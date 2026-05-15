"""Health check endpoint — no authentication required."""
from fastapi import APIRouter

router = APIRouter()

_VERSION = "0.2.0"


@router.get("/api/health")
async def health():
    """Liveness probe. Returns service status and version."""
    return {"status": "ok", "version": _VERSION}
