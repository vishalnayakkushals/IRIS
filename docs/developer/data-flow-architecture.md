# IRIS Data Flow Architecture

**Last updated:** 2026-05-12

## Canonical Flow

```text
Source (Google Drive URL / folder id / local path)
    ↓
source_clients.py
    ↓
LIST + metadata parse
    ↓
version-aware skip check (SQLite)
    ↓
download_manager.py
    ↓
YOLO detection (ONNX Runtime)
    ↓
smart frame sampling + dedup + business-time filters
    ↓
gpt_runtime.py
    ↓
session_reconstruction.py
    ↓
report_writer.py
    ↓
React/FastAPI UI + CSV exports
```

## Module Responsibilities

| Module | Responsibility |
| --- | --- |
| `src/iris/source_clients.py` | Drive/local clients, folder-id parsing, filename metadata extraction |
| `src/iris/download_manager.py` | byte download helpers, SHA-256 reuse, frame sampling decisions, YOLO byte-path helpers |
| `src/iris/gpt_runtime.py` | GPT prompt/runtime helpers, rate limiting, heartbeat, circuit breaker |
| `src/iris/session_reconstruction.py` | walk-in persistence, sampled-frame resolution, QA correction replay |
| `src/iris/report_writer.py` | canonical CSVs, run summaries, cost metrics |
| `src/iris/pipeline_events.py` | SQLite schema, run/event/queue helpers |
| `src/iris/onfly_pipeline.py` | orchestration wrapper across the modules above |

## Runtime Services

| Service | Purpose |
| --- | --- |
| API | serves web app + routes |
| Core scheduler | periodic platform jobs |
| On-fly scheduler | scan scheduling + retry orchestration |
| Store auto-sync | mapped-store sync loop |

## Databases

- PostgreSQL: platform metadata and web-facing app data
- SQLite: pipeline runtime truth and interim report materialization

## Cost Controls in the Flow

Before GPT:
- already-processed/version skip
- store-hours skip
- camera exclusion
- SHA-256 duplicate reuse
- smart frame sampling
- YOLO relevance gate

At GPT:
- realtime mode or batch mode
- quota-aware retry queueing
- circuit-breaker protection

After GPT:
- sampled frame resolution
- session reconstruction
- cost metric writes

## Out of Scope / Legacy

These are no longer the canonical architecture story:
- Streamlit as the primary UI (retired; legacy reference only)
- single-process web app with embedded scheduler loops
- PyTorch-only YOLO runtime on server
- Celery as the required scheduler story for the current local/cloud web app

