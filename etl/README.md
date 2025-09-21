# ETL pipeline

This directory contains a minimal pipeline that compiles the additive CSV sources
into a deterministic JSON payload, signs it with Ed25519, and validates the
signature.

## Usage

```bash
python etl/build_pack.py          # produces output/payload.json + output/meta.json
python etl/sign_pack.py           # signs using keys/private_key.ed25519
python etl/verify_pack.py         # verifies signature using keys/public_key.ed25519
```

The signing step expects a 32-byte Ed25519 private key stored as a hex string at
`keys/private_key.ed25519`. The repository includes only the public key. You can
generate a new pair with:

```bash
python - <<'PY'
from nacl.signing import SigningKey
key = SigningKey.generate()
print(key.encode().hex())              # save to keys/private_key.ed25519
print(key.verify_key.encode().hex())   # save to keys/public_key.ed25519
PY
```

## Data sources

The CSV files in `data/` describe additives, synonyms, references, and
region-specific rules. They are combined into a pack following the schema used
by the mobile client.
