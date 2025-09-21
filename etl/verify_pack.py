"""Verifies the pack signature using the stored public key."""
from __future__ import annotations

import binascii
import json
from pathlib import Path

from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
KEYS_DIR = ROOT.parent / "keys"


class VerificationError(RuntimeError):
  pass


def _load_public_key(path: Path) -> VerifyKey:
  if not path.exists():
    raise VerificationError(f"Public key not found at {path}")
  data = path.read_text(encoding="utf-8").strip()
  try:
    key_bytes = binascii.unhexlify(data)
  except binascii.Error as exc:  # pragma: no cover - defensive
    raise VerificationError("Public key must be hex encoded") from exc
  if len(key_bytes) != 32:
    raise VerificationError("Ed25519 public keys must be 32 bytes")
  return VerifyKey(key_bytes)


def verify_pack(public_key_path: Path | None = None) -> bool:
  meta_path = OUTPUT_DIR / "meta.json"
  payload_path = OUTPUT_DIR / "payload.json"
  if not meta_path.exists() or not payload_path.exists():
    raise VerificationError("Pack payload and meta not found. Run build_pack.py first.")

  meta = json.loads(meta_path.read_text(encoding="utf-8"))
  payload = json.loads(payload_path.read_text(encoding="utf-8"))

  checksum = payload.get("checksum")
  signature_hex = meta.get("signature")
  if not checksum or not signature_hex:
    raise VerificationError("Checksum or signature missing")
  if checksum != meta.get("checksum"):
    raise VerificationError("Checksum mismatch between payload and meta")

  verify_key = _load_public_key(public_key_path or (KEYS_DIR / "public_key.ed25519"))
  try:
    verify_key.verify(binascii.unhexlify(checksum), binascii.unhexlify(signature_hex))
  except BadSignatureError as exc:
    raise VerificationError("Signature verification failed") from exc

  print(f"Verified pack {meta['version']} with checksum {checksum[:16]}…")
  return True


if __name__ == "__main__":
  verify_pack()
