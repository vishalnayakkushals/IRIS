#!/usr/bin/env python3
"""
IRIS Post-Deploy Smoke Test
Run on the server after first deployment to verify all critical paths work.

Usage:
    python scripts/smoke_test.py --url http://localhost:8767 --email admin@example.com --password YourPassword

Against production domain:
    python scripts/smoke_test.py --url https://iris.your-domain.com --email admin@example.com --password YourPassword
"""
from __future__ import annotations

import argparse
import sys
import time

import requests

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
WARN = "\033[93m[WARN]\033[0m"


def check(label: str, ok: bool, detail: str = "") -> bool:
    status = PASS if ok else FAIL
    line = f"  {status}  {label}"
    if detail:
        line += f"  — {detail}"
    print(line)
    return ok


def run(base_url: str, email: str, password: str) -> int:
    base_url = base_url.rstrip("/")
    failures = 0
    session = requests.Session()
    session.timeout = 15

    print(f"\nIRIS Smoke Test → {base_url}\n{'─'*55}")

    # 1. Health
    try:
        r = session.get(f"{base_url}/api/health")
        ok = r.status_code == 200
        failures += 0 if check("Health endpoint /api/health", ok, f"HTTP {r.status_code}") else 1
    except Exception as exc:
        failures += 1
        check("Health endpoint /api/health", False, str(exc))

    # 2. React SPA root
    try:
        r = session.get(f"{base_url}/")
        ok = r.status_code == 200 and ("text/html" in r.headers.get("content-type", ""))
        failures += 0 if check("React SPA served at /", ok, f"HTTP {r.status_code}") else 1
    except Exception as exc:
        failures += 1
        check("React SPA served at /", False, str(exc))

    # 3. Login
    token = None
    try:
        r = session.post(
            f"{base_url}/api/auth/login",
            json={"email": email, "password": password},
        )
        ok = r.status_code == 200
        if ok:
            token = r.json().get("access_token")
            ok = bool(token)
        failures += 0 if check("Login /api/auth/login", ok, f"HTTP {r.status_code}") else 1
    except Exception as exc:
        failures += 1
        check("Login /api/auth/login", False, str(exc))

    if not token:
        print(f"\n  {WARN}  Skipping authenticated checks — login failed.\n")
        return failures

    auth = {"Authorization": f"Bearer {token}"}

    # 4. Dashboard overview
    try:
        r = session.get(f"{base_url}/api/dashboard/overview", headers=auth)
        ok = r.status_code == 200
        failures += 0 if check("Dashboard overview", ok, f"HTTP {r.status_code}") else 1
    except Exception as exc:
        failures += 1
        check("Dashboard overview", False, str(exc))

    # 5. Store list
    try:
        r = session.get(f"{base_url}/api/stores", headers=auth)
        ok = r.status_code == 200
        stores = r.json() if ok else []
        count = len(stores) if isinstance(stores, list) else "?"
        failures += 0 if check("Store list /api/stores", ok, f"{count} store(s)") else 1
    except Exception as exc:
        failures += 1
        check("Store list /api/stores", False, str(exc))

    # 6. Scheduler runs
    try:
        r = session.get(f"{base_url}/api/runs?limit=5", headers=auth)
        ok = r.status_code == 200
        failures += 0 if check("Pipeline run history /api/runs", ok, f"HTTP {r.status_code}") else 1
    except Exception as exc:
        failures += 1
        check("Pipeline run history /api/runs", False, str(exc))

    # 7. Security headers
    try:
        r = session.get(f"{base_url}/")
        headers = r.headers
        missing = [
            h for h in ["X-Content-Type-Options", "X-Frame-Options"]
            if h not in headers
        ]
        ok = len(missing) == 0
        detail = "missing: " + ", ".join(missing) if missing else "all present"
        failures += 0 if check("Security headers present", ok, detail) else 1
    except Exception as exc:
        failures += 1
        check("Security headers present", False, str(exc))

    # 8. HTTPS redirect (only if hitting HTTP)
    if base_url.startswith("http://") and not base_url.startswith("http://localhost") and not base_url.startswith("http://127"):
        try:
            r = requests.get(base_url + "/", allow_redirects=False, timeout=10)
            ok = r.status_code in (301, 302) and "https" in r.headers.get("Location", "")
            failures += 0 if check("HTTP→HTTPS redirect", ok, f"HTTP {r.status_code} → {r.headers.get('Location', 'none')}") else 1
        except Exception as exc:
            failures += 1
            check("HTTP→HTTPS redirect", False, str(exc))

    print(f"\n{'─'*55}")
    if failures == 0:
        print(f"  {PASS}  All checks passed. IRIS is healthy.\n")
    else:
        print(f"  {FAIL}  {failures} check(s) failed. Review output above.\n")

    return failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IRIS post-deploy smoke test")
    parser.add_argument("--url", default="http://localhost:8767", help="Base URL of the IRIS app")
    parser.add_argument("--email", required=True, help="Admin email address")
    parser.add_argument("--password", required=True, help="Admin password")
    args = parser.parse_args()

    sys.exit(run(args.url, args.email, args.password))
