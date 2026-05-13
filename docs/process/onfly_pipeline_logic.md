# On-Fly Pipeline Logic (Source of Truth)

This document is the canonical logic reference for IRIS on-fly processing.
Update this file whenever on-fly behavior changes.

## Pipeline Stages

### Step 1 - `LIST`
- Input source can be:
  - Google Drive URL
  - Google Drive folder id
  - Local path
- The scanner discovers `.jpg`, `.jpeg`, `.png`.
- Derives metadata:
  - `folder_name` (date bucket source)
  - `camera_id` (from filename, e.g. `D07`)
  - `timestamp_hint` (from filename, e.g. `12-17-32`)

### Step 2 - `SKIP_CHECK` (Delta / Idempotent)
- Uses `onfly_image_state` in `store_registry.db`.
- Version-aware skip:
  - YOLO uses `yolo_version`
  - GPT uses `gpt_version`
  - fallback compatibility uses `pipeline_version` for legacy rows
- If YOLO version is unchanged and YOLO already done, YOLO is skipped.
- If GPT version changed (and image is relevant), only GPT re-runs.
- Only new or version-changed images continue.

### Step 3 - `DOWNLOAD` (Memory Only)
- Fetches bytes from source.
- Keeps bytes in memory cache.
- No permanent image write at this stage.
- SHA-256 is computed for exact duplicate reuse.

### Step 4 - `YOLO`
- Runs person detection.
- Outputs:
  - `person_count`
  - `yolo_conf`
  - `yolo_error` (if any)
  - person boxes used by downstream smart sampling
- Relevance rule:
  - `person_count > 0` => relevant
- Persists in `onfly_image_state`:
  - `yolo_status`
  - `yolo_relevant`
- If Drive write credentials are configured, relevant Google Drive images are copied to:
  - `Relevant image/<same date-folder name>/<original image filename>`

## Plain-English Brain Logic

This section explains what the current IRIS "brain" is actually doing in simple English.

### What YOLO is doing today

YOLO is currently acting as a fast visual gatekeeper, not as the final business-decision engine.

Its job is mainly:
- open one image
- check whether a person is visible
- estimate how many people are visible
- return person-box locations and confidence
- decide whether the frame is worth sending further in the pipeline

Very simply, the current rule is:
- no valid person found -> not relevant
- one or more valid people found -> relevant

In code, that rule is the direct decision:
- `relevant = int(pcount > 0 and not yerr)`

So YOLO is not currently deciding:
- customer vs staff
- walk-in vs non-walk-in
- conversion vs bounce
- session meaning

Those business meanings are decided later by GPT and session reconstruction.

### What happens before YOLO even runs

IRIS does not blindly run YOLO on every discovered file.

Before detection, the pipeline:
- builds the correct source client from the configured Drive URL / folder id / local path
- lists image files from that source
- loads excluded cameras for the store
- skips cameras that should never be analyzed, such as external or ignored feeds
- skips images outside store operating hours
- checks `onfly_image_state` so already-completed work is not repeated unless versions changed or force-rerun is used

This means many images can be discovered but still never reach YOLO, by design.

### What the detector actually returns

The detector returns a structured result, not just yes/no.

The useful outputs are:
- `person_count`
- `max_person_conf`
- `detection_error`
- `person_boxes`
- `person_confidences`

Those person boxes are then used for:
- relevance marking
- smart frame sampling
- later cost reduction before GPT

### How IRIS decides which detector to use

IRIS has a detector factory and does not hardcode only one backend.

Supported detector paths include:
- YOLO PyTorch
- YOLO ONNX Runtime
- OpenCV HOG fallback
- mock / legacy fallback paths

The detector choice is controlled by `build_detector(...)`.

Current practical meaning:
- if configured detector is available, use it
- if not available, fall back safely instead of crashing the whole pipeline

### What the current YOLO brain does inside detection

Inside the detector, IRIS is not accepting every raw box blindly.

It filters detections using rules such as:
- keep only person class for relevance
- apply confidence threshold
- run non-maximum suppression to remove overlapping duplicate boxes
- reject unrealistic person boxes using `_is_reasonable_person_box(...)`

That "reasonable person box" filter is important because it tries to reject boxes that are too small, too stretched, or geometrically unlikely to be a real person.

### Why a frame can still look wrong to a human reviewer

Even with the above filtering, YOLO is still a detection model, not human judgment.

So some frames may still look wrong in review, for example:
- only legs visible
- partial body visible
- distant person still counted
- older rows processed before a camera became excluded

That does not always mean the detector crashed.
It usually means the current relevance rule is still broad: if a valid person-like box exists, the frame can be marked relevant.

### Why relevant does not mean GPT will run on every frame

Relevant is only the first gate.

After YOLO marks a frame relevant, IRIS still may not call GPT for that exact frame because smart frame sampling runs next.

Smart frame sampling compares nearby frames from the same camera and date using:
- person count
- person-box layout
- overlap similarity
- time proximity

If two frames are very similar, only the anchor frame is sent to GPT.
The follow-up frame inherits the anchor result later.

This is how IRIS reduces GPT cost without losing the session outcome.

### Where the main brain code lives

The current source-of-truth code path is:

- `src/iris/onfly_pipeline.py`
  - orchestration of list -> skip -> download -> YOLO -> smart sampling -> GPT -> reporting
- `src/iris/iris_analysis.py`
  - detector selection and detector implementations
- `src/iris/download_manager.py`
  - byte-based YOLO wrappers and smart frame sampling comparison logic

### Important code anchors

- `src/iris/onfly_pipeline.py`
  - `run_onfly_pipeline(...)`
  - builds the source client
  - calls `list_images(...)`
  - loads excluded cameras
  - applies excluded-camera skip
  - applies outside-hours skip
  - calls YOLO through `_yolo_detect_full_result(...)`
  - marks relevance using `pcount > 0 and not yerr`
  - queues remaining anchor frames for GPT

- `src/iris/iris_analysis.py`
  - `build_detector(...)` chooses the detection backend
  - `OnnxPersonDetector` and `YoloPersonDetector` implement the person-detection brain
  - `_run_inference(...)` turns raw model output into filtered person boxes
  - `_is_reasonable_person_box(...)` removes obviously bad boxes

- `src/iris/download_manager.py`
  - `yolo_detect_direct(...)` runs a simple byte-path person check
  - `yolo_detect_full_result(...)` returns the richer detection result including person boxes
  - `evaluate_frame_sampling(...)` decides whether a relevant frame should be skipped as a near-duplicate for GPT

### The most important truth to remember

Current YOLO logic in IRIS answers this question first:

"Is there a valid visible person in this frame, and is this frame worth deeper analysis?"

It does not answer the full business question by itself.
The final business meaning is built later from:
- GPT interpretation
- camera rules
- time rules
- session reconstruction
- report aggregation

### Step 5 - `SMART_FRAME_SAMPLING`
- Runs only after YOLO on relevant frames.
- Consecutive frames from the same camera/date are compared using YOLO person-box signature and timing proximity.
- The first anchor frame goes to GPT.
- Similar follow-up frames are marked:
  - `gpt_status='sampled_wait_anchor'`
  - `sampled_anchor_image_id`
  - `sampled_signature`
  - `sampled_skip_reason`
- After the anchor GPT result is known, sampled frames inherit the resolved session output.

### Step 6 - `GPT`
- Runs only for relevant anchor frames (when GPT enabled).
- Input image is base64 in memory (not persisted as raw image blobs).
- GPT decides semantics:
  - role/event understanding (`ENTRY`, `EXIT`, `INSIDE_ACTIVE`, etc.)
  - customer/staff/banner/pedestrian context
- **Time source-of-truth is filename timestamp parsing**:
  - `entry_time` / `exit_time` are assigned from parsed image time, not GPT free-text clock.
- If GPT quota is unavailable:
  - YOLO must continue
  - GPT work moves to retry state instead of repeatedly burning API calls.

### Step 7 - `REPORT_WRITER`
- Writes canonical store files:
  - `data/exports/current/onfly/<STORE_ID>/onfly_image_results.csv`
  - `data/exports/current/onfly/<STORE_ID>/onfly_walkin_sessions.csv`
  - `data/exports/current/onfly/<STORE_ID>/onfly_walkin_sessions_audit.csv`
- Writes shared summary:
  - `data/exports/current/onfly/onfly_store_date_report.csv`
- Writes per-run summary:
  - `data/exports/current/onfly/onfly_run_summary_<run_id>.json`
  - `data/exports/current/onfly/<STORE_ID>/onfly_process_timings.csv`
- Writes cost proof rows into:
  - `onfly_cost_metrics`
- Relevant image review files are stored in Google Drive, not in the local export tree.
- The source scanner ignores the `Relevant image` folder so review copies are not reprocessed as source images.

### Step 8 - `DASHBOARD_INGEST`
- Updates on-fly report index tables for UI/report discovery.
- Pipeline journey is recorded in:
  - `onfly_pipeline_runs`
  - `onfly_pipeline_run_events`

## Session Logic (Current)

- GPT classifies event semantics.
- Session state transitions:
  - `ENTRY` -> `OPEN`
  - `INSIDE_ACTIVE` / `INSIDE_PURCHASING` -> update open session or create `INFERRED_INSIDE_OPEN`
  - `EXIT` -> close best matching open session (`CLOSED`) else `UNMATCHED_EXIT`
- End-of-day closeout:
  - remaining open sessions -> `CLOSED_EOD`

## Staff Override Rule (Current)

- Red shirt + black pant/trouser store-staff pattern is forced to staff in post-processing.
- White shirt + black pant/trouser manager pattern is forced to staff in post-processing.

## Runtime Model (Current)

IRIS now uses:
- FastAPI web process
- dedicated core scheduler worker
- dedicated on-fly scheduler worker
- dedicated store auto-sync worker

The web server does not own long-running scheduler loops.

## Update Discipline

Whenever pipeline logic changes, update:
1. `docs/process/onfly_pipeline_logic.md` (this file)
2. `CHANGE_LEDGER.md` (touched files + behavior summary)
3. `docs/AI_HANDOVER_STORAGE.md` if runtime/cost behavior changes
