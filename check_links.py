import json
import urllib.request
import urllib.error
import ssl
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

INPUT_FILE = "state_bar_directory.json"
OUTPUT_FILE = "docs/results.json"
TIMEOUT = 12
MAX_WORKERS = 10
ACTIVE_CODES = {200, 301, 302, 303, 307, 308, 401, 403}
NO_ALT_PREFIX = "No alternative link as of"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def check_url(url):
    if not url or url.startswith(NO_ALT_PREFIX):
        return None, None, None
    try:
        start = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            code = resp.status
            ms = round((time.time() - start) * 1000)
            return "active" if code in ACTIVE_CODES else "inactive", code, ms
    except urllib.error.HTTPError as e:
        ms = round((time.time() - start) * 1000)
        return ("active" if e.code in ACTIVE_CODES else "inactive"), e.code, ms
    except Exception as e:
        return "inactive", None, None

def check_entry(entry):
    state = entry.get("state")
    url = entry.get("url")
    url_alt = entry.get("url_alt")

    status, code, ms = check_url(url)
    
    # Determine alt status
    if url_alt is None:
        alt_status, alt_code, alt_ms = None, None, None
        alt_label = None
    elif url_alt.startswith(NO_ALT_PREFIX):
        alt_status, alt_code, alt_ms = "no_alt", None, None
        alt_label = url_alt
    else:
        alt_status, alt_code, alt_ms = check_url(url_alt)
        alt_label = None

    return {
        "state": state,
        "phone": entry.get("phone"),
        "phone_alt": entry.get("phone_alt"),
        "phone_required": entry.get("phone_required", False),
        "notes": entry.get("notes", ""),
        "url": url,
        "url_status": status,
        "url_http_code": code,
        "url_response_ms": ms,
        "url_alt": url_alt,
        "url_alt_label": alt_label,
        "url_alt_status": alt_status,
        "url_alt_http_code": alt_code,
        "url_alt_response_ms": alt_ms,
    }

def main():
    with open(INPUT_FILE) as f:
        data = json.load(f)

    directories = data["directories"]
    results = []
    any_inactive = False

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(check_entry, entry): entry for entry in directories}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if result["url_status"] == "inactive":
                any_inactive = True
            print(f"  {result['state']}: primary={result['url_status']} ({result['url_http_code']}) | alt={result['url_alt_status']} ({result['url_alt_http_code']})")

    results.sort(key=lambda x: x["state"])

    output = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "active": sum(1 for r in results if r["url_status"] == "active"),
        "inactive": sum(1 for r in results if r["url_status"] == "inactive"),
        "phone_required": sum(1 for r in results if r["phone_required"]),
        "results": results
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nScan complete: {output['active']} active, {output['inactive']} inactive out of {output['total']} entries.")
    print(f"Results written to {OUTPUT_FILE}")

    if any_inactive:
        exit(1)

if __name__ == "__main__":
    main()
