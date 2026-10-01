# Bootstrap payload

This folder contains the compact deployment payload used by Render.

- `source.b64`: gzip-compressed application source encoded as Base64.
- `db.part*.b64`: Base64 chunks of the XZ-compressed pretrained SQLite seed database.
- `unpack.sh`: reconstructs the source tree and pretrained database during build.

The RF artifact itself is rebuilt deterministically from the frozen 100-track dataset at image-build time, so the large `.joblib` file does not need to live in Git.
