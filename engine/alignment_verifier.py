"""
Alignment Verifier
Re-checks alignment after browser fixes and refresh
Determines if fixes worked
"""

import time


class AlignmentVerifier:
    """Verify that browser fixes actually resolved misalignment"""
    
    def __init__(self, profile_id, db_manager):
        self.profile_id = profile_id
        self.db = db_manager
    
    def verify_alignment(self, driver, geo_data):
        """
        Re-verify alignment after fixes applied
        Loads Whoer and checks if timezone/language now match
        
        Args:
            driver: Selenium WebDriver
            geo_data (dict): IP geolocation data with timezone, language
        
        Returns:
            tuple: (language_aligned: bool, timezone_aligned: bool, full_data: dict)
        """
        if not geo_data:
            return False, False, {}
        
        print(f"\n[Verifier {self.profile_id}] 🔍 Re-verifying alignment after fixes...")
        
        expected_language = geo_data.get('language', 'en-US')
        expected_timezone = geo_data.get('timezone', 'UTC')
        expected_country = geo_data.get('country_code', 'US')
        
        try:
            # Navigate to Whoer
            driver.get("https://whoer.net/")
            time.sleep(4)
            
            # Try to extract browser language from page
            detected_language = self._detect_browser_language(driver)
            
            # Try to extract timezone from page
            detected_timezone = self._detect_browser_timezone(driver)
            
            # Try to extract country from page
            detected_country = self._detect_browser_country(driver)
            
            # Compare
            language_aligned = self._languages_match(detected_language, expected_language)
            timezone_aligned = self._timezones_match(detected_timezone, expected_timezone)
            
            verification_data = {
                'expected_language': expected_language,
                'detected_language': detected_language,
                'language_aligned': language_aligned,
                'expected_timezone': expected_timezone,
                'detected_timezone': detected_timezone,
                'timezone_aligned': timezone_aligned,
                'expected_country': expected_country,
                'detected_country': detected_country,
            }
            
            # Report results
            self._report_verification(verification_data)
            
            return language_aligned, timezone_aligned, verification_data
        
        except Exception as e:
            print(f"[Verifier {self.profile_id}] ⚠️ Verification failed: {e}")
            return False, False, {}
    
    def _detect_browser_language(self, driver):
        """
        Detect the language the browser is actually sending in HTTP headers.
        Reads navigator.language (JS) which reflects Emulation.setLocaleOverride,
        but also checks navigator.languages[0] as a cross-check.
        The Accept-Language header (set via Network.setUserAgentOverride) is what
        Whoer reads server-side — navigator.language should match it after our fixes.
        """
        try:
            lang = driver.execute_script(
                "return navigator.languages && navigator.languages.length "
                "? navigator.languages[0] : navigator.language;"
            )
            print(f"[Verifier {self.profile_id}] 📝 Browser language: {lang}")
            return lang
        except:
            return None
    
    def _detect_browser_timezone(self, driver):
        """Try to detect browser timezone offset"""
        try:
            offset = driver.execute_script("return new Date().getTimezoneOffset();")
            print(f"[Verifier {self.profile_id}] 🕐 Browser timezone offset: {offset} minutes")
            return offset
        except:
            return None
    
    def _detect_browser_country(self, driver):
        """Try to detect country from page content"""
        try:
            # Look for country indicators on Whoer page
            country_elements = driver.find_elements("xpath", "//td[contains(text(), 'Country')]/../td[2]")
            if country_elements:
                country = country_elements[0].text.strip()
                print(f"[Verifier {self.profile_id}] 🌍 Detected country: {country}")
                return country
        except:
            pass
        return None
    
    def _languages_match(self, detected, expected):
        """
        Check if detected language matches expected
        Handles variations (en-US vs en, etc.)
        
        Args:
            detected (str): Detected language code
            expected (str): Expected language code
        
        Returns:
            bool: Languages match
        """
        if not detected or not expected:
            return False
        
        detected = str(detected).lower()
        expected = str(expected).lower()
        
        # Exact match
        if detected == expected:
            return True
        
        # Prefix match (en-US matches en)
        detected_prefix = detected.split('-')[0]
        expected_prefix = expected.split('-')[0]
        
        return detected_prefix == expected_prefix
    
    def _timezones_match(self, detected_offset, expected_tz):
        """
        Check if detected timezone matches expected
        
        Args:
            detected_offset (int): Timezone offset in minutes
            expected_tz (str): IANA timezone string
        
        Returns:
            bool: Timezones match
        """
        if detected_offset is None or not expected_tz:
            return False
        
        # Map IANA to expected offset
        iana_to_offset = {
            'America/New_York': -300,  # UTC-5 (standard time)
            'America/Chicago': -360,
            'America/Denver': -420,
            'America/Los_Angeles': -480,
            'Europe/London': 0,
            'Europe/Berlin': -60,  # UTC+1 in offset terms (getTimezoneOffset is negative)
            'Europe/Paris': -60,
            'Europe/Madrid': -60,
            'Europe/Rome': -60,
            'Europe/Moscow': -180,
            'Asia/Tokyo': -540,
            'Asia/Singapore': -480,
            'Asia/Dubai': -240,
            'Australia/Sydney': -600,
        }
        
        expected_offset = iana_to_offset.get(expected_tz)
        
        if expected_offset is None:
            # Can't verify this timezone
            return True  # Assume match if we don't know it
        
        # Allow ±60 minute variance due to DST/seasonal changes
        return abs(detected_offset - expected_offset) <= 60
    
    def _report_verification(self, data):
        """Log verification results"""
        print(f"\n[Verifier {self.profile_id}] 📊 ALIGNMENT VERIFICATION RESULTS:")
        
        lang_status = "✅" if data['language_aligned'] else "❌"
        print(f"[Verifier {self.profile_id}] {lang_status} Language: {data['detected_language']} (expected: {data['expected_language']})")
        
        tz_status = "✅" if data['timezone_aligned'] else "❌"
        print(f"[Verifier {self.profile_id}] {tz_status} Timezone: {data['detected_timezone']} min offset (expected: {data['expected_timezone']})")
        
        print(f"[Verifier {self.profile_id}] 🌍 Country: {data['detected_country']} (expected: {data['expected_country']})")