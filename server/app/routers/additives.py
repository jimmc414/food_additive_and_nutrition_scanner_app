from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_pack_repository
from ..pack_repository import PackRepository

router = APIRouter(prefix="/v1/additives", tags=["additives"])


@router.get("/{code}")
def get_additive(code: str, repo: PackRepository = Depends(get_pack_repository)):
  additive = repo.get_additive(code)
  if not additive:
    raise HTTPException(status_code=404, detail=f"Additive {code} not found")
  return additive
