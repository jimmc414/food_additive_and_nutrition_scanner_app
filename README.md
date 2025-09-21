# Nutrition Scanner MVP

A minimal yet functional implementation of the Nutrition Scanner platform. The
project demonstrates how mobile logic, an additive data ETL pipeline, and a
FastAPI backend collaborate to deliver offline additive risk evaluation with an
optionally connected telemetry surface.

The repository is structured so each component can be developed and tested in
isolation while sharing a common pack format. The documentation in
[`requirements.md`](requirements.md), [`architecture.md`](architecture.md), and
[`implementation.md`](implementation.md) captures the full specification that
this slice implements.

## Platform components

| Component | Language | Responsibilities | Key entry points |
| --- | --- | --- | --- |
| Mobile core logic | TypeScript | Parse OCR output, resolve additives, run the risk engine, and expose pure functions suitable for React Native integration. | [`mobile/src/data/parser.ts`](mobile/src/data/parser.ts), [`mobile/src/data/additiveStore.ts`](mobile/src/data/additiveStore.ts), [`mobile/src/risk`](mobile/src/risk) |
| ETL pipeline | Python | Compile CSV source data into a deterministic additive payload, calculate checksums, and produce signed metadata. | [`etl/build_pack.py`](etl/build_pack.py), [`etl/sign_pack.py`](etl/sign_pack.py), [`etl/verify_pack.py`](etl/verify_pack.py) |
| Backend API | Python/FastAPI | Serve pack metadata and additive details, and accept anonymised telemetry events from clients. | [`server/app/main.py`](server/app/main.py), [`server/app/routers`](server/app/routers) |

## Repository layout

```
├── etl/                 # Data compilation and signing pipeline
├── mobile/              # Shareable mobile domain logic with Jest tests
├── server/              # FastAPI application and pytest suite
├── docs/                # Supplemental design documents
├── keys/                # Location for Ed25519 signing keys (public key checked in)
└── requirements.md      # Product requirements driving this MVP
```

## Prerequisites

- **Python 3.10+** with `pip`. A virtual environment is recommended for the ETL
  scripts and FastAPI application.
- **Node.js 18+** and **Yarn** for running the TypeScript tests.
- **PyNaCl** for pack signing and verification (installed via
  `pip install -r etl/requirements.txt`).
- **uvicorn** for serving the backend locally (installed automatically via the
  server extras).

## Environment setup

1. Clone the repository and move into it:

   ```bash
   git clone <repo-url>
   cd food_additive_and_nutrition_scanner_app
   ```

2. Create and activate a Python virtual environment, then install dependencies
   for the ETL and server:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r etl/requirements.txt
   python -m pip install --user -e server[dev]
   ```

3. Install the mobile TypeScript dependencies:

   ```bash
   cd mobile
   yarn install
   cd ..
   ```

4. (Optional) Generate a fresh Ed25519 keypair for signing packs. Store the
   private key outside version control and copy only the public key into
   `keys/public_key.ed25519`:

   ```bash
   python - <<'PY'
   from nacl.signing import SigningKey
   key = SigningKey.generate()
   print(key.encode().hex())              # -> keys/private_key.ed25519
   print(key.verify_key.encode().hex())   # -> keys/public_key.ed25519
   PY
   ```

## Building and signing the additive pack

The ETL reads the CSV sources in `etl/data/` and writes signed output files to
`etl/output/`.

```bash
# Compile the additive payload and metadata
python etl/build_pack.py

# Sign meta.json using the private key at keys/private_key.ed25519
python etl/sign_pack.py

# Confirm the signature using keys/public_key.ed25519
python etl/verify_pack.py
```

`build_pack.py` prints the generated pack version and number of additives. The
signing step fails fast if the checksum does not match or the key is missing.
`verify_pack.py` should be run as a post-signature sanity check before
publishing the pack.

## Running the backend locally

1. Ensure a signed pack exists in `etl/output/`.
2. (Optional) Override defaults via environment variables:
   - `NS_PACK_OUTPUT_DIR` – directory containing `payload.json` and `meta.json`.
   - `NS_TELEMETRY_BUFFER_SIZE` – maximum number of telemetry events retained in
     memory (default `1000`).
3. Launch the FastAPI app with hot reloading:

   ```bash
   uvicorn server.app.main:app --reload
   ```

4. Available endpoints:
   - `GET /healthz` – reports API status and loaded pack version.
   - `GET /v1/packs/latest?region=EU` – returns latest pack metadata for a
     region.
   - `GET /v1/packs/{version}` – metadata for a specific pack version.
   - `GET /v1/additives/{code}` – additive details from the loaded payload.
   - `POST /v1/telemetry` – stores anonymised telemetry events in an in-memory
     buffer.

## Running automated tests

- **Mobile logic**:

  ```bash
  cd mobile
  yarn test --runInBand
  ```

- **Backend API**:

  ```bash
  pytest server/app/tests
  ```

  The tests expect that `etl/output/` already contains a freshly built pack.

## Additional documentation

- [`architecture.md`](architecture.md) – high-level system design.
- [`implementation.md`](implementation.md) – details on this repository's
  approach.
- [`requirements.md`](requirements.md) – product and technical requirements.
- [`docs/`](docs) – alternate formats of the same planning documents.

