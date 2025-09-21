from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReferenceModel(BaseModel):
  id: str
  label: str
  url: str


class RegionRuleModel(BaseModel):
  id: str
  type: str
  summary: str
  audience: List[str] = Field(default_factory=list)
  referenceIds: List[str] = Field(default_factory=list)
  condition: Optional[str] = None
  severity: Optional[str] = None
  diet: Optional[str] = None
  approved: Optional[bool] = None


class AdditiveModel(BaseModel):
  code: str
  names: List[str]
  class_: str = Field(alias="class")
  evidence_level: str
  plain_summary: str
  dietary: Dict[str, bool]
  source: Dict[str, bool]
  population_cautions: List[RegionRuleModel] = Field(default_factory=list)
  region_rules: Dict[str, List[RegionRuleModel]]
  references: List[ReferenceModel]

  model_config = ConfigDict(populate_by_name=True)


class PackPayloadModel(BaseModel):
  version: str
  generated_at: datetime
  checksum: str
  additives: List[AdditiveModel]
  alias_index: Dict[str, str]


class PackMetaModel(BaseModel):
  version: str
  regions: List[str]
  checksum: str
  signature: Optional[str]
  diff_from: Optional[str]


class TelemetryEventModel(BaseModel):
  event: str
  timestamp: datetime
  platform: Optional[str] = None
  region: Optional[str] = None
  payload: Dict[str, object] = Field(default_factory=dict)

  @field_validator("event")
  @classmethod
  def validate_event(cls, value: str) -> str:  # noqa: D401
    """Ensure event names match expected patterns."""
    if not value:
      raise ValueError("event must not be empty")
    return value
