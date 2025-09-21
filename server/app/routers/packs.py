from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_pack_repository
from ..pack_repository import PackRepository

router = APIRouter(prefix="/v1/packs", tags=["packs"])


@router.get("/latest")
def get_latest_pack(
  region: str = Query(..., description="Region code such as EU or US"),
  repo: PackRepository = Depends(get_pack_repository),
):
  try:
    return repo.get_latest_meta(region)
  except KeyError as exc:  # pragma: no cover - defensive
    raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{version}")
def get_pack_version(version: str, repo: PackRepository = Depends(get_pack_repository)):
  try:
    return repo.get_meta(version)
  except KeyError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
