import random
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from .base_platform_runner import BasePlatformRunner


_RANDOM_SEARCHES = [
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


class DeezerRunner(BasePlatformRunner):
    platform     = "deezer"
    homepage_url = "https://www.deezer.com"

    def platform_display_name(self):
        return "Deezer"

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
            return (f"https://www.deezer.com/artist/{cleaned}"
                    if cleaned.isdigit()
                    else f"https://www.deezer.com/search/{self.quote(cleaned)}/artist")

        if target_type in ["song", "track"]:
            return (f"https://www.deezer.com/track/{cleaned}"
                    if cleaned.isdigit()
                    else f"https://www.deezer.com/search/{self.quote(cleaned)}/track")

        if target_type == "album":
            return (f"https://www.deezer.com/album/{cleaned}"
                    if cleaned.isdigit()
                    else f"https://www.deezer.com/search/{self.quote(cleaned)}/album")

        if target_type == "playlist":
            return (f"https://www.deezer.com/playlist/{cleaned}"
                    if cleaned.isdigit()
                    else f"https://www.deezer.com/search/{self.quote(cleaned)}/playlist")

        return f"https://www.deezer.com/search/{self.quote(cleaned)}"

    # ── Navigation ────────────────────────────────────────────────────

    def _open_targeted(self, driver, target) -> bool:
        try:
            url = self.build_target_url(target)
            driver.get(url)
            self.wait_for_page_ready(driver)
            self._dismiss_popups(driver)
            self._click_first_item(driver)
            return True
        except Exception:
            return False

    def _open_random(self, driver) -> bool:
        try:
            if random.random() < 0.5:
                term = random.choice(_RANDOM_SEARCHES)
                driver.get(f"https://www.deezer.com/us/search/{self.quote(term)}")
            else:
                driver.get(random.choice(_GENRE_URLS))
            self.wait_for_page_ready(driver)
            self._dismiss_popups(driver)
            self._click_first_item(driver)
            return True
        except Exception:
            return False

    def _click_first_item(self, driver):
        try:
            selectors = [
                "a[href*='/track/']",
                "a[href*='/album/']",
                "a[href*='/playlist/']",
                ".datagrid-item a",
                ".ResultsGrid a",
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
                "button[aria-label*='Favorite']",
                "button[aria-label*='Love']",
                "[data-testid='love-button']",
                ".love-button",
                "button[title*='Favorite']",
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
        # Deezer uses "Add to My Music" for artists
        try:
            for sel in [
                "button[aria-label*='Add to My Music']",
                "button[title*='Add to My Music']",
                "[data-testid='add-to-library']",
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
        # Deezer does not have a comment section in its web player
        return False

    # ── Page inspection + ad detection ───────────────────────────────

    def inspect_platform_state(self, driver, profile_id, session_id="", selected_target=None):
        events      = []
        current_url = self.safe_current_url(driver).lower()
        title       = self.safe_title(driver)

        if "deezer.com" in current_url:
            events.append("DEEZER_OPENED")
        else:
            events.append("DEEZER_URL_NOT_CONFIRMED")
            return {"ok": False, "events": events, "ads_detected": None, "page_type": "unknown"}

        page_type = "unknown"
        if "/artist/" in current_url:
            page_type = "artist";   events.append("DEEZER_ARTIST_PAGE_DETECTED")
        elif "/track/" in current_url:
            page_type = "track";    events.append("DEEZER_TRACK_PAGE_DETECTED")
        elif "/album/" in current_url:
            page_type = "album";    events.append("DEEZER_ALBUM_PAGE_DETECTED")
        elif "/playlist/" in current_url:
            page_type = "playlist"; events.append("DEEZER_PLAYLIST_PAGE_DETECTED")
        elif "/search/" in current_url:
            page_type = "search";   events.append("DEEZER_SEARCH_PAGE_DETECTED")

        # Ad detection (observe only — never skip)
        ads_detected = None
        try:
            ad_selectors = [
                ".ads-player",
                "[data-testid='ad-banner']",
                ".advertisement",
                "iframe[src*='ads']",
                "iframe[src*='doubleclick']",
                "[class*='ads-']",
            ]
            for sel in ad_selectors:
                if driver.find_elements(By.CSS_SELECTOR, sel):
                    ads_detected = True
                    events.append("DEEZER_AD_DETECTED")
                    break

            if ads_detected is None and page_type in ("track", "artist", "album", "playlist"):
                ads_detected = False
                events.append("DEEZER_NO_AD_ON_CONTENT")
        except Exception:
            pass

        try:
            body = driver.find_element(By.TAG_NAME, "body").text.lower()
            if "log in" in body or "sign up" in body:
                events.append("DEEZER_LOGIN_PROMPT_VISIBLE")
            if "not available" in body or "unavailable" in body:
                events.append("DEEZER_CONTENT_UNAVAILABLE")
        except Exception:
            pass

        self.record_event(profile_id, session_id, "DEEZER_PAGE_CLASSIFIED",
                          f"page_type={page_type}; url={current_url}")

        return {"ok": True, "events": events, "ads_detected": ads_detected, "page_type": page_type}

    # ── Popup dismissal ───────────────────────────────────────────────

    def _dismiss_popups(self, driver):
        selectors = [
            "#gdpr-banner-accept",
            "button[aria-label*='Accept']",
            ".didomi-continue-without-agreeing",
            "[id*='onetrust-accept']",
        ]
        for sel in selectors:
            try:
                for el in driver.find_elements(By.CSS_SELECTOR, sel):
                    if el.is_displayed() and any(
                        w in (el.text or "").lower()
                        for w in ["accept", "agree", "ok", "got it", "continue", "close"]
                    ):
                        el.click()
                        time.sleep(0.4)
            except Exception:
                pass
