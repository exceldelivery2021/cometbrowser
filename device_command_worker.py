import json
import os
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path

import requests


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATHS = [
    BASE_DIR / "local_config.json",
    BASE_DIR / "sync_client_config.json",
]

LOG_PATH = BASE_DIR / "device_command_worker_log.txt"


def log(message):
    line = f"[DeviceCommandWorker] {time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    print(line)
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\\n")
    except Exception:
        pass


def load_config():
    data = {}

    for path in CONFIG_PATHS:
        if not path.exists():
            continue

        try:
            with path.open("r", encoding="utf-8-sig") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                data.update(raw)
        except Exception:
            pass

    return data


CFG = load_config()

COORDINATOR_URL = (
    CFG.get("COORDINATOR_URL")
    or CFG.get("coordinator_url")
    or CFG.get("MAIN_COORDINATOR_URL")
    or "http://100.68.214.2:9555"
)

PC_ID = (
    CFG.get("PC_ID")
    or CFG.get("pc_id")
    or CFG.get("DEVICE_ID")
    or CFG.get("device_id")
    or socket.gethostname()
)

DEVICE_TYPE = CFG.get("DEVICE_TYPE") or CFG.get("device_type") or "laptop"


def coordinator_url(path):
    return str(COORDINATOR_URL).rstrip("/") + path


def headers():
    return {
        "X-PC-ID": str(PC_ID),
        "X-Device-Type": str(DEVICE_TYPE),
    }


def post(path, payload=None, timeout=10):
    response = requests.post(
        coordinator_url(path),
        json=payload or {},
        headers=headers(),
        timeout=timeout
    )
    response.raise_for_status()
    return response.json()


def register_worker():
    payload = {
        "pc_id": PC_ID,
        "device_type": DEVICE_TYPE,
        "type": "command_worker",
        "platform": platform.platform(),
        "hostname": socket.gethostname(),
        "status": "online",
    }

    try:
        post("/api/workers/register", payload, timeout=5)
    except Exception as e:
        log(f"Worker register failed: {e}")


def heartbeat():
    payload = {
        "pc_id": PC_ID,
        "device_type": DEVICE_TYPE,
        "type": "command_worker",
        "status": "online",
        "time": int(time.time()),
    }

    try:
        post("/api/workers/heartbeat", payload, timeout=5)
    except Exception as e:
        log(f"Worker heartbeat failed: {e}")


def claim_commands():
    try:
        return post("/api/device-commands/claim", {"pc_id": PC_ID}, timeout=10).get("commands") or []
    except Exception as e:
        log(f"Claim failed: {e}")
        return []


def complete_command(command_id, status="completed", result=None, error=""):
    try:
        post(
            "/api/device-commands/complete",
            {
                "command_id": command_id,
                "pc_id": PC_ID,
                "status": status,
                "result": result or {},
                "error": error or "",
            },
            timeout=10
        )
    except Exception as e:
        log(f"Complete failed for {command_id}: {e}")


def start_python_script(script_name):
    path = BASE_DIR / script_name

    if not path.exists():
        return {
            "started": False,
            "error": f"Missing script: {script_name}",
        }

    log_file = BASE_DIR / (Path(script_name).stem + "_from_command_center.log")

    with open(log_file, "a", encoding="utf-8") as out:
        proc = subprocess.Popen(
            [sys.executable, str(path)],
            cwd=str(BASE_DIR),
            stdout=out,
            stderr=out,
            creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0,
        )

    return {
        "started": True,
        "script": script_name,
        "pid": proc.pid,
        "log": str(log_file),
    }


def status_report():
    result = {
        "pc_id": PC_ID,
        "device_type": DEVICE_TYPE,
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": sys.version,
        "cwd": str(BASE_DIR),
        "time": int(time.time()),
    }

    try:
        import psutil
        result["cpu_percent"] = psutil.cpu_percent(interval=0.2)
        result["ram_percent"] = psutil.virtual_memory().percent
    except Exception as e:
        result["psutil_error"] = str(e)

    return result


def execute_command(command):
    command_id = command.get("command_id")
    command_type = str(command.get("command_type") or "").upper().strip()

    log(f"Executing {command_type} command_id={command_id}")

    if command_type == "PING":
        return "completed", {"pong": True, "pc_id": PC_ID, "time": int(time.time())}, ""

    if command_type == "STATUS_REPORT":
        return "completed", status_report(), ""

    if command_type == "START_DASHBOARD":
        return "completed", start_python_script("start_dashboard.py"), ""

    if command_type == "START_MOBILE_WORKER":
        return "completed", start_python_script("mobile_worker.py"), ""

    if command_type == "START_SYNC":
        return "completed", start_python_script("sync_updates_to_main.py"), ""

    if command_type == "MARK_AVAILABLE":
        return "completed", {"device_state": "available", "pc_id": PC_ID}, ""

    if command_type == "MARK_UNAVAILABLE":
        return "completed", {"device_state": "unavailable", "pc_id": PC_ID}, ""

    if command_type == "STOP_COMMAND_WORKER":
        return "completed", {"stopping": True, "pc_id": PC_ID}, "STOP_AFTER_COMPLETE"

    return "failed", {}, f"Unsupported command_type: {command_type}"


def main():
    log(f"Starting. PC_ID={PC_ID} DEVICE_TYPE={DEVICE_TYPE} COORDINATOR={COORDINATOR_URL}")

    register_worker()

    last_heartbeat = 0

    while True:
        now = time.time()

        if now - last_heartbeat >= 20:
            heartbeat()
            last_heartbeat = now

        commands = claim_commands()

        for command in commands:
            command_id = command.get("command_id")

            try:
                status, result, error = execute_command(command)

                stop_after = error == "STOP_AFTER_COMPLETE"
                if stop_after:
                    error = ""

                complete_command(command_id, status=status, result=result, error=error)

                if stop_after:
                    log("STOP_COMMAND_WORKER received. Exiting.")
                    return

            except Exception as e:
                complete_command(command_id, status="failed", result={}, error=str(e))

        time.sleep(5)


if __name__ == "__main__":
    main()
