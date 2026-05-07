# AI Handover: Storage Architecture & Scaling

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

## Future S3 Implementation Notes
When IT grants S3 access, the next agent should:
1. Complete `backend/app/celery_app/tasks/s3_sync.py` (or inject S3 client logic into the sync task).
2. Modify `OnFlyConfig` and `build_source_client` to recognize `s3://` URIs and stream bytes directly into memory.
3. Update `TargetDir` logic so `data/stores/` is bypassed completely if `enable_s3_storage` is true.
