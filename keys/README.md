# Keys

The repository only includes the Ed25519 public key used to verify additive pack
signatures. Generate a private key locally and keep it out of version control.
Use `python etl/sign_pack.py` after creating `keys/private_key.ed25519` with the
hex-encoded private key material.
