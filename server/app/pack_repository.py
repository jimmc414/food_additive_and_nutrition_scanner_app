from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from .models import AdditiveModel, PackMetaModel, PackPayloadModel


class PackRepository:
  """Loads pack payloads from disk and exposes query helpers."""

  def __init__(self, payload_path: Path, meta_path: Path) -> None:
    self._payload_path = payload_path
    self._meta_path = meta_path
    self._meta_by_version: Dict[str, PackMetaModel] = {}
    self._payload_by_version: Dict[str, PackPayloadModel] = {}
    self._additive_index: Dict[str, AdditiveModel] = {}
    self._region_latest: Dict[str, PackMetaModel] = {}
    self.refresh()

  def refresh(self) -> None:
    payload = PackPayloadModel.model_validate_json(self._payload_path.read_text(encoding="utf-8"))
    meta = PackMetaModel.model_validate_json(self._meta_path.read_text(encoding="utf-8"))
    self._payload_by_version[payload.version] = payload
    self._meta_by_version[meta.version] = meta
    self._region_latest = {region.upper(): meta for region in meta.regions}
    self._additive_index = {item.code: item for item in payload.additives}

  def get_latest_meta(self, region: str) -> PackMetaModel:
    region_key = region.upper()
    if region_key not in self._region_latest:
      raise KeyError(f"Region {region} not available")
    return self._region_latest[region_key]

  def get_meta(self, version: str) -> PackMetaModel:
    if version not in self._meta_by_version:
      raise KeyError(f"Unknown pack version {version}")
    return self._meta_by_version[version]

  def get_additive(self, code: str) -> Optional[AdditiveModel]:
    return self._additive_index.get(code.upper())

  @property
  def payload(self) -> PackPayloadModel:
    return next(iter(self._payload_by_version.values()))
