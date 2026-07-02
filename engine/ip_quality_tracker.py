"""
IP Quality Tracker
Tracks per-IP, per-platform ad detection results and bans IPs that
never show ads on a platform (strong signal the IP is blacklisted there).
"""

import sqlite3
import threading
import time
from datetime import datetime


_DB_PATH   = "data/ip_quality.db"
_LOCK      = threading.Lock()

# How many no-ad sessions in a row before banning an IP on a platform
_BAN_THRESHOLD = 3


def _connect():
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ip_platform_quality (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ip              TEXT    NOT NULL,
            platform        TEXT    NOT NULL,
            sessions_total  INTEGER NOT NULL DEFAULT 0,
            ads_seen        INTEGER NOT NULL DEFAULT 0,
            no_ads_streak   INTEGER NOT NULL DEFAULT 0,
            banned          INTEGER NOT NULL DEFAULT 0,
            banned_reason   TEXT,
            first_seen      TEXT,
            last_seen       TEXT,
            UNIQUE(ip, platform)
        );

        CREATE TABLE IF NOT EXISTS ip_quality_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ip              TEXT    NOT NULL,
            platform        TEXT    NOT NULL,
            session_id      TEXT,
            ads_detected    INTEGER NOT NULL DEFAULT 0,
            page_type       TEXT,
            note            TEXT,
            recorded_at     TEXT    NOT NULL
        );
    """)
    conn.commit()


class IPQualityTracker:
    """
    Records per-IP, per-platform ad-presence results.
    After _BAN_THRESHOLD consecutive no-ad sessions, the IP is
    banned on that platform and will not be selected again for it.
    """

    def __init__(self, db_path=None):
        self._db_path = db_path or _DB_PATH
        with _LOCK:
            conn = self._conn()
            _ensure_schema(conn)
            conn.close()

    def _conn(self):
        conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_session(self, ip, platform, ads_detected, session_id="", page_type="", note=""):
        """
        Call after every platform session.

        ads_detected=True  → IP is working normally on this platform
        ads_detected=False → no ads seen; one step closer to ban
        """
        if not ip or not platform:
            return

        ip       = str(ip).strip().lower()
        platform = str(platform).strip().lower()
        now      = datetime.utcnow().isoformat(timespec="seconds") + "Z"

        with _LOCK:
            conn = self._conn()
            try:
                # Upsert quality row
                conn.execute("""
                    INSERT INTO ip_platform_quality
                        (ip, platform, sessions_total, ads_seen, no_ads_streak,
                         banned, first_seen, last_seen)
                    VALUES (?, ?, 1, ?, ?, 0, ?, ?)
                    ON CONFLICT(ip, platform) DO UPDATE SET
                        sessions_total = sessions_total + 1,
                        ads_seen       = ads_seen + ?,
                        no_ads_streak  = CASE WHEN ? = 1 THEN 0
                                              ELSE no_ads_streak + 1 END,
                        last_seen      = ?
                """, (
                    ip, platform,
                    1 if ads_detected else 0,
                    0 if ads_detected else 1,
                    now, now,
                    1 if ads_detected else 0,
                    1 if ads_detected else 0,
                    now,
                ))

                # Log entry
                conn.execute("""
                    INSERT INTO ip_quality_log
                        (ip, platform, session_id, ads_detected, page_type, note, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    ip, platform,
                    session_id or "",
                    1 if ads_detected else 0,
                    page_type or "",
                    note or "",
                    now,
                ))

                conn.commit()

                # Check whether to auto-ban
                row = conn.execute(
                    "SELECT no_ads_streak, banned FROM ip_platform_quality WHERE ip=? AND platform=?",
                    (ip, platform)
                ).fetchone()

                if row and not row["banned"] and row["no_ads_streak"] >= _BAN_THRESHOLD:
                    self._ban(conn, ip, platform,
                              f"No ads detected in {row['no_ads_streak']} consecutive sessions")

                conn.commit()
            finally:
                conn.close()

        status = "ads_seen" if ads_detected else "no_ads"
        print(f"[IPQuality] {ip} | {platform.upper()} | {status}")

    def is_banned(self, ip, platform):
        """Returns True if this IP is banned on the given platform."""
        if not ip or not platform:
            return False
        ip       = str(ip).strip().lower()
        platform = str(platform).strip().lower()
        with _LOCK:
            conn = self._conn()
            try:
                row = conn.execute(
                    "SELECT banned FROM ip_platform_quality WHERE ip=? AND platform=?",
                    (ip, platform)
                ).fetchone()
                return bool(row and row["banned"])
            finally:
                conn.close()

    def ban_ip(self, ip, platform, reason="manual ban"):
        """Manually ban an IP on a specific platform."""
        ip       = str(ip).strip().lower()
        platform = str(platform).strip().lower()
        with _LOCK:
            conn = self._conn()
            try:
                _ensure_schema(conn)
                self._ban(conn, ip, platform, reason)
                conn.commit()
            finally:
                conn.close()

    def get_good_ips_for_platform(self, platform):
        """
        Returns list of IPs that have at least one confirmed ad-seen session
        and are not banned on this platform.
        """
        platform = str(platform).strip().lower()
        with _LOCK:
            conn = self._conn()
            try:
                rows = conn.execute("""
                    SELECT ip, sessions_total, ads_seen, no_ads_streak, last_seen
                    FROM ip_platform_quality
                    WHERE platform = ?
                      AND banned   = 0
                      AND ads_seen > 0
                    ORDER BY ads_seen DESC, last_seen DESC
                """, (platform,)).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_banned_ips_for_platform(self, platform):
        """Returns all banned IPs for a platform with ban reasons."""
        platform = str(platform).strip().lower()
        with _LOCK:
            conn = self._conn()
            try:
                rows = conn.execute("""
                    SELECT ip, sessions_total, ads_seen, no_ads_streak,
                           banned_reason, last_seen
                    FROM ip_platform_quality
                    WHERE platform = ? AND banned = 1
                    ORDER BY last_seen DESC
                """, (platform,)).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_ip_report(self, ip):
        """Full report for a single IP across all platforms."""
        ip = str(ip).strip().lower()
        with _LOCK:
            conn = self._conn()
            try:
                rows = conn.execute("""
                    SELECT platform, sessions_total, ads_seen, no_ads_streak,
                           banned, banned_reason, first_seen, last_seen
                    FROM ip_platform_quality
                    WHERE ip = ?
                    ORDER BY platform
                """, (ip,)).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_platform_summary(self):
        """Returns a summary table: platform → {total, good, banned, untested}."""
        with _LOCK:
            conn = self._conn()
            try:
                rows = conn.execute("""
                    SELECT platform,
                           COUNT(*)                              AS total_ips,
                           SUM(CASE WHEN banned=0 AND ads_seen>0 THEN 1 ELSE 0 END) AS good_ips,
                           SUM(CASE WHEN banned=1              THEN 1 ELSE 0 END) AS banned_ips,
                           SUM(CASE WHEN banned=0 AND ads_seen=0 THEN 1 ELSE 0 END) AS untested_ips
                    FROM ip_platform_quality
                    GROUP BY platform
                    ORDER BY platform
                """).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_recent_log(self, limit=100):
        """Last N log entries across all IPs and platforms."""
        with _LOCK:
            conn = self._conn()
            try:
                rows = conn.execute("""
                    SELECT ip, platform, session_id, ads_detected,
                           page_type, note, recorded_at
                    FROM ip_quality_log
                    ORDER BY id DESC
                    LIMIT ?
                """, (limit,)).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ban(self, conn, ip, platform, reason):
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        conn.execute("""
            INSERT INTO ip_platform_quality
                (ip, platform, sessions_total, banned, banned_reason, first_seen, last_seen)
            VALUES (?, ?, 0, 1, ?, ?, ?)
            ON CONFLICT(ip, platform) DO UPDATE SET
                banned        = 1,
                banned_reason = ?,
                last_seen     = ?
        """, (ip, platform, reason, now, now, reason, now))
        conn.execute("""
            INSERT INTO ip_quality_log
                (ip, platform, session_id, ads_detected, note, recorded_at)
            VALUES (?, ?, '', 0, ?, ?)
        """, (ip, platform, f"BANNED: {reason}", now))
        print(f"[IPQuality] 🚫 BANNED {ip} on {platform.upper()}: {reason}")


# Module-level singleton
_tracker = None
_tracker_lock = threading.Lock()


def get_tracker(db_path=None):
    global _tracker
    with _tracker_lock:
        if _tracker is None:
            _tracker = IPQualityTracker(db_path)
    return _tracker
