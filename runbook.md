# Nutrition Scanner Runbook

This runbook documents the operational procedures for the Nutrition Scanner MVP
stack. It targets engineers who own data pack generation, backend operations,
and mobile logic validation. Follow the steps below before shipping a new pack or
debugging issues in any environment (local, staging, or production).

## Quick reference

| Topic | Commands / Files |
| --- | --- |
| Build additive pack | `python etl/build_pack.py` |
| Sign metadata | `python etl/sign_pack.py` (needs `keys/private_key.ed25519`) |
| Verify signature | `python etl/verify_pack.py` |
| Run backend tests | `pytest server/app/tests` |
| Run mobile tests | `cd mobile && yarn test --runInBand` |
| Launch API locally | `uvicorn server.app.main:app --reload` |
| Health check | `curl http://localhost:8000/healthz` |

## 1. Prerequisites

- Python **3.10 or newer** with the following packages installed inside a
  virtual environment:
  - `pip install -r etl/requirements.txt`
  - `python -m pip install --user -e server[dev]`
- Node.js **18+** with Yarn (`corepack enable` or install via package manager).
- Access to the **Ed25519 private key** that matches the checked-in public key at
  `keys/public_key.ed25519`. Store the private key outside of Git.
- File system access to the repository so that generated packs can be written to
  `etl/output/` and read by the server.

## 2. Data pack lifecycle

### 2.1 Refresh cadence

Regenerate the pack whenever:

- source CSV files in `etl/data/` change,
- a new region is added,
- or a new production deployment is cut.

### 2.2 Build

1. Activate the Python virtual environment.
2. Run the ETL build script:

   ```bash
   python etl/build_pack.py
   ```

   - Output: `etl/output/payload.json` and `etl/output/meta.json`.
   - The script prints the new version (UTC date) and additive count. Capture the
     version string for release notes.

### 2.3 Sign

1. Ensure `keys/private_key.ed25519` contains a 32-byte Ed25519 private key in
   hex.
2. Sign the pack metadata:

   ```bash
   python etl/sign_pack.py
   ```

   - Fails if `meta.json` or `payload.json` are missing or if checksums differ.
   - Updates the `signature` field in `meta.json`.

### 2.4 Verify

Run the verification script before publishing:

```bash
python etl/verify_pack.py
```

- Uses `keys/public_key.ed25519` to confirm the signature.
- Halts with a descriptive error if the checksum or signature are invalid.

### 2.5 Distribute

- Copy both `payload.json` and `meta.json` (with signature) to the deployment
  artifact or storage bucket used by the backend.
- If the backend runs on another host, set the `NS_PACK_OUTPUT_DIR` environment
  variable to point at the directory containing these files.

### 2.6 Key management

- Rotate keys by generating a fresh pair using the Python snippet in the README.
- Distribute the new public key to all environments before signing with the new
  private key to prevent verification failures.
- Retire old private keys securely once all environments confirm the new
  signature.

## 3. Backend operations

### 3.1 Configuration

Environment variables consumed by `server/app/settings.py`:

- `NS_PACK_OUTPUT_DIR` – absolute or relative path to the directory that holds
  `payload.json` and `meta.json`. Defaults to `<repo>/etl/output`.
- `NS_TELEMETRY_BUFFER_SIZE` – integer cap on in-memory telemetry events.
  Default is `1000`.

### 3.2 Local launch

1. Confirm the pack files exist in the configured directory.
2. Start the server:

   ```bash
   uvicorn server.app.main:app --reload
   ```

3. Validate availability:

   ```bash
   curl http://localhost:8000/healthz
   curl "http://localhost:8000/v1/packs/latest?region=EU"
   curl http://localhost:8000/v1/additives/E100
   ```

4. Inspect telemetry ingestion (stored in memory for demo purposes):

   ```bash
   curl -X POST http://localhost:8000/v1/telemetry \
     -H 'Content-Type: application/json' \
     -d '{"session_id":"demo","events":[{"type":"scan","region":"EU"}]}'
   ```

   The endpoint responds with `{ "stored": true }`. The buffer is cleared when
   the process restarts.

### 3.3 Deployment checklist

Before deploying or restarting the backend:

1. Rebuild, sign, and verify the data pack.
2. Run the automated tests:

   ```bash
   pytest server/app/tests
   cd mobile && yarn test --runInBand && cd ..
   ```

3. Record the new pack version from `etl/output/meta.json`.
4. Update environment variables if the pack directory or telemetry buffer size
   changes.
5. Restart the FastAPI process (e.g., systemd service or container).
6. Re-run the health checks after deployment.

## 4. Monitoring and diagnostics

### 4.1 Health checks

- `GET /healthz` returns `{ "status": "ok", "pack_version": "<version>" }`.
  Ensure the reported version matches the freshly generated pack.
- `GET /v1/packs/latest?region=<REGION>` surfaces region availability errors in
  the HTTP response. A `404` indicates the requested region is absent from the
  metadata (likely a data pipeline issue).

### 4.2 Logs

- `uvicorn` logs requests and errors to stdout/stderr. Capture them via your
  process manager (systemd journald, container logs, etc.).
- Validation failures in the ETL scripts raise explicit `RuntimeError`
  subclasses (`SigningError`, `VerificationError`). Retain command output when
  debugging failures.

### 4.3 Telemetry buffer

- Telemetry events are stored only in memory via
  `server/app/deps.py::TelemetryBuffer`. They are not persisted. For production
  readiness, plan to swap this for a durable queue or database.
- The buffer evicts the oldest events once `NS_TELEMETRY_BUFFER_SIZE` is
  exceeded.

## 5. Troubleshooting

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| `sign_pack.py` reports "Private key not found" | Missing `keys/private_key.ed25519` | Place the private key file (hex encoded) at the expected path or pass a custom path to `sign_pack.sign_pack(Path(...))`. |
| `verify_pack.py` fails with "Signature verification failed" | Signature mismatch or wrong public key | Ensure the signing step was run after the latest build and that the public key matches the private key used for signing. |
| API `GET /v1/packs/latest` returns 500 | Pack files missing or unreadable | Confirm `NS_PACK_OUTPUT_DIR` is correct and that `payload.json` + `meta.json` are readable by the process. Rebuild the pack if files are corrupted. |
| Tests in `server/app/tests` fail because of missing pack | ETL not run before tests | Execute `python etl/build_pack.py` and `python etl/sign_pack.py` prior to running pytest. |
| Telemetry POST returns 500 | JSON payload malformed | Validate request body against `server/app/models.py::TelemetryEventModel`. Ensure fields like `session_id`, `events`, and nested attributes are provided. |

## 6. Appendix

- **Data sources:** CSV inputs live in `etl/data/`. Keep region and reference IDs
  consistent when editing to avoid ETL validation errors.
- **Models:** Pydantic models in `server/app/models.py` define the wire format for
  API responses and telemetry ingestion.
- **Code ownership:**
  - ETL scripts – Data engineering team.
  - Server – Backend/API team.
  - Mobile logic – Mobile platform team.

Keep this runbook updated as the platform evolves. Changes to infrastructure,
external dependencies, or operational tooling should be reflected here.
