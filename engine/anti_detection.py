"""
Runtime browser identity checks.

This module intentionally does not hide automation or bypass site detection.
It reads the browser identity that is currently visible to pages and compares
it with the saved Comet Fleet profile identity.
"""


class AntiDetection:
    """
    Backward-compatible class name used by ghost_core.py.

    The old implementation tried to mutate browser fingerprints at runtime.
    That was unreliable and could conflict with the saved profile identity.
    This corrected version is read-only and deterministic.
    """

    def __init__(self, driver, profile_id):
        self.driver = driver
        self.profile_id = profile_id

    def collect_browser_identity(self):
        """Return the browser-visible identity values for auditing."""
        if self.driver is None:
            return {"ok": False, "error": "driver_missing"}

        try:
            identity = self.driver.execute_script(
                """
                const tz = (() => {
                    try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ""; }
                    catch (e) { return ""; }
                })();

                return {
                    user_agent: navigator.userAgent || "",
                    platform: navigator.platform || "",
                    language: navigator.language || "",
                    languages: Array.from(navigator.languages || []),
                    hardware_concurrency: navigator.hardwareConcurrency || null,
                    device_memory: navigator.deviceMemory || null,
                    max_touch_points: navigator.maxTouchPoints || 0,
                    webdriver: navigator.webdriver === true,
                    timezone: tz,
                    screen_width: screen.width || null,
                    screen_height: screen.height || null,
                    device_pixel_ratio: window.devicePixelRatio || null
                };
                """
            )

            if not isinstance(identity, dict):
                identity = {}

            identity["ok"] = True
            return identity

        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc)
            }

    def compare_to_cloak(self, cloak):
        """Compare browser-visible values with a saved profile cloak."""
        cloak = cloak if isinstance(cloak, dict) else {}
        browser = self.collect_browser_identity()
        mismatches = []

        if not browser.get("ok"):
            return {
                "ok": False,
                "browser": browser,
                "mismatches": ["Could not read browser identity."]
            }

        expected_ua = str(cloak.get("user_agent") or "")
        if expected_ua and expected_ua != str(browser.get("user_agent") or ""):
            mismatches.append("User agent does not match saved profile identity.")

        expected_platform = str(cloak.get("platform") or "")
        if expected_platform and expected_platform != str(browser.get("platform") or ""):
            mismatches.append("Navigator platform does not match saved profile identity.")

        expected_language = str(cloak.get("language") or "")
        if expected_language and expected_language != str(browser.get("language") or ""):
            mismatches.append("Navigator language does not match saved profile identity.")

        expected_cores = cloak.get("hardware_concurrency")
        if expected_cores not in (None, "") and int(expected_cores) != int(browser.get("hardware_concurrency") or 0):
            mismatches.append("CPU core count does not match saved profile identity.")

        expected_memory = cloak.get("device_memory")
        if expected_memory not in (None, "") and int(expected_memory) != int(browser.get("device_memory") or 0):
            mismatches.append("Device memory does not match saved profile identity.")

        expected_touch = cloak.get("touch_points")
        if expected_touch not in (None, "") and int(expected_touch) != int(browser.get("max_touch_points") or 0):
            mismatches.append("Touch point count does not match saved profile identity.")

        resolution = cloak.get("resolution") or []
        if isinstance(resolution, (list, tuple)) and len(resolution) >= 2:
            expected_width = int(resolution[0])
            expected_height = int(resolution[1])
            actual_width = int(browser.get("screen_width") or 0)
            actual_height = int(browser.get("screen_height") or 0)
            if expected_width and expected_height and (expected_width != actual_width or expected_height != actual_height):
                mismatches.append("Screen size does not match saved profile identity.")

        return {
            "ok": len(mismatches) == 0,
            "browser": browser,
            "mismatches": mismatches
        }

    # Backward-compatible method names. They now report instead of mutating.
    def inject_stealth_js(self):
        print(f"[IdentityCheck {self.profile_id}] Runtime JS mutation disabled; using saved profile identity only.")
        return False

    def disable_webrtc_leak(self):
        print(f"[IdentityCheck {self.profile_id}] WebRTC policy is controlled by browser launch arguments.")
        return False

    def spoof_geolocation(self, ip_info):
        print(f"[IdentityCheck {self.profile_id}] Geolocation mutation disabled; reporting only.")
        return False

    def randomize_hardware_fingerprint(self):
        print(f"[IdentityCheck {self.profile_id}] Hardware randomization disabled; saved identity remains stable.")
        return False

    def inject_timezone_spoofing(self, timezone_str):
        print(f"[IdentityCheck {self.profile_id}] Timezone mutation disabled; expected timezone={timezone_str or 'unknown'}.")
        return False

    def apply_all_protections(self, ip_info=None, timezone_str=None, cloak=None):
        """
        Backward-compatible entry point.

        Returns a runtime identity report. It does not alter the browser.
        """
        report = self.compare_to_cloak(cloak or {})
        status = "OK" if report.get("ok") else "WARN"
        print(f"[IdentityCheck {self.profile_id}] Runtime identity check: {status}")
        return report
