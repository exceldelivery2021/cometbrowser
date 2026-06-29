"""
Browser Alignment Fixer
Applies browser-level fixes for timezone, language, and DNS after IP detection.
All fixes use CDP so they persist across page refreshes.
"""

import time


class BrowserAlignmentFixer:
    """Fix timezone/language/geolocation/WebRTC misalignment at browser level."""

    def __init__(self, driver, profile_id):
        self.driver = driver
        self.profile_id = profile_id
        self.fixes_applied = []

    # ------------------------------------------------------------------
    # Language
    # ------------------------------------------------------------------

    def apply_language_fix(self, language_code):
        """
        Align all language surfaces to match the IP's country language.

        Three surfaces must match or Whoer/sites will flag a mismatch:
          1. Accept-Language HTTP header  (Network.setUserAgentOverride → acceptLanguage)
          2. navigator.language           (Emulation.setLocaleOverride)
          3. navigator.languages[]        (Page.addScriptToEvaluateOnNewDocument override,
                                           run immediately via execute_script as well)

        Args:
            language_code: BCP-47 tag, e.g. 'nl-NL', 'de-DE', 'en-US'
        """
        try:
            base = language_code.split('-')[0]  # 'nl' from 'nl-NL'

            # Build a realistic Accept-Language header value.
            if base == 'en':
                accept_lang = f"{language_code};q=1.0"
                lang_list = [language_code]
            else:
                accept_lang = f"{language_code};q=1.0,{base};q=0.9,en-US;q=0.8,en;q=0.7"
                lang_list = [language_code, base, "en-US", "en"]

            # 1. Accept-Language HTTP header — what servers read
            try:
                current_ua = self.driver.execute_script("return navigator.userAgent;") or ""
                self.driver.execute_cdp_cmd("Network.setUserAgentOverride", {
                    "userAgent": current_ua,
                    "acceptLanguage": accept_lang,
                })
            except Exception as e:
                print(f"[Fixer {self.profile_id}] ⚠️ Accept-Language header update failed: {e}")

            # 2. navigator.language — JS-visible locale
            self.driver.execute_cdp_cmd("Emulation.setLocaleOverride", {"locale": language_code})

            # 3. navigator.languages[] and navigator.language
            #    selenium-stealth defines these with configurable:false, so
            #    Object.defineProperty on the navigator instance fails silently.
            #    Work-around: replace window.navigator itself with a Proxy.
            #    window.navigator IS configurable, so this always succeeds and
            #    intercepts every property read — including language/languages —
            #    before the locked instance properties are reached.
            lang_js_array = str(lang_list).replace("'", '"')
            lang_override_script = f"""
                (function() {{
                    const langs = {lang_js_array};
                    const lang0 = langs[0];
                    try {{
                        const _nav = window.navigator;
                        const navProxy = new Proxy(_nav, {{
                            get: function(target, prop) {{
                                if (prop === 'language')  return lang0;
                                if (prop === 'languages') return langs;
                                const val = target[prop];
                                return (typeof val === 'function') ? val.bind(target) : val;
                            }}
                        }});
                        Object.defineProperty(window, 'navigator', {{
                            get: function() {{ return navProxy; }},
                            configurable: true
                        }});
                    }} catch(e) {{
                        try {{ Object.defineProperty(navigator, 'language',  {{ get: () => lang0, configurable: true }}); }} catch(_) {{}}
                        try {{ Object.defineProperty(navigator, 'languages', {{ get: () => langs,  configurable: true }}); }} catch(_) {{}}
                    }}
                }})();
            """
            # Inject so it runs on every future navigation (survives refresh)
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": lang_override_script},
            )
            # Apply to the current page immediately
            try:
                self.driver.execute_script(lang_override_script)
            except Exception:
                pass

            self.fixes_applied.append('language')
            print(
                f"[Fixer {self.profile_id}] ✅ Language fix applied: {language_code} "
                f"| Accept-Language: {accept_lang}"
            )
            return True

        except Exception as e:
            print(f"[Fixer {self.profile_id}] ⚠️ Language fix failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Timezone
    # ------------------------------------------------------------------

    # Minimal IANA → JS getTimezoneOffset() value map (UTC - local, in minutes).
    # JS getTimezoneOffset() = -(UTC offset in minutes), e.g. UTC+1 → -60, UTC-5 → 300.
    _TZ_OFFSET_MAP = {
        'America/New_York': 300, 'America/Chicago': 360, 'America/Denver': 420,
        'America/Phoenix': 420, 'America/Los_Angeles': 480, 'America/Anchorage': 540,
        'America/Honolulu': 600, 'America/Toronto': 300, 'America/Vancouver': 480,
        'America/Sao_Paulo': 180, 'America/Argentina/Buenos_Aires': 180,
        'America/Mexico_City': 360, 'America/Bogota': 300, 'America/Lima': 300,
        'America/Santiago': 180, 'America/Caracas': 270,
        'Europe/London': 0, 'Europe/Dublin': 0, 'Europe/Lisbon': 0,
        'Europe/Berlin': -60, 'Europe/Paris': -60, 'Europe/Madrid': -60,
        'Europe/Rome': -60, 'Europe/Amsterdam': -60, 'Europe/Brussels': -60,
        'Europe/Vienna': -60, 'Europe/Zurich': -60, 'Europe/Stockholm': -60,
        'Europe/Oslo': -60, 'Europe/Copenhagen': -60, 'Europe/Warsaw': -60,
        'Europe/Prague': -60, 'Europe/Budapest': -60,
        'Europe/Bucharest': -120, 'Europe/Helsinki': -120, 'Europe/Athens': -120,
        'Europe/Kiev': -120, 'Europe/Moscow': -180, 'Europe/Istanbul': -180,
        'Africa/Cairo': -120, 'Africa/Johannesburg': -120,
        'Africa/Lagos': -60, 'Africa/Nairobi': -180,
        'Asia/Dubai': -240, 'Asia/Karachi': -300, 'Asia/Kolkata': -330,
        'Asia/Dhaka': -360, 'Asia/Bangkok': -420, 'Asia/Jakarta': -420,
        'Asia/Singapore': -480, 'Asia/Kuala_Lumpur': -480, 'Asia/Shanghai': -480,
        'Asia/Hong_Kong': -480, 'Asia/Taipei': -480,
        'Asia/Seoul': -540, 'Asia/Tokyo': -540,
        'Australia/Perth': -480, 'Australia/Adelaide': -570,
        'Australia/Sydney': -600, 'Australia/Melbourne': -600,
        'Pacific/Auckland': -720, 'Pacific/Honolulu': 600,
        'UTC': 0, 'Etc/UTC': 0,
    }

    def apply_timezone_fix(self, timezone_str):
        """
        Apply timezone via CDP Emulation.setTimezoneOverride (takes effect on next navigation)
        plus JS overrides for Date.getTimezoneOffset and Intl.DateTimeFormat as
        belt-and-suspenders — these fire immediately on the current page AND persist
        across navigations via addScriptToEvaluateOnNewDocument.

        Args:
            timezone_str: IANA timezone id, e.g. 'Europe/Amsterdam'
        """
        try:
            self.driver.execute_cdp_cmd(
                "Emulation.setTimezoneOverride", {"timezoneId": timezone_str}
            )

            # Compute the expected JS offset (may be None for unknown zones)
            js_offset = self._TZ_OFFSET_MAP.get(timezone_str)

            # Build JS spoof script
            if js_offset is not None:
                offset_spoof = f"""
                    // Spoof Date.prototype.getTimezoneOffset
                    const _origGTO = Date.prototype.getTimezoneOffset;
                    Date.prototype.getTimezoneOffset = function() {{ return {js_offset}; }};
                """
            else:
                offset_spoof = ""

            tz_script = f"""
            (function() {{
                const tz = "{timezone_str}";
                {offset_spoof}
                // Spoof Intl.DateTimeFormat so resolvedOptions().timeZone is correct
                try {{
                    const OrigDTF = Intl.DateTimeFormat;
                    function PatchedDTF(locale, opts) {{
                        opts = Object.assign({{}}, opts || {{}});
                        if (!opts.timeZone) opts.timeZone = tz;
                        return new OrigDTF(locale, opts);
                    }}
                    PatchedDTF.prototype = OrigDTF.prototype;
                    PatchedDTF.supportedLocalesOf = OrigDTF.supportedLocalesOf
                        ? OrigDTF.supportedLocalesOf.bind(OrigDTF) : undefined;
                    Intl.DateTimeFormat = PatchedDTF;
                }} catch(e) {{}}
            }})();
            """
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument", {"source": tz_script}
            )
            try:
                self.driver.execute_script(tz_script)
            except Exception:
                pass
            self.fixes_applied.append('timezone')
            print(f"[Fixer {self.profile_id}] ✅ Timezone fix applied: {timezone_str} "
                  f"(JS offset: {js_offset})")
            return True
        except Exception as e:
            print(f"[Fixer {self.profile_id}] ⚠️ Timezone fix failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Geolocation
    # ------------------------------------------------------------------

    def apply_geolocation_spoof(self, latitude, longitude):
        """
        Spoof navigator.geolocation to match the IP's coordinates.
        JS-injected, so must be re-applied after each page navigation.
        """
        try:
            script = f"""
            (function() {{
                const lat = {float(latitude)};
                const lon = {float(longitude)};
                const mockGeo = {{
                    getCurrentPosition: function(success, error, opts) {{
                        success({{ coords: {{ latitude: lat, longitude: lon, accuracy: 50,
                            altitude: null, altitudeAccuracy: null, heading: null, speed: null }},
                            timestamp: Date.now() }});
                    }},
                    watchPosition: function(success, error, opts) {{
                        success({{ coords: {{ latitude: lat, longitude: lon, accuracy: 50,
                            altitude: null, altitudeAccuracy: null, heading: null, speed: null }},
                            timestamp: Date.now() }});
                        return 1;
                    }},
                    clearWatch: function(id) {{}}
                }};
                try {{
                    Object.defineProperty(navigator, 'geolocation', {{
                        get: function() {{ return mockGeo; }},
                        configurable: true
                    }});
                }} catch(e) {{}}
            }})();
            """
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument", {"source": script}
            )
            self.driver.execute_script(script)
            self.fixes_applied.append('geolocation')
            print(f"[Fixer {self.profile_id}] ✅ Geolocation spoof applied: {latitude}, {longitude}")
            return True
        except Exception as e:
            print(f"[Fixer {self.profile_id}] ⚠️ Geolocation spoof failed: {e}")
            return False

    # ------------------------------------------------------------------
    # WebRTC leak prevention
    # ------------------------------------------------------------------

    def apply_webrtc_fix(self):
        """
        Prevent WebRTC from leaking the real local/public IP.

        Overrides RTCPeerConnection so ICE candidate gathering never exposes
        non-VPN addresses. The browser launch args already include
        --force-webrtc-ip-handling-policy=disable_non_proxied_udp, but this
        JS override adds a second layer for sites that probe via the API.
        """
        try:
            script = """
            (function() {
                const OrigRTCPC = window.RTCPeerConnection
                    || window.webkitRTCPeerConnection
                    || window.mozRTCPeerConnection;
                if (!OrigRTCPC) return;

                function FakeRTCPC(config, constraints) {
                    // Strip any iceServers so STUN/TURN never resolve a real IP
                    const safeConfig = Object.assign({}, config || {}, { iceServers: [] });
                    const pc = new OrigRTCPC(safeConfig, constraints);
                    return pc;
                }
                FakeRTCPC.prototype = OrigRTCPC.prototype;
                FakeRTCPC.generateCertificate = OrigRTCPC.generateCertificate
                    ? OrigRTCPC.generateCertificate.bind(OrigRTCPC) : undefined;

                try {
                    Object.defineProperty(window, 'RTCPeerConnection', {
                        get: function() { return FakeRTCPC; }, configurable: true
                    });
                    window.webkitRTCPeerConnection = FakeRTCPC;
                    window.mozRTCPeerConnection = FakeRTCPC;
                } catch(e) {}
            })();
            """
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument", {"source": script}
            )
            self.driver.execute_script(script)
            self.fixes_applied.append('webrtc')
            print(f"[Fixer {self.profile_id}] ✅ WebRTC leak prevention applied")
            return True
        except Exception as e:
            print(f"[Fixer {self.profile_id}] ⚠️ WebRTC fix failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def apply_all_fixes(self, geo_data):
        """
        Apply CDP-level fixes (timezone + language) that must be set BEFORE the
        next navigation, then stash geo coords for apply_post_refresh_fixes().

        Call order in ghost_core:
            fixer.apply_all_fixes(geo_data)   ← CDP overrides (this method)
            fixer.refresh_browser()            ← navigates; CDP overrides take effect;
                                                  calls apply_post_refresh_fixes() internally

        Args:
            geo_data: dict from IPGeolocationQuery with keys:
                      timezone, language, latitude, longitude
        """
        if not geo_data:
            print(f"[Fixer {self.profile_id}] ❌ No geolocation data provided")
            return False

        print(f"\n[Fixer {self.profile_id}] 🔧 Applying browser alignment fixes...")

        results = []

        # CDP overrides — must come BEFORE the page refresh
        timezone = geo_data.get('timezone', 'UTC')
        results.append(self.apply_timezone_fix(timezone))

        language = geo_data.get('language', 'en-US')
        results.append(self.apply_language_fix(language))

        # Stash geo coords; JS spoofs run after refresh in apply_post_refresh_fixes
        self._pending_geo = (
            geo_data.get('latitude', 40.7128),
            geo_data.get('longitude', -74.0060),
        )

        all_ok = all(results)
        status = "✅ CDP fixes staged" if all_ok else "⚠️ Some CDP fixes failed"
        print(f"[Fixer {self.profile_id}] {status} — refresh browser to activate")
        return all_ok

    def apply_post_refresh_fixes(self):
        """
        Apply JS-injected spoofs after the page has refreshed.
        Called automatically by refresh_browser().
        """
        results = []
        if hasattr(self, '_pending_geo'):
            lat, lon = self._pending_geo
            del self._pending_geo
            results.append(self.apply_geolocation_spoof(lat, lon))
        results.append(self.apply_webrtc_fix())
        return all(results)

    def refresh_browser(self):
        """
        Refresh to activate CDP overrides, then immediately re-inject JS spoofs.
        """
        try:
            print(f"[Fixer {self.profile_id}] 🔄 Refreshing browser to activate alignment fixes...")
            self.driver.refresh()
            time.sleep(3)
            self.apply_post_refresh_fixes()
            print(f"[Fixer {self.profile_id}] ✅ Browser refreshed and post-refresh fixes applied")
            return True
        except Exception as e:
            print(f"[Fixer {self.profile_id}] ⚠️ Browser refresh failed: {e}")
            return False
