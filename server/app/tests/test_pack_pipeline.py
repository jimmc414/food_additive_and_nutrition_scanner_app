from __future__ import annotations

from pathlib import Path

from nacl.signing import SigningKey

from etl import build_pack, sign_pack, verify_pack

OUTPUT_DIR = Path(__file__).resolve().parents[3] / "etl" / "output"


def test_build_sign_verify(tmp_path):
  build_pack.build_pack()
  assert (OUTPUT_DIR / "payload.json").exists()
  assert (OUTPUT_DIR / "meta.json").exists()

  signing_key = SigningKey.generate()
  private_path = tmp_path / "private_key.ed25519"
  public_path = tmp_path / "public_key.ed25519"
  private_path.write_text(signing_key.encode().hex(), encoding="utf-8")
  public_path.write_text(signing_key.verify_key.encode().hex(), encoding="utf-8")

  meta_path = OUTPUT_DIR / "meta.json"
  original_meta = meta_path.read_text(encoding="utf-8")
  try:
    sign_pack.sign_pack(private_key_path=private_path)
    meta_data = meta_path.read_text(encoding="utf-8")
    assert '"signature"' in meta_data
    assert verify_pack.verify_pack(public_key_path=public_path)
  finally:
    meta_path.write_text(original_meta, encoding="utf-8")
