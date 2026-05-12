"""Config criteria endpoint — serves classification criteria from JSON config files."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.middleware.auth import require_api_key

_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
_FRAMEWORK_FILES = {
    "acgs_snv": _CONFIG_DIR / "acgs-snv-criteria.json",
    "svig": _CONFIG_DIR / "svig-criteria.json",
}

router = APIRouter(prefix="/api/config", dependencies=[Depends(require_api_key)])


@router.get("/criteria/{framework}")
async def get_criteria(framework: str):
    """Return criteria list and combination rules for a supported classification framework."""
    path = _FRAMEWORK_FILES.get(framework)
    if not path:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown framework: {framework!r}. Supported: {list(_FRAMEWORK_FILES)}",
        )
    return json.loads(path.read_text())
