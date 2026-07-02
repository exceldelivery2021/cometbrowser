"""
BasePlatformRunner - Full behavioral session orchestrator for platform runners.

Session contract:
  - Random duration: 30 minutes to 4 hours per session
  - 60-90% of session time on targeted content (random split per session)
  - Remaining 10-40% on random/discovery content
  - Order (targeted-first vs random-first) is randomly decided per session
  - Likes / follows applied 5-15% of the time per content visit
  - Comments applied 3-8% of the time per content visit
  - Ads are NEVER skipped or dismissed — presence/absence is observed
    only for IP quality scoring
"""

import random
import time
import traceback
import urllib.parse
from datetime import datetime

from selenium.webdriver.support.ui import WebDriverWait

from engine.ip_quality_tracker import get_tracker

# Session length — random between 30 min and 4 hours
_SESSION_MIN_S = 30 * 60        # 30 minutes
_SESSION_MAX_S = 4 * 60 * 60    # 4 hours

# Dwell time per content piece (seconds)
_DWELL_TARGETED_MIN = 90
_DWELL_TARGETED_MAX = 300   # up to 5 min per targeted item
_DWELL_RANDOM_MIN   = 45
_DWELL_RANDOM_MAX   = 180   # up to 3 min per random item

# Idle micro-pause inside dwell (look-away simulation)
_PAUSE_CHANCE = 0.12
_PAUSE_MIN_S  = 8
_PAUSE_MAX_S  = 40
_TICK_S       = 5           # polling interval during dwell


class BasePlatformRunner:
    """
    Full behavioral session orchestrator.

    Subclasses must implement:
        build_target_url(target)         → str
        inspect_platform_state(...)      → dict with ads_detected / page_type
        _open_targeted(driver, target)   → bool
        _open_random(driver)             → bool
        _try_like(driver)                → bool
        _try_follow(driver)              → bool
        _try_comment(driver)             → bool

    Optional overrides:
        _dwell_extra(driver, tick_s)     → platform-specific activity during dwell
        platform_display_name()          → str
    """

    platform     = "base"
    homepage_url = "about:blank"

    def __init__(self, db=None, state_updater=None, default_wait=25):
        self.db            = db
        self.state_updater = state_updater
        self.default_wait  = default_wait

    # ══════════════════════════════════════════════════════════════════
    # Public entry point
    # ══════════════════════════════════════════════════════════════════

    def run(self, driver, profile_id, session_id="", targets=None,
            runtime_seconds=None, ip_address=None):

        started_at = time.time()
        targets    = targets or []

        self.record_event(profile_id, session_id, "PLATFORM_RUNNER_STARTED",
                          f"{self.platform} runner started")
        self.update_state(profile_id, status="PLATFORM_RUNNING",
                          target_platform=self.platform_display_name())

        # ── Per-session randomised parameters ────────────────────────
        session_secs   = runtime_seconds or random.randint(_SESSION_MIN_S, _SESSION_MAX_S)
        targeted_pct   = random.uniform(0.60, 0.90)
        targeted_secs  = session_secs * targeted_pct
        random_secs    = session_secs * (1.0 - targeted_pct)
        targeted_first = random.random() < 0.5

        self._like_chance    = random.uniform(0.05, 0.15)
        self._follow_chance  = random.uniform(0.05, 0.15)
        self._comment_chance = random.uniform(0.03, 0.08)

        pct_label   = f"{int(targeted_pct*100)}% targeted / {int((1-targeted_pct)*100)}% random"
        order_label = "targeted→random" if targeted_first else "random→targeted"
        mins        = int(session_secs / 60)

        print(
            f"[{self.platform.upper()} {profile_id}] "
            f"Session {mins}m | {pct_label} | order={order_label} | "
            f"like={int(self._like_chance*100)}% "
            f"follow={int(self._follow_chance*100)}% "
            f"comment={int(self._comment_chance*100)}%"
        )
        self.record_event(profile_id, session_id, "SESSION_PLAN",
                          f"secs={session_secs}; {pct_label}; order={order_label}")

        result = {
            "ok":               False,
            "platform":         self.platform,
            "events":           [],
            "error":            "",
            "started_at":       datetime.now().isoformat(timespec="seconds"),
            "ended_at":         None,
            "duration_seconds": 0,
            "ip_address":       ip_address or "",
            "items_visited":    0,
            "likes":            0,
            "follows":          0,
            "comments":         0,
        }

        all_ads_detected = []

        try:
            if targeted_first:
                self._run_targeted_loop(driver, profile_id, session_id,
                                        targets, targeted_secs, result, all_ads_detected)
                self._run_random_loop(driver, profile_id, session_id,
                                      random_secs, result, all_ads_detected)
            else:
                self._run_random_loop(driver, profile_id, session_id,
                                      random_secs, result, all_ads_detected)
                self._run_targeted_loop(driver, profile_id, session_id,
                                        targets, targeted_secs, result, all_ads_detected)

            result["ok"] = True
            self.record_event(profile_id, session_id, "PLATFORM_RUNNER_FINISHED",
                              f"visited={result['items_visited']}; "
                              f"likes={result['likes']}; follows={result['follows']}; "
                              f"comments={result['comments']}")

        except Exception as e:
            result["ok"]    = False
            result["error"] = str(e)
            print(f"[{self.platform.upper()} Runner] ❌ Error for Profile {profile_id}: {e}")
            traceback.print_exc()
            self.record_event(profile_id, session_id, "PLATFORM_RUNNER_ERROR", str(e))

        finally:
            result["ended_at"]         = datetime.now().isoformat(timespec="seconds")
            result["duration_seconds"] = int(time.time() - started_at)

        # ── IP quality tracking ───────────────────────────────────────
        if ip_address and all_ads_detected:
            ads_seen = any(all_ads_detected)
            tracker  = get_tracker()
            tracker.record_session(
                ip=ip_address, platform=self.platform,
                ads_detected=ads_seen,
                session_id=session_id or "",
                note=f"profile={profile_id}; visits={len(all_ads_detected)}"
            )
            if not ads_seen:
                result["events"].append("IP_NO_ADS_DETECTED")
            if tracker.is_banned(ip_address, self.platform):
                result["events"].append("IP_BANNED_ON_PLATFORM")
                result["ip_banned"] = True

        return result

    # ══════════════════════════════════════════════════════════════════
    # Browse loops
    # ══════════════════════════════════════════════════════════════════

    def _run_targeted_loop(self, driver, profile_id, session_id,
                           targets, duration_secs, result, ads_log):
        if not targets or duration_secs <= 0:
            return

        deadline = time.time() + duration_secs
        print(f"[{self.platform.upper()} {profile_id}] ▶ Targeted phase: {int(duration_secs)}s")

        while time.time() < deadline:
            if not self._browser_alive(driver):
                break

            target = self.choose_target(targets)
            if not target:
                break

            url   = self.build_target_url(target)
            label = target.get("title") or target.get("identifier") or url
            print(f"[{self.platform.upper()} {profile_id}] 🎯 Targeted: {label}")
            self.record_event(profile_id, session_id, "TARGETED_CONTENT_OPEN",
                              f"url={url}; label={label}")

            if not self._open_targeted(driver, target):
                continue

            state = self.inspect_platform_state(driver, profile_id, session_id, target)
            result["events"].extend(state.get("events", []))
            if state.get("ads_detected") is not None:
                ads_log.append(state["ads_detected"])

            dwell = min(
                random.randint(_DWELL_TARGETED_MIN, _DWELL_TARGETED_MAX),
                max(10, int(deadline - time.time()))
            )
            self._dwell(driver, dwell)
            result["items_visited"] += 1
            self._maybe_engage(driver, profile_id, result)

            if not self._browser_alive(driver):
                break

    def _run_random_loop(self, driver, profile_id, session_id,
                         duration_secs, result, ads_log):
        if duration_secs <= 0:
            return

        deadline = time.time() + duration_secs
        print(f"[{self.platform.upper()} {profile_id}] 🔀 Random phase: {int(duration_secs)}s")

        while time.time() < deadline:
            if not self._browser_alive(driver):
                break

            if not self._open_random(driver):
                time.sleep(3)
                continue

            state = self.inspect_platform_state(driver, profile_id, session_id, None)
            result["events"].extend(state.get("events", []))
            if state.get("ads_detected") is not None:
                ads_log.append(state["ads_detected"])

            dwell = min(
                random.randint(_DWELL_RANDOM_MIN, _DWELL_RANDOM_MAX),
                max(10, int(deadline - time.time()))
            )
            self._dwell(driver, dwell)
            result["items_visited"] += 1
            self._maybe_engage(driver, profile_id, result)

            if not self._browser_alive(driver):
                break

    # ══════════════════════════════════════════════════════════════════
    # Engagement
    # ══════════════════════════════════════════════════════════════════

    def _maybe_engage(self, driver, profile_id, result):
        p = self.platform.upper()

        if random.random() < self._like_chance:
            if self._try_like(driver):
                result["likes"] += 1
                print(f"[{p} {profile_id}] ❤️  Like applied")

        if random.random() < self._follow_chance:
            if self._try_follow(driver):
                result["follows"] += 1
                print(f"[{p} {profile_id}] ➕ Follow applied")

        if random.random() < self._comment_chance:
            if self._try_comment(driver):
                result["comments"] += 1
                print(f"[{p} {profile_id}] 💬 Comment posted")

    # ══════════════════════════════════════════════════════════════════
    # Dwell
    # ══════════════════════════════════════════════════════════════════

    def _dwell(self, driver, seconds):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if not self._browser_alive(driver):
                return
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            if random.random() < _PAUSE_CHANCE:
                time.sleep(random.randint(_PAUSE_MIN_S, min(_PAUSE_MAX_S, int(remaining))))
            else:
                if random.random() < 0.20:
                    try:
                        driver.execute_script(
                            f"window.scrollBy(0, window.innerHeight * {random.uniform(0.3, 0.7):.2f});"
                        )
                    except Exception:
                        pass
                time.sleep(min(_TICK_S, remaining))
            self._dwell_extra(driver, _TICK_S)

    # ══════════════════════════════════════════════════════════════════
    # Stubs — subclasses implement these
    # ══════════════════════════════════════════════════════════════════

    def _open_targeted(self, driver, target) -> bool:
        try:
            driver.get(self.build_target_url(target))
            self.wait_for_page_ready(driver)
            return True
        except Exception:
            return False

    def _open_random(self, driver) -> bool:
        return False

    def _try_like(self, driver) -> bool:
        return False

    def _try_follow(self, driver) -> bool:
        return False

    def _try_comment(self, driver) -> bool:
        return False

    def _dwell_extra(self, driver, tick_seconds):
        pass

    def inspect_platform_state(self, driver, profile_id, session_id="", selected_target=None):
        return {"ok": True, "events": [], "ads_detected": None, "page_type": "unknown"}

    # ══════════════════════════════════════════════════════════════════
    # Target selection (priority-weighted)
    # ══════════════════════════════════════════════════════════════════

    def choose_target(self, targets):
        clean = []
        for item in targets or []:
            if not isinstance(item, dict):
                continue
            enabled = item.get("enabled", 1)
            if str(enabled).strip().lower() in ["0", "false", "no", "off", "disabled"]:
                continue
            clean.append(item)

        if not clean:
            return None

        weighted = []
        for item in clean:
            try:
                p = max(1, min(int(item.get("priority", 5)), 10))
            except Exception:
                p = 5
            weighted.append((item, p))

        total = sum(w for _, w in weighted)
        pick  = random.uniform(0, total)
        upto  = 0
        for item, w in weighted:
            upto += w
            if pick <= upto:
                return item
        return weighted[-1][0]

    # ══════════════════════════════════════════════════════════════════
    # URL / browser helpers
    # ══════════════════════════════════════════════════════════════════

    def build_target_url(self, target):
        if target and target.get("url"):
            return str(target["url"]).strip()
        return self.homepage_url

    def quote(self, value):
        return urllib.parse.quote(str(value or "").strip(), safe="")

    def clean_identifier_or_title(self, target):
        if not target:
            return ""
        return (str(target.get("identifier") or "").strip()
                or str(target.get("title") or "").strip())

    def wait_for_page_ready(self, driver, timeout=None):
        try:
            WebDriverWait(driver, timeout or self.default_wait).until(
                lambda d: d.execute_script("return document.readyState")
                in ["interactive", "complete"]
            )
            time.sleep(random.uniform(1.5, 3.0))
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

    def _browser_alive(self, driver):
        try:
            _ = driver.current_url
            return True
        except Exception:
            return False

    # ══════════════════════════════════════════════════════════════════
    # Analytics / state
    # ══════════════════════════════════════════════════════════════════

    def update_state(self, profile_id, status=None, ip_address=None, target_platform=None):
        if not self.state_updater:
            return
        try:
            self.state_updater(profile_id, status=status,
                               ip_address=ip_address, target_platform=target_platform)
        except Exception:
            pass

    def record_event(self, profile_id=None, session_id="", event_type="EVENT",
                     details="", event_value=0.0, duration_seconds=0):
        if not self.db or not hasattr(self.db, "record_analytics_event"):
            return
        try:
            self.db.record_analytics_event(
                profile_id=profile_id, session_id=session_id,
                platform=self.platform, event_type=event_type,
                event_value=event_value, duration_seconds=duration_seconds,
                details=details
            )
        except Exception:
            pass

    def platform_display_name(self):
        return self.platform.capitalize()

    def describe_target(self, target, target_url):
        if not target:
            return f"No enabled target. Using homepage: {target_url}"
        return (
            f"platform={target.get('platform', self.platform)}; "
            f"type={target.get('target_type', '')}; "
            f"title={target.get('title', '')}; "
            f"url={target_url}"
        )
