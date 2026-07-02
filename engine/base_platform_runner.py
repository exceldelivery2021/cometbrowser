"""
BasePlatformRunner - Richer base class for platform runners.
Handles target selection, page-load verification, event recording,
and IP quality tracking (bans IPs that platforms don't show ads to).
"""

import random
import time
import traceback
import urllib.parse
from datetime import datetime

from selenium.webdriver.support.ui import WebDriverWait

from engine.ip_quality_tracker import get_tracker


class BasePlatformRunner:
    """
    Shared platform runner foundation.

    Key contract:
    - Opens platform targets and verifies page load.
    - Records timeline events to the analytics DB.
    - Reports ad-detection results to IPQualityTracker after every session.
    - Does NOT manually skip or dismiss ads — ad presence/absence is
      used only for IP quality scoring.
    """

    platform     = "base"
    homepage_url = "about:blank"

    def __init__(self, db=None, state_updater=None, default_wait=25):
        self.db           = db
        self.state_updater = state_updater
        self.default_wait = default_wait

    # ==============================
    # Public API
    # ==============================

    def run(self, driver, profile_id, session_id="", targets=None,
            runtime_seconds=None, ip_address=None):
        started_at = time.time()
        targets = targets or []

        self.record_event(
            profile_id=profile_id,
            session_id=session_id,
            event_type="PLATFORM_RUNNER_STARTED",
            details=f"{self.platform} runner started"
        )

        self.update_state(
            profile_id,
            status="PLATFORM_RUNNING",
            target_platform=self.platform_display_name()
        )

        selected_target = self.choose_target(targets)
        target_url      = self.build_target_url(selected_target)

        if not target_url:
            target_url = self.homepage_url

        result = {
            "ok":               False,
            "platform":         self.platform,
            "target":           selected_target,
            "target_url":       target_url,
            "final_url":        "",
            "title":            "",
            "events":           [],
            "error":            "",
            "started_at":       datetime.now().isoformat(timespec="seconds"),
            "ended_at":         None,
            "duration_seconds": 0,
            "ip_address":       ip_address or "",
        }

        try:
            self.record_event(
                profile_id=profile_id,
                session_id=session_id,
                event_type="TARGET_SELECTED",
                details=self.describe_target(selected_target, target_url)
            )

            print(f"[{self.platform.upper()} Runner] Profile {profile_id} opening: {target_url}")

            driver.get(target_url)

            loaded    = self.wait_for_page_ready(driver, timeout=self.default_wait)
            final_url = self.safe_current_url(driver)
            title     = self.safe_title(driver)

            result["final_url"] = final_url
            result["title"]     = title

            event_name = "PAGE_LOADED" if loaded else "PAGE_LOAD_TIMEOUT"
            self.record_event(
                profile_id=profile_id,
                session_id=session_id,
                event_type=event_name,
                details=f"title={title}; url={final_url}"
            )
            result["events"].append(event_name)

            platform_result = self.inspect_platform_state(
                driver=driver,
                profile_id=profile_id,
                session_id=session_id,
                selected_target=selected_target
            )

            result["events"].extend(platform_result.get("events", []))
            result["ok"] = bool(platform_result.get("ok", loaded))

            # ── IP quality tracking ────────────────────────────────────
            if ip_address:
                ads_detected = platform_result.get("ads_detected", None)
                if ads_detected is not None:
                    tracker = get_tracker()
                    tracker.record_session(
                        ip          = ip_address,
                        platform    = self.platform,
                        ads_detected= bool(ads_detected),
                        session_id  = session_id or "",
                        page_type   = platform_result.get("page_type", ""),
                        note        = f"profile={profile_id}"
                    )
                    if not ads_detected:
                        result["events"].append("IP_NO_ADS_DETECTED")
                    if tracker.is_banned(ip_address, self.platform):
                        result["events"].append("IP_BANNED_ON_PLATFORM")
                        result["ip_banned"] = True
            # ─────────────────────────────────────────────────────────

            self.record_event(
                profile_id=profile_id,
                session_id=session_id,
                event_type="PLATFORM_RUNNER_FINISHED",
                details=f"ok={result['ok']}; title={title}; url={final_url}"
            )

        except Exception as e:
            result["ok"]    = False
            result["error"] = str(e)

            print(f"[{self.platform.upper()} Runner] ❌ Error for Profile {profile_id}: {e}")
            traceback.print_exc()

            self.record_event(
                profile_id=profile_id,
                session_id=session_id,
                event_type="PLATFORM_RUNNER_ERROR",
                details=str(e)
            )

        finally:
            result["ended_at"]         = datetime.now().isoformat(timespec="seconds")
            result["duration_seconds"] = int(time.time() - started_at)

        return result

    # ==============================
    # Target selection
    # ==============================

    def choose_target(self, targets):
        """Weighted target selection by dashboard priority (1–10)."""
        clean_targets = []
        for item in targets or []:
            if not isinstance(item, dict):
                continue
            enabled = item.get("enabled", 1)
            if str(enabled).strip().lower() in ["0", "false", "no", "off", "disabled"]:
                continue
            clean_targets.append(item)

        if not clean_targets:
            return None

        weighted = []
        for item in clean_targets:
            try:
                priority = int(item.get("priority", 5))
            except Exception:
                priority = 5
            priority = max(1, min(priority, 10))
            weighted.append((item, priority))

        total = sum(w for _, w in weighted)
        pick  = random.uniform(0, total)
        upto  = 0
        for item, weight in weighted:
            upto += weight
            if pick <= upto:
                return item

        return weighted[-1][0]

    def build_target_url(self, target):
        """Override in subclass for platform-specific URL construction."""
        if target and target.get("url"):
            return str(target["url"]).strip()
        return self.homepage_url

    def describe_target(self, target, target_url):
        if not target:
            return f"No enabled target. Using homepage: {target_url}"
        return (
            f"platform={target.get('platform', self.platform)}; "
            f"type={target.get('target_type', '')}; "
            f"title={target.get('title', '')}; "
            f"identifier={target.get('identifier', '')}; "
            f"url={target_url}"
        )

    # ==============================
    # Browser helpers
    # ==============================

    def wait_for_page_ready(self, driver, timeout=25):
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: d.execute_script("return document.readyState")
                in ["interactive", "complete"]
            )
            time.sleep(2)
            return True
        except Exception:
            return False

    def safe_current_url(self, driver):
        try:
            return str(driver.current_url or "")
        except Exception:
            return ""

    def safe_title(self, driver):
        try:
            return str(driver.title or "")
        except Exception:
            return ""

    def quote(self, value):
        return urllib.parse.quote(str(value or "").strip(), safe="")

    def clean_identifier_or_title(self, target):
        if not target:
            return ""
        identifier = str(target.get("identifier") or "").strip()
        title      = str(target.get("title") or "").strip()
        return identifier or title

    # ==============================
    # Event / state helpers
    # ==============================

    def update_state(self, profile_id, status=None, ip_address=None, target_platform=None):
        if not self.state_updater:
            return
        try:
            self.state_updater(
                profile_id,
                status=status,
                ip_address=ip_address,
                target_platform=target_platform
            )
        except Exception as e:
            print(f"[{self.platform.upper()} Runner] State update failed: {e}")

    def record_event(self, profile_id=None, session_id="", event_type="EVENT",
                     details="", event_value=0.0, duration_seconds=0):
        if not self.db or not hasattr(self.db, "record_analytics_event"):
            return
        try:
            self.db.record_analytics_event(
                profile_id=profile_id,
                session_id=session_id,
                platform=self.platform,
                event_type=event_type,
                event_value=event_value,
                duration_seconds=duration_seconds,
                details=details
            )
        except Exception as e:
            print(f"[{self.platform.upper()} Runner] Analytics event failed: {e}")

    def platform_display_name(self):
        return self.platform.capitalize()

    def inspect_platform_state(self, driver, profile_id, session_id="", selected_target=None):
        """
        Override in subclass. Must return a dict with at minimum:
            ok           (bool)
            events       (list of str)
            ads_detected (bool | None)  ← None = unknown/not applicable
            page_type    (str)
        """
        return {
            "ok":           True,
            "events":       ["BASE_PLATFORM_INSPECTED"],
            "ads_detected": None,
            "page_type":    "unknown",
        }
