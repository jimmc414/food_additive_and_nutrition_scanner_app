from __future__ import annotations

import json
from pathlib import Path

from server.app.pack_repository import PackRepository


def test_refresh_updates_payload_version(tmp_path):
  root = Path(__file__).resolve().parents[3]
  payload_src = root / "etl" / "output" / "payload.json"
  meta_src = root / "etl" / "output" / "meta.json"

  payload_path = tmp_path / "payload.json"
  meta_path = tmp_path / "meta.json"
  payload_path.write_text(payload_src.read_text(encoding="utf-8"), encoding="utf-8")
  meta_path.write_text(meta_src.read_text(encoding="utf-8"), encoding="utf-8")

  repo = PackRepository(payload_path, meta_path)
  original_version = repo.payload.version

  payload_data = json.loads(payload_path.read_text(encoding="utf-8"))
  meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
  new_version = f"{original_version}-test"
  payload_data["version"] = new_version
  meta_data["version"] = new_version
  payload_path.write_text(json.dumps(payload_data, indent=2), encoding="utf-8")
  meta_path.write_text(json.dumps(meta_data, indent=2), encoding="utf-8")

  repo.refresh()

  assert repo.payload.version == new_version
  assert repo.get_meta(new_version).version == new_version
  for region in meta_data["regions"]:
    assert repo.get_latest_meta(region).version == new_version
  assert repo.get_meta(original_version).version == original_version
