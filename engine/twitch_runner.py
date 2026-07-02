from selenium.webdriver.common.by import By

from .base_platform_runner import BasePlatformRunner


class TwitchRunner(BasePlatformRunner):
    platform     = "twitch"
    homepage_url = "https://www.twitch.tv"

    def platform_display_name(self):
        return "Twitch"

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
            cleaned = value.replace("@", "").strip("/")
            return f"https://www.twitch.tv/{self.quote(cleaned)}"

        if target_type == "category":
            return f"https://www.twitch.tv/directory/category/{self.quote(value)}"

        if target_type in ["search", "keyword", "other"]:
            return f"https://www.twitch.tv/search?term={self.quote(value)}"

        return f"https://www.twitch.tv/search?term={self.quote(value)}"

    def inspect_platform_state(self, driver, profile_id, session_id="", selected_target=None):
        events = []

        current_url = self.safe_current_url(driver).lower()
        title       = self.safe_title(driver)

        if "twitch.tv" in current_url:
            events.append("TWITCH_OPENED")
            self.record_event(
                profile_id=profile_id,
                session_id=session_id,
                event_type="TWITCH_OPENED",
                details=f"title={title}; url={current_url}"
            )
        else:
            events.append("TWITCH_URL_NOT_CONFIRMED")
            self.record_event(
                profile_id=profile_id,
                session_id=session_id,
                event_type="TWITCH_URL_NOT_CONFIRMED",
                details=f"title={title}; url={current_url}"
            )

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

        # ── Ad detection (IP quality scoring only — ads are never skipped) ──
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
                    self.record_event(
                        profile_id=profile_id,
                        session_id=session_id,
                        event_type="TWITCH_AD_DETECTED",
                        details=f"selector={sel}"
                    )
                    break

            # On a live channel page with no ad element → record no-ads
            if ads_detected is None and page_type == "channel":
                ads_detected = False
                events.append("TWITCH_NO_AD_ON_CHANNEL")
                self.record_event(
                    profile_id=profile_id,
                    session_id=session_id,
                    event_type="TWITCH_NO_AD_ON_CHANNEL",
                    details=f"url={current_url}"
                )
        except Exception:
            pass

        # ── Live / offline state ──────────────────────────────────────────
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text.lower()

            if "offline" in body_text or "check out this" in body_text:
                live_state = "offline_or_inactive"
                events.append("TWITCH_CHANNEL_OFFLINE_OR_INACTIVE")
            elif "live" in body_text or "viewers" in body_text:
                live_state = "possibly_live"
                events.append("TWITCH_CHANNEL_POSSIBLY_LIVE")
        except Exception:
            pass

        # ── Chat area ─────────────────────────────────────────────────────
        try:
            if driver.find_elements(By.CSS_SELECTOR,
                                    "[data-a-target='chat-input'], textarea"):
                events.append("TWITCH_CHAT_AREA_VISIBLE")
                self.record_event(
                    profile_id=profile_id,
                    session_id=session_id,
                    event_type="TWITCH_CHAT_AREA_VISIBLE",
                    details="Chat area detected"
                )
        except Exception:
            pass

        self.record_event(
            profile_id=profile_id,
            session_id=session_id,
            event_type="TWITCH_PAGE_CLASSIFIED",
            details=f"page_type={page_type}; live_state={live_state}; title={title}; url={current_url}"
        )

        return {
            "ok":           "TWITCH_OPENED" in events,
            "events":       events,
            "ads_detected": ads_detected,
            "page_type":    page_type,
            "live_state":   live_state,
        }
