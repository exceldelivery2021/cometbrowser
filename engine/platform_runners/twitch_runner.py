import random
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from .base_runner import BasePlatformRunner


_CHAT_MESSAGES = [
    "LUL", "PogChamp", "Pog", "KEKW", "monkaS", "pepeLaugh",
    "nice", "lol", "gg", "ez", "let's go", "POG", "Sadge",
    "LULW", "based", "W", "actually insane", "no way",
    "PauseChamp", "Clap", "OMEGALUL", "FeelsBadMan", "FeelsGoodMan",
    "HeyGuys", "BibleThump", "kreygasm", "VoHiYo",
    "hypers", "widepeepoHappy", "peepoHappy", "monkaW",
]

_RANDOM_SEARCHES = [
    "just chatting", "gaming", "music", "art", "irl", "slots",
    "minecraft", "fortnite", "variety", "programming", "chess",
    "valorant", "league of legends", "apex legends", "gta",
    "pokemon", "cooking", "travel", "asmr", "talk shows",
]

_RANDOM_CATEGORIES = [
    "https://www.twitch.tv/directory/category/just-chatting",
    "https://www.twitch.tv/directory/category/gaming",
    "https://www.twitch.tv/directory/category/music",
    "https://www.twitch.tv/directory/category/art",
    "https://www.twitch.tv/directory/category/sports",
    "https://www.twitch.tv/directory",
]


class TwitchRunner(BasePlatformRunner):
    platform     = "twitch"
    homepage_url = "https://www.twitch.tv"

    def platform_display_name(self):
        return "Twitch"

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
            return f"https://www.twitch.tv/{self.quote(value.replace('@', '').strip('/'))}"
        if target_type == "category":
            return f"https://www.twitch.tv/directory/category/{self.quote(value)}"
        if target_type in ["search", "keyword", "other"]:
            return f"https://www.twitch.tv/search?term={self.quote(value)}"

        return f"https://www.twitch.tv/search?term={self.quote(value)}"

    # ── Navigation ────────────────────────────────────────────────────

    def _open_targeted(self, driver, target) -> bool:
        try:
            url = self.build_target_url(target)
            driver.get(url)
            self.wait_for_page_ready(driver)
            self._dismiss_popups(driver)
            return True
        except Exception:
            return False

    def _open_random(self, driver) -> bool:
        try:
            if random.random() < 0.5:
                term = random.choice(_RANDOM_SEARCHES)
                driver.get(f"https://www.twitch.tv/search?term={self.quote(term)}")
            else:
                driver.get(random.choice(_RANDOM_CATEGORIES))
            self.wait_for_page_ready(driver)
            self._dismiss_popups(driver)
            self._click_first_stream(driver)
            return True
        except Exception:
            return False

    def _click_first_stream(self, driver):
        try:
            selectors = [
                "a[data-a-target='preview-card-image-link']",
                ".tw-tower a",
                "article a",
                ".stream-thumbnail a",
            ]
            for sel in selectors:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    choice = random.choice(els[:5])
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
            for sel in ["button[aria-label*='thumbs']", "[data-a-target='thumbs-up-button']"]:
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
                "button[data-a-target='follow-button']",
                "[data-test-selector='follow-button']",
            ]:
                btns = driver.find_elements(By.CSS_SELECTOR, sel)
                if btns and btns[0].is_displayed():
                    btns[0].click()
                    time.sleep(random.uniform(0.8, 1.5))
                    return True
        except Exception:
            pass
        return False

    def _try_comment(self, driver) -> bool:
        try:
            chat_input = None
            for sel in [
                "textarea[data-a-target='chat-input']",
                ".chat-input textarea",
                "#chat-input",
            ]:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els and els[0].is_displayed():
                    chat_input = els[0]
                    break

            if not chat_input:
                return False

            msg = random.choice(_CHAT_MESSAGES)
            chat_input.click()
            time.sleep(random.uniform(0.3, 0.8))
            chat_input.send_keys(msg)
            time.sleep(random.uniform(0.5, 1.2))
            chat_input.send_keys(Keys.RETURN)
            time.sleep(random.uniform(1.0, 2.0))
            return True
        except Exception:
            return False

    def _dwell_extra(self, driver, tick_seconds):
        if random.random() < 0.20:
            try:
                chat = driver.find_elements(
                    By.CSS_SELECTOR, ".chat-scrollable-area__message-container"
                )
                if chat:
                    driver.execute_script(
                        "arguments[0].scrollTop = arguments[0].scrollHeight;", chat[0]
                    )
            except Exception:
                pass

    # ── Page inspection + ad detection ───────────────────────────────

    def inspect_platform_state(self, driver, profile_id, session_id="", selected_target=None):
        events      = []
        current_url = self.safe_current_url(driver).lower()
        title       = self.safe_title(driver)

        if "twitch.tv" in current_url:
            events.append("TWITCH_OPENED")
        else:
            events.append("TWITCH_URL_NOT_CONFIRMED")
            return {"ok": False, "events": events, "ads_detected": None, "page_type": "unknown"}

        page_type  = "unknown"
        live_state = "unknown"

        if "/directory/category/" in current_url:
            page_type = "category"
            events.append("TWITCH_CATEGORY_PAGE_DETECTED")
        elif "/search" in current_url:
            page_type = "search"
            events.append("TWITCH_SEARCH_PAGE_DETECTED")
        elif "twitch.tv/" in current_url and "/directory" not in current_url:
            page_type = "channel"
            events.append("TWITCH_CHANNEL_PAGE_DETECTED")

        # Ad detection — observe only, never skip
        ads_detected = None
        try:
            ad_selectors = [
                "[data-a-target='ad-overlay']",
                ".player-ad-overlay",
                ".tw-ad",
                "[data-test-selector='ad-banner-default']",
            ]
            for sel in ad_selectors:
                if driver.find_elements(By.CSS_SELECTOR, sel):
                    ads_detected = True
                    events.append("TWITCH_AD_DETECTED")
                    break
            if ads_detected is None and page_type == "channel":
                ads_detected = False
                events.append("TWITCH_NO_AD_ON_CHANNEL")
        except Exception:
            pass

        try:
            body = driver.find_element(By.TAG_NAME, "body").text.lower()
            if "offline" in body or "check out this" in body:
                live_state = "offline_or_inactive"
                events.append("TWITCH_CHANNEL_OFFLINE_OR_INACTIVE")
            elif "live" in body or "viewers" in body:
                live_state = "possibly_live"
                events.append("TWITCH_CHANNEL_POSSIBLY_LIVE")
        except Exception:
            pass

        try:
            if driver.find_elements(By.CSS_SELECTOR,
                                    "[data-a-target='chat-input'], textarea"):
                events.append("TWITCH_CHAT_AREA_VISIBLE")
        except Exception:
            pass

        self.record_event(profile_id, session_id, "TWITCH_PAGE_CLASSIFIED",
                          f"page_type={page_type}; live_state={live_state}; url={current_url}")

        return {
            "ok":           True,
            "events":       events,
            "ads_detected": ads_detected,
            "page_type":    page_type,
            "live_state":   live_state,
        }

    # ── Popup dismissal ───────────────────────────────────────────────

    def _dismiss_popups(self, driver):
        selectors = [
            "[data-a-target='consent-banner-accept']",
            "button[data-a-target='tw-core-button-label-text']",
            "[data-a-target='player-overlay-mature-accept']",
            ".tw-button--primary",
        ]
        for sel in selectors:
            try:
                for el in driver.find_elements(By.CSS_SELECTOR, sel):
                    if el.is_displayed() and any(
                        w in (el.text or "").lower()
                        for w in ["accept", "agree", "ok", "got it", "i agree",
                                  "start watching", "confirm"]
                    ):
                        el.click()
                        time.sleep(0.4)
            except Exception:
                pass
