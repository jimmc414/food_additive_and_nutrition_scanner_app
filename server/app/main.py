from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .deps import get_pack_repository
from .routers import additives, packs, telemetry

@asynccontextmanager
async def lifespan(_: FastAPI):
  repo = get_pack_repository()
  repo.refresh()
  yield


app = FastAPI(title="Nutrition Scanner Backend", version="0.1.0", lifespan=lifespan)
app.include_router(packs.router)
app.include_router(additives.router)
app.include_router(telemetry.router)


@app.get("/healthz")
def healthcheck():
  repo = get_pack_repository()
  return {"status": "ok", "pack_version": repo.payload.version}
