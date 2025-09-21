# Nutrition Scanner MVP

This repository contains a functional slice of the Nutrition Scanner MVP
including:

- a TypeScript mobile core that parses ingredients, resolves additives from a
  local pack, and runs the risk engine;
- a Python ETL pipeline that compiles CSV sources into a signed additive pack;
- a FastAPI backend that exposes pack metadata, additive details, and telemetry
  ingestion endpoints.

Refer to `requirements.md`, `architecture.md`, and `implementation.md` for the
full specification that guided this build.

## Getting started

### Mobile logic tests

```bash
cd mobile
yarn install
yarn test --runInBand
```

### Pack generation

```bash
python etl/build_pack.py
python etl/sign_pack.py   # requires keys/private_key.ed25519 (hex)
python etl/verify_pack.py # uses keys/public_key.ed25519
```

### Backend API tests

```bash
python -m pip install --user -e server[dev]
pytest server/app/tests
```

Once the ETL has produced a pack, launch the server:

```bash
uvicorn server.app.main:app --reload
```

The server serves the latest pack metadata at `/v1/packs/latest` and additive
data at `/v1/additives/{code}`.
