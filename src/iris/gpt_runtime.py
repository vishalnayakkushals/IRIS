from __future__ import annotations

from pathlib import Path
import base64
import json
import sqlite3
import threading
import time
from typing import Any

import requests

from .pipeline_events import now_iso
from .source_clients import OnFlyConfig, TIME_PATTERN

_WALKIN_COLUMNS = [
    "Date", "Walk-in ID", "Group ID", "Role", "Entry Time", "Exit Time", "Time Spent (mins)", "Session Status",
    "Entry Type", "Gender", "Age Band", "Attire / Visual Marker", "Primary Clothing", "Jewellery Load", "Bag Type",
    "Primary Clothing Style Archetype", "Engagement Type", "Engagement Depth", "Purchase Signal (Bag)", "Conversion Signal",
    "Included in Analytics", "Event Type", "Direction Confidence", "Match Fingerprint",
]

_RETAIL_WALKIN_PROMPT = """You are an AI system analysing retail store security camera images for offline customer intelligence.
Output is consumed by store operations teams, analytics dashboards, and AI learning systems.
Operate in a privacy-safe, recall-safe, non-PII manner.

PRIVACY & SAFETY RULES (NON-NEGOTIABLE):
Do NOT identify or recognise individuals. Do NOT use face recognition or biometrics.
Do NOT persist identity across days. Do NOT infer names, religion, caste, income, or any sensitive personal trait.
Use ONLY: visual cues, clothing, jewellery, bags, spatial position, temporal ordering, behavioural posture, group movement, entry/exit continuity.
All identification must be session-local only.

TEMPORAL REASONING (MANDATORY):
Treat all provided frames as a time-ordered sequence. Extract visible timestamps from each frame. Sort chronologically.
Detect new walk-ins even if they appear in only one frame. Track continuity only when visually and temporally supported.
NEVER merge people across frames only because they have similar clothing.
Create a NEW walk-in if a person appears at a new time window with no clear continuity from prior frames.
Create a NEW group if: time gap is more than about 2 minutes AND no clear visual continuity AND no coordinated movement/waiting/joint browsing.

PEOPLE DETECTION & ROLE SEPARATION:
Detect all visible people in every frame. Classify each as: Customer, Staff, or Uncertain.
Staff identification signals: repeated presence across frames, uniform/name tag/store dress, stationary near store entrance,
door handling for others, counter-side positioning, repeated customer-facing interaction pattern.
NOTE: A person standing at a billing/checkout counter is NOT automatically staff — customers also stand at billing counters to pay.
Special staff uniform rules (OVERRIDE clothing-alone restriction):
  - Red shirt + black pant/trouser = Staff (floor staff)
  - White shirt + black pant/trouser = Staff (managers, senior staff, supervisors)
Both patterns are always classified as Staff regardless of other cues. Do NOT classify either pattern as Customer or Manager — the only valid Role values are Customer, Staff, Uncertain.
Clothing colour alone is NOT sufficient to classify staff UNLESS the above specific uniform combinations are present.
Staff and Uncertain must be excluded from customer analytics: set Included in Analytics = No.

CRITICAL FALSE-POSITIVE CONTROL:
Do not treat posters, banners, standees, mannequins, printed humans, wall graphics, or reflection-only humans as customers.
If figure looks non-real (flat print, no limb articulation, no depth, fixed pose), mark as Uncertain and Included in Analytics = No.
If no clear real-human body cues (hands/legs/joint posture/motion context), prefer Uncertain over Customer.

EVENT-TYPE CLASSIFICATION (MANDATORY): choose exactly one: ENTRY, EXIT, INSIDE_ACTIVE, INSIDE_PURCHASING, PASSERBY_OUTSIDE, STAFF, POSTER_NON_HUMAN, UNCLEAR.
Use visual cues: body orientation, movement direction, relation to door/entrance, inside vs outside context.
Do NOT invent clock times from visual reasoning. Return event semantics only; system timestamping is handled by filename parser.

WALK-IN SESSION LOGIC:
Each detected customer walk-in is one session. Every walk-in MUST have a unique Walk-in ID and a Group ID.
If solo: still assign a Group ID. If multiple customers together: each gets a unique Walk-in ID, all share one Group ID.

GROUPING LOGIC (STRICT):
Group customers ONLY if they enter together OR show clear in-store convergence:
proximity, waiting together, shared browsing, coordinated movement, common engagement with the same counter/display.
Do NOT group if: different timestamps without continuity, only spatially close once, independent posture and direction.

ENTRY TYPE: Assisted Entry (staff facilitates entry) / Walk-in (customer enters independently) / Already Inside / NA.

SESSION TIME:
Entry Time: use actual timestamp of first supported entry or first seen moment; if threshold crossing not visible use earliest reliable timestamp; else NA.
Exit Time: use actual exit timestamp only if exit is visible; else NA.
Time Spent (mins): calculate only if both entry and exit are available; else NA.
Session Status: OPEN if no exit observed; CLOSED if exit observed.

DETERMINISTIC ID GENERATION (MANDATORY):
Walk-in ID: YYYYMMDDHHMMSSWNN   Group ID: YYYYMMDDHHMMSSGNN
Use Entry Time as anchor. If Entry Time is NA, use earliest reliable visible timestamp. If no timestamp visible at all, IDs = NA.
Sort walk-ins by Entry Time asc; tie-break: smaller group size first, then left-to-right, then stable non-random order.
Assign W01, W02, W03... Set each group anchor = earliest Entry Time among its members. Sort groups by anchor asc. Assign G01, G02, G03...
Do NOT use random IDs. Do NOT change IDs across reruns for the same frame set.

CUSTOMER PROFILE (NON-PII):
Gender: Male / Female / Uncertain.
Age Band (choose ONE): Under 18 / 18 - 24 / 25 - 34 / 35 - 45 / 45 - 55 / Above 55 / NA. Prefer wider bands if unsure.

VISUAL ATTRIBUTES:
Attire / Visual Marker: describe only visible clothing, accessories, bags, hairstyle cues if non-sensitive. Keep short, descriptive, recall-safe.
Primary Clothing (ONE): Saree / Dress / Suit / Casual / Formal / Office / Workwear / Festive / Mixed / NA.
Jewellery Load: None / Minimal / Everyday jewellery / Ethnic jewellery / Celebration / Heavy / Uncertain. If not clearly visible prefer Minimal/None/Uncertain.
Bag Type: Tote bag / Sling bag / Handbag / Backpack / Branded paper bag / None / NA.
Primary Clothing Style Archetype (ONE): Ethnic / Casual / Western / Office / Festive / Mixed / Uncertain.

ENGAGEMENT SIGNALS:
Engagement Type: Browsing / Assisted / Assisted Entry / Waiting / Billing / NA. If unclear prefer Browsing/NA.
Engagement Depth: Low / Medium / High / NA. If unclear prefer Low/NA.

PURCHASE SIGNAL (EXIT ONLY):
Purchase Signal (Bag): Yes / No / NA. Carry bag is only a proxy, not a guaranteed purchase.

CONVERSION SIGNAL (MANDATORY FOR EVERY ROW):
A conversion means the customer completed or is completing a purchase. Set Conversion Signal = Yes if ANY of these are true:
  1. This image is from a BILLING/CHECKOUT camera (camera context will be stated if so) AND the person is a Customer.
  2. The customer is visibly at a billing counter or payment terminal (Engagement Type = Billing).
  3. The customer exits with a carry bag (Purchase Signal (Bag) = Yes).
These are OR conditions — any single condition is sufficient. Set Conversion Signal = No if Role = Customer but none apply. Set Conversion Signal = NA if Role = Staff or Uncertain.

Included in Analytics: Yes if Role = Customer. No if Role = Staff or Uncertain.

OUTPUT: Return strict JSON only with key 'rows' containing an array of objects — one object per detected person — with exactly these fields: Date, Walk-in ID, Group ID, Role, Entry Time, Exit Time, Time Spent (mins), Session Status, Entry Type, Gender, Age Band, Attire / Visual Marker, Primary Clothing, Jewellery Load, Bag Type, Primary Clothing Style Archetype, Engagement Type, Engagement Depth, Purchase Signal (Bag), Conversion Signal, Included in Analytics, Event Type, Direction Confidence, Match Fingerprint. Prefer NA over guessing. Never invent data. Never output explanatory text outside the JSON."""


class TokenBucket:
    def __init__(self, rate: float, capacity: int) -> None:
        self._rate = max(0.1, rate)
        self._capacity = max(1, capacity)
        self._tokens = float(capacity)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, timeout: float = 60.0) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(self._capacity, self._tokens + (now - self._last) * self._rate)
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
                wait = (1.0 - self._tokens) / self._rate
            if time.monotonic() + wait > deadline:
                return False
            time.sleep(min(wait, 0.25))


class CircuitBreaker:
    CLOSED = "closed"
    OPEN = "open"

    def __init__(self, fail_max: int = 5, reset_timeout: float = 60.0) -> None:
        self._fail_max = fail_max
        self._reset_timeout = reset_timeout
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return False
            if time.monotonic() - self._opened_at >= self._reset_timeout:
                self._failures = 0
                self._opened_at = None
                return False
            return True

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self._fail_max and self._opened_at is None:
                self._opened_at = time.monotonic()

    @property
    def state(self) -> str:
        return self.OPEN if self.is_open else self.CLOSED


class HeartbeatThread(threading.Thread):
    def __init__(self, db_path: Path, run_id: str, interval: float = 25.0) -> None:
        super().__init__(daemon=True, name=f"heartbeat-{run_id[-8:]}")
        self._db_path = db_path
        self._run_id = run_id
        self._interval = interval
        self._stop_evt = threading.Event()

    def stop(self) -> None:
        self._stop_evt.set()

    def run(self) -> None:
        while not self._stop_evt.wait(self._interval):
            try:
                c = sqlite3.connect(str(self._db_path), timeout=5)
                c.execute("UPDATE onfly_pipeline_runs SET last_heartbeat_at=? WHERE run_id=?", (now_iso(), self._run_id))
                c.commit()
                c.close()
            except Exception:
                pass


def walkin_schema() -> dict[str, Any]:
    row_props = {col: {"type": "string"} for col in _WALKIN_COLUMNS}
    return {
        "name": "retail_onfly_walkin_table",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "rows": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": row_props,
                        "required": list(row_props.keys()),
                    },
                }
            },
            "required": ["rows"],
        },
    }


def apply_staff_manager_rule(walkins: list[dict[str, str]]) -> list[dict[str, str]]:
    for row in walkins:
        role = str(row.get("Role", "") or "").strip().lower()
        marker = str(row.get("Attire / Visual Marker", "") or "").lower()
        primary = str(row.get("Primary Clothing", "") or "").lower()
        style = str(row.get("Primary Clothing Style Archetype", "") or "").lower()
        text = " ".join([marker, primary, style])
        has_white = "white" in text
        has_red = "red" in text
        has_black = "black" in text
        has_pant = any(tok in text for tok in ("pant", "pants", "trouser", "trousers"))
        has_staff_uniform = (has_white or has_red) and has_black and has_pant
        if has_staff_uniform and role in {"customer", "uncertain", ""}:
            row["Role"] = "Staff"
            row["Included in Analytics"] = "No"
    return walkins


def parse_filename_time(image_name: str) -> str:
    match = TIME_PATTERN.match(str(image_name or "").strip())
    if not match:
        return ""
    return match.group(1).replace("-", ":")


def openai_eval(cfg: OnFlyConfig, image_bytes: bytes, image_name: str, prompt_extra: str = "", is_billing_camera: bool = False) -> dict[str, Any]:
    if not cfg.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY missing")
    ext = Path(image_name).suffix.lower().lstrip(".") or "jpeg"
    if ext == "jpg":
        ext = "jpeg"
    data_uri = f"data:image/{ext};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    billing_ctx = (
        "\n\nCAMERA CONTEXT — BILLING/CHECKOUT: This image is captured by a camera positioned at a billing counter or checkout area. Any Customer visible here is at the payment point. Apply Conversion Signal = Yes for all Customers in this image. Set Engagement Type = Billing."
        if is_billing_camera else ""
    )
    full_prompt = _RETAIL_WALKIN_PROMPT + billing_ctx + (f"\n\nSTORE-SPECIFIC RULES:\n{prompt_extra}" if prompt_extra else "")
    body = {
        "model": cfg.openai_model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": full_prompt}, {"type": "input_image", "image_url": data_uri}]}],
        "text": {"format": {"type": "json_schema", **walkin_schema()}},
        "max_output_tokens": 2000,
    }
    resp = requests.post(
        f"{cfg.openai_api_base.rstrip('/')}/responses",
        headers={"Authorization": f"Bearer {cfg.openai_api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=120,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenAI error {resp.status_code}: {resp.text[:500]}")
    payload = resp.json()
    text = payload.get("output_text")
    if not isinstance(text, str) or not text.strip():
        for item in payload.get("output", []):
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                    chunk = content.get("text", "")
                    if isinstance(chunk, str) and chunk.strip():
                        text = chunk
                        break
            if isinstance(text, str) and text.strip():
                break
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("Empty output_text from Responses API")
    parsed = json.loads(text)
    rows = parsed.get("rows", [])
    walkins: list[dict[str, str]] = []
    for row in rows:
        if isinstance(row, dict):
            walkins.append({col: str(row.get(col, "NA") or "NA").strip() for col in _WALKIN_COLUMNS})
    walkins = apply_staff_manager_rule(walkins)
    customer_count = sum(1 for item in walkins if item.get("Included in Analytics", "").lower() == "yes")
    staff_count = sum(1 for item in walkins if item.get("Role", "").lower() == "staff")
    conversions = sum(1 for item in walkins if item.get("Conversion Signal", "").lower() == "yes" or item.get("Purchase Signal (Bag)", "").lower() == "yes")
    return {
        "customer_count": customer_count,
        "staff_count": staff_count,
        "conversions": conversions,
        "bounce": 0,
        "notes": f"{len(walkins)} persons detected ({customer_count} customers, {staff_count} staff)",
        "walkins": walkins,
    }
