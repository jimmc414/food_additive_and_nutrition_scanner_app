# Nutrition scanner backend

A FastAPI application that serves signed additive packs and accepts anonymised
telemetry events.

## Endpoints

- `GET /v1/packs/latest?region=EU|US` – returns the most recent pack metadata
  for the region.
- `GET /v1/packs/{version}` – returns the metadata for a specific pack version.
- `GET /v1/additives/{code}` – returns a single additive entry from the installed
  pack data.
- `POST /v1/telemetry` – stores anonymised client telemetry payloads.

## Running locally

```bash
uvicorn server.app.main:app --reload
```

The server reads the pack built by `etl/build_pack.py` from `etl/output`. Run the
ETL before starting the server to populate data.
