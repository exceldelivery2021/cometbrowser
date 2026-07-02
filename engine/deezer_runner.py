from selenium.webdriver.common.by import By

from .base_platform_runner import BasePlatformRunner


class DeezerRunner(BasePlatformRunner):
    platform     = "deezer"
    homepage_url = "https://www.deezer.com"

    def platform_display_name(self):
        return "Deezer"

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
            if cleaned.isdigit():
                return f"https://www.deezer.com/artist/{cleaned}"
            return f"https://www.deezer.com/search/{self.quote(cleaned)}/artist"

        if target_type in ["song", "track"]:
            if cleaned.isdigit():
                return f"https://www.deezer.com/track/{cleaned}"
            return f"https://www.deezer.com/search/{self.quote(cleaned)}/track"

        if target_type == "album":
            if cleaned.isdigit():
                return f"https://www.deezer.com/album/{cleaned}"
            return f"https://www.deezer.com/search/{self.quote(cleaned)}/album"

        if target_type == "playlist":
            if cleaned.isdigit():
                return f"https://www.deezer.com/playlist/{cleaned}"
            return f"https://www.deezer.com/search/{self.quote(cleaned)}/playlist"

        if target_type in ["search", "keyword", "other"]:
            return f"https://www.deezer.com/search/{self.quote(cleaned)}"

        return f"https://www.deezer.com/search/{self.quote(cleaned)}"

    def inspect_platform_state(self, driver, profile_id, session_id="", selected_target=None):
        events = []

        current_url = self.safe_current_url(driver).lower()
        title       = self.safe_title(driver)

        if "deezer.com" in current_url:
            events.append("DEEZER_OPENED")
            self.record_event(
                profile_id=profile_id,
                session_id=session_id,
                event_type="DEEZER_OPENED",
                details=f"title={title}; url={current_url}"
            )
        else:
            events.append("DEEZER_URL_NOT_CONFIRMED")
            self.record_event(
                profile_id=profile_id,
                session_id=session_id,
                event_type="DEEZER_URL_NOT_CONFIRMED",
                details=f"title={title}; url={current_url}"
            )

        page_type = "unknown"

        if "/artist/" in current_url:
            page_type = "artist"
            events.append("DEEZER_ARTIST_PAGE_DETECTED")
        elif "/track/" in current_url:
            page_type = "track"
            events.append("DEEZER_TRACK_PAGE_DETECTED")
        elif "/album/" in current_url:
            page_type = "album"
            events.append("DEEZER_ALBUM_PAGE_DETECTED")
        elif "/playlist/" in current_url:
            page_type = "playlist"
            events.append("DEEZER_PLAYLIST_PAGE_DETECTED")
        elif "/search/" in current_url:
            page_type = "search"
            events.append("DEEZER_SEARCH_PAGE_DETECTED")

        # ── Ad detection (IP quality scoring only — ads are never skipped) ──
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
                    self.record_event(
                        profile_id=profile_id,
                        session_id=session_id,
                        event_type="DEEZER_AD_DETECTED",
                        details=f"selector={sel}"
                    )
                    break

            # On content pages with no ad element → record no-ads
            if ads_detected is None and page_type in ("track", "artist", "album", "playlist"):
                ads_detected = False
                events.append("DEEZER_NO_AD_ON_CONTENT")
                self.record_event(
                    profile_id=profile_id,
                    session_id=session_id,
                    event_type="DEEZER_NO_AD_ON_CONTENT",
                    details=f"page_type={page_type}; url={current_url}"
                )
        except Exception:
            pass

        # ── Login / availability checks ───────────────────────────────────
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text.lower()

            if "log in" in body_text or "sign up" in body_text:
                events.append("DEEZER_LOGIN_PROMPT_VISIBLE")
                self.record_event(
                    profile_id=profile_id,
                    session_id=session_id,
                    event_type="DEEZER_LOGIN_PROMPT_VISIBLE",
                    details="Login/sign-up prompt detected"
                )

            if "not available" in body_text or "unavailable" in body_text:
                events.append("DEEZER_CONTENT_UNAVAILABLE")
                self.record_event(
                    profile_id=profile_id,
                    session_id=session_id,
                    event_type="DEEZER_CONTENT_UNAVAILABLE",
                    details="Unavailable content text detected"
                )
        except Exception:
            pass

        self.record_event(
            profile_id=profile_id,
            session_id=session_id,
            event_type="DEEZER_PAGE_CLASSIFIED",
            details=f"page_type={page_type}; title={title}; url={current_url}"
        )

        return {
            "ok":           "DEEZER_OPENED" in events,
            "events":       events,
            "ads_detected": ads_detected,
            "page_type":    page_type,
        }
