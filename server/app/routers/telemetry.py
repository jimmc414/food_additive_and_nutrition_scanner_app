from __future__ import annotations

from fastapi import APIRouter, Depends, status

from ..deps import TelemetryBuffer, get_telemetry_buffer
from ..models import TelemetryEventModel

router = APIRouter(prefix="/v1/telemetry", tags=["telemetry"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def ingest(event: TelemetryEventModel, buffer: TelemetryBuffer = Depends(get_telemetry_buffer)):
  buffer.append(event)
  return {"stored": True}
