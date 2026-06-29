import webview
import psutil
import threading
import time
import os
import sys
import logging
import socket
import requests
import re
import hashlib
import random

# Force UTF-8 console output on Windows.
# Prevents crashes when print() contains emojis/special characters and output is piped to Tee-Object.
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
    
logging.getLogger('pywebview').setLevel(logging.CRITICAL)

# Import our new engines
from engine.db_manager import DatabaseManager
from engine.ghost_core import GhostCore

# --- CONFIGURATION ---
# --- SYSTEM PATHS ---
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_CONFIG_PATH = os.path.join(BASE_DIR, "local_config.json")

DEFAULT_LOCAL_CONFIG = {
    "COMET_PATH": r"C:\Users\newave\AppData\Local\Perplexity\Comet\Application\comet.exe",
    "CHROMEDRIVER_PATH": r"C:\Users\newave\.cache\selenium\chromedriver\win64\140.0.7339.207\chromedriver.exe",
    "PROTON_VPN_PATH": os.path.join(
        BASE_DIR,
        "extension_template",
        "Extensions",
        "jplgfhpmjnbigmhklmmbgecoobifkmpa",
        "1.2.16_0"
    ),
    "HOME_IP": "190.110.36.47",
    "PC_ID": socket.gethostname(),

    # Device identity:
    # PC, Laptop, Phone, Tablet, or blank for auto-detect.
    "DEVICE_TYPE": "",

    "COORDINATOR_URL": ""
}

def load_local_config():
    if not os.path.exists(LOCAL_CONFIG_PATH):
        with open(LOCAL_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_LOCAL_CONFIG, f, indent=4)
        print(f"[System] Created default local_config.json at: {LOCAL_CONFIG_PATH}")
        return DEFAULT_LOCAL_CONFIG

    with open(LOCAL_CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        loaded = json.load(f)

    config = DEFAULT_LOCAL_CONFIG.copy()
    config.update(loaded)
    return config

LOCAL_CONFIG = load_local_config()

COMET_PATH = LOCAL_CONFIG["COMET_PATH"]
CHROMEDRIVER_PATH = LOCAL_CONFIG["CHROMEDRIVER_PATH"]
PROTON_VPN_PATH = LOCAL_CONFIG["PROTON_VPN_PATH"]
HOME_IP = LOCAL_CONFIG["HOME_IP"]
PC_ID = LOCAL_CONFIG.get("PC_ID", socket.gethostname())
DEVICE_TYPE = str(LOCAL_CONFIG.get("DEVICE_TYPE", "") or "").strip()
COORDINATOR_URL = (LOCAL_CONFIG.get("COORDINATOR_URL") or "").rstrip("/")

print("[System] Loaded local PC config:")
print(f"[System] COMET_PATH: {COMET_PATH}")
print(f"[System] CHROMEDRIVER_PATH: {CHROMEDRIVER_PATH}")
print(f"[System] PROTON_VPN_PATH: {PROTON_VPN_PATH}")
print(f"[System] HOME_IP: {HOME_IP}")
print(f"[System] PC_ID: {PC_ID}")
print(f"[System] DEVICE_TYPE: {DEVICE_TYPE or 'auto'}")
print(f"[System] COORDINATOR_URL: {COORDINATOR_URL}")

# ---------------------

import subprocess

class BackendAPI:
    def __init__(self):
        print("[System] Initializing Ghost HQ Backend...")
        self.window = None
        self.db = DatabaseManager()
        self.db.reset_all_statuses()
        
        if len(self.db.get_all_profiles()) == 0:
            for i in range(1, 11):
                self.db.create_profile(f"Profile {i}", "Pending Execution")

        self.ghost_core = GhostCore(
            self.db,
            COMET_PATH,
            CHROMEDRIVER_PATH,
            PROTON_VPN_PATH,
            HOME_IP,
            state_callback=self._on_ghost_profile_state,
            ip_blacklist_callback=self.is_ip_blacklisted
        )
        self._ensure_saved_hardware_profiles()
        
        # --- NEW: Network State Tracking ---
        self.last_net_io = psutil.net_io_counters()
        self.last_net_time = time.time()
        
        # --- NEW: Hardware Detection ---
        self.gpu_name = self._detect_gpu_names()

        # --- Central Coordinator State ---
        self.coordinator_owned_profile_ids = set()
        self.profile_runtime_cache = {}
        self.autoscale_managed_profile_ids = set()
        self.autoscale_last_action_at = 0
        self.autoscale_lock = threading.Lock()
        self.profile_watchdog_last_alert = {}
        self.profile_watchdog_lock = threading.Lock()

        # PC Control / coordinator block state.
        self.is_blocked_by_coordinator = False
        self.blocked_reason = ""

        # Coordinator is optional.
        # Laptop must still open, edit code, create local profiles, and test locally
        # when the main PC coordinator is offline.
        self.coordinator_online = False
        self.coordinator_offline_until = 0
        self.coordinator_last_error = None
        self.coordinator_last_log_time = 0

        # Try once. If it fails, dashboard continues locally.
        self._register_with_coordinator()

        self.autoscale_thread = threading.Thread(
            target=self._autoscale_background_loop,
            daemon=True,
            name="CometAutoscaleLoop"
        )
        self.autoscale_thread.start()

        self.profile_watchdog_thread = threading.Thread(
            target=self._profile_watchdog_loop,
            daemon=True,
            name="CometProfileWatchdog"
        )
        self.profile_watchdog_thread.start()

    def _coordinator_enabled(self):
        return bool(COORDINATOR_URL)

    def _coordinator_url(self, path):
        return f"{COORDINATOR_URL}{path}"

    def _coordinator_request(self, method, path, payload=None, timeout=1, quiet=False, force=False):
        """
        Optional central coordinator request.

        If the main PC coordinator is offline:
        - fail fast
        - enter cooldown
        - do not spam timeout errors
        - let the laptop keep working locally
        """
        if not self._coordinator_enabled():
            return None

        now = time.time()

        if not hasattr(self, "coordinator_online"):
            self.coordinator_online = False
        if not hasattr(self, "coordinator_offline_until"):
            self.coordinator_offline_until = 0
        if not hasattr(self, "coordinator_last_error"):
            self.coordinator_last_error = None
        if not hasattr(self, "coordinator_last_log_time"):
            self.coordinator_last_log_time = 0

        # If coordinator failed recently, do not retry every dashboard refresh.
        if not force and self.coordinator_offline_until > now:
            return None

        try:
            response = requests.request(
                method,
                self._coordinator_url(path),
                json=payload,
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=timeout
            )

            self.coordinator_online = True
            self.coordinator_offline_until = 0
            self.coordinator_last_error = None

            if response.status_code in (400, 403, 404, 409):
                try:
                    return response.json()
                except Exception:
                    return {"ok": False, "error": response.text}

            response.raise_for_status()
            return response.json()

        except Exception as e:
            self.coordinator_online = False
            self.coordinator_last_error = str(e)

            # Wait 5 minutes before trying again automatically.
            self.coordinator_offline_until = time.time() + 300

            # Print only once every 5 minutes unless forced.
            if not quiet and (time.time() - self.coordinator_last_log_time > 300):
                self.coordinator_last_log_time = time.time()
                print(f"[Coordinator] Offline/unreachable. Dashboard will keep running locally. Last error: {e}")

            return None

    def _register_with_coordinator(self):
        if not self._coordinator_enabled():
            print("[Coordinator] Disabled: no COORDINATOR_URL configured.")
            return

        result = self._coordinator_request(
            "POST",
            "/api/workers/register",
            self._current_worker_identity_payload(),
            timeout=1,
            quiet=False,
            force=True
        )

        if result and result.get("ok"):
            if result.get("blocked"):
                self.is_blocked_by_coordinator = True
                self.blocked_reason = result.get("blocked_reason") or "This PC is blocked by coordinator."
                print(f"[Coordinator] BLOCKED: {PC_ID} cannot run profiles. Reason: {self.blocked_reason}")
            else:
                self.is_blocked_by_coordinator = False
                self.blocked_reason = ""
                print(f"[Coordinator] Register result: {result}")
        else:
            print("[Coordinator] Main PC coordinator unavailable. Laptop is running in LOCAL mode.")

    def _hardware_profile_json(self, hardware):
        return json.dumps(hardware or {}, sort_keys=True)

    def _hardware_profile_from_text(self, value):
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip().startswith("{"):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return None
        return None

    def _hardware_display_from_value(self, value):
        parsed = self._hardware_profile_from_text(value)
        if parsed:
            return parsed.get("display_string") or parsed.get("device_name") or "Mobile Device"
        return value or "Pending Execution"

    def _used_device_signatures(self, profiles=None):
        signatures = set()
        for profile in profiles or self.db.get_all_profiles():
            hardware = (
                profile.get("hardware_profile")
                or self._hardware_profile_from_text(profile.get("hardware_profile_json"))
                or self._hardware_profile_from_text(profile.get("hardware_cloak"))
            )
            if not isinstance(hardware, dict):
                continue
            signature = hardware.get("fingerprint_signature") or hardware.get("fingerprint_id")
            if signature:
                signatures.add(str(signature))
            device_name = hardware.get("device_name")
            if device_name:
                signatures.add(f"device:{device_name}")
        return signatures

    def _is_desktop_hardware(self, hardware):
        if not isinstance(hardware, dict):
            return False
        type_text = str(hardware.get("type") or "").strip().lower()
        if type_text in {"desktop", "pc", "computer"}:
            return True
        os_text = str(hardware.get("os") or "").strip().lower()
        return os_text in {"windows", "macos", "linux"} and not bool(hardware.get("mobile", False))

    def _hardware_kind_counts(self, profiles):
        desktop = 0
        mobile = 0
        for profile in profiles or []:
            hardware = (
                profile.get("hardware_profile")
                or self._hardware_profile_from_text(profile.get("hardware_profile_json"))
                or self._hardware_profile_from_text(profile.get("hardware_cloak"))
            )
            if not isinstance(hardware, dict):
                continue
            if self._is_desktop_hardware(hardware):
                desktop += 1
            else:
                mobile += 1
        return desktop, mobile

    def _target_desktop_count(self, total_profiles):
        return int((int(total_profiles or 0) * 0.30) + 0.5)

    def _next_hardware_type(self, profiles):
        desktop_count, _ = self._hardware_kind_counts(profiles)
        target_desktop_count = self._target_desktop_count(len(profiles or []) + 1)
        return "Desktop" if desktop_count < target_desktop_count else "Mobile"

    def _next_profile_number(self, profiles):
        numbers = []
        for profile in profiles or []:
            try:
                numbers.append(int(profile.get("id")))
            except Exception:
                pass
            name = str(profile.get("name") or "")
            match = re.search(r"(\d+)$", name)
            if match:
                try:
                    numbers.append(int(match.group(1)))
                except Exception:
                    pass
        return (max(numbers) + 1) if numbers else 1

    def _ensure_saved_hardware_profiles(self):
        profiles = self.db.get_all_profiles()
        signatures = self._used_device_signatures(profiles)
        working_profiles = []
        updated = 0

        for profile in profiles:
            hardware = (
                profile.get("hardware_profile")
                or self._hardware_profile_from_text(profile.get("hardware_profile_json"))
                or self._hardware_profile_from_text(profile.get("hardware_cloak"))
            )
            is_saved_device = (
                isinstance(hardware, dict)
                and hardware.get("schema") == "comet_device_identity_v2"
                and str(hardware.get("type", "")).lower() in {"mobile", "desktop"}
            )

            if is_saved_device:
                working_profiles.append({"hardware_profile": hardware})
                continue

            profile_id = int(profile.get("id"))
            hardware_type = self._next_hardware_type(working_profiles)
            hardware = self.ghost_core._generate_hardware_cloak(
                profile_id,
                existing_signatures=signatures,
                forced_type=hardware_type
            )
            signatures.add(hardware.get("fingerprint_signature", ""))
            if hardware.get("device_name"):
                signatures.add(f"device:{hardware['device_name']}")
            working_profiles.append({"hardware_profile": hardware})

            if self.db.update_profile_hardware(
                profile_id,
                hardware.get("display_string", "Device"),
                self._hardware_profile_json(hardware)
            ):
                updated += 1

        if updated:
            print(f"[Hardware] Assigned saved device identities to {updated} profile(s).")

    def _get_coordinator_profiles(self, force=False):
        result = self._coordinator_request(
            "GET",
            "/api/profiles",
            timeout=1,
            quiet=True,
            force=force
        )

        if not result or not result.get("ok"):
            return None

        mapped = []
        for p in result.get("profiles", []):
            pid = p.get("id")
            ip = p.get("ip_origin") or "Not verified"

            if str(ip).lower() in ["unknown", "none", ""]:
                ip = "Not verified"

            hardware_raw = p.get("hardware_profile_json") or p.get("hardware_cloak") or "Pending Execution"
            hardware_profile = self._hardware_profile_from_text(hardware_raw)
            hardware_json = self._hardware_profile_json(hardware_profile) if hardware_profile else ""

            mapped.append({
                "id": pid,
                "profile_id": pid,
                "name": p.get("name", f"Profile {pid}"),
                "status": p.get("status", "OFFLINE"),
                "current_target": p.get("current_target", "None"),
                "currentTarget": p.get("current_target", "None"),
                "target": p.get("current_target", "None"),
                "hardware_cloak": self._hardware_display_from_value(hardware_raw),
                "hardware_profile_json": hardware_json,
                "hardware_profile": hardware_profile,
                "ip_origin": ip,
                "ipOrigin": ip,
                "ip": ip,
                "last_ip": ip,
                "locked_by": p.get("locked_by") or "",
                "lease_until": p.get("lease_until")
            })

        return mapped

    def _create_coordinator_profile(self, name, hardware_cloak, hardware_profile_json=""):
        return self._coordinator_request(
            "POST",
            "/api/profiles/create",
            {
                "name": name,
                "hardware_cloak": hardware_cloak,
                "hardware_profile_json": hardware_profile_json or ""
            }
        )

    def _acquire_coordinator_profile(self, profile_id, target="Manual"):
        result = self._coordinator_request(
            "POST",
            f"/api/profiles/{int(profile_id)}/acquire",
            {
                "pc_id": PC_ID,
                "current_target": target
            }
        )

        if result and result.get("ok"):
            self.coordinator_owned_profile_ids.add(int(profile_id))
            return True, result

        return False, result

    def _release_coordinator_profile(self, profile_id, force=False):
        result = self._coordinator_request(
            "POST",
            f"/api/profiles/{int(profile_id)}/release",
            {
                "pc_id": PC_ID,
                "force": force
            }
        )
        self.coordinator_owned_profile_ids.discard(int(profile_id))
        return result

    def _release_all_coordinator_profiles(self):
        result = self._coordinator_request(
            "POST",
            "/api/profiles/release-by-pc",
            {
                "pc_id": PC_ID
            }
        )
        self.coordinator_owned_profile_ids.clear()
        return result

    def _send_coordinator_heartbeat(self, profile_id, current_target=None, ip_origin=None):
        payload = {
            "pc_id": PC_ID,
            "current_target": current_target or "",
            "ip_origin": ip_origin or ""
        }
        return self._coordinator_request(
            "POST",
            f"/api/profiles/{int(profile_id)}/heartbeat",
            payload,
            timeout=3
        )

    def _classify_profile_lifecycle(self, status=None, target_platform=None, active=False):
        status_text = str(status or "").strip().upper()
        target_text = str(target_platform or "").strip()
        target_lower = target_text.lower()

        state = "UNKNOWN"
        stage = "Waiting for state update"
        severity = "info"

        if status_text in {"OFFLINE", "CLOSED"}:
            state = "OFFLINE"
            stage = "Idle"
        elif status_text in {"STOPPING", "STOPPED"} or "stop" in target_lower:
            state = "STOPPING"
            stage = "Stopping browser"
        elif status_text in {"STARTING", "LAUNCHING"} or target_lower in {"launching", "pending execution"}:
            state = "LAUNCHING"
            stage = "Launching browser"
        elif status_text in {"RETRYING", "RETRY"}:
            state = "RETRYING"
            stage = "Retrying after a failed check"
            severity = "warning"
        elif status_text in {"BLACKLISTED", "BLOCKED", "LOCKED"}:
            state = "BLOCKED"
            stage = target_text or status_text.title()
            severity = "warning"
        elif status_text in {"FAILED", "ERROR"}:
            state = "FAILED"
            stage = target_text or status_text.title()
            severity = "error"
        elif status_text == "RUNNING":
            if target_lower in {"verified", "ip verified"}:
                state = "IP_VERIFIED"
                stage = "IP verified; waiting for next route"
            elif "ip unknown" in target_lower:
                state = "IP_UNKNOWN"
                stage = "Running with unknown IP status"
                severity = "warning"
            elif target_lower in {"manual", "none", ""}:
                state = "MANUAL_RUNNING" if target_lower == "manual" else "RUNNING"
                stage = "Manual browser open" if target_lower == "manual" else "Running"
            else:
                state = "ROUTED"
                stage = f"Routed to {target_text}"
        elif active:
            state = "ACTIVE_UNKNOWN"
            stage = target_text or "Active session without clear status"
            severity = "warning"
        else:
            state = status_text or "UNKNOWN"
            stage = target_text or status_text.title() or "Unknown"

        return {
            "state": state,
            "stage": stage,
            "severity": severity
        }

    def _profile_lifecycle_threshold(self, state, status=None, target_platform=None):
        state_text = str(state or "").upper()
        status_text = str(status or "").upper()
        target_lower = str(target_platform or "").lower()

        if state_text == "LAUNCHING":
            return 120
        if state_text == "IP_VERIFIED":
            return 150
        if state_text in {"IP_UNKNOWN", "RETRYING", "ACTIVE_UNKNOWN"}:
            return 180
        if state_text == "STOPPING":
            return 240
        if status_text in {"STARTING", "LAUNCHING"} or target_lower == "launching":
            return 120
        return 0

    def _record_profile_lifecycle_from_cache(self, profile_id, source="state_callback", force_event=False, details=None):
        try:
            profile_id = int(profile_id)
            cache = self.profile_runtime_cache.get(profile_id, {}) if isinstance(self.profile_runtime_cache, dict) else {}
            active_sessions = getattr(getattr(self, "ghost_core", None), "active_sessions", {}) or {}
            session = active_sessions.get(profile_id, {}) if isinstance(active_sessions, dict) else {}
            lifecycle = self._classify_profile_lifecycle(
                cache.get("status"),
                cache.get("current_target"),
                active=profile_id in active_sessions
            )
            entered_at = float(cache.get("state_entered_at") or cache.get("last_state_at") or time.time())
            elapsed = max(0, int(time.time() - entered_at))
            payload = {
                "profile_id": profile_id,
                "session_id": session.get("session_id", "") if isinstance(session, dict) else "",
                "state": lifecycle.get("state"),
                "status": cache.get("status") or "",
                "stage": lifecycle.get("stage"),
                "target_platform": cache.get("current_target") or "",
                "ip_address": cache.get("ip_origin") or cache.get("ip_address") or "",
                "source": source,
                "severity": lifecycle.get("severity") or "info",
                "elapsed_seconds": elapsed,
                "force_event": force_event,
                "details": details if isinstance(details, dict) else {}
            }
            if hasattr(self.db, "record_profile_lifecycle"):
                return self.db.record_profile_lifecycle(payload)
        except Exception as e:
            print(f"[Lifecycle] Could not record lifecycle for Profile {profile_id}: {e}")
        return {"ok": False}

    def _on_ghost_profile_state(self, profile_id, status=None, ip_address=None, target_platform=None):
        """Receives live updates from GhostCore and forwards them to the coordinator."""
        profile_id = int(profile_id)

        now = time.time()
        cache = self.profile_runtime_cache.setdefault(profile_id, {})
        previous_state = cache.get("lifecycle_state")
        previous_status = cache.get("status")
        previous_target = cache.get("current_target")

        if status is not None:
            cache["status"] = status
        if ip_address is not None:
            cache["ip_origin"] = ip_address
            cache["ip_address"] = ip_address
        if target_platform is not None:
            cache["current_target"] = target_platform

        lifecycle = self._classify_profile_lifecycle(
            cache.get("status"),
            cache.get("current_target"),
            active=profile_id in (getattr(getattr(self, "ghost_core", None), "active_sessions", {}) or {})
        )
        signature_changed = (
            previous_state != lifecycle.get("state")
            or previous_status != cache.get("status")
            or previous_target != cache.get("current_target")
        )
        if signature_changed or not cache.get("state_entered_at"):
            cache["state_entered_at"] = now
        cache["last_state_at"] = now
        cache["lifecycle_state"] = lifecycle.get("state")
        cache["lifecycle_stage"] = lifecycle.get("stage")
        cache["lifecycle_severity"] = lifecycle.get("severity")

        self._record_profile_lifecycle_from_cache(
            profile_id,
            source="state_callback",
            force_event=False,
            details={
                "status_changed": previous_status != cache.get("status"),
                "target_changed": previous_target != cache.get("current_target")
            }
        )

        # Local analytics trail. This is intentionally lightweight:
        # only state/IP/platform changes generate rows.
        try:
            event_type = "PROFILE_STATE"
            status_text_for_event = str(status or "").upper()
            if status_text_for_event == "RUNNING":
                event_type = "SESSION_STARTED"
            elif status_text_for_event == "OFFLINE":
                event_type = "SESSION_ENDED"
            elif ip_address:
                event_type = "IP_VERIFIED"
            elif target_platform:
                event_type = "PLATFORM_OPENED"

            self.db.record_analytics_event(
                profile_id=profile_id,
                pc_id=PC_ID,
                platform=cache.get("current_target") or target_platform or "",
                ip_label=cache.get("ip_origin") or ip_address or "",
                event_type=event_type,
                details=f"status={status or ''}; target={target_platform or ''}"
            )
        except Exception as e:
            print(f"[Analytics] State event record failed for Profile {profile_id}: {e}")

        if not self._coordinator_enabled():
            return

        status_text = str(status or cache.get("status") or "").upper()

        if status_text == "OFFLINE":
            if profile_id in self.coordinator_owned_profile_ids:
                result = self._release_coordinator_profile(profile_id)
                print(f"[Coordinator] Released Profile {profile_id}: {result}")
            return

        if profile_id in self.coordinator_owned_profile_ids:
            result = self._send_coordinator_heartbeat(
                profile_id,
                current_target=cache.get("current_target") or "Manual",
                ip_origin=cache.get("ip_origin") or ""
            )
            if result and result.get("error") == "not_lock_owner":
                print(f"[Coordinator] Lost ownership of Profile {profile_id}. Removing from local ownership set.")
                self.coordinator_owned_profile_ids.discard(profile_id)

    def send_coordinator_heartbeats(self):
        if not self._coordinator_enabled():
            return

        # If coordinator is offline, do not keep trying heartbeats.
        if not getattr(self, "coordinator_online", False):
            return

        for pid in list(self.coordinator_owned_profile_ids):
            cache = self.profile_runtime_cache.get(pid, {})

            result = self._send_coordinator_heartbeat(
                pid,
                current_target=cache.get("current_target") or "Manual",
                ip_origin=cache.get("ip_origin") or ""
            )

            if result and result.get("error") == "not_lock_owner":
                print(f"[Coordinator] Lost ownership of Profile {pid}. Removing local heartbeat.")
                self.coordinator_owned_profile_ids.discard(pid)

    def check_worker_block_status(self):
        """Checks whether this PC has been blocked by the coordinator."""
        if not self._coordinator_enabled():
            return False

        result = self._coordinator_request(
            "POST",
            "/api/workers/heartbeat",
            self._current_worker_identity_payload(),
            timeout=1,
            quiet=True
        )

        if result and result.get("ok"):
            if result.get("blocked"):
                self.is_blocked_by_coordinator = True
                self.blocked_reason = result.get("blocked_reason") or "This PC is blocked by coordinator."
                print(f"[Coordinator] BLOCKED: {PC_ID}. Stopping local fleet. Reason: {self.blocked_reason}")
                try:
                    self.ghost_core.abort_fleet()
                except Exception as e:
                    print(f"[Coordinator] Could not abort local fleet after block: {e}")
                return True

            self.is_blocked_by_coordinator = False
            self.blocked_reason = ""
            return False

        return bool(getattr(self, "is_blocked_by_coordinator", False))

    def get_worker_data(self):
        """Returns all devices registered with the coordinator for the PC Control tab."""
        if not self._coordinator_enabled():
            local_worker = {
                "pc_id": PC_ID,
                "hostname": socket.gethostname(),
                "ip_address": "local",
                "display_status": "LOCAL ONLY",
                "status": "LOCAL ONLY",
                "blocked": False,
                "blocked_reason": "Coordinator URL is not configured.",
                "active_profiles": len(getattr(self.ghost_core, "active_sessions", {}) or {}),
                "seconds_since_seen": 0
            }

            local_worker.update(
                self._build_device_capabilities(
                    pc_id=local_worker["pc_id"],
                    hostname=local_worker["hostname"],
                    blocked=local_worker["blocked"],
                    status=local_worker["status"],
                    default_type="PC"
                )
            )

            return {
                "ok": True,
                "coordinator_online": False,
                "workers": [local_worker]
            }

        result = self._coordinator_request(
            "GET",
            "/api/workers",
            timeout=2,
            quiet=True,
            force=True
        )

        if result and result.get("ok"):
            workers = result.get("workers", [])

            enriched_workers = []
            for worker in workers:
                item = dict(worker or {})
                blocked = item.get("blocked") is True or str(item.get("blocked")).lower() in ["1", "true", "yes"]
                status = item.get("display_status") or item.get("status") or "UNKNOWN"

                item.update(
                    self._build_device_capabilities(
                        pc_id=item.get("pc_id") or "",
                        hostname=item.get("hostname") or "",
                        blocked=blocked,
                        status=status,
                        default_type="Unknown"
                    )
                )

                enriched_workers.append(item)

            return {
                "ok": True,
                "coordinator_online": True,
                "workers": enriched_workers
            }

        return {
            "ok": False,
            "coordinator_online": False,
            "error": self.coordinator_last_error or "Coordinator unavailable",
            "workers": []
        }

    def block_worker(self, pc_id):
        """Blocks a PC at the coordinator and releases its profile locks."""
        pc_id = str(pc_id or "").strip()
        if not pc_id:
            return {"ok": False, "error": "pc_id required"}

        result = self._coordinator_request(
            "POST",
            f"/api/workers/{pc_id}/block",
            {
                "hostname": "",
                "reason": f"Blocked from {PC_ID} dashboard"
            },
            timeout=2,
            quiet=False,
            force=True
        )

        if pc_id == PC_ID and result and result.get("ok"):
            self.is_blocked_by_coordinator = True
            self.blocked_reason = "Blocked from dashboard"
            try:
                self.ghost_core.abort_fleet()
            except Exception:
                pass

        return result or {"ok": False, "error": self.coordinator_last_error or "Coordinator unavailable"}

    def unblock_worker(self, pc_id):
        """Unblocks a PC at the coordinator."""
        pc_id = str(pc_id or "").strip()
        if not pc_id:
            return {"ok": False, "error": "pc_id required"}

        result = self._coordinator_request(
            "POST",
            f"/api/workers/{pc_id}/unblock",
            {},
            timeout=2,
            quiet=False,
            force=True
        )

        if pc_id == PC_ID and result and result.get("ok"):
            self.is_blocked_by_coordinator = False
            self.blocked_reason = ""

        return result or {"ok": False, "error": self.coordinator_last_error or "Coordinator unavailable"}


    # ==============================
    # Mobile Task Queue Dashboard Bridge
    # ==============================

    def get_mobile_tasks(self, pc_id="", status="", limit=50):
        """Returns recent mobile task queue rows from the coordinator."""
        try:
            if not self._coordinator_enabled():
                return {
                    "ok": False,
                    "error": "Coordinator URL is not configured.",
                    "tasks": []
                }

            import urllib.parse

            clean_pc_id = str(pc_id or "").strip()
            clean_status = str(status or "").strip().upper()

            try:
                clean_limit = int(limit or 50)
            except Exception:
                clean_limit = 50

            clean_limit = max(1, min(clean_limit, 200))

            params = {
                "limit": clean_limit
            }

            if clean_pc_id:
                params["pc_id"] = clean_pc_id

            if clean_status:
                params["status"] = clean_status

            query = urllib.parse.urlencode(params)

            result = self._coordinator_request(
                "GET",
                f"/api/mobile/tasks?{query}",
                timeout=4,
                quiet=True,
                force=True
            )

            return result or {
                "ok": False,
                "error": self.coordinator_last_error or "Coordinator unavailable or mobile task API missing.",
                "tasks": []
            }

        except Exception as e:
            print(f"[MobileTasks] get_mobile_tasks failed: {e}")
            return {
                "ok": False,
                "error": str(e),
                "tasks": []
            }

    def create_mobile_task(self, pc_id, task_type, payload=None):
        """Creates a mobile task for a phone/mobile worker through the coordinator."""
        try:
            if not self._coordinator_enabled():
                return {
                    "ok": False,
                    "error": "Coordinator URL is not configured."
                }

            clean_pc_id = str(pc_id or "").strip()
            clean_task_type = str(task_type or "").strip().upper()

            if not clean_pc_id:
                return {
                    "ok": False,
                    "error": "pc_id is required"
                }

            if not clean_task_type:
                return {
                    "ok": False,
                    "error": "task_type is required"
                }

            allowed_tasks = {
                "PING",
                "STATUS_SNAPSHOT",
                "BATTERY_REPORT",
                "MARK_AVAILABLE",
                "MARK_UNAVAILABLE",
                "STOP_WORKER"
            }

            if clean_task_type not in allowed_tasks:
                return {
                    "ok": False,
                    "error": f"Unsupported task_type: {clean_task_type}",
                    "allowed_tasks": sorted(list(allowed_tasks))
                }

            safe_payload = payload if isinstance(payload, dict) else {}

            result = self._coordinator_request(
                "POST",
                "/api/mobile/tasks/create",
                {
                    "pc_id": clean_pc_id,
                    "task_type": clean_task_type,
                    "payload": safe_payload,
                    "created_by": f"{PC_ID}-dashboard"
                },
                timeout=4,
                quiet=False,
                force=True
            )

            return result or {
                "ok": False,
                "error": self.coordinator_last_error or "Coordinator unavailable or mobile task API missing."
            }

        except Exception as e:
            print(f"[MobileTasks] create_mobile_task failed: {e}")
            return {
                "ok": False,
                "error": str(e)
            }


    # ==============================
    # Backup + Rollback Manager Bridge
    # ==============================

    def _backup_manager_root(self):
        from pathlib import Path
        root = Path(__file__).resolve().parent / "_archive" / "backups" / "system"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _backup_manager_manifest(self):
        return [
            "coordinator_server.py",
            "start_dashboard.py",
            "mobile_worker.py",
            "health_check.py",
            "sync_updates_to_main.py",
            "apply_incoming_updates.py",
            "ui/index.html",
            "ui/app.js",
            "ui/style.css",
            "engine/db_manager.py",
            "engine/ghost_core.py",
            "engine/session_recorder.py",
            "engine/platform_runners/__init__.py",
            "engine/platform_runners/base_runner.py",
            "engine/platform_runners/youtube_runner.py",
            "engine/platform_runners/twitch_runner.py",
            "engine/platform_runners/spotify_runner.py",
            "engine/platform_runners/deezer_runner.py",
            "RUN_MAIN_COORDINATOR.bat",
            "RUN_MAIN_DASHBOARD.bat",
            "RUN_LAPTOP_SYNC.bat",
            "RUN_LAPTOP_DASHBOARD.bat",
            "RUN_LAPTOP_MOBILE_WORKER.bat"
        ]

    def _backup_manager_safe_id(self, value):
        import re
        clean = re.sub(r"[^A-Za-z0-9_\-\.]", "_", str(value or "").strip())
        return clean[:120]

    def _backup_manager_dir_size(self, folder):
        total = 0
        try:
            for path in folder.rglob("*"):
                if path.is_file():
                    total += path.stat().st_size
        except Exception:
            pass
        return total

    def _backup_manager_format_size(self, size_bytes):
        try:
            n = float(size_bytes or 0)
            for unit in ["B", "KB", "MB", "GB"]:
                if n < 1024:
                    return f"{n:.1f} {unit}"
                n = n / 1024
            return f"{n:.1f} TB"
        except Exception:
            return "0 B"

    def get_backup_manager_status(self):
        """Lists available local system backups."""
        try:
            import json
            from pathlib import Path

            root = self._backup_manager_root()
            backups = []

            for folder in sorted(root.iterdir(), reverse=True):
                if not folder.is_dir():
                    continue

                manifest_path = folder / "backup_manifest.json"

                manifest = {}
                if manifest_path.exists():
                    try:
                        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    except Exception:
                        manifest = {}

                files = manifest.get("files", [])
                if not isinstance(files, list):
                    files = []

                size_bytes = self._backup_manager_dir_size(folder)

                backups.append({
                    "backup_id": folder.name,
                    "label": manifest.get("label", ""),
                    "created_at": manifest.get("created_at", ""),
                    "created_by": manifest.get("created_by", ""),
                    "file_count": len(files),
                    "size_bytes": size_bytes,
                    "size_text": self._backup_manager_format_size(size_bytes),
                    "path": str(folder),
                    "files": files[:200]
                })

            return {
                "ok": True,
                "backup_root": str(root),
                "backup_count": len(backups),
                "backups": backups
            }

        except Exception as e:
            print(f"[BackupManager] get_backup_manager_status failed: {e}")
            return {
                "ok": False,
                "error": str(e),
                "backups": []
            }

    def create_system_backup(self, label="manual"):
        """Creates a local code backup. Does not copy configs, DBs, profiles, extensions, or logs."""
        try:
            import json
            import shutil
            import socket
            import time
            from pathlib import Path

            base_dir = Path(__file__).resolve().parent
            root = self._backup_manager_root()

            clean_label = self._backup_manager_safe_id(label or "manual")
            stamp = time.strftime("%Y%m%d_%H%M%S")
            backup_id = f"{stamp}_{clean_label}"
            backup_dir = root / backup_id
            backup_dir.mkdir(parents=True, exist_ok=True)

            copied_files = []
            skipped_files = []

            for rel in self._backup_manager_manifest():
                src = base_dir / rel
                dst = backup_dir / rel

                if not src.exists() or not src.is_file():
                    skipped_files.append(rel)
                    continue

                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied_files.append(rel)

            manifest = {
                "backup_id": backup_id,
                "label": clean_label,
                "created_at": stamp,
                "created_by": socket.gethostname(),
                "base_dir": str(base_dir),
                "files": copied_files,
                "skipped": skipped_files,
                "note": "Code backup only. local_config, databases, profiles, extensions, and logs are excluded."
            }

            (backup_dir / "backup_manifest.json").write_text(
                json.dumps(manifest, indent=4),
                encoding="utf-8"
            )

            return {
                "ok": True,
                "backup_id": backup_id,
                "backup_path": str(backup_dir),
                "copied_count": len(copied_files),
                "skipped_count": len(skipped_files),
                "files": copied_files,
                "skipped": skipped_files
            }

        except Exception as e:
            print(f"[BackupManager] create_system_backup failed: {e}")
            return {
                "ok": False,
                "error": str(e)
            }

    def restore_system_backup(self, backup_id):
        """Restores a selected backup locally. Creates a pre-restore backup first."""
        try:
            import json
            import shutil
            from pathlib import Path

            base_dir = Path(__file__).resolve().parent
            root = self._backup_manager_root()
            clean_id = self._backup_manager_safe_id(backup_id)

            if not clean_id:
                return {
                    "ok": False,
                    "error": "backup_id is required"
                }

            backup_dir = root / clean_id

            if not backup_dir.exists() or not backup_dir.is_dir():
                return {
                    "ok": False,
                    "error": f"Backup not found: {clean_id}"
                }

            # Safety: create a pre-restore backup before overwriting anything.
            pre_restore = self.create_system_backup(f"pre_restore_before_{clean_id}")
            if not pre_restore.get("ok"):
                return {
                    "ok": False,
                    "error": "Could not create pre-restore safety backup.",
                    "details": pre_restore
                }

            manifest_path = backup_dir / "backup_manifest.json"
            files_to_restore = []

            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    files = manifest.get("files", [])
                    if isinstance(files, list):
                        files_to_restore = files
                except Exception:
                    files_to_restore = []

            if not files_to_restore:
                for rel in self._backup_manager_manifest():
                    if (backup_dir / rel).exists():
                        files_to_restore.append(rel)

            restored = []
            skipped = []

            allowed = set(self._backup_manager_manifest())

            for rel in files_to_restore:
                rel = str(rel).replace("\\", "/").strip().lstrip("/")

                if rel not in allowed:
                    skipped.append({
                        "path": rel,
                        "reason": "not in allowed restore manifest"
                    })
                    continue

                src = backup_dir / rel
                dst = base_dir / rel

                if not src.exists() or not src.is_file():
                    skipped.append({
                        "path": rel,
                        "reason": "file missing in backup"
                    })
                    continue

                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                restored.append(rel)

            return {
                "ok": True,
                "restored_from": clean_id,
                "pre_restore_backup": pre_restore.get("backup_id"),
                "restored_count": len(restored),
                "skipped_count": len(skipped),
                "restored": restored,
                "skipped": skipped,
                "restart_required": True,
                "message": "Restore complete. Restart the dashboard/coordinator for restored code to take effect."
            }

        except Exception as e:
            print(f"[BackupManager] restore_system_backup failed: {e}")
            return {
                "ok": False,
                "error": str(e)
            }

    def delete_system_backup(self, backup_id):
        """Deletes a selected local backup folder."""
        try:
            import shutil

            root = self._backup_manager_root()
            clean_id = self._backup_manager_safe_id(backup_id)

            if not clean_id:
                return {
                    "ok": False,
                    "error": "backup_id is required"
                }

            backup_dir = root / clean_id

            if not backup_dir.exists() or not backup_dir.is_dir():
                return {
                    "ok": False,
                    "error": f"Backup not found: {clean_id}"
                }

            shutil.rmtree(backup_dir)

            return {
                "ok": True,
                "deleted": clean_id
            }

        except Exception as e:
            print(f"[BackupManager] delete_system_backup failed: {e}")
            return {
                "ok": False,
                "error": str(e)
            }


    # ==============================
    # System Diagnostics + Log Viewer Bridge
    # ==============================

    def _diagnostics_base_dir(self):
        from pathlib import Path
        return Path(__file__).resolve().parent

    def _diagnostics_safe_log_map(self):
        base_dir = self._diagnostics_base_dir()

        return {
            "crash": base_dir / "crash_log.txt",
            "health": base_dir / "health_log.txt",
            "sync_client": base_dir / "sync_client_log.txt",
            "coordinator": base_dir / "coordinator_log.txt",
            "mobile_worker": base_dir / "mobile_worker_log.txt"
        }

    def _diagnostics_file_info(self, path):
        try:
            from pathlib import Path
            p = Path(path)

            if not p.exists():
                return {
                    "exists": False,
                    "size_bytes": 0,
                    "modified": "",
                    "path": str(p)
                }

            stat = p.stat()

            return {
                "exists": True,
                "size_bytes": stat.st_size,
                "modified": str(stat.st_mtime),
                "path": str(p)
            }

        except Exception as e:
            return {
                "exists": False,
                "size_bytes": 0,
                "modified": "",
                "path": str(path),
                "error": str(e)
            }

    def _diagnostics_format_size(self, size_bytes):
        try:
            n = float(size_bytes or 0)
            for unit in ["B", "KB", "MB", "GB"]:
                if n < 1024:
                    return f"{n:.1f} {unit}"
                n = n / 1024
            return f"{n:.1f} TB"
        except Exception:
            return "0 B"

    def _diagnostics_compile_file(self, rel_path):
        try:
            import py_compile
            from pathlib import Path

            base_dir = self._diagnostics_base_dir()
            path = base_dir / rel_path

            if not path.exists():
                return {
                    "file": rel_path,
                    "ok": False,
                    "exists": False,
                    "error": "File missing"
                }

            py_compile.compile(str(path), doraise=True)

            return {
                "file": rel_path,
                "ok": True,
                "exists": True,
                "error": ""
            }

        except Exception as e:
            return {
                "file": rel_path,
                "ok": False,
                "exists": True,
                "error": str(e)
            }

    def _diagnostics_check_local_files(self):
        from pathlib import Path

        base_dir = self._diagnostics_base_dir()

        files = [
            "start_dashboard.py",
            "coordinator_server.py",
            "mobile_worker.py",
            "health_check.py",
            "sync_updates_to_main.py",
            "ui/index.html",
            "ui/app.js",
            "ui/style.css",
            "engine/db_manager.py",
            "engine/ghost_core.py"
        ]

        results = []

        for rel in files:
            path = base_dir / rel
            info = self._diagnostics_file_info(path)
            results.append({
                "file": rel,
                "exists": info.get("exists"),
                "size_bytes": info.get("size_bytes"),
                "size_text": self._diagnostics_format_size(info.get("size_bytes")),
                "path": info.get("path")
            })

        return results

    def _diagnostics_check_python_compile(self):
        python_files = [
            "start_dashboard.py",
            "coordinator_server.py",
            "mobile_worker.py",
            "health_check.py",
            "sync_updates_to_main.py",
            "engine/db_manager.py",
            "engine/ghost_core.py"
        ]

        return [
            self._diagnostics_compile_file(rel)
            for rel in python_files
        ]

    def _diagnostics_check_coordinator_routes(self):
        routes = [
            {
                "name": "Health",
                "path": "/api/health",
                "required": True
            },
            {
                "name": "Workers",
                "path": "/api/workers",
                "required": True
            },
            {
                "name": "Mobile Tasks",
                "path": "/api/mobile/tasks",
                "required": False
            },
            {
                "name": "Sync Status",
                "path": "/api/sync/status",
                "required": False
            }
        ]

        results = []

        if not self._coordinator_enabled():
            for route in routes:
                results.append({
                    "name": route["name"],
                    "path": route["path"],
                    "required": route["required"],
                    "ok": False,
                    "error": "Coordinator URL is not configured.",
                    "data": {}
                })

            return results

        for route in routes:
            try:
                result = self._coordinator_request(
                    "GET",
                    route["path"],
                    timeout=4,
                    quiet=True,
                    force=True
                )

                if result:
                    ok = bool(result.get("ok", True))
                    error = ""
                else:
                    ok = False
                    error = self.coordinator_last_error or "No response"

                results.append({
                    "name": route["name"],
                    "path": route["path"],
                    "required": route["required"],
                    "ok": ok,
                    "error": error,
                    "data": result or {}
                })

            except Exception as e:
                results.append({
                    "name": route["name"],
                    "path": route["path"],
                    "required": route["required"],
                    "ok": False,
                    "error": str(e),
                    "data": {}
                })

        return results

    def _diagnostics_recent_log_summary(self):
        logs = []

        for name, path in self._diagnostics_safe_log_map().items():
            info = self._diagnostics_file_info(path)
            logs.append({
                "name": name,
                "path": info.get("path"),
                "exists": info.get("exists"),
                "size_bytes": info.get("size_bytes"),
                "size_text": self._diagnostics_format_size(info.get("size_bytes"))
            })

        return logs

    def get_system_diagnostics(self):
        """Returns full dashboard/coordinator diagnostics for the UI."""
        try:
            import socket
            import time

            route_results = self._diagnostics_check_coordinator_routes()
            file_results = self._diagnostics_check_local_files()
            compile_results = self._diagnostics_check_python_compile()
            log_results = self._diagnostics_recent_log_summary()

            required_route_failures = [
                item for item in route_results
                if item.get("required") and not item.get("ok")
            ]

            compile_failures = [
                item for item in compile_results
                if not item.get("ok")
            ]

            missing_files = [
                item for item in file_results
                if not item.get("exists")
            ]

            overall_ok = (
                len(required_route_failures) == 0
                and len(compile_failures) == 0
                and len(missing_files) == 0
            )

            return {
                "ok": True,
                "overall_ok": overall_ok,
                "checked_at": int(time.time()),
                "hostname": socket.gethostname(),
                "pc_id": PC_ID,
                "device_type": DEVICE_TYPE or "auto",
                "coordinator_url": COORDINATOR_URL,
                "coordinator_enabled": self._coordinator_enabled(),
                "routes": route_results,
                "files": file_results,
                "compile": compile_results,
                "logs": log_results,
                "summary": {
                    "required_route_failures": len(required_route_failures),
                    "compile_failures": len(compile_failures),
                    "missing_files": len(missing_files),
                    "log_count": len(log_results)
                }
            }

        except Exception as e:
            print(f"[Diagnostics] get_system_diagnostics failed: {e}")
            return {
                "ok": False,
                "overall_ok": False,
                "error": str(e)
            }

    def read_system_log(self, log_name="crash", max_lines=250):
        """Reads an allowed local log file for the dashboard log viewer."""
        try:
            logs = self._diagnostics_safe_log_map()
            clean_name = str(log_name or "crash").strip().lower()

            if clean_name not in logs:
                return {
                    "ok": False,
                    "error": f"Unknown log name: {clean_name}",
                    "allowed": sorted(list(logs.keys()))
                }

            path = logs[clean_name]

            try:
                limit = int(max_lines or 250)
            except Exception:
                limit = 250

            limit = max(25, min(limit, 2000))

            if not path.exists():
                return {
                    "ok": True,
                    "log_name": clean_name,
                    "path": str(path),
                    "exists": False,
                    "content": "",
                    "lines": []
                }

            text = path.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()

            if len(lines) > limit:
                lines = lines[-limit:]

            return {
                "ok": True,
                "log_name": clean_name,
                "path": str(path),
                "exists": True,
                "line_count": len(lines),
                "content": "\n".join(lines),
                "lines": lines
            }

        except Exception as e:
            print(f"[Diagnostics] read_system_log failed: {e}")
            return {
                "ok": False,
                "error": str(e)
            }

    def clear_system_log(self, log_name="crash"):
        """Clears an allowed local log file."""
        try:
            logs = self._diagnostics_safe_log_map()
            clean_name = str(log_name or "crash").strip().lower()

            if clean_name not in logs:
                return {
                    "ok": False,
                    "error": f"Unknown log name: {clean_name}",
                    "allowed": sorted(list(logs.keys()))
                }

            path = logs[clean_name]
            path.write_text("", encoding="utf-8")

            return {
                "ok": True,
                "log_name": clean_name,
                "path": str(path),
                "message": f"Cleared log: {clean_name}"
            }

        except Exception as e:
            print(f"[Diagnostics] clear_system_log failed: {e}")
            return {
                "ok": False,
                "error": str(e)
            }


    # ==============================
    # Easy Version Status Bridge
    # ==============================

    def _easy_version_base(self):
        from pathlib import Path
        return Path(__file__).resolve().parent

    def _easy_version_sha(self, path):
        import hashlib
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def get_version_status(self):
        import json, time, socket

        files = [
            "coordinator_server.py",
            "start_dashboard.py",
            "mobile_worker.py",
            "sync_updates_to_main.py",
            "ui/app.js",
            "ui/style.css",
            "ui/index.html",
        ]

        base = self._easy_version_base()
        local = []

        for rel in files:
            p = base / rel
            item = {"path": rel, "exists": p.is_file(), "sha256": "", "size_bytes": 0, "modified": 0}
            if item["exists"]:
                st = p.stat()
                item["size_bytes"] = st.st_size
                item["modified"] = int(st.st_mtime)
                item["sha256"] = self._easy_version_sha(p)
            local.append(item)

        remote = []
        remote_ok = False
        remote_error = ""

        if self._coordinator_enabled():
            result = self._coordinator_request("GET", "/api/sync/file-status", timeout=5, quiet=True, force=True)
            if result and result.get("ok"):
                remote_ok = True
                remote = result.get("files", []) or []
            else:
                remote_error = self.coordinator_last_error or "Remote file-status route unavailable"

        remote_map = {str(x.get("path")): x for x in remote}
        comparisons = []

        for l in local:
            r = remote_map.get(l["path"])
            if not r:
                status = "REMOTE_UNKNOWN"
            elif not r.get("exists"):
                status = "REMOTE_MISSING"
            elif l.get("sha256") == r.get("sha256"):
                status = "MATCH"
            else:
                status = "DIFFERENT"

            comparisons.append({
                "path": l["path"],
                "status": status,
                "local_size": l.get("size_bytes", 0),
                "remote_size": r.get("size_bytes", 0) if r else 0,
                "local_sha256": l.get("sha256", ""),
                "remote_sha256": r.get("sha256", "") if r else ""
            })

        hist = []
        hp = base / "sync_history.jsonl"
        if hp.exists():
            for line in hp.read_text(encoding="utf-8", errors="replace").splitlines()[-25:]:
                try:
                    hist.append(json.loads(line))
                except Exception:
                    pass
            hist.reverse()

        return {
            "ok": True,
            "hostname": socket.gethostname(),
            "pc_id": PC_ID,
            "coordinator_url": COORDINATOR_URL,
            "remote_available": remote_ok,
            "remote_error": remote_error,
            "summary": {
                "local_count": len(local),
                "remote_count": len(remote),
                "match": len([x for x in comparisons if x["status"] == "MATCH"]),
                "different": len([x for x in comparisons if x["status"] == "DIFFERENT"]),
                "remote_missing": len([x for x in comparisons if x["status"] == "REMOTE_MISSING"]),
                "remote_unknown": len([x for x in comparisons if x["status"] == "REMOTE_UNKNOWN"])
            },
            "comparisons": comparisons,
            "sync_history": hist,
            "checked_at": int(time.time())
        }

    def create_version_snapshot(self, label="manual"):
        import json, time
        root = self._easy_version_base() / "_archive" / "version_snapshots"
        root.mkdir(exist_ok=True)
        clean = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(label or "manual"))[:80]
        data = self.get_version_status()
        path = root / f"{time.strftime('%Y%m%d_%H%M%S')}_{clean}.json"
        path.write_text(json.dumps(data, indent=4), encoding="utf-8")
        return {"ok": True, "snapshot_id": path.stem, "path": str(path)}

    def clear_sync_history(self):
        base = self._easy_version_base()
        for name in ["sync_history.jsonl", "sync_client_log.txt"]:
            (base / name).write_text("", encoding="utf-8")
        return {"ok": True, "message": "Sync history cleared"}


    # ==============================
    # Device Groups + Permissions Bridge
    # ==============================

    def _device_permissions_request(self, method, path, payload=None, timeout=8):
        try:
            import requests
            url = str(COORDINATOR_URL).rstrip("/") + path
            method = str(method or "GET").upper()
            if method == "GET":
                response = requests.get(url, timeout=timeout)
            else:
                response = requests.post(url, json=(payload or {}), timeout=timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"ok": False, "error": str(e), "path": path}

    def get_device_permissions(self):
        try:
            permissions = self._device_permissions_request("GET", "/api/device-permissions", timeout=8)
            workers_result = self._device_permissions_request("GET", "/api/workers", timeout=8)
            workers = []
            if workers_result and workers_result.get("ok"):
                if isinstance(workers_result.get("workers"), list): workers = workers_result.get("workers") or []
                elif isinstance(workers_result.get("items"), list): workers = workers_result.get("items") or []
                elif isinstance(workers_result.get("devices"), list): workers = workers_result.get("devices") or []
                elif isinstance(workers_result.get("workers"), dict): workers = list((workers_result.get("workers") or {}).values())
            roles = ["main_controller", "worker_laptop", "worker_pc", "phone_worker", "monitor_only", "blocked"]
            devices = {}
            if permissions and permissions.get("ok"):
                devices = permissions.get("devices") or {}; roles = permissions.get("roles") or roles
            return {"ok": bool(permissions and permissions.get("ok")), "error": "" if permissions and permissions.get("ok") else (permissions.get("error") if isinstance(permissions, dict) else "Could not load permissions"), "workers": workers, "devices": devices, "roles": roles, "coordinator_url": COORDINATOR_URL, "workers_status": workers_result}
        except Exception as e:
            return {"ok": False, "error": str(e), "workers": [], "devices": {}, "roles": []}

    def set_device_permission(self, pc_id, role):
        try:
            return self._device_permissions_request("POST", "/api/device-permissions/set", payload={"pc_id": str(pc_id or "").strip(), "role": str(role or "monitor_only").strip()}, timeout=8)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def block_device_permission(self, pc_id, blocked=True):
        try:
            return self._device_permissions_request("POST", "/api/device-permissions/block", payload={"pc_id": str(pc_id or "").strip(), "blocked": bool(blocked)}, timeout=8)
        except Exception as e:
            return {"ok": False, "error": str(e)}


    # ==============================
    # Security Audit Log Bridge
    # ==============================

    def get_security_events(self, limit=200, event_type="", pc_id="", status=""):
        try:
            import requests

            params = {
                "limit": int(limit or 200)
            }

            if event_type:
                params["event_type"] = str(event_type)

            if pc_id:
                params["pc_id"] = str(pc_id)

            if status:
                params["status"] = str(status)

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/security-events",
                params=params,
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=8
            )

            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "events": []
            }

    def clear_security_events(self):
        try:
            import requests

            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/security-events/clear",
                json={
                    "request_pc_id": str(globals().get("PC_ID", "UNKNOWN_PC"))
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=8
            )

            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e)
            }


    # ==============================
    # Main PC ↔ Laptop Command Center Bridge
    # ==============================

    def get_device_commands(self, target_pc_id="", status="", limit=100):
        try:
            import requests

            params = {"limit": int(limit or 100)}

            if target_pc_id:
                params["target_pc_id"] = str(target_pc_id)

            if status:
                params["status"] = str(status)

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/device-commands",
                params=params,
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=8
            )

            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "commands": []
            }

    def create_device_command(self, target_pc_id, command_type, payload=None):
        try:
            import requests

            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/device-commands/create",
                json={
                    "target_pc_id": str(target_pc_id or "").strip(),
                    "command_type": str(command_type or "").strip(),
                    "payload": payload or {},
                    "request_pc_id": str(globals().get("PC_ID", "UNKNOWN_PC")),
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=8
            )

            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e)
            }


    # ==============================
    # ML Reliability + Anomaly Detection Bridge v1
    # ==============================

    def get_ml_status(self):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/status",
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=10
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "engine": "ml_reliability_v1"
            }

    def get_ml_reliability(self):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/reliability",
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=10
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "device_scores": []
            }

    def get_ml_anomalies(self):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/anomalies",
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=10
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "anomalies": []
            }

    def get_ml_recommendations(self):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/recommendations",
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=10
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "recommendations": []
            }

    def predict_device_command_success(self, target_pc_id="", command_type=""):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/command-prediction",
                params={
                    "target_pc_id": str(target_pc_id or ""),
                    "command_type": str(command_type or ""),
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=10
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e)
            }

    def get_ml_events(self, limit=200):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/events",
                params={"limit": int(limit or 200)},
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=10
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "events": []
            }

    def clear_ml_events(self):
        try:
            import requests

            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/events/clear",
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=10
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e)
            }


    # ==============================
    # ML History + Trend Learning Bridge v1
    # ==============================

    def create_ml_history_snapshot(self):
        try:
            import requests

            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/history/snapshot",
                json={
                    "source": "dashboard",
                    "pc_id": str(globals().get("PC_ID", "UNKNOWN_PC")),
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=15
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e)
            }

    def get_ml_history(self, limit=200):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/history",
                params={"limit": int(limit or 200)},
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=12
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "history": []
            }

    def get_ml_trends(self, limit=500):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/trends",
                params={"limit": int(limit or 500)},
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=12
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "device_trends": [],
                "recommendations": []
            }

    def clear_ml_history(self):
        try:
            import requests

            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/history/clear",
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=12
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e)
            }


    # ==============================
    # ML Auto-Recommendation Action Queue Bridge v1
    # ==============================

    def get_ml_actions(self, status="", severity="", limit=200):
        try:
            import requests

            params = {"limit": int(limit or 200)}

            if status:
                params["status"] = str(status)

            if severity:
                params["severity"] = str(severity)

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/actions",
                params=params,
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=12
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "actions": []
            }

    def generate_ml_actions(self):
        try:
            import requests

            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/actions/generate",
                json={
                    "request_pc_id": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "source": "dashboard"
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=15
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "added": []
            }

    def approve_ml_action(self, action_id, notes=""):
        try:
            import requests

            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/actions/approve",
                json={
                    "action_id": str(action_id or ""),
                    "notes": str(notes or ""),
                    "request_pc_id": str(globals().get("PC_ID", "UNKNOWN_PC")),
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=12
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def reject_ml_action(self, action_id, notes=""):
        try:
            import requests

            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/actions/reject",
                json={
                    "action_id": str(action_id or ""),
                    "notes": str(notes or ""),
                    "request_pc_id": str(globals().get("PC_ID", "UNKNOWN_PC")),
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=12
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def complete_ml_action(self, action_id, status="completed", notes=""):
        try:
            import requests

            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/actions/complete",
                json={
                    "action_id": str(action_id or ""),
                    "status": str(status or "completed"),
                    "notes": str(notes or ""),
                    "request_pc_id": str(globals().get("PC_ID", "UNKNOWN_PC")),
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=12
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def clear_ml_actions(self, mode="completed"):
        try:
            import requests

            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/actions/clear",
                json={
                    "mode": str(mode or "completed"),
                    "request_pc_id": str(globals().get("PC_ID", "UNKNOWN_PC")),
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=12
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"ok": False, "error": str(e)}


    # ==============================
    # ML Safe Auto-Executor Bridge v1
    # ==============================

    def get_ml_auto_executor_config(self):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/auto-executor/config",
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=12
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_ml_auto_executor_config(self, enabled=True, max_auto_commands_per_cycle=5):
        try:
            import requests

            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/auto-executor/config",
                json={
                    "enabled": bool(enabled),
                    "max_auto_commands_per_cycle": int(max_auto_commands_per_cycle or 5),
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=12
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def run_ml_auto_executor_once(self):
        try:
            import requests

            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/actions/auto-run",
                json={
                    "source": "dashboard",
                    "request_pc_id": str(globals().get("PC_ID", "UNKNOWN_PC")),
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=20
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_ml_auto_executor_events(self, limit=200):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/auto-executor/events",
                params={"limit": int(limit or 200)},
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=12
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"ok": False, "error": str(e), "events": []}


    # ==============================
    # ML Result Feedback Loop Bridge v1
    # ==============================

    def get_ml_feedback_config(self):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/feedback/config",
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=12
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_ml_feedback_config(self, enabled=True):
        try:
            import requests

            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/feedback/config",
                json={
                    "enabled": bool(enabled)
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=12
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def run_ml_feedback_once(self):
        try:
            import requests

            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/feedback/run",
                json={
                    "source": "dashboard",
                    "request_pc_id": str(globals().get("PC_ID", "UNKNOWN_PC")),
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=20
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_ml_feedback_events(self, limit=200):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/feedback/events",
                params={"limit": int(limit or 200)},
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=12
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"ok": False, "error": str(e), "events": []}


    # ==============================
    # ML Auto-Resolver + Score Adjustment Bridge v1
    # ==============================

    def get_ml_auto_resolver_config(self):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/auto-resolver/config",
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=12
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_ml_auto_resolver_config(self, enabled=True):
        try:
            import requests

            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/auto-resolver/config",
                json={"enabled": bool(enabled)},
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=12
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def run_ml_auto_resolver_once(self):
        try:
            import requests

            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/auto-resolver/run",
                json={
                    "source": "dashboard",
                    "request_pc_id": str(globals().get("PC_ID", "UNKNOWN_PC")),
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=20
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_ml_auto_resolver_events(self, limit=200):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/auto-resolver/events",
                params={"limit": int(limit or 200)},
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=12
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"ok": False, "error": str(e), "events": []}

    def get_ml_adjusted_reliability(self):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/adjusted-reliability",
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=12
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {"ok": False, "error": str(e), "device_scores": []}


    # ==============================
    # Unified ML Control Center + Timeline Bridge v1
    # ==============================

    def get_unified_ml_control_center(self):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/control-center",
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=15
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "devices": []
            }

    def get_ml_device_timeline(self, pc_id="", limit=500):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/device-timeline",
                params={
                    "pc_id": str(pc_id or ""),
                    "limit": int(limit or 500),
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=15
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "timeline": []
            }


    # ==============================
    # ML Smart Worker + Stale PC_ID Bridge v1
    # ==============================

    def get_ml_smart_workers(self):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/smart-workers",
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=15
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "workers": [],
                "stale_targets": []
            }

    def get_ml_stale_targets(self):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/stale-targets",
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=15
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "stale_targets": []
            }


    # ==============================
    # ML Backup Guard + Update Readiness Gate Bridge v1
    # ==============================

    def get_ml_backup_guard_status(self):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/backup-guard/status",
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=20
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "backups": []
            }

    def get_ml_backup_guard_recommendation(self):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/backup-guard/recommendation",
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=20
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e)
            }

    def create_ml_backup_guard_backup(self, reason="manual_dashboard"):
        try:
            import requests

            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/backup-guard/create",
                json={
                    "reason": str(reason or "manual_dashboard"),
                    "request_pc_id": str(globals().get("PC_ID", "UNKNOWN_PC")),
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=60
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e)
            }

    def run_ml_backup_guard_auto(self):
        try:
            import requests

            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/backup-guard/auto-run",
                json={
                    "source": "dashboard",
                    "request_pc_id": str(globals().get("PC_ID", "UNKNOWN_PC")),
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=60
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e)
            }

    def list_ml_backup_guard_backups(self):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/backup-guard/list",
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=20
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "backups": []
            }


    # ==============================
    # ML Capacity Forecast + Worker Load Planner Bridge v1
    # ==============================

    def get_ml_capacity_forecast(self):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/capacity-forecast",
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=20
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "plans": []
            }

    def export_ml_capacity_forecast(self):
        try:
            import requests

            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/capacity-forecast/export",
                json={
                    "source": "dashboard",
                    "request_pc_id": str(globals().get("PC_ID", "UNKNOWN_PC")),
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=25
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e)
            }

    def get_ml_capacity_forecast_reports(self):
        try:
            import requests

            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/capacity-forecast/reports",
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=15
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "reports": []
            }


    # ==============================
    # ML/RL Architecture v2 Bridge
    # ==============================

    def get_ml_rl_architecture_status(self):
        try:
            import requests
            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/rl-architecture/status",
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=20
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_ml_rl_architecture_enabled(self, enabled):
        try:
            import requests
            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/rl-architecture/config",
                json={
                    "enabled": bool(enabled),
                    "request_pc_id": str(globals().get("PC_ID", "UNKNOWN_PC")),
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=20
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def run_ml_rl_architecture_episode(self, steps=5):
        try:
            import requests
            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/rl-architecture/run-episode",
                json={
                    "steps": int(steps or 5),
                    "source": "dashboard",
                    "request_pc_id": str(globals().get("PC_ID", "UNKNOWN_PC")),
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=60
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def train_ml_rl_architecture_q(self, episodes=5, steps_per_episode=5):
        try:
            import requests
            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/rl-architecture/train-q",
                json={
                    "episodes": int(episodes or 5),
                    "steps_per_episode": int(steps_per_episode or 5),
                    "source": "dashboard",
                    "request_pc_id": str(globals().get("PC_ID", "UNKNOWN_PC")),
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=120
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_ml_rl_architecture_behavior_dataset(self):
        try:
            import requests
            response = requests.get(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/rl-architecture/behavior-dataset",
                params={"limit": 500},
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"ok": False, "error": str(e), "samples": []}

    def export_ml_rl_architecture_report(self):
        try:
            import requests
            response = requests.post(
                str(COORDINATOR_URL).rstrip("/") + "/api/ml/rl-architecture/export",
                json={
                    "source": "dashboard",
                    "request_pc_id": str(globals().get("PC_ID", "UNKNOWN_PC")),
                },
                headers={
                    "X-PC-ID": str(globals().get("PC_ID", "UNKNOWN_PC")),
                    "X-Device-Type": str(globals().get("DEVICE_TYPE", "pc")),
                },
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}


    # === COMET PATCH 009 BACKEND REFRESH SNAPSHOT API START ===
    def get_dashboard_snapshot(self):
        try:
            snapshot = self.db.get_dashboard_snapshot() if hasattr(self.db, "get_dashboard_snapshot") else {
                "ok": False,
                "error": "Database snapshot method unavailable."
            }

            if not isinstance(snapshot, dict):
                snapshot = {"ok": False, "error": "Invalid snapshot payload."}

            snapshot["pc"] = {
                "pc_id": str(globals().get("PC_ID", "UNKNOWN_PC")),
                "device_type": str(globals().get("DEVICE_TYPE", "") or "auto"),
                "coordinator_enabled": bool(getattr(self, "_coordinator_enabled", lambda: False)()),
                "coordinator_online": bool(getattr(self, "coordinator_online", False)),
                "coordinator_url": str(globals().get("COORDINATOR_URL", "") or ""),
                "coordinator_last_error": str(getattr(self, "coordinator_last_error", "") or "")
            }

            try:
                if hasattr(self, "get_laptop_sync_status"):
                    snapshot["laptop_sync"] = self.get_laptop_sync_status()
            except Exception as e:
                snapshot["laptop_sync"] = {"ok": False, "error": str(e)}

            try:
                sessions = getattr(getattr(self, "ghost_core", None), "active_sessions", {}) or {}
                snapshot["runtime"] = {
                    "active_session_count": len(sessions),
                    "active_profile_ids": [int(x) for x in sessions.keys()]
                }
            except Exception:
                snapshot["runtime"] = {"active_session_count": 0, "active_profile_ids": []}

            return snapshot
        except Exception as e:
            print(f"[Patch009] get_dashboard_snapshot failed: {e}")
            return {"ok": False, "error": str(e)}

    def record_dashboard_refresh_history(self, payload=None):
        try:
            if not hasattr(self.db, "record_dashboard_refresh_history"):
                return {"ok": False, "error": "Database refresh history method unavailable."}
            return self.db.record_dashboard_refresh_history(payload if isinstance(payload, dict) else {})
        except Exception as e:
            print(f"[Patch009] record_dashboard_refresh_history failed: {e}")
            return {"ok": False, "error": str(e)}

    def get_dashboard_refresh_history(self, limit=25):
        try:
            if not hasattr(self.db, "get_dashboard_refresh_history"):
                return {"ok": False, "history": [], "error": "Database refresh history method unavailable."}
            return self.db.get_dashboard_refresh_history(limit=limit)
        except Exception as e:
            return {"ok": False, "history": [], "error": str(e)}
    # === COMET PATCH 009 BACKEND REFRESH SNAPSHOT API END ===

    def _detect_gpu_names(self):
        """Asks Windows to identify all installed graphics cards."""
        try:
            raw = subprocess.check_output(['wmic', 'path', 'win32_videocontroller', 'get', 'name'], creationflags=subprocess.CREATE_NO_WINDOW).decode('utf-8')
            names = [line.strip() for line in raw.split('\n') if line.strip() and 'Name' not in line]
            return " + ".join(names) if names else "Unknown GPU"
        except:
            return "Unknown GPU"

    def get_gpu_load(self):
        """Uses a lightweight Windows command to get total 3D Engine load across ALL GPUs."""
        try:
            ps_cmd = r"((Get-Counter '\GPU Engine(*engtype_3D)\Utilization Percentage' -ErrorAction SilentlyContinue).CounterSamples | Measure-Object -Property CookedValue -Sum).Sum"
            output = subprocess.check_output(['powershell', '-Command', ps_cmd], creationflags=subprocess.CREATE_NO_WINDOW).decode('utf-8').strip()
            total = int(float(output)) if output else 0
            return min(total, 100) # Cap at 100%
        except:
            return 0

    def get_network_speed(self):
        """Calculates Mbps (Megabits per second) and detects connection type."""
        curr_time = time.time()
        curr_io = psutil.net_io_counters()
        
        time_diff = curr_time - self.last_net_time
        if time_diff <= 0: time_diff = 1 
        
        # Convert Bytes to Megabits: (Bytes * 8) / 1,000,000
        dl_mbps = round((((curr_io.bytes_recv - self.last_net_io.bytes_recv) * 8) / 1000000) / time_diff, 1)
        ul_mbps = round((((curr_io.bytes_sent - self.last_net_io.bytes_sent) * 8) / 1000000) / time_diff, 1)
        
        self.last_net_io = curr_io
        self.last_net_time = curr_time
        
        # Detect Wi-Fi vs Landline
        net_type = "Offline"
        for interface, stat in psutil.net_if_stats().items():
            if stat.isup:
                name = interface.lower()
                if "wi-fi" in name or "wireless" in name:
                    net_type = "Wi-Fi Connection"
                    break
                elif "ethernet" in name or "local area" in name:
                    net_type = "Landline (Ethernet)"
                    break
        return net_type, dl_mbps, ul_mbps

    def set_window(self, window): self.window = window
    
    # ==============================
    # Device Capability / Launch Permission Helpers
    # ==============================

    def _truthy(self, value):
        return str(value).strip().lower() in ["1", "true", "yes", "y", "on"]

    def _infer_device_type(self, pc_id=None, hostname=None, default_type="PC"):
        """
        Infers whether this worker is a PC, laptop, phone, tablet, or unknown.

        For the current desktop dashboard, default_type='PC' prevents accidental launch blocking
        when DEVICE_TYPE is not configured yet.
        """
        configured = str(DEVICE_TYPE or "").strip().lower()
        raw = f"{configured} {pc_id or PC_ID} {hostname or socket.gethostname()}".lower()

        if any(term in raw for term in ["phone", "android", "iphone", "ios", "mobile"]):
            return "Phone"

        if any(term in raw for term in ["tablet", "ipad"]):
            return "Tablet"

        if any(term in raw for term in ["laptop", "notebook", "legion"]):
            return "Laptop"

        if any(term in raw for term in ["desktop", "pc", "tower", "workstation"]):
            return "PC"

        if configured in ["pc", "desktop"]:
            return "PC"

        if configured in ["laptop", "notebook"]:
            return "Laptop"

        if configured in ["phone", "mobile", "android", "iphone", "ios"]:
            return "Phone"

        if configured in ["tablet", "ipad"]:
            return "Tablet"

        return default_type

    def _infer_device_role(self, pc_id=None, hostname=None, device_type=None):
        raw = f"{DEVICE_TYPE or ''} {pc_id or PC_ID} {hostname or socket.gethostname()}".lower()
        device_type = device_type or self._infer_device_type(pc_id=pc_id, hostname=hostname)

        if any(term in raw for term in ["controller", "main", "master"]):
            return "Controller"

        if device_type == "Phone":
            return "Worker Phone"

        if device_type == "Tablet":
            return "Worker Tablet"

        if device_type == "Laptop":
            return "Worker Laptop"

        if device_type == "PC":
            return "Worker PC"

        return "Monitor Only"

    def _build_device_capabilities(self, pc_id=None, hostname=None, blocked=False, status="ONLINE", default_type="Unknown"):
        """
        Builds backend-safe device capability flags.

        Normal Comet/Selenium profile launching is allowed only on PC/Laptop devices.
        Phones/tablets remain visible as workers but are not assigned normal browser profile work.
        """
        device_type = self._infer_device_type(
            pc_id=pc_id,
            hostname=hostname,
            default_type=default_type
        )

        role = self._infer_device_role(
            pc_id=pc_id,
            hostname=hostname,
            device_type=device_type
        )

        status_text = str(status or "UNKNOWN").upper()
        blocked_bool = bool(blocked)

        is_computer = device_type in ["PC", "Laptop"]
        is_mobile = device_type in ["Phone", "Tablet"]

        can_launch_profiles = is_computer and not blocked_bool
        can_run_mobile_tasks = is_mobile and not blocked_bool
        can_control_fleet = role == "Controller" and not blocked_bool
        can_be_blocked = role != "Controller"

        if status_text in ["OFFLINE", "UNKNOWN", "BLOCKED"]:
            can_launch_profiles = False
            can_run_mobile_tasks = False
            can_control_fleet = False

        return {
            "device_type": device_type,
            "device_role": role,
            "can_launch_profiles": can_launch_profiles,
            "can_run_mobile_tasks": can_run_mobile_tasks,
            "can_control_fleet": can_control_fleet,
            "can_be_blocked": can_be_blocked
        }

    def _current_device_capabilities(self):
        return self._build_device_capabilities(
            pc_id=PC_ID,
            hostname=socket.gethostname(),
            blocked=getattr(self, "is_blocked_by_coordinator", False),
            status="ONLINE",
            default_type="PC"
        )
    
    def _current_worker_identity_payload(self):
        caps = self._current_device_capabilities()

        return {
            "pc_id": PC_ID,
            "hostname": socket.gethostname(),
            "device_type": caps.get("device_type") or DEVICE_TYPE or "",
            "device_role": caps.get("device_role") or "",
            "can_launch_profiles": bool(caps.get("can_launch_profiles")),
            "can_run_mobile_tasks": bool(caps.get("can_run_mobile_tasks")),
            "can_control_fleet": bool(caps.get("can_control_fleet")),
            "can_be_blocked": bool(caps.get("can_be_blocked")),
            "worker_version": "desktop-dashboard-1",
            "device_note": "Desktop dashboard worker"
        }
        
    def _normalize_active_platforms(self, active_platforms=None):
        """Returns a clean unique list of enabled platform keys."""
        if active_platforms is None:
            return []

        if isinstance(active_platforms, str):
            active_platforms = [active_platforms]

        cleaned = []
        for platform in active_platforms:
            value = str(platform or "").strip().lower()
            if value and value not in cleaned:
                cleaned.append(value)

        return cleaned

    def _build_launch_preflight(self):
        """Checks system paths before START ALL launches anything."""
        errors = []
        warnings = []

        if not COMET_PATH or not os.path.exists(COMET_PATH):
            errors.append({
                "code": "COMET_PATH_MISSING",
                "label": "Comet browser path missing",
                "path": str(COMET_PATH or "")
            })

        # ChromeDriver is kept as a warning because the current GhostCore attach path can use Selenium Manager.
        if not CHROMEDRIVER_PATH or not os.path.exists(CHROMEDRIVER_PATH):
            warnings.append({
                "code": "CHROMEDRIVER_PATH_MISSING",
                "label": "ChromeDriver path missing or unused",
                "path": str(CHROMEDRIVER_PATH or "")
            })

        manifest_path = os.path.join(str(PROTON_VPN_PATH or ""), "manifest.json")
        if not PROTON_VPN_PATH or not os.path.exists(manifest_path):
            errors.append({
                "code": "PROTON_EXTENSION_MISSING",
                "label": "ProtonVPN extension manifest missing",
                "path": manifest_path
            })

        return {
            "ok": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    def _new_launch_summary(self, active_platforms=None):
        """Creates the standard launch summary object returned to the dashboard."""
        return {
            "ok": False,
            "code": "NOT_RUN",
            "mode": "unknown",
            "message": "Launch not evaluated.",
            "active_platforms": self._normalize_active_platforms(active_platforms),
            "requested_count": 0,
            "launchable_count": 0,
            "launched_count": 0,
            "launchable_ids": [],
            "launched_ids": [],
            "skipped_counts": {
                "running": 0,
                "quarantined": 0,
                "locked": 0,
                "invalid": 0,
                "preflight": 0,
                "no_proton": 0,
                "proton_not_ready": 0,
                "proton_blocked": 0
            },
            "skipped": {
                "running": [],
                "quarantined": [],
                "locked": [],
                "invalid": [],
                "preflight": [],
                "no_proton": [],
                "proton_not_ready": [],
                "proton_blocked": []
            },
            "warnings": []
        }

    def _finalize_launch_summary_counts(self, summary):
        """Keeps all count fields synced after launch eligibility changes."""
        summary["requested_count"] = int(summary.get("requested_count") or 0)
        summary["launchable_ids"] = [int(pid) for pid in summary.get("launchable_ids", [])]
        summary["launched_ids"] = [int(pid) for pid in summary.get("launched_ids", [])]
        summary["launchable_count"] = len(summary["launchable_ids"])
        summary["launched_count"] = len(summary["launched_ids"])

        skipped = summary.setdefault("skipped", {})
        skipped_counts = summary.setdefault("skipped_counts", {})

        for key in ["running", "quarantined", "locked", "invalid", "preflight", "no_proton", "proton_not_ready", "proton_blocked"]:
            skipped.setdefault(key, [])
            skipped_counts[key] = len(skipped.get(key, []))

        return summary

    # ==============================
    # Patch 006: Proton Ready Launch Guard
    # ==============================

    def _profile_proton_launch_check(self, profile):
        """Returns (ok, skipped_key, detail) for Proton readiness Launch Guard."""
        try:
            pid = int(profile.get("id"))
        except Exception:
            pid = profile.get("id")

        assigned = bool(profile.get("proton_assigned"))
        account_active = bool(profile.get("proton_account_active", True))
        setup_status = str(profile.get("proton_setup_status") or "NEEDS_LOGIN").strip().upper()
        account_label = profile.get("proton_account_label") or ""

        if not assigned:
            return False, "no_proton", {
                "id": pid,
                "reason": "No Proton account assigned",
                "proton_status": "UNASSIGNED"
            }

        if not account_active:
            return False, "proton_blocked", {
                "id": pid,
                "account": account_label,
                "reason": "Assigned Proton account is inactive",
                "proton_status": setup_status
            }

        if setup_status == "BLOCKED":
            return False, "proton_blocked", {
                "id": pid,
                "account": account_label,
                "reason": "Proton setup is blocked",
                "proton_status": setup_status
            }

        if setup_status != "READY":
            return False, "proton_not_ready", {
                "id": pid,
                "account": account_label,
                "reason": "Proton setup is not marked READY",
                "proton_status": setup_status
            }

        return True, "", {}

    def _build_launch_eligibility_summary(self, active_platforms=None):
        """
        Builds a clear START ALL report before launching:
        - which profiles can launch
        - which profiles are skipped
        - why they are skipped
        """
        active_platforms = self._normalize_active_platforms(active_platforms)
        summary = self._new_launch_summary(active_platforms)

        if self.check_worker_block_status():
            print(f"[Backend] START ALL blocked: this device is blocked by coordinator. {self.blocked_reason}")
            summary["ok"] = False
            summary["code"] = "DEVICE_BLOCKED"
            summary["message"] = self.blocked_reason or "This device is blocked by the coordinator."
            return self._finalize_launch_summary_counts(summary)

        current_caps = self._current_device_capabilities()

        if not current_caps.get("can_launch_profiles"):
            print(
                "[Backend] START ALL blocked: current device is not allowed to launch normal browser profiles. "
                f"device_type={current_caps.get('device_type')} "
                f"role={current_caps.get('device_role')} "
                f"pc_id={PC_ID}"
            )
            summary["ok"] = False
            summary["code"] = "DEVICE_CANNOT_LAUNCH_PROFILES"
            summary["message"] = "This device is not allowed to launch normal browser profiles."
            summary["device"] = current_caps
            return self._finalize_launch_summary_counts(summary)

        if not active_platforms:
            print("[Backend] START ALL blocked: No platforms toggled ON.")
            summary["ok"] = False
            summary["code"] = "NO_PLATFORMS"
            summary["message"] = "No platforms are toggled ON."
            return self._finalize_launch_summary_counts(summary)

        preflight = self._build_launch_preflight()
        summary["warnings"] = preflight.get("warnings", [])

        if not preflight.get("ok"):
            summary["code"] = "PREFLIGHT_FAILED"
            summary["message"] = "Launch blocked because one or more required paths are missing."
            summary["skipped"]["preflight"] = preflight.get("errors", [])
            return self._finalize_launch_summary_counts(summary)

        # Quarantine is advisory only. START ALL should still retest profiles after repairs.
        # The live guards below still close unsafe launches for home IP, duplicate IP, or blacklisted IP.

        coordinator_profiles = self._get_coordinator_profiles()

        if coordinator_profiles is not None:
            summary["mode"] = "coordinator"
            summary["requested_count"] = len(coordinator_profiles)

            for profile in coordinator_profiles:
                try:
                    pid = int(profile.get("id"))
                except Exception:
                    summary["skipped"]["invalid"].append({
                        "id": profile.get("id"),
                        "reason": "Invalid profile ID from coordinator"
                    })
                    continue

                status = str(profile.get("status", "OFFLINE")).upper()
                locked_by = str(profile.get("locked_by") or "").strip()

                if status == "RUNNING":
                    summary["skipped"]["running"].append(pid)
                elif locked_by and locked_by != PC_ID:
                    summary["skipped"]["locked"].append({
                        "id": pid,
                        "locked_by": locked_by,
                        "reason": "Locked by another PC"
                    })
                else:
                    summary["launchable_ids"].append(pid)

        else:
            summary["mode"] = "local"
            local_profiles = self.db.get_all_profiles()
            summary["requested_count"] = len(local_profiles)

            for profile in local_profiles:
                try:
                    pid = int(profile.get("id"))
                except Exception:
                    summary["skipped"]["invalid"].append({
                        "id": profile.get("id"),
                        "reason": "Invalid local profile ID"
                    })
                    continue

                status = str(profile.get("status", "OFFLINE")).upper()

                if status == "RUNNING":
                    summary["skipped"]["running"].append(pid)
                else:
                    proton_ok, proton_key, proton_detail = self._profile_proton_launch_check(profile)
                    if not proton_ok:
                        summary["skipped"].setdefault(proton_key, [])
                        summary["skipped"][proton_key].append(proton_detail)
                    else:
                        summary["launchable_ids"].append(pid)

        summary = self._finalize_launch_summary_counts(summary)

        if summary["launchable_count"] <= 0:
            summary["code"] = "ALL_LOCKED"
            summary["message"] = "No profiles are eligible to launch."
            return summary

        summary["ok"] = True
        summary["code"] = "READY"
        summary["message"] = f"{summary['launchable_count']} profile(s) eligible to launch."
        return summary

    def get_launch_eligibility_summary(self, active_platforms=None):
        """Dashboard preview API for START ALL eligibility."""
        try:
            return self._build_launch_eligibility_summary(active_platforms)
        except Exception as e:
            print(f"[Launch Guard] Eligibility summary failed: {e}")
            summary = self._new_launch_summary(active_platforms)
            summary["code"] = "ERROR"
            summary["message"] = str(e)
            return self._finalize_launch_summary_counts(summary)

    def trigger_start_all(self, active_platforms=None):
        """
        Start all eligible profiles and return a launch summary to the dashboard.
        """
        summary = self._build_launch_eligibility_summary(active_platforms)

        if not summary.get("ok"):
            print(f"[Launch Guard] START ALL blocked: {summary.get('message')}")
            return summary

        active_platforms = summary.get("active_platforms", [])
        launchable_ids = [int(pid) for pid in summary.get("launchable_ids", [])]

        if summary.get("mode") == "coordinator":
            acquired_ids = []
            acquire_failures = []
            target = ",".join(active_platforms) or "Automation"

            for pid in launchable_ids:
                acquired, result = self._acquire_coordinator_profile(pid, target=target)

                if acquired:
                    acquired_ids.append(pid)
                    self.profile_runtime_cache.setdefault(pid, {})
                    self.profile_runtime_cache[pid]["current_target"] = target
                    print(f"[Coordinator] Acquired Profile {pid} for {PC_ID} START ALL.")
                else:
                    acquire_failures.append({
                        "id": pid,
                        "reason": result or "Coordinator acquire failed"
                    })
                    print(f"[Coordinator] START ALL acquire blocked for Profile {pid}: {result}")

            summary["skipped"].setdefault("locked", [])
            summary["skipped"]["locked"].extend(acquire_failures)
            summary["launched_ids"] = acquired_ids
            summary = self._finalize_launch_summary_counts(summary)

            if not acquired_ids:
                summary["ok"] = False
                summary["code"] = "ALL_LOCKED"
                summary["message"] = "No coordinator profiles could be acquired."
                return summary

            print(f"\n[Backend] Coordinator START ALL launching IDs: {acquired_ids} | Platforms: {active_platforms}")
            self.ghost_core.execute_fleet(active_platforms, specific_ids=acquired_ids, instant=False)

        else:
            summary["launched_ids"] = launchable_ids
            summary = self._finalize_launch_summary_counts(summary)

            print(f"\n[Backend] Local START ALL launching IDs: {launchable_ids} | Platforms: {active_platforms}")
            self.ghost_core.execute_fleet(active_platforms, specific_ids=launchable_ids, instant=False)

        summary["ok"] = True
        summary["code"] = "SUCCESS"
        summary["message"] = (
            f"Launch started: {summary['launched_count']} launched, "
            f"{summary['skipped_counts']['running']} running skipped, "
            f"{summary['skipped_counts']['locked']} locked skipped, "
            f"{summary['skipped_counts']['invalid']} invalid skipped."
        )
        return summary


    def _normalize_profile_create_count(self, count):
        try:
            count = int(count)
        except Exception:
            count = 1
        return max(1, min(500, count))

    def _remember_hardware_signature(self, signatures, hardware):
        if not isinstance(hardware, dict):
            return
        signature = hardware.get("fingerprint_signature") or hardware.get("fingerprint_id")
        if signature:
            signatures.add(str(signature))
        device_name = hardware.get("device_name")
        if device_name:
            signatures.add(f"device:{device_name}")

    def trigger_create_profile(self):
        result = self.trigger_create_profiles(1)
        return "SUCCESS" if result and result.get("ok") else "ERROR"

    def trigger_create_profiles(self, count=1):
        requested_count = self._normalize_profile_create_count(count)
        print(f"\n[Backend] CREATE PROFILES signal received. Count={requested_count}")

        preflight = self._build_launch_preflight()
        extension_ready = not any(
            error.get("code") == "PROTON_EXTENSION_MISSING"
            for error in preflight.get("errors", [])
        )

        created = []
        errors = []

        # Try central coordinator only if it is reachable.
        coordinator_profiles = self._get_coordinator_profiles()

        if coordinator_profiles is not None:
            working_profiles = list(coordinator_profiles)
            signatures = self._used_device_signatures(working_profiles)

            for _ in range(requested_count):
                next_id = self._next_profile_number(working_profiles)
                name = f"Profile {next_id}"
                hardware_type = self._next_hardware_type(working_profiles)

                hardware = self.ghost_core._generate_hardware_cloak(
                    next_id,
                    existing_signatures=signatures,
                    forced_type=hardware_type
                )
                cloak_string = hardware["display_string"]
                hardware_json = self._hardware_profile_json(hardware)

                result = self._create_coordinator_profile(name, cloak_string, hardware_json)
                print(f"[Coordinator] Create profile result: {result}")

                if result and result.get("ok"):
                    profile_row = result.get("profile") or {}
                    created_id = profile_row.get("id") or next_id
                    created.append({
                        "id": created_id,
                        "name": name,
                        "type": hardware.get("type", "Unknown"),
                        "hardware": cloak_string
                    })
                    self._remember_hardware_signature(signatures, hardware)
                    working_profiles.append({
                        "id": created_id,
                        "name": name,
                        "hardware_cloak": cloak_string,
                        "hardware_profile_json": hardware_json,
                        "hardware_profile": hardware
                    })
                    continue

                errors.append(result.get("error") if isinstance(result, dict) else "Coordinator create failed")
                break

            if created or not errors:
                return {
                    "ok": len(created) > 0,
                    "code": "SUCCESS" if created else "ERROR",
                    "source": "coordinator",
                    "requested": requested_count,
                    "created": len(created),
                    "profiles": created,
                    "errors": errors,
                    "extension_ready": extension_ready,
                    "proton_assignment": {
                        "ok": True,
                        "message": "Coordinator profiles created. Proton account assignment is handled on the PC that owns the local vault."
                    },
                    "message": f"Created {len(created)} of {requested_count} profile(s)."
                }

            print("[Coordinator] Create failed before any profile was made. Falling back to local profile creation.")

        # Local fallback mode.
        existing_profiles = self.db.get_all_profiles()
        working_profiles = list(existing_profiles)
        signatures = self._used_device_signatures(working_profiles)

        for _ in range(requested_count):
            next_id = self._next_profile_number(working_profiles)
            name = f"Profile {next_id}"
            hardware_type = self._next_hardware_type(working_profiles)

            hardware = self.ghost_core._generate_hardware_cloak(
                next_id,
                existing_signatures=signatures,
                forced_type=hardware_type
            )
            cloak_string = hardware["display_string"]
            hardware_json = self._hardware_profile_json(hardware)

            created_id = self.db.create_profile(
                name,
                cloak_string,
                hardware_json,
                rebalance_proton=False
            )

            if not created_id:
                errors.append(f"Could not create {name}")
                continue

            created.append({
                "id": created_id,
                "name": name,
                "type": hardware.get("type", "Unknown"),
                "hardware": cloak_string
            })
            self._remember_hardware_signature(signatures, hardware)
            working_profiles.append({
                "id": created_id,
                "name": name,
                "hardware_cloak": cloak_string,
                "hardware_profile_json": hardware_json,
                "hardware_profile": hardware
            })
            print(f"[Vault] Stored locally: {name} | id={created_id} | {cloak_string} | {hardware['type']}")

        assignment = self.db.rebalance_proton_profile_assignments()
        proton_status = self.db.get_proton_account_status()

        return {
            "ok": len(created) > 0,
            "code": "SUCCESS" if created else "ERROR",
            "source": "local",
            "requested": requested_count,
            "created": len(created),
            "profiles": created,
            "errors": errors,
            "extension_ready": extension_ready,
            "proton_assignment": assignment,
            "proton_status": proton_status,
            "message": f"Created {len(created)} of {requested_count} profile(s)."
        }

    def trigger_open_selected(self, profile_ids, active_platforms=None):
        """
        Manual Open Selected.

        This is NOT a session run.
        It must open immediately with no random launch delay.

        Manual open always uses raw/manual browser mode:
            active_platforms = []
        """
        try:
            clean_ids = [int(pid) for pid in profile_ids]
        except Exception as e:
            print(f"[Backend] Invalid profile IDs received: {profile_ids} | {e}")
            return "ERROR"

        if not clean_ids:
            return "NO_SELECTION"

        if self.check_worker_block_status():
            print(f"[Backend] OPEN SELECTED blocked: this PC is blocked by coordinator. {self.blocked_reason}")
            return "PC_BLOCKED"

        manual_platforms = []
        target = "Manual"

        print(f"\n[Backend] âš¡ MANUAL OPEN selected IDs instantly: {clean_ids}")

        coordinator_profiles = self._get_coordinator_profiles()

        if coordinator_profiles is not None:
            acquired_ids = []

            for pid in clean_ids:
                acquired, result = self._acquire_coordinator_profile(pid, target=target)

                if acquired:
                    acquired_ids.append(pid)
                    self.profile_runtime_cache.setdefault(pid, {})
                    self.profile_runtime_cache[pid]["current_target"] = target
                    print(f"[Coordinator] Acquired Profile {pid} for {PC_ID} manual open.")
                else:
                    print(f"[Coordinator] Blocked Profile {pid}: {result}")

            if not acquired_ids:
                print("[Coordinator] No selected profiles were available for manual open.")
                return "ALL_LOCKED"

            self.ghost_core.execute_fleet(
                manual_platforms,
                specific_ids=acquired_ids,
                instant=True
            )
            return "SUCCESS"

        # Local fallback mode.
        print(f"[Backend] Coordinator offline. Manual opening local IDs instantly: {clean_ids}")

        self.ghost_core.execute_fleet(
            manual_platforms,
            specific_ids=clean_ids,
            instant=True
        )

        return "SUCCESS"

    def trigger_stop_all(self):
        """Fires the global kill switch and releases this PC's coordinator locks."""
        def release_coordinator_after_shutdown():
            if self._coordinator_enabled():
                result = self._release_all_coordinator_profiles()
                print(f"[Coordinator] Released all profiles for {PC_ID}: {result}")

        result = self.ghost_core.abort_fleet(
            randomized=True,
            min_delay=30,
            max_delay=180,
            on_complete=release_coordinator_after_shutdown
        )

        if isinstance(result, dict):
            result["code"] = "SUCCESS"
            result["message"] = (
                f"Random STOP ALL scheduled for {result.get('scheduled', 0)} profile(s). "
                f"Profiles will close in random order with {result.get('min_delay', 30)}-"
                f"{result.get('max_delay', 180)} seconds between closes."
            )
            return result

        return "SUCCESS"

    def trigger_delete_selected(self, profile_ids):
        """Deletes profiles from DB and physically wipes their cloned hard drives."""
        import shutil # Used to delete folders
        
        try:
            clean_ids = [int(pid) for pid in profile_ids]
        except Exception:
            return "ERROR"

        if not clean_ids: return "NO_SELECTION"

        print(f"\n[Backend] ðŸ—‘ï¸ Initiation purge for Ghost IDs: {clean_ids}")

        # 1. Erase from the SQLite Database
        self.db.delete_profiles(clean_ids)

        # 2. Physically delete the cloned hard drive folders to save space
        for pid in clean_ids:
            folder_path = os.path.join(BASE_DIR, "comet_profiles", f"profile_{pid}")
            if os.path.exists(folder_path):
                try:
                    shutil.rmtree(folder_path)
                    print(f"[-] Wiped physical drive for Profile {pid}")
                except Exception as e:
                    print(f"[!] Could not wipe drive for Profile {pid}: {e}")

        return "SUCCESS"
        

    def get_analytics_data(self):
        """Returns local analytics data for the Analytics tab."""
        try:
            return self.db.get_analytics_data()
        except Exception as e:
            print(f"[Analytics] get_analytics_data failed: {e}")
            return {
                "ok": False,
                "error": str(e),
                "summary": {},
                "profiles": [],
                "ip_reputation": [],
                "blacklisted_ips": [],
                "platforms": [],
                "events": [],
                "sessions": [],
                "revenue_models": []
            }


    def quarantine_profile(self, profile_id, reason="", score=0):
        """Manual quarantine from dashboard."""
        try:
            result = self.db.quarantine_profile(
                profile_id=profile_id,
                reason=reason or "Manual quarantine from dashboard",
                score=score,
                source="manual"
            )
            return result
        except Exception as e:
            print(f"[Quarantine] Manual quarantine failed for Profile {profile_id}: {e}")
            return {"ok": False, "error": str(e)}

    def unquarantine_profile(self, profile_id, reason="Manual review passed"):
        """Manual unquarantine from dashboard."""
        try:
            result = self.db.unquarantine_profile(
                profile_id=profile_id,
                reason=reason or "Manual review passed"
            )
            return result
        except Exception as e:
            print(f"[Quarantine] Manual unquarantine failed for Profile {profile_id}: {e}")
            return {"ok": False, "error": str(e)}

    def apply_auto_quarantine(self):
        """Manual trigger from dashboard to re-check all profile scores."""
        try:
            return self.db.apply_auto_quarantine(threshold=30, min_events=3)
        except Exception as e:
            print(f"[Quarantine] Manual auto-quarantine scan failed: {e}")
            return {"ok": False, "error": str(e)}

    def _extract_ip_only(self, ip_label_or_ip):
        import re
        raw = str(ip_label_or_ip or "").strip()
        match = re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", raw)
        return match.group(0) if match else ""

    def is_ip_blacklisted(self, ip_label_or_ip):
        """Used by GhostCore after live IP detection; local DB first, coordinator second."""
        ip_address = self._extract_ip_only(ip_label_or_ip)
        if not ip_address:
            return {"blacklisted": False}

        try:
            if hasattr(self.db, "is_ip_blacklisted") and self.db.is_ip_blacklisted(ip_address):
                return {"blacklisted": True, "source": "local", "reason": "Local blacklist"}
        except Exception as e:
            print(f"[Blacklist] Local check failed for {ip_address}: {e}")

        if self._coordinator_enabled():
            result = self._coordinator_request(
                "POST",
                "/api/ip-blacklist/check",
                {"ip": ip_address},
                timeout=1,
                quiet=True
            )

            if result and result.get("ok") and result.get("blacklisted"):
                reason = result.get("reason") or "Coordinator blacklist"
                try:
                    if hasattr(self.db, "add_ip_to_blacklist"):
                        self.db.add_ip_to_blacklist(ip_address, reason=reason, source="coordinator", record_event=False)
                except Exception:
                    pass
                return {"blacklisted": True, "source": "coordinator", "reason": reason}

        return {"blacklisted": False}

    def add_blacklisted_ip(self, ip_address, reason=""):
        """Adds an IP to the local blacklist and, if online, the coordinator blacklist."""
        ip_address = self._extract_ip_only(ip_address)
        if not ip_address:
            return {"ok": False, "error": "Valid IPv4 address required."}

        reason = str(reason or "Manual blacklist from dashboard").strip()
        local_result = self.db.add_ip_to_blacklist(ip_address, reason=reason, source="manual", record_event=True)

        coordinator_result = None
        if self._coordinator_enabled():
            coordinator_result = self._coordinator_request(
                "POST",
                "/api/ip-blacklist/add",
                {
                    "ip": ip_address,
                    "reason": reason,
                    "pc_id": PC_ID
                },
                timeout=2,
                quiet=True,
                force=True
            )

        return {
            "ok": bool(local_result and local_result.get("ok")),
            "ip": ip_address,
            "local": local_result,
            "coordinator": coordinator_result
        }

    def remove_blacklisted_ip(self, ip_address):
        """Removes an IP from the local blacklist and, if online, the coordinator blacklist."""
        ip_address = self._extract_ip_only(ip_address)
        if not ip_address:
            return {"ok": False, "error": "Valid IPv4 address required."}

        local_result = self.db.remove_ip_from_blacklist(ip_address)

        coordinator_result = None
        if self._coordinator_enabled():
            coordinator_result = self._coordinator_request(
                "POST",
                "/api/ip-blacklist/remove",
                {
                    "ip": ip_address,
                    "pc_id": PC_ID
                },
                timeout=2,
                quiet=True,
                force=True
            )

        return {
            "ok": bool(local_result and local_result.get("ok")),
            "ip": ip_address,
            "local": local_result,
            "coordinator": coordinator_result
        }

    def get_blacklisted_ips(self):
        try:
            return {
                "ok": True,
                "blacklisted_ips": self.db.get_blacklisted_ips()
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "blacklisted_ips": []}


    def get_platform_targets(self, platform=None, target_type=None, enabled=None):
        """Returns channel/song/artist/etc. focus targets for the Targets tab."""
        try:
            return {
                "ok": True,
                "targets": self.db.get_platform_targets(
                    platform=platform,
                    target_type=target_type,
                    enabled=enabled
                )
            }
        except Exception as e:
            print(f"[Targets] get_platform_targets failed: {e}")
            return {"ok": False, "error": str(e), "targets": []}

    def add_platform_target(self, payload):
        """Adds a platform focus target from the dashboard."""
        try:
            return self.db.add_platform_target(payload or {})
        except Exception as e:
            print(f"[Targets] add_platform_target failed: {e}")
            return {"ok": False, "error": str(e)}

    def update_platform_target(self, target_id, payload):
        """Updates a platform focus target from the dashboard."""
        try:
            return self.db.update_platform_target(target_id, payload or {})
        except Exception as e:
            print(f"[Targets] update_platform_target failed: {e}")
            return {"ok": False, "error": str(e)}

    def delete_platform_target(self, target_id):
        """Deletes a platform focus target from the dashboard."""
        try:
            return self.db.delete_platform_target(target_id)
        except Exception as e:
            print(f"[Targets] delete_platform_target failed: {e}")
            return {"ok": False, "error": str(e)}

    def set_platform_target_enabled(self, target_id, enabled):
        """Enables/disables a platform focus target from the dashboard."""
        try:
            return self.db.set_platform_target_enabled(target_id, enabled)
        except Exception as e:
            print(f"[Targets] set_platform_target_enabled failed: {e}")
            return {"ok": False, "error": str(e)}

    def get_enabled_platform_targets(self, platform=None):
        """Future automation hook. Returns only enabled targets for a platform."""
        try:
            return {
                "ok": True,
                "targets": self.db.get_enabled_platform_targets(platform=platform)
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "targets": []}

    def validate_platform_targets(self, platform=None):
        """Dashboard validation for saved Targets rows."""
        try:
            if not hasattr(self.db, "validate_platform_targets"):
                return {"ok": False, "error": "Target validation is not available.", "summary": {}, "rows": []}
            return self.db.validate_platform_targets(platform=platform)
        except Exception as e:
            print(f"[Targets] validate_platform_targets failed: {e}")
            return {"ok": False, "error": str(e), "summary": {}, "rows": []}

    def get_safe_route_plan_history(self, limit=10):
        """Returns saved safe route plan history for the PC Control tab."""
        try:
            if not hasattr(self.db, "get_safe_route_plan_history"):
                return {"ok": False, "history": [], "error": "Safe route plan history is not available."}
            return self.db.get_safe_route_plan_history(limit=limit)
        except Exception as e:
            print(f"[RoutePlan] get_safe_route_plan_history failed: {e}")
            return {"ok": False, "history": [], "error": str(e)}

    def _ensure_profile_watchdog_runtime(self):
        if not hasattr(self, "profile_watchdog_last_alert"):
            self.profile_watchdog_last_alert = {}
        if not hasattr(self, "profile_watchdog_lock"):
            self.profile_watchdog_lock = threading.Lock()

    def _collect_profile_watchdog_warnings(self, record_events=False, source="watchdog"):
        """
        Detects profiles parked too long in transitional states.

        This is intentionally diagnostic: it records warnings but does not
        close browsers, relaunch profiles, or change platform runner behavior.
        """
        self._ensure_profile_watchdog_runtime()
        warnings = []
        now = time.time()

        active_sessions = getattr(getattr(self, "ghost_core", None), "active_sessions", {}) or {}
        runtime_cache = getattr(self, "profile_runtime_cache", {}) or {}

        for raw_pid, session in list(active_sessions.items()):
            try:
                pid = int(raw_pid)
            except Exception:
                continue

            session = session if isinstance(session, dict) else {}
            cache = runtime_cache.setdefault(pid, {})
            status = cache.get("status") or session.get("status") or "RUNNING"
            target = cache.get("current_target") or session.get("current_target") or "Unknown"
            lifecycle = self._classify_profile_lifecycle(status, target, active=True)
            state = cache.get("lifecycle_state") or lifecycle.get("state")
            stage = cache.get("lifecycle_stage") or lifecycle.get("stage")
            threshold = self._profile_lifecycle_threshold(state, status, target)

            if threshold <= 0:
                continue

            entered_at = float(cache.get("state_entered_at") or cache.get("last_state_at") or now)
            age_seconds = max(0, int(now - entered_at))
            if age_seconds < threshold:
                continue

            warning = {
                "profile_id": pid,
                "session_id": session.get("session_id", ""),
                "state": state,
                "status": status,
                "stage": stage,
                "target_platform": target,
                "age_seconds": age_seconds,
                "threshold_seconds": threshold,
                "reason": f"Profile {pid} has been in {state} for {age_seconds}s."
            }
            warnings.append(warning)

            if not record_events:
                continue

            signature = f"{pid}:{state}:{status}:{target}"
            last_alert = self.profile_watchdog_last_alert.get(pid, {})
            if (
                last_alert.get("signature") == signature
                and now - float(last_alert.get("at") or 0) < 180
            ):
                continue

            self.profile_watchdog_last_alert[pid] = {
                "signature": signature,
                "at": now
            }

            try:
                if hasattr(self.db, "record_profile_lifecycle"):
                    self.db.record_profile_lifecycle({
                        "profile_id": pid,
                        "session_id": session.get("session_id", ""),
                        "state": "STUCK_WARNING",
                        "status": status,
                        "stage": f"Watchdog warning: {stage}",
                        "target_platform": target,
                        "ip_address": cache.get("ip_origin") or cache.get("ip_address") or "",
                        "source": source,
                        "severity": "warning",
                        "elapsed_seconds": age_seconds,
                        "force_event": True,
                        "details": warning
                    })
            except Exception as e:
                print(f"[Watchdog] Could not record warning for Profile {pid}: {e}")

        return warnings

    def run_profile_watchdog_scan(self):
        """Manual dashboard scan for profiles stuck in transitional states."""
        try:
            with self.profile_watchdog_lock:
                warnings = self._collect_profile_watchdog_warnings(
                    record_events=True,
                    source="manual_watchdog_scan"
                )
            lifecycle = (
                self.db.get_profile_lifecycle_snapshot(limit_events=80)
                if hasattr(self.db, "get_profile_lifecycle_snapshot")
                else {"events": [], "states": [], "summary": {}}
            )
            return {
                "ok": True,
                "warnings": warnings,
                "warning_count": len(warnings),
                "lifecycle": lifecycle
            }
        except Exception as e:
            print(f"[Watchdog] Manual scan failed: {e}")
            return {"ok": False, "error": str(e), "warnings": []}

    def _profile_watchdog_loop(self):
        time.sleep(10)
        while True:
            try:
                with self.profile_watchdog_lock:
                    warnings = self._collect_profile_watchdog_warnings(
                        record_events=True,
                        source="profile_watchdog"
                    )
                if warnings:
                    print(f"[Watchdog] {len(warnings)} stuck profile warning(s) recorded.")
            except Exception as e:
                print(f"[Watchdog] Loop failed: {e}")
            time.sleep(20)

    def get_run_control_center(self):
        """Read-only profile runtime view for PC Control."""
        try:
            profiles = self.db.get_all_profiles()
            active_sessions = getattr(getattr(self, "ghost_core", None), "active_sessions", {}) or {}
            runtime_cache = getattr(self, "profile_runtime_cache", {}) or {}
            watchdog_warnings = self._collect_profile_watchdog_warnings(record_events=False)
            warning_by_id = {}
            for item in watchdog_warnings:
                try:
                    warning_by_id[int(item.get("profile_id"))] = item
                except Exception:
                    continue
            lifecycle = (
                self.db.get_profile_lifecycle_snapshot(limit_events=80)
                if hasattr(self.db, "get_profile_lifecycle_snapshot")
                else {"ok": False, "summary": {}, "states": [], "events": []}
            )
            lifecycle_by_id = {}
            for item in lifecycle.get("states", []) if isinstance(lifecycle, dict) else []:
                try:
                    lifecycle_by_id[int(item.get("profile_id"))] = item
                except Exception:
                    continue

            active_by_id = {}
            for raw_pid, session in active_sessions.items():
                try:
                    active_by_id[int(raw_pid)] = session if isinstance(session, dict) else {}
                except Exception:
                    continue

            rows = []
            counts = {
                "total": len(profiles),
                "active": 0,
                "launching": 0,
                "verified_waiting": 0,
                "stopping": 0,
                "offline": 0,
                "quarantined": 0,
                "watchdog_warnings": len(watchdog_warnings),
                "lifecycle_warnings": 0
            }

            for profile in profiles:
                try:
                    pid = int(profile.get("id") or 0)
                except Exception:
                    pid = 0

                session = active_by_id.get(pid, {})
                cache = runtime_cache.get(pid, {}) if isinstance(runtime_cache, dict) else {}
                lifecycle_row = lifecycle_by_id.get(pid, {})
                status = str(profile.get("status") or "").strip().upper() or "UNKNOWN"
                target = (
                    session.get("current_target")
                    or cache.get("current_target")
                    or profile.get("target_platform")
                    or profile.get("current_target")
                    or "None"
                )
                ip_address = (
                    cache.get("ip_address")
                    or profile.get("last_ip")
                    or profile.get("ip_origin")
                    or "Unknown"
                )

                active = pid in active_by_id
                entered_at = float(cache.get("state_entered_at") or cache.get("last_state_at") or time.time())
                age_seconds = max(0, int(time.time() - entered_at)) if active else 0
                proc_state = "not tracked"
                proc = session.get("proc") if isinstance(session, dict) else None
                if proc is not None:
                    try:
                        proc_state = "alive" if proc.poll() is None else "closed"
                    except Exception:
                        proc_state = "unknown"

                stage = "Idle"
                if active:
                    counts["active"] += 1
                    if status == "STARTING" or str(target).lower() == "launching":
                        stage = "Launching browser"
                        counts["launching"] += 1
                    elif str(target).strip().lower() == "verified":
                        stage = "IP verified / waiting route"
                        counts["verified_waiting"] += 1
                    elif status == "STOPPING" or str(target).strip().lower() == "stop all":
                        stage = "Stopping"
                        counts["stopping"] += 1
                    else:
                        stage = f"Running: {target}"
                elif status == "STOPPING":
                    stage = "Stopping"
                    counts["stopping"] += 1
                elif status == "OFFLINE":
                    stage = "Idle"
                    counts["offline"] += 1
                else:
                    stage = status.title()

                quarantined = bool(int(profile.get("quarantined") or 0))
                if quarantined:
                    counts["quarantined"] += 1

                lifecycle_state = (
                    lifecycle_row.get("state")
                    or cache.get("lifecycle_state")
                    or self._classify_profile_lifecycle(status, target, active=active).get("state")
                )
                lifecycle_stage = (
                    lifecycle_row.get("stage")
                    or cache.get("lifecycle_stage")
                    or stage
                )
                lifecycle_severity = str(
                    lifecycle_row.get("severity")
                    or cache.get("lifecycle_severity")
                    or "info"
                ).lower()
                if lifecycle_severity in {"warning", "error"}:
                    counts["lifecycle_warnings"] += 1

                watchdog = warning_by_id.get(pid)

                rows.append({
                    "profile_id": pid,
                    "profile_name": profile.get("name") or f"Profile {pid}",
                    "status": status,
                    "stage": stage,
                    "lifecycle_state": lifecycle_state,
                    "lifecycle_stage": lifecycle_stage,
                    "lifecycle_severity": lifecycle_severity,
                    "age_seconds": age_seconds,
                    "last_lifecycle_update": lifecycle_row.get("updated_at") or "",
                    "watchdog_status": watchdog.get("reason") if watchdog else "OK",
                    "watchdog_warning": bool(watchdog),
                    "current_target": target,
                    "ip_address": ip_address,
                    "active_session": active,
                    "session_id": session.get("session_id", "") if isinstance(session, dict) else "",
                    "debug_port": session.get("debug_port", "") if isinstance(session, dict) else "",
                    "process_state": proc_state,
                    "profile_dir": session.get("profile_dir", "") if isinstance(session, dict) else "",
                    "quarantined": quarantined,
                    "quarantine_reason": profile.get("quarantine_reason") or ""
                })

            rows.sort(key=lambda item: (0 if item.get("active_session") else 1, item.get("profile_id") or 0))

            return {
                "ok": True,
                "summary": counts,
                "rows": rows,
                "watchdog": {
                    "warnings": watchdog_warnings,
                    "warning_count": len(watchdog_warnings)
                },
                "lifecycle": lifecycle,
                "safe_mode": True
            }
        except Exception as e:
            print(f"[RunControl] get_run_control_center failed: {e}")
            return {"ok": False, "error": str(e), "summary": {}, "rows": []}

    def _ensure_autoscale_runtime(self):
        if not hasattr(self, "autoscale_managed_profile_ids"):
            self.autoscale_managed_profile_ids = set()
        if not hasattr(self, "autoscale_last_action_at"):
            self.autoscale_last_action_at = 0
        if not hasattr(self, "autoscale_lock"):
            self.autoscale_lock = threading.Lock()

    def _autoscale_collect_metrics(self):
        ram = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.1)
        try:
            gpu = self.get_gpu_load()
        except Exception:
            gpu = 0

        cpu_threads = psutil.cpu_count(logical=True) or 1
        available_ram_gb = ram.available / (1024 ** 3)
        total_ram_gb = ram.total / (1024 ** 3)
        reserved_ram_gb = max(4.0, total_ram_gb * 0.15)
        usable_ram_gb = max(0, available_ram_gb - reserved_ram_gb)
        profiles_by_cpu = int(cpu_threads * 3 * max(0.25, (100 - cpu) / 100))
        profiles_by_ram = int(usable_ram_gb / 0.65)
        safe_limit = max(1, min(profiles_by_cpu, profiles_by_ram))

        active_sessions = getattr(getattr(self, "ghost_core", None), "active_sessions", {}) or {}
        active_ids = []
        for raw_pid in active_sessions.keys():
            try:
                active_ids.append(int(raw_pid))
            except Exception:
                pass

        profiles = self._get_coordinator_profiles()
        source = "coordinator" if profiles is not None else "local"
        if profiles is None:
            profiles = self.db.get_all_profiles()

        return {
            "cpu": round(float(cpu or 0), 1),
            "ram_percent": round(float(ram.percent or 0), 1),
            "gpu": round(float(gpu or 0), 1),
            "safe_limit": int(safe_limit),
            "active_profiles": len(active_ids),
            "active_ids": active_ids,
            "profiles": profiles,
            "profile_source": source
        }

    def _autoscale_candidate_profile_ids(self, metrics):
        active_ids = set(metrics.get("active_ids") or [])
        profiles = metrics.get("profiles") if isinstance(metrics.get("profiles"), list) else []
        candidates = []

        for profile in profiles:
            try:
                pid = int(profile.get("id"))
            except Exception:
                continue
            if pid in active_ids:
                continue
            status = str(profile.get("status") or "OFFLINE").upper()
            if status in {"RUNNING", "STARTING", "STOPPING", "BLACKLISTED"}:
                continue
            if int(profile.get("quarantined") or 0):
                continue
            candidates.append(pid)

        rng = random.SystemRandom()
        rng.shuffle(candidates)
        return candidates

    def _autoscale_decision(self, config, metrics):
        active = int(metrics.get("active_profiles") or 0)
        safe_limit = int(metrics.get("safe_limit") or 1)
        target = int(config.get("target_profiles") or 0)
        min_profiles = int(config.get("min_profiles") or 0)
        max_profiles = int(config.get("max_profiles") or target or 1)
        desired = max(min_profiles, min(target, max_profiles, safe_limit))

        high_resource = (
            float(metrics.get("cpu") or 0) >= float(config.get("cpu_high") or 82) or
            float(metrics.get("ram_percent") or 0) >= float(config.get("ram_high") or 88) or
            float(metrics.get("gpu") or 0) >= float(config.get("gpu_high") or 92)
        )
        low_resource = (
            float(metrics.get("cpu") or 0) <= float(config.get("cpu_low") or 68) and
            float(metrics.get("ram_percent") or 0) <= float(config.get("ram_low") or 78) and
            float(metrics.get("gpu") or 0) <= float(config.get("gpu_low") or 85)
        )

        now = time.time()
        cooldown = int(config.get("cooldown_seconds") or 90)
        seconds_since_action = now - float(getattr(self, "autoscale_last_action_at", 0) or 0)
        cooldown_active = seconds_since_action < cooldown

        decision = {
            "action": "hold",
            "reason": "Profile count is within target range.",
            "desired_profiles": desired,
            "scale_count": 0,
            "cooldown_active": cooldown_active,
            "seconds_until_next_action": max(0, int(cooldown - seconds_since_action)),
            "high_resource": high_resource,
            "low_resource": low_resource,
            "launch_ids": [],
            "close_ids": []
        }

        if cooldown_active:
            decision["reason"] = "Cooldown active; waiting before next autoscale action."
            return decision

        if high_resource and active > min_profiles:
            decision["action"] = "scale_down"
            decision["scale_count"] = min(int(config.get("scale_down_step") or 1), active - min_profiles)
            decision["reason"] = "Resource pressure is high; closing managed autoscale profile(s)."
            return decision

        if active > desired:
            decision["action"] = "scale_down"
            decision["scale_count"] = min(int(config.get("scale_down_step") or 1), active - desired)
            decision["reason"] = "Active profile count is above desired target."
            return decision

        if active < desired and low_resource:
            candidates = self._autoscale_candidate_profile_ids(metrics)
            decision["action"] = "scale_up"
            decision["scale_count"] = min(int(config.get("scale_up_step") or 1), desired - active, len(candidates))
            decision["launch_ids"] = candidates[:decision["scale_count"]]
            decision["reason"] = "Resources are healthy and active profile count is below target."
            if decision["scale_count"] <= 0:
                decision["action"] = "hold"
                decision["reason"] = "No eligible offline profiles are available to scale up."
            return decision

        if active < desired:
            decision["reason"] = "Below target, but resources are not low enough for a safe scale-up."
        return decision

    def _autoscale_launch_manual_profiles(self, profile_ids):
        clean_ids = []
        for pid in profile_ids or []:
            try:
                clean_ids.append(int(pid))
            except Exception:
                pass
        if not clean_ids:
            return []

        if self.check_worker_block_status():
            print(f"[Autoscale] Launch blocked: {self.blocked_reason}")
            return []

        coordinator_profiles = self._get_coordinator_profiles()
        launched_ids = []

        if coordinator_profiles is not None:
            for pid in clean_ids:
                acquired, result = self._acquire_coordinator_profile(pid, target="Autoscale Manual")
                if acquired:
                    launched_ids.append(pid)
                    self.profile_runtime_cache.setdefault(pid, {})
                    self.profile_runtime_cache[pid]["current_target"] = "Autoscale Manual"
                else:
                    print(f"[Autoscale] Coordinator acquire failed for Profile {pid}: {result}")
        else:
            launched_ids = clean_ids

        if launched_ids:
            self.autoscale_managed_profile_ids.update(launched_ids)
            self.ghost_core.execute_fleet([], specific_ids=launched_ids, instant=True)

        return launched_ids

    def _autoscale_close_managed_profiles(self, count, allow_unmanaged=False):
        self._ensure_autoscale_runtime()
        active_sessions = getattr(getattr(self, "ghost_core", None), "active_sessions", {}) or {}
        managed = []
        unmanaged = []

        for raw_pid, session in list(active_sessions.items()):
            try:
                pid = int(raw_pid)
            except Exception:
                continue
            if pid in self.autoscale_managed_profile_ids:
                managed.append((pid, session))
            else:
                unmanaged.append((pid, session))

        rng = random.SystemRandom()
        rng.shuffle(managed)
        rng.shuffle(unmanaged)
        selected = managed[:max(0, int(count or 0))]
        if allow_unmanaged and len(selected) < int(count or 0):
            selected.extend(unmanaged[:int(count or 0) - len(selected)])

        closed = []
        for pid, session in selected:
            try:
                ok = self.ghost_core._close_stop_all_session(
                    pid,
                    session,
                    close_reason="Autoscale resource adjustment"
                )
                if ok:
                    closed.append(pid)
                    self.autoscale_managed_profile_ids.discard(pid)
                    if pid in self.coordinator_owned_profile_ids:
                        self._release_coordinator_profile(pid, force=True)
            except Exception as e:
                print(f"[Autoscale] Could not close Profile {pid}: {e}")
        return closed

    def _autoscale_reward(self, action, metrics, changed_count):
        cpu = float(metrics.get("cpu") or 0)
        ram = float(metrics.get("ram_percent") or 0)
        gpu = float(metrics.get("gpu") or 0)
        pressure = max(cpu / 100.0, ram / 100.0, gpu / 100.0)
        reward = 1.0 - pressure
        if action in {"scale_up", "scale_down"} and int(changed_count or 0) > 0:
            reward += 0.25
        if pressure >= 0.9:
            reward -= 1.0
        return round(float(reward), 3)

    def _record_autoscale_learning(self, event_payload, observation_profiles=None):
        try:
            self.db.record_autoscale_event(event_payload)
        except Exception:
            pass

        observation_profiles = observation_profiles if isinstance(observation_profiles, list) else []
        if not observation_profiles:
            observation_profiles = [None]

        for pid in observation_profiles:
            payload = {
                "source": event_payload.get("source") or "autoscale",
                "event_type": "AUTOSCALE_DECISION",
                "profile_id": pid,
                "action": event_payload.get("action") or "hold",
                "action_result": event_payload.get("reason") or "",
                "reward": event_payload.get("reward") or 0.0,
                "cpu_percent": event_payload.get("cpu_percent") or 0.0,
                "ram_percent": event_payload.get("ram_percent") or 0.0,
                "gpu_percent": event_payload.get("gpu_percent") or 0.0,
                "active_profiles": event_payload.get("active_profiles") or 0,
                "target_profiles": event_payload.get("desired_profiles") or 0,
                "details": event_payload
            }
            try:
                self.db.record_ml_observation(payload)
            except Exception:
                pass

    def run_autoscale_once(self, dry_run=False, source="manual"):
        """Runs one resource-aware autoscale cycle. Scale-up opens manual-mode browsers only."""
        self._ensure_autoscale_runtime()
        if not self.autoscale_lock.acquire(blocking=False):
            return {"ok": False, "error": "Autoscale cycle already running."}

        try:
            config = self.db.get_autoscale_config()
            metrics = self._autoscale_collect_metrics()
            decision = self._autoscale_decision(config, metrics)
            action = decision.get("action") or "hold"
            launched_ids = []
            closed_ids = []

            if not dry_run and action == "scale_up":
                launched_ids = self._autoscale_launch_manual_profiles(decision.get("launch_ids") or [])
                decision["launch_ids"] = launched_ids
                if launched_ids:
                    self.autoscale_last_action_at = time.time()

            elif not dry_run and action == "scale_down":
                closed_ids = self._autoscale_close_managed_profiles(
                    decision.get("scale_count") or 0,
                    allow_unmanaged=not bool(config.get("close_autoscale_only", True))
                )
                decision["close_ids"] = closed_ids
                if closed_ids:
                    self.autoscale_last_action_at = time.time()
                elif config.get("close_autoscale_only", True):
                    decision["action"] = "hold"
                    decision["reason"] = "Scale-down requested, but no autoscale-managed active profiles were available to close."
                    action = "hold"

            changed_count = len(launched_ids) + len(closed_ids)
            reward = self._autoscale_reward(decision.get("action") or action, metrics, changed_count)

            event_payload = {
                "source": source or "manual",
                "mode": config.get("mode") or "manual_profile_scaling",
                "enabled": bool(config.get("enabled")),
                "action": "dry_run_" + action if dry_run else decision.get("action") or action,
                "reason": decision.get("reason") or "",
                "active_profiles": metrics.get("active_profiles") or 0,
                "desired_profiles": decision.get("desired_profiles") or 0,
                "safe_limit": metrics.get("safe_limit") or 0,
                "cpu_percent": metrics.get("cpu") or 0.0,
                "ram_percent": metrics.get("ram_percent") or 0.0,
                "gpu_percent": metrics.get("gpu") or 0.0,
                "launch_ids": decision.get("launch_ids") or [],
                "close_ids": decision.get("close_ids") or [],
                "reward": reward,
                "details": {
                    "dry_run": bool(dry_run),
                    "config": config,
                    "decision": decision,
                    "metrics": {
                        k: v for k, v in metrics.items()
                        if k not in {"profiles"}
                    }
                }
            }
            self._record_autoscale_learning(
                event_payload,
                observation_profiles=(decision.get("launch_ids") or []) + (decision.get("close_ids") or [])
            )

            learning = self.db.get_learning_summary(limit=12)
            return {
                "ok": True,
                "dry_run": bool(dry_run),
                "config": config,
                "metrics": {k: v for k, v in metrics.items() if k not in {"profiles"}},
                "decision": decision,
                "launched_ids": launched_ids,
                "closed_ids": closed_ids,
                "reward": reward,
                "learning": learning
            }

        except Exception as e:
            print(f"[Autoscale] Cycle failed: {e}")
            return {"ok": False, "error": str(e)}
        finally:
            try:
                self.autoscale_lock.release()
            except Exception:
                pass

    def get_autoscale_learning_status(self):
        """Returns autoscale config, current dry-run decision, and learning history."""
        try:
            self._ensure_autoscale_runtime()
            config = self.db.get_autoscale_config()
            metrics = self._autoscale_collect_metrics()
            decision = self._autoscale_decision(config, metrics)
            learning = self.db.get_learning_summary(limit=20)
            return {
                "ok": True,
                "config": config,
                "metrics": {k: v for k, v in metrics.items() if k not in {"profiles"}},
                "decision": decision,
                "managed_profile_ids": sorted(list(self.autoscale_managed_profile_ids)),
                "learning": learning
            }
        except Exception as e:
            print(f"[Autoscale] Status failed: {e}")
            return {"ok": False, "error": str(e)}

    def set_autoscale_config(self, payload=None):
        try:
            result = self.db.set_autoscale_config(payload if isinstance(payload, dict) else {})
            return result
        except Exception as e:
            print(f"[Autoscale] Config save failed: {e}")
            return {"ok": False, "error": str(e)}

    def _autoscale_background_loop(self):
        time.sleep(5)
        while True:
            try:
                config = self.db.get_autoscale_config()
                interval = int(config.get("loop_interval_seconds") or 30)
                if config.get("enabled"):
                    self.run_autoscale_once(dry_run=False, source="autoscale_loop")
                time.sleep(max(10, min(600, interval)))
            except Exception as e:
                print(f"[Autoscale] Background loop error: {e}")
                time.sleep(30)

    def _normalize_route_plan_platforms(self, active_platforms=None):
        allowed = ["youtube", "twitch", "spotify", "deezer"]

        if not active_platforms:
            return []

        clean = []
        for item in active_platforms:
            value = str(item or "").strip().lower()
            if value in allowed and value not in clean:
                clean.append(value)

        return clean

    def _recent_platform_by_profile(self):
        recent = {}

        if not hasattr(self.db, "_get_connection"):
            return recent

        ignored = {"", "pending", "unknown", "manual", "launching", "none", "ip blacklisted", "duplicate ip"}
        try:
            with self.db._get_connection() as conn:
                conn.row_factory = None
                rows = conn.execute("""
                    SELECT profile_id, platform
                    FROM profile_sessions
                    WHERE profile_id IS NOT NULL
                    ORDER BY started_at DESC, rowid DESC
                    LIMIT 1000
                """).fetchall()

            for profile_id, platform in rows:
                try:
                    pid = int(profile_id)
                except Exception:
                    continue
                if pid in recent:
                    continue

                platform_key = str(platform or "").strip().lower()
                if platform_key in ignored:
                    continue
                recent[pid] = platform_key

        except Exception as e:
            print(f"[RoutePlan] Could not load recent platform history: {e}")

        return recent

    def get_safe_automation_route_plan(self, active_platforms=None):
        """
        Builds a randomized automation route plan without executing public platform navigation.

        Safety notes:
        - This is planning/reporting only.
        - It does not open YouTube/Twitch/Spotify/Deezer.
        - It limits each profile to at most two active platforms per session.
        """
        try:
            platforms = self._normalize_route_plan_platforms(active_platforms)
            profiles = self.db.get_all_profiles()
            rng = random.SystemRandom()
            rng.shuffle(profiles)

            if not platforms:
                summary = {
                    "safe_mode": True,
                    "profile_count": len(profiles),
                    "active_platforms": [],
                    "platforms_per_profile": 0,
                    "note": "No platforms are toggled ON.",
                    "public_navigation_executed": False,
                    "persisted": False
                }
                saved = self.db.save_safe_route_plan([], [], summary) if hasattr(self.db, "save_safe_route_plan") else {}
                summary["persisted"] = bool(saved and saved.get("ok"))
                if saved and saved.get("route_plan_id"):
                    summary["route_plan_id"] = saved.get("route_plan_id")
                return {
                    "ok": True,
                    "plan": [],
                    "summary": summary,
                    "route_plan_id": saved.get("route_plan_id") if isinstance(saved, dict) else None
                }

            platforms_per_profile = min(2, len(platforms))
            recent_platforms = self._recent_platform_by_profile()
            plan = []

            for order, profile in enumerate(profiles, start=1):
                pid = int(profile.get("id") or 0)
                pool = list(platforms)
                rng.shuffle(pool)

                last_platform = recent_platforms.get(pid, "")

                if platforms_per_profile == 1:
                    if last_platform in pool and len(pool) > 1:
                        alternatives = [p for p in pool if p != last_platform]
                        selected = [rng.choice(alternatives)]
                    else:
                        selected = [pool[0]]
                else:
                    selected = pool[:platforms_per_profile]
                    if last_platform and selected and selected[0] == last_platform:
                        for idx, value in enumerate(selected[1:], start=1):
                            if value != last_platform:
                                selected[0], selected[idx] = selected[idx], selected[0]
                                break

                random_warmup_seconds = rng.randint(30, 90)

                plan.append({
                    "order": order,
                    "profile_id": pid,
                    "profile_name": profile.get("name") or f"Profile {pid}",
                    "last_platform": last_platform or "None",
                    "planned_platforms": selected,
                    "random_warmup_seconds": random_warmup_seconds,
                    "session_minutes": 180,
                    "target_policy": "Safe planning only; approved test targets required before navigation.",
                    "notes": (
                        "Avoided last platform when possible."
                        if last_platform and selected and selected[0] != last_platform
                        else "Randomized platform plan."
                    )
                })

            summary = {
                "safe_mode": True,
                "profile_count": len(profiles),
                "active_platforms": platforms,
                "platforms_per_profile": platforms_per_profile,
                "session_minutes": 180,
                "random_warmup_min_seconds": 30,
                "random_warmup_max_seconds": 90,
                "public_navigation_executed": False,
                "persisted": False
            }
            saved = self.db.save_safe_route_plan(platforms, plan, summary) if hasattr(self.db, "save_safe_route_plan") else {}
            summary["persisted"] = bool(saved and saved.get("ok"))
            if saved and saved.get("route_plan_id"):
                summary["route_plan_id"] = saved.get("route_plan_id")

            return {
                "ok": True,
                "plan": plan,
                "summary": summary,
                "route_plan_id": saved.get("route_plan_id") if isinstance(saved, dict) else None
            }

        except Exception as e:
            print(f"[RoutePlan] Safe route plan failed: {e}")
            return {"ok": False, "error": str(e), "plan": [], "summary": {}}

    def _stable_identity_hash(self, value, length=12):
        if isinstance(value, (dict, list)):
            raw = json.dumps(value, sort_keys=True, ensure_ascii=True)
        else:
            raw = str(value or "")
        return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:length]

    def _profile_identity_key(self, hardware):
        hardware = hardware if isinstance(hardware, dict) else {}
        return {
            "type": hardware.get("type", ""),
            "device_name": hardware.get("device_name", ""),
            "os": hardware.get("os", ""),
            "os_version": hardware.get("os_version", ""),
            "resolution": hardware.get("resolution") or [],
            "device_scale_factor": hardware.get("device_scale_factor", ""),
            "language": hardware.get("language", ""),
            "platform": hardware.get("platform", ""),
            "renderer": hardware.get("renderer", ""),
            "user_agent": hardware.get("user_agent", ""),
            "mobile": hardware.get("mobile", ""),
            "touch_points": hardware.get("touch_points", ""),
            "hardware_concurrency": hardware.get("hardware_concurrency", ""),
            "device_memory": hardware.get("device_memory", ""),
        }

    def get_profile_identity_report(self):
        """Read-only dashboard report for saved profile device identities."""
        try:
            profiles = self._get_coordinator_profiles()
            source = "coordinator" if profiles is not None else "local"
            if profiles is None:
                profiles = self.db.get_all_profiles()

            rows = []
            identity_counts = {}
            signature_counts = {}
            model_counts = {}

            for profile in profiles:
                hardware = (
                    profile.get("hardware_profile")
                    or self._hardware_profile_from_text(profile.get("hardware_profile_json"))
                    or self._hardware_profile_from_text(profile.get("hardware_cloak"))
                    or {}
                )
                if not isinstance(hardware, dict):
                    hardware = {}

                has_identity = bool(hardware)
                identity_key = self._profile_identity_key(hardware)
                identity_hash = self._stable_identity_hash(identity_key) if has_identity else ""
                signature = str(hardware.get("fingerprint_signature") or hardware.get("fingerprint_id") or "")
                signature_hash = self._stable_identity_hash(signature) if signature else ""
                model = str(hardware.get("device_name") or "")

                if identity_hash:
                    identity_counts[identity_hash] = identity_counts.get(identity_hash, 0) + 1
                if signature_hash:
                    signature_counts[signature_hash] = signature_counts.get(signature_hash, 0) + 1
                if model:
                    model_counts[model] = model_counts.get(model, 0) + 1

                resolution = hardware.get("resolution") or []
                width = resolution[0] if isinstance(resolution, list) and len(resolution) > 0 else ""
                height = resolution[1] if isinstance(resolution, list) and len(resolution) > 1 else ""

                rows.append({
                    "id": profile.get("id") or profile.get("profile_id") or "",
                    "name": profile.get("name") or "",
                    "status": profile.get("status") or "OFFLINE",
                    "locked_by": profile.get("locked_by") or "",
                    "last_ip": profile.get("last_ip") or profile.get("ip_origin") or profile.get("ip") or "",
                    "type": hardware.get("type") or "",
                    "device_name": model,
                    "os": hardware.get("os") or "",
                    "os_version": hardware.get("os_version") or "",
                    "viewport": f"{width}x{height}" if width and height else "",
                    "language": hardware.get("language") or "",
                    "platform": hardware.get("platform") or "",
                    "hardware_concurrency": hardware.get("hardware_concurrency") or "",
                    "device_memory": hardware.get("device_memory") or "",
                    "touch_points": hardware.get("touch_points") or "",
                    "renderer": hardware.get("renderer") or "",
                    "user_agent_hash": self._stable_identity_hash(hardware.get("user_agent") or "") if hardware.get("user_agent") else "",
                    "identity_hash": identity_hash,
                    "signature_hash": signature_hash,
                    "has_identity": has_identity,
                    "_model": model,
                })

            desktop_count = 0
            mobile_count = 0
            missing_identity_count = 0

            for row in rows:
                row["duplicate_identity"] = bool(row["identity_hash"]) and identity_counts.get(row["identity_hash"], 0) > 1
                row["duplicate_signature"] = bool(row["signature_hash"]) and signature_counts.get(row["signature_hash"], 0) > 1
                row["duplicate_model"] = bool(row["_model"]) and model_counts.get(row["_model"], 0) > 1

                if not row["has_identity"]:
                    missing_identity_count += 1

                if str(row.get("type") or "").lower() == "desktop":
                    desktop_count += 1
                elif str(row.get("type") or "").lower() == "mobile":
                    mobile_count += 1

                status_bits = []
                if not row["has_identity"]:
                    status_bits.append("Missing identity")
                if row["duplicate_identity"]:
                    status_bits.append("Duplicate identity")
                if row["duplicate_signature"]:
                    status_bits.append("Duplicate signature")
                if row["duplicate_model"]:
                    status_bits.append("Duplicate model")
                row["identity_status"] = "Unique" if not status_bits else ", ".join(status_bits)
                row.pop("_model", None)

            duplicate_identity_count = sum(1 for row in rows if row["duplicate_identity"])
            duplicate_signature_count = sum(1 for row in rows if row["duplicate_signature"])
            duplicate_model_count = sum(1 for row in rows if row["duplicate_model"])
            unique_count = sum(1 for row in rows if row.get("identity_status") == "Unique")
            total = len(rows)
            desktop_percent = round((desktop_count / total) * 100, 1) if total else 0

            return {
                "ok": True,
                "source": source,
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "summary": {
                    "total": total,
                    "desktop_count": desktop_count,
                    "mobile_count": mobile_count,
                    "desktop_percent": desktop_percent,
                    "duplicate_identity_count": duplicate_identity_count,
                    "duplicate_signature_count": duplicate_signature_count,
                    "duplicate_model_count": duplicate_model_count,
                    "missing_identity_count": missing_identity_count,
                    "unique_count": unique_count,
                    "ok": (
                        duplicate_identity_count == 0
                        and duplicate_signature_count == 0
                        and duplicate_model_count == 0
                        and missing_identity_count == 0
                    )
                },
                "rows": rows
            }
        except Exception as e:
            print(f"[Profile Identity] Report failed: {e}")
            return {
                "ok": False,
                "error": str(e),
                "source": "error",
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "summary": {},
                "rows": []
            }

    def fix_duplicate_fingerprints(self):
        """Detects profiles with duplicate or missing fingerprints and regenerates them."""
        try:
            profiles = self._get_coordinator_profiles()
            use_coordinator = profiles is not None
            if profiles is None:
                profiles = self.db.get_all_profiles()

            signature_to_profiles = {}
            for profile in profiles:
                hardware = (
                    profile.get("hardware_profile")
                    or self._hardware_profile_from_text(profile.get("hardware_profile_json"))
                    or self._hardware_profile_from_text(profile.get("hardware_cloak"))
                    or {}
                )
                if not isinstance(hardware, dict):
                    hardware = {}
                sig = hardware.get("fingerprint_signature") or hardware.get("fingerprint_id") or ""
                schema_ok = (
                    isinstance(hardware, dict)
                    and hardware.get("schema") == "comet_device_identity_v2"
                    and str(hardware.get("type", "")).lower() in {"mobile", "desktop"}
                )
                profile["_hardware"] = hardware
                profile["_sig"] = sig
                profile["_schema_ok"] = schema_ok
                if sig:
                    signature_to_profiles.setdefault(sig, []).append(profile)

            # Profiles that need a new fingerprint: missing identity or duplicate signature
            needs_regen = set()
            for profile in profiles:
                if not profile["_schema_ok"] or not profile["_sig"]:
                    needs_regen.add(profile.get("id"))
            for sig, group in signature_to_profiles.items():
                if len(group) > 1:
                    # Keep first, regenerate the rest
                    for p in group[1:]:
                        needs_regen.add(p.get("id"))

            if not needs_regen:
                return {"ok": True, "fixed": 0, "message": "All fingerprints are already unique."}

            # Build existing signatures from profiles that do NOT need regeneration
            good_profiles = [p for p in profiles if p.get("id") not in needs_regen]
            signatures = self._used_device_signatures(
                [{"hardware_profile": p["_hardware"]} for p in good_profiles if p.get("_schema_ok")]
            )

            fixed = 0
            errors = []
            for profile in profiles:
                pid = profile.get("id")
                if pid not in needs_regen:
                    continue
                try:
                    hardware_type = self._next_hardware_type(
                        [{"hardware_profile": p["_hardware"]} for p in profiles if p.get("id") not in needs_regen]
                    )
                    hardware = self.ghost_core._generate_hardware_cloak(
                        pid,
                        existing_signatures=signatures,
                        forced_type=hardware_type,
                    )
                    signatures.add(hardware.get("fingerprint_signature", ""))
                    if hardware.get("device_name"):
                        signatures.add(f"device:{hardware['device_name']}")

                    cloak_string = hardware.get("display_string", "Device")
                    hw_json = self._hardware_profile_json(hardware)

                    if use_coordinator:
                        self._coordinator_request(
                            "POST",
                            f"/api/profiles/{pid}/hardware",
                            json={"hardware_cloak": cloak_string, "hardware_profile_json": hw_json},
                            quiet=True,
                        )
                    else:
                        self.db.update_profile_hardware(pid, cloak_string, hw_json)

                    fixed += 1
                    needs_regen.discard(pid)
                except Exception as e:
                    errors.append(f"Profile {pid}: {e}")

            return {
                "ok": True,
                "fixed": fixed,
                "errors": errors,
                "message": f"Regenerated fingerprints for {fixed} profile(s)." + (
                    f" {len(errors)} error(s)." if errors else ""
                ),
            }
        except Exception as e:
            print(f"[Fix Fingerprints] Failed: {e}")
            return {"ok": False, "error": str(e)}

    def import_proton_accounts(self, text, max_profiles=4):
        """Imports Proton VPN accounts into the local encrypted account vault."""
        try:
            return self.db.import_proton_accounts(text or "", max_profiles=max_profiles or 4)
        except Exception as e:
            print(f"[ProtonVault] Import failed: {e}")
            return {"ok": False, "error": str(e)}

    def get_proton_account_status(self):
        """Returns Proton VPN account/profile assignment status without passwords."""
        try:
            return self.db.get_proton_account_status()
        except Exception as e:
            return {"ok": False, "error": str(e), "accounts": [], "summary": {}}

    def rebalance_proton_accounts(self, max_profiles=4):
        """Reassigns profiles to Proton VPN accounts in account order."""
        try:
            result = self.db.rebalance_proton_profile_assignments(max_profiles=max_profiles or 4)
            status = self.db.get_proton_account_status()
            return {
                "ok": bool(result and result.get("ok")),
                "assignment": result,
                "status": status
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_proton_profile_readiness(self):
        """Profile-level Proton readiness for PC Control / Launch Guard."""
        try:
            return self.db.get_proton_profile_readiness()
        except Exception as e:
            return {"ok": False, "error": str(e), "profiles": [], "summary": {}}

    def set_profile_proton_setup_status(self, profile_id, setup_status, notes=""):
        """Marks one profile READY / NEEDS_LOGIN / SETUP_OPENED / BLOCKED."""
        try:
            result = self.db.set_profile_proton_setup_status(
                profile_id=profile_id,
                setup_status=setup_status,
                notes=notes or "",
                source="dashboard"
            )
            status = self.db.get_proton_account_status()
            return {
                "ok": bool(result and result.get("ok")),
                "result": result,
                "status": status
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def open_proton_setup_profile(self, profile_id):
        """
        Opens a selected profile for manual Proton login/setup.
        This does not automate Proton login; it only opens the assigned profile safely.
        """
        try:
            profile_id = int(profile_id)
        except Exception:
            return {"ok": False, "error": "Invalid profile ID"}

        mark = self.db.set_profile_proton_setup_status(
            profile_id=profile_id,
            setup_status="SETUP_OPENED",
            notes="Opened for manual Proton setup from dashboard.",
            source="open_proton_setup"
        )
        if not mark.get("ok"):
            return mark

        result = self.trigger_open_selected([profile_id], [])
        return {
            "ok": result == "SUCCESS",
            "profile_id": profile_id,
            "open_result": result,
            "message": "Profile opened for manual Proton setup." if result == "SUCCESS" else str(result)
        }

    def get_profile_data(self):
        """
        Fetches all profiles and forces UI-compatible fields.

        This prevents the dashboard from staying stuck on:
        - Current Target = None
        - Live IP / Country = Checking...

        even when the database already has the correct values.
        """
        profiles = self.db.get_all_profiles()

        fixed_profiles = []

        for p in profiles:
            pid = p.get("id")

            status = str(
                p.get("status")
                or "OFFLINE"
            ).strip()

            target = str(
                p.get("target_platform")
                or p.get("current_target")
                or p.get("currentTarget")
                or p.get("target")
                or "None"
            ).strip()

            ip = str(
                p.get("last_ip")
                or p.get("ip_origin")
                or p.get("ipOrigin")
                or p.get("ip")
                or ""
            ).strip()

            if not ip or ip.lower() in ["none", "unknown", "not verified", "checking", "checking..."]:
                ip = "Checking..."

            if not target or target.lower() in ["none", "unknown", "null"]:
                target = "None"

            # Force every possible frontend alias.
            p["status"] = status

            p["target_platform"] = target
            p["current_target"] = target
            p["currentTarget"] = target
            p["target"] = target

            p["last_ip"] = ip
            p["ip_origin"] = ip
            p["ipOrigin"] = ip
            p["ip"] = ip
            p["live_ip"] = ip
            p["liveIp"] = ip
            p["live_ip_country"] = ip
            p["liveIpCountry"] = ip

            fixed_profiles.append(p)

        # Debug line so we can confirm Python is sending the right value to the UI.
        for p in fixed_profiles:
            if str(p.get("status", "")).upper() == "RUNNING":
                print(
                    f"[UI DATA] Profile {p.get('id')} -> "
                    f"status={p.get('status')} | "
                    f"target={p.get('current_target')} | "
                    f"ip={p.get('ip_origin')}"
                )

        return fixed_profiles


    def get_laptop_sync_status(self):
        """
        Local laptop coding/sync status for the dashboard.

        Reads:
            _sync_status/sync_status.json

        This does not contact the Main PC. It only reports what the local
        laptop sync loop last wrote.
        """
        try:
            status_path = os.path.join(BASE_DIR, "_sync_status", "sync_status.json")
            now = int(time.time())

            if not os.path.exists(status_path):
                return {
                    "ok": True,
                    "state": "no_status",
                    "mode": "laptop_offline_coding",
                    "main_pc_state": "unknown",
                    "coordinator": COORDINATOR_URL or "",
                    "files_ready": 0,
                    "skipped_files": [],
                    "updated_at": 0,
                    "age_seconds": None,
                    "last_success_at": None,
                    "message": "No sync status exists yet. Start RUN_LAPTOP_CODING_MODE.bat or RUN_LAPTOP_SYNC_VISIBLE.bat.",
                    "last_error": ""
                }

            with open(status_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                data = {}

            updated_at = int(data.get("updated_at") or 0)
            last_success_at = data.get("last_success_at")
            try:
                last_success_at = int(last_success_at) if last_success_at else None
            except Exception:
                last_success_at = None

            age_seconds = None
            if updated_at > 0:
                age_seconds = max(0, now - updated_at)

            state = str(data.get("state") or "unknown")
            if state in ("synced", "synced_restart_requested", "synced_restart_failed"):
                main_pc_state = "online"
            elif state == "offline_waiting":
                main_pc_state = "offline"
            elif state == "preparing":
                main_pc_state = "checking"
            else:
                main_pc_state = "unknown"

            skipped_files = data.get("skipped_files") or []
            if not isinstance(skipped_files, list):
                skipped_files = []

            return {
                "ok": True,
                "state": state,
                "mode": data.get("mode") or "laptop_offline_coding",
                "main_pc_state": main_pc_state,
                "coordinator": data.get("coordinator") or COORDINATOR_URL or "",
                "files_ready": int(data.get("files_ready") or 0),
                "skipped_files": skipped_files,
                "skipped_count": len(skipped_files),
                "updated_at": updated_at,
                "age_seconds": age_seconds,
                "last_success_at": last_success_at,
                "changed_count": int(data.get("changed_count") or 0),
                "message": data.get("message") or "",
                "last_error": data.get("last_error") or ""
            }

        except Exception as e:
            return {
                "ok": False,
                "state": "error",
                "mode": "laptop_offline_coding",
                "main_pc_state": "unknown",
                "coordinator": COORDINATOR_URL or "",
                "files_ready": 0,
                "skipped_files": [],
                "updated_at": 0,
                "age_seconds": None,
                "last_success_at": None,
                "message": "Could not read local laptop sync status.",
                "last_error": str(e)
            }


    def get_system_metrics(self):
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory()
        
        net_type, dl, ul = self.get_network_speed()
        gpu_load = self.get_gpu_load()

        # 1. Pull EVERY profile from the database
        all_profiles = self.db.get_all_profiles()
        total_db_count = len(all_profiles)
        
        # 2. Calculate In-Use based on REAL status
        active_count = sum(1 for p in all_profiles if p['status'].upper() == 'RUNNING')
        available_count = total_db_count - active_count

        # 3. Dynamic Safe Limit Calculation
        # Uses real CPU thread count + available RAM instead of fake percentage-only cap.

        cpu_threads = psutil.cpu_count(logical=True) or 1
        total_ram_gb = ram.total / (1024**3)
        available_ram_gb = ram.available / (1024**3)

        # Keep Windows and background apps protected.
        reserved_ram_gb = max(4.0, total_ram_gb * 0.15)
        usable_ram_gb = max(0, available_ram_gb - reserved_ram_gb)

        # Estimated resource cost per Comet profile.
        # Adjust these after real testing.
        ram_per_profile_gb = 0.65
        profiles_per_cpu_thread = 3

        profiles_by_cpu = int(cpu_threads * profiles_per_cpu_thread * max(0.25, (100 - cpu) / 100))
        profiles_by_ram = int(usable_ram_gb / ram_per_profile_gb)

        safe_limit = max(1, min(profiles_by_cpu, profiles_by_ram))

        # Refresh global counts once more before returning metrics.
        all_profiles = self._get_coordinator_profiles()
        if all_profiles is None:
            all_profiles = self.db.get_all_profiles()

        total_db_count = len(all_profiles)
        active_count = sum(1 for p in all_profiles if str(p.get('status', '')).upper() == 'RUNNING')
        available_count = total_db_count - active_count
        
        return {
            "cpu": cpu,
            "ram_percent": ram.percent,
            "ram_used_gb": round(ram.used / (1024**3), 1),
            "gpu": gpu_load,
            "gpu_name": self.gpu_name,
            "safe_limit": safe_limit, 
            "active_profiles": active_count, # This will show 0 now
            "total_profiles": total_db_count, # This will show 12 now
            "available_profiles": available_count, # This will show 12 now
            "net_type": net_type,
            "dl_speed": dl,
            "ul_speed": ul
        }

def resource_monitor_thread(api):
    time.sleep(2) 
    while True:
        if api.window:
            try:
                # 1. Hardware Metrics
                m = api.get_system_metrics()
                
                # 2. Profiles Data
                p_list = api.get_profile_data()
                
                # Update the command to include the new available profiles count
                js_cmd = f"updateSystemMetrics({m['cpu']}, {m['ram_percent']}, {m['ram_used_gb']}, {m['gpu']}, `{m['gpu_name']}`, {m['safe_limit']}, {m['active_profiles']}, {m['available_profiles']}, `{m['net_type']}`, {m['dl_speed']}, {m['ul_speed']});"
                
                # Convert the Python list to a JS string safely
                import json
                js_p_list = json.dumps(p_list)

                # Render the table using app.js only.
                # Do not inject forced IP styling from Python.
                js_cmd += f"renderProfileTable({js_p_list});"
                
                api.window.evaluate_js(js_cmd)
            except Exception as e:
                print(f"Monitor Error: {e}")
        time.sleep(1)


def coordinator_heartbeat_thread(api):
    """
    Keeps coordinator profile locks alive.
    Safe fallback: if this start_dashboard.py version does not yet have
    send_coordinator_heartbeats(), this thread will not crash the app.
    """
    time.sleep(5)

    while True:
        try:
            if hasattr(api, "check_worker_block_status"):
                api.check_worker_block_status()
            if hasattr(api, "send_coordinator_heartbeats"):
                api.send_coordinator_heartbeats()
        except Exception as e:
            print(f"Coordinator Heartbeat Error: {e}")

        time.sleep(25)


if __name__ == '__main__':
    api = BackendAPI()

    current_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(current_dir, 'ui', 'index.html')

    window = webview.create_window(
        'Ghost HQ - Comet Fleet Commander', 
        url=html_path,
        js_api=api,
        width=1280, 
        height=800,
        background_color='#121212',
        resizable=True
    )
    api.set_window(window)

    threading.Thread(target=resource_monitor_thread, args=(api,), daemon=True).start()
    threading.Thread(target=coordinator_heartbeat_thread, args=(api,), daemon=True).start()

    print("[System] Booting User Interface...")
    webview.start()
