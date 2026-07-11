"""
Hermes — Comet Fleet self-healing startup engine.

Hermes runs BEFORE and AROUND the main dashboard. Its job is simple and concrete:

  1. ANALYZE the things that actually break Comet Fleet at startup.
  2. RECORD every problem it finds (human-readable log + machine-readable status).
  3. HEAL the problem automatically, so the next launch just works.

Design rules that keep this honest (not "more code for the sake of it"):

  * Hermes only depends on the Python standard library. If pywebview / psutil /
    selenium are broken, Hermes must still be able to run and repair them.
  * Every healer is IDEMPOTENT: running it when nothing is wrong does nothing.
  * Every healer targets a REAL failure mode in this codebase, verified against
    start_dashboard.py and engine/db_manager.py.
  * Nothing is destroyed silently. Corrupt files are quarantined (renamed with a
    timestamp), never deleted, so you can always inspect what happened.

The visible outputs Hermes writes (so you can SEE it working):

  * logs/hermes_log.txt        — running history, newest actions appended.
  * hermes_status.json         — last run summary the dashboard/UI can read.
  * logs/hermes_last_crash.json — captured crash, used to heal on next launch.
"""

import json
import os
import shutil
import sqlite3
import sys
import time
import importlib.util
import subprocess
from datetime import datetime


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")

LOCAL_CONFIG_PATH = os.path.join(BASE_DIR, "local_config.json")
DB_FOLDER = os.path.join(BASE_DIR, "database")
DB_PATH = os.path.join(DB_FOLDER, "fleet.db")

HERMES_LOG_PATH = os.path.join(LOG_DIR, "hermes_log.txt")
HERMES_STATUS_PATH = os.path.join(BASE_DIR, "hermes_status.json")
LAST_CRASH_PATH = os.path.join(LOG_DIR, "hermes_last_crash.json")
QUARANTINE_DIR = os.path.join(BASE_DIR, "quarantine")


# The keys start_dashboard.py reads out of local_config.json. If any are missing
# the dashboard falls back to a default, but a MISSING FILE or CORRUPT JSON makes
# json.load() raise and the whole app dies on boot. Hermes guarantees a valid file.
DEFAULT_LOCAL_CONFIG = {
    "COMET_PATH": r"C:\Users\newave\AppData\Local\Perplexity\Comet\Application\comet.exe",
    "CHROMEDRIVER_PATH": r"C:\Users\newave\.cache\selenium\chromedriver\win64\140.0.7339.207\chromedriver.exe",
    "PROTON_VPN_PATH": os.path.join(
        BASE_DIR, "extension_template", "Extensions",
        "jplgfhpmjnbigmhklmmbgecoobifkmpa", "1.2.16_0",
    ),
    "HOME_IP": "190.110.36.47",
    "PC_ID": "",
    "DEVICE_TYPE": "",
    "COORDINATOR_URL": "",
}

# import-name -> pip package name. These are the third-party imports start_dashboard.py
# and the engine actually use. A missing one is an ImportError crash at boot.
REQUIRED_DEPENDENCIES = {
    "webview": "pywebview",
    "psutil": "psutil",
    "requests": "requests",
    "selenium": "selenium",
    "selenium_stealth": "selenium-stealth",
}


def _timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _file_stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# --------------------------------------------------------------------------- #
# Hermes
# --------------------------------------------------------------------------- #

class Hermes:
    """The self-healing brain of the Comet Fleet bot."""

    def __init__(self, verbose=True):
        self.verbose = verbose
        os.makedirs(LOG_DIR, exist_ok=True)
        # Findings/actions accumulate here and get written to hermes_status.json.
        self.findings = []   # problems detected this run
        self.actions = []    # heals performed this run
        self.started_at = _timestamp()

    # ---- logging / recording ------------------------------------------- #

    def log(self, message, level="INFO"):
        line = f"[{_timestamp()}] [Hermes] [{level}] {message}"
        if self.verbose:
            try:
                print(line)
            except Exception:
                # Never let a console encoding issue take Hermes down.
                pass
        try:
            with open(HERMES_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def _record_finding(self, check, detail):
        self.findings.append({"check": check, "detail": detail, "at": _timestamp()})
        self.log(f"PROBLEM in '{check}': {detail}", level="WARN")

    def _record_action(self, check, action):
        self.actions.append({"check": check, "action": action, "at": _timestamp()})
        self.log(f"HEALED '{check}': {action}", level="HEAL")

    def _quarantine(self, path, reason):
        """Move a broken file out of the way instead of deleting it."""
        if not os.path.exists(path):
            return None
        os.makedirs(QUARANTINE_DIR, exist_ok=True)
        dest = os.path.join(
            QUARANTINE_DIR,
            f"{os.path.basename(path)}.{_file_stamp()}.broken",
        )
        try:
            shutil.move(path, dest)
            self.log(f"Quarantined {os.path.basename(path)} -> {dest} ({reason})")
            return dest
        except Exception as e:
            self.log(f"Could not quarantine {path}: {e}", level="ERROR")
            return None

    def _backup(self, path):
        """Keep a last-known-good copy of a healthy file."""
        if not os.path.exists(path):
            return
        try:
            shutil.copy2(path, path + ".hermes.bak")
        except Exception:
            pass

    # ---- individual checks (each returns True if healthy AFTER healing) - #

    def check_filesystem(self):
        """The dashboard writes into database/ and we log into logs/."""
        healthy = True
        for folder in (DB_FOLDER, LOG_DIR):
            if not os.path.isdir(folder):
                self._record_finding("filesystem", f"Missing folder: {folder}")
                try:
                    os.makedirs(folder, exist_ok=True)
                    self._record_action("filesystem", f"Created folder: {folder}")
                except Exception as e:
                    self.log(f"Failed to create {folder}: {e}", level="ERROR")
                    healthy = False
        return healthy

    def check_local_config(self):
        """
        start_dashboard.py does json.load(local_config.json) with NO try/except.
        A missing file, a BOM, a trailing comma, or a truncated write == instant
        crash on boot. Heal strategy:
          - missing file            -> write defaults
          - unparseable JSON        -> quarantine, restore .bak if valid, else defaults
          - valid but missing keys  -> merge defaults in (backup first)
        """
        if not os.path.exists(LOCAL_CONFIG_PATH):
            self._record_finding("local_config", "local_config.json is missing")
            self._write_config(DEFAULT_LOCAL_CONFIG)
            self._record_action("local_config", "Recreated local_config.json from defaults")
            return True

        raw = None
        try:
            with open(LOCAL_CONFIG_PATH, "r", encoding="utf-8-sig") as f:
                raw = f.read()
            config = json.loads(raw)
            if not isinstance(config, dict):
                raise ValueError("top-level JSON is not an object")
        except Exception as e:
            self._record_finding("local_config", f"local_config.json is corrupt: {e}")
            self._quarantine(LOCAL_CONFIG_PATH, "corrupt JSON")
            restored = self._restore_config_from_backup()
            if restored:
                self._record_action("local_config", "Restored local_config.json from last-known-good backup")
            else:
                self._write_config(DEFAULT_LOCAL_CONFIG)
                self._record_action("local_config", "Rebuilt local_config.json from defaults")
            return True

        # Valid JSON — make sure every key the dashboard reads exists.
        missing = [k for k in DEFAULT_LOCAL_CONFIG if k not in config]
        if missing:
            self._record_finding("local_config", f"local_config.json missing keys: {missing}")
            self._backup(LOCAL_CONFIG_PATH)
            merged = DEFAULT_LOCAL_CONFIG.copy()
            merged.update(config)
            self._write_config(merged)
            self._record_action("local_config", f"Merged missing keys: {missing}")
        else:
            # Healthy — snapshot it so we can restore it if it breaks later.
            self._backup(LOCAL_CONFIG_PATH)
        return True

    def _write_config(self, config):
        with open(LOCAL_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)

    def _restore_config_from_backup(self):
        bak = LOCAL_CONFIG_PATH + ".hermes.bak"
        if not os.path.exists(bak):
            return False
        try:
            with open(bak, "r", encoding="utf-8-sig") as f:
                config = json.load(f)
            if not isinstance(config, dict):
                return False
            self._write_config(config)
            return True
        except Exception:
            return False

    def check_database(self):
        """
        The dashboard opens database/fleet.db immediately. A power-loss / hard
        crash mid-write leaves either:
          - a malformed image ("database disk image is malformed"), or
          - a stale rollback journal / WAL file that jams the next open.
        Heal strategy:
          - integrity_check fails  -> quarantine db (+journal/-wal); tables get
                                      rebuilt automatically by DatabaseManager.
          - integrity ok           -> checkpoint & clear any stale WAL safely.
        """
        if not os.path.exists(DB_PATH):
            # Nothing to heal; DatabaseManager will create it fresh. Fine.
            return True

        corrupt = False
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            try:
                cur = conn.cursor()
                cur.execute("PRAGMA integrity_check")
                row = cur.fetchone()
                if not row or str(row[0]).lower() != "ok":
                    corrupt = True
                else:
                    # Healthy: fold any stale WAL back into the main file so a
                    # leftover -wal from a crash can't jam the dashboard's open.
                    try:
                        cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    except Exception:
                        pass
            finally:
                conn.close()
        except sqlite3.DatabaseError as e:
            # Can't even open it — treat as corrupt.
            corrupt = True
            self._record_finding("database", f"fleet.db unreadable: {e}")

        if corrupt:
            self._record_finding("database", "fleet.db failed integrity_check (corrupt)")
            self._quarantine(DB_PATH, "corrupt sqlite image")
            # Remove the paired journal/WAL so the fresh db starts clean.
            for suffix in ("-journal", "-wal", "-shm"):
                self._quarantine(DB_PATH + suffix, "orphaned sqlite sidecar")
            self._record_action(
                "database",
                "Quarantined corrupt fleet.db; DatabaseManager will rebuild empty tables",
            )
        return True

    def check_stuck_statuses(self):
        """
        This is the classic 'it crashed while running' case. Profiles left in
        RUNNING never get cleared, so the fleet looks busy and won't relaunch.
        start_dashboard.py calls reset_all_statuses() on boot, but only AFTER a
        successful DatabaseManager() init — if boot dies earlier, the statuses
        stay stuck. Hermes clears them pre-emptively so a reopen is always clean.
        """
        if not os.path.exists(DB_PATH):
            return True
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            try:
                cur = conn.cursor()
                # Table may not exist yet on a brand-new db; guard it.
                cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='profiles'"
                )
                if cur.fetchone() is None:
                    return True
                cur.execute("SELECT COUNT(*) FROM profiles WHERE UPPER(status)='RUNNING'")
                stuck = cur.fetchone()[0]
                if stuck:
                    self._record_finding(
                        "stuck_statuses",
                        f"{stuck} profile(s) stuck in RUNNING from a previous crash",
                    )
                    cur.execute(
                        "UPDATE profiles SET status='OFFLINE', target_platform='None' "
                        "WHERE UPPER(status)='RUNNING'"
                    )
                    # Lifecycle table may not exist on older schemas.
                    try:
                        cur.execute("DELETE FROM profile_lifecycle_state")
                    except sqlite3.OperationalError:
                        pass
                    conn.commit()
                    self._record_action(
                        "stuck_statuses",
                        f"Reset {stuck} stuck profile(s) to OFFLINE",
                    )
            finally:
                conn.close()
        except sqlite3.DatabaseError as e:
            # Corruption is handled by check_database(); don't double-report.
            self.log(f"stuck_statuses skipped (db error): {e}", level="INFO")
        return True

    def check_dependencies(self, allow_install=True):
        """
        A missing third-party import is an instant boot crash. Detect any that
        aren't importable and pip-install them. This is the one healer that
        needs the network; if install is disabled or offline, it records the
        problem so the log tells you exactly what to `pip install`.
        """
        missing = []
        for module, package in REQUIRED_DEPENDENCIES.items():
            if importlib.util.find_spec(module) is None:
                missing.append((module, package))

        if not missing:
            return True

        for module, package in missing:
            self._record_finding("dependencies", f"Python module '{module}' not installed")

        if not allow_install:
            self.log("Dependency auto-install disabled; skipping pip.", level="WARN")
            return False

        healed_all = True
        for module, package in missing:
            self.log(f"Installing missing dependency: {package}")
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install",
                     "--disable-pip-version-check", package],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT,
                    timeout=600,
                )
                # Reset the import caches so find_spec sees the new package.
                importlib.invalidate_caches()
                if importlib.util.find_spec(module) is not None:
                    self._record_action("dependencies", f"Installed {package}")
                else:
                    healed_all = False
                    self.log(f"pip finished but '{module}' still not importable", level="ERROR")
            except Exception as e:
                healed_all = False
                self.log(f"Failed to install {package}: {e}", level="ERROR")
        return healed_all

    # ---- crash capture & recovery -------------------------------------- #

    def record_crash(self, exit_code, output_tail):
        """
        Called by the supervisor when the dashboard process dies unexpectedly.
        Persists what happened so the NEXT launch can heal it automatically.
        """
        crash = {
            "at": _timestamp(),
            "exit_code": exit_code,
            "signature": self._classify(output_tail),
            "output_tail": output_tail[-8000:] if output_tail else "",
            "healed": False,
        }
        try:
            with open(LAST_CRASH_PATH, "w", encoding="utf-8") as f:
                json.dump(crash, f, indent=4)
        except Exception as e:
            self.log(f"Could not write crash record: {e}", level="ERROR")
        self.log(
            f"CRASH captured (exit={exit_code}, signature={crash['signature']})",
            level="ERROR",
        )
        return crash

    def _classify(self, text):
        """Map a crash's output to a known, healable signature."""
        t = (text or "").lower()
        if "json" in t and ("decode" in t or "expecting" in t or "extra data" in t):
            return "corrupt_config"
        if "database disk image is malformed" in t or "file is not a database" in t:
            return "corrupt_database"
        if "database is locked" in t:
            return "database_locked"
        if "modulenotfounderror" in t or "no module named" in t:
            return "missing_dependency"
        if "no such file or directory" in t and "config" in t:
            return "missing_config"
        return "unknown"

    def heal_last_crash(self):
        """
        Read the crash record left by the previous run and apply the targeted
        heal for its signature. Returns the signature handled (or None).
        """
        if not os.path.exists(LAST_CRASH_PATH):
            return None
        try:
            with open(LAST_CRASH_PATH, "r", encoding="utf-8") as f:
                crash = json.load(f)
        except Exception:
            return None
        if crash.get("healed"):
            return None

        sig = crash.get("signature", "unknown")
        self.log(f"Recovering from previous crash (signature={sig})")

        # Each signature routes to the healer that fixes that class of failure.
        # These healers are the same idempotent ones used in preflight, so the
        # targeted call is safe even if preflight already ran.
        if sig in ("corrupt_config", "missing_config"):
            self.check_local_config()
        elif sig in ("corrupt_database", "database_locked"):
            self.check_database()
            self.check_stuck_statuses()
        elif sig == "missing_dependency":
            self.check_dependencies()
        else:
            # Unknown: run the full battery — cheap and idempotent.
            self.check_filesystem()
            self.check_local_config()
            self.check_database()
            self.check_stuck_statuses()

        crash["healed"] = True
        crash["healed_at"] = _timestamp()
        try:
            with open(LAST_CRASH_PATH, "w", encoding="utf-8") as f:
                json.dump(crash, f, indent=4)
        except Exception:
            pass
        self._record_action("crash_recovery", f"Applied recovery for signature '{sig}'")
        return sig

    # ---- orchestration -------------------------------------------------- #

    def preflight(self, allow_install=True, recover_crash=True):
        """
        Run the whole self-heal battery before the dashboard launches.
        Returns a status dict (also written to hermes_status.json).
        """
        self.findings = []
        self.actions = []
        self.started_at = _timestamp()
        self.log("=== Hermes preflight starting ===")

        # 0. If we crashed last time, heal that specific failure first.
        recovered_signature = None
        if recover_crash:
            recovered_signature = self.heal_last_crash()

        # 1..N: the standing checks. Order matters: filesystem, then config,
        # then database, then stuck state, then deps.
        self.check_filesystem()
        self.check_local_config()
        self.check_database()
        self.check_stuck_statuses()
        self.check_dependencies(allow_install=allow_install)

        healthy = len(self.findings) == 0
        status = {
            "started_at": self.started_at,
            "finished_at": _timestamp(),
            "healthy_on_entry": healthy,
            "recovered_crash_signature": recovered_signature,
            "problems_found": len(self.findings),
            "heals_applied": len(self.actions),
            "findings": self.findings,
            "actions": self.actions,
        }
        self._write_status(status)

        if healthy and not self.actions:
            self.log("=== Hermes preflight PASSED (nothing to heal) ===")
        else:
            self.log(
                f"=== Hermes preflight COMPLETE — "
                f"{len(self.findings)} problem(s), {len(self.actions)} heal(s) applied ==="
            )
        return status

    def _write_status(self, status):
        try:
            with open(HERMES_STATUS_PATH, "w", encoding="utf-8") as f:
                json.dump(status, f, indent=4)
        except Exception as e:
            self.log(f"Could not write hermes_status.json: {e}", level="ERROR")


def read_status():
    """Convenience for the dashboard/UI to display the last Hermes run."""
    try:
        with open(HERMES_STATUS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


if __name__ == "__main__":
    # Running the engine directly performs a one-shot self-heal pass.
    Hermes().preflight()
