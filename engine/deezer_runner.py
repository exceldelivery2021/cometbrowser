"""
Deezer Runner - Automates Deezer Web Player behavior across all archetypes
Implements: track listening, album/playlist browsing, artist pages, search, favorites
"""

import time
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from engine.platform_logic import SearchPattern, AdBehavior, SessionTracker
from .base_runner import BaseRunner


_SEARCH_TERMS = [
    "pop", "hip hop", "chill", "workout", "jazz", "classical",
    "rock", "electronic", "r&b", "indie", "lofi", "country",
    "latin", "k-pop", "reggae", "blues", "soul", "metal",
    "new releases", "top charts", "trending",
]

_GENRE_URLS = [
    "https://www.deezer.com/us/channels/pop",
    "https://www.deezer.com/us/channels/rap",
    "https://www.deezer.com/us/channels/rock",
    "https://www.deezer.com/us/channels/electro",
    "https://www.deezer.com/us/channels/rnb",
    "https://www.deezer.com/us/channels/latin",
    "https://www.deezer.com/us/channels/jazz",
    "https://www.deezer.com/us/channels/films_series_jeux",
]

_HOME_URL = "https://www.deezer.com"


class DeezerRunner(BaseRunner):
    """Deezer Web Player automation — listening, browsing, playlists, search, favorites"""

    def __init__(self, db=None, state_updater=None):
        super().__init__(db, state_updater)
        self.platform = "deezer"

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self, driver, profile_id, session_id="", targets=None):
        print(f"\n[Deezer {profile_id}] 🟠 Starting Deezer session")

        self.driver     = driver
        self.profile_id = profile_id
        self.session_id = session_id
        self.targets    = targets or []
        self.tracker    = SessionTracker(profile_id)

        try:
            if "deezer.com" not in driver.current_url.lower():
                driver.get(_HOME_URL)
                time.sleep(5)

            self._dismiss_popups()

            session  = self.tracker.start_session()
            behavior = self.tracker.behavior

            print(f"[Deezer {profile_id}] Archetype: {behavior.archetype.value}")
            print(f"[Deezer {profile_id}] Session: {session['duration_minutes']}m")

            archetype = behavior.archetype.value
            if archetype == "idle":
                result = self._deezer_idle(behavior)
            elif archetype == "quick_jump":
                result = self._deezer_quick_jump(behavior)
            elif archetype == "targeted_first":
                result = self._deezer_targeted_first(behavior, session)
            else:
                result = self._deezer_random_first(behavior, session)

            print(f"[Deezer {profile_id}] ✅ Session complete")
            return result

        except Exception as e:
            print(f"[Deezer {profile_id}] ❌ Error: {e}")
            return self._fail(str(e))

    # ------------------------------------------------------------------
    # Archetypes
    # ------------------------------------------------------------------

    def _deezer_idle(self, behavior):
        print(f"[Deezer {self.profile_id}] IDLE: Staying on page")
        self._scroll_page(random.randint(2, 4))
        time.sleep(random.randint(60, 180))
        return self._ok(["idle"])

    def _deezer_quick_jump(self, behavior):
        print(f"[Deezer {self.profile_id}] QUICK_JUMP: Jumping to target")
        if self.targets:
            self._navigate_to_target(self.targets[0])
        else:
            genre_url = random.choice(_GENRE_URLS)
            self.driver.get(genre_url)
            time.sleep(random.uniform(2, 4))
            self._click_first_item()
        self._listen(behavior, max_seconds=random.randint(120, 360))
        return self._ok(["quick_jump"])

    def _deezer_targeted_first(self, behavior, session):
        print(f"[Deezer {self.profile_id}] TARGETED_FIRST")
        duration = session["duration_minutes"] * 60
        t_time   = duration * behavior.targeted_time_percent
        r_time   = duration * behavior.random_time_percent
        tracks   = 0
        tracks  += self._browse_targeted(t_time, behavior)
        if r_time > 0:
            tracks += self._browse_random(r_time, behavior)
        return self._ok([f"tracks_listened:{tracks}"])

    def _deezer_random_first(self, behavior, session):
        print(f"[Deezer {self.profile_id}] RANDOM_FIRST")
        duration = session["duration_minutes"] * 60
        r_time   = duration * behavior.random_time_percent
        t_time   = duration * behavior.targeted_time_percent
        tracks   = 0
        if r_time > 0:
            tracks += self._browse_random(r_time, behavior)
        tracks  += self._browse_targeted(t_time, behavior)
        return self._ok([f"tracks_listened:{tracks}"])

    # ------------------------------------------------------------------
    # Browse loops
    # ------------------------------------------------------------------

    def _browse_targeted(self, duration_seconds, behavior) -> int:
        start   = time.time()
        tracked = 0
        while time.time() - start < duration_seconds:
            if not self._is_browser_alive():
                break
            if not self.targets:
                break
            target = random.choice(self.targets)
            print(f"[Deezer {self.profile_id}] 🎯 Target: {target}")
            self._navigate_to_target(target)
            self._listen(behavior)
            tracked += 1
            self._maybe_favorite(behavior)
            self._maybe_add_to_playlist(behavior)
            if not self._is_browser_alive():
                break
        return tracked

    def _browse_random(self, duration_seconds, behavior) -> int:
        start   = time.time()
        tracked = 0
        while time.time() - start < duration_seconds:
            if not self._is_browser_alive():
                break
            if behavior.search_pattern.value == "search_bar":
                self._search_music()
            else:
                genre_url = random.choice(_GENRE_URLS)
                self.driver.get(genre_url)
                time.sleep(random.uniform(2, 4))
            self._click_first_item()
            self._listen(behavior)
            tracked += 1
            if not self._is_browser_alive():
                break
        return tracked

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
            elif url.isdigit():
                # Deezer track ID
                self.driver.get(f"https://www.deezer.com/us/track/{url}")
            else:
                self.driver.get(
                    f"https://www.deezer.com/us/search/{url.replace(' ', '%20')}"
                )

            time.sleep(random.uniform(3, 5))
            self._dismiss_popups()
        except Exception as e:
            print(f"[Deezer {self.profile_id}] Navigation error: {e}")

    def _search_music(self):
        try:
            term = random.choice(_SEARCH_TERMS)
            self.driver.get(
                f"https://www.deezer.com/us/search/{term.replace(' ', '%20')}"
            )
            time.sleep(random.uniform(2, 4))
            print(f"[Deezer {self.profile_id}] 🔍 Searched: {term}")
        except Exception as e:
            print(f"[Deezer {self.profile_id}] Search failed: {e}")

    def _click_first_item(self):
        """Click first playable track/album/playlist card."""
        try:
            selectors = [
                "a[href*='/track/']",
                "a[href*='/album/']",
                "a[href*='/playlist/']",
                ".datagrid-item a",
                ".ResultsGrid a",
                ".ListGridItem a",
                "[data-testid='track-list'] a",
            ]
            for sel in selectors:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    choice = random.choice(els[:5])
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", choice
                    )
                    choice.click()
                    time.sleep(random.uniform(2, 4))
                    self._dismiss_popups()
                    return
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Listening
    # ------------------------------------------------------------------

    def _listen(self, behavior, max_seconds=None):
        """Listen to current track/album/playlist with realistic behavior."""
        try:
            time.sleep(2)
            self._dismiss_popups()
            self._handle_ads(behavior)

            listen_time = max_seconds or random.randint(60, int(
                behavior.watch_duration_percent * 1800
            ))
            listen_time = max(30, min(listen_time, 1800))
            print(f"[Deezer {self.profile_id}] 🎵 Listening for {listen_time}s")

            start = time.time()
            while time.time() - start < listen_time:
                if not self._is_browser_alive():
                    return
                if random.random() < 0.08:
                    self._scroll_page(1)
                if random.random() < behavior.pause_probability * 0.3:
                    pause = random.randint(10, 45)
                    print(f"[Deezer {self.profile_id}] ⏸ Idle pause {pause}s")
                    time.sleep(pause)
                else:
                    time.sleep(random.uniform(4, 10))

        except Exception as e:
            print(f"[Deezer {self.profile_id}] Listen error: {e}")

    # ------------------------------------------------------------------
    # Engagement
    # ------------------------------------------------------------------

    def _maybe_favorite(self, behavior):
        if random.random() > behavior.like_probability:
            return
        try:
            for sel in [
                "button[aria-label*='Favorite']",
                "button[aria-label*='Love']",
                "[data-testid='love-button']",
                ".love-button",
                "button[title*='Favorite']",
            ]:
                btns = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if btns and btns[0].is_displayed():
                    btns[0].click()
                    print(f"[Deezer {self.profile_id}] ❤️ Favorited track")
                    time.sleep(random.uniform(0.5, 1.5))
                    return
        except Exception:
            pass

    def _maybe_add_to_playlist(self, behavior):
        if random.random() > behavior.subscribe_probability * 0.5:
            return
        try:
            for sel in [
                "button[aria-label*='Add to playlist']",
                "[data-testid='add-to-playlist']",
                "button[title*='Add to']",
            ]:
                btns = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if btns and btns[0].is_displayed():
                    btns[0].click()
                    print(f"[Deezer {self.profile_id}] ➕ Opened add-to-playlist")
                    time.sleep(random.uniform(1, 2))
                    # Close dialog without selecting
                    self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                    return
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Ads
    # ------------------------------------------------------------------

    def _handle_ads(self, behavior):
        try:
            ad_selectors = [
                ".ads-player",
                "[data-testid='ad-banner']",
                ".advertisement",
                "iframe[src*='ads']",
            ]
            ad_visible = any(
                self.driver.find_elements(By.CSS_SELECTOR, sel)
                for sel in ad_selectors
            )
            if not ad_visible:
                return

            if behavior.ad_behavior == AdBehavior.SKIP_IMMEDIATELY:
                time.sleep(1)
                self._try_skip_ad()
            elif behavior.ad_behavior == AdBehavior.SKIP_AFTER_5S:
                time.sleep(5)
                self._try_skip_ad()
            elif behavior.ad_behavior == AdBehavior.WATCH_FULL:
                print(f"[Deezer {self.profile_id}] 📢 Listening to full ad")
                time.sleep(random.randint(15, 35))
            else:
                time.sleep(random.randint(8, 15))
                self._try_skip_ad()
        except Exception:
            pass

    def _try_skip_ad(self):
        try:
            for sel in [
                "button[aria-label*='Skip']",
                ".skip-ad-button",
                "[data-testid='skip-ad']",
            ]:
                btns = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if btns:
                    btns[0].click()
                    print(f"[Deezer {self.profile_id}] ⏭ Skipped ad")
                    time.sleep(1)
                    return
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _dismiss_popups(self):
        selectors = [
            "#gdpr-banner-accept",
            "button[aria-label*='Accept']",
            ".didomi-continue-without-agreeing",
            ".sc-accept-all",
            "[id*='onetrust-accept']",
        ]
        for sel in selectors:
            try:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed() and any(
                        w in (el.text or "").lower()
                        for w in ["accept", "agree", "ok", "got it", "continue", "close"]
                    ):
                        el.click()
                        time.sleep(0.5)
            except Exception:
                pass

    def _scroll_page(self, times=1):
        for _ in range(times):
            self.driver.execute_script("window.scrollBy(0, window.innerHeight * 0.6);")
            time.sleep(random.uniform(0.8, 1.5))

    def _is_browser_alive(self):
        try:
            _ = self.driver.current_url
            return True
        except Exception:
            return False
