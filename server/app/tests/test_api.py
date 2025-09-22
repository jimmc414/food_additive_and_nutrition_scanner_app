from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from etl import build_pack
from server.app.deps import get_pack_repository, get_telemetry_buffer
from server.app.main import app
from server.app.settings import get_settings


def setup_module(_: object) -> None:
  build_pack.build_pack()
  get_pack_repository().refresh()
  get_telemetry_buffer().clear()


def test_pack_endpoints():
  client = TestClient(app)

  latest = client.get("/v1/packs/latest", params={"region": "EU"})
  assert latest.status_code == 200
  data = latest.json()
  assert "checksum" in data
  version = data["version"]

  same = client.get(f"/v1/packs/{version}")
  assert same.status_code == 200
  assert same.json()["version"] == version

  additive = client.get("/v1/additives/E102")
  assert additive.status_code == 200
  additive_data = additive.json()
  assert additive_data["code"] == "E102"
  assert additive_data["class"] == "Colour"


def test_telemetry_ingest():
  client = TestClient(app)
  payload = {
    "event": "scan_completed",
    "timestamp": datetime.now(UTC).isoformat(),
    "platform": "ios",
    "region": "EU",
    "payload": {"additives": 3, "flags": 1},
  }
  response = client.post("/v1/telemetry", json=payload)
  assert response.status_code == 202
  buffer = get_telemetry_buffer()
  assert buffer.items
  assert buffer.items[-1].event == "scan_completed"


def test_healthcheck():
  client = TestClient(app)
  settings = get_settings()
  repo = get_pack_repository()
  payload_path = settings.pack_output_dir / "payload.json"
  meta_path = settings.pack_output_dir / "meta.json"
  original_payload = payload_path.read_text(encoding="utf-8")
  original_meta = meta_path.read_text(encoding="utf-8")
  payload_data = json.loads(original_payload)
  meta_data = json.loads(original_meta)
  original_version = payload_data["version"]
  new_version = f"{original_version}-health"
  payload_data["version"] = new_version
  meta_data["version"] = new_version
  payload_path.write_text(json.dumps(payload_data, indent=2), encoding="utf-8")
  meta_path.write_text(json.dumps(meta_data, indent=2), encoding="utf-8")
  try:
    repo.refresh()
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["pack_version"] == new_version
    assert repo.payload.version == new_version
  finally:
    payload_path.write_text(original_payload, encoding="utf-8")
    meta_path.write_text(original_meta, encoding="utf-8")
    repo.refresh()
