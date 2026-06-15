import json
import socket
import time
import traceback
from datetime import datetime


class SessionRecorder:
    """
    Central session timeline recorder.

    Purpose:
    - Create one session_id per profile run.
    - Record every important step into analytics_events.
    - Update profile_sessions when the session starts/ends.
    - Keep this separate from GhostCore so browser launching does not become messy.

    This does NOT fake views, streams, ads, follows, likes, chats, or engagement.
    It only records what actually happened during a browser/profile session.
    """

    def __init__(self, db_manager, pc_id=None):
        self.db = db_manager
        self.pc_id = str(pc_id or socket.gethostname() or "LOCAL_PC").strip()
        self.session_cache = {}

    # ==============================
    # Core Helpers
    # ==============================

    def _now_iso(self):
        return datetime.now().isoformat(timespec="seconds")

    def _safe_platform(self, platform):
        value = str(platform or "").strip()
        return value if value else "Unknown"

    def _safe_details(self, details="", extra=None):
        base = {}

        if isinstance(details, dict):
            base.update(details)
        elif details:
            base["message"] = str(details)

        if isinstance(extra, dict):
            base.update(extra)

        if not base:
            return ""

        try:
            return json.dumps(base, ensure_ascii=False, default=str)
        except Exception:
            return str(base)

    def _safe_current_url(self, driver):
        try:
            return str(driver.current_url or "")
        except Exception:
            return ""

    def _safe_title(self, driver):
        try:
            return str(driver.title or "")
        except Exception:
            return ""

    def _safe_window_count(self, driver):
        try:
            return len(driver.window_handles or [])
        except Exception:
            return 0

    def _driver_snapshot(self, driver):
        if driver is None:
            return {}

        return {
            "url": self._safe_current_url(driver),
            "title": self._safe_title(driver),
            "window_count": self._safe_window_count(driver),
        }

    def _update_profile_session_fields(self, session_id, **fields):
        """
        Updates profile_sessions directly when needed.

        This is intentionally defensive. If the DB structure changes later,
        this method fails silently instead of crashing the browser session.
        """
        if not session_id or not fields:
            return False

        if not hasattr(self.db, "_get_connection"):
            return False

        allowed = {
            "platform",
            "starting_ip",
            "final_ip",
            "ip_status",
            "status",
            "close_reason",
            "estimated_revenue",
        }

        clean_fields = {}
        for key, value in fields.items():
            if key in allowed:
                clean_fields[key] = value

        if not clean_fields:
            return False

        try:
            assignments = []
            values = []

            for key, value in clean_fields.items():
                assignments.append(f"{key} = ?")
                values.append(value)

            values.append(session_id)

            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    UPDATE profile_sessions
                    SET {", ".join(assignments)}
                    WHERE session_id = ?
                    """,
                    values
                )
                conn.commit()

            return True

        except Exception as e:
            print(f"[SessionRecorder] Could not update profile_sessions for {session_id}: {e}")
            return False

    # ==============================
    # Session Lifecycle
    # ==============================

    def start(
        self,
        profile_id,
        platform="Pending",
        ip_label="",
        ip_status="UNKNOWN",
        mode="automation",
        details=""
    ):
        """
        Starts a profile session and returns session_id.

        Uses DatabaseManager.start_profile_session() if available.
        Falls back to a generated session_id if not.
        """
        profile_id = int(profile_id)
        platform = self._safe_platform(platform)

        try:
            if hasattr(self.db, "start_profile_session"):
                session_id = self.db.start_profile_session(
                    pc_id=self.pc_id,
                    profile_id=profile_id,
                    platform=platform,
                    ip_label=ip_label,
                    ip_status=ip_status
                )
            else:
                session_id = f"{self.pc_id}-{profile_id}-{int(time.time())}"
                self.event(
                    profile_id=profile_id,
                    session_id=session_id,
                    platform=platform,
                    ip_label=ip_label,
                    ip_status=ip_status,
                    event_type="SESSION_STARTED",
                    details="Fallback session start"
                )

            self.session_cache[profile_id] = {
                "session_id": session_id,
                "profile_id": profile_id,
                "platform": platform,
                "mode": mode,
                "ip_label": ip_label,
                "ip_status": ip_status,
                "started_at": time.time(),
                "last_event": "SESSION_STARTED",
            }

            self.event(
                profile_id=profile_id,
                session_id=session_id,
                platform=platform,
                ip_label=ip_label,
                ip_status=ip_status,
                event_type="SESSION_RECORDER_ATTACHED",
                details={
                    "mode": mode,
                    "platform": platform,
                    "details": details,
                    "timestamp": self._now_iso(),
                }
            )

            print(f"[SessionRecorder] ✅ Started session {session_id} for Profile {profile_id} | mode={mode} | platform={platform}")
            return session_id

        except Exception as e:
            session_id = f"{self.pc_id}-{profile_id}-{int(time.time())}"
            print(f"[SessionRecorder] ❌ Session start failed. Using fallback session_id={session_id}: {e}")

            self.session_cache[profile_id] = {
                "session_id": session_id,
                "profile_id": profile_id,
                "platform": platform,
                "mode": mode,
                "ip_label": ip_label,
                "ip_status": ip_status,
                "started_at": time.time(),
                "last_event": "SESSION_START_FAILED",
            }

            return session_id

    def end(
        self,
        profile_id,
        session_id=None,
        final_ip="",
        status="ENDED",
        close_reason="normal",
        platform="",
        estimated_revenue=0.0,
        details=""
    ):
        profile_id = int(profile_id)
        session_id = session_id or self.get_session_id(profile_id)
        platform = self._safe_platform(platform or self.get_platform(profile_id))

        if not session_id:
            return False

        try:
            self.event(
                profile_id=profile_id,
                session_id=session_id,
                platform=platform,
                ip_label=final_ip,
                ip_status=status,
                event_type="SESSION_ENDING",
                details={
                    "close_reason": close_reason,
                    "details": details,
                    "timestamp": self._now_iso(),
                }
            )

            if hasattr(self.db, "end_profile_session"):
                self.db.end_profile_session(
                    session_id=session_id,
                    final_ip=final_ip,
                    status=status,
                    close_reason=close_reason,
                    estimated_revenue=estimated_revenue
                )
            else:
                self._update_profile_session_fields(
                    session_id,
                    final_ip=final_ip,
                    status=status,
                    close_reason=close_reason,
                    estimated_revenue=float(estimated_revenue or 0.0)
                )

            self.event(
                profile_id=profile_id,
                session_id=session_id,
                platform=platform,
                ip_label=final_ip,
                ip_status=status,
                event_type="SESSION_ENDED",
                details={
                    "close_reason": close_reason,
                    "status": status,
                    "timestamp": self._now_iso(),
                }
            )

            self.session_cache.pop(profile_id, None)

            print(f"[SessionRecorder] ✅ Ended session {session_id} for Profile {profile_id} | reason={close_reason}")
            return True

        except Exception as e:
            print(f"[SessionRecorder] ❌ Could not end session {session_id}: {e}")
            return False

    # ==============================
    # Event Recording
    # ==============================

    def event(
        self,
        profile_id,
        session_id=None,
        platform="",
        ip_label="",
        ip_status="",
        event_type="EVENT",
        event_value=0.0,
        duration_seconds=0,
        details="",
        extra=None
    ):
        profile_id = int(profile_id)
        session_id = session_id or self.get_session_id(profile_id)
        platform = self._safe_platform(platform or self.get_platform(profile_id))
        event_type = str(event_type or "EVENT").strip().upper()

        if profile_id in self.session_cache:
            self.session_cache[profile_id]["last_event"] = event_type
            if platform and platform != "Unknown":
                self.session_cache[profile_id]["platform"] = platform
            if ip_label:
                self.session_cache[profile_id]["ip_label"] = ip_label
            if ip_status:
                self.session_cache[profile_id]["ip_status"] = ip_status

        if not hasattr(self.db, "record_analytics_event"):
            print(f"[SessionRecorder] {event_type} | Profile {profile_id} | {details}")
            return False

        try:
            self.db.record_analytics_event(
                profile_id=profile_id,
                pc_id=self.pc_id,
                session_id=session_id or "",
                platform=platform,
                ip_label=ip_label,
                ip_status=ip_status,
                event_type=event_type,
                event_value=event_value,
                duration_seconds=duration_seconds,
                details=self._safe_details(details, extra)
            )
            return True

        except Exception as e:
            print(f"[SessionRecorder] ❌ Event record failed: profile={profile_id}, event={event_type}, error={e}")
            return False

    def error(
        self,
        profile_id,
        session_id=None,
        platform="",
        error=None,
        event_type="SESSION_ERROR",
        details="",
        driver=None
    ):
        err_text = str(error or "")
        tb = traceback.format_exc()

        snapshot = self._driver_snapshot(driver)

        payload = {
            "error": err_text,
            "traceback": tb,
            "details": details,
            "browser": snapshot,
            "timestamp": self._now_iso(),
        }

        return self.event(
            profile_id=profile_id,
            session_id=session_id,
            platform=platform,
            event_type=event_type,
            details=payload
        )

    # ==============================
    # Specific Timeline Events
    # ==============================

    def browser_launched(self, profile_id, session_id=None, platform="", proc=None, debug_port=None, profile_dir=""):
        return self.event(
            profile_id=profile_id,
            session_id=session_id,
            platform=platform,
            event_type="BROWSER_LAUNCHED",
            details={
                "pid": getattr(proc, "pid", None),
                "debug_port": debug_port,
                "profile_dir": profile_dir,
            }
        )

    def selenium_attached(self, profile_id, session_id=None, platform="", driver=None, debug_port=None):
        return self.event(
            profile_id=profile_id,
            session_id=session_id,
            platform=platform,
            event_type="SELENIUM_ATTACHED",
            details={
                "debug_port": debug_port,
                "browser": self._driver_snapshot(driver),
            }
        )

    def ip_checking(self, profile_id, session_id=None, platform=""):
        return self.event(
            profile_id=profile_id,
            session_id=session_id,
            platform=platform,
            event_type="IP_CHECKING",
            details="Starting one-time browser IP verification"
        )

    def ip_verified(self, profile_id, session_id=None, platform="", ip_info=None):
        ip_info = ip_info or {}
        ip_label = str(ip_info.get("label") or ip_info.get("ip") or "").strip()

        self._update_profile_session_fields(
            session_id,
            starting_ip=ip_label,
            final_ip=ip_label,
            ip_status="OK"
        )

        return self.event(
            profile_id=profile_id,
            session_id=session_id,
            platform=platform,
            ip_label=ip_label,
            ip_status="OK",
            event_type="IP_VERIFIED",
            details={
                "ip": ip_info.get("ip"),
                "label": ip_label,
                "raw": ip_info.get("raw", {}),
            }
        )

    def ip_failed(self, profile_id, session_id=None, platform="", reason="", ip_info=None):
        ip_info = ip_info or {}
        ip_label = str(ip_info.get("label") or ip_info.get("ip") or "").strip()

        self._update_profile_session_fields(
            session_id,
            final_ip=ip_label,
            ip_status="FAILED",
            status="FAILED",
            close_reason=reason or "IP check failed"
        )

        return self.event(
            profile_id=profile_id,
            session_id=session_id,
            platform=platform,
            ip_label=ip_label,
            ip_status="FAILED",
            event_type="IP_CHECK_FAILED",
            details={
                "reason": reason,
                "ip": ip_info.get("ip"),
                "label": ip_label,
            }
        )

    def home_ip_blocked(self, profile_id, session_id=None, platform="", ip_info=None):
        ip_info = ip_info or {}
        ip_label = str(ip_info.get("label") or ip_info.get("ip") or "").strip()

        self._update_profile_session_fields(
            session_id,
            final_ip=ip_label,
            ip_status="HOME_IP",
            status="BLOCKED",
            close_reason="Home IP detected"
        )

        return self.event(
            profile_id=profile_id,
            session_id=session_id,
            platform=platform,
            ip_label=ip_label,
            ip_status="HOME_IP",
            event_type="HOME_IP_BLOCKED",
            details={
                "ip": ip_info.get("ip"),
                "label": ip_label,
                "reason": "Home IP detected",
            }
        )

    def blacklisted_ip_blocked(self, profile_id, session_id=None, platform="", ip_info=None, reason="Blacklisted IP"):
        ip_info = ip_info or {}
        ip_label = str(ip_info.get("label") or ip_info.get("ip") or "").strip()

        self._update_profile_session_fields(
            session_id,
            final_ip=ip_label,
            ip_status="BLACKLISTED",
            status="BLACKLISTED",
            close_reason=reason
        )

        return self.event(
            profile_id=profile_id,
            session_id=session_id,
            platform=platform,
            ip_label=ip_label,
            ip_status="BLACKLISTED",
            event_type="IP_BLACKLISTED_BLOCKED",
            details={
                "ip": ip_info.get("ip"),
                "label": ip_label,
                "reason": reason,
            }
        )

    def platform_selected(self, profile_id, session_id=None, platform="", active_platforms=None):
        platform = self._safe_platform(platform)

        self._update_profile_session_fields(
            session_id,
            platform=platform
        )

        if profile_id in self.session_cache:
            self.session_cache[profile_id]["platform"] = platform

        return self.event(
            profile_id=profile_id,
            session_id=session_id,
            platform=platform,
            event_type="PLATFORM_SELECTED",
            details={
                "selected_platform": platform,
                "active_platforms": active_platforms or [],
            }
        )

    def page_snapshot(self, profile_id, session_id=None, platform="", event_type="PAGE_SNAPSHOT", driver=None, details=""):
        return self.event(
            profile_id=profile_id,
            session_id=session_id,
            platform=platform,
            event_type=event_type,
            details={
                "details": details,
                "browser": self._driver_snapshot(driver),
            }
        )

    # ==============================
    # Cache Helpers
    # ==============================

    def get_session_id(self, profile_id):
        try:
            profile_id = int(profile_id)
        except Exception:
            return ""

        item = self.session_cache.get(profile_id) or {}
        return str(item.get("session_id") or "")

    def get_platform(self, profile_id):
        try:
            profile_id = int(profile_id)
        except Exception:
            return "Unknown"

        item = self.session_cache.get(profile_id) or {}
        return str(item.get("platform") or "Unknown")

    def attach_to_active_session(self, active_sessions, profile_id, session_id):
        try:
            profile_id = int(profile_id)
            active_sessions.setdefault(profile_id, {})
            active_sessions[profile_id]["session_id"] = session_id
            return True
        except Exception:
            return False