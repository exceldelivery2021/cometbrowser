"""
Spotify Runner - Automates Spotify Web Player behavior across all archetypes
Implements: track listening, playlist browsing, artist pages, search, likes
"""

import time
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from engine.platform_logic import SearchPattern, AdBehavior, SessionTracker
from .base_runner import BaseRunner


_SEARCH_TERMS = [
    "chill vibes", "hip hop", "pop hits", "lofi", "workout music",
    "jazz", "classical", "rock", "edm", "r&b", "indie", "country",
    "study music", "sleep sounds", "top hits", "new releases",
    "rap", "blues", "reggae", "latin", "k-pop",
]

_GENRE_URLS = [
    "https://open.spotify.com/genre/pop",
    "https://open.spotify.com/genre/hiphop",
    "https://open.spotify.com/genre/rock",
    "https://open.spotify.com/genre/electronic",
    "https://open.spotify.com/genre/rnb",
    "https://open.spotify.com/genre/country",
    "https://open.spotify.com/genre/latin",
]

_FEATURED_URL = "https://open.spotify.com/browse/featured"
_HOME_URL      = "https://open.spotify.com"


class SpotifyRunner(BaseRunner):
    """Spotify Web Player automation — listening, browsing, playlists, search"""

    def __init__(self, db=None, state_updater=None):
        super().__init__(db, state_updater)
        self.platform = "spotify"

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self, driver, profile_id, session_id="", targets=None):
        print(f"\n[Spotify {profile_id}] 🟢 Starting Spotify session")

        self.driver     = driver
        self.profile_id = profile_id
        self.session_id = session_id
        self.targets    = targets or []
        self.tracker    = SessionTracker(profile_id)

        try:
            if "open.spotify.com" not in driver.current_url.lower():
                driver.get(_HOME_URL)
                time.sleep(5)

            self._dismiss_popups()

            session  = self.tracker.start_session()
            behavior = self.tracker.behavior

            print(f"[Spotify {profile_id}] Archetype: {behavior.archetype.value}")
            print(f"[Spotify {profile_id}] Session: {session['duration_minutes']}m")

            archetype = behavior.archetype.value
            if archetype == "idle":
                result = self._spotify_idle(behavior)
            elif archetype == "quick_jump":
                result = self._spotify_quick_jump(behavior)
            elif archetype == "targeted_first":
                result = self._spotify_targeted_first(behavior, session)
            else:
                result = self._spotify_random_first(behavior, session)

            print(f"[Spotify {profile_id}] ✅ Session complete")
            return result

        except Exception as e:
            print(f"[Spotify {profile_id}] ❌ Error: {e}")
            return self._fail(str(e))

    # ------------------------------------------------------------------
    # Archetypes
    # ------------------------------------------------------------------

    def _spotify_idle(self, behavior):
        print(f"[Spotify {self.profile_id}] IDLE: Staying on page")
        self._scroll_page(random.randint(2, 4))
        time.sleep(random.randint(60, 180))
        return self._ok(["idle"])

    def _spotify_quick_jump(self, behavior):
        print(f"[Spotify {self.profile_id}] QUICK_JUMP: Jumping to target")
        if self.targets:
            self._navigate_to_target(self.targets[0])
        else:
            self._browse_featured()
            self._click_first_item()
        self._listen(behavior, max_seconds=random.randint(120, 360))
        return self._ok(["quick_jump"])

    def _spotify_targeted_first(self, behavior, session):
        print(f"[Spotify {self.profile_id}] TARGETED_FIRST")
        duration = session["duration_minutes"] * 60
        t_time   = duration * behavior.targeted_time_percent
        r_time   = duration * behavior.random_time_percent
        tracks   = 0
        tracks  += self._browse_targeted(t_time, behavior)
        if r_time > 0:
            tracks += self._browse_random(r_time, behavior)
        return self._ok([f"tracks_listened:{tracks}"])

    def _spotify_random_first(self, behavior, session):
        print(f"[Spotify {self.profile_id}] RANDOM_FIRST")
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
            print(f"[Spotify {self.profile_id}] 🎯 Target: {target}")
            self._navigate_to_target(target)
            self._listen(behavior)
            tracked += 1
            self._maybe_like(behavior)
            self._maybe_follow_artist(behavior)
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
            elif url.startswith("spotify:"):
                # Convert spotify URI to web URL
                parts = url.replace("spotify:", "").split(":")
                self.driver.get(f"https://open.spotify.com/{'/'.join(parts)}")
            else:
                self.driver.get(f"https://open.spotify.com/search/{url.replace(' ', '%20')}")

            time.sleep(random.uniform(3, 5))
            self._dismiss_popups()
        except Exception as e:
            print(f"[Spotify {self.profile_id}] Navigation error: {e}")

    def _browse_featured(self):
        try:
            self.driver.get(_FEATURED_URL)
            time.sleep(random.uniform(2, 4))
        except Exception:
            pass

    def _search_music(self):
        try:
            term = random.choice(_SEARCH_TERMS)
            self.driver.get(f"https://open.spotify.com/search/{term.replace(' ', '%20')}")
            time.sleep(random.uniform(2, 4))
            print(f"[Spotify {self.profile_id}] 🔍 Searched: {term}")
        except Exception as e:
            print(f"[Spotify {self.profile_id}] Search failed: {e}")

    def _click_first_item(self):
        """Click first playable card on a browse/search page."""
        try:
            selectors = [
                "[data-testid='card-play-button']",
                "[aria-label*='Play']",
                ".GlueCard",
                "[data-testid='tracklist-row']",
                "a[href*='/track/']",
                "a[href*='/playlist/']",
                "a[href*='/album/']",
            ]
            for sel in selectors:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    choice = random.choice(els[:5])
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", choice)
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
        """Listen to current track/playlist with realistic behavior."""
        try:
            time.sleep(2)
            self._dismiss_popups()
            self._handle_ads(behavior)

            listen_time = max_seconds or random.randint(60, int(
                behavior.watch_duration_percent * 1800  # max 30 min
            ))
            listen_time = max(30, min(listen_time, 1800))
            print(f"[Spotify {self.profile_id}] 🎵 Listening for {listen_time}s")

            start = time.time()
            while time.time() - start < listen_time:
                if not self._is_browser_alive():
                    return
                if random.random() < 0.08:
                    self._scroll_page(1)
                if random.random() < behavior.pause_probability * 0.3:
                    pause = random.randint(10, 45)
                    print(f"[Spotify {self.profile_id}] ⏸ Idle pause {pause}s")
                    time.sleep(pause)
                else:
                    time.sleep(random.uniform(4, 10))

        except Exception as e:
            print(f"[Spotify {self.profile_id}] Listen error: {e}")

    # ------------------------------------------------------------------
    # Engagement
    # ------------------------------------------------------------------

    def _maybe_like(self, behavior):
        if random.random() > behavior.like_probability:
            return
        try:
            for sel in [
                "button[aria-label*='Save to']",
                "button[aria-label*='Add to Liked']",
                "[data-testid='add-button']",
            ]:
                btns = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if btns and btns[0].is_displayed():
                    btns[0].click()
                    print(f"[Spotify {self.profile_id}] ❤️ Liked track")
                    time.sleep(random.uniform(0.5, 1.5))
                    return
        except Exception:
            pass

    def _maybe_follow_artist(self, behavior):
        if random.random() > behavior.subscribe_probability:
            return
        try:
            for sel in [
                "button[aria-label*='Follow']",
                "[data-testid='follow-button']",
            ]:
                btns = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if btns and btns[0].is_displayed():
                    btns[0].click()
                    print(f"[Spotify {self.profile_id}] ➕ Followed artist")
                    time.sleep(random.uniform(0.5, 1.5))
                    return
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Ads
    # ------------------------------------------------------------------

    def _handle_ads(self, behavior):
        try:
            ad_selectors = [
                "[data-testid='ad-slot']",
                ".advertisement",
                "[aria-label*='Advertisement']",
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
                print(f"[Spotify {self.profile_id}] 📢 Listening to full ad")
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
                "[data-testid='skip-ad-button']",
                ".skip-ad",
            ]:
                btns = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if btns:
                    btns[0].click()
                    print(f"[Spotify {self.profile_id}] ⏭ Skipped ad")
                    time.sleep(1)
                    return
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _dismiss_popups(self):
        selectors = [
            "[data-testid='cookies-banner-accept-button']",
            "button[aria-label='Accept cookies']",
            ".onetrust-accept-btn-handler",
            "[id*='accept']",
        ]
        for sel in selectors:
            try:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed() and any(
                        w in (el.text or "").lower()
                        for w in ["accept", "agree", "ok", "got it", "i agree", "close"]
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
