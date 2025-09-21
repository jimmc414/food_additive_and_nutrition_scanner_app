from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from etl import build_pack
from server.app.deps import get_pack_repository, get_telemetry_buffer
from server.app.main import app


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
  resp = client.get("/healthz")
  assert resp.status_code == 200
  body = resp.json()
  assert body["status"] == "ok"
  assert "pack_version" in body
