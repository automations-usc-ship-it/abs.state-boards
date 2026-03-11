#!/usr/bin/env python3
import json
import urllib.request
import urllib.error
import ssl
import time
import datetime
import concurrent.futures
import os
import smtplib
from email.mime.text import MIMEText

INPUT_FILE  = "state_bar_directory.json"
OUTPUT_FILE = "docs/results.json"
TIMEOUT     = 12
MAX_WORKERS = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

ACTIVE_CODES = {200, 301, 302, 303, 307, 308, 401, 403}

def check_url(entry):
    url   = entry["url"]
    state = entry["state"]
    start = time.time()
    status = None
    code   = None
    error  = None

    if not url or url == "N/A":
        return {**entry, "status": "skip", "http_code": None,
                "response_ms": 0, "error": "No URL provided", "checked_at": _now()}

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE

    try:
        req  = urllib.request.Request(url, headers=HEADERS)
        resp = urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx)
        code = resp.getcode()
        status = "active" if code in ACTIVE_CODES else "inactive"
    except urllib.error.HTTPError as e:
        code   = e.code
        status = "active" if code in ACTIVE_CODES else "inactive"
        if code not in ACTIVE_CODES:
            error = f"HTTP {code}"
    except urllib.error.URLError as e:
        status = "inactive"
        error  = str(e.reason)
    except Exception as e:
        status = "inactive"
        error  = str(e)

    elapsed = round((time.time() - start) * 1000)
    return {
        "state":        state,
        "phone":        entry.get("phone"),
        "phone_alt":    entry.get("phone_alt"),
        "url":          url,
        "phone_required": entry.get("phone_required", False),
        "notes":        entry.get("notes", ""),
        "status":       status,
        "http_code":    code,
        "response_ms":  elapsed,
        "error":        error,
        "checked_at":   _now(),
    }

def _now():
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def send_email(inactive_results):
    sender   = os.environ.get("GMAIL_USER")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not sender or not password:
        print("Email skipped — GMAIL_USER or GMAIL_APP_PASSWORD not set")
        return

    lines = [
        f"  • {r['state']}: {r['url']} ({r.get('error') or r.get('http_code')})"
        for r in inactive_results
    ]
    body = "The following state bar links are DOWN:\n\n" + "\n".join(lines)

    msg = MIMEText(body)
    msg["Subject"] = f"⚠️ {len(inactive_results)} State Bar Link(s) Down"
    msg["From"]    = sender
    msg["To"]      = sender

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)
    print(f"Alert email sent to {sender}")

def main():
    with open(INPUT_FILE) as f:
        data = json.load(f)

    entries  = data["directories"]
    metadata = data.get("metadata", {})

    print(f"Checking {len(entries)} URLs...")
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(check_url, e): e for e in entries}
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            r = fut.result()
            results.append(r)
            icon = "✅" if r["status"] == "active" else "❌"
            print(f"  [{i:>2}/{len(entries)}] {icon} {r['state']:30s} {r['status']}")

    results.sort(key=lambda x: x["state"])

    active   = sum(1 for r in results if r["status"] == "active")
    inactive = sum(1 for r in results if r["status"] == "inactive")
    skipped  = sum(1 for r in results if r["status"] == "skip")

    output = {
        "meta": {
            **metadata,
            "scan_time_utc": _now(),
            "total":    len(results),
            "active":   active,
            "inactive": inactive,
            "skipped":  skipped,
        },
        "results": results,
    }

    os.makedirs("docs", exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nDone — {active} active · {inactive} inactive · {skipped} skipped")
    if inactive > 0:
        inactive_list = [r for r in results if r["status"] == "inactive"]
        send_email(inactive_list)
        exit(1)

if __name__ == "__main__":
    main()
