#!/usr/bin/env python3
import json, urllib.request, urllib.error, ssl, time, datetime, concurrent.futures, os

INPUT_FILE  = "state_bar_directory.json"
OUTPUT_FILE = "docs/results.json"
TIMEOUT     = 12
MAX_WORKERS = 10

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

ACTIVE_CODES = {200, 301, 302, 303, 307, 308, 401, 403}

def check_url(entry):
    url = entry["url"]
    start = time.time()
    status = code = error = None
    if not url or url == "N/A":
        return {**entry, "status": "skip", "http_code": None, "response_ms": 0, "error": "No URL", "checked_at": _now()}
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        resp = urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx)
        code = resp.getcode()
        status = "active" if code in ACTIVE_CODES else "inactive"
    except urllib.error.HTTPError as e:
        code = e.code
        status = "active" if code in ACTIVE_CODES else "inactive"
        if code not in ACTIVE_CODES: error = f"HTTP {code}"
    except urllib.error.URLError as e:
        status = "inactive"; error = str(e.reason)
    except Exception as e:
        status = "inactive"; error = str(e)
    return {
        "state": entry["state"], "phone": entry.get("phone"),
        "phone_alt": entry.get("phone_alt"), "url": url,
        "phone_required": entry.get("phone_required", False),
        "notes": entry.get("notes", ""), "status": status,
        "http_code": code, "response_ms": round((time.time()-start)*1000),
        "error": error, "checked_at": _now(),
    }

def _now():
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def main():
    with open(INPUT_FILE) as f:
        data = json.load(f)
    entries = data["directories"]
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
    active = sum(1 for r in results if r["status"] == "active")
    inactive = sum(1 for r in results if r["status"] == "inactive")
    skipped = sum(1 for r in results if r["status"] == "skip")
    output = {
        "meta": {**metadata, "scan_time_utc": _now(), "total": len(results), "active": active, "inactive": inactive, "skipped": skipped},
        "results": results,
    }
    os.makedirs("docs", exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nDone — {active} active · {inactive} inactive · {skipped} skipped")
    if inactive > 0:
        exit(1)

if __name__ == "__main__":
    main()
