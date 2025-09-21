from __future__ import annotations

from functools import lru_cache
from typing import List

from .models import TelemetryEventModel
from .pack_repository import PackRepository
from .settings import get_settings


@lru_cache(maxsize=1)
def get_pack_repository() -> PackRepository:
  settings = get_settings()
  return PackRepository(settings.pack_output_dir / "payload.json", settings.pack_output_dir / "meta.json")


class TelemetryBuffer:
  """Simple in-memory telemetry buffer for demo purposes."""

  def __init__(self, max_size: int) -> None:
    self._max_size = max_size
    self._items: List[TelemetryEventModel] = []

  def append(self, event: TelemetryEventModel) -> None:
    self._items.append(event)
    if len(self._items) > self._max_size:
      self._items.pop(0)

  @property
  def items(self) -> List[TelemetryEventModel]:
    return list(self._items)

  def clear(self) -> None:
    self._items.clear()


@lru_cache(maxsize=1)
def get_telemetry_buffer() -> TelemetryBuffer:
  settings = get_settings()
  return TelemetryBuffer(settings.telemetry_buffer_size)
