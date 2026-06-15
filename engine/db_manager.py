import sqlite3
import os
import traceback
import json
import csv
import io
import base64
import ctypes
import urllib.parse
from datetime import datetime


# Revenue projection constants are deliberately stored as editable local defaults.
# These are NOT guaranteed payouts. They are dashboard projection ranges only.
DEFAULT_PLATFORM_REVENUE_MODELS = {
    "youtube": {
        "display_name": "YouTube",
        "metric": "view_or_ad_event",
        "payout_min": 0.0012,
        "payout_avg": 0.0035,
        "payout_max": 0.0080,
        "condition": "Use only for counted view/ad events; RPM varies by geography, niche, and ad inventory.",
        "notes": "Projection only. Real revenue must be reconciled with YouTube Studio revenue reports."
    },
    "twitch_ads": {
        "display_name": "Twitch Ads",
        "metric": "ad_impression",
        "payout_min": 0.0020,
        "payout_avg": 0.0050,
        "payout_max": 0.0100,
        "condition": "Use only when an ad impression is actually detected/completed.",
        "notes": "A live view does not automatically mean an ad impression."
    },
    "twitch_bits": {
        "display_name": "Twitch Bits",
        "metric": "bit",
        "payout_min": 0.0100,
        "payout_avg": 0.0100,
        "payout_max": 0.0100,
        "condition": "Use only for recorded Bits/Cheer events.",
        "notes": "Twitch states creators receive one cent per Bit used to Cheer."
    },
    "twitch_subs": {
        "display_name": "Twitch Subs",
        "metric": "tier_1_sub",
        "payout_min": 2.5000,
        "payout_avg": 2.5000,
        "payout_max": 3.5000,
        "condition": "Use only for a real subscription event.",
        "notes": "Default assumes standard Tier 1 split; high-volume deals may vary."
    },
    "spotify": {
        "display_name": "Spotify",
        "metric": "counted_stream",
        "payout_min": 0.0030,
        "payout_avg": 0.0040,
        "payout_max": 0.0050,
        "condition": "duration_seconds >= 30 OR event_type is STREAM_COUNTED/TRACK_30S_REACHED",
        "notes": "Spotify uses streamshare, not a fixed per-stream rate; this is an estimate only."
    },
    "deezer": {
        "display_name": "Deezer",
        "metric": "counted_stream",
        "payout_min": 0.0040,
        "payout_avg": 0.0048,
        "payout_max": 0.0056,
        "condition": "duration_seconds >= 30 OR event_type is STREAM_COUNTED/TRACK_30S_REACHED",
        "notes": "Projection only; Deezer uses an artist-centric payment model in supported markets."
    }
}


class DatabaseManager:
    def __init__(self):
        # Ensure the database folder exists
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.db_folder = os.path.join(base_dir, "database")
        os.makedirs(self.db_folder, exist_ok=True)

        self.db_path = os.path.join(self.db_folder, "fleet.db")
        self._initialize_tables()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _column_exists(self, cursor, table_name, column_name):
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]
        return column_name in columns

    def _add_column_if_missing(self, cursor, table_name, column_name, column_sql):
        if not self._column_exists(cursor, table_name, column_name):
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")
            print(f"[Database] ✅ Added missing column: {table_name}.{column_name}")

    def _initialize_tables(self):
        """Creates and repairs the master tables if needed."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    status TEXT DEFAULT 'OFFLINE',
                    target_platform TEXT DEFAULT 'None',
                    hardware_cloak TEXT,
                    last_ip TEXT DEFAULT 'Unknown',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Repair older existing databases that may be missing newer columns.
            self._add_column_if_missing(cursor, "profiles", "status", "TEXT DEFAULT 'OFFLINE'")
            self._add_column_if_missing(cursor, "profiles", "target_platform", "TEXT DEFAULT 'None'")
            self._add_column_if_missing(cursor, "profiles", "hardware_cloak", "TEXT")
            self._add_column_if_missing(cursor, "profiles", "hardware_profile_json", "TEXT DEFAULT ''")
            self._add_column_if_missing(cursor, "profiles", "last_ip", "TEXT DEFAULT 'Unknown'")
            self._add_column_if_missing(cursor, "profiles", "created_at", "TEXT")

            # Automatic Profile Quarantine support.
            # Quarantine does NOT delete profiles.
            # It only excludes weak/bad profiles from normal START ALL launches.
            self._add_column_if_missing(cursor, "profiles", "quarantined", "INTEGER DEFAULT 0")
            self._add_column_if_missing(cursor, "profiles", "quarantine_score", "INTEGER DEFAULT 100")
            self._add_column_if_missing(cursor, "profiles", "quarantine_reason", "TEXT DEFAULT ''")
            self._add_column_if_missing(cursor, "profiles", "quarantine_source", "TEXT DEFAULT ''")
            self._add_column_if_missing(cursor, "profiles", "quarantined_at", "TIMESTAMP")

            # IP Alignment region config columns — store per-profile expected region.
            self._add_column_if_missing(cursor, "profiles", "expected_country", "TEXT DEFAULT ''")
            self._add_column_if_missing(cursor, "profiles", "expected_timezone", "TEXT DEFAULT ''")
            self._add_column_if_missing(cursor, "profiles", "expected_language", "TEXT DEFAULT ''")
            self._add_column_if_missing(cursor, "profiles", "expected_dns_region", "TEXT DEFAULT ''")
            self._add_column_if_missing(cursor, "profiles", "alignment_strict", "INTEGER DEFAULT 0")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS financials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER,
                    platform TEXT,
                    ads_watched INTEGER DEFAULT 0,
                    estimated_revenue REAL DEFAULT 0.0,
                    log_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id)
                )
            """)


            cursor.execute("""
                CREATE TABLE IF NOT EXISTS profile_sessions (
                    session_id TEXT PRIMARY KEY,
                    pc_id TEXT,
                    profile_id INTEGER,
                    platform TEXT,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP,
                    duration_seconds INTEGER DEFAULT 0,
                    starting_ip TEXT,
                    final_ip TEXT,
                    ip_status TEXT DEFAULT 'UNKNOWN',
                    status TEXT DEFAULT 'RUNNING',
                    close_reason TEXT DEFAULT '',
                    estimated_revenue REAL DEFAULT 0.0
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS analytics_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    pc_id TEXT,
                    profile_id INTEGER,
                    session_id TEXT,
                    platform TEXT,
                    ip_address TEXT,
                    ip_label TEXT,
                    ip_status TEXT DEFAULT 'UNKNOWN',
                    event_type TEXT NOT NULL,
                    event_value REAL DEFAULT 0.0,
                    estimated_value REAL DEFAULT 0.0,
                    details TEXT DEFAULT ''
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ip_reputation (
                    ip_address TEXT PRIMARY KEY,
                    ip_label TEXT,
                    country TEXT DEFAULT '',
                    city TEXT DEFAULT '',
                    provider TEXT DEFAULT '',
                    status TEXT DEFAULT 'UNKNOWN',
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_profiles INTEGER DEFAULT 0,
                    total_sessions INTEGER DEFAULT 0,
                    total_ads_detected INTEGER DEFAULT 0,
                    total_failures INTEGER DEFAULT 0,
                    estimated_revenue REAL DEFAULT 0.0,
                    good_for_youtube INTEGER DEFAULT 0,
                    good_for_twitch INTEGER DEFAULT 0,
                    good_for_spotify INTEGER DEFAULT 0,
                    good_for_deezer INTEGER DEFAULT 0,
                    bad_for_youtube INTEGER DEFAULT 0,
                    bad_for_twitch INTEGER DEFAULT 0,
                    bad_for_spotify INTEGER DEFAULT 0,
                    bad_for_deezer INTEGER DEFAULT 0,
                    blacklisted INTEGER DEFAULT 0,
                    blacklisted_at TIMESTAMP,
                    blacklist_reason TEXT DEFAULT '',
                    manually_blacklisted INTEGER DEFAULT 0,
                    notes TEXT DEFAULT ''
                )
            """)

            # Repair existing ip_reputation tables created before blacklist support.
            self._add_column_if_missing(cursor, "ip_reputation", "blacklisted", "INTEGER DEFAULT 0")
            self._add_column_if_missing(cursor, "ip_reputation", "blacklisted_at", "TIMESTAMP")
            self._add_column_if_missing(cursor, "ip_reputation", "blacklist_reason", "TEXT DEFAULT ''")
            self._add_column_if_missing(cursor, "ip_reputation", "manually_blacklisted", "INTEGER DEFAULT 0")
            # Revenue projection columns for min / average / max estimates.
            self._add_column_if_missing(cursor, "analytics_events", "estimated_min", "REAL DEFAULT 0.0")
            self._add_column_if_missing(cursor, "analytics_events", "estimated_avg", "REAL DEFAULT 0.0")
            self._add_column_if_missing(cursor, "analytics_events", "estimated_max", "REAL DEFAULT 0.0")
            self._add_column_if_missing(cursor, "analytics_events", "metric_count", "REAL DEFAULT 0.0")
            self._add_column_if_missing(cursor, "analytics_events", "duration_seconds", "INTEGER DEFAULT 0")
            self._add_column_if_missing(cursor, "analytics_events", "revenue_model_key", "TEXT DEFAULT ''")

            self._add_column_if_missing(cursor, "ip_reputation", "estimated_revenue_min", "REAL DEFAULT 0.0")
            self._add_column_if_missing(cursor, "ip_reputation", "estimated_revenue_avg", "REAL DEFAULT 0.0")
            self._add_column_if_missing(cursor, "ip_reputation", "estimated_revenue_max", "REAL DEFAULT 0.0")

            self._add_column_if_missing(cursor, "profile_sessions", "estimated_revenue_min", "REAL DEFAULT 0.0")
            self._add_column_if_missing(cursor, "profile_sessions", "estimated_revenue_avg", "REAL DEFAULT 0.0")
            self._add_column_if_missing(cursor, "profile_sessions", "estimated_revenue_max", "REAL DEFAULT 0.0")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS proton_vpn_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label TEXT DEFAULT '',
                    username TEXT UNIQUE NOT NULL,
                    password_secret TEXT DEFAULT '',
                    max_profiles INTEGER DEFAULT 4,
                    active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS profile_proton_assignments (
                    profile_id INTEGER PRIMARY KEY,
                    account_id INTEGER NOT NULL,
                    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id),
                    FOREIGN KEY(account_id) REFERENCES proton_vpn_accounts(id)
                )
            """)

            # Patch 006: Proton Ready Launch Guard support.
            # These columns track whether a profile has completed manual Proton setup.
            self._add_column_if_missing(cursor, "profile_proton_assignments", "setup_status", "TEXT DEFAULT 'NEEDS_LOGIN'")
            self._add_column_if_missing(cursor, "profile_proton_assignments", "setup_notes", "TEXT DEFAULT ''")
            self._add_column_if_missing(cursor, "profile_proton_assignments", "setup_source", "TEXT DEFAULT ''")
            self._add_column_if_missing(cursor, "profile_proton_assignments", "setup_updated_at", "TIMESTAMP")
            self._add_column_if_missing(cursor, "profile_proton_assignments", "setup_verified_at", "TIMESTAMP")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS platform_targets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT DEFAULT '',
                    identifier TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    priority INTEGER DEFAULT 5,
                    enabled INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            self._add_column_if_missing(cursor, "platform_targets", "platform", "TEXT DEFAULT ''")
            self._add_column_if_missing(cursor, "platform_targets", "target_type", "TEXT DEFAULT ''")
            self._add_column_if_missing(cursor, "platform_targets", "title", "TEXT DEFAULT ''")
            self._add_column_if_missing(cursor, "platform_targets", "url", "TEXT DEFAULT ''")
            self._add_column_if_missing(cursor, "platform_targets", "identifier", "TEXT DEFAULT ''")
            self._add_column_if_missing(cursor, "platform_targets", "notes", "TEXT DEFAULT ''")
            self._add_column_if_missing(cursor, "platform_targets", "priority", "INTEGER DEFAULT 5")
            self._add_column_if_missing(cursor, "platform_targets", "enabled", "INTEGER DEFAULT 1")
            self._add_column_if_missing(cursor, "platform_targets", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            self._add_column_if_missing(cursor, "platform_targets", "updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_platform_targets_platform_enabled
                ON platform_targets(platform, enabled, priority)
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS safe_route_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    source TEXT DEFAULT 'safe_route_plan',
                    active_platforms_json TEXT DEFAULT '[]',
                    profile_count INTEGER DEFAULT 0,
                    platforms_per_profile INTEGER DEFAULT 0,
                    plan_json TEXT DEFAULT '{}',
                    summary_json TEXT DEFAULT '{}'
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_safe_route_plans_created_at
                ON safe_route_plans(created_at)
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT DEFAULT '{}',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ml_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    source TEXT DEFAULT '',
                    event_type TEXT DEFAULT '',
                    profile_id INTEGER,
                    session_id TEXT DEFAULT '',
                    action TEXT DEFAULT '',
                    action_result TEXT DEFAULT '',
                    reward REAL DEFAULT 0.0,
                    cpu_percent REAL DEFAULT 0.0,
                    ram_percent REAL DEFAULT 0.0,
                    gpu_percent REAL DEFAULT 0.0,
                    active_profiles INTEGER DEFAULT 0,
                    target_profiles INTEGER DEFAULT 0,
                    details_json TEXT DEFAULT '{}'
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ml_observations_created_at
                ON ml_observations(created_at)
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS autoscale_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    source TEXT DEFAULT '',
                    mode TEXT DEFAULT 'manual',
                    enabled INTEGER DEFAULT 0,
                    action TEXT DEFAULT 'hold',
                    reason TEXT DEFAULT '',
                    active_profiles INTEGER DEFAULT 0,
                    desired_profiles INTEGER DEFAULT 0,
                    safe_limit INTEGER DEFAULT 0,
                    cpu_percent REAL DEFAULT 0.0,
                    ram_percent REAL DEFAULT 0.0,
                    gpu_percent REAL DEFAULT 0.0,
                    launch_ids_json TEXT DEFAULT '[]',
                    close_ids_json TEXT DEFAULT '[]',
                    details_json TEXT DEFAULT '{}'
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_autoscale_events_created_at
                ON autoscale_events(created_at)
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS profile_lifecycle_state (
                    profile_id INTEGER PRIMARY KEY,
                    session_id TEXT DEFAULT '',
                    state TEXT DEFAULT 'OFFLINE',
                    status TEXT DEFAULT '',
                    stage TEXT DEFAULT '',
                    target_platform TEXT DEFAULT '',
                    ip_address TEXT DEFAULT '',
                    source TEXT DEFAULT '',
                    severity TEXT DEFAULT 'info',
                    entered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    details_json TEXT DEFAULT '{}'
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS profile_lifecycle_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    profile_id INTEGER,
                    session_id TEXT DEFAULT '',
                    state TEXT DEFAULT '',
                    status TEXT DEFAULT '',
                    stage TEXT DEFAULT '',
                    target_platform TEXT DEFAULT '',
                    ip_address TEXT DEFAULT '',
                    source TEXT DEFAULT '',
                    severity TEXT DEFAULT 'info',
                    elapsed_seconds INTEGER DEFAULT 0,
                    details_json TEXT DEFAULT '{}'
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_profile_lifecycle_events_created_at
                ON profile_lifecycle_events(created_at)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_profile_lifecycle_events_profile
                ON profile_lifecycle_events(profile_id, created_at)
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS platform_revenue_models (
                    platform_key TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    payout_min REAL DEFAULT 0.0,
                    payout_avg REAL DEFAULT 0.0,
                    payout_max REAL DEFAULT 0.0,
                    condition TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    enabled INTEGER DEFAULT 1,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            for platform_key, model in DEFAULT_PLATFORM_REVENUE_MODELS.items():
                cursor.execute("""
                    INSERT OR IGNORE INTO platform_revenue_models (
                        platform_key,
                        display_name,
                        metric,
                        payout_min,
                        payout_avg,
                        payout_max,
                        condition,
                        notes,
                        enabled
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    platform_key,
                    model.get("display_name", platform_key),
                    model.get("metric", "event"),
                    float(model.get("payout_min", 0.0)),
                    float(model.get("payout_avg", 0.0)),
                    float(model.get("payout_max", 0.0)),
                    model.get("condition", ""),
                    model.get("notes", "")
                ))

            conn.commit()

    def create_profile(self, name, hardware_cloak, hardware_profile_json="", rebalance_proton=True):
        """Generates a new, permanently unique profile."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO profiles (name, hardware_cloak, hardware_profile_json) VALUES (?, ?, ?)",
                    (name, hardware_cloak, hardware_profile_json or "")
                )
                conn.commit()
                profile_id = cursor.lastrowid

            if rebalance_proton:
                self.rebalance_proton_profile_assignments()
            return profile_id

        except sqlite3.IntegrityError:
            print(f"[Database] ⚠️ Profile already exists: {name}")
            return None

        except Exception as e:
            print(f"[Database] ❌ Error creating profile {name}: {e}")
            return None

    def update_profile_hardware(self, profile_id, hardware_cloak, hardware_profile_json=""):
        """Updates the saved device identity for an existing profile."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE profiles
                    SET hardware_cloak = ?,
                        hardware_profile_json = ?
                    WHERE id = ?
                    """,
                    (hardware_cloak, hardware_profile_json or "", int(profile_id))
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"[Database] ❌ Error updating hardware profile {profile_id}: {e}")
            return False

    # ==============================
    # Proton VPN Account Vault
    # ==============================

    class _DataBlob(ctypes.Structure):
        _fields_ = [
            ("cbData", ctypes.c_ulong),
            ("pbData", ctypes.POINTER(ctypes.c_byte)),
        ]

    def _protect_secret(self, value):
        value = str(value or "")
        if not value:
            return ""

        if os.name != "nt":
            return "plain:" + base64.b64encode(value.encode("utf-8")).decode("ascii")

        try:
            raw = value.encode("utf-8")
            in_buffer = ctypes.create_string_buffer(raw)
            in_blob = self._DataBlob(
                len(raw),
                ctypes.cast(in_buffer, ctypes.POINTER(ctypes.c_byte))
            )
            out_blob = self._DataBlob()

            crypt32 = ctypes.windll.crypt32
            kernel32 = ctypes.windll.kernel32

            ok = crypt32.CryptProtectData(
                ctypes.byref(in_blob),
                "Comet Fleet Proton Account",
                None,
                None,
                None,
                0,
                ctypes.byref(out_blob)
            )
            if not ok:
                raise ctypes.WinError()

            try:
                protected = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            finally:
                kernel32.LocalFree(out_blob.pbData)

            return "dpapi:" + base64.b64encode(protected).decode("ascii")
        except Exception as e:
            print(f"[ProtonVault] DPAPI encrypt failed: {e}")
            return ""

    def _unprotect_secret(self, value):
        value = str(value or "")
        if not value:
            return ""

        if value.startswith("plain:"):
            try:
                return base64.b64decode(value.split(":", 1)[1]).decode("utf-8")
            except Exception:
                return ""

        if not value.startswith("dpapi:") or os.name != "nt":
            return ""

        try:
            protected = base64.b64decode(value.split(":", 1)[1])
            in_buffer = ctypes.create_string_buffer(protected)
            in_blob = self._DataBlob(
                len(protected),
                ctypes.cast(in_buffer, ctypes.POINTER(ctypes.c_byte))
            )
            out_blob = self._DataBlob()

            crypt32 = ctypes.windll.crypt32
            kernel32 = ctypes.windll.kernel32

            ok = crypt32.CryptUnprotectData(
                ctypes.byref(in_blob),
                None,
                None,
                None,
                None,
                0,
                ctypes.byref(out_blob)
            )
            if not ok:
                raise ctypes.WinError()

            try:
                raw = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            finally:
                kernel32.LocalFree(out_blob.pbData)

            return raw.decode("utf-8")
        except Exception as e:
            print(f"[ProtonVault] DPAPI decrypt failed: {e}")
            return ""

    def _parse_proton_account_text(self, text):
        def clean(value):
            return str(value or "").strip()

        def split_inline_account(line):
            line = clean(line)
            if not line:
                return None

            if "," in line:
                try:
                    row = next(csv.reader(io.StringIO(line)))
                    row = [clean(cell) for cell in row]
                    if len(row) >= 2 and row[0] and row[1]:
                        return row
                except Exception:
                    pass

            for separator in (":", "|", ";"):
                if separator in line:
                    row = [clean(part) for part in line.split(separator)]
                    if len(row) >= 2 and row[0] and row[1]:
                        return row

            return None

        def looks_like_username(value):
            value = clean(value)
            if not value:
                return False
            if any(char.isspace() for char in value):
                return False
            if value.lower() in {"email", "username", "user", "login", "account"}:
                return False
            return True

        def add_account(username, password, label=None):
            username = clean(username)
            password = clean(password)
            label = clean(label) or username

            if not username or not password:
                return
            if username.lower() in {"email", "username", "user", "login", "account"}:
                return
            if password.lower() in {"password", "pass"}:
                return

            accounts.append({
                "username": username,
                "password": password,
                "label": label
            })

        accounts = []
        lines = [
            clean(raw_line)
            for raw_line in str(text or "").splitlines()
            if clean(raw_line) and not clean(raw_line).startswith("#")
        ]

        index = 0
        while index < len(lines):
            line = lines[index]
            row = split_inline_account(line)

            if row:
                add_account(
                    username=row[0],
                    password=row[1],
                    label=row[2] if len(row) > 2 else row[0]
                )
                index += 1
                continue

            if looks_like_username(line) and index + 1 < len(lines):
                password_line = lines[index + 1]
                add_account(
                    username=line,
                    password=password_line,
                    label=line
                )
                index += 2
                continue

            index += 1

        return accounts

    def import_proton_accounts(self, text, max_profiles=4):
        max_profiles = max(1, int(max_profiles or 4))
        accounts = self._parse_proton_account_text(text)

        imported = 0
        updated = 0
        skipped = 0

        with self._get_connection() as conn:
            cursor = conn.cursor()

            for account in accounts:
                secret = self._protect_secret(account["password"])
                if not secret:
                    skipped += 1
                    continue

                existing = cursor.execute(
                    "SELECT id FROM proton_vpn_accounts WHERE username = ?",
                    (account["username"],)
                ).fetchone()

                if existing:
                    cursor.execute(
                        """
                        UPDATE proton_vpn_accounts
                        SET label = ?,
                            password_secret = ?,
                            max_profiles = ?,
                            active = 1,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE username = ?
                        """,
                        (account["label"], secret, max_profiles, account["username"])
                    )
                    updated += 1
                else:
                    cursor.execute(
                        """
                        INSERT INTO proton_vpn_accounts (label, username, password_secret, max_profiles, active)
                        VALUES (?, ?, ?, ?, 1)
                        """,
                        (account["label"], account["username"], secret, max_profiles)
                    )
                    imported += 1

            conn.commit()

        assignment = self.rebalance_proton_profile_assignments(max_profiles=max_profiles)

        return {
            "ok": True,
            "parsed": len(accounts),
            "imported": imported,
            "updated": updated,
            "skipped": skipped,
            "max_profiles": max_profiles,
            "assignment": assignment
        }

    def rebalance_proton_profile_assignments(self, max_profiles=None):
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                accounts = [dict(row) for row in cursor.execute(
                    """
                    SELECT id, username, max_profiles
                    FROM proton_vpn_accounts
                    WHERE active = 1
                    ORDER BY id ASC
                    """
                ).fetchall()]
                profiles = [dict(row) for row in cursor.execute(
                    "SELECT id FROM profiles ORDER BY id ASC"
                ).fetchall()]

                cursor.execute("DELETE FROM profile_proton_assignments")

                assigned = 0
                unassigned = 0
                for index, profile in enumerate(profiles):
                    if not accounts:
                        unassigned += 1
                        continue

                    account_index = None
                    running_index = 0
                    for idx, account in enumerate(accounts):
                        cap = max(1, int(max_profiles or account.get("max_profiles") or 4))
                        if index < running_index + cap:
                            account_index = idx
                            break
                        running_index += cap

                    if account_index is None:
                        unassigned += 1
                        continue

                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO profile_proton_assignments (profile_id, account_id, assigned_at)
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                        """,
                        (int(profile["id"]), int(accounts[account_index]["id"]))
                    )
                    assigned += 1

                conn.commit()

            return {
                "ok": True,
                "assigned": assigned,
                "unassigned": unassigned,
                "accounts": len(accounts),
                "profiles": len(profiles)
            }
        except Exception as e:
            print(f"[ProtonVault] Rebalance failed: {e}")
            return {"ok": False, "error": str(e), "assigned": 0, "unassigned": 0}

    # ==============================
    # Patch 006: Proton Ready Launch Guard
    # ==============================

    def _ensure_proton_readiness_schema(self, conn=None):
        """Repairs Proton assignment readiness columns if an older DB is opened."""
        close_conn = False
        if conn is None:
            conn = self._get_connection()
            close_conn = True

        try:
            cursor = conn.cursor()
            self._add_column_if_missing(cursor, "profile_proton_assignments", "setup_status", "TEXT DEFAULT 'NEEDS_LOGIN'")
            self._add_column_if_missing(cursor, "profile_proton_assignments", "setup_notes", "TEXT DEFAULT ''")
            self._add_column_if_missing(cursor, "profile_proton_assignments", "setup_source", "TEXT DEFAULT ''")
            self._add_column_if_missing(cursor, "profile_proton_assignments", "setup_updated_at", "TIMESTAMP")
            self._add_column_if_missing(cursor, "profile_proton_assignments", "setup_verified_at", "TIMESTAMP")
            conn.commit()
        finally:
            if close_conn:
                conn.close()

    def _normalize_proton_setup_status(self, value):
        status = str(value or "").strip().upper().replace(" ", "_")
        aliases = {
            "READY": "READY",
            "PROTON_READY": "READY",
            "OK": "READY",
            "DONE": "READY",
            "NEEDS_LOGIN": "NEEDS_LOGIN",
            "LOGIN_REQUIRED": "NEEDS_LOGIN",
            "NOT_READY": "NEEDS_LOGIN",
            "SETUP_OPENED": "SETUP_OPENED",
            "OPENED": "SETUP_OPENED",
            "IN_PROGRESS": "SETUP_OPENED",
            "BLOCKED": "BLOCKED",
            "DISABLED": "BLOCKED",
            "BAD": "BLOCKED",
        }
        return aliases.get(status, "NEEDS_LOGIN")

    def _mask_proton_username(self, username):
        username = str(username or "").strip()
        if not username:
            return ""
        if "@" in username:
            left, right = username.split("@", 1)
            if len(left) <= 2:
                return left[:1] + "***@" + right
            return left[:2] + "***@" + right
        if len(username) <= 4:
            return username[:1] + "***"
        return username[:2] + "***" + username[-2:]

    def _get_proton_assignment_map(self, conn=None):
        """Returns Proton assignment/readiness by profile_id without exposing passwords."""
        close_conn = False
        if conn is None:
            conn = self._get_connection()
            close_conn = True

        try:
            conn.row_factory = sqlite3.Row
            self._ensure_proton_readiness_schema(conn)
            rows = conn.execute(
                """
                SELECT
                    pa.profile_id,
                    pa.account_id,
                    COALESCE(pa.setup_status, 'NEEDS_LOGIN') AS setup_status,
                    COALESCE(pa.setup_notes, '') AS setup_notes,
                    COALESCE(pa.setup_source, '') AS setup_source,
                    pa.setup_updated_at,
                    pa.setup_verified_at,
                    a.label,
                    a.username,
                    a.max_profiles,
                    a.active
                FROM profile_proton_assignments pa
                LEFT JOIN proton_vpn_accounts a ON a.id = pa.account_id
                """
            ).fetchall()

            out = {}
            for row in rows:
                data = dict(row)
                try:
                    pid = int(data.get("profile_id"))
                except Exception:
                    continue
                out[pid] = data
            return out

        except Exception as e:
            print(f"[ProtonReady] Could not read assignment map: {e}")
            return {}
        finally:
            if close_conn:
                conn.close()

    def _apply_proton_profile_fields(self, row, proton_data=None):
        """Adds UI/Launch Guard Proton readiness fields to one profile dict."""
        proton_data = proton_data or {}
        assigned = bool(proton_data.get("account_id"))
        active = bool(proton_data.get("active", 1)) if assigned else False
        setup_status = self._normalize_proton_setup_status(proton_data.get("setup_status") or "NEEDS_LOGIN")
        ready = bool(assigned and active and setup_status == "READY")

        if not assigned:
            reason = "No Proton account assigned"
        elif not active:
            reason = "Assigned Proton account is inactive"
        elif setup_status == "BLOCKED":
            reason = "Proton setup is blocked"
        elif setup_status == "SETUP_OPENED":
            reason = "Proton setup was opened but not marked READY"
        elif setup_status != "READY":
            reason = "Proton login/setup not marked READY"
        else:
            reason = ""

        row["proton_account_id"] = proton_data.get("account_id")
        row["proton_account_label"] = proton_data.get("label") or proton_data.get("username") or ""
        row["proton_username"] = self._mask_proton_username(proton_data.get("username") or "")
        row["proton_assigned"] = assigned
        row["proton_account_active"] = active
        row["proton_setup_status"] = setup_status
        row["proton_setup_notes"] = proton_data.get("setup_notes") or ""
        row["proton_setup_source"] = proton_data.get("setup_source") or ""
        row["proton_setup_updated_at"] = proton_data.get("setup_updated_at") or ""
        row["proton_setup_verified_at"] = proton_data.get("setup_verified_at") or ""
        row["proton_ready"] = ready
        row["proton_launch_ready"] = ready
        row["proton_launch_block_reason"] = reason
        return row

    def set_profile_proton_setup_status(self, profile_id, setup_status, notes="", source="manual"):
        """Marks one profile as READY / NEEDS_LOGIN / SETUP_OPENED / BLOCKED."""
        try:
            profile_id = int(profile_id)
            setup_status = self._normalize_proton_setup_status(setup_status)
            notes = str(notes or "").strip()
            source = str(source or "manual").strip() or "manual"

            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                self._ensure_proton_readiness_schema(conn)

                assignment = conn.execute(
                    "SELECT profile_id, account_id FROM profile_proton_assignments WHERE profile_id = ?",
                    (profile_id,)
                ).fetchone()

                if not assignment:
                    return {
                        "ok": False,
                        "profile_id": profile_id,
                        "error": "No Proton account assigned to this profile. Import/rebalance accounts first."
                    }

                verified_sql = "CURRENT_TIMESTAMP" if setup_status == "READY" else "NULL"
                conn.execute(
                    f"""
                    UPDATE profile_proton_assignments
                    SET setup_status = ?,
                        setup_notes = ?,
                        setup_source = ?,
                        setup_updated_at = CURRENT_TIMESTAMP,
                        setup_verified_at = {verified_sql}
                    WHERE profile_id = ?
                    """,
                    (setup_status, notes, source, profile_id)
                )
                conn.commit()

            return {
                "ok": True,
                "profile_id": profile_id,
                "setup_status": setup_status,
                "status": setup_status,
                "message": f"Profile {profile_id} Proton status set to {setup_status}."
            }

        except Exception as e:
            return {"ok": False, "profile_id": profile_id, "error": str(e)}

    def get_proton_profile_readiness(self):
        """Returns profile-level Proton readiness for the PC Control panel."""
        try:
            profiles = self.get_all_profiles()
            rows = []
            ready_count = 0
            assigned_count = 0
            blocked_count = 0
            needs_login_count = 0
            setup_opened_count = 0
            unassigned_count = 0

            for p in profiles:
                status = p.get("proton_setup_status") or "NEEDS_LOGIN"
                if p.get("proton_assigned"):
                    assigned_count += 1
                else:
                    unassigned_count += 1

                if p.get("proton_launch_ready"):
                    ready_count += 1
                elif status == "BLOCKED":
                    blocked_count += 1
                elif status == "SETUP_OPENED":
                    setup_opened_count += 1
                else:
                    needs_login_count += 1

                rows.append({
                    "profile_id": p.get("id"),
                    "profile_name": p.get("name") or f"Profile {p.get('id')}",
                    "profile_status": p.get("status") or "OFFLINE",
                    "account_id": p.get("proton_account_id"),
                    "account_label": p.get("proton_account_label") or "",
                    "username": p.get("proton_username") or "",
                    "assigned": bool(p.get("proton_assigned")),
                    "setup_status": status,
                    "ready": bool(p.get("proton_launch_ready")),
                    "launch_ready": bool(p.get("proton_launch_ready")),
                    "block_reason": p.get("proton_launch_block_reason") or "",
                    "updated_at": p.get("proton_setup_updated_at") or "",
                    "verified_at": p.get("proton_setup_verified_at") or "",
                    "notes": p.get("proton_setup_notes") or ""
                })

            return {
                "ok": True,
                "profiles": rows,
                "summary": {
                    "total_profiles": len(rows),
                    "assigned_profiles": assigned_count,
                    "unassigned_profiles": unassigned_count,
                    "ready_profiles": ready_count,
                    "needs_login_profiles": needs_login_count,
                    "setup_opened_profiles": setup_opened_count,
                    "blocked_profiles": blocked_count,
                    "launch_guard_enabled": True
                }
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "profiles": [], "summary": {}}

    def get_proton_account_status(self):
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                self._ensure_proton_readiness_schema(conn)

                accounts = [dict(row) for row in conn.execute(
                    """
                    SELECT
                        a.id,
                        a.label,
                        a.username,
                        a.max_profiles,
                        a.active,
                        COUNT(pa.profile_id) AS assigned_count,
                        GROUP_CONCAT(pa.profile_id, ', ') AS profile_ids,
                        SUM(CASE WHEN COALESCE(pa.setup_status, 'NEEDS_LOGIN') = 'READY' THEN 1 ELSE 0 END) AS ready_count,
                        SUM(CASE WHEN COALESCE(pa.setup_status, 'NEEDS_LOGIN') = 'BLOCKED' THEN 1 ELSE 0 END) AS blocked_count,
                        SUM(CASE WHEN COALESCE(pa.setup_status, 'NEEDS_LOGIN') NOT IN ('READY', 'BLOCKED') THEN 1 ELSE 0 END) AS needs_login_count
                    FROM proton_vpn_accounts a
                    LEFT JOIN profile_proton_assignments pa ON pa.account_id = a.id
                    GROUP BY a.id
                    ORDER BY a.id ASC
                    """
                ).fetchall()]

                total_profiles = conn.execute("SELECT COUNT(*) AS c FROM profiles").fetchone()["c"]
                assigned_profiles = conn.execute("SELECT COUNT(*) AS c FROM profile_proton_assignments").fetchone()["c"]
                ready_profiles = conn.execute(
                    "SELECT COUNT(*) AS c FROM profile_proton_assignments WHERE COALESCE(setup_status, 'NEEDS_LOGIN') = 'READY'"
                ).fetchone()["c"]
                blocked_profiles = conn.execute(
                    "SELECT COUNT(*) AS c FROM profile_proton_assignments WHERE COALESCE(setup_status, 'NEEDS_LOGIN') = 'BLOCKED'"
                ).fetchone()["c"]

            clean_accounts = []
            for account in accounts:
                clean_accounts.append({
                    "id": account.get("id"),
                    "label": account.get("label") or account.get("username"),
                    "username": self._mask_proton_username(account.get("username") or ""),
                    "max_profiles": int(account.get("max_profiles") or 4),
                    "active": bool(account.get("active")),
                    "assigned_count": int(account.get("assigned_count") or 0),
                    "ready_count": int(account.get("ready_count") or 0),
                    "needs_login_count": int(account.get("needs_login_count") or 0),
                    "blocked_count": int(account.get("blocked_count") or 0),
                    "profile_ids": account.get("profile_ids") or ""
                })

            readiness = self.get_proton_profile_readiness()
            readiness_summary = readiness.get("summary", {}) if readiness.get("ok") else {}

            return {
                "ok": True,
                "accounts": clean_accounts,
                "profile_readiness": readiness.get("profiles", []) if readiness.get("ok") else [],
                "summary": {
                    "account_count": len(clean_accounts),
                    "total_profiles": int(total_profiles or 0),
                    "assigned_profiles": int(assigned_profiles or 0),
                    "unassigned_profiles": max(0, int(total_profiles or 0) - int(assigned_profiles or 0)),
                    "ready_profiles": int(ready_profiles or 0),
                    "needs_login_profiles": int(readiness_summary.get("needs_login_profiles") or 0),
                    "setup_opened_profiles": int(readiness_summary.get("setup_opened_profiles") or 0),
                    "blocked_profiles": int(blocked_profiles or 0),
                    "launch_guard_enabled": True
                }
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "accounts": [], "profile_readiness": [], "summary": {}}

    def get_proton_credentials_for_profile(self, profile_id):
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT a.id, a.label, a.username, a.password_secret
                    FROM profile_proton_assignments pa
                    JOIN proton_vpn_accounts a ON a.id = pa.account_id
                    WHERE pa.profile_id = ?
                    """,
                    (int(profile_id),)
                ).fetchone()

            if not row:
                return None

            data = dict(row)
            return {
                "account_id": data.get("id"),
                "label": data.get("label") or data.get("username"),
                "username": data.get("username"),
                "password": self._unprotect_secret(data.get("password_secret") or "")
            }
        except Exception as e:
            print(f"[ProtonVault] Credential lookup failed for Profile {profile_id}: {e}")
            return None

    def update_profile_state(self, profile_id, status=None, ip_address=None, target_platform=None):
        """
        Updates dashboard-visible profile state:
        - status
        - last_ip
        - target_platform
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                fields = []
                values = []

                if status is not None:
                    fields.append("status = ?")
                    values.append(str(status))

                if ip_address is not None:
                    fields.append("last_ip = ?")
                    values.append(str(ip_address))

                if target_platform is not None:
                    fields.append("target_platform = ?")
                    values.append(str(target_platform))

                if not fields:
                    return

                values.append(profile_id)

                query = f"UPDATE profiles SET {', '.join(fields)} WHERE id = ?"
                cursor.execute(query, values)
                conn.commit()

                if cursor.rowcount == 0:
                    print(f"[Database] ⚠️ No profile row updated for id={profile_id}")
                else:
                    print(
                        f"[Database] ✅ Profile {profile_id} updated | "
                        f"status={status} | ip={ip_address} | target={target_platform}"
                    )

        except Exception as e:
            print(f"[Database] ❌ Error updating profile state for profile {profile_id}: {e}")

    def reset_all_statuses(self):
        """Forcefully resets dashboard state on startup."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE profiles
                    SET status = 'OFFLINE',
                        target_platform = 'None'
                """)
                cursor.execute("DELETE FROM profile_lifecycle_state")
                conn.commit()

            print("[Database] 🛡️ Global Status Reset: All profiles set to OFFLINE.")

        except Exception as e:
            print(f"[Database Error] Could not reset statuses: {e}")

    def get_all_profiles(self):
        """
        Retrieves all profiles and adds UI-compatible aliases.

        Database columns:
        - target_platform
        - last_ip

        Dashboard/UI aliases:
        - current_target
        - ip_origin
        """
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM profiles ORDER BY id ASC")
                rows = [dict(row) for row in cursor.fetchall()]
                proton_map = self._get_proton_assignment_map(conn)

            for row in rows:
                try:
                    proton_data = proton_map.get(int(row.get("id") or 0), {})
                except Exception:
                    proton_data = {}
                self._apply_proton_profile_fields(row, proton_data)

                target = row.get("target_platform") or "None"
                ip = row.get("last_ip") or "Unknown"

                row["target_platform"] = target
                row["last_ip"] = ip

                # Frontend-compatible aliases
                row["current_target"] = target
                row["currentTarget"] = target
                row["target"] = target

                row["ip_origin"] = ip
                row["ipOrigin"] = ip
                row["ip"] = ip

                # Quarantine aliases for UI/start filters.
                row["quarantined"] = int(row.get("quarantined") or 0)
                row["is_quarantined"] = bool(row["quarantined"])
                row["quarantine_score"] = int(row.get("quarantine_score") or 100)
                row["quarantine_reason"] = row.get("quarantine_reason") or ""
                row["quarantine_source"] = row.get("quarantine_source") or ""
                row["quarantined_at"] = row.get("quarantined_at") or ""

                hardware_json = row.get("hardware_profile_json") or ""
                row["hardware_profile_json"] = hardware_json
                row["hardware_profile"] = None

                if hardware_json:
                    try:
                        hardware_profile = json.loads(hardware_json)
                        if isinstance(hardware_profile, dict):
                            row["hardware_profile"] = hardware_profile
                            row["hardware_cloak"] = (
                                hardware_profile.get("display_string")
                                or hardware_profile.get("device_name")
                                or row.get("hardware_cloak")
                                or "Mobile Device"
                            )
                            row["device_name"] = hardware_profile.get("device_name", "")
                            row["device_type"] = hardware_profile.get("type", "")
                    except Exception:
                        row["hardware_profile"] = None

            return rows

        except Exception as e:
            print(f"[Database] ❌ Error fetching profiles: {e}")
            return []

    # ==============================
    # Profile Quarantine Helpers
    # ==============================

    def quarantine_profile(self, profile_id, reason="", score=0, source="manual"):
        """
        Marks a profile as quarantined.

        Quarantined profiles are not deleted.
        Quarantine is an advisory reliability flag; START ALL retests profiles after repairs.
        Live guards still stop unsafe launches for home IP, duplicate IP, or blacklisted IP.
        """
        try:
            profile_id = int(profile_id)
            reason = str(reason or "Manual quarantine").strip()
            source = str(source or "manual").strip()
            score = int(score or 0)

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE profiles
                    SET quarantined = 1,
                        quarantine_score = ?,
                        quarantine_reason = ?,
                        quarantine_source = ?,
                        quarantined_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (
                    score,
                    reason,
                    source,
                    profile_id
                ))
                conn.commit()

            self.record_analytics_event(
                profile_id=profile_id,
                platform="System",
                ip_status="QUARANTINED",
                event_type="PROFILE_QUARANTINED",
                details=f"Profile quarantined. score={score}; reason={reason}; source={source}"
            )

            return {
                "ok": True,
                "profile_id": profile_id,
                "quarantined": True,
                "score": score,
                "reason": reason,
                "source": source
            }

        except Exception as e:
            print(f"[Quarantine] Could not quarantine profile {profile_id}: {e}")
            return {
                "ok": False,
                "error": str(e)
            }

    def unquarantine_profile(self, profile_id, reason="Manual review passed"):
        """Removes a profile from quarantine."""
        try:
            profile_id = int(profile_id)
            reason = str(reason or "Manual review passed").strip()

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE profiles
                    SET quarantined = 0,
                        quarantine_reason = '',
                        quarantine_source = '',
                        quarantined_at = NULL
                    WHERE id = ?
                """, (profile_id,))
                conn.commit()

            self.record_analytics_event(
                profile_id=profile_id,
                platform="System",
                ip_status="OK",
                event_type="PROFILE_UNQUARANTINED",
                details=f"Profile removed from quarantine. reason={reason}"
            )

            return {
                "ok": True,
                "profile_id": profile_id,
                "quarantined": False,
                "reason": reason
            }

        except Exception as e:
            print(f"[Quarantine] Could not unquarantine profile {profile_id}: {e}")
            return {
                "ok": False,
                "error": str(e)
            }

    def get_quarantined_profile_ids(self):
        """Returns a set of profile IDs currently quarantined."""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                rows = cursor.execute("""
                    SELECT id
                    FROM profiles
                    WHERE COALESCE(quarantined, 0) = 1
                """).fetchall()

            return {int(row["id"]) for row in rows}

        except Exception as e:
            print(f"[Quarantine] Could not load quarantined profile IDs: {e}")
            return set()

    def _profile_reliability_score_from_rows(self, event_rows, session_rows):
        """
        Backend reliability score used for automatic quarantine.
        This mirrors the frontend scoring idea, but keeps enforcement server-side.
        """
        score = 100
        reasons = []

        text_parts = []

        for row in event_rows:
            text_parts.extend([
                str(row.get("event_type") or ""),
                str(row.get("ip_status") or ""),
                str(row.get("details") or ""),
                str(row.get("platform") or "")
            ])

        for row in session_rows:
            text_parts.extend([
                str(row.get("status") or ""),
                str(row.get("close_reason") or ""),
                str(row.get("ip_status") or ""),
                str(row.get("platform") or "")
            ])

        text = " ".join(text_parts).upper()

        def has_any(*terms):
            return any(str(term).upper() in text for term in terms)

        if has_any("BLACKLISTED", "IP_BLACKLISTED_BLOCKED"):
            score -= 35
            reasons.append("Blacklisted IP")

        if has_any("HOME_IP", "HOME IP DETECTED", "HOME_IP_BLOCKED"):
            score -= 35
            reasons.append("Home IP detected")

        if has_any("SELENIUM_ATTACH_FAILED", "COULD NOT ATTACH SELENIUM"):
            score -= 20
            reasons.append("Selenium attach failed")

        if has_any("IP_CHECK_FAILED", "IP_GUARD_ERROR", "IP VERIFICATION FAILED", "COULD NOT DETECT"):
            score -= 18
            reasons.append("IP check failed")

        if has_any("PLATFORM_PAGE_OPEN_FAILED", "NO_RUNNER_FOUND", "PAGE_FAILED", "TARGET_FAILED"):
            score -= 15
            reasons.append("Platform/page failed")

        if has_any("BROWSER_CLOSED", "BROWSER CLOSED", "UNEXPECTEDLY"):
            score -= 10
            reasons.append("Browser closed unexpectedly")

        error_count = 0
        for row in event_rows:
            event_type = str(row.get("event_type") or "").upper()
            ip_status = str(row.get("ip_status") or "").upper()
            details = str(row.get("details") or "").upper()

            if (
                "ERROR" in event_type
                or "FAILED" in event_type
                or "BLOCKED" in event_type
                or "BLACKLISTED" in event_type
                or "ERROR" in details
                or "FAILED" in details
                or ip_status in ["FAILED", "BLOCKED", "BLACKLISTED", "HOME_IP"]
            ):
                error_count += 1

        if error_count > 0:
            score -= min(25, error_count * 3)
            reasons.append(f"{error_count} error event(s)")

        short_sessions = 0
        for row in session_rows:
            try:
                duration = int(row.get("duration_seconds") or 0)
            except Exception:
                duration = 0

            status = str(row.get("status") or "").upper()

            if duration > 0 and duration < 60 and "RUNNING" not in status:
                short_sessions += 1

        if short_sessions > 0:
            score -= min(20, short_sessions * 10)
            reasons.append(f"{short_sessions} short session(s)")

        positive_terms = [
            "IP_VERIFIED",
            "SELENIUM_ATTACHED",
            "BROWSER_LAUNCHED",
            "PLATFORM_SELECTED",
            "PAGE_OPENED",
            "PAGE_LOADED",
            "SESSION_ENDED"
        ]

        positive_count = 0
        for term in positive_terms:
            if term in text:
                positive_count += 1

        score += min(20, positive_count * 3)

        if not event_rows and not session_rows:
            score = 50
            reasons.append("No session data yet")

        score = max(0, min(100, int(round(score))))

        if not reasons:
            reasons.append("No major issue")

        return score, "; ".join(reasons)

    def apply_auto_quarantine(self, threshold=30, min_events=3):
        """
        Automatically quarantines profiles whose reliability score is below threshold.

        Existing quarantined profiles stay quarantined until manually unquarantined.
        This avoids profiles re-entering normal launch rotation without review.
        """
        try:
            threshold = int(threshold)
            min_events = int(min_events)

            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                profiles = [dict(r) for r in cursor.execute("""
                    SELECT *
                    FROM profiles
                    ORDER BY id ASC
                """).fetchall()]

                quarantined = []

                for profile in profiles:
                    profile_id = int(profile["id"])

                    if int(profile.get("quarantined") or 0) == 1:
                        continue

                    event_rows = [dict(r) for r in cursor.execute("""
                        SELECT *
                        FROM analytics_events
                        WHERE profile_id = ?
                        ORDER BY id DESC
                        LIMIT 100
                    """, (profile_id,)).fetchall()]

                    session_rows = [dict(r) for r in cursor.execute("""
                        SELECT *
                        FROM profile_sessions
                        WHERE profile_id = ?
                        ORDER BY started_at DESC
                        LIMIT 50
                    """, (profile_id,)).fetchall()]

                    if len(event_rows) < min_events and len(session_rows) == 0:
                        continue

                    score, reason = self._profile_reliability_score_from_rows(event_rows, session_rows)

                    cursor.execute("""
                        UPDATE profiles
                        SET quarantine_score = ?
                        WHERE id = ?
                    """, (score, profile_id))

                    if score < threshold:
                        cursor.execute("""
                            UPDATE profiles
                            SET quarantined = 1,
                                quarantine_score = ?,
                                quarantine_reason = ?,
                                quarantine_source = 'auto',
                                quarantined_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (
                            score,
                            reason,
                            profile_id
                        ))

                        quarantined.append({
                            "profile_id": profile_id,
                            "score": score,
                            "reason": reason
                        })

                conn.commit()

            for item in quarantined:
                try:
                    self.record_analytics_event(
                        profile_id=item["profile_id"],
                        platform="System",
                        ip_status="QUARANTINED",
                        event_type="PROFILE_AUTO_QUARANTINED",
                        details=f"Auto-quarantined. score={item['score']}; reason={item['reason']}"
                    )
                except Exception:
                    pass

            return {
                "ok": True,
                "threshold": threshold,
                "quarantined": quarantined,
                "count": len(quarantined)
            }

        except Exception as e:
            print(f"[Quarantine] Auto-quarantine failed: {e}")
            return {
                "ok": False,
                "error": str(e),
                "quarantined": [],
                "count": 0
            }
    
    # ==============================
    # Analytics / Reputation Helpers
    # ==============================


    # === COMET PATCH 009 BACKEND REFRESH SNAPSHOT DB START ===
    def patch009_ensure_refresh_history(self):
        try:
            with self._get_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    CREATE TABLE IF NOT EXISTS dashboard_refresh_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        source TEXT DEFAULT 'dashboard',
                        mode TEXT DEFAULT '',
                        ok INTEGER DEFAULT 1,
                        duration_ms INTEGER DEFAULT 0,
                        updated_count INTEGER DEFAULT 0,
                        skipped_count INTEGER DEFAULT 0,
                        failed_count INTEGER DEFAULT 0,
                        missing_count INTEGER DEFAULT 0,
                        slow_count INTEGER DEFAULT 0,
                        missing_sections TEXT DEFAULT '',
                        slow_sections TEXT DEFAULT '',
                        details_json TEXT DEFAULT ''
                    )
                """)
                c.execute("CREATE INDEX IF NOT EXISTS idx_dashboard_refresh_history_created_at ON dashboard_refresh_history(created_at)")
                conn.commit()
            return True
        except Exception as e:
            print(f"[Patch009] ensure refresh history failed: {e}")
            return False

    def record_dashboard_refresh_history(self, payload=None):
        try:
            self.patch009_ensure_refresh_history()
            data = payload if isinstance(payload, dict) else {}
            results = data.get("results") if isinstance(data.get("results"), list) else []

            updated = skipped = failed = missing = slow = 0
            missing_names = []
            slow_names = []

            for item in results:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or item.get("key") or "section")
                status = str(item.get("status") or "").lower()
                ok = bool(item.get("ok"))
                try:
                    ms = int(float(item.get("ms") or item.get("duration_ms") or 0))
                except Exception:
                    ms = 0

                if ok or status == "ok":
                    updated += 1
                elif status == "missing":
                    skipped += 1
                    missing += 1
                    missing_names.append(name)
                elif status == "fail":
                    failed += 1
                else:
                    skipped += 1

                if ms >= 2500:
                    slow += 1
                    slow_names.append(f"{name} ({ms}ms)")

            source = str(data.get("source") or "dashboard")[:80]
            mode = str(data.get("mode") or "")[:40]
            duration_ms = int(float(data.get("duration_ms") or data.get("durationMs") or 0))
            details_json = json.dumps(data, ensure_ascii=False, default=str)[:200000]

            with self._get_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO dashboard_refresh_history (
                        source, mode, ok, duration_ms, updated_count, skipped_count,
                        failed_count, missing_count, slow_count, missing_sections,
                        slow_sections, details_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    source, mode, 1 if failed == 0 else 0, duration_ms, updated, skipped,
                    failed, missing, slow, ", ".join(missing_names[:30]),
                    ", ".join(slow_names[:30]), details_json
                ))
                conn.commit()
                row_id = c.lastrowid

            return {
                "ok": True,
                "id": row_id,
                "updated_count": updated,
                "skipped_count": skipped,
                "failed_count": failed,
                "missing_count": missing,
                "slow_count": slow
            }
        except Exception as e:
            print(f"[Patch009] record history failed: {e}")
            return {"ok": False, "error": str(e)}

    def get_dashboard_refresh_history(self, limit=25):
        try:
            self.patch009_ensure_refresh_history()
            limit = max(1, min(200, int(limit or 25)))
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT *
                    FROM dashboard_refresh_history
                    ORDER BY id DESC
                    LIMIT ?
                """, (limit,)).fetchall()
            return {"ok": True, "history": [dict(r) for r in rows]}
        except Exception as e:
            return {"ok": False, "error": str(e), "history": []}

    def get_dashboard_snapshot(self):
        try:
            self.patch009_ensure_refresh_history()

            try:
                profiles = self.get_all_profiles()
            except Exception:
                profiles = []

            profile_summary = {
                "total": len(profiles),
                "running": 0,
                "starting": 0,
                "offline": 0,
                "blocked": 0,
                "quarantined": 0,
                "unknown_ip": 0
            }

            for p in profiles:
                status = str(p.get("status") or "").upper()
                ip = str(p.get("last_ip") or p.get("ip_origin") or "").strip().lower()

                if status == "RUNNING":
                    profile_summary["running"] += 1
                elif status in ("STARTING", "LAUNCHING"):
                    profile_summary["starting"] += 1
                elif status in ("BLOCKED", "FAILED", "ERROR", "BLACKLISTED"):
                    profile_summary["blocked"] += 1
                else:
                    profile_summary["offline"] += 1

                if int(p.get("quarantined") or 0):
                    profile_summary["quarantined"] += 1

                if not ip or ip in ("unknown", "not verified", "none", "checking", "checking..."):
                    profile_summary["unknown_ip"] += 1

            try:
                proton_status = self.get_proton_account_status()
                proton_summary = proton_status.get("summary") or {}
            except Exception as e:
                proton_summary = {"error": str(e)}

            history_payload = self.get_dashboard_refresh_history(limit=30)
            history = history_payload.get("history") or []

            refresh_summary = {
                "history_count": len(history),
                "last_refresh_at": history[0].get("created_at", "") if history else "",
                "last_duration_ms": int(history[0].get("duration_ms") or 0) if history else 0,
                "recent_failures": sum(int(r.get("failed_count") or 0) for r in history[:10]),
                "recent_missing": sum(int(r.get("missing_count") or 0) for r in history[:10]),
                "recent_slow": sum(int(r.get("slow_count") or 0) for r in history[:10])
            }

            analytics_summary = {}
            try:
                if hasattr(self, "get_analytics_data"):
                    analytics = self.get_analytics_data()
                    analytics_summary = analytics.get("summary") or {}
            except Exception as e:
                analytics_summary = {"error": str(e)}

            recommendations = []

            def add(level, title, detail, action=""):
                recommendations.append({"level": level, "title": title, "detail": detail, "action": action})

            unassigned = int(proton_summary.get("unassigned_profiles") or 0)
            if unassigned:
                add("warning", "Profiles missing Proton assignment", f"{unassigned} profile(s) are unassigned.", "Open PC Control > Proton Accounts and rebalance.")

            if profile_summary["quarantined"]:
                add("warning", "Quarantined profiles detected", f"{profile_summary['quarantined']} profile(s) are quarantined.", "Review Profile Identity before running sessions.")

            if profile_summary["unknown_ip"]:
                add("info", "Unknown IP states detected", f"{profile_summary['unknown_ip']} profile(s) show unknown/not verified IP.", "Use refresh and profile checks to update dashboard state.")

            if not history:
                add("info", "No backend refresh history yet", "Click REFRESH ALL once so SQLite can start storing refresh runs.", "Keep AUTO OFF for the first test.")
            else:
                if refresh_summary["recent_failures"]:
                    add("warning", "Recent refresh failures", f"{refresh_summary['recent_failures']} failure(s) in recent refresh history.", "Check failed sections in the history table.")
                if refresh_summary["recent_slow"]:
                    add("info", "Slow refresh sections", f"{refresh_summary['recent_slow']} slow section(s) in recent refresh history.", "Use AUTO SAFE until performance is stable.")
                if refresh_summary["recent_missing"]:
                    add("info", "Missing optional refresh functions", f"{refresh_summary['recent_missing']} optional section(s) were skipped as missing.", "This is normal if those panels are not installed.")

            if not recommendations:
                add("good", "Snapshot looks stable", "No critical dashboard refresh or readiness problems detected.", "AUTO SAFE is okay for normal monitoring.")

            return {
                "ok": True,
                "snapshot_at": datetime.now().isoformat(timespec="seconds"),
                "profiles": profile_summary,
                "proton": proton_summary,
                "analytics": analytics_summary,
                "refresh": refresh_summary,
                "refresh_history": history,
                "recommendations": recommendations[:8]
            }
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "snapshot_at": datetime.now().isoformat(timespec="seconds"),
                "profiles": {},
                "proton": {},
                "analytics": {},
                "refresh": {},
                "refresh_history": [],
                "recommendations": [{
                    "level": "warning",
                    "title": "Snapshot failed",
                    "detail": str(e),
                    "action": "Upload the patch report and dashboard log."
                }]
            }
    # === COMET PATCH 009 BACKEND REFRESH SNAPSHOT DB END ===

    def _extract_ip_only(self, ip_label):
        import re
        raw = str(ip_label or "").strip()
        match = re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", raw)
        return match.group(0) if match else ""

    def _parse_ip_label_parts(self, ip_label):
        """
        Parses labels like:
        155.117.189.29 | Secaucus, New Jersey, United States | Proton AG
        """
        raw = str(ip_label or "").strip()
        parts = [p.strip() for p in raw.split("|")]
        ip_address = self._extract_ip_only(raw)

        city = ""
        country = ""
        provider = ""

        if len(parts) >= 2:
            location = parts[1]
            loc_parts = [p.strip() for p in location.split(",") if p.strip()]
            if loc_parts:
                city = loc_parts[0]
                country = loc_parts[-1]

        if len(parts) >= 3:
            provider = parts[2]

        return {
            "ip_address": ip_address,
            "ip_label": raw,
            "city": city,
            "country": country,
            "provider": provider
        }

    def _normalize_ip_status(self, ip_label=None, ip_status=None):
        raw_status = str(ip_status or "").strip().upper()
        raw_label = str(ip_label or "").strip().lower()

        if raw_status in ["BLACKLISTED", "IP_BLACKLISTED"]:
            return "BLACKLISTED"

        if raw_status:
            return raw_status

        if not raw_label or raw_label in ["unknown", "none", "not verified", "checking", "checking..."]:
            return "UNKNOWN"

        if "blacklist" in raw_label:
            return "BLACKLISTED"

        if "home" in raw_label:
            return "HOME_IP"

        if "duplicate" in raw_label:
            return "DUPLICATE_IP"

        if "blocked" in raw_label or "failed" in raw_label:
            return "BAD_OR_BLOCKED"

        return "OK"

    def _normalize_revenue_model_key(self, platform="", event_type=""):
        """Maps raw platform/event values to the configured revenue model key."""
        p = str(platform or "").strip().lower()
        e = str(event_type or "").strip().upper()

        if p in ["youtube", "yt"]:
            return "youtube"

        if p in ["spotify"]:
            return "spotify"

        if p in ["deezer"]:
            return "deezer"

        if p in ["twitch_bits", "bits"] or e in ["TWITCH_BITS", "CHEER_BITS", "BITS_CHEERED"]:
            return "twitch_bits"

        if p in ["twitch_subs", "subs"] or e in ["TWITCH_SUB", "TWITCH_SUB_T1", "SUBSCRIPTION"]:
            return "twitch_subs"

        if p in ["twitch", "twitch_ads"]:
            return "twitch_ads"

        return p

    def _monetized_metric_count(self, platform_key, event_type="", event_value=0.0, duration_seconds=0):
        """
        Returns the number of payable units to multiply by the platform model.
        Non-monetized state events return 0.
        """
        e = str(event_type or "").strip().upper()
        try:
            raw_count = float(event_value or 0.0)
        except Exception:
            raw_count = 0.0

        one_unit = raw_count if raw_count > 0 else 1.0

        if platform_key == "youtube":
            if e in ["VIEW_COUNTED", "AD_DETECTED", "AD_COMPLETED", "YOUTUBE_AD_DETECTED", "YOUTUBE_AD_COMPLETED"]:
                return one_unit
            return 0.0

        if platform_key == "twitch_ads":
            if e in ["AD_DETECTED", "AD_COMPLETED", "TWITCH_AD_DETECTED", "TWITCH_AD_COMPLETED"]:
                return one_unit
            return 0.0

        if platform_key == "twitch_bits":
            if e in ["TWITCH_BITS", "CHEER_BITS", "BITS_CHEERED"]:
                return raw_count if raw_count > 0 else 0.0
            return 0.0

        if platform_key == "twitch_subs":
            if e in ["TWITCH_SUB", "TWITCH_SUB_T1", "SUBSCRIPTION"]:
                return one_unit
            return 0.0

        if platform_key in ["spotify", "deezer"]:
            if e in ["STREAM_COUNTED", "TRACK_30S_REACHED", "SONG_30S_REACHED", "STREAM_30S"]:
                return one_unit
            if e in ["TRACK_PLAYED", "SONG_PLAYED", "STREAM_PLAYED"] and int(duration_seconds or 0) >= 30:
                return one_unit
            return 0.0

        return 0.0

    def estimate_event_revenue(self, platform="", event_type="", event_value=0.0, duration_seconds=0, estimated_value=0.0):
        """
        Returns min/avg/max projection for a single event.
        The dashboard should treat this as an estimate, not confirmed revenue.
        """
        model_key = self._normalize_revenue_model_key(platform, event_type)
        metric_count = self._monetized_metric_count(model_key, event_type, event_value, duration_seconds)

        explicit_estimate = float(estimated_value or 0.0)
        if explicit_estimate > 0:
            return {
                "revenue_model_key": model_key,
                "metric_count": metric_count if metric_count > 0 else 1.0,
                "estimated_min": explicit_estimate,
                "estimated_avg": explicit_estimate,
                "estimated_max": explicit_estimate
            }

        if metric_count <= 0:
            return {
                "revenue_model_key": model_key,
                "metric_count": 0.0,
                "estimated_min": 0.0,
                "estimated_avg": 0.0,
                "estimated_max": 0.0
            }

        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                row = cursor.execute("""
                    SELECT *
                    FROM platform_revenue_models
                    WHERE platform_key = ? AND enabled = 1
                    LIMIT 1
                """, (model_key,)).fetchone()

            if not row:
                model = DEFAULT_PLATFORM_REVENUE_MODELS.get(model_key, {})
                payout_min = float(model.get("payout_min", 0.0))
                payout_avg = float(model.get("payout_avg", 0.0))
                payout_max = float(model.get("payout_max", 0.0))
            else:
                payout_min = float(row["payout_min"] or 0.0)
                payout_avg = float(row["payout_avg"] or 0.0)
                payout_max = float(row["payout_max"] or 0.0)

            return {
                "revenue_model_key": model_key,
                "metric_count": metric_count,
                "estimated_min": round(metric_count * payout_min, 8),
                "estimated_avg": round(metric_count * payout_avg, 8),
                "estimated_max": round(metric_count * payout_max, 8)
            }

        except Exception as e:
            print(f"[Analytics] Revenue estimate failed for {model_key}/{event_type}: {e}")
            return {
                "revenue_model_key": model_key,
                "metric_count": metric_count,
                "estimated_min": 0.0,
                "estimated_avg": 0.0,
                "estimated_max": 0.0
            }

    def get_platform_revenue_models(self):
        """Returns configured platform projection constants."""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                rows = cursor.execute("""
                    SELECT *
                    FROM platform_revenue_models
                    ORDER BY
                        CASE platform_key
                            WHEN 'youtube' THEN 1
                            WHEN 'twitch_ads' THEN 2
                            WHEN 'twitch_bits' THEN 3
                            WHEN 'twitch_subs' THEN 4
                            WHEN 'spotify' THEN 5
                            WHEN 'deezer' THEN 6
                            ELSE 99
                        END,
                        platform_key ASC
                """).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            print(f"[Analytics] Could not load platform revenue models: {e}")
            return []

    def record_analytics_event(
        self,
        profile_id=None,
        pc_id="",
        session_id="",
        platform="",
        ip_label="",
        ip_status="",
        event_type="EVENT",
        event_value=0.0,
        estimated_value=0.0,
        details="",
        duration_seconds=0
    ):
        """
        Stores one lightweight analytics event.

        Use this for:
        - SESSION_STARTED
        - IP_VERIFIED
        - PLATFORM_OPENED
        - AD_DETECTED
        - AD_COMPLETED
        - SESSION_ENDED
        - HOME_IP_BLOCKED
        - DUPLICATE_IP_BLOCKED
        """
        try:
            ip_parts = self._parse_ip_label_parts(ip_label)
            ip_address = ip_parts["ip_address"]
            normalized_status = self._normalize_ip_status(ip_label, ip_status)

            revenue_estimate = self.estimate_event_revenue(
                platform=platform,
                event_type=event_type,
                event_value=event_value,
                duration_seconds=duration_seconds,
                estimated_value=estimated_value
            )

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO analytics_events (
                        pc_id,
                        profile_id,
                        session_id,
                        platform,
                        ip_address,
                        ip_label,
                        ip_status,
                        event_type,
                        event_value,
                        estimated_value,
                        estimated_min,
                        estimated_avg,
                        estimated_max,
                        metric_count,
                        duration_seconds,
                        revenue_model_key,
                        details
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(pc_id or ""),
                    profile_id,
                    str(session_id or ""),
                    str(platform or ""),
                    ip_address,
                    str(ip_label or ""),
                    normalized_status,
                    str(event_type or "EVENT"),
                    float(event_value or 0),
                    float(revenue_estimate.get("estimated_avg", 0.0)),
                    float(revenue_estimate.get("estimated_min", 0.0)),
                    float(revenue_estimate.get("estimated_avg", 0.0)),
                    float(revenue_estimate.get("estimated_max", 0.0)),
                    float(revenue_estimate.get("metric_count", 0.0)),
                    int(duration_seconds or 0),
                    str(revenue_estimate.get("revenue_model_key", "") or ""),
                    str(details or "")
                ))
                conn.commit()

            self.update_ip_reputation(
                ip_label=ip_label,
                platform=platform,
                ip_status=normalized_status,
                ads_detected_delta=1 if str(event_type).upper() in ["AD_DETECTED", "AD_COMPLETED"] else 0,
                failures_delta=1 if normalized_status not in ["OK", "UNKNOWN"] or str(event_type).upper().endswith("FAILED") else 0,
                estimated_revenue_delta=float(revenue_estimate.get("estimated_avg", 0.0)),
                estimated_min_delta=float(revenue_estimate.get("estimated_min", 0.0)),
                estimated_avg_delta=float(revenue_estimate.get("estimated_avg", 0.0)),
                estimated_max_delta=float(revenue_estimate.get("estimated_max", 0.0))
            )

            # Any future ad-detection/platform code can trigger one of these events.
            # When it does, this IP becomes persistent-blocked immediately.
            auto_blacklist_events = {
                "NO_AD_WITHIN_LIMIT",
                "NO_BENEFIT",
                "NO_VIEW_CREDIT",
                "IP_NO_BENEFIT",
                "IP_NO_ADS",
                "AD_VALUE_ZERO",
                "VIEW_NOT_COUNTED"
            }
            event_name = str(event_type or "").upper().strip()
            if event_name in auto_blacklist_events and ip_address:
                self.add_ip_to_blacklist(
                    ip_label or ip_address,
                    reason=f"Auto-blacklisted after event: {event_name}",
                    source="auto",
                    record_event=False
                )

        except Exception as e:
            print(f"[Analytics] ❌ Could not record event {event_type}: {e}")

    def update_ip_reputation(
        self,
        ip_label="",
        platform="",
        ip_status="",
        ads_detected_delta=0,
        failures_delta=0,
        estimated_revenue_delta=0.0,
        estimated_min_delta=0.0,
        estimated_avg_delta=None,
        estimated_max_delta=0.0
    ):
        """
        Creates/updates the optional ip_reputation table.

        Platform-specific fields:
        - good_for_youtube / bad_for_youtube
        - good_for_twitch / bad_for_twitch
        - good_for_spotify / bad_for_spotify
        - good_for_deezer / bad_for_deezer
        """
        ip_parts = self._parse_ip_label_parts(ip_label)
        ip_address = ip_parts["ip_address"]

        if not ip_address:
            return

        platform = str(platform or "").strip().lower()
        normalized_status = self._normalize_ip_status(ip_label, ip_status)
        if estimated_avg_delta is None:
            estimated_avg_delta = float(estimated_revenue_delta or 0.0)

        good_field = None
        bad_field = None

        if platform in ["youtube", "twitch", "spotify", "deezer"]:
            good_field = f"good_for_{platform}"
            bad_field = f"bad_for_{platform}"

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO ip_reputation (
                        ip_address,
                        ip_label,
                        city,
                        country,
                        provider,
                        status,
                        total_profiles,
                        total_sessions,
                        total_ads_detected,
                        total_failures,
                        estimated_revenue,
                        estimated_revenue_min,
                        estimated_revenue_avg,
                        estimated_revenue_max,
                        last_seen
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 1, 1, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(ip_address) DO UPDATE SET
                        ip_label = excluded.ip_label,
                        city = excluded.city,
                        country = excluded.country,
                        provider = excluded.provider,
                        status = CASE
                            WHEN ip_reputation.blacklisted = 1 THEN 'BLACKLISTED'
                            WHEN excluded.status = 'BLACKLISTED' THEN 'BLACKLISTED'
                            WHEN excluded.status != 'UNKNOWN' THEN excluded.status
                            ELSE ip_reputation.status
                        END,
                        last_seen = CURRENT_TIMESTAMP,
                        total_sessions = total_sessions + 1,
                        total_ads_detected = total_ads_detected + excluded.total_ads_detected,
                        total_failures = total_failures + excluded.total_failures,
                        estimated_revenue = estimated_revenue + excluded.estimated_revenue,
                        estimated_revenue_min = estimated_revenue_min + excluded.estimated_revenue_min,
                        estimated_revenue_avg = estimated_revenue_avg + excluded.estimated_revenue_avg,
                        estimated_revenue_max = estimated_revenue_max + excluded.estimated_revenue_max
                """, (
                    ip_address,
                    ip_parts["ip_label"],
                    ip_parts["city"],
                    ip_parts["country"],
                    ip_parts["provider"],
                    normalized_status,
                    int(ads_detected_delta or 0),
                    int(failures_delta or 0),
                    float(estimated_avg_delta or 0.0),
                    float(estimated_min_delta or 0.0),
                    float(estimated_avg_delta or 0.0),
                    float(estimated_max_delta or 0.0)
                ))

                if normalized_status == "BLACKLISTED":
                    cursor.execute("""
                        UPDATE ip_reputation
                        SET
                            blacklisted = 1,
                            status = 'BLACKLISTED',
                            blacklisted_at = COALESCE(blacklisted_at, CURRENT_TIMESTAMP),
                            blacklist_reason = COALESCE(NULLIF(blacklist_reason, ''), 'Auto-blacklisted')
                        WHERE ip_address = ?
                    """, (ip_address,))
                else:
                    # A manually blacklisted IP must stay blacklisted even if later events look OK.
                    cursor.execute("""
                        UPDATE ip_reputation
                        SET status = 'BLACKLISTED'
                        WHERE ip_address = ? AND blacklisted = 1
                    """, (ip_address,))

                if good_field and int(ads_detected_delta or 0) > 0:
                    cursor.execute(
                        f"UPDATE ip_reputation SET {good_field} = 1 WHERE ip_address = ?",
                        (ip_address,)
                    )

                if bad_field and (normalized_status not in ["OK", "UNKNOWN"] or int(failures_delta or 0) > 0):
                    cursor.execute(
                        f"UPDATE ip_reputation SET {bad_field} = 1 WHERE ip_address = ?",
                        (ip_address,)
                    )

                conn.commit()

        except Exception as e:
            print(f"[Analytics] ❌ Could not update IP reputation for {ip_address}: {e}")

    def start_profile_session(self, pc_id, profile_id, platform="", ip_label="", ip_status="UNKNOWN"):
        session_id = f"{pc_id}-{profile_id}-{int(datetime.now().timestamp())}"

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO profile_sessions (
                        session_id,
                        pc_id,
                        profile_id,
                        platform,
                        starting_ip,
                        final_ip,
                        ip_status,
                        status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'RUNNING')
                """, (
                    session_id,
                    str(pc_id or ""),
                    int(profile_id),
                    str(platform or ""),
                    str(ip_label or ""),
                    str(ip_label or ""),
                    self._normalize_ip_status(ip_label, ip_status)
                ))
                conn.commit()

            self.record_analytics_event(
                profile_id=profile_id,
                pc_id=pc_id,
                session_id=session_id,
                platform=platform,
                ip_label=ip_label,
                ip_status=ip_status,
                event_type="SESSION_STARTED",
                details="Profile session started"
            )

            return session_id

        except Exception as e:
            print(f"[Analytics] ❌ Could not start profile session: {e}")
            return session_id

    def end_profile_session(self, session_id, final_ip="", status="ENDED", close_reason="", estimated_revenue=0.0):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE profile_sessions
                    SET
                        ended_at = CURRENT_TIMESTAMP,
                        duration_seconds = CAST((julianday(CURRENT_TIMESTAMP) - julianday(started_at)) * 86400 AS INTEGER),
                        final_ip = COALESCE(NULLIF(?, ''), final_ip),
                        status = ?,
                        close_reason = ?,
                        estimated_revenue = estimated_revenue + ?
                    WHERE session_id = ?
                """, (
                    str(final_ip or ""),
                    str(status or "ENDED"),
                    str(close_reason or ""),
                    float(estimated_revenue or 0.0),
                    str(session_id or "")
                ))
                conn.commit()
        except Exception as e:
            print(f"[Analytics] ❌ Could not end profile session {session_id}: {e}")

    def get_analytics_data(self):
        """
        Returns data for the Analytics tab:
        - summary cards
        - profile performance
        - IP reputation
        - platform performance
        - recent event log
        """
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Safe quarantine schema repair.
                # This prevents Analytics from going empty if the DB existed before quarantine columns were added.
                try:
                    self._add_column_if_missing(cursor, "profiles", "quarantined", "INTEGER DEFAULT 0")
                    self._add_column_if_missing(cursor, "profiles", "hardware_profile_json", "TEXT DEFAULT ''")
                    self._add_column_if_missing(cursor, "profiles", "quarantine_score", "INTEGER DEFAULT 100")
                    self._add_column_if_missing(cursor, "profiles", "quarantine_reason", "TEXT DEFAULT ''")
                    self._add_column_if_missing(cursor, "profiles", "quarantine_source", "TEXT DEFAULT ''")
                    self._add_column_if_missing(cursor, "profiles", "quarantined_at", "TIMESTAMP")
                    conn.commit()
                except Exception as e:
                    print(f"[Quarantine] Analytics schema repair failed: {e}")
                    
                total_events = cursor.execute("SELECT COUNT(*) AS c FROM analytics_events").fetchone()["c"]
                total_ads = cursor.execute("""
                    SELECT COUNT(*) AS c
                    FROM analytics_events
                    WHERE event_type IN ('AD_DETECTED', 'AD_COMPLETED')
                """).fetchone()["c"]
                revenue_totals = cursor.execute("""
                    SELECT
                        COALESCE(SUM(estimated_min), 0) AS min_v,
                        COALESCE(SUM(estimated_avg), 0) AS avg_v,
                        COALESCE(SUM(estimated_max), 0) AS max_v,
                        COALESCE(SUM(estimated_value), 0) AS legacy_v
                    FROM analytics_events
                """).fetchone()
                estimated_revenue_min = revenue_totals["min_v"]
                estimated_revenue_avg = revenue_totals["avg_v"] if revenue_totals["avg_v"] is not None else revenue_totals["legacy_v"]
                estimated_revenue_max = revenue_totals["max_v"]

                active_profiles = cursor.execute("""
                    SELECT COUNT(*) AS c
                    FROM profiles
                    WHERE UPPER(status) = 'RUNNING'
                """).fetchone()["c"]

                bad_ip_count = cursor.execute("""
                    SELECT COUNT(*) AS c
                    FROM ip_reputation
                    WHERE blacklisted = 1
                       OR status IN ('HOME_IP', 'DUPLICATE_IP', 'BAD_OR_BLOCKED', 'BLACKLISTED')
                """).fetchone()["c"]

                profile_rows = cursor.execute("""
                    SELECT
                        p.id AS profile_id,
                        p.name AS profile_name,
                        p.status,
                        p.target_platform,
                        p.last_ip,
                        COALESCE(p.quarantined, 0) AS quarantined,
                        COALESCE(p.quarantine_score, 100) AS quarantine_score,
                        COALESCE(p.quarantine_reason, '') AS quarantine_reason,
                        COALESCE(p.quarantine_source, '') AS quarantine_source,
                        COALESCE(p.quarantined_at, '') AS quarantined_at,
                        COUNT(e.id) AS events,
                        SUM(CASE WHEN e.event_type IN ('AD_DETECTED', 'AD_COMPLETED', 'YOUTUBE_AD_COMPLETED', 'TWITCH_AD_COMPLETED') THEN 1 ELSE 0 END) AS ads_detected,
                        COALESCE(SUM(e.metric_count), 0) AS metric_count,
                        COALESCE(SUM(e.estimated_min), 0) AS estimated_min,
                        COALESCE(SUM(e.estimated_avg), 0) AS estimated_avg,
                        COALESCE(SUM(e.estimated_max), 0) AS estimated_max,
                        COALESCE(SUM(e.estimated_avg), SUM(e.estimated_value), 0) AS estimated_revenue,
                        MAX(e.event_ts) AS last_event
                    FROM profiles p
                    LEFT JOIN analytics_events e ON e.profile_id = p.id
                    GROUP BY p.id
                    ORDER BY p.id ASC
                """).fetchall()

                ip_rows = cursor.execute("""
                    SELECT *
                    FROM ip_reputation
                    ORDER BY
                        CASE status
                            WHEN 'HOME_IP' THEN 1
                            WHEN 'DUPLICATE_IP' THEN 2
                            WHEN 'BAD_OR_BLOCKED' THEN 3
                            WHEN 'OK' THEN 4
                            ELSE 5
                        END,
                        last_seen DESC
                """).fetchall()

                platform_rows = cursor.execute("""
                    SELECT
                        COALESCE(NULLIF(platform, ''), 'Unknown') AS platform,
                        COUNT(DISTINCT profile_id) AS profiles_used,
                        COUNT(DISTINCT ip_address) AS unique_ips,
                        COUNT(*) AS total_events,
                        SUM(CASE WHEN event_type IN ('AD_DETECTED', 'AD_COMPLETED', 'YOUTUBE_AD_COMPLETED', 'TWITCH_AD_COMPLETED') THEN 1 ELSE 0 END) AS ads_detected,
                        COALESCE(SUM(metric_count), 0) AS metric_count,
                        COALESCE(SUM(estimated_min), 0) AS estimated_min,
                        COALESCE(SUM(estimated_avg), 0) AS estimated_avg,
                        COALESCE(SUM(estimated_max), 0) AS estimated_max,
                        COALESCE(SUM(estimated_avg), SUM(estimated_value), 0) AS estimated_revenue,
                        MAX(event_ts) AS last_event
                    FROM analytics_events
                    GROUP BY COALESCE(NULLIF(platform, ''), 'Unknown')
                    ORDER BY ads_detected DESC, total_events DESC
                """).fetchall()

                event_rows = cursor.execute("""
                    SELECT *
                    FROM analytics_events
                    ORDER BY id DESC
                    LIMIT 500
                """).fetchall()

                session_rows = cursor.execute("""
                    SELECT
                        ps.*,
                        COUNT(e.id) AS event_count,
                        SUM(
                            CASE
                                WHEN UPPER(e.event_type) LIKE '%ERROR%'
                                  OR UPPER(e.event_type) LIKE '%FAILED%'
                                  OR UPPER(e.event_type) LIKE '%BLOCKED%'
                                  OR UPPER(e.event_type) LIKE '%BLACKLISTED%'
                                THEN 1
                                ELSE 0
                            END
                        ) AS error_count,
                        MAX(e.event_ts) AS last_event
                    FROM profile_sessions ps
                    LEFT JOIN analytics_events e
                        ON e.session_id = ps.session_id
                    GROUP BY ps.session_id
                    ORDER BY
                        COALESCE(ps.ended_at, ps.started_at) DESC,
                        ps.started_at DESC
                    LIMIT 300
                """).fetchall()

                blacklisted_rows = cursor.execute("""
                    SELECT *
                    FROM ip_reputation
                    WHERE blacklisted = 1 OR status = 'BLACKLISTED'
                    ORDER BY blacklisted_at DESC, last_seen DESC
                """).fetchall()

                return {
                    "ok": True,
                    "summary": {
                        "total_events": total_events,
                        "active_profiles": active_profiles,
                        "ads_detected": total_ads,
                        "estimated_revenue_min": round(float(estimated_revenue_min or 0), 6),
                        "estimated_revenue": round(float(estimated_revenue_avg or 0), 6),
                        "estimated_revenue_avg": round(float(estimated_revenue_avg or 0), 6),
                        "estimated_revenue_max": round(float(estimated_revenue_max or 0), 6),
                        "bad_ip_count": bad_ip_count,
                        "blacklisted_count": len(blacklisted_rows),
                        "ip_reputation_count": len(ip_rows)
                    },
                    "profiles": [dict(r) for r in profile_rows],
                    "ip_reputation": [dict(r) for r in ip_rows],
                    "blacklisted_ips": [dict(r) for r in blacklisted_rows],
                    "platforms": [dict(r) for r in platform_rows],
                    "events": [dict(r) for r in event_rows],
                    "sessions": [dict(r) for r in session_rows],
                    "revenue_models": self.get_platform_revenue_models()
                }

        except Exception as e:
            print(f"[Analytics] get_analytics_data failed: {e}")
            traceback.print_exc()
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


    # ==============================
    # Persistent IP Blacklist
    # ==============================

    def is_ip_blacklisted(self, ip_label_or_ip):
        """Returns True when an IP is manually/automatically blacklisted."""
        ip_address = self._extract_ip_only(ip_label_or_ip)
        if not ip_address:
            return False

        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                row = cursor.execute("""
                    SELECT ip_address, status, blacklisted
                    FROM ip_reputation
                    WHERE ip_address = ?
                    LIMIT 1
                """, (ip_address,)).fetchone()

            if not row:
                return False

            return bool(int(row["blacklisted"] or 0) == 1 or str(row["status"] or "").upper() == "BLACKLISTED")

        except Exception as e:
            print(f"[Blacklist] Could not check IP {ip_address}: {e}")
            return False

    def add_ip_to_blacklist(self, ip_label_or_ip, reason="", source="manual", record_event=True):
        """Adds/updates a persistent blacklist entry in ip_reputation."""
        ip_parts = self._parse_ip_label_parts(ip_label_or_ip)
        ip_address = ip_parts["ip_address"]

        if not ip_address:
            return {
                "ok": False,
                "error": "Valid IPv4 address required. Example: 155.117.189.29"
            }

        reason = str(reason or "Manual blacklist").strip() or "Manual blacklist"
        source = str(source or "manual").strip().lower()
        manually_blacklisted = 1 if source == "manual" else 0

        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO ip_reputation (
                        ip_address,
                        ip_label,
                        city,
                        country,
                        provider,
                        status,
                        blacklisted,
                        blacklisted_at,
                        blacklist_reason,
                        manually_blacklisted,
                        total_profiles,
                        total_sessions,
                        last_seen
                    )
                    VALUES (?, ?, ?, ?, ?, 'BLACKLISTED', 1, CURRENT_TIMESTAMP, ?, ?, 0, 0, CURRENT_TIMESTAMP)
                    ON CONFLICT(ip_address) DO UPDATE SET
                        ip_label = COALESCE(NULLIF(excluded.ip_label, ''), ip_reputation.ip_label),
                        city = COALESCE(NULLIF(excluded.city, ''), ip_reputation.city),
                        country = COALESCE(NULLIF(excluded.country, ''), ip_reputation.country),
                        provider = COALESCE(NULLIF(excluded.provider, ''), ip_reputation.provider),
                        status = 'BLACKLISTED',
                        blacklisted = 1,
                        blacklisted_at = CURRENT_TIMESTAMP,
                        blacklist_reason = excluded.blacklist_reason,
                        manually_blacklisted = CASE
                            WHEN excluded.manually_blacklisted = 1 THEN 1
                            ELSE ip_reputation.manually_blacklisted
                        END,
                        last_seen = CURRENT_TIMESTAMP
                """, (
                    ip_address,
                    ip_parts["ip_label"] or ip_address,
                    ip_parts["city"],
                    ip_parts["country"],
                    ip_parts["provider"],
                    reason,
                    manually_blacklisted
                ))

                if record_event:
                    cursor.execute("""
                        INSERT INTO analytics_events (
                            ip_address,
                            ip_label,
                            ip_status,
                            event_type,
                            details
                        )
                        VALUES (?, ?, 'BLACKLISTED', 'IP_BLACKLISTED', ?)
                    """, (
                        ip_address,
                        ip_parts["ip_label"] or ip_address,
                        reason
                    ))

                row = cursor.execute(
                    "SELECT * FROM ip_reputation WHERE ip_address = ?",
                    (ip_address,)
                ).fetchone()
                conn.commit()

            print(f"[Blacklist] ✅ IP blacklisted: {ip_address} | reason={reason}")
            return {"ok": True, "ip": ip_address, "row": dict(row) if row else None}

        except Exception as e:
            print(f"[Blacklist] ❌ Could not blacklist IP {ip_address}: {e}")
            return {"ok": False, "error": str(e), "ip": ip_address}

    def remove_ip_from_blacklist(self, ip_label_or_ip):
        """Removes an IP from the persistent blacklist but keeps reputation history."""
        ip_address = self._extract_ip_only(ip_label_or_ip)
        if not ip_address:
            return {"ok": False, "error": "Valid IPv4 address required."}

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE ip_reputation
                    SET
                        blacklisted = 0,
                        blacklisted_at = NULL,
                        blacklist_reason = '',
                        manually_blacklisted = 0,
                        status = CASE
                            WHEN status = 'BLACKLISTED' THEN 'UNKNOWN'
                            ELSE status
                        END,
                        last_seen = CURRENT_TIMESTAMP
                    WHERE ip_address = ?
                """, (ip_address,))

                cursor.execute("""
                    INSERT INTO analytics_events (
                        ip_address,
                        ip_label,
                        ip_status,
                        event_type,
                        details
                    )
                    VALUES (?, ?, 'UNKNOWN', 'IP_UNBLACKLISTED', 'Removed from blacklist')
                """, (ip_address, ip_address))
                conn.commit()

            print(f"[Blacklist] ✅ IP removed from blacklist: {ip_address}")
            return {"ok": True, "ip": ip_address}

        except Exception as e:
            print(f"[Blacklist] ❌ Could not remove IP {ip_address}: {e}")
            return {"ok": False, "error": str(e), "ip": ip_address}

    def get_blacklisted_ips(self):
        """Returns all active blacklist entries."""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                rows = cursor.execute("""
                    SELECT *
                    FROM ip_reputation
                    WHERE blacklisted = 1 OR status = 'BLACKLISTED'
                    ORDER BY blacklisted_at DESC, last_seen DESC
                """).fetchall()

            return [dict(r) for r in rows]

        except Exception as e:
            print(f"[Blacklist] ❌ Could not load blacklisted IPs: {e}")
            return []


    def _normalize_target_payload(self, payload, require_title=True):
        """Normalizes platform target form data from the dashboard."""
        payload = payload or {}

        platform = str(payload.get("platform", "")).strip().lower()
        target_type = str(payload.get("target_type", payload.get("targetType", ""))).strip().lower()
        title = str(payload.get("title", payload.get("name", ""))).strip()
        url = str(payload.get("url", "")).strip()
        identifier = str(payload.get("identifier", "")).strip()
        notes = str(payload.get("notes", "")).strip()

        try:
            priority = int(payload.get("priority", 5))
        except Exception:
            priority = 5
        priority = max(1, min(priority, 10))

        enabled_raw = payload.get("enabled", 1)
        if isinstance(enabled_raw, str):
            enabled = 0 if enabled_raw.strip().lower() in ["0", "false", "no", "off", "disabled"] else 1
        else:
            enabled = 1 if bool(enabled_raw) else 0

        allowed_platforms = {"youtube", "twitch", "spotify", "deezer"}
        if platform not in allowed_platforms:
            raise ValueError("platform must be youtube, twitch, spotify, or deezer")

        allowed_types = {
            "channel", "video", "playlist", "artist", "song", "track",
            "album", "category", "search", "keyword", "url", "other"
        }
        if target_type not in allowed_types:
            raise ValueError("target_type is not supported")

        if require_title and not title:
            raise ValueError("title/name is required")

        return {
            "platform": platform,
            "target_type": target_type,
            "title": title,
            "url": url,
            "identifier": identifier,
            "notes": notes,
            "priority": priority,
            "enabled": enabled
        }

    def add_platform_target(self, payload):
        """Adds a channel/song/artist/video/playlist target to the local focus list."""
        try:
            data = self._normalize_target_payload(payload, require_title=True)
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cur = cursor.execute("""
                    INSERT INTO platform_targets (
                        platform,
                        target_type,
                        title,
                        url,
                        identifier,
                        notes,
                        priority,
                        enabled,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (
                    data["platform"],
                    data["target_type"],
                    data["title"],
                    data["url"],
                    data["identifier"],
                    data["notes"],
                    data["priority"],
                    data["enabled"]
                ))
                target_id = cur.lastrowid
                row = cursor.execute("SELECT * FROM platform_targets WHERE id = ?", (target_id,)).fetchone()
                conn.commit()

            print(f"[Targets] Added {data['platform']} {data['target_type']}: {data['title']}")
            return {"ok": True, "target": dict(row)}

        except Exception as e:
            print(f"[Targets] Add target failed: {e}")
            return {"ok": False, "error": str(e)}

    def update_platform_target(self, target_id, payload):
        """Updates an existing platform target."""
        try:
            target_id = int(target_id)
            data = self._normalize_target_payload(payload, require_title=True)
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE platform_targets
                    SET
                        platform = ?,
                        target_type = ?,
                        title = ?,
                        url = ?,
                        identifier = ?,
                        notes = ?,
                        priority = ?,
                        enabled = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (
                    data["platform"],
                    data["target_type"],
                    data["title"],
                    data["url"],
                    data["identifier"],
                    data["notes"],
                    data["priority"],
                    data["enabled"],
                    target_id
                ))

                if cursor.rowcount == 0:
                    return {"ok": False, "error": "target not found"}

                row = cursor.execute("SELECT * FROM platform_targets WHERE id = ?", (target_id,)).fetchone()
                conn.commit()

            print(f"[Targets] Updated target {target_id}: {data['title']}")
            return {"ok": True, "target": dict(row)}

        except Exception as e:
            print(f"[Targets] Update target failed: {e}")
            return {"ok": False, "error": str(e)}

    def delete_platform_target(self, target_id):
        """Deletes one platform target from the focus list."""
        try:
            target_id = int(target_id)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM platform_targets WHERE id = ?", (target_id,))
                deleted = cursor.rowcount
                conn.commit()

            if deleted == 0:
                return {"ok": False, "error": "target not found"}

            print(f"[Targets] Deleted target {target_id}")
            return {"ok": True, "deleted": target_id}

        except Exception as e:
            print(f"[Targets] Delete target failed: {e}")
            return {"ok": False, "error": str(e)}

    def set_platform_target_enabled(self, target_id, enabled):
        """Enables/disables a target without deleting it."""
        try:
            target_id = int(target_id)
            enabled = 1 if bool(enabled) else 0
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE platform_targets
                    SET enabled = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (enabled, target_id))
                changed = cursor.rowcount
                conn.commit()

            if changed == 0:
                return {"ok": False, "error": "target not found"}
            return {"ok": True, "target_id": target_id, "enabled": enabled}

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_platform_targets(self, platform=None, target_type=None, enabled=None):
        """Returns dashboard-managed focus targets for channels/songs/artists/etc."""
        try:
            conditions = []
            values = []

            if platform:
                conditions.append("platform = ?")
                values.append(str(platform).strip().lower())

            if target_type:
                conditions.append("target_type = ?")
                values.append(str(target_type).strip().lower())

            if enabled is not None and str(enabled) != "":
                conditions.append("enabled = ?")
                values.append(1 if bool(enabled) and str(enabled).lower() not in ["0", "false", "no", "off"] else 0)

            where = ""
            if conditions:
                where = "WHERE " + " AND ".join(conditions)

            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                rows = cursor.execute(f"""
                    SELECT *
                    FROM platform_targets
                    {where}
                    ORDER BY
                        platform ASC,
                        enabled DESC,
                        priority DESC,
                        target_type ASC,
                        title COLLATE NOCASE ASC
                """, values).fetchall()

            return [dict(r) for r in rows]

        except Exception as e:
            print(f"[Targets] Load targets failed: {e}")
            return []

    def get_enabled_platform_targets(self, platform=None):
        """Future bot runner hook: returns only enabled focus targets."""
        return self.get_platform_targets(platform=platform, enabled=True)

    def ensure_safe_route_plan_tables(self):
        """Creates the saved route plan table when older databases do not have it yet."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS safe_route_plans (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        source TEXT DEFAULT 'safe_route_plan',
                        active_platforms_json TEXT DEFAULT '[]',
                        profile_count INTEGER DEFAULT 0,
                        platforms_per_profile INTEGER DEFAULT 0,
                        plan_json TEXT DEFAULT '{}',
                        summary_json TEXT DEFAULT '{}'
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_safe_route_plans_created_at
                    ON safe_route_plans(created_at)
                """)
                conn.commit()
            return True
        except Exception as e:
            print(f"[RoutePlan] Could not ensure safe_route_plans table: {e}")
            return False

    def save_safe_route_plan(self, active_platforms, plan, summary, source="safe_route_plan"):
        """Persists a generated safe planning report without executing browser navigation."""
        try:
            self.ensure_safe_route_plan_tables()
            active_platforms = active_platforms if isinstance(active_platforms, list) else []
            plan = plan if isinstance(plan, list) else []
            summary = summary if isinstance(summary, dict) else {}

            profile_count = int(summary.get("profile_count") or len(plan) or 0)
            platforms_per_profile = int(summary.get("platforms_per_profile") or 0)

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cur = cursor.execute("""
                    INSERT INTO safe_route_plans (
                        source,
                        active_platforms_json,
                        profile_count,
                        platforms_per_profile,
                        plan_json,
                        summary_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    str(source or "safe_route_plan"),
                    json.dumps(active_platforms, ensure_ascii=True),
                    profile_count,
                    platforms_per_profile,
                    json.dumps(plan, ensure_ascii=True),
                    json.dumps(summary, ensure_ascii=True)
                ))
                plan_id = cur.lastrowid
                conn.commit()

            return {"ok": True, "route_plan_id": plan_id}

        except Exception as e:
            print(f"[RoutePlan] Save failed: {e}")
            return {"ok": False, "error": str(e)}

    def get_safe_route_plan_history(self, limit=10):
        """Returns recent safe route plan snapshots for dashboard review."""
        try:
            self.ensure_safe_route_plan_tables()
            try:
                limit = int(limit)
            except Exception:
                limit = 10
            limit = max(1, min(limit, 100))

            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT *
                    FROM safe_route_plans
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                """, (limit,)).fetchall()

            history = []
            for row in rows:
                item = dict(row)
                json_defaults = {
                    "active_platforms_json": [],
                    "plan_json": [],
                    "summary_json": {}
                }
                for json_key, default_value in json_defaults.items():
                    parsed_key = json_key.replace("_json", "")
                    try:
                        raw_value = item.get(json_key)
                        item[parsed_key] = json.loads(raw_value) if raw_value else default_value
                    except Exception:
                        item[parsed_key] = default_value
                history.append(item)

            return {"ok": True, "history": history}

        except Exception as e:
            print(f"[RoutePlan] History load failed: {e}")
            return {"ok": False, "error": str(e), "history": []}

    def validate_platform_targets(self, platform=None):
        """Checks saved Targets rows for missing fields and obvious URL/platform mismatches."""
        allowed_platforms = {"youtube", "twitch", "spotify", "deezer"}
        allowed_types = {
            "channel", "video", "playlist", "artist", "song", "track",
            "album", "category", "search", "keyword", "url", "other"
        }
        platform_hosts = {
            "youtube": ["youtube.com", "youtu.be"],
            "twitch": ["twitch.tv"],
            "spotify": ["spotify.com", "open.spotify.com"],
            "deezer": ["deezer.com"]
        }

        try:
            rows = self.get_platform_targets(platform=platform)
            validated = []
            error_count = 0
            warning_count = 0
            valid_count = 0

            for row in rows:
                issues = []
                status = "valid"
                target_platform = str(row.get("platform") or "").strip().lower()
                target_type = str(row.get("target_type") or "").strip().lower()
                title = str(row.get("title") or "").strip()
                url = str(row.get("url") or "").strip()
                identifier = str(row.get("identifier") or "").strip()
                enabled = int(row.get("enabled") or 0) == 1

                def add_issue(level, message):
                    issues.append({"level": level, "message": message})

                if not title:
                    add_issue("error", "Missing name/title.")

                if target_platform not in allowed_platforms:
                    add_issue("error", "Unsupported platform.")

                if target_type not in allowed_types:
                    add_issue("error", "Unsupported target type.")

                if url:
                    parsed = urllib.parse.urlparse(url if "://" in url else "https://" + url)
                    host = (parsed.netloc or "").lower()
                    if not host:
                        add_issue("error", "URL does not include a valid host.")
                    elif target_platform in platform_hosts:
                        if not any(host == expected or host.endswith("." + expected) for expected in platform_hosts[target_platform]):
                            add_issue("warning", f"URL host '{host}' does not look like {target_platform}.")
                elif target_type in {"channel", "video", "playlist", "artist", "song", "track", "album", "url"} and not identifier:
                    add_issue("warning", "No URL or identifier is saved for this target.")

                if not enabled:
                    add_issue("info", "Target is disabled.")

                levels = {issue["level"] for issue in issues}
                if "error" in levels:
                    status = "error"
                    error_count += 1
                elif "warning" in levels:
                    status = "warning"
                    warning_count += 1
                else:
                    valid_count += 1

                checked = dict(row)
                checked["validation_status"] = status
                checked["validation_issues"] = issues
                validated.append(checked)

            return {
                "ok": True,
                "summary": {
                    "total": len(validated),
                    "valid": valid_count,
                    "warnings": warning_count,
                    "errors": error_count
                },
                "rows": validated
            }

        except Exception as e:
            print(f"[Targets] Validation failed: {e}")
            return {"ok": False, "error": str(e), "summary": {}, "rows": []}

    def ensure_learning_autoscale_tables(self):
        """Creates local learning/autoscale tables for older databases."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bot_settings (
                        key TEXT PRIMARY KEY,
                        value_json TEXT DEFAULT '{}',
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ml_observations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        source TEXT DEFAULT '',
                        event_type TEXT DEFAULT '',
                        profile_id INTEGER,
                        session_id TEXT DEFAULT '',
                        action TEXT DEFAULT '',
                        action_result TEXT DEFAULT '',
                        reward REAL DEFAULT 0.0,
                        cpu_percent REAL DEFAULT 0.0,
                        ram_percent REAL DEFAULT 0.0,
                        gpu_percent REAL DEFAULT 0.0,
                        active_profiles INTEGER DEFAULT 0,
                        target_profiles INTEGER DEFAULT 0,
                        details_json TEXT DEFAULT '{}'
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ml_observations_created_at
                    ON ml_observations(created_at)
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS autoscale_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        source TEXT DEFAULT '',
                        mode TEXT DEFAULT 'manual',
                        enabled INTEGER DEFAULT 0,
                        action TEXT DEFAULT 'hold',
                        reason TEXT DEFAULT '',
                        active_profiles INTEGER DEFAULT 0,
                        desired_profiles INTEGER DEFAULT 0,
                        safe_limit INTEGER DEFAULT 0,
                        cpu_percent REAL DEFAULT 0.0,
                        ram_percent REAL DEFAULT 0.0,
                        gpu_percent REAL DEFAULT 0.0,
                        launch_ids_json TEXT DEFAULT '[]',
                        close_ids_json TEXT DEFAULT '[]',
                        details_json TEXT DEFAULT '{}'
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_autoscale_events_created_at
                    ON autoscale_events(created_at)
                """)
                conn.commit()
            return True
        except Exception as e:
            print(f"[Learning] Could not ensure tables: {e}")
            return False

    def get_bot_setting(self, key, default=None):
        try:
            self.ensure_learning_autoscale_tables()
            key = str(key or "").strip()
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT value_json FROM bot_settings WHERE key = ?",
                    (key,)
                ).fetchone()
            if not row:
                return default
            value = row[0] if isinstance(row, tuple) else row["value_json"]
            return json.loads(value or "{}")
        except Exception:
            return default

    def set_bot_setting(self, key, value):
        try:
            self.ensure_learning_autoscale_tables()
            key = str(key or "").strip()
            value_json = json.dumps(value if value is not None else {}, ensure_ascii=True, default=str)
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO bot_settings (key, value_json, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET
                        value_json = excluded.value_json,
                        updated_at = CURRENT_TIMESTAMP
                """, (key, value_json))
                conn.commit()
            return {"ok": True, "key": key}
        except Exception as e:
            print(f"[Learning] Could not save setting {key}: {e}")
            return {"ok": False, "error": str(e)}

    def default_autoscale_config(self):
        return {
            "enabled": False,
            "mode": "manual_profile_scaling",
            "target_profiles": 3,
            "min_profiles": 0,
            "max_profiles": 10,
            "scale_up_step": 1,
            "scale_down_step": 1,
            "cooldown_seconds": 90,
            "loop_interval_seconds": 30,
            "cpu_high": 82,
            "ram_high": 88,
            "gpu_high": 92,
            "cpu_low": 68,
            "ram_low": 78,
            "gpu_low": 85,
            "manual_mode_only": True,
            "close_autoscale_only": True
        }

    def get_autoscale_config(self):
        config = self.default_autoscale_config()
        saved = self.get_bot_setting("autoscale_config", {})
        if isinstance(saved, dict):
            config.update(saved)

        for key in ["target_profiles", "min_profiles", "max_profiles", "scale_up_step", "scale_down_step", "cooldown_seconds", "loop_interval_seconds"]:
            try:
                config[key] = int(config.get(key))
            except Exception:
                config[key] = self.default_autoscale_config()[key]

        for key in ["cpu_high", "ram_high", "gpu_high", "cpu_low", "ram_low", "gpu_low"]:
            try:
                config[key] = float(config.get(key))
            except Exception:
                config[key] = self.default_autoscale_config()[key]

        config["target_profiles"] = max(0, min(500, config["target_profiles"]))
        config["min_profiles"] = max(0, min(config["target_profiles"], config["min_profiles"]))
        config["max_profiles"] = max(config["min_profiles"], min(500, config["max_profiles"]))
        config["scale_up_step"] = max(1, min(25, config["scale_up_step"]))
        config["scale_down_step"] = max(1, min(25, config["scale_down_step"]))
        config["cooldown_seconds"] = max(15, min(3600, config["cooldown_seconds"]))
        config["loop_interval_seconds"] = max(10, min(600, config["loop_interval_seconds"]))
        config["enabled"] = bool(config.get("enabled"))
        config["manual_mode_only"] = bool(config.get("manual_mode_only", True))
        config["close_autoscale_only"] = bool(config.get("close_autoscale_only", True))
        return config

    def set_autoscale_config(self, updates):
        config = self.get_autoscale_config()
        updates = updates if isinstance(updates, dict) else {}
        allowed = set(config.keys())
        for key, value in updates.items():
            if key in allowed:
                config[key] = value
        config["enabled"] = bool(config.get("enabled"))
        self.set_bot_setting("autoscale_config", config)
        return {"ok": True, "config": self.get_autoscale_config()}

    def record_ml_observation(self, payload=None):
        try:
            self.ensure_learning_autoscale_tables()
            data = payload if isinstance(payload, dict) else {}
            details = data.get("details")
            if details is None:
                details = data
            with self._get_connection() as conn:
                cur = conn.execute("""
                    INSERT INTO ml_observations (
                        source, event_type, profile_id, session_id, action,
                        action_result, reward, cpu_percent, ram_percent,
                        gpu_percent, active_profiles, target_profiles, details_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(data.get("source") or ""),
                    str(data.get("event_type") or ""),
                    data.get("profile_id"),
                    str(data.get("session_id") or ""),
                    str(data.get("action") or ""),
                    str(data.get("action_result") or ""),
                    float(data.get("reward") or 0.0),
                    float(data.get("cpu_percent") or 0.0),
                    float(data.get("ram_percent") or 0.0),
                    float(data.get("gpu_percent") or 0.0),
                    int(data.get("active_profiles") or 0),
                    int(data.get("target_profiles") or 0),
                    json.dumps(details, ensure_ascii=True, default=str)
                ))
                conn.commit()
                row_id = cur.lastrowid
            return {"ok": True, "id": row_id}
        except Exception as e:
            print(f"[Learning] Observation save failed: {e}")
            return {"ok": False, "error": str(e)}

    def record_autoscale_event(self, payload=None):
        try:
            self.ensure_learning_autoscale_tables()
            data = payload if isinstance(payload, dict) else {}
            launch_ids = data.get("launch_ids") if isinstance(data.get("launch_ids"), list) else []
            close_ids = data.get("close_ids") if isinstance(data.get("close_ids"), list) else []
            details = data.get("details")
            if details is None:
                details = data
            with self._get_connection() as conn:
                cur = conn.execute("""
                    INSERT INTO autoscale_events (
                        source, mode, enabled, action, reason, active_profiles,
                        desired_profiles, safe_limit, cpu_percent, ram_percent,
                        gpu_percent, launch_ids_json, close_ids_json, details_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(data.get("source") or ""),
                    str(data.get("mode") or "manual"),
                    1 if bool(data.get("enabled")) else 0,
                    str(data.get("action") or "hold"),
                    str(data.get("reason") or ""),
                    int(data.get("active_profiles") or 0),
                    int(data.get("desired_profiles") or 0),
                    int(data.get("safe_limit") or 0),
                    float(data.get("cpu_percent") or 0.0),
                    float(data.get("ram_percent") or 0.0),
                    float(data.get("gpu_percent") or 0.0),
                    json.dumps(launch_ids, ensure_ascii=True),
                    json.dumps(close_ids, ensure_ascii=True),
                    json.dumps(details, ensure_ascii=True, default=str)
                ))
                conn.commit()
                row_id = cur.lastrowid
            return {"ok": True, "id": row_id}
        except Exception as e:
            print(f"[Autoscale] Event save failed: {e}")
            return {"ok": False, "error": str(e)}

    def get_learning_summary(self, limit=20):
        try:
            self.ensure_learning_autoscale_tables()
            limit = max(1, min(200, int(limit or 20)))
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                obs_rows = conn.execute("""
                    SELECT *
                    FROM ml_observations
                    ORDER BY id DESC
                    LIMIT ?
                """, (limit,)).fetchall()
                auto_rows = conn.execute("""
                    SELECT *
                    FROM autoscale_events
                    ORDER BY id DESC
                    LIMIT ?
                """, (limit,)).fetchall()
                obs_count = conn.execute("SELECT COUNT(*) FROM ml_observations").fetchone()[0]
                auto_count = conn.execute("SELECT COUNT(*) FROM autoscale_events").fetchone()[0]
                avg_reward = conn.execute("SELECT AVG(reward) FROM ml_observations").fetchone()[0]

            observations = [dict(r) for r in obs_rows]
            autoscale_events = []
            for row in auto_rows:
                item = dict(row)
                for key, default_value in [("launch_ids_json", []), ("close_ids_json", []), ("details_json", {})]:
                    parsed_key = key.replace("_json", "")
                    try:
                        item[parsed_key] = json.loads(item.get(key) or ("{}" if isinstance(default_value, dict) else "[]"))
                    except Exception:
                        item[parsed_key] = default_value
                autoscale_events.append(item)

            recommendations = []
            if auto_count == 0:
                recommendations.append("Run autoscale in DRY RUN first to collect baseline decisions.")
            if obs_count < 25:
                recommendations.append("Collect at least 25 observations before trusting learned recommendations.")
            if avg_reward is not None and float(avg_reward) < 0:
                recommendations.append("Average reward is negative. Lower target profiles or raise cooldown.")

            return {
                "ok": True,
                "summary": {
                    "observation_count": int(obs_count or 0),
                    "autoscale_event_count": int(auto_count or 0),
                    "average_reward": round(float(avg_reward or 0.0), 3)
                },
                "observations": observations,
                "autoscale_events": autoscale_events,
                "recommendations": recommendations
            }
        except Exception as e:
            print(f"[Learning] Summary failed: {e}")
            return {"ok": False, "error": str(e), "summary": {}, "observations": [], "autoscale_events": [], "recommendations": []}

    def ensure_profile_lifecycle_tables(self):
        """Creates local profile lifecycle tables for older databases."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS profile_lifecycle_state (
                        profile_id INTEGER PRIMARY KEY,
                        session_id TEXT DEFAULT '',
                        state TEXT DEFAULT 'OFFLINE',
                        status TEXT DEFAULT '',
                        stage TEXT DEFAULT '',
                        target_platform TEXT DEFAULT '',
                        ip_address TEXT DEFAULT '',
                        source TEXT DEFAULT '',
                        severity TEXT DEFAULT 'info',
                        entered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        details_json TEXT DEFAULT '{}'
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS profile_lifecycle_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        profile_id INTEGER,
                        session_id TEXT DEFAULT '',
                        state TEXT DEFAULT '',
                        status TEXT DEFAULT '',
                        stage TEXT DEFAULT '',
                        target_platform TEXT DEFAULT '',
                        ip_address TEXT DEFAULT '',
                        source TEXT DEFAULT '',
                        severity TEXT DEFAULT 'info',
                        elapsed_seconds INTEGER DEFAULT 0,
                        details_json TEXT DEFAULT '{}'
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_profile_lifecycle_events_created_at
                    ON profile_lifecycle_events(created_at)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_profile_lifecycle_events_profile
                    ON profile_lifecycle_events(profile_id, created_at)
                """)
                conn.commit()
            return True
        except Exception as e:
            print(f"[Lifecycle] Could not ensure tables: {e}")
            return False

    def record_profile_lifecycle(self, payload=None):
        """
        Records a deduplicated lifecycle state and optional event row.

        This is local observability only. It does not launch, stop, or alter
        browser automation behavior.
        """
        try:
            self.ensure_profile_lifecycle_tables()
            data = payload if isinstance(payload, dict) else {}
            profile_id = data.get("profile_id")
            if profile_id is None:
                return {"ok": False, "error": "profile_id is required"}

            profile_id = int(profile_id)
            details = data.get("details")
            if details is None:
                details = {}
            if not isinstance(details, dict):
                details = {"value": details}

            state = str(data.get("state") or "UNKNOWN").strip().upper()
            status = str(data.get("status") or "").strip()
            stage = str(data.get("stage") or "").strip()
            target_platform = str(data.get("target_platform") or "").strip()
            ip_address = str(data.get("ip_address") or "").strip()
            session_id = str(data.get("session_id") or "").strip()
            source = str(data.get("source") or "backend").strip()
            severity = str(data.get("severity") or "info").strip().lower()
            elapsed_seconds = int(float(data.get("elapsed_seconds") or 0))
            force_event = bool(data.get("force_event") or details.get("force_event"))
            details_json = json.dumps(details, ensure_ascii=True, default=str)

            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                prior = conn.execute(
                    """
                    SELECT *
                    FROM profile_lifecycle_state
                    WHERE profile_id = ?
                    """,
                    (profile_id,)
                ).fetchone()

                changed = force_event or prior is None
                state_changed = prior is None
                if prior is not None:
                    state_changed = str(prior["state"] or "").upper() != state
                    changed = changed or state_changed
                    changed = changed or str(prior["status"] or "") != status
                    changed = changed or str(prior["stage"] or "") != stage
                    changed = changed or str(prior["target_platform"] or "") != target_platform
                    changed = changed or str(prior["ip_address"] or "") != ip_address
                    changed = changed or str(prior["session_id"] or "") != session_id
                    changed = changed or str(prior["severity"] or "") != severity

                if prior is None:
                    conn.execute("""
                        INSERT INTO profile_lifecycle_state (
                            profile_id, session_id, state, status, stage,
                            target_platform, ip_address, source, severity,
                            details_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        profile_id,
                        session_id,
                        state,
                        status,
                        stage,
                        target_platform,
                        ip_address,
                        source,
                        severity,
                        details_json
                    ))
                elif state_changed:
                    conn.execute("""
                        UPDATE profile_lifecycle_state
                        SET session_id = ?,
                            state = ?,
                            status = ?,
                            stage = ?,
                            target_platform = ?,
                            ip_address = ?,
                            source = ?,
                            severity = ?,
                            entered_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP,
                            last_seen_at = CURRENT_TIMESTAMP,
                            details_json = ?
                        WHERE profile_id = ?
                    """, (
                        session_id,
                        state,
                        status,
                        stage,
                        target_platform,
                        ip_address,
                        source,
                        severity,
                        details_json,
                        profile_id
                    ))
                else:
                    conn.execute("""
                        UPDATE profile_lifecycle_state
                        SET session_id = ?,
                            status = ?,
                            stage = ?,
                            target_platform = ?,
                            ip_address = ?,
                            source = ?,
                            severity = ?,
                            updated_at = CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE updated_at END,
                            last_seen_at = CURRENT_TIMESTAMP,
                            details_json = CASE WHEN ? THEN ? ELSE details_json END
                        WHERE profile_id = ?
                    """, (
                        session_id,
                        status,
                        stage,
                        target_platform,
                        ip_address,
                        source,
                        severity,
                        1 if changed else 0,
                        1 if changed else 0,
                        details_json,
                        profile_id
                    ))

                inserted = False
                if changed:
                    conn.execute("""
                        INSERT INTO profile_lifecycle_events (
                            profile_id, session_id, state, status, stage,
                            target_platform, ip_address, source, severity,
                            elapsed_seconds, details_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        profile_id,
                        session_id,
                        state,
                        status,
                        stage,
                        target_platform,
                        ip_address,
                        source,
                        severity,
                        elapsed_seconds,
                        details_json
                    ))
                    inserted = True

                conn.commit()

            return {"ok": True, "inserted": inserted, "state": state}
        except Exception as e:
            print(f"[Lifecycle] Record failed: {e}")
            return {"ok": False, "error": str(e)}

    def get_profile_lifecycle_snapshot(self, limit_events=60):
        """Returns latest profile lifecycle states and recent lifecycle events."""
        try:
            self.ensure_profile_lifecycle_tables()
            limit_events = max(1, min(300, int(limit_events or 60)))
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                state_rows = conn.execute("""
                    SELECT *
                    FROM profile_lifecycle_state
                    ORDER BY profile_id ASC
                """).fetchall()
                event_rows = conn.execute("""
                    SELECT *
                    FROM profile_lifecycle_events
                    ORDER BY id DESC
                    LIMIT ?
                """, (limit_events,)).fetchall()

            states = []
            state_counts = {}
            severity_counts = {}
            for row in state_rows:
                item = dict(row)
                try:
                    item["details"] = json.loads(item.get("details_json") or "{}")
                except Exception:
                    item["details"] = {}
                state = str(item.get("state") or "UNKNOWN").upper()
                severity = str(item.get("severity") or "info").lower()
                state_counts[state] = state_counts.get(state, 0) + 1
                severity_counts[severity] = severity_counts.get(severity, 0) + 1
                states.append(item)

            events = []
            for row in event_rows:
                item = dict(row)
                try:
                    item["details"] = json.loads(item.get("details_json") or "{}")
                except Exception:
                    item["details"] = {}
                events.append(item)

            return {
                "ok": True,
                "summary": {
                    "tracked_profiles": len(states),
                    "state_counts": state_counts,
                    "severity_counts": severity_counts,
                    "event_count_returned": len(events)
                },
                "states": states,
                "events": events
            }
        except Exception as e:
            print(f"[Lifecycle] Snapshot failed: {e}")
            return {"ok": False, "error": str(e), "summary": {}, "states": [], "events": []}


    def delete_profiles(self, profile_ids):
        """Permanently erases profiles from the database."""
        if not profile_ids:
            return

        placeholders = ",".join(["?"] * len(profile_ids))
        query = f"DELETE FROM profiles WHERE id IN ({placeholders})"

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, profile_ids)
                conn.commit()

            print(f"[Database] 🗑️ Wiped {len(profile_ids)} profile(s) from existence.")

        except Exception as e:
            print(f"[Database Error] Deletion failed: {e}")

    # ==============================
    # IP Alignment Region Config
    # ==============================

    def set_profile_region_config(self, profile_id, country="", timezone="", language="", dns_region="", strict=False):
        """Save expected region config for a profile (used by alignment enforcement after IP verification)."""
        try:
            profile_id = int(profile_id)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                self._add_column_if_missing(cursor, "profiles", "expected_country", "TEXT DEFAULT ''")
                self._add_column_if_missing(cursor, "profiles", "expected_timezone", "TEXT DEFAULT ''")
                self._add_column_if_missing(cursor, "profiles", "expected_language", "TEXT DEFAULT ''")
                self._add_column_if_missing(cursor, "profiles", "expected_dns_region", "TEXT DEFAULT ''")
                self._add_column_if_missing(cursor, "profiles", "alignment_strict", "INTEGER DEFAULT 0")
                cursor.execute("""
                    UPDATE profiles
                    SET expected_country = ?,
                        expected_timezone = ?,
                        expected_language = ?,
                        expected_dns_region = ?,
                        alignment_strict = ?
                    WHERE id = ?
                """, (
                    str(country or ""),
                    str(timezone or ""),
                    str(language or ""),
                    str(dns_region or ""),
                    1 if strict else 0,
                    profile_id
                ))
                conn.commit()
            return {"ok": True, "profile_id": profile_id}
        except Exception as e:
            print(f"[Database] ❌ set_profile_region_config failed for {profile_id}: {e}")
            return {"ok": False, "error": str(e)}

    def get_profile_region_config(self, profile_id):
        """Get expected region config for a profile. Returns None if profile not found."""
        try:
            profile_id = int(profile_id)
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                row = cursor.execute("""
                    SELECT expected_country, expected_timezone, expected_language,
                           expected_dns_region, alignment_strict
                    FROM profiles
                    WHERE id = ?
                """, (profile_id,)).fetchone()
            if not row:
                return None
            return {
                "expected_country": row["expected_country"] or "",
                "expected_timezone": row["expected_timezone"] or "",
                "expected_language": row["expected_language"] or "",
                "expected_dns_region": row["expected_dns_region"] or "",
                "alignment_strict": bool(row["alignment_strict"])
            }
        except Exception as e:
            print(f"[Database] ❌ get_profile_region_config failed for {profile_id}: {e}")
            return None

