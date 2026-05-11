# AI Handover: Storage Architecture & Scaling

**Last updated:** 2026-05-11

---

## Current Storage Flow (150-Store Scale)

As of **May 2026**, IRIS is designed to handle ~180,000 images per day for 150 stores. To manage this massive data throughput without filling up the server's local SSD, the following storage policies are implemented:

### 1. Zero Waste Policy

Images pulled from Google Drive are downloaded locally for processing. Immediately after the YOLO person-detection scan, if an image is determined to be **irrelevant** (no people detected), it is **instantly deleted** from the local disk (`Path.unlink()`).

- **Drive Sync Guard**: `store_source_file_index` was updated so `drive_delta_sync.py` checks the database for `source_file_id`. It will **not** re-download images that were previously downloaded but deleted.
- **Code Locations**: `scripts/yolo_relevance_scan.py` and `src/iris/onfly_pipeline.py`.

### 2. 7-Day Short Retention Policy

Raw images (even relevant ones) are not kept indefinitely. A Celery background task runs daily to sweep the `data/stores/` directory and permanently delete any image older than 7 days.

- **Task**: `backend.app.celery_app.tasks.cleanup.cleanup_old_images_task`
- **Schedule**: Daily at 2:00 AM (`crontab(hour=2, minute=0)` in `worker.py`)
- **Impact**: Keeps the server's SSD footprint strictly capped to a 7-day rolling window of relevant imagery.

### 3. S3 Object Storage Alternative

The groundwork for migrating from Google Drive/Local SSD to AWS S3 has been added but is **disabled by default**.

- Config flag: `enable_s3_storage` in `backend/app/config.py`.
- When set to `False`, the app uses Google Drive API for sync.
- When set to `True`, the Drive Sync Celery task will log a stub and eventually (when S3 is fully provisioned by IT) route to S3 bucket reads.
- **Reversion**: The user requested that Drive remain the primary source until IT provides bucket access, at which point the single `enable_s3_storage = True` flag can be used to switch architectures.

---

## GPT Cost Architecture (as of 2026-05-11)

Four optimizations are now live. Each reduces how many images reach GPT and/or reduces the per-call cost.

| Optimization | Where | Status | Saving |
|---|---|---|---|
| Camera-type exclusion | `onfly_pipeline.py` → `_load_excluded_cameras()` | Live | 15–25% fewer GPT calls |
| Store-hours filter | `onfly_pipeline.py` → `yolo_status = 'outside_hours'` | Live | 30–40% fewer GPT calls |
| GPT hash cache | `onfly_pipeline.py` → SHA-256 content hash dedup | Live | 5–10% fewer GPT calls |
| OpenAI Batch API | `src/iris/gpt_batch.py` + `gpt_batch_mode=True` | Live | 50% price reduction |

### Batch API Flow (overnight mode)

```
Evening pipeline run (gpt_batch_mode=True)
  └─ Per relevant image: queue_image_for_batch() → onfly_gpt_batch_queue
  └─ End of run: build_and_submit_batch() → OpenAI /v1/files + /v1/batches
       (~1 second HTTP call — laptop can close after this)

OpenAI processes overnight (2–12 hours)

6 AM: Windows Task Scheduler wakes laptop
  └─ scripts/batch_retrieve.py
       └─ check_batch_status() for each pending batch
       └─ apply_batch_results() → onfly_image_state + onfly_walkin_sessions + PG sync
```

**Key files:**

| File | Purpose |
|---|---|
| `src/iris/gpt_batch.py` | Full batch module: queue / submit / retrieve / apply |
| `scripts/batch_retrieve.py` | Morning CLI script — run manually or via Task Scheduler |
| `scripts/setup_morning_retrieval.ps1` | Registers Task Scheduler job (run once, admin PS) |

**SQLite tables added:**

| Table | Purpose |
|---|---|
| `onfly_gpt_batch_queue` | One row per queued image; stores base64 bytes, status, batch_db_id |
| `onfly_gpt_batches` | One row per OpenAI batch job; tracks openai_batch_id, status, results_applied |

**API endpoints:**

| Endpoint | Purpose |
|---|---|
| `POST /api/onfly/sync/{store_id}` body `gpt_batch_mode: true` | Start pipeline in batch mode |
| `GET /api/onfly/batch/status/{store_id}` | List all pending batches for a store |
| `POST /api/onfly/batch/retrieve/{store_id}` | Poll OpenAI + apply completed results |

**Important implementation notes:**

- OpenAI Batch API uses `/v1/chat/completions` format — NOT `/v1/responses`. The real-time pipeline uses `/v1/responses` (Responses API). These are different endpoints; batch only supports chat/completions and embeddings.
- `custom_id` format: `irisq_{queue_row_id}` — maps batch output lines back to the queued image.
- `apply_batch_results` applies the same staff-rule post-processing as real-time GPT (white/red + black pants = Staff). Walk-in sessions are written and synced to PostgreSQL identically.
- If PostgreSQL is down at retrieval time, SQLite is still updated correctly. PG sync retries on the next pipeline run.

---

## Image Scans Report (as of 2026-05-11)

`GET /api/reports/image-scans` now returns up to 50,000 rows per request with full rejection metadata.

| Column | Source | Meaning |
|---|---|---|
| `yolo_status` | `onfly_image_state` | Raw pipeline status (done, camera_excluded, outside_hours, skipped_irrelevant, failed_download, pending) |
| `gpt_status` | `onfly_image_state` | GPT status (done, cached_from_hash, batch_queued, failed, skipped_irrelevant) |
| `rejection_reason` | Derived CASE expression | Human-readable reason (Processed, Camera type excluded, Outside store hours, No people detected, Duplicate image, GPT cached, GPT analysis failed, Pending) |
| `error_detail` | COALESCE(gpt_error, yolo_error) | First non-empty error message |

Frontend: `ReportsPage.tsx` uses `@tanstack/react-virtual` row virtualizer for the image_scans tab (same pattern as ValidationTable). Facility filter is independent of the global store selector — changing it does not clear other report tabs.

---

## Future S3 Implementation Notes

When IT grants S3 access, the next agent should:

1. Complete `backend/app/celery_app/tasks/s3_sync.py` (or inject S3 client logic into the sync task).
2. Modify `OnFlyConfig` and `build_source_client` to recognize `s3://` URIs and stream bytes directly into memory.
3. Update `TargetDir` logic so `data/stores/` is bypassed completely if `enable_s3_storage` is true.
4. For batch mode: `queue_image_for_batch` stores image bytes as base64 in SQLite. With S3, consider storing the S3 object key instead and fetching bytes at `build_and_submit_batch` time — avoids storing large base64 blobs in SQLite.
