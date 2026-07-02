import random
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from .base_runner import BasePlatformRunner


_RANDOM_SEARCHES = [
    "technology", "music", "gaming", "vlog", "tutorial",
    "entertainment", "news", "education", "sports", "comedy",
    "cooking", "travel", "fitness", "diy", "science",
    "documentary", "reaction", "review", "shorts", "podcast",
]

_RANDOM_CATEGORIES = [
    "https://www.youtube.com/feed/trending",
    "https://www.youtube.com/feed/explore",
    "https://www.youtube.com/?feature=shorts",
    "https://www.youtube.com",
]


class YouTubeRunner(BasePlatformRunner):
    platform     = "youtube"
    homepage_url = "https://www.youtube.com"

    def platform_display_name(self):
        return "YouTube"

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

        if target_type == "channel":
            cleaned = value.lstrip("@").strip("/")
            return f"https://www.youtube.com/@{self.quote(cleaned)}"

        if target_type == "video":
            if len(value) == 11 and " " not in value:
                return f"https://www.youtube.com/watch?v={value}"
            return f"https://www.youtube.com/results?search_query={self.quote(value)}"

        if target_type == "playlist":
            if value.startswith("PL") or value.startswith("UU"):
                return f"https://www.youtube.com/playlist?list={value}"
            return f"https://www.youtube.com/results?search_query={self.quote(value)}"

        if target_type in ["search", "keyword", "other"]:
            return f"https://www.youtube.com/results?search_query={self.quote(value)}"

        # Fallback: treat as search
        return f"https://www.youtube.com/results?search_query={self.quote(value)}"

    # ── Navigation ────────────────────────────────────────────────────

    def _open_targeted(self, driver, target) -> bool:
        try:
            url = self.build_target_url(target)
            driver.get(url)
            self.wait_for_page_ready(driver)
            self._dismiss_popups(driver)
            # If we landed on a channel/search page, click the first video
            current = self.safe_current_url(driver)
            if "/watch" not in current:
                self._click_first_video(driver)
            return True
        except Exception:
            return False

    def _open_random(self, driver) -> bool:
        try:
            if random.random() < 0.6:
                term = random.choice(_RANDOM_SEARCHES)
                driver.get(
                    f"https://www.youtube.com/results?search_query={self.quote(term)}"
                )
                self.wait_for_page_ready(driver)
                self._dismiss_popups(driver)
                self._click_first_video(driver)
            else:
                driver.get(random.choice(_RANDOM_CATEGORIES))
                self.wait_for_page_ready(driver)
                self._dismiss_popups(driver)
                # Try recommended / trending video
                self._click_first_video(driver)
            return True
        except Exception:
            return False

    def _click_first_video(self, driver):
        try:
            selectors = [
                "a#video-title",
                "a.yt-simple-endpoint[href*='/watch']",
                "ytd-video-renderer a#thumbnail",
                "ytd-compact-video-renderer a#thumbnail",
                "ytd-rich-item-renderer a#thumbnail",
            ]
            for sel in selectors:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    choice = random.choice(els[:8])
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", choice
                    )
                    choice.click()
                    time.sleep(random.uniform(2, 4))
                    self._dismiss_popups(driver)
                    return
        except Exception:
            pass

    # ── Engagement ────────────────────────────────────────────────────

    def _try_like(self, driver) -> bool:
        try:
            selectors = [
                "ytd-toggle-button-renderer[is-icon-button] button",
                "button[aria-label*='like this video']",
                "button[aria-label*='Like']",
                ".yt-spec-button-toggle-round",
            ]
            for sel in selectors:
                btns = driver.find_elements(By.CSS_SELECTOR, sel)
                for btn in btns[:3]:
                    label = (btn.get_attribute("aria-label") or "").lower()
                    if "like" in label and "dislike" not in label and btn.is_displayed():
                        btn.click()
                        time.sleep(random.uniform(0.5, 1.2))
                        return True
        except Exception:
            pass
        return False

    def _try_follow(self, driver) -> bool:
        """Subscribe to channel."""
        try:
            selectors = [
                "button[aria-label*='Subscribe']",
                "ytd-subscribe-button-renderer button",
                "#subscribe-button button",
            ]
            for sel in selectors:
                btns = driver.find_elements(By.CSS_SELECTOR, sel)
                if btns and btns[0].is_displayed():
                    label = (btns[0].get_attribute("aria-label") or "").lower()
                    # Only click if not already subscribed
                    if "subscribed" not in label:
                        btns[0].click()
                        time.sleep(random.uniform(0.8, 1.5))
                        return True
        except Exception:
            pass
        return False

    def _try_comment(self, driver) -> bool:
        """
        YouTube comment posting requires sign-in and is a high-risk action.
        We scroll to the comment section to simulate reading comments instead,
        which is realistic behaviour without posting.
        """
        try:
            driver.execute_script(
                "window.scrollTo(0, document.documentElement.scrollHeight * 0.6);"
            )
            time.sleep(random.uniform(2, 5))
            # Scroll back up a little
            driver.execute_script("window.scrollBy(0, -300);")
            time.sleep(random.uniform(0.5, 1.5))
            return True  # counts as comment-section engagement
        except Exception:
            return False

    def _dwell_extra(self, driver, tick_seconds):
        """Occasionally watch the next recommended video during long dwell."""
        if random.random() < 0.08:
            try:
                recs = driver.find_elements(
                    By.CSS_SELECTOR,
                    "ytd-compact-video-renderer a#thumbnail, "
                    "ytd-watch-next-secondary-results-renderer a#thumbnail"
                )
                if recs:
                    choice = random.choice(recs[:5])
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", choice
                    )
                    choice.click()
                    time.sleep(random.uniform(2, 4))
            except Exception:
                pass

    # ── Page inspection + ad detection ───────────────────────────────

    def inspect_platform_state(self, driver, profile_id, session_id="", selected_target=None):
        events      = []
        current_url = self.safe_current_url(driver).lower()
        title       = self.safe_title(driver)

        if "youtube.com" in current_url:
            events.append("YOUTUBE_OPENED")
        else:
            events.append("YOUTUBE_URL_NOT_CONFIRMED")
            return {"ok": False, "events": events, "ads_detected": None, "page_type": "unknown"}

        page_type = "unknown"
        if "/watch" in current_url:
            page_type = "video"
            events.append("YOUTUBE_VIDEO_PAGE_DETECTED")
        elif "/results" in current_url or "/search" in current_url:
            page_type = "search"
            events.append("YOUTUBE_SEARCH_PAGE_DETECTED")
        elif "/@" in current_url or "/channel/" in current_url or "/c/" in current_url:
            page_type = "channel"
            events.append("YOUTUBE_CHANNEL_PAGE_DETECTED")
        elif "/playlist" in current_url:
            page_type = "playlist"
            events.append("YOUTUBE_PLAYLIST_PAGE_DETECTED")
        elif "/feed/" in current_url or current_url.endswith("youtube.com/"):
            page_type = "home"
            events.append("YOUTUBE_HOME_PAGE_DETECTED")

        # Ad detection — observe only, never skip
        ads_detected = None
        try:
            ad_selectors = [
                ".ytp-ad-overlay-container",
                ".ytp-ad-player-overlay",
                ".ytp-ad-skip-button",
                "div[id='player-ads']",
                ".video-ads",
            ]
            for sel in ad_selectors:
                if driver.find_elements(By.CSS_SELECTOR, sel):
                    ads_detected = True
                    events.append("YOUTUBE_AD_DETECTED")
                    break

            # On a video page with no ad element → record no-ads
            if ads_detected is None and page_type == "video":
                ads_detected = False
                events.append("YOUTUBE_NO_AD_ON_VIDEO")
        except Exception:
            pass

        # Video loaded check
        try:
            if driver.find_elements(By.CSS_SELECTOR, "video.html5-main-video"):
                events.append("YOUTUBE_VIDEO_ELEMENT_FOUND")
        except Exception:
            pass

        self.record_event(profile_id, session_id, "YOUTUBE_PAGE_CLASSIFIED",
                          f"page_type={page_type}; title={title}; url={current_url}")

        return {
            "ok":           True,
            "events":       events,
            "ads_detected": ads_detected,
            "page_type":    page_type,
        }

    # ── Popup dismissal ───────────────────────────────────────────────

    def _dismiss_popups(self, driver):
        selectors = [
            "button[aria-label='Accept all']",
            "button[aria-label='Agree to the use of cookies']",
            ".ytd-consent-bump-v2-lightbox button",
            "#dialog button.yt-spec-button-shape-next--filled",
        ]
        for sel in selectors:
            try:
                for el in driver.find_elements(By.CSS_SELECTOR, sel):
                    if el.is_displayed() and any(
                        w in (el.text or "").lower()
                        for w in ["accept", "agree", "ok", "got it", "i agree", "continue"]
                    ):
                        el.click()
                        time.sleep(0.4)
            except Exception:
                pass
