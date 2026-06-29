import base64
import hashlib
import json
import os
import sqlite3
import sys
import threading
import time
import uuid
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "coordinator_state.db")

LEASE_SECONDS = 120
WORKER_ONLINE_SECONDS = 90

app = Flask(__name__)
CORS(app)


def now_ts():
    return int(time.time())


def extract_ip_only(value):
    import re
    raw = str(value or "").strip()
    match = re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", raw)
    return match.group(0) if match else ""


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def column_exists(conn, table_name, column_name):
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row[1] == column_name for row in rows)


def add_column_if_missing(conn, table_name, column_name, column_sql):
    if not column_exists(conn, table_name, column_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")
        print(f"[Coordinator DB] Added missing column: {table_name}.{column_name}")


def init_db():
    conn = get_db()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                hardware_cloak TEXT DEFAULT 'Pending Execution',
                hardware_profile_json TEXT DEFAULT '',
                status TEXT DEFAULT 'OFFLINE',
                current_target TEXT DEFAULT 'None',
                ip_origin TEXT DEFAULT 'Unknown',
                locked_by TEXT,
                locked_at INTEGER,
                lease_until INTEGER,
                last_heartbeat INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                pc_id TEXT PRIMARY KEY,
                hostname TEXT,
                ip_address TEXT,
                last_seen INTEGER,
                status TEXT DEFAULT 'ONLINE',
                blocked INTEGER DEFAULT 0,
                blocked_at INTEGER,
                blocked_reason TEXT DEFAULT ''
            )
        """)

        # Repair older coordinator databases.
        add_column_if_missing(conn, "workers", "blocked", "INTEGER DEFAULT 0")
        add_column_if_missing(conn, "workers", "blocked_at", "INTEGER")
        add_column_if_missing(conn, "workers", "blocked_reason", "TEXT DEFAULT ''")
        add_column_if_missing(conn, "profiles", "hardware_profile_json", "TEXT DEFAULT ''")

        # Device / mobile worker support.
        add_column_if_missing(conn, "workers", "device_type", "TEXT DEFAULT 'Unknown'")
        add_column_if_missing(conn, "workers", "device_role", "TEXT DEFAULT ''")
        add_column_if_missing(conn, "workers", "battery_percent", "INTEGER")
        add_column_if_missing(conn, "workers", "charging", "INTEGER DEFAULT 0")
        add_column_if_missing(conn, "workers", "network_type", "TEXT DEFAULT ''")
        add_column_if_missing(conn, "workers", "can_launch_profiles", "INTEGER DEFAULT 0")
        add_column_if_missing(conn, "workers", "can_run_mobile_tasks", "INTEGER DEFAULT 0")
        add_column_if_missing(conn, "workers", "can_control_fleet", "INTEGER DEFAULT 0")
        add_column_if_missing(conn, "workers", "can_be_blocked", "INTEGER DEFAULT 1")
        add_column_if_missing(conn, "workers", "worker_version", "TEXT DEFAULT ''")
        add_column_if_missing(conn, "workers", "device_note", "TEXT DEFAULT ''")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ip_blacklist (
                ip_address TEXT PRIMARY KEY,
                ip_label TEXT DEFAULT '',
                reason TEXT DEFAULT '',
                source_pc_id TEXT DEFAULT '',
                active INTEGER DEFAULT 1,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)

        # WORKER COMPATIBILITY ROUTES
        # These tables back the laptop/dashboard panels when the main PC is online.
        # They are intentionally local and simple so an older main PC can accept the
        # newer laptop UI without crashing on missing routes.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mobile_tasks (
                task_id TEXT PRIMARY KEY,
                pc_id TEXT NOT NULL,
                task_type TEXT NOT NULL,
                payload_json TEXT DEFAULT '{}',
                status TEXT DEFAULT 'pending',
                result_json TEXT DEFAULT '{}',
                error TEXT DEFAULT '',
                requested_by TEXT DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                completed_at INTEGER
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS device_commands (
                command_id TEXT PRIMARY KEY,
                target_pc_id TEXT NOT NULL,
                command_type TEXT NOT NULL,
                payload_json TEXT DEFAULT '{}',
                status TEXT DEFAULT 'queued',
                result_json TEXT DEFAULT '{}',
                error TEXT DEFAULT '',
                requested_by TEXT DEFAULT '',
                claimed_by TEXT DEFAULT '',
                claimed_at INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                completed_at INTEGER
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS security_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_ts INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                pc_id TEXT DEFAULT '',
                status TEXT DEFAULT 'INFO',
                severity TEXT DEFAULT 'info',
                details TEXT DEFAULT ''
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS coordinator_settings (
                key TEXT PRIMARY KEY,
                value TEXT DEFAULT '',
                updated_at INTEGER NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ml_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_ts INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                pc_id TEXT DEFAULT '',
                severity TEXT DEFAULT 'info',
                details TEXT DEFAULT ''
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ml_actions (
                action_id TEXT PRIMARY KEY,
                action_type TEXT NOT NULL,
                target_pc_id TEXT DEFAULT '',
                severity TEXT DEFAULT 'info',
                status TEXT DEFAULT 'pending',
                details TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                completed_at INTEGER
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ml_history (
                history_id TEXT PRIMARY KEY,
                event_ts INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT DEFAULT '{}'
            )
        """)
    finally:
        conn.close()


def row_to_dict(row):
    return dict(row) if row else None


def clean_limit(value, default=100, maximum=1000):
    try:
        limit = int(value or default)
    except Exception:
        limit = default
    return max(1, min(limit, maximum))


def json_pack(value):
    try:
        return json.dumps(value if value is not None else {}, separators=(",", ":"), sort_keys=True)
    except Exception:
        return "{}"


def json_unpack(value, fallback=None):
    fallback = {} if fallback is None else fallback
    try:
        if not value:
            return fallback
        data = json.loads(value)
        return data
    except Exception:
        return fallback


def request_pc_id(default=""):
    data = request.get_json(silent=True) or {}
    return (
        str(data.get("request_pc_id") or data.get("pc_id") or "").strip()
        or str(request.headers.get("X-PC-ID") or "").strip()
        or default
    )


def configured_sync_token():
    env_token = str(os.environ.get("COMET_SYNC_TOKEN") or "").strip()
    if env_token:
        return env_token

    cfg_path = os.path.join(BASE_DIR, "sync_client_config.json")
    try:
        with open(cfg_path, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
        token = str(cfg.get("SYNC_TOKEN") or "").strip()
        if token:
            return token
    except Exception:
        pass

    return "comet-sync-local"


def sync_authorized():
    data = request.get_json(silent=True) or {}
    supplied = (
        str(request.headers.get("X-Sync-Token") or "").strip()
        or str(data.get("token") or "").strip()
    )
    expected = configured_sync_token()
    return bool(supplied and supplied == expected)


def set_setting(conn, key, value):
    conn.execute("""
        INSERT INTO coordinator_settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
    """, (str(key), str(value), now_ts()))


def get_setting(conn, key, default=""):
    row = conn.execute(
        "SELECT value FROM coordinator_settings WHERE key = ?",
        (str(key),)
    ).fetchone()
    return str(row["value"]) if row else default


def record_security_event(conn, event_type, pc_id="", status="INFO", severity="info", details=""):
    conn.execute("""
        INSERT INTO security_events (event_ts, event_type, pc_id, status, severity, details)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        now_ts(),
        str(event_type or "EVENT"),
        str(pc_id or ""),
        str(status or "INFO"),
        str(severity or "info"),
        str(details or "")
    ))


def record_ml_event(conn, event_type, pc_id="", severity="info", details=""):
    conn.execute("""
        INSERT INTO ml_events (event_ts, event_type, pc_id, severity, details)
        VALUES (?, ?, ?, ?, ?)
    """, (
        now_ts(),
        str(event_type or "ML_EVENT"),
        str(pc_id or ""),
        str(severity or "info"),
        str(details or "")
    ))


def command_row_to_dict(row):
    item = row_to_dict(row) or {}
    item["payload"] = json_unpack(item.pop("payload_json", ""), {})
    item["result"] = json_unpack(item.pop("result_json", ""), {})
    return item


def task_row_to_dict(row):
    item = row_to_dict(row) or {}
    item["payload"] = json_unpack(item.pop("payload_json", ""), {})
    item["result"] = json_unpack(item.pop("result_json", ""), {})
    return item


def is_worker_blocked(conn, pc_id):
    if not pc_id:
        return False

    row = conn.execute(
        "SELECT blocked FROM workers WHERE pc_id = ?",
        (pc_id,)
    ).fetchone()

    return bool(row and int(row["blocked"] or 0) == 1)


def truthy(value):
    return str(value).strip().lower() in ["1", "true", "yes", "y", "on"]


def clean_int_or_none(value):
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except Exception:
        return None


def infer_device_type_from_payload(pc_id="", hostname="", payload=None):
    payload = payload or {}

    explicit = str(payload.get("device_type") or payload.get("DEVICE_TYPE") or "").strip()
    raw = f"{explicit} {pc_id} {hostname}".lower()

    if any(term in raw for term in ["phone", "android", "iphone", "ios", "mobile"]):
        return "Phone"

    if any(term in raw for term in ["tablet", "ipad"]):
        return "Tablet"

    if any(term in raw for term in ["laptop", "notebook", "legion"]):
        return "Laptop"

    if any(term in raw for term in ["desktop", "pc", "tower", "workstation"]):
        return "PC"

    return explicit or "Unknown"


def default_device_role(device_type):
    if device_type == "Phone":
        return "Worker Phone"
    if device_type == "Tablet":
        return "Worker Tablet"
    if device_type == "Laptop":
        return "Worker Laptop"
    if device_type == "PC":
        return "Worker PC"
    return "Monitor Only"


def build_worker_device_fields(pc_id="", hostname="", payload=None):
    payload = payload or {}

    device_type = infer_device_type_from_payload(pc_id=pc_id, hostname=hostname, payload=payload)
    device_role = str(payload.get("device_role") or payload.get("role") or "").strip() or default_device_role(device_type)

    is_computer = device_type in ["PC", "Laptop"]
    is_mobile = device_type in ["Phone", "Tablet"]

    can_launch_profiles = payload.get("can_launch_profiles")
    if can_launch_profiles is None:
        can_launch_profiles = 1 if is_computer else 0
    else:
        can_launch_profiles = 1 if truthy(can_launch_profiles) else 0

    can_run_mobile_tasks = payload.get("can_run_mobile_tasks")
    if can_run_mobile_tasks is None:
        can_run_mobile_tasks = 1 if is_mobile else 0
    else:
        can_run_mobile_tasks = 1 if truthy(can_run_mobile_tasks) else 0

    can_control_fleet = 1 if truthy(payload.get("can_control_fleet")) else 0
    can_be_blocked = 0 if device_role == "Controller" else 1

    return {
        "device_type": device_type,
        "device_role": device_role,
        "battery_percent": clean_int_or_none(payload.get("battery_percent")),
        "charging": 1 if truthy(payload.get("charging")) else 0,
        "network_type": str(payload.get("network_type") or "").strip(),
        "can_launch_profiles": can_launch_profiles,
        "can_run_mobile_tasks": can_run_mobile_tasks,
        "can_control_fleet": can_control_fleet,
        "can_be_blocked": can_be_blocked,
        "worker_version": str(payload.get("worker_version") or "").strip(),
        "device_note": str(payload.get("device_note") or "").strip()
    }


def touch_worker(conn, pc_id, hostname="", ip_address="", payload=None):
    if not pc_id:
        return None

    payload = payload or {}
    now = now_ts()

    existing = conn.execute(
        "SELECT blocked FROM workers WHERE pc_id = ?",
        (pc_id,)
    ).fetchone()

    if existing and int(existing["blocked"] or 0) == 1:
        status = "BLOCKED"
    else:
        status = "ONLINE"

    fields = build_worker_device_fields(
        pc_id=pc_id,
        hostname=hostname,
        payload=payload
    )

    conn.execute("""
        INSERT INTO workers (
            pc_id,
            hostname,
            ip_address,
            last_seen,
            status,
            blocked,
            device_type,
            device_role,
            battery_percent,
            charging,
            network_type,
            can_launch_profiles,
            can_run_mobile_tasks,
            can_control_fleet,
            can_be_blocked,
            worker_version,
            device_note
        )
        VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(pc_id) DO UPDATE SET
            hostname = excluded.hostname,
            ip_address = excluded.ip_address,
            last_seen = excluded.last_seen,
            status = CASE
                WHEN workers.blocked = 1 THEN 'BLOCKED'
                ELSE excluded.status
            END,
            device_type = COALESCE(NULLIF(excluded.device_type, ''), workers.device_type),
            device_role = COALESCE(NULLIF(excluded.device_role, ''), workers.device_role),
            battery_percent = excluded.battery_percent,
            charging = excluded.charging,
            network_type = excluded.network_type,
            can_launch_profiles = excluded.can_launch_profiles,
            can_run_mobile_tasks = excluded.can_run_mobile_tasks,
            can_control_fleet = excluded.can_control_fleet,
            can_be_blocked = excluded.can_be_blocked,
            worker_version = COALESCE(NULLIF(excluded.worker_version, ''), workers.worker_version),
            device_note = COALESCE(NULLIF(excluded.device_note, ''), workers.device_note)
    """, (
        pc_id,
        hostname,
        ip_address,
        now,
        status,
        fields["device_type"],
        fields["device_role"],
        fields["battery_percent"],
        fields["charging"],
        fields["network_type"],
        fields["can_launch_profiles"],
        fields["can_run_mobile_tasks"],
        fields["can_control_fleet"],
        fields["can_be_blocked"],
        fields["worker_version"],
        fields["device_note"]
    ))

    return conn.execute(
        "SELECT * FROM workers WHERE pc_id = ?",
        (pc_id,)
    ).fetchone()


def release_expired_locks(conn):
    now = now_ts()
    conn.execute("""
        UPDATE profiles
        SET
            status = 'OFFLINE',
            locked_by = NULL,
            locked_at = NULL,
            lease_until = NULL,
            last_heartbeat = NULL,
            current_target = 'None',
            updated_at = ?
        WHERE status = 'RUNNING'
          AND lease_until IS NOT NULL
          AND lease_until < ?
    """, (now, now))


def release_profiles_for_worker(conn, pc_id):
    now = now_ts()
    conn.execute("""
        UPDATE profiles
        SET
            status = 'OFFLINE',
            locked_by = NULL,
            locked_at = NULL,
            lease_until = NULL,
            last_heartbeat = NULL,
            current_target = 'None',
            updated_at = ?
        WHERE locked_by = ?
    """, (now, pc_id))


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "server": "Comet Fleet Coordinator",
        "time": now_ts()
    })


@app.route("/api/workers/register", methods=["POST"])
def register_worker():
    data = request.get_json(force=True) or {}

    pc_id = str(data.get("pc_id", "")).strip()
    hostname = str(data.get("hostname", "")).strip()
    ip_address = request.remote_addr

    if not pc_id:
        return jsonify({"ok": False, "error": "pc_id is required"}), 400

    conn = get_db()
    try:
        row = touch_worker(conn, pc_id, hostname, ip_address, data)
        worker = row_to_dict(row)
        blocked = bool(worker and int(worker.get("blocked") or 0) == 1)

        return jsonify({
            "ok": True,
            "pc_id": pc_id,
            "blocked": blocked,
            "blocked_reason": worker.get("blocked_reason", "") if worker else "",
            "worker": worker
        })
    finally:
        conn.close()


@app.route("/api/workers/heartbeat", methods=["POST"])
def heartbeat_worker():
    data = request.get_json(force=True) or {}

    pc_id = str(data.get("pc_id", "")).strip()
    hostname = str(data.get("hostname", "")).strip()
    ip_address = request.remote_addr

    if not pc_id:
        return jsonify({"ok": False, "error": "pc_id is required"}), 400

    conn = get_db()
    try:
        row = touch_worker(conn, pc_id, hostname, ip_address, data)
        worker = row_to_dict(row)
        blocked = bool(worker and int(worker.get("blocked") or 0) == 1)

        if blocked:
            release_profiles_for_worker(conn, pc_id)

        return jsonify({
            "ok": True,
            "pc_id": pc_id,
            "blocked": blocked,
            "blocked_reason": worker.get("blocked_reason", "") if worker else "",
            "worker": worker
        })
    finally:
        conn.close()


@app.route("/api/workers", methods=["GET"])
def list_workers():
    now = now_ts()
    conn = get_db()
    try:
        release_expired_locks(conn)

        rows = conn.execute("""
            SELECT
                w.*,
                COUNT(p.id) AS active_profiles
            FROM workers w
            LEFT JOIN profiles p
                ON p.locked_by = w.pc_id
               AND p.status = 'RUNNING'
               AND p.lease_until IS NOT NULL
               AND p.lease_until >= ?
            GROUP BY w.pc_id
            ORDER BY w.last_seen DESC, w.pc_id ASC
        """, (now,)).fetchall()

        workers = []
        for row in rows:
            item = row_to_dict(row)
            last_seen = int(item.get("last_seen") or 0)
            blocked = bool(int(item.get("blocked") or 0) == 1)

            if blocked:
                display_status = "BLOCKED"
            elif last_seen and now - last_seen <= WORKER_ONLINE_SECONDS:
                display_status = "ONLINE"
            else:
                display_status = "OFFLINE"

            item["blocked"] = blocked
            item["display_status"] = display_status
            item["seconds_since_seen"] = (now - last_seen) if last_seen else None
            workers.append(item)

        return jsonify({
            "ok": True,
            "workers": workers,
            "time": now
        })
    finally:
        conn.close()


@app.route("/api/workers/<pc_id>/block", methods=["POST"])
def block_worker(pc_id):
    data = request.get_json(force=True) or {}
    reason = str(data.get("reason", "Blocked from PC Control tab")).strip()
    hostname = str(data.get("hostname", "")).strip()
    now = now_ts()

    pc_id = str(pc_id).strip()
    if not pc_id:
        return jsonify({"ok": False, "error": "pc_id is required"}), 400

    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO workers (pc_id, hostname, ip_address, last_seen, status, blocked, blocked_at, blocked_reason)
            VALUES (?, ?, '', ?, 'BLOCKED', 1, ?, ?)
            ON CONFLICT(pc_id) DO UPDATE SET
                blocked = 1,
                blocked_at = excluded.blocked_at,
                blocked_reason = excluded.blocked_reason,
                status = 'BLOCKED',
                hostname = COALESCE(NULLIF(excluded.hostname, ''), workers.hostname),
                last_seen = COALESCE(workers.last_seen, excluded.last_seen)
        """, (pc_id, hostname, now, now, reason))

        release_profiles_for_worker(conn, pc_id)

        row = conn.execute("SELECT * FROM workers WHERE pc_id = ?", (pc_id,)).fetchone()
        return jsonify({
            "ok": True,
            "blocked": True,
            "worker": row_to_dict(row)
        })
    finally:
        conn.close()


@app.route("/api/workers/<pc_id>/unblock", methods=["POST"])
def unblock_worker(pc_id):
    pc_id = str(pc_id).strip()
    if not pc_id:
        return jsonify({"ok": False, "error": "pc_id is required"}), 400

    conn = get_db()
    try:
        conn.execute("""
            UPDATE workers
            SET
                blocked = 0,
                blocked_at = NULL,
                blocked_reason = '',
                status = 'OFFLINE'
            WHERE pc_id = ?
        """, (pc_id,))

        row = conn.execute("SELECT * FROM workers WHERE pc_id = ?", (pc_id,)).fetchone()
        return jsonify({
            "ok": True,
            "blocked": False,
            "worker": row_to_dict(row)
        })
    finally:
        conn.close()



@app.route("/api/ip-blacklist", methods=["GET"])
def list_ip_blacklist():
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT *
            FROM ip_blacklist
            WHERE active = 1
            ORDER BY updated_at DESC
        """).fetchall()
        return jsonify({
            "ok": True,
            "blacklisted_ips": [row_to_dict(r) for r in rows]
        })
    finally:
        conn.close()


@app.route("/api/ip-blacklist/check", methods=["POST"])
def check_ip_blacklist():
    data = request.get_json(force=True) or {}
    ip_address = extract_ip_only(data.get("ip") or data.get("ip_address") or data.get("ip_label"))

    if not ip_address:
        return jsonify({"ok": False, "error": "valid ip required", "blacklisted": False}), 400

    conn = get_db()
    try:
        row = conn.execute("""
            SELECT *
            FROM ip_blacklist
            WHERE ip_address = ? AND active = 1
            LIMIT 1
        """, (ip_address,)).fetchone()

        if not row:
            return jsonify({"ok": True, "ip": ip_address, "blacklisted": False})

        item = row_to_dict(row)
        return jsonify({
            "ok": True,
            "ip": ip_address,
            "blacklisted": True,
            "reason": item.get("reason") or "Coordinator blacklist",
            "item": item
        })
    finally:
        conn.close()


@app.route("/api/ip-blacklist/add", methods=["POST"])
def add_ip_blacklist():
    data = request.get_json(force=True) or {}
    ip_address = extract_ip_only(data.get("ip") or data.get("ip_address") or data.get("ip_label"))
    ip_label = str(data.get("ip_label") or data.get("ip") or ip_address).strip()
    reason = str(data.get("reason") or "Manual blacklist").strip()
    source_pc_id = str(data.get("pc_id") or data.get("source_pc_id") or "").strip()
    now = now_ts()

    if not ip_address:
        return jsonify({"ok": False, "error": "valid ip required"}), 400

    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO ip_blacklist (ip_address, ip_label, reason, source_pc_id, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(ip_address) DO UPDATE SET
                ip_label = excluded.ip_label,
                reason = excluded.reason,
                source_pc_id = excluded.source_pc_id,
                active = 1,
                updated_at = excluded.updated_at
        """, (ip_address, ip_label, reason, source_pc_id, now, now))

        row = conn.execute("SELECT * FROM ip_blacklist WHERE ip_address = ?", (ip_address,)).fetchone()
        return jsonify({"ok": True, "ip": ip_address, "item": row_to_dict(row)})
    finally:
        conn.close()


@app.route("/api/ip-blacklist/remove", methods=["POST"])
def remove_ip_blacklist():
    data = request.get_json(force=True) or {}
    ip_address = extract_ip_only(data.get("ip") or data.get("ip_address") or data.get("ip_label"))
    now = now_ts()

    if not ip_address:
        return jsonify({"ok": False, "error": "valid ip required"}), 400

    conn = get_db()
    try:
        conn.execute("""
            UPDATE ip_blacklist
            SET active = 0,
                updated_at = ?
            WHERE ip_address = ?
        """, (now, ip_address))
        return jsonify({"ok": True, "ip": ip_address, "removed": True})
    finally:
        conn.close()


@app.route("/api/profiles", methods=["GET"])
def list_profiles():
    conn = get_db()
    try:
        release_expired_locks(conn)

        rows = conn.execute("""
            SELECT *
            FROM profiles
            ORDER BY id ASC
        """).fetchall()

        return jsonify({
            "ok": True,
            "profiles": [row_to_dict(r) for r in rows]
        })
    finally:
        conn.close()


@app.route("/api/profiles/seed", methods=["POST"])
def seed_profiles():
    data = request.get_json(force=True) or {}
    count = int(data.get("count", 10))
    now = now_ts()

    conn = get_db()
    try:
        existing = conn.execute("SELECT COUNT(*) AS c FROM profiles").fetchone()["c"]

        if existing > 0:
            return jsonify({
                "ok": True,
                "message": "Profiles already exist",
                "existing_count": existing
            })

        for i in range(1, count + 1):
            conn.execute("""
                INSERT INTO profiles (name, hardware_cloak, hardware_profile_json, status, current_target, ip_origin, created_at, updated_at)
                VALUES (?, 'Pending Execution', '', 'OFFLINE', 'None', 'Unknown', ?, ?)
            """, (f"Profile {i}", now, now))

        return jsonify({
            "ok": True,
            "created": count
        })
    finally:
        conn.close()


@app.route("/api/profiles/create", methods=["POST"])
def create_profile():
    data = request.get_json(force=True) or {}

    name = str(data.get("name", "")).strip()
    hardware_cloak = str(data.get("hardware_cloak", "Pending Execution")).strip()
    hardware_profile_json = str(data.get("hardware_profile_json", "") or "").strip()
    if not hardware_profile_json and hardware_cloak.startswith("{"):
        hardware_profile_json = hardware_cloak
    now = now_ts()

    conn = get_db()
    try:
        if not name:
            next_id = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM profiles").fetchone()["next_id"]
            name = f"Profile {next_id}"

        cur = conn.execute("""
            INSERT INTO profiles (name, hardware_cloak, hardware_profile_json, status, current_target, ip_origin, created_at, updated_at)
            VALUES (?, ?, ?, 'OFFLINE', 'None', 'Unknown', ?, ?)
        """, (name, hardware_cloak, hardware_profile_json, now, now))

        profile_id = cur.lastrowid

        row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()

        return jsonify({
            "ok": True,
            "profile": row_to_dict(row)
        })
    finally:
        conn.close()


@app.route("/api/profiles/<int:profile_id>/hardware", methods=["POST"])
def update_profile_hardware(profile_id):
    data = request.get_json(force=True) or {}
    hardware_cloak = str(data.get("hardware_cloak", "")).strip() or "Pending Execution"
    hardware_profile_json = str(data.get("hardware_profile_json", "") or "").strip()
    now = now_ts()

    conn = get_db()
    try:
        result = conn.execute(
            "UPDATE profiles SET hardware_cloak = ?, hardware_profile_json = ?, updated_at = ? WHERE id = ?",
            (hardware_cloak, hardware_profile_json, now, profile_id),
        )
        if result.rowcount == 0:
            return jsonify({"ok": False, "error": "profile not found"}), 404
        row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        return jsonify({"ok": True, "profile": row_to_dict(row)})
    finally:
        conn.close()


@app.route("/api/profiles/<int:profile_id>/acquire", methods=["POST"])
def acquire_profile(profile_id):
    data = request.get_json(force=True) or {}

    pc_id = str(data.get("pc_id", "")).strip()
    current_target = str(data.get("current_target", "Starting")).strip()
    now = now_ts()

    if not pc_id:
        return jsonify({"ok": False, "error": "pc_id is required"}), 400

    conn = get_db()
    try:
        if is_worker_blocked(conn, pc_id):
            return jsonify({
                "ok": False,
                "error": "pc_blocked",
                "pc_id": pc_id,
                "blocked": True,
                "blocked_reason": get_worker_block_reason(conn, pc_id)
            }), 200

        conn.execute("BEGIN IMMEDIATE")

        release_expired_locks(conn)

        row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()

        if not row:
            conn.execute("ROLLBACK")
            return jsonify({"ok": False, "error": "profile not found"}), 404

        row = row_to_dict(row)

        locked_by = row.get("locked_by")
        lease_until = row.get("lease_until") or 0
        status = row.get("status")

        if status == "RUNNING" and lease_until > now and locked_by != pc_id:
            conn.execute("ROLLBACK")
            return jsonify({
                "ok": False,
                "error": "profile_locked",
                "profile_id": profile_id,
                "locked_by": locked_by,
                "lease_until": lease_until
            }), 409

        conn.execute("""
            UPDATE profiles
            SET
                status = 'RUNNING',
                locked_by = ?,
                locked_at = ?,
                lease_until = ?,
                last_heartbeat = ?,
                current_target = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            pc_id,
            now,
            now + LEASE_SECONDS,
            now,
            current_target,
            now,
            profile_id
        ))

        conn.execute("COMMIT")

        updated = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()

        return jsonify({
            "ok": True,
            "status": "ACQUIRED",
            "profile": row_to_dict(updated)
        })
    except Exception as e:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/profiles/<int:profile_id>/heartbeat", methods=["POST"])
def heartbeat_profile(profile_id):
    data = request.get_json(force=True) or {}

    pc_id = str(data.get("pc_id", "")).strip()
    current_target = str(data.get("current_target", "")).strip()
    ip_origin = str(data.get("ip_origin", "")).strip()
    now = now_ts()

    if not pc_id:
        return jsonify({"ok": False, "error": "pc_id is required"}), 400

    conn = get_db()
    try:
        if is_worker_blocked(conn, pc_id):
            release_profiles_for_worker(conn, pc_id)
            return jsonify({
                "ok": False,
                "error": "pc_blocked",
                "pc_id": pc_id,
                "blocked": True,
                "blocked_reason": get_worker_block_reason(conn, pc_id)
            }), 200

        row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()

        if not row:
            return jsonify({"ok": False, "error": "profile not found"}), 404

        row = row_to_dict(row)

        if row.get("locked_by") != pc_id:
            return jsonify({
                "ok": False,
                "error": "not_lock_owner",
                "locked_by": row.get("locked_by")
            }), 409

        touch_worker(conn, pc_id, "", request.remote_addr)

        conn.execute("""
            UPDATE profiles
            SET
                lease_until = ?,
                last_heartbeat = ?,
                current_target = COALESCE(NULLIF(?, ''), current_target),
                ip_origin = COALESCE(NULLIF(?, ''), ip_origin),
                updated_at = ?
            WHERE id = ?
        """, (
            now + LEASE_SECONDS,
            now,
            current_target,
            ip_origin,
            now,
            profile_id
        ))

        return jsonify({
            "ok": True,
            "profile_id": profile_id,
            "lease_until": now + LEASE_SECONDS
        })
    finally:
        conn.close()


@app.route("/api/profiles/<int:profile_id>/release", methods=["POST"])
def release_profile(profile_id):
    data = request.get_json(force=True) or {}

    pc_id = str(data.get("pc_id", "")).strip()
    force = bool(data.get("force", False))
    now = now_ts()

    if not pc_id and not force:
        return jsonify({"ok": False, "error": "pc_id is required"}), 400

    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()

        if not row:
            return jsonify({"ok": False, "error": "profile not found"}), 404

        row = row_to_dict(row)

        if not force and row.get("locked_by") != pc_id:
            return jsonify({
                "ok": False,
                "error": "not_lock_owner",
                "locked_by": row.get("locked_by")
            }), 409

        conn.execute("""
            UPDATE profiles
            SET
                status = 'OFFLINE',
                locked_by = NULL,
                locked_at = NULL,
                lease_until = NULL,
                last_heartbeat = NULL,
                current_target = 'None',
                updated_at = ?
            WHERE id = ?
        """, (now, profile_id))

        return jsonify({
            "ok": True,
            "released": profile_id
        })
    finally:
        conn.close()


@app.route("/api/profiles/release-by-pc", methods=["POST"])
def release_by_pc():
    data = request.get_json(force=True) or {}

    pc_id = str(data.get("pc_id", "")).strip()
    now = now_ts()

    if not pc_id:
        return jsonify({"ok": False, "error": "pc_id is required"}), 400

    conn = get_db()
    try:
        conn.execute("""
            UPDATE profiles
            SET
                status = 'OFFLINE',
                locked_by = NULL,
                locked_at = NULL,
                lease_until = NULL,
                last_heartbeat = NULL,
                current_target = 'None',
                updated_at = ?
            WHERE locked_by = ?
        """, (now, pc_id))

        return jsonify({
            "ok": True,
            "released_by_pc": pc_id
        })
    finally:
        conn.close()


# ============================================================
# WORKER COMPATIBILITY ROUTES
# ============================================================

@app.route("/api/mobile/tasks", methods=["GET"])
def list_mobile_tasks():
    pc_id = str(request.args.get("pc_id") or "").strip()
    status = str(request.args.get("status") or "").strip()
    limit = clean_limit(request.args.get("limit"), default=50, maximum=500)

    where = []
    params = []

    if pc_id:
        where.append("pc_id = ?")
        params.append(pc_id)
    if status:
        where.append("status = ?")
        params.append(status)

    sql = "SELECT * FROM mobile_tasks"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    conn = get_db()
    try:
        rows = conn.execute(sql, params).fetchall()
        return jsonify({
            "ok": True,
            "tasks": [task_row_to_dict(row) for row in rows],
            "time": now_ts()
        })
    finally:
        conn.close()


@app.route("/api/mobile/tasks/create", methods=["POST"])
def create_mobile_task():
    data = request.get_json(force=True) or {}
    pc_id = str(data.get("pc_id") or data.get("target_pc_id") or "").strip()
    task_type = str(data.get("task_type") or data.get("type") or "").strip()
    payload = data.get("payload") or {}
    requester = request_pc_id(default="")

    if not pc_id:
        return jsonify({"ok": False, "error": "pc_id is required"}), 400
    if not task_type:
        return jsonify({"ok": False, "error": "task_type is required"}), 400

    task_id = uuid.uuid4().hex
    now = now_ts()

    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO mobile_tasks (
                task_id, pc_id, task_type, payload_json, status,
                requested_by, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
        """, (task_id, pc_id, task_type, json_pack(payload), requester, now, now))
        record_security_event(conn, "MOBILE_TASK_CREATED", requester, "INFO", "info", f"{task_type} -> {pc_id}")
        row = conn.execute("SELECT * FROM mobile_tasks WHERE task_id = ?", (task_id,)).fetchone()
        return jsonify({"ok": True, "task": task_row_to_dict(row), "task_id": task_id})
    finally:
        conn.close()


@app.route("/api/device-permissions", methods=["GET"])
def get_device_permissions_route():
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM workers ORDER BY last_seen DESC, pc_id ASC").fetchall()
        workers = [row_to_dict(row) for row in rows]
        devices = {}

        for item in workers:
            pc_id = item.get("pc_id")
            if not pc_id:
                continue
            devices[pc_id] = {
                "pc_id": pc_id,
                "role": item.get("device_role") or "Monitor Only",
                "device_type": item.get("device_type") or "Unknown",
                "blocked": bool(int(item.get("blocked") or 0) == 1),
                "can_launch_profiles": bool(int(item.get("can_launch_profiles") or 0) == 1),
                "can_run_mobile_tasks": bool(int(item.get("can_run_mobile_tasks") or 0) == 1),
                "can_control_fleet": bool(int(item.get("can_control_fleet") or 0) == 1),
                "can_be_blocked": bool(int(item.get("can_be_blocked") or 1) == 1),
            }

        return jsonify({
            "ok": True,
            "workers": workers,
            "devices": devices,
            "time": now_ts()
        })
    finally:
        conn.close()


def role_to_permission_fields(role):
    raw = str(role or "monitor_only").strip().lower()

    if raw in ["controller", "control", "fleet_controller"]:
        return {
            "device_role": "Controller",
            "can_launch_profiles": 0,
            "can_run_mobile_tasks": 0,
            "can_control_fleet": 1,
            "can_be_blocked": 0,
        }
    if raw in ["worker_pc", "pc", "desktop", "worker laptop", "worker_laptop", "laptop"]:
        return {
            "device_role": "Worker Laptop" if "laptop" in raw else "Worker PC",
            "can_launch_profiles": 1,
            "can_run_mobile_tasks": 0,
            "can_control_fleet": 0,
            "can_be_blocked": 1,
        }
    if raw in ["worker_phone", "phone", "mobile", "tablet", "worker_tablet"]:
        return {
            "device_role": "Worker Phone" if "phone" in raw or "mobile" in raw else "Worker Tablet",
            "can_launch_profiles": 0,
            "can_run_mobile_tasks": 1,
            "can_control_fleet": 0,
            "can_be_blocked": 1,
        }

    return {
        "device_role": "Monitor Only",
        "can_launch_profiles": 0,
        "can_run_mobile_tasks": 0,
        "can_control_fleet": 0,
        "can_be_blocked": 1,
    }


@app.route("/api/device-permissions/set", methods=["POST"])
def set_device_permissions_route():
    data = request.get_json(force=True) or {}
    pc_id = str(data.get("pc_id") or "").strip()
    role = str(data.get("role") or "monitor_only").strip()

    if not pc_id:
        return jsonify({"ok": False, "error": "pc_id is required"}), 400

    fields = role_to_permission_fields(role)
    now = now_ts()

    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO workers (
                pc_id, hostname, ip_address, last_seen, status, blocked,
                device_type, device_role, can_launch_profiles,
                can_run_mobile_tasks, can_control_fleet, can_be_blocked
            )
            VALUES (?, '', '', ?, 'OFFLINE', 0, 'Unknown', ?, ?, ?, ?, ?)
            ON CONFLICT(pc_id) DO UPDATE SET
                device_role = excluded.device_role,
                can_launch_profiles = excluded.can_launch_profiles,
                can_run_mobile_tasks = excluded.can_run_mobile_tasks,
                can_control_fleet = excluded.can_control_fleet,
                can_be_blocked = excluded.can_be_blocked
        """, (
            pc_id,
            now,
            fields["device_role"],
            fields["can_launch_profiles"],
            fields["can_run_mobile_tasks"],
            fields["can_control_fleet"],
            fields["can_be_blocked"],
        ))
        record_security_event(conn, "DEVICE_PERMISSION_SET", request_pc_id(), "INFO", "info", f"{pc_id} -> {role}")
        row = conn.execute("SELECT * FROM workers WHERE pc_id = ?", (pc_id,)).fetchone()
        return jsonify({"ok": True, "worker": row_to_dict(row), "devices": {pc_id: row_to_dict(row)}})
    finally:
        conn.close()


@app.route("/api/device-permissions/block", methods=["POST"])
def block_device_permissions_route():
    data = request.get_json(force=True) or {}
    pc_id = str(data.get("pc_id") or "").strip()
    blocked = bool(data.get("blocked", True))
    now = now_ts()

    if not pc_id:
        return jsonify({"ok": False, "error": "pc_id is required"}), 400

    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO workers (pc_id, hostname, ip_address, last_seen, status, blocked, blocked_at, blocked_reason)
            VALUES (?, '', '', ?, ?, ?, ?, ?)
            ON CONFLICT(pc_id) DO UPDATE SET
                blocked = excluded.blocked,
                blocked_at = excluded.blocked_at,
                blocked_reason = excluded.blocked_reason,
                status = excluded.status
        """, (
            pc_id,
            now,
            "BLOCKED" if blocked else "OFFLINE",
            1 if blocked else 0,
            now if blocked else None,
            "Blocked from Device Permissions" if blocked else "",
        ))

        if blocked:
            release_profiles_for_worker(conn, pc_id)

        record_security_event(conn, "DEVICE_BLOCK_CHANGED", request_pc_id(), "INFO", "warning" if blocked else "info", f"{pc_id} blocked={blocked}")
        row = conn.execute("SELECT * FROM workers WHERE pc_id = ?", (pc_id,)).fetchone()
        return jsonify({"ok": True, "blocked": blocked, "worker": row_to_dict(row)})
    finally:
        conn.close()


@app.route("/api/security-events", methods=["GET"])
def list_security_events_route():
    limit = clean_limit(request.args.get("limit"), default=200, maximum=1000)
    event_type = str(request.args.get("event_type") or "").strip()
    pc_id = str(request.args.get("pc_id") or "").strip()
    status = str(request.args.get("status") or "").strip()

    where = []
    params = []
    if event_type:
        where.append("event_type = ?")
        params.append(event_type)
    if pc_id:
        where.append("pc_id = ?")
        params.append(pc_id)
    if status:
        where.append("status = ?")
        params.append(status)

    sql = "SELECT * FROM security_events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY event_ts DESC, id DESC LIMIT ?"
    params.append(limit)

    conn = get_db()
    try:
        rows = conn.execute(sql, params).fetchall()
        return jsonify({"ok": True, "events": [row_to_dict(row) for row in rows], "time": now_ts()})
    finally:
        conn.close()


@app.route("/api/security-events/clear", methods=["POST"])
def clear_security_events_route():
    conn = get_db()
    try:
        count = conn.execute("SELECT COUNT(*) FROM security_events").fetchone()[0]
        conn.execute("DELETE FROM security_events")
        record_security_event(conn, "SECURITY_EVENTS_CLEARED", request_pc_id(), "INFO", "info", f"cleared={count}")
        return jsonify({"ok": True, "cleared": count})
    finally:
        conn.close()


@app.route("/api/device-commands", methods=["GET"])
def list_device_commands_route():
    target_pc_id = str(request.args.get("target_pc_id") or "").strip()
    status = str(request.args.get("status") or "").strip()
    limit = clean_limit(request.args.get("limit"), default=100, maximum=1000)

    where = []
    params = []
    if target_pc_id:
        where.append("target_pc_id = ?")
        params.append(target_pc_id)
    if status:
        where.append("status = ?")
        params.append(status)

    sql = "SELECT * FROM device_commands"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    conn = get_db()
    try:
        rows = conn.execute(sql, params).fetchall()
        return jsonify({"ok": True, "commands": [command_row_to_dict(row) for row in rows], "time": now_ts()})
    finally:
        conn.close()


@app.route("/api/device-commands/create", methods=["POST"])
def create_device_command_route():
    data = request.get_json(force=True) or {}
    target_pc_id = str(data.get("target_pc_id") or "").strip()
    command_type = str(data.get("command_type") or "").strip().upper()
    payload = data.get("payload") or {}
    requester = request_pc_id()

    allowed = {
        "PING",
        "STATUS_REPORT",
        "START_DASHBOARD",
        "START_MOBILE_WORKER",
        "START_SYNC",
        "MARK_AVAILABLE",
        "MARK_UNAVAILABLE",
        "STOP_COMMAND_WORKER",
    }

    if not target_pc_id:
        return jsonify({"ok": False, "error": "target_pc_id is required"}), 400
    if command_type not in allowed:
        return jsonify({"ok": False, "error": f"unsupported command_type: {command_type}"}), 400

    command_id = uuid.uuid4().hex
    now = now_ts()

    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO device_commands (
                command_id, target_pc_id, command_type, payload_json,
                status, requested_by, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'queued', ?, ?, ?)
        """, (command_id, target_pc_id, command_type, json_pack(payload), requester, now, now))
        record_security_event(conn, "DEVICE_COMMAND_CREATED", requester, "INFO", "info", f"{command_type} -> {target_pc_id}")
        row = conn.execute("SELECT * FROM device_commands WHERE command_id = ?", (command_id,)).fetchone()
        return jsonify({"ok": True, "command": command_row_to_dict(row), "command_id": command_id})
    finally:
        conn.close()


@app.route("/api/device-commands/claim", methods=["POST"])
def claim_device_commands_route():
    data = request.get_json(force=True) or {}
    pc_id = str(data.get("pc_id") or request.headers.get("X-PC-ID") or "").strip()
    limit = clean_limit(data.get("limit"), default=5, maximum=25)
    now = now_ts()

    if not pc_id:
        return jsonify({"ok": False, "error": "pc_id is required", "commands": []}), 400

    conn = get_db()
    try:
        touch_worker(conn, pc_id, "", request.remote_addr, {"device_type": request.headers.get("X-Device-Type", "")})

        rows = conn.execute("""
            SELECT * FROM device_commands
            WHERE target_pc_id = ?
              AND status IN ('queued', 'pending')
            ORDER BY created_at ASC
            LIMIT ?
        """, (pc_id, limit)).fetchall()

        command_ids = [row["command_id"] for row in rows]
        if command_ids:
            placeholders = ",".join("?" for _ in command_ids)
            conn.execute(f"""
                UPDATE device_commands
                SET status = 'claimed',
                    claimed_by = ?,
                    claimed_at = ?,
                    updated_at = ?
                WHERE command_id IN ({placeholders})
            """, [pc_id, now, now] + command_ids)

        claimed = []
        for command_id in command_ids:
            row = conn.execute("SELECT * FROM device_commands WHERE command_id = ?", (command_id,)).fetchone()
            claimed.append(command_row_to_dict(row))

        return jsonify({"ok": True, "commands": claimed, "time": now})
    finally:
        conn.close()


@app.route("/api/device-commands/complete", methods=["POST"])
def complete_device_command_route():
    data = request.get_json(force=True) or {}
    command_id = str(data.get("command_id") or "").strip()
    pc_id = str(data.get("pc_id") or request.headers.get("X-PC-ID") or "").strip()
    status = str(data.get("status") or "completed").strip().lower()
    result = data.get("result") or {}
    error = str(data.get("error") or "").strip()
    now = now_ts()

    if not command_id:
        return jsonify({"ok": False, "error": "command_id is required"}), 400
    if status not in ["completed", "failed", "cancelled"]:
        status = "completed"

    conn = get_db()
    try:
        conn.execute("""
            UPDATE device_commands
            SET status = ?,
                result_json = ?,
                error = ?,
                claimed_by = COALESCE(NULLIF(claimed_by, ''), ?),
                updated_at = ?,
                completed_at = ?
            WHERE command_id = ?
        """, (status, json_pack(result), error, pc_id, now, now, command_id))
        row = conn.execute("SELECT * FROM device_commands WHERE command_id = ?", (command_id,)).fetchone()
        return jsonify({"ok": True, "command": command_row_to_dict(row)})
    finally:
        conn.close()


# ============================================================
# AUTO SYNC ROUTES
# ============================================================

SYNC_ALLOWED_FILES = {
    "coordinator_server.py",
    "start_dashboard.py",
    "mobile_worker.py",
    "sync_updates_to_main.py",
    "engine/db_manager.py",
    "engine/ghost_core.py",
    "engine/session_recorder.py",
    "ui/index.html",
    "ui/app.js",
    "ui/style.css",
}


def sync_path_allowed(rel_path):
    rel = str(rel_path or "").replace("\\", "/").strip("/")
    if not rel or rel.startswith("../") or "/../" in rel or os.path.isabs(rel):
        return False
    if rel in SYNC_ALLOWED_FILES:
        return True
    return rel.startswith("engine/platform_runners/") and rel.endswith(".py")


def safe_sync_destination(rel_path):
    rel = str(rel_path or "").replace("\\", "/").strip("/")
    dest = (Path(BASE_DIR) / Path(rel)).resolve()
    base = Path(BASE_DIR).resolve()
    try:
        dest.relative_to(base)
    except ValueError:
        return None
    return dest


@app.route("/api/sync/status", methods=["GET"])
def sync_status_route():
    conn = get_db()
    try:
        return jsonify({
            "ok": True,
            "time": now_ts(),
            "sync_token_configured": bool(configured_sync_token()),
            "pending_restart": truthy(get_setting(conn, "pending_restart", "false")),
            "server_file": os.path.abspath(__file__),
        })
    finally:
        conn.close()


@app.route("/api/sync/upload", methods=["POST"])
def sync_upload_route():
    if not sync_authorized():
        return jsonify({"ok": False, "error": "invalid sync token"}), 403

    data = request.get_json(force=True) or {}
    files = data.get("files") or []

    if not isinstance(files, list):
        return jsonify({"ok": False, "error": "files must be a list"}), 400

    changed = []
    skipped = []
    rejected = []
    backup_root = Path(BASE_DIR) / "_archive" / "sync_backups" / time.strftime("%Y%m%d_%H%M%S")

    for item in files:
        rel = str((item or {}).get("path") or "").replace("\\", "/").strip("/")
        expected_sha = str((item or {}).get("sha256") or "").lower().strip()
        content_b64 = str((item or {}).get("content_b64") or "")

        if not sync_path_allowed(rel):
            rejected.append({"path": rel, "reason": "path not allowed"})
            continue

        dest = safe_sync_destination(rel)
        if dest is None:
            rejected.append({"path": rel, "reason": "unsafe path"})
            continue

        try:
            raw = base64.b64decode(content_b64)
        except Exception as e:
            rejected.append({"path": rel, "reason": f"bad base64: {e}"})
            continue

        actual_sha = hashlib.sha256(raw).hexdigest()
        if expected_sha and actual_sha != expected_sha:
            rejected.append({"path": rel, "reason": "sha256 mismatch"})
            continue

        if dest.exists():
            current_sha = hashlib.sha256(dest.read_bytes()).hexdigest()
            if current_sha == actual_sha:
                skipped.append({"path": rel, "reason": "already current"})
                continue

            backup_path = backup_root / rel
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            backup_path.write_bytes(dest.read_bytes())

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        changed.append({"path": rel, "sha256": actual_sha})

    restart_required = any(item["path"] == "coordinator_server.py" for item in changed)

    conn = get_db()
    try:
        if changed:
            set_setting(conn, "last_sync_time", str(now_ts()))
            set_setting(conn, "last_sync_changed_count", str(len(changed)))
        if restart_required:
            set_setting(conn, "pending_restart", "true")
        record_security_event(conn, "SYNC_UPLOAD", request_pc_id(), "INFO", "info", f"changed={len(changed)} rejected={len(rejected)}")
    finally:
        conn.close()

    return jsonify({
        "ok": True,
        "changed": changed,
        "changed_count": len(changed),
        "skipped": skipped,
        "rejected": rejected,
        "restart_required": restart_required,
    })


@app.route("/api/sync/restart", methods=["POST"])
def sync_restart_route():
    if not sync_authorized():
        return jsonify({"ok": False, "error": "invalid sync token"}), 403

    conn = get_db()
    try:
        set_setting(conn, "pending_restart", "false")
        record_security_event(conn, "SYNC_RESTART_REQUESTED", request_pc_id(), "INFO", "warning", "Coordinator restart requested")
    finally:
        conn.close()

    # If your main PC launcher watches exit code 10, set this environment
    # variable on the main PC before starting the coordinator:
    #   set COMET_ALLOW_COORDINATOR_SELF_RESTART=1
    if truthy(os.environ.get("COMET_ALLOW_COORDINATOR_SELF_RESTART", "")):
        def delayed_exit():
            time.sleep(0.5)
            os._exit(10)

        threading.Thread(target=delayed_exit, daemon=True).start()

    return jsonify({
        "ok": True,
        "exit_code": 10,
        "message": "Coordinator restart requested. Master launcher should restart it.",
    })


# ============================================================
# ML COMPATIBILITY ROUTES
# ============================================================

def list_ml_events(conn, limit=200):
    rows = conn.execute(
        "SELECT * FROM ml_events ORDER BY event_ts DESC, id DESC LIMIT ?",
        (clean_limit(limit, default=200, maximum=1000),)
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def list_ml_actions(conn, status="", severity="", limit=200):
    where = []
    params = []
    if status:
        where.append("status = ?")
        params.append(str(status))
    if severity:
        where.append("severity = ?")
        params.append(str(severity))

    sql = "SELECT * FROM ml_actions"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(clean_limit(limit, default=200, maximum=1000))

    rows = conn.execute(sql, params).fetchall()
    return [row_to_dict(row) for row in rows]


def worker_scores(conn):
    rows = conn.execute("SELECT * FROM workers ORDER BY last_seen DESC, pc_id ASC").fetchall()
    scores = []
    now = now_ts()
    for row in rows:
        item = row_to_dict(row)
        last_seen = int(item.get("last_seen") or 0)
        blocked = bool(int(item.get("blocked") or 0) == 1)
        score = 0 if blocked else (100 if last_seen and now - last_seen <= WORKER_ONLINE_SECONDS else 40)
        scores.append({
            "pc_id": item.get("pc_id"),
            "device_type": item.get("device_type") or "Unknown",
            "display_status": "BLOCKED" if blocked else ("ONLINE" if score == 100 else "OFFLINE"),
            "reliability_score": score,
            "recommendation": "Available" if score == 100 else "Check worker connectivity",
        })
    return scores


@app.route("/api/ml/<path:ml_path>", methods=["GET", "POST"])
def ml_compat_route(ml_path):
    path = str(ml_path or "").strip("/")
    data = request.get_json(silent=True) or {}
    requester = request_pc_id()

    conn = get_db()
    try:
        if path == "status":
            return jsonify({
                "ok": True,
                "engine": "ml_compatibility_v1",
                "enabled": True,
                "events_count": conn.execute("SELECT COUNT(*) FROM ml_events").fetchone()[0],
                "actions_count": conn.execute("SELECT COUNT(*) FROM ml_actions").fetchone()[0],
                "time": now_ts(),
            })

        if path in ["reliability", "adjusted-reliability"]:
            return jsonify({"ok": True, "device_scores": worker_scores(conn), "time": now_ts()})

        if path == "anomalies":
            return jsonify({"ok": True, "anomalies": []})

        if path == "recommendations":
            return jsonify({"ok": True, "recommendations": []})

        if path == "command-prediction":
            target_pc_id = str(request.args.get("target_pc_id") or "").strip()
            command_type = str(request.args.get("command_type") or "").strip().upper()
            known = conn.execute("SELECT pc_id FROM workers WHERE pc_id = ?", (target_pc_id,)).fetchone()
            return jsonify({
                "ok": True,
                "target_pc_id": target_pc_id,
                "command_type": command_type,
                "success_probability": 0.85 if known else 0.35,
                "recommendation": "Known worker" if known else "Worker has not registered yet",
            })

        if path in ["events", "auto-executor/events", "feedback/events", "auto-resolver/events"]:
            return jsonify({"ok": True, "events": list_ml_events(conn, request.args.get("limit", 200))})

        if path == "events/clear":
            count = conn.execute("SELECT COUNT(*) FROM ml_events").fetchone()[0]
            conn.execute("DELETE FROM ml_events")
            return jsonify({"ok": True, "cleared": count})

        if path == "history/snapshot":
            history_id = uuid.uuid4().hex
            payload = {
                "workers": len(worker_scores(conn)),
                "actions": conn.execute("SELECT COUNT(*) FROM ml_actions").fetchone()[0],
                "events": conn.execute("SELECT COUNT(*) FROM ml_events").fetchone()[0],
            }
            conn.execute("""
                INSERT INTO ml_history (history_id, event_ts, event_type, payload_json)
                VALUES (?, ?, 'snapshot', ?)
            """, (history_id, now_ts(), json_pack(payload)))
            return jsonify({"ok": True, "history_id": history_id, "snapshot": payload})

        if path == "history":
            rows = conn.execute(
                "SELECT * FROM ml_history ORDER BY event_ts DESC LIMIT ?",
                (clean_limit(request.args.get("limit"), default=200, maximum=1000),)
            ).fetchall()
            history = []
            for row in rows:
                item = row_to_dict(row)
                item["payload"] = json_unpack(item.pop("payload_json", ""), {})
                history.append(item)
            return jsonify({"ok": True, "history": history})

        if path == "trends":
            return jsonify({"ok": True, "device_trends": worker_scores(conn), "recommendations": []})

        if path == "history/clear":
            count = conn.execute("SELECT COUNT(*) FROM ml_history").fetchone()[0]
            conn.execute("DELETE FROM ml_history")
            return jsonify({"ok": True, "cleared": count})

        if path == "actions":
            return jsonify({
                "ok": True,
                "actions": list_ml_actions(
                    conn,
                    request.args.get("status", ""),
                    request.args.get("severity", ""),
                    request.args.get("limit", 200),
                )
            })

        if path == "actions/generate":
            record_ml_event(conn, "ACTIONS_GENERATED", requester, "info", "Compatibility generator checked worker state")
            return jsonify({"ok": True, "added": [], "message": "No automatic actions needed."})

        if path in ["actions/approve", "actions/reject", "actions/complete"]:
            action_id = str(data.get("action_id") or "").strip()
            if not action_id:
                return jsonify({"ok": False, "error": "action_id is required"}), 400
            new_status = {
                "actions/approve": "approved",
                "actions/reject": "rejected",
                "actions/complete": str(data.get("status") or "completed"),
            }[path]
            conn.execute("""
                UPDATE ml_actions
                SET status = ?, notes = ?, updated_at = ?, completed_at = ?
                WHERE action_id = ?
            """, (new_status, str(data.get("notes") or ""), now_ts(), now_ts(), action_id))
            row = conn.execute("SELECT * FROM ml_actions WHERE action_id = ?", (action_id,)).fetchone()
            return jsonify({"ok": True, "action": row_to_dict(row)})

        if path == "actions/clear":
            mode = str(data.get("mode") or "completed")
            if mode == "all":
                count = conn.execute("SELECT COUNT(*) FROM ml_actions").fetchone()[0]
                conn.execute("DELETE FROM ml_actions")
            else:
                count = conn.execute(
                    "SELECT COUNT(*) FROM ml_actions WHERE status IN ('completed', 'rejected')"
                ).fetchone()[0]
                conn.execute("DELETE FROM ml_actions WHERE status IN ('completed', 'rejected')")
            return jsonify({"ok": True, "cleared": count})

        if path == "actions/auto-run":
            record_ml_event(conn, "AUTO_EXECUTOR_RUN", requester, "info", "Compatibility auto-run did not execute commands")
            return jsonify({"ok": True, "executed": [], "message": "No approved automatic actions to run."})

        if path in ["auto-executor/config", "feedback/config", "auto-resolver/config", "rl-architecture/config"]:
            key = "ml_" + path.replace("/", "_")
            if request.method == "POST":
                set_setting(conn, key, json_pack(data))
            return jsonify({"ok": True, "config": json_unpack(get_setting(conn, key, "{}"), {})})

        if path in ["feedback/run", "auto-resolver/run"]:
            record_ml_event(conn, path.upper().replace("/", "_"), requester, "info", "Compatibility run completed")
            return jsonify({"ok": True, "changed": [], "message": "Compatibility run completed."})

        if path == "control-center":
            return jsonify({
                "ok": True,
                "devices": worker_scores(conn),
                "actions": list_ml_actions(conn, limit=100),
                "events": list_ml_events(conn, 100),
            })

        if path == "device-timeline":
            pc_id = str(request.args.get("pc_id") or "").strip()
            rows = conn.execute("""
                SELECT event_ts, event_type, pc_id, severity, details
                FROM ml_events
                WHERE (? = '' OR pc_id = ?)
                ORDER BY event_ts DESC
                LIMIT ?
            """, (pc_id, pc_id, clean_limit(request.args.get("limit"), default=500, maximum=1000))).fetchall()
            return jsonify({"ok": True, "timeline": [row_to_dict(row) for row in rows]})

        if path == "smart-workers":
            return jsonify({"ok": True, "workers": worker_scores(conn), "stale_targets": []})

        if path == "stale-targets":
            return jsonify({"ok": True, "stale_targets": []})

        if path in ["backup-guard/status", "backup-guard/list"]:
            backup_dir = Path(BASE_DIR) / "system_backups"
            backups = []
            if backup_dir.exists():
                for child in sorted(backup_dir.iterdir(), reverse=True):
                    if child.is_dir():
                        backups.append({"id": child.name, "path": str(child), "created_at": int(child.stat().st_mtime)})
            return jsonify({"ok": True, "backups": backups})

        if path == "backup-guard/recommendation":
            return jsonify({"ok": True, "recommendation": "Create a backup before large coordinator updates."})

        if path in ["backup-guard/create", "backup-guard/auto-run"]:
            return jsonify({"ok": True, "created": False, "message": "Use the dashboard Backup Manager for local file backups."})

        if path == "capacity-forecast":
            return jsonify({"ok": True, "plans": [], "workers": worker_scores(conn)})

        if path == "capacity-forecast/export":
            return jsonify({"ok": True, "exported": False, "message": "No forecast data to export."})

        if path == "capacity-forecast/reports":
            return jsonify({"ok": True, "reports": []})

        if path == "rl-architecture/status":
            return jsonify({"ok": True, "enabled": False, "episodes": 0, "message": "Compatibility RL panel is available."})

        if path in ["rl-architecture/run-episode", "rl-architecture/train-q"]:
            record_ml_event(conn, path.upper().replace("/", "_"), requester, "info", "Compatibility RL run skipped execution")
            return jsonify({"ok": True, "episodes": [], "message": "No RL training executed by compatibility route."})

        if path == "rl-architecture/behavior-dataset":
            return jsonify({"ok": True, "samples": []})

        if path == "rl-architecture/export":
            return jsonify({"ok": True, "exported": False, "message": "No RL report data to export."})

        return jsonify({"ok": True, "path": path, "message": "Compatibility route available."})
    finally:
        conn.close()



# ============================================================
# EASY VERSION STATUS ROUTE
# ============================================================

@app.route("/api/sync/file-status", methods=["GET"])
def easy_version_file_status():
    import hashlib
    base = os.path.dirname(os.path.abspath(__file__))

    files = [
        "coordinator_server.py",
        "start_dashboard.py",
        "mobile_worker.py",
        "sync_updates_to_main.py",
        "ui/app.js",
        "ui/style.css",
        "ui/index.html",
    ]

    def sha(path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    rows = []
    for rel in files:
        path = os.path.join(base, rel.replace("/", os.sep))
        item = {
            "path": rel,
            "exists": os.path.isfile(path),
            "sha256": "",
            "size_bytes": 0,
            "modified": 0
        }
        if item["exists"]:
            try:
                st = os.stat(path)
                item["size_bytes"] = st.st_size
                item["modified"] = int(st.st_mtime)
                item["sha256"] = sha(path)
            except Exception as e:
                item["error"] = str(e)
        rows.append(item)

    return jsonify({"ok": True, "files": rows, "time": int(time.time())})

if __name__ == "__main__":
    init_db()

    print("[Coordinator] Starting central profile coordinator")
    print("[Coordinator] Listening on: http://0.0.0.0:9555")
    print("[Coordinator] DB:", DB_PATH)

    app.run(host="0.0.0.0", port=9555, debug=False, threaded=True)
