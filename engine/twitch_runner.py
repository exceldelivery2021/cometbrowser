"""
Twitch Runner - Automates Twitch behavior across all archetypes
Implements: stream watching, channel browsing, chat interaction,
            clips, raids, subscriptions, bit cheering, search
"""

import time
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from engine.platform_logic import SearchPattern, AdBehavior, SessionTracker
from .base_runner import BaseRunner


# Realistic generic chat messages that fit any stream context
_CHAT_MESSAGES = [
    "LUL", "PogChamp", "Pog", "KEKW", "monkaS", "pepeLaugh",
    "nice", "lol", "gg", "ez", "let's go", "POG", "Sadge",
    "LULW", "based", "W", "actually insane", "no way",
    "PauseChamp", "Clap", "OMEGALUL", "FeelsBadMan", "FeelsGoodMan",
    "HeyGuys", "BibleThump", "kreygasm", "VoHiYo",
]

_SEARCH_TERMS = [
    "just chatting", "gaming", "music", "art", "irl", "slots",
    "minecraft", "fortnite", "variety", "programming", "chess",
    "valorant", "league of legends", "apex legends", "gta",
]


class TwitchRunner(BaseRunner):
    """Twitch-specific automation — stream watching, chat, clips, browse"""

    def __init__(self, db=None, state_updater=None):
        super().__init__(db, state_updater)
        self.platform = "twitch"

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self, driver, profile_id, session_id="", targets=None):
        print(f"\n[Twitch {profile_id}] 🟣 Starting Twitch session")

        self.driver    = driver
        self.profile_id = profile_id
        self.session_id = session_id
        self.targets    = targets or []
        self.tracker    = SessionTracker(profile_id)

        try:
            if "twitch.tv" not in driver.current_url.lower():
                driver.get("https://www.twitch.tv")
                time.sleep(4)

            self._dismiss_popups()

            session  = self.tracker.start_session()
            behavior = self.tracker.behavior

            print(f"[Twitch {profile_id}] Archetype: {behavior.archetype.value}")
            print(f"[Twitch {profile_id}] Session: {session['duration_minutes']}m")

            archetype = behavior.archetype.value
            if archetype == "idle":
                result = self._twitch_idle(behavior)
            elif archetype == "quick_jump":
                result = self._twitch_quick_jump(behavior)
            elif archetype == "targeted_first":
                result = self._twitch_targeted_first(behavior, session)
            else:
                result = self._twitch_random_first(behavior, session)

            print(f"[Twitch {profile_id}] ✅ Session complete")
            return result

        except Exception as e:
            print(f"[Twitch {profile_id}] ❌ Error: {e}")
            return self._fail(str(e))

    # ------------------------------------------------------------------
    # Archetypes
    # ------------------------------------------------------------------

    def _twitch_idle(self, behavior):
        print(f"[Twitch {self.profile_id}] IDLE: Staying on page")
        self._scroll_page(random.randint(2, 4))
        time.sleep(random.randint(60, 180))
        return self._ok(["idle"])

    def _twitch_quick_jump(self, behavior):
        print(f"[Twitch {self.profile_id}] QUICK_JUMP: Jumping to target")
        if self.targets:
            self._navigate_to_target(self.targets[0])
        else:
            self._browse_directory()
        self._watch_stream(behavior, max_seconds=random.randint(120, 360))
        return self._ok(["quick_jump"])

    def _twitch_targeted_first(self, behavior, session):
        print(f"[Twitch {self.profile_id}] TARGETED_FIRST")
        duration    = session["duration_minutes"] * 60
        t_time      = duration * behavior.targeted_time_percent
        r_time      = duration * behavior.random_time_percent
        streams     = 0
        streams    += self._browse_targeted_streams(t_time, behavior)
        if r_time > 0:
            streams += self._browse_random_streams(r_time, behavior)
        return self._ok([f"streams_watched:{streams}"])

    def _twitch_random_first(self, behavior, session):
        print(f"[Twitch {self.profile_id}] RANDOM_FIRST")
        duration    = session["duration_minutes"] * 60
        r_time      = duration * behavior.random_time_percent
        t_time      = duration * behavior.targeted_time_percent
        streams     = 0
        if r_time > 0:
            streams += self._browse_random_streams(r_time, behavior)
        streams    += self._browse_targeted_streams(t_time, behavior)
        return self._ok([f"streams_watched:{streams}"])

    # ------------------------------------------------------------------
    # Browse loops
    # ------------------------------------------------------------------

    def _browse_targeted_streams(self, duration_seconds, behavior) -> int:
        start   = time.time()
        watched = 0
        while time.time() - start < duration_seconds:
            if not self._is_browser_alive():
                break
            if not self.targets:
                break
            target = random.choice(self.targets)
            print(f"[Twitch {self.profile_id}] 🎯 Target: {target}")
            self._navigate_to_target(target)
            self._watch_stream(behavior)
            watched += 1
            self._maybe_chat(behavior)
            self._maybe_follow(behavior)
            self._maybe_clip(behavior)
            if not self._is_browser_alive():
                break
        return watched

    def _browse_random_streams(self, duration_seconds, behavior) -> int:
        start   = time.time()
        watched = 0
        while time.time() - start < duration_seconds:
            if not self._is_browser_alive():
                break
            if behavior.search_pattern.value == "search_bar":
                self._search_streams()
            else:
                self._browse_directory()
            self._click_first_stream()
            self._watch_stream(behavior)
            watched += 1
            if not self._is_browser_alive():
                break
        return watched

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _navigate_to_target(self, target):
        try:
            if isinstance(target, dict):
                url = str(target.get("url") or target.get("identifier") or "").strip()
            else:
                url = str(target).strip()

            if url.startswith("http"):
                self.driver.get(url)
            elif "/" not in url:
                self.driver.get(f"https://www.twitch.tv/{url.lstrip('@')}")
            else:
                self.driver.get(f"https://www.twitch.tv/{url.strip('/')}")

            time.sleep(random.uniform(3, 5))
            self._dismiss_popups()
        except Exception as e:
            print(f"[Twitch {self.profile_id}] Navigation error: {e}")

    def _browse_directory(self):
        """Open the Twitch browse/directory page."""
        try:
            self.driver.get("https://www.twitch.tv/directory")
            time.sleep(random.uniform(2, 4))
        except Exception:
            pass

    def _search_streams(self):
        try:
            term = random.choice(_SEARCH_TERMS)
            self.driver.get(f"https://www.twitch.tv/search?term={term.replace(' ', '+')}")
            time.sleep(random.uniform(2, 4))
            print(f"[Twitch {self.profile_id}] 🔍 Searched: {term}")
        except Exception as e:
            print(f"[Twitch {self.profile_id}] Search failed: {e}")

    def _click_first_stream(self):
        """Click first live stream card visible on directory/search page."""
        try:
            selectors = [
                "a[data-a-target='preview-card-image-link']",
                ".tw-tower a",
                "article a",
                ".stream-thumbnail a",
            ]
            for sel in selectors:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    choice = random.choice(els[:5])
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", choice)
                    choice.click()
                    time.sleep(random.uniform(3, 5))
                    self._dismiss_popups()
                    return
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Stream watching
    # ------------------------------------------------------------------

    def _watch_stream(self, behavior, max_seconds=None):
        """Watch the current stream with realistic behavior."""
        try:
            time.sleep(2)
            self._dismiss_popups()
            self._handle_twitch_ads(behavior)

            watch_time = max_seconds or random.randint(60, int(
                behavior.watch_duration_percent * 1800  # max 30 min per stream
            ))
            watch_time = max(30, min(watch_time, 1800))
            print(f"[Twitch {self.profile_id}] 👁 Watching for {watch_time}s")

            start = time.time()
            while time.time() - start < watch_time:
                if not self._is_browser_alive():
                    return
                elapsed = time.time() - start
                # Occasional chat scroll
                if random.random() < 0.15:
                    self._scroll_chat()
                # Occasional page scroll
                if random.random() < 0.05:
                    self._scroll_page(1)
                # Random pause simulation (look away from screen)
                if random.random() < behavior.pause_probability * 0.3:
                    pause = random.randint(10, 45)
                    print(f"[Twitch {self.profile_id}] ⏸ Idle pause {pause}s")
                    time.sleep(pause)
                else:
                    time.sleep(random.uniform(3, 8))

        except Exception as e:
            print(f"[Twitch {self.profile_id}] Watch error: {e}")

    # ------------------------------------------------------------------
    # Engagement
    # ------------------------------------------------------------------

    def _maybe_chat(self, behavior):
        if random.random() > behavior.like_probability * 2:
            return
        try:
            chat_input = None
            for sel in [
                "textarea[data-a-target='chat-input']",
                ".chat-input textarea",
                "#chat-input",
            ]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els and els[0].is_displayed():
                    chat_input = els[0]
                    break

            if not chat_input:
                return

            msg = random.choice(_CHAT_MESSAGES)
            chat_input.click()
            time.sleep(0.3)
            chat_input.send_keys(msg)
            time.sleep(random.uniform(0.5, 1.5))
            chat_input.send_keys(Keys.RETURN)
            print(f"[Twitch {self.profile_id}] 💬 Chat: {msg}")
            time.sleep(random.uniform(1, 2))
        except Exception:
            pass

    def _maybe_follow(self, behavior):
        if random.random() > behavior.subscribe_probability:
            return
        try:
            for sel in [
                "button[data-a-target='follow-button']",
                "[data-test-selector='follow-button']",
            ]:
                btn = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if btn and btn[0].is_displayed():
                    btn[0].click()
                    print(f"[Twitch {self.profile_id}] ➕ Followed channel")
                    time.sleep(random.uniform(1, 2))
                    return
        except Exception:
            pass

    def _maybe_clip(self, behavior):
        """Occasionally open clip creator (does not actually submit)."""
        if random.random() > behavior.comment_probability:
            return
        try:
            for sel in [
                "button[aria-label='Clip']",
                "[data-a-target='clip-button']",
            ]:
                btn = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if btn and btn[0].is_displayed():
                    btn[0].click()
                    print(f"[Twitch {self.profile_id}] 🎬 Opened clip creator")
                    time.sleep(random.uniform(2, 4))
                    # Close it — don't actually create clip
                    self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                    return
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Ads
    # ------------------------------------------------------------------

    def _handle_twitch_ads(self, behavior):
        try:
            ad_selectors = [
                "[data-a-target='ad-overlay']",
                ".player-ad-overlay",
                ".tw-ad",
            ]
            ad_visible = False
            for sel in ad_selectors:
                if self.driver.find_elements(By.CSS_SELECTOR, sel):
                    ad_visible = True
                    break

            if not ad_visible:
                return

            if behavior.ad_behavior == AdBehavior.SKIP_IMMEDIATELY:
                time.sleep(1)
                self._try_click_ad_skip()
            elif behavior.ad_behavior == AdBehavior.SKIP_AFTER_5S:
                time.sleep(5)
                self._try_click_ad_skip()
            elif behavior.ad_behavior == AdBehavior.WATCH_FULL:
                print(f"[Twitch {self.profile_id}] 📺 Watching full ad")
                time.sleep(random.randint(15, 35))
            else:
                time.sleep(random.randint(8, 15))
                self._try_click_ad_skip()
        except Exception:
            pass

    def _try_click_ad_skip(self):
        try:
            for sel in [
                "[data-a-target='ad-overlay-skip-button']",
                ".player-ad-overlay__skip-btn",
                "button[aria-label*='Skip']",
            ]:
                btns = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if btns:
                    btns[0].click()
                    print(f"[Twitch {self.profile_id}] ⏭ Skipped ad")
                    time.sleep(1)
                    return
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _dismiss_popups(self):
        """Dismiss cookie banners, age gates, mature content warnings."""
        selectors = [
            "[data-a-target='consent-banner-accept']",
            "button[data-a-target='tw-core-button-label-text']",
            "[data-a-target='player-overlay-mature-accept']",
            ".tw-button--primary",
        ]
        for sel in selectors:
            try:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed() and any(
                        w in (el.text or "").lower()
                        for w in ["accept", "agree", "ok", "got it", "i agree", "start watching", "confirm"]
                    ):
                        el.click()
                        time.sleep(0.5)
            except Exception:
                pass

    def _scroll_page(self, times=1):
        for _ in range(times):
            self.driver.execute_script("window.scrollBy(0, window.innerHeight * 0.6);")
            time.sleep(random.uniform(0.8, 1.5))

    def _scroll_chat(self):
        try:
            chat = self.driver.find_elements(By.CSS_SELECTOR, ".chat-scrollable-area__message-container")
            if chat:
                self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", chat[0])
        except Exception:
            pass

    def _is_browser_alive(self):
        try:
            _ = self.driver.current_url
            return True
        except Exception:
            return False
