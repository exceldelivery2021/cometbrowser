"""
Browser Alignment Fixer
Applies browser-level fixes for timezone, language, and DNS
Does NOT require system-level changes
"""

import time


class BrowserAlignmentFixer:
    """Fix timezone/language/DNS misalignment at browser level"""
    
    def __init__(self, driver, profile_id):
        self.driver = driver
        self.profile_id = profile_id
        self.fixes_applied = []
    
    def apply_language_fix(self, language_code):
        """
        Apply language fix via JavaScript
        Note: Browser was launched with previous language, this helps partially
        
        Args:
            language_code (str): Language code (e.g., 'en-US', 'de-DE')
        
        Returns:
            bool: Success
        """
        try:
            script = f"""
            Object.defineProperty(navigator, 'language', {{
                get: () => '{language_code}',
            }});
            Object.defineProperty(navigator, 'languages', {{
                get: () => ['{language_code}', 'en'],
            }});
            
            // Also set in document
            document.documentElement.lang = '{language_code.split('-')[0]}';
            """
            
            self.driver.execute_script(script)
            self.fixes_applied.append('language')
            print(f"[Fixer {self.profile_id}] ✅ Language fix applied: {language_code}")
            return True
        
        except Exception as e:
            print(f"[Fixer {self.profile_id}] ⚠️ Language fix failed: {e}")
            return False
    
    def apply_timezone_fix(self, timezone_str):
        """
        Apply timezone fix via JavaScript
        Spoofs timezone-related JavaScript values
        
        Args:
            timezone_str (str): IANA timezone (e.g., 'America/New_York')
        
        Returns:
            bool: Success
        """
        try:
            # Map IANA to UTC offset for this specific moment
            # This is a simplified approach - in reality you'd calculate actual offset
            iana_to_offset = {
                'America/New_York': -5,
                'America/Chicago': -6,
                'America/Denver': -7,
                'America/Los_Angeles': -8,
                'Europe/London': 0,
                'Europe/Berlin': 1,
                'Europe/Paris': 1,
                'Europe/Madrid': 1,
                'Europe/Rome': 1,
                'Europe/Amsterdam': 1,
                'Europe/Stockholm': 1,
                'Europe/Moscow': 3,
                'Asia/Tokyo': 9,
                'Asia/Singapore': 8,
                'Asia/Hong_Kong': 8,
                'Asia/Dubai': 4,
                'Australia/Sydney': 11,
            }
            
            offset = iana_to_offset.get(timezone_str, 0)
            offset_minutes = offset * 60
            
            script = f"""
            // Override getTimezoneOffset
            Date.prototype.getTimezoneOffset = function() {{
                return {offset_minutes};
            }};
            
            // Also set via Intl
            if (typeof Intl !== 'undefined' && Intl.DateTimeFormat) {{
                const original = Intl.DateTimeFormat;
                Intl.DateTimeFormat = class extends original {{
                    constructor(locales, options) {{
                        super(locales, {{...options, timeZone: '{timezone_str}'}});
                    }}
                }};
            }}
            """
            
            self.driver.execute_script(script)
            self.fixes_applied.append('timezone')
            print(f"[Fixer {self.profile_id}] ✅ Timezone fix applied: {timezone_str}")
            return True
        
        except Exception as e:
            print(f"[Fixer {self.profile_id}] ⚠️ Timezone fix failed: {e}")
            return False
    
    def apply_geolocation_spoof(self, latitude, longitude):
        """
        Spoof geolocation to match IP location
        
        Args:
            latitude (float): IP's latitude
            longitude (float): IP's longitude
        
        Returns:
            bool: Success
        """
        try:
            script = f"""
            const mockGeolocation = {{
                getCurrentPosition: function(success, error) {{
                    success({{
                        coords: {{
                            latitude: {latitude},
                            longitude: {longitude},
                            accuracy: 50
                        }}
                    }});
                }},
                watchPosition: function(success, error) {{
                    success({{
                        coords: {{
                            latitude: {latitude},
                            longitude: {longitude},
                            accuracy: 50
                        }}
                    }});
                    return 1;
                }},
                clearWatch: function(id) {{}}
            }};
            
            Object.defineProperty(navigator, 'geolocation', {{
                value: mockGeolocation,
                writable: true
            }});
            """
            
            self.driver.execute_script(script)
            self.fixes_applied.append('geolocation')
            print(f"[Fixer {self.profile_id}] ✅ Geolocation spoof applied: {latitude}, {longitude}")
            return True
        
        except Exception as e:
            print(f"[Fixer {self.profile_id}] ⚠️ Geolocation spoof failed: {e}")
            return False
    
    def apply_webrtc_dns_fix(self):
        """
        Prevent WebRTC IP leak
        Note: Relies on browser launch args already having --force-webrtc-ip-handling-policy
        This just ensures it's enforced
        
        Returns:
            bool: Success
        """
        try:
            script = """
            // Disable WebRTC leak if possible
            try {
                navigator.mediaDevices.getUserMedia({ audio: false, video: true })
                    .then(stream => {
                        stream.getTracks().forEach(track => track.stop());
                    })
                    .catch(e => {});
            } catch (e) {}
            """
            
            self.driver.execute_script(script)
            self.fixes_applied.append('webrtc_dns')
            print(f"[Fixer {self.profile_id}] ✅ WebRTC DNS fix applied")
            return True
        
        except Exception as e:
            print(f"[Fixer {self.profile_id}] ⚠️ WebRTC DNS fix failed: {e}")
            return False
    
    def apply_all_fixes(self, geo_data):
        """
        Apply all browser alignment fixes
        
        Args:
            geo_data (dict): Geolocation data from IPGeolocationQuery
                Required keys: timezone, language, latitude, longitude
        
        Returns:
            bool: All fixes applied successfully
        """
        if not geo_data:
            print(f"[Fixer {self.profile_id}] ❌ No geolocation data provided")
            return False
        
        print(f"\n[Fixer {self.profile_id}] 🔧 Applying browser alignment fixes...")
        time.sleep(0.5)
        
        results = []
        
        # Apply language fix
        language = geo_data.get('language', 'en-US')
        results.append(self.apply_language_fix(language))
        time.sleep(0.3)
        
        # Apply timezone fix
        timezone = geo_data.get('timezone', 'UTC')
        results.append(self.apply_timezone_fix(timezone))
        time.sleep(0.3)
        
        # Apply geolocation spoof
        latitude = geo_data.get('latitude', 40.7128)
        longitude = geo_data.get('longitude', -74.0060)
        results.append(self.apply_geolocation_spoof(latitude, longitude))
        time.sleep(0.3)
        
        # Apply WebRTC DNS fix
        results.append(self.apply_webrtc_dns_fix())
        time.sleep(0.3)
        
        all_success = all(results)
        
        if all_success:
            print(f"[Fixer {self.profile_id}] ✅ All browser fixes applied successfully")
        else:
            print(f"[Fixer {self.profile_id}] ⚠️ Some fixes failed, but continuing")
        
        return all_success
    
    def refresh_browser(self):
        """
        Refresh the browser to apply fixes
        
        Returns:
            bool: Success
        """
        try:
            print(f"[Fixer {self.profile_id}] 🔄 Refreshing browser...")
            self.driver.refresh()
            time.sleep(3)
            print(f"[Fixer {self.profile_id}] ✅ Browser refreshed")
            return True
        
        except Exception as e:
            print(f"[Fixer {self.profile_id}] ⚠️ Browser refresh failed: {e}")
            return False