import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
STATUS_PATH = BASE_DIR / "health_status.json"
LOG_PATH = BASE_DIR / "health_log.txt"


def log(message):
    line = f"[HealthCheck] {message}"
    print(line)
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def get_json(url, timeout=5):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "CometFleetHealthCheck/1.0"}
    )

    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except Exception:
            return {"raw": raw}


def check_endpoint(base_url, path, required=True):
    url = base_url.rstrip("/") + path

    started = time.time()

    try:
        data = get_json(url, timeout=5)
        elapsed = round(time.time() - started, 2)

        ok = bool(data.get("ok", True)) if isinstance(data, dict) else True

        return {
            "path": path,
            "url": url,
            "ok": ok,
            "required": required,
            "elapsed": elapsed,
            "data": data,
            "error": ""
        }

    except urllib.error.HTTPError as e:
        return {
            "path": path,
            "url": url,
            "ok": False,
            "required": required,
            "elapsed": round(time.time() - started, 2),
            "data": {},
            "error": f"HTTP {e.code}"
        }

    except Exception as e:
        return {
            "path": path,
            "url": url,
            "ok": False,
            "required": required,
            "elapsed": round(time.time() - started, 2),
            "data": {},
            "error": str(e)
        }


def get_workers(base_url):
    result = check_endpoint(base_url, "/api/workers", required=True)
    if not result["ok"]:
        return result, []

    data = result.get("data") or {}
    workers = data.get("workers", [])

    if not isinstance(workers, list):
        workers = []

    return result, workers


def write_status(status):
    try:
        with STATUS_PATH.open("w", encoding="utf-8") as f:
            json.dump(status, f, indent=4)
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--coordinator", default="http://100.68.214.2:9555")
    parser.add_argument("--wait", type=int, default=45)
    parser.add_argument("--expect-worker", default="")
    parser.add_argument("--require-worker", action="store_true")
    args = parser.parse_args()

    base_url = args.coordinator.rstrip("/")
    deadline = time.time() + max(1, args.wait)

    required_paths = [
        "/api/health",
        "/api/workers"
    ]

    optional_paths = [
        "/api/mobile/tasks",
        "/api/sync/status"
    ]

    final_results = []
    workers = []

    log(f"Checking coordinator: {base_url}")

    while True:
        required_results = [
            check_endpoint(base_url, path, required=True)
            for path in required_paths
        ]

        required_ok = all(item["ok"] for item in required_results)

        workers_result, workers = get_workers(base_url)

        if required_ok and workers_result["ok"]:
            final_results = required_results
            break

        final_results = required_results

        if time.time() >= deadline:
            break

        time.sleep(2)

    optional_results = [
        check_endpoint(base_url, path, required=False)
        for path in optional_paths
    ]

    all_results = final_results + optional_results

    for item in all_results:
        status = "OK" if item["ok"] else "FAILED"
        required_text = "REQUIRED" if item["required"] else "OPTIONAL"
        error = f" | {item['error']}" if item["error"] else ""
        log(f"{required_text} {item['path']}: {status}{error}")

    expected_worker_ok = True

    if args.expect_worker:
        expected = args.expect_worker.strip().lower()
        found = False

        for worker in workers:
            pc_id = str(worker.get("pc_id") or "").strip().lower()
            if pc_id == expected:
                found = True
                break

        expected_worker_ok = found

        if found:
            log(f"Expected worker found: {args.expect_worker}")
        else:
            log(f"Expected worker NOT found: {args.expect_worker}")

    required_failed = [
        item for item in all_results
        if item["required"] and not item["ok"]
    ]

    status = {
        "ok": not required_failed and (expected_worker_ok or not args.require_worker),
        "coordinator": base_url,
        "checked_at": int(time.time()),
        "results": all_results,
        "workers": workers,
        "expected_worker": args.expect_worker,
        "expected_worker_ok": expected_worker_ok
    }

    write_status(status)

    if required_failed:
        log("Startup health check FAILED.")
        return 1

    if args.require_worker and not expected_worker_ok:
        log("Startup health check FAILED because required worker is missing.")
        return 1

    log("Startup health check PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
