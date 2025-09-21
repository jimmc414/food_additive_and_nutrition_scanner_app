from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass
class Settings:
  pack_output_dir: Path
  telemetry_buffer_size: int = 1000

  @classmethod
  def from_env(cls) -> "Settings":
    base_dir = Path(__file__).resolve().parents[2]
    pack_dir = os.getenv("NS_PACK_OUTPUT_DIR")
    telemetry = os.getenv("NS_TELEMETRY_BUFFER_SIZE")
    pack_path = Path(pack_dir).expanduser() if pack_dir else base_dir / "etl" / "output"
    buffer_size = int(telemetry) if telemetry else 1000
    return cls(pack_output_dir=pack_path, telemetry_buffer_size=buffer_size)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
  return Settings.from_env()
