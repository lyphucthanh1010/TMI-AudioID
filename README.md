# TMI AudioID

**Reference-based music identification with Chromaprint, Random Forest candidate retrieval, direct fingerprint verification, and temporal multi-song scanning.**

TMI AudioID is an end-to-end music identification system designed for a Master's research project and practical deployment. It supports short-clip recognition, long-form audio/video scanning, social-video URLs, multi-user libraries, model versioning, dataset snapshots, and reproducible benchmarking.

> Current pretrained release: **100 reference tracks · 4,359 fingerprint windows · 100 RF classes · 100 trees**

## Highlights

- **Quick Identify** for short audio clips and single-song queries.
- **Scan Timeline** for long audio/video containing multiple known and unknown regions.
- Inputs: local audio/video, YouTube, YouTube Shorts, TikTok, Facebook Reels, and microphone-oriented API flows.
- **Chromaprint raw uint32 fingerprints** as the canonical representation.
- **64-dimensional RF features**: 32 bit-frequency features + 32 adjacent-transition features.
- **Random Forest Top-K retrieval** followed by direct fingerprint verification.
- Comparator uses **12-MSB alignment hypotheses**, Top-3 offsets, and full 32-bit Hamming verification.
- Dataset/version lifecycle: `DRAFT → FROZEN → TRAIN → VALIDATE → ACTIVATE`.
- Global/private library scopes and asynchronous jobs.
- OpenAPI/Swagger documentation included.
- Docker/Render-ready deployment configuration.

## Architecture

```text
Audio / Video / URL / Mic
          │
          ▼
 Decode + canonicalize audio
 44.1 kHz mono PCM16
          │
          ▼
 10 s windows / 5 s hop
          │
          ▼
 Chromaprint raw uint32[]
          │
          ├──────────────► 64-D bit_pair_stats
          │                       │
          │                       ▼
          │               Random Forest
          │                    Top-K
          │                       │
          ▼                       ▼
 Raw reference fingerprints ◄ Candidate songs
          │
          ▼
 Direct Comparator
 alignment + Hamming verification
          │
          ▼
 MATCH / UNKNOWN
          │
          ├─ Quick Identify → one result
          └─ Scan Timeline  → temporal clusters + timestamps
```

## Random Forest I/O

The RF is a **candidate retriever**, not the final match decision layer.

**Input per fingerprint window**

```text
X ∈ R^64
├─ 32 normalized bit frequencies
└─ 32 normalized adjacent XOR-transition frequencies
```

**Output**

```text
P(song_1 | x), ..., P(song_N | x)
            ↓
         Top-K songs
            ↓
 direct fingerprint comparator
            ↓
       MATCH / UNKNOWN
```

## Pretrained Model

| Property | Value |
|---|---:|
| Reference tracks | 100 |
| Fingerprint windows | 4,359 |
| RF classes | 100 |
| Trees | 100 |
| RF Top-K | 5 |
| Window length | 10 s |
| Window hop | 5 s |
| Verification score gate | 0.60 |
| Verification overlap gate | 0.50 |

See `PRETRAINED_MODEL.md` and `VALIDATION_AND_BENCHMARK.md` for exact artifact and benchmark details.

## Benchmark Snapshot

| Scenario | Result |
|---|---|
| Known-song excerpt | ✅ Correct match |
| Mixed playlist with known + unknown sections | ✅ Both known tracks localized |
| Live-like pitch/tempo/reverb/crowd proxy | ✅ UNKNOWN, no false accept |
| 8 s known song inside speech-heavy 70 s audio | ✅ Localized in scan mode |
| 100-track arbitrary-offset MP3 sweep | **100/100 correct** |
| Backend automated tests | **22/22 passed** |

Measured on the current research environment, the 100-track arbitrary-offset MP3 sweep had approximately **0.158 s median** and **0.175 s P95** query latency. These are implementation benchmarks, not universal production SLAs.

## Repository Layout

```text
.
├─ backend/
│  ├─ audioid/              # FastAPI domain logic
│  ├─ scripts/              # API / worker entrypoints
│  ├─ tests/                # backend regression tests
│  ├─ validation/           # benchmark artifacts
│  └─ runtime/              # local/pretrained DB + model artifacts
├─ frontend/
│  └─ src/                  # React/Vite UI
├─ validation/              # top-level benchmark snapshots
├─ render.yaml              # Render Blueprint
├─ docker-compose.yml       # local full-stack
└─ RENDER_FREE_DEPLOY.md    # free deployment notes
```

## Local Run

### Docker

```bash
docker compose up --build
```

Default local URLs:

```text
Frontend: http://localhost:5173
API:      http://localhost:8000
Swagger:  http://localhost:8000/docs
Health:   http://localhost:8000/health
```

### Run backend from source

```bash
cd backend
python scripts/run_api.py
```

Run the worker in a second terminal:

```bash
cd backend
python scripts/run_worker.py
```

Async operations such as ingestion, identification, scanning, and training require the worker process.

## Main API Groups

The backend currently exposes **33 endpoints** across system health/readiness, authentication, reference ingestion, Quick Identify, temporal Scan, datasets, model training/activation, jobs, library, and social URL workflows.

Full endpoint documentation is available in `backend/API_MAP_COMPLETE.md` and Swagger at `/docs`.

Example training lifecycle:

```text
POST /api/v1/datasets
        ↓
add reference songs
        ↓
POST /api/v1/datasets/{dataset_id}/freeze
        ↓
POST /api/v1/models/train
        ↓
GET /api/v1/jobs/{job_id}
        ↓
POST /api/v1/models/{model_id}/activate
```

## Quick Identify vs Scan

Use **Quick Identify** when the input is expected to correspond to one recording:

```text
POST /api/v1/identify/file
POST /api/v1/identify/youtube
POST /api/v1/identify/url
```

Use **Scan Timeline** for long or heterogeneous media:

```text
POST /api/v1/scan/file
POST /api/v1/scan/youtube
POST /api/v1/scan/url
```

Scan evaluates local windows independently and clusters adjacent accepted windows into song events with timestamps.

## Deployment

A Render Blueprint is included in `render.yaml`. The free/demo deployment is designed to run the FastAPI process and background worker together in one web service.

> **Free-tier note:** Render's free filesystem is ephemeral. The baked research snapshot can boot with the image, but newly created users, newly ingested references, job history, and newly trained model artifacts should be moved to persistent PostgreSQL/object storage before treating the service as production.

## Research Scope and Limitations

TMI AudioID currently targets **reference-recording identification**.

- Same master recording with compression/noise: generally suitable.
- Speech/crowd overlap: performance depends on signal dominance and local coverage.
- Live/acoustic/cover/re-arranged performances: not guaranteed by Chromaprint-based exact-recording verification.
- A future composition-level branch may use chroma/CQT + DTW or learned music embeddings while keeping exact-recording identity separate.

Thresholds in the current research snapshot are provisional and should be recalibrated on larger track-disjoint and real-world evaluation sets before production claims are made.

## Reproducibility

```text
Dataset snapshot
    ↓
Feature version
    ↓
Model version + artifact SHA-256
    ↓
Validation results
    ↓
Active deployment model
```

## Tech Stack

**Backend:** Python, FastAPI, SQLAlchemy, scikit-learn, Chromaprint/libchromaprint, FFmpeg, yt-dlp  
**Frontend:** React, Vite  
**Data:** SQLite for local/demo; PostgreSQL-compatible architecture for production migration  
**Deployment:** Docker, Render Blueprint

## Project Status

- reference-based identification ✅
- multi-song timeline scanning ✅
- pretrained 100-track research model ✅
- social-video URL pipeline ✅
- responsive web UI ✅
- live/cover composition recognition ⏳ future branch
- production persistent storage ⏳ deployment hardening

## Author

**Thanh Ly-Phuc (Lý Phúc Thành)**  
Computer Science, University of Information Technology, VNU-HCM

Research title: **A Reference-Based Audio Identification System Using Chromaprint and Random Forest Candidate Filtering**

---

This repository is primarily a research and demonstration system. Benchmark results should be interpreted within the exact dataset, transformations, thresholds, and hardware/runtime conditions documented in the validation artifacts.
