import json
import os
import socket
import subprocess
import time

import requests


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "mobile_worker_config.json")


DEFAULT_CONFIG = {
    "COORDINATOR_URL": "http://100.68.214.2:9555",
    "PC_ID": "PHONE-01",
    "DEVICE_TYPE": "Phone",
    "HOSTNAME": "",
    "NETWORK_TYPE": "WiFi",
    "HEARTBEAT_SECONDS": 30
}


def load_config():
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        return DEFAULT_CONFIG.copy()

    with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        loaded = json.load(f)

    config = DEFAULT_CONFIG.copy()
    config.update(loaded)
    return config


def try_termux_battery():
    """
    Works on Android Termux if termux-api is installed:
        pkg install termux-api
        Install the Termux:API Android app too.
    """
    try:
        result = subprocess.run(
            ["termux-battery-status"],
            capture_output=True,
            text=True,
            timeout=4
        )

        if result.returncode != 0:
            return None

        data = json.loads(result.stdout or "{}")

        percent = data.get("percentage")
        status = str(data.get("status") or "").lower()
        plugged = str(data.get("plugged") or "").lower()

        charging = (
            "charging" in status
            or plugged not in ["", "unplugged", "none"]
        )

        return {
            "battery_percent": int(percent) if percent is not None else None,
            "charging": charging
        }

    except Exception:
        return None


def build_payload(config):
    battery = try_termux_battery() or {
        "battery_percent": None,
        "charging": False
    }

    hostname = config.get("HOSTNAME") or socket.gethostname()

    return {
        "pc_id": config.get("PC_ID", "PHONE-01"),
        "hostname": hostname,
        "device_type": config.get("DEVICE_TYPE", "Phone"),
        "device_role": "Worker Phone",
        "battery_percent": battery.get("battery_percent"),
        "charging": bool(battery.get("charging")),
        "network_type": config.get("NETWORK_TYPE", "WiFi"),
        "can_launch_profiles": False,
        "can_run_mobile_tasks": True,
        "can_control_fleet": False,
        "can_be_blocked": True,
        "worker_version": "mobile-worker-1",
        "device_note": "Phone/mobile heartbeat worker"
    }


def post_json(url, payload, timeout=8):
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def main():
    config = load_config()
    coordinator = str(config.get("COORDINATOR_URL") or "").rstrip("/")
    heartbeat_seconds = int(config.get("HEARTBEAT_SECONDS") or 30)

    if not coordinator:
        raise SystemExit("COORDINATOR_URL is required in mobile_worker_config.json")

    register_url = f"{coordinator}/api/workers/register"

    # Compatibility mode:
    # Some coordinator versions do not expose /api/workers/heartbeat.
    # /api/workers/register also refreshes last_seen, so we use it as the heartbeat endpoint.
    heartbeat_url = f"{coordinator}/api/workers/register"

    payload = build_payload(config)

    print(f"[MobileWorker] Registering {payload['pc_id']} -> {coordinator}")
    result = post_json(register_url, payload)
    print(f"[MobileWorker] Register result: {result}")

    while True:
        try:
            payload = build_payload(config)
            result = post_json(heartbeat_url, payload)

            blocked = result.get("blocked")
            reason = result.get("blocked_reason") or ""

            print(
                f"[MobileWorker] Heartbeat OK | "
                f"id={payload['pc_id']} | "
                f"battery={payload.get('battery_percent')} | "
                f"charging={payload.get('charging')} | "
                f"blocked={blocked} | "
                f"reason={reason}"
            )

        except Exception as e:
            print(f"[MobileWorker] Heartbeat failed: {e}")

        time.sleep(heartbeat_seconds)


if __name__ == "__main__":
    main()