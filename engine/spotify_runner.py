import random
import time

from selenium.webdriver.common.by import By

from .base_platform_runner import BasePlatformRunner


_RANDOM_SEARCHES = [
    "chill vibes", "hip hop", "pop hits", "lofi", "workout",
    "jazz", "classical", "rock", "edm", "r&b", "indie", "country",
    "study music", "sleep sounds", "top hits", "new releases",
    "rap", "blues", "reggae", "latin", "k-pop", "soul", "funk",
]

_GENRE_URLS = [
    "https://open.spotify.com/genre/pop",
    "https://open.spotify.com/genre/hiphop",
    "https://open.spotify.com/genre/rock",
    "https://open.spotify.com/genre/electronic",
    "https://open.spotify.com/genre/rnb",
    "https://open.spotify.com/genre/country",
    "https://open.spotify.com/genre/latin",
    "https://open.spotify.com/genre/jazz",
    "https://open.spotify.com/browse/featured",
]


class SpotifyRunner(BasePlatformRunner):
    platform     = "spotify"
    homepage_url = "https://open.spotify.com"

    def platform_display_name(self):
        return "Spotify"

    # ── URL builder ───────────────────────────────────────────────────

    def build_target_url(self, target):
        if not target:
            return self.homepage_url

        direct_url = str(target.get("url") or "").strip()
        if direct_url:
            return direct_url

        target_type = str(target.get("target_type") or "").strip().lower()
        value       = self.clean_identifier_or_title(target)

        if not value:
            return self.homepage_url

        cleaned = value.strip()

        if target_type == "artist":
            return (f"https://open.spotify.com/artist/{cleaned}"
                    if self._is_spotify_id(cleaned)
                    else f"https://open.spotify.com/search/{self.quote(cleaned)}/artists")

        if target_type in ["song", "track"]:
            return (f"https://open.spotify.com/track/{cleaned}"
                    if self._is_spotify_id(cleaned)
                    else f"https://open.spotify.com/search/{self.quote(cleaned)}/tracks")

        if target_type == "album":
            return (f"https://open.spotify.com/album/{cleaned}"
                    if self._is_spotify_id(cleaned)
                    else f"https://open.spotify.com/search/{self.quote(cleaned)}/albums")

        if target_type == "playlist":
            return (f"https://open.spotify.com/playlist/{cleaned}"
                    if self._is_spotify_id(cleaned)
                    else f"https://open.spotify.com/search/{self.quote(cleaned)}/playlists")

        return f"https://open.spotify.com/search/{self.quote(cleaned)}"

    def _is_spotify_id(self, value):
        v = str(value or "").strip()
        return len(v) >= 15 and "/" not in v and " " not in v and "spotify" not in v.lower()

    # ── Navigation ────────────────────────────────────────────────────

    def _open_targeted(self, driver, target) -> bool:
        try:
            url = self.build_target_url(target)
            driver.get(url)
            self.wait_for_page_ready(driver)
            self._dismiss_popups(driver)
            self._click_first_playable(driver)
            return True
        except Exception:
            return False

    def _open_random(self, driver) -> bool:
        try:
            if random.random() < 0.5:
                term = random.choice(_RANDOM_SEARCHES)
                driver.get(f"https://open.spotify.com/search/{self.quote(term)}")
            else:
                driver.get(random.choice(_GENRE_URLS))
            self.wait_for_page_ready(driver)
            self._dismiss_popups(driver)
            self._click_first_playable(driver)
            return True
        except Exception:
            return False

    def _click_first_playable(self, driver):
        try:
            selectors = [
                "[data-testid='card-play-button']",
                "[aria-label*='Play']",
                "a[href*='/track/']",
                "a[href*='/playlist/']",
                "a[href*='/album/']",
                ".GlueCard",
            ]
            for sel in selectors:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    choice = random.choice(els[:5])
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", choice
                    )
                    choice.click()
                    time.sleep(random.uniform(1.5, 3.0))
                    return
        except Exception:
            pass

    # ── Engagement ────────────────────────────────────────────────────

    def _try_like(self, driver) -> bool:
        try:
            for sel in [
                "button[aria-label*='Save to']",
                "button[aria-label*='Add to Liked']",
                "[data-testid='add-button']",
            ]:
                btns = driver.find_elements(By.CSS_SELECTOR, sel)
                if btns and btns[0].is_displayed():
                    btns[0].click()
                    time.sleep(random.uniform(0.5, 1.2))
                    return True
        except Exception:
            pass
        return False

    def _try_follow(self, driver) -> bool:
        try:
            for sel in [
                "button[aria-label*='Follow']",
                "[data-testid='follow-button']",
            ]:
                btns = driver.find_elements(By.CSS_SELECTOR, sel)
                if btns and btns[0].is_displayed():
                    btns[0].click()
                    time.sleep(random.uniform(0.5, 1.2))
                    return True
        except Exception:
            pass
        return False

    def _try_comment(self, driver) -> bool:
        # Spotify Web Player has no public comment feature — skip
        return False

    # ── Page inspection + ad detection ───────────────────────────────

    def inspect_platform_state(self, driver, profile_id, session_id="", selected_target=None):
        events      = []
        current_url = self.safe_current_url(driver).lower()
        title       = self.safe_title(driver)

        if "open.spotify.com" in current_url:
            events.append("SPOTIFY_OPENED")
        else:
            events.append("SPOTIFY_URL_NOT_CONFIRMED")
            return {"ok": False, "events": events, "ads_detected": None, "page_type": "unknown"}

        page_type = "unknown"
        if "/artist/" in current_url:
            page_type = "artist";   events.append("SPOTIFY_ARTIST_PAGE_DETECTED")
        elif "/track/" in current_url:
            page_type = "track";    events.append("SPOTIFY_TRACK_PAGE_DETECTED")
        elif "/album/" in current_url:
            page_type = "album";    events.append("SPOTIFY_ALBUM_PAGE_DETECTED")
        elif "/playlist/" in current_url:
            page_type = "playlist"; events.append("SPOTIFY_PLAYLIST_PAGE_DETECTED")
        elif "/search/" in current_url:
            page_type = "search";   events.append("SPOTIFY_SEARCH_PAGE_DETECTED")

        # Ad detection (observe only — never skip)
        ads_detected = None
        try:
            ad_selectors = [
                "[data-testid='ad-slot']",
                "[data-testid='advertisement']",
                ".advertisement",
                "[aria-label*='Advertisement']",
                "audio[src*='audio-ak-spotify']",
            ]
            for sel in ad_selectors:
                if driver.find_elements(By.CSS_SELECTOR, sel):
                    ads_detected = True
                    events.append("SPOTIFY_AD_DETECTED")
                    break

            if ads_detected is None and page_type in ("track", "artist", "album", "playlist"):
                ads_detected = False
                events.append("SPOTIFY_NO_AD_ON_CONTENT")
        except Exception:
            pass

        try:
            body = driver.find_element(By.TAG_NAME, "body").text.lower()
            if "log in" in body or "sign up" in body:
                events.append("SPOTIFY_LOGIN_PROMPT_VISIBLE")
            if "not available" in body or "unavailable" in body:
                events.append("SPOTIFY_CONTENT_UNAVAILABLE")
        except Exception:
            pass

        self.record_event(profile_id, session_id, "SPOTIFY_PAGE_CLASSIFIED",
                          f"page_type={page_type}; url={current_url}")

        return {"ok": True, "events": events, "ads_detected": ads_detected, "page_type": page_type}

    # ── Popup dismissal ───────────────────────────────────────────────

    def _dismiss_popups(self, driver):
        selectors = [
            "[data-testid='cookies-banner-accept-button']",
            "button[aria-label='Accept cookies']",
            ".onetrust-accept-btn-handler",
        ]
        for sel in selectors:
            try:
                for el in driver.find_elements(By.CSS_SELECTOR, sel):
                    if el.is_displayed() and any(
                        w in (el.text or "").lower()
                        for w in ["accept", "agree", "ok", "got it", "close"]
                    ):
                        el.click()
                        time.sleep(0.4)
            except Exception:
                pass
