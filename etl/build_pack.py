"""Builds the additive payload JSON from CSV sources."""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

@dataclass
class AdditiveRow:
  code: str
  additive_class: str
  evidence_level: str
  plain_summary: str
  dietary: Dict[str, bool]
  source: Dict[str, bool]
  names: List[str] = field(default_factory=list)
  references: List[Dict[str, str]] = field(default_factory=list)
  region_rules: Dict[str, List[Dict[str, object]]] = field(default_factory=dict)


def _to_bool(value: str) -> bool:
  return value.strip().lower() in {"1", "true", "yes"}


def _read_additives() -> Dict[str, AdditiveRow]:
  additives: Dict[str, AdditiveRow] = {}
  with (DATA_DIR / "additives.csv").open(newline="", encoding="utf-8") as handle:
    reader = csv.DictReader(handle)
    for row in reader:
      code = row["code"].strip().upper()
      additives[code] = AdditiveRow(
        code=code,
        additive_class=row["class"].strip(),
        evidence_level=row["evidence_level"].strip(),
        plain_summary=row["plain_summary"].strip(),
        dietary={
          "vegan": _to_bool(row["dietary_vegan"]),
          "vegetarian": _to_bool(row["dietary_vegetarian"]),
          "kosher": _to_bool(row["dietary_kosher"]),
          "halal": _to_bool(row["dietary_halal"]),
        },
        source={
          "animal": _to_bool(row["source_animal"]),
          "insect": _to_bool(row["source_insect"]),
          "plant": _to_bool(row["source_plant"]),
          "synthetic": _to_bool(row["source_synthetic"]),
        },
      )
  return additives


def _read_synonyms(additives: Dict[str, AdditiveRow]) -> Dict[str, str]:
  alias_index: Dict[str, str] = {}
  with (DATA_DIR / "synonyms.csv").open(newline="", encoding="utf-8") as handle:
    reader = csv.DictReader(handle)
    for row in reader:
      code = row["code"].strip().upper()
      if code not in additives:
        raise ValueError(f"Synonym references unknown code {code}")
      name = row["name"].strip().upper()
      additives[code].names.append(name)
      alias_index[name] = code
  for code, additive in additives.items():
    additive.names.append(code)
    alias_index[code] = code
    additive.names = sorted(set(additive.names))
  return alias_index


def _read_references(additives: Dict[str, AdditiveRow]) -> None:
  with (DATA_DIR / "references.csv").open(newline="", encoding="utf-8") as handle:
    reader = csv.DictReader(handle)
    for row in reader:
      code = row["code"].strip().upper()
      if code not in additives:
        raise ValueError(f"Reference references unknown code {code}")
      additives[code].references.append(
        {
          "id": row["reference_id"].strip(),
          "label": row["label"].strip(),
          "url": row["url"].strip(),
        }
      )


def _parse_audience(value: str) -> List[str]:
  if not value:
    return []
  return [item.strip().title() for item in value.split("|") if item.strip()]


def _read_region_rules(additives: Dict[str, AdditiveRow]) -> None:
  with (DATA_DIR / "region_rules.csv").open(newline="", encoding="utf-8") as handle:
    reader = csv.DictReader(handle)
    for row in reader:
      code = row["code"].strip().upper()
      if code not in additives:
        raise ValueError(f"Region rule references unknown code {code}")
      region = row["region"].strip().upper()
      audience = _parse_audience(row["audience"].strip()) if row["audience"] else []
      reference_ids = [item.strip() for item in row["reference_ids"].split("|") if item.strip()]
      rule_type = row["type"].strip()
      rule: Dict[str, object]
      if rule_type == "regulatory_warning":
        rule = {
          "id": row["rule_id"].strip(),
          "type": "regulatory_warning",
          "summary": row["summary"].strip(),
          "audience": audience,
          "referenceIds": reference_ids,
        }
      elif rule_type == "population_caution":
        rule = {
          "id": row["rule_id"].strip(),
          "type": "population_caution",
          "summary": row["summary"].strip(),
          "audience": audience,
          "condition": row["diet_or_condition"].strip().lower(),
          "severity": row["severity"].strip().lower(),
          "referenceIds": reference_ids,
        }
      elif rule_type == "diet_conflict":
        rule = {
          "id": row["rule_id"].strip(),
          "type": "diet_conflict",
          "summary": row["summary"].strip(),
          "audience": audience,
          "diet": row["diet_or_condition"].strip().lower(),
          "referenceIds": reference_ids,
        }
      elif rule_type == "evidence_annotation":
        rule = {
          "id": row["rule_id"].strip(),
          "type": "evidence_annotation",
          "summary": row["summary"].strip(),
          "audience": audience,
          "severity": row["severity"].strip().lower(),
          "referenceIds": reference_ids,
        }
      elif rule_type == "region_approval":
        rule = {
          "id": row["rule_id"].strip(),
          "type": "region_approval",
          "summary": row["summary"].strip(),
          "audience": audience,
          "approved": row["severity"].strip().lower() != "red",
          "referenceIds": reference_ids,
        }
      else:
        raise ValueError(f"Unknown rule type {rule_type}")

      additive = additives[code]
      additive.region_rules.setdefault(region, []).append(rule)

  for additive in additives.values():
    for rules in additive.region_rules.values():
      rules.sort(key=lambda entry: entry["id"])  # type: ignore[index]


def build_pack() -> None:
  OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

  additives = _read_additives()
  alias_index = _read_synonyms(additives)
  _read_references(additives)
  _read_region_rules(additives)

  version = datetime.now(timezone.utc).strftime("%Y.%m.%d")
  generated_at = datetime.now(timezone.utc).isoformat()

  additives_payload = [
    {
      "code": additive.code,
      "names": additive.names,
      "class": additive.additive_class,
      "evidence_level": additive.evidence_level,
      "plain_summary": additive.plain_summary,
      "dietary": additive.dietary,
      "source": additive.source,
      "population_cautions": [],
      "region_rules": additive.region_rules,
      "references": additive.references,
    }
    for additive in sorted(additives.values(), key=lambda item: item.code)
  ]

  payload = {
    "version": version,
    "generated_at": generated_at,
    "additives": additives_payload,
    "alias_index": dict(sorted(alias_index.items())),
  }

  serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
  checksum = hashlib.sha256(serialized).hexdigest()
  payload["checksum"] = checksum

  (OUTPUT_DIR / "payload.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

  regions = sorted({region for additive in additives_payload for region in additive["region_rules"].keys()})
  meta = {
    "version": version,
    "regions": regions,
    "checksum": checksum,
    "signature": None,
    "diff_from": None,
  }
  (OUTPUT_DIR / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
  print(f"Built pack version {version} with {len(additives_payload)} additives")


if __name__ == "__main__":
  build_pack()
