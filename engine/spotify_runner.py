from selenium.webdriver.common.by import By

from .base_platform_runner import BasePlatformRunner


class SpotifyRunner(BasePlatformRunner):
    platform     = "spotify"
    homepage_url = "https://open.spotify.com"

    def platform_display_name(self):
        return "Spotify"

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
            if self._looks_like_spotify_id(cleaned):
                return f"https://open.spotify.com/artist/{cleaned}"
            return f"https://open.spotify.com/search/{self.quote(cleaned)}/artists"

        if target_type in ["song", "track"]:
            if self._looks_like_spotify_id(cleaned):
                return f"https://open.spotify.com/track/{cleaned}"
            return f"https://open.spotify.com/search/{self.quote(cleaned)}/tracks"

        if target_type == "album":
            if self._looks_like_spotify_id(cleaned):
                return f"https://open.spotify.com/album/{cleaned}"
            return f"https://open.spotify.com/search/{self.quote(cleaned)}/albums"

        if target_type == "playlist":
            if self._looks_like_spotify_id(cleaned):
                return f"https://open.spotify.com/playlist/{cleaned}"
            return f"https://open.spotify.com/search/{self.quote(cleaned)}/playlists"

        if target_type in ["search", "keyword", "other"]:
            return f"https://open.spotify.com/search/{self.quote(cleaned)}"

        return f"https://open.spotify.com/search/{self.quote(cleaned)}"

    def _looks_like_spotify_id(self, value):
        value = str(value or "").strip()
        return (
            len(value) >= 15
            and "/" not in value
            and " " not in value
            and "spotify" not in value.lower()
        )

    def inspect_platform_state(self, driver, profile_id, session_id="", selected_target=None):
        events = []

        current_url = self.safe_current_url(driver).lower()
        title       = self.safe_title(driver)

        if "open.spotify.com" in current_url:
            events.append("SPOTIFY_OPENED")
            self.record_event(
                profile_id=profile_id,
                session_id=session_id,
                event_type="SPOTIFY_OPENED",
                details=f"title={title}; url={current_url}"
            )
        else:
            events.append("SPOTIFY_URL_NOT_CONFIRMED")
            self.record_event(
                profile_id=profile_id,
                session_id=session_id,
                event_type="SPOTIFY_URL_NOT_CONFIRMED",
                details=f"title={title}; url={current_url}"
            )

        page_type = "unknown"

        if "/artist/" in current_url:
            page_type = "artist"
            events.append("SPOTIFY_ARTIST_PAGE_DETECTED")
        elif "/track/" in current_url:
            page_type = "track"
            events.append("SPOTIFY_TRACK_PAGE_DETECTED")
        elif "/album/" in current_url:
            page_type = "album"
            events.append("SPOTIFY_ALBUM_PAGE_DETECTED")
        elif "/playlist/" in current_url:
            page_type = "playlist"
            events.append("SPOTIFY_PLAYLIST_PAGE_DETECTED")
        elif "/search/" in current_url:
            page_type = "search"
            events.append("SPOTIFY_SEARCH_PAGE_DETECTED")

        # ── Ad detection (IP quality scoring only — ads are never skipped) ──
        ads_detected = None
        try:
            ad_selectors = [
                "[data-testid='ad-slot']",
                "[data-testid='advertisement']",
                ".advertisement",
                "[aria-label*='Advertisement']",
                "audio[src*='audio-ak-spotify']",   # Spotify audio ad marker
            ]
            for sel in ad_selectors:
                if driver.find_elements(By.CSS_SELECTOR, sel):
                    ads_detected = True
                    events.append("SPOTIFY_AD_DETECTED")
                    self.record_event(
                        profile_id=profile_id,
                        session_id=session_id,
                        event_type="SPOTIFY_AD_DETECTED",
                        details=f"selector={sel}"
                    )
                    break

            # On a content page with no ad element → record no-ads
            if ads_detected is None and page_type in ("track", "artist", "album", "playlist"):
                ads_detected = False
                events.append("SPOTIFY_NO_AD_ON_CONTENT")
                self.record_event(
                    profile_id=profile_id,
                    session_id=session_id,
                    event_type="SPOTIFY_NO_AD_ON_CONTENT",
                    details=f"page_type={page_type}; url={current_url}"
                )
        except Exception:
            pass

        # ── Login / availability checks ───────────────────────────────────
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text.lower()

            if "log in" in body_text or "sign up" in body_text:
                events.append("SPOTIFY_LOGIN_PROMPT_VISIBLE")
                self.record_event(
                    profile_id=profile_id,
                    session_id=session_id,
                    event_type="SPOTIFY_LOGIN_PROMPT_VISIBLE",
                    details="Login/sign-up prompt detected"
                )

            if "not available" in body_text or "unavailable" in body_text:
                events.append("SPOTIFY_CONTENT_UNAVAILABLE")
                self.record_event(
                    profile_id=profile_id,
                    session_id=session_id,
                    event_type="SPOTIFY_CONTENT_UNAVAILABLE",
                    details="Unavailable content text detected"
                )
        except Exception:
            pass

        self.record_event(
            profile_id=profile_id,
            session_id=session_id,
            event_type="SPOTIFY_PAGE_CLASSIFIED",
            details=f"page_type={page_type}; title={title}; url={current_url}"
        )

        return {
            "ok":           "SPOTIFY_OPENED" in events,
            "events":       events,
            "ads_detected": ads_detected,
            "page_type":    page_type,
        }
