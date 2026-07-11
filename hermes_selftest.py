"""
hermes_selftest.py — PROOF that Hermes actually heals, not just logs.

This deliberately BREAKS each thing Hermes is supposed to fix, runs Hermes,
and then verifies the breakage is gone. If any heal fails, the script exits
non-zero and tells you which one. Run it any time you want to trust the system:

    python hermes_selftest.py

It works on any OS (pure standard library) and does NOT touch your real
local_config.json or fleet.db — it runs against throwaway copies in a temp
sandbox, so it is safe to run on your live machine.
"""

import json
import os
import sqlite3
import sys
import tempfile
import importlib

import engine.hermes as hermes_mod
from engine.hermes import Hermes


PASS = "PASS"
FAIL = "FAIL"


def _point_hermes_at(sandbox):
    """Redirect Hermes' module-level paths into a throwaway sandbox."""
    hermes_mod.BASE_DIR = sandbox
    hermes_mod.LOG_DIR = os.path.join(sandbox, "logs")
    hermes_mod.LOCAL_CONFIG_PATH = os.path.join(sandbox, "local_config.json")
    hermes_mod.DB_FOLDER = os.path.join(sandbox, "database")
    hermes_mod.DB_PATH = os.path.join(sandbox, "database", "fleet.db")
    hermes_mod.HERMES_LOG_PATH = os.path.join(sandbox, "logs", "hermes_log.txt")
    hermes_mod.HERMES_STATUS_PATH = os.path.join(sandbox, "hermes_status.json")
    hermes_mod.LAST_CRASH_PATH = os.path.join(sandbox, "logs", "hermes_last_crash.json")
    hermes_mod.QUARANTINE_DIR = os.path.join(sandbox, "quarantine")
    os.makedirs(hermes_mod.LOG_DIR, exist_ok=True)
    os.makedirs(hermes_mod.DB_FOLDER, exist_ok=True)


def _make_valid_db(path):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE profiles (id INTEGER PRIMARY KEY, name TEXT, "
        "status TEXT, target_platform TEXT)"
    )
    conn.executemany(
        "INSERT INTO profiles (name, status, target_platform) VALUES (?,?,?)",
        [("Profile 1", "RUNNING", "youtube"),
         ("Profile 2", "RUNNING", "twitch"),
         ("Profile 3", "OFFLINE", "None")],
    )
    conn.commit()
    conn.close()


def scenario_corrupt_config():
    """Write garbage into local_config.json; Hermes must restore valid JSON."""
    with open(hermes_mod.LOCAL_CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write('{ "COMET_PATH": "x",,, this is not valid json ]]')

    Hermes(verbose=False).preflight(allow_install=False, recover_crash=False)

    try:
        with open(hermes_mod.LOCAL_CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
        ok = isinstance(cfg, dict) and "COMET_PATH" in cfg
        return (PASS if ok else FAIL,
                "local_config.json parses as valid JSON with expected keys")
    except Exception as e:
        return FAIL, f"config still unparseable: {e}"


def scenario_missing_config():
    """Delete local_config.json; Hermes must recreate it."""
    if os.path.exists(hermes_mod.LOCAL_CONFIG_PATH):
        os.remove(hermes_mod.LOCAL_CONFIG_PATH)

    Hermes(verbose=False).preflight(allow_install=False, recover_crash=False)

    exists = os.path.exists(hermes_mod.LOCAL_CONFIG_PATH)
    return (PASS if exists else FAIL, "local_config.json recreated from defaults")


def scenario_corrupt_database():
    """Corrupt fleet.db; Hermes must quarantine it so the app can rebuild."""
    with open(hermes_mod.DB_PATH, "wb") as f:
        f.write(b"SQLite format 3\x00" + b"\xDE\xAD\xBE\xEF" * 64)  # junk

    Hermes(verbose=False).preflight(allow_install=False, recover_crash=False)

    # After healing, the corrupt file must be gone from its live location...
    still_corrupt = False
    if os.path.exists(hermes_mod.DB_PATH):
        try:
            conn = sqlite3.connect(hermes_mod.DB_PATH)
            conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
        except sqlite3.DatabaseError:
            still_corrupt = True
    # ...and a quarantined copy should exist for inspection.
    quarantined = os.path.isdir(hermes_mod.QUARANTINE_DIR) and any(
        "fleet.db" in n for n in os.listdir(hermes_mod.QUARANTINE_DIR)
    )
    ok = (not still_corrupt) and quarantined
    return (PASS if ok else FAIL,
            "corrupt fleet.db quarantined; live path is clean for rebuild")


def scenario_stuck_running():
    """Leave profiles RUNNING (crash leftover); Hermes must reset them."""
    _make_valid_db(hermes_mod.DB_PATH)

    Hermes(verbose=False).preflight(allow_install=False, recover_crash=False)

    conn = sqlite3.connect(hermes_mod.DB_PATH)
    running = conn.execute(
        "SELECT COUNT(*) FROM profiles WHERE UPPER(status)='RUNNING'"
    ).fetchone()[0]
    conn.close()
    return (PASS if running == 0 else FAIL,
            f"{running} profiles left RUNNING after heal (want 0)")


def scenario_crash_recovery():
    """
    Simulate a crash record from a previous run and verify heal_last_crash()
    routes to the right healer and marks the crash healed.
    """
    # Break the config, then plant a crash record pointing at it.
    with open(hermes_mod.LOCAL_CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write("}{ broken")
    with open(hermes_mod.LAST_CRASH_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "at": "test",
            "exit_code": 1,
            "signature": "corrupt_config",
            "output_tail": "json.decoder.JSONDecodeError: Expecting value",
            "healed": False,
        }, f)

    Hermes(verbose=False).preflight(allow_install=False, recover_crash=True)

    # Config must be valid again AND the crash record marked healed.
    config_ok = False
    try:
        with open(hermes_mod.LOCAL_CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            config_ok = isinstance(json.load(f), dict)
    except Exception:
        config_ok = False
    with open(hermes_mod.LAST_CRASH_PATH, "r", encoding="utf-8") as f:
        healed = json.load(f).get("healed") is True

    ok = config_ok and healed
    return (PASS if ok else FAIL,
            "crash record healed and config restored on next boot")


SCENARIOS = [
    ("Corrupt config JSON",        scenario_corrupt_config),
    ("Missing config file",        scenario_missing_config),
    ("Corrupt fleet.db",           scenario_corrupt_database),
    ("Profiles stuck RUNNING",     scenario_stuck_running),
    ("Crash auto-recovery",        scenario_crash_recovery),
]


def main():
    results = []
    for name, fn in SCENARIOS:
        # Fresh sandbox per scenario so tests never contaminate each other.
        with tempfile.TemporaryDirectory(prefix="hermes_test_") as sandbox:
            _point_hermes_at(sandbox)
            try:
                status, detail = fn()
            except Exception as e:
                status, detail = FAIL, f"scenario raised: {e!r}"
            results.append((name, status, detail))

    print("\n" + "=" * 62)
    print(" HERMES SELF-TEST — deliberately break, then verify the heal")
    print("=" * 62)
    for name, status, detail in results:
        mark = "OK  " if status == PASS else "XX  "
        print(f" [{mark}] {name:<26} {status}")
        print(f"        -> {detail}")
    print("=" * 62)

    failed = [r for r in results if r[1] == FAIL]
    if failed:
        print(f" RESULT: {len(failed)}/{len(results)} scenario(s) FAILED\n")
        return 1
    print(f" RESULT: all {len(results)} heals verified working\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
