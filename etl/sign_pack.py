"""Signs the generated pack metadata using an Ed25519 private key."""
from __future__ import annotations

import binascii
import json
from pathlib import Path

from nacl.signing import SigningKey

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
KEYS_DIR = ROOT.parent / "keys"


class SigningError(RuntimeError):
  pass


def _load_private_key(path: Path) -> SigningKey:
  if not path.exists():
    raise SigningError(
      f"Private key not found at {path}. Generate a key using 'python -m nacl.public' or 'generate_keys.py'."
    )
  data = path.read_text(encoding="utf-8").strip()
  try:
    key_bytes = binascii.unhexlify(data)
  except binascii.Error as exc:  # pragma: no cover - defensive
    raise SigningError("Private key must be hex encoded") from exc
  if len(key_bytes) != 32:
    raise SigningError("Ed25519 private keys must be 32 bytes")
  return SigningKey(key_bytes)


def sign_pack(private_key_path: Path | None = None) -> Path:
  meta_path = OUTPUT_DIR / "meta.json"
  payload_path = OUTPUT_DIR / "payload.json"
  if not meta_path.exists() or not payload_path.exists():
    raise SigningError("Run build_pack.py before signing")

  meta = json.loads(meta_path.read_text(encoding="utf-8"))
  payload = json.loads(payload_path.read_text(encoding="utf-8"))

  checksum = payload.get("checksum")
  if not checksum or checksum != meta.get("checksum"):
    raise SigningError("Checksum mismatch between payload and meta")

  key_path = private_key_path or (KEYS_DIR / "private_key.ed25519")
  signing_key = _load_private_key(key_path)

  signature = signing_key.sign(binascii.unhexlify(checksum)).signature
  meta["signature"] = signature.hex()
  meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
  print(f"Signed pack {meta['version']} -> {meta['signature'][:16]}…")
  return meta_path


if __name__ == "__main__":
  sign_pack()
