import sys, time, threading
sys.path.insert(0, 'src')

from iris.onfly_pipeline import _TokenBucket, _CircuitBreaker, _HeartbeatThread

print("=== _TokenBucket ===")
bucket = _TokenBucket(rate=5.0, capacity=5)
t0 = time.monotonic()
for i in range(5):
    bucket.acquire()
elapsed = time.monotonic() - t0
print(f"  5 tokens acquired in {elapsed:.3f}s (expect ~0s since bucket starts full): {'OK' if elapsed < 0.5 else 'SLOW'}")

t0 = time.monotonic()
bucket.acquire()
elapsed = time.monotonic() - t0
print(f"  6th token (refill) took {elapsed:.3f}s (expect ~0.2s): {'OK' if 0.1 < elapsed < 0.5 else 'UNEXPECTED'}")

print("\n=== _CircuitBreaker ===")
cb = _CircuitBreaker(fail_max=3, reset_timeout=2.0)
print(f"  Initial state: {cb.state} (expect CLOSED)")
for i in range(3):
    cb.record_failure()
print(f"  After 3 failures: {cb.state} (expect OPEN)")
print(f"  is_open: {cb.is_open} (expect True)")
time.sleep(2.1)
print(f"  After 2.1s sleep: {cb.state} (expect CLOSED, auto-reset)")
print(f"  is_open: {cb.is_open} (expect False)")
cb.record_success()
print(f"  After success: {cb.state} (expect CLOSED)")

print("\n=== _HeartbeatThread (mock - no DB) ===")
# Just test it can be instantiated and stopped without a real DB
import sqlite3, tempfile, os
with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
    tmp_db = f.name
conn = sqlite3.connect(tmp_db)
conn.execute("CREATE TABLE onfly_pipeline_runs (run_id TEXT PRIMARY KEY, last_heartbeat_at TEXT)")
conn.execute("INSERT INTO onfly_pipeline_runs VALUES ('test-run-1', NULL)")
conn.commit()
conn.close()

hb = _HeartbeatThread(tmp_db, 'test-run-1', interval=0.3)
hb.start()
time.sleep(0.7)
hb.stop()

conn2 = sqlite3.connect(tmp_db)
row = conn2.execute("SELECT last_heartbeat_at FROM onfly_pipeline_runs WHERE run_id='test-run-1'").fetchone()
conn2.close()
os.unlink(tmp_db)
updated = row[0] is not None
print(f"  Heartbeat updated DB: {'OK' if updated else 'FAIL'} (last_heartbeat_at={row[0]})")

print("\nAll tests passed.")
