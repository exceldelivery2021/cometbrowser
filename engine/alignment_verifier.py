"""
Alignment Verifier
Confirms that browser-level fixes actually landed after the page refresh.
Reads directly from the browser via JS — does NOT navigate to an external site
so automation flow is never interrupted.
"""

import time


# IANA timezone → UTC offset in minutes using JS getTimezoneOffset() convention.
# getTimezoneOffset() returns (UTC - local) so UTC+1 → -60, UTC-5 → +300.
# Values use standard (non-DST) offset; we allow ±90 min variance for DST.
_IANA_TO_OFFSET = {
    # Americas
    'America/New_York':      300,
    'America/Chicago':       360,
    'America/Denver':        420,
    'America/Phoenix':       420,
    'America/Los_Angeles':   480,
    'America/Anchorage':     540,
    'America/Honolulu':      600,
    'America/Toronto':       300,
    'America/Vancouver':     480,
    'America/Sao_Paulo':     180,
    'America/Argentina/Buenos_Aires': 180,
    'America/Mexico_City':   360,
    'America/Bogota':        300,
    'America/Lima':          300,
    'America/Santiago':      180,
    'America/Caracas':       270,
    # Europe
    'Europe/London':          0,
    'Europe/Dublin':          0,
    'Europe/Lisbon':          0,
    'Europe/Berlin':         -60,
    'Europe/Paris':          -60,
    'Europe/Madrid':         -60,
    'Europe/Rome':           -60,
    'Europe/Amsterdam':      -60,
    'Europe/Brussels':       -60,
    'Europe/Vienna':         -60,
    'Europe/Zurich':         -60,
    'Europe/Stockholm':      -60,
    'Europe/Oslo':           -60,
    'Europe/Copenhagen':     -60,
    'Europe/Warsaw':         -60,
    'Europe/Prague':         -60,
    'Europe/Budapest':       -60,
    'Europe/Bucharest':     -120,
    'Europe/Helsinki':      -120,
    'Europe/Athens':        -120,
    'Europe/Kiev':          -120,
    'Europe/Moscow':        -180,
    'Europe/Istanbul':      -180,
    # Africa
    'Africa/Cairo':         -120,
    'Africa/Johannesburg':  -120,
    'Africa/Lagos':          -60,
    'Africa/Nairobi':       -180,
    # Asia
    'Asia/Dubai':           -240,
    'Asia/Karachi':         -300,
    'Asia/Kolkata':         -330,
    'Asia/Dhaka':           -360,
    'Asia/Bangkok':         -420,
    'Asia/Jakarta':         -420,
    'Asia/Singapore':       -480,
    'Asia/Kuala_Lumpur':    -480,
    'Asia/Shanghai':        -480,
    'Asia/Hong_Kong':       -480,
    'Asia/Taipei':          -480,
    'Asia/Seoul':           -540,
    'Asia/Tokyo':           -540,
    'Asia/Vladivostok':     -600,
    # Australia / Pacific
    'Australia/Perth':      -480,
    'Australia/Adelaide':   -570,
    'Australia/Sydney':     -600,
    'Australia/Melbourne':  -600,
    'Pacific/Auckland':     -720,
    'Pacific/Honolulu':      600,
    # UTC
    'UTC':                    0,
    'Etc/UTC':                0,
}


class AlignmentVerifier:
    """Verify that browser fixes resolved timezone and language misalignment."""

    def __init__(self, profile_id, db_manager=None):
        self.profile_id = profile_id
        self.db = db_manager

    def verify_alignment(self, driver, geo_data):
        """
        Read timezone offset and language directly from the browser via JS.
        Does NOT navigate to any external site — automation is not interrupted.

        Args:
            driver: Selenium WebDriver (already on whatever page it's on)
            geo_data: dict with keys 'language', 'timezone', 'country_code'

        Returns:
            (language_aligned: bool, timezone_aligned: bool, details: dict)
        """
        if not geo_data:
            return False, False, {}

        print(f"\n[Verifier {self.profile_id}] 🔍 Verifying alignment via browser JS...")

        expected_language = geo_data.get('language', 'en-US')
        expected_timezone = geo_data.get('timezone', 'UTC')
        expected_country = geo_data.get('country_code', 'US')

        try:
            detected_language  = self._detect_browser_language(driver)
            detected_offset    = self._detect_browser_timezone_offset(driver)
            detected_tz_name   = self._detect_browser_timezone_name(driver)

            language_aligned  = self._languages_match(detected_language, expected_language)
            timezone_aligned  = self._timezones_match(detected_offset, expected_timezone, detected_tz_name)

            details = {
                'expected_language':  expected_language,
                'detected_language':  detected_language,
                'language_aligned':   language_aligned,
                'expected_timezone':  expected_timezone,
                'detected_tz_name':   detected_tz_name,
                'detected_tz_offset': detected_offset,
                'timezone_aligned':   timezone_aligned,
                'expected_country':   expected_country,
            }

            self._report(details)
            return language_aligned, timezone_aligned, details

        except Exception as e:
            print(f"[Verifier {self.profile_id}] ⚠️ Verification error: {e}")
            return False, False, {}

    # ------------------------------------------------------------------
    # Detection helpers
    # ------------------------------------------------------------------

    def _detect_browser_language(self, driver):
        """Read navigator.languages[0] then fallback to navigator.language."""
        try:
            lang = driver.execute_script(
                "return (navigator.languages && navigator.languages.length) "
                "? navigator.languages[0] : navigator.language;"
            )
            print(f"[Verifier {self.profile_id}] 📝 Browser language: {lang}")
            return lang
        except Exception:
            return None

    def _detect_browser_timezone_offset(self, driver):
        """Return JS getTimezoneOffset() — (UTC - local) in minutes."""
        try:
            offset = driver.execute_script("return new Date().getTimezoneOffset();")
            print(f"[Verifier {self.profile_id}] 🕐 Timezone offset: {offset} min")
            return int(offset)
        except Exception:
            return None

    def _detect_browser_timezone_name(self, driver):
        """Return the IANA timezone name the browser reports (if available)."""
        try:
            name = driver.execute_script(
                "return Intl.DateTimeFormat().resolvedOptions().timeZone;"
            )
            print(f"[Verifier {self.profile_id}] 🌍 Timezone name: {name}")
            return name
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Matching helpers
    # ------------------------------------------------------------------

    def _languages_match(self, detected, expected):
        """
        Match language codes. Accepts exact match or same primary subtag.
        e.g. 'nl-NL' matches 'nl', 'en-US' matches 'en-GB' at prefix level.
        """
        if not detected or not expected:
            return False
        d = str(detected).lower()
        e = str(expected).lower()
        if d == e:
            return True
        return d.split('-')[0] == e.split('-')[0]

    def _timezones_match(self, detected_offset, expected_tz, detected_tz_name=None):
        """
        Check timezone alignment using two signals:
        1. IANA name match (primary — spoofed by our Intl.DateTimeFormat override)
        2. getTimezoneOffset() offset match ±90 min (fallback / DST tolerance)
        Either signal passing is sufficient.
        """
        if not expected_tz:
            return False

        # Signal 1: IANA name match (most reliable when our Intl spoof is active)
        if detected_tz_name:
            if str(detected_tz_name).strip() == str(expected_tz).strip():
                return True

        if detected_offset is None:
            return False

        expected_offset = _IANA_TO_OFFSET.get(expected_tz)
        if expected_offset is None:
            # Unknown timezone — don't block the session
            print(
                f"[Verifier {self.profile_id}] ⚠️ Unknown IANA tz '{expected_tz}', "
                "assuming aligned"
            )
            return True

        # Signal 2: offset within ±90 min
        match = abs(int(detected_offset) - expected_offset) <= 90
        if not match:
            print(
                f"[Verifier {self.profile_id}] ❌ TZ mismatch: name={detected_tz_name} "
                f"offset={detected_offset}, expected {expected_tz} (~{expected_offset})"
            )
        return match

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def _report(self, data):
        lang_icon = "✅" if data['language_aligned'] else "❌"
        tz_icon   = "✅" if data['timezone_aligned']  else "❌"
        print(
            f"\n[Verifier {self.profile_id}] 📊 ALIGNMENT RESULTS:\n"
            f"  {lang_icon} Language : {data['detected_language']} "
            f"(expected {data['expected_language']})\n"
            f"  {tz_icon} Timezone : {data['detected_tz_name']} "
            f"offset={data['detected_tz_offset']} min "
            f"(expected {data['expected_timezone']})"
        )
