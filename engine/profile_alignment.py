"""
Profile alignment checks.

This module builds a read-only alignment report for a running profile. It does
not change Windows timezone, system time, or DNS because those settings are
machine-wide and would break multiple profiles running at the same time.
"""

from datetime import datetime
import re

try:
    from pytz import timezone as pytz_timezone
except Exception:
    pytz_timezone = None


class ProfileAligner:
    """Checks whether a saved profile identity is internally consistent with the live IP."""

    TIMEZONE_MAP = {
        "US": "America/New_York",
        "CA": "America/Toronto",
        "GB": "Europe/London",
        "DE": "Europe/Berlin",
        "FR": "Europe/Paris",
        "ES": "Europe/Madrid",
        "IT": "Europe/Rome",
        "NL": "Europe/Amsterdam",
        "SE": "Europe/Stockholm",
        "CH": "Europe/Zurich",
        "AT": "Europe/Vienna",
        "BE": "Europe/Brussels",
        "PL": "Europe/Warsaw",
        "RU": "Europe/Moscow",
        "JP": "Asia/Tokyo",
        "AU": "Australia/Sydney",
        "NZ": "Pacific/Auckland",
        "SG": "Asia/Singapore",
        "HK": "Asia/Hong_Kong",
        "CN": "Asia/Shanghai",
        "IN": "Asia/Kolkata",
        "BR": "America/Sao_Paulo",
        "MX": "America/Mexico_City",
        "AR": "America/Argentina/Buenos_Aires",
        "ZA": "Africa/Johannesburg",
        "AE": "Asia/Dubai",
        "KR": "Asia/Seoul",
        "DO": "America/Santo_Domingo",
    }

    LOCALE_MAP = {
        "US": "en-US",
        "GB": "en-GB",
        "CA": "en-CA",
        "AU": "en-AU",
        "DE": "de-DE",
        "FR": "fr-FR",
        "ES": "es-ES",
        "IT": "it-IT",
        "NL": "nl-NL",
        "SE": "sv-SE",
        "CH": "de-CH",
        "AT": "de-AT",
        "BE": "nl-BE",
        "JP": "ja-JP",
        "KR": "ko-KR",
        "CN": "zh-CN",
        "BR": "pt-BR",
        "MX": "es-MX",
        "AR": "es-AR",
        "ZA": "en-ZA",
        "AE": "ar-AE",
        "DO": "es-DO",
    }

    COUNTRY_NAME_MAP = {
        "UNITED STATES": "US",
        "UNITED STATES OF AMERICA": "US",
        "USA": "US",
        "CANADA": "CA",
        "UNITED KINGDOM": "GB",
        "GREAT BRITAIN": "GB",
        "ENGLAND": "GB",
        "GERMANY": "DE",
        "FRANCE": "FR",
        "SPAIN": "ES",
        "ITALY": "IT",
        "NETHERLANDS": "NL",
        "SWEDEN": "SE",
        "SWITZERLAND": "CH",
        "AUSTRIA": "AT",
        "BELGIUM": "BE",
        "POLAND": "PL",
        "RUSSIA": "RU",
        "JAPAN": "JP",
        "AUSTRALIA": "AU",
        "NEW ZEALAND": "NZ",
        "SINGAPORE": "SG",
        "HONG KONG": "HK",
        "CHINA": "CN",
        "INDIA": "IN",
        "BRAZIL": "BR",
        "MEXICO": "MX",
        "ARGENTINA": "AR",
        "SOUTH AFRICA": "ZA",
        "UNITED ARAB EMIRATES": "AE",
        "SOUTH KOREA": "KR",
        "KOREA": "KR",
        "DOMINICAN REPUBLIC": "DO",
    }

    def __init__(self, db_manager=None):
        self.db = db_manager
        self.alignment_history = {}

    def _raw_ip_info(self, ip_info):
        if not isinstance(ip_info, dict):
            return {}
        raw = ip_info.get("raw")
        return raw if isinstance(raw, dict) else ip_info

    def get_country_code(self, ip_info):
        raw = self._raw_ip_info(ip_info)
        country = (
            raw.get("country_code")
            or raw.get("countryCode")
            or raw.get("country_code2")
            or raw.get("countryCode2")
            or raw.get("country")
            or raw.get("country_name")
            or raw.get("countryName")
            or ""
        )
        country = str(country or "").strip()
        if not country and isinstance(ip_info, dict):
            country = self._country_from_label(ip_info.get("label", ""))

        country = country.strip()
        if len(country) == 2 and country.isalpha():
            return country.upper()

        return self.COUNTRY_NAME_MAP.get(country.upper(), "")

    def _country_from_label(self, label):
        label = str(label or "").strip()
        if not label:
            return ""

        # Labels usually look like: IP | City, Region, Country | ISP
        parts = [part.strip() for part in label.split("|")]
        if len(parts) >= 2:
            location = parts[1]
            location_parts = [part.strip() for part in location.split(",") if part.strip()]
            if location_parts:
                return location_parts[-1]

        for name in sorted(self.COUNTRY_NAME_MAP, key=len, reverse=True):
            if re.search(rf"\b{re.escape(name)}\b", label, flags=re.IGNORECASE):
                return name

        return ""

    def get_timezone_from_ip(self, ip_info):
        raw = self._raw_ip_info(ip_info)
        direct = raw.get("timezone") or raw.get("time_zone") or raw.get("tz")
        if isinstance(direct, dict):
            direct = direct.get("id") or direct.get("name") or direct.get("timezone") or ""
        if direct:
            return str(direct).strip()

        country = self.get_country_code(ip_info)
        return self.TIMEZONE_MAP.get(country, "UTC")

    def get_locale_from_ip(self, ip_info):
        country = self.get_country_code(ip_info)
        return self.LOCALE_MAP.get(country, "en-US")

    def get_current_time_label(self, timezone_str):
        if not timezone_str or pytz_timezone is None:
            return ""
        try:
            tz = pytz_timezone(timezone_str)
            return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
        except Exception:
            return ""

    def set_windows_timezone(self, timezone_str, profile_id):
        """
        Backward-compatible method.

        Intentionally does not call tzutil. Windows timezone is global and cannot
        safely represent multiple simultaneous profile regions.
        """
        print(f"[Alignment {profile_id}] Windows timezone unchanged. Expected profile timezone: {timezone_str or 'unknown'}")
        return False

    def set_system_time(self, timezone_str, profile_id):
        """Backward-compatible read-only time report."""
        time_label = self.get_current_time_label(timezone_str)
        if time_label:
            print(f"[Alignment {profile_id}] Time in {timezone_str}: {time_label}")
        return True

    def configure_dns(self, profile_id, dns_servers=None):
        """
        Backward-compatible method.

        DNS is not changed here. DNS should come from the active VPN/proxy or
        network adapter policy, not from per-profile browser code.
        """
        planned = dns_servers or []
        print(f"[Alignment {profile_id}] DNS unchanged. Expected DNS should be provided by VPN/proxy. Planned={planned}")
        return False

    def get_browser_args(self, ip_info, profile_id):
        """Return the locale/timezone plan for reporting and future launch-time use."""
        timezone_str = self.get_timezone_from_ip(ip_info)
        locale = self.get_locale_from_ip(ip_info)
        country = self.get_country_code(ip_info)

        return {
            "timezone": timezone_str,
            "locale": locale,
            "country": country,
            "launch_args": [
                f"--accept-lang={locale}",
                f"--lang={locale}",
            ],
            "note": "Returned for reporting; ghost_core uses the saved profile identity at launch."
        }

    def evaluate_profile(self, profile_id, ip_info, cloak=None, browser_identity=None):
        """Build a profile/IP/browser alignment report."""
        cloak = cloak if isinstance(cloak, dict) else {}
        browser_identity = browser_identity if isinstance(browser_identity, dict) else {}

        timezone_str = self.get_timezone_from_ip(ip_info)
        locale = self.get_locale_from_ip(ip_info)
        country = self.get_country_code(ip_info)
        ip_label = ""
        if isinstance(ip_info, dict):
            ip_label = str(ip_info.get("label") or ip_info.get("ip") or "")

        warnings = []

        profile_language = str(cloak.get("language") or "")
        if profile_language and locale and profile_language.split("-")[0] != locale.split("-")[0]:
            warnings.append(f"Profile language {profile_language} differs from IP locale {locale}.")

        browser_language = str(browser_identity.get("language") or "")
        if browser_language and profile_language and browser_language != profile_language:
            warnings.append(f"Browser language {browser_language} differs from saved profile language {profile_language}.")

        browser_timezone = str(browser_identity.get("timezone") or "")
        if browser_timezone and timezone_str and browser_timezone != timezone_str:
            warnings.append(f"Browser timezone {browser_timezone} differs from IP timezone {timezone_str}.")

        if browser_identity.get("webdriver") is True:
            warnings.append("Browser reports navigator.webdriver=true.")

        report = {
            "ok": len(warnings) == 0,
            "profile_id": int(profile_id),
            "ip": ip_info.get("ip") if isinstance(ip_info, dict) else "",
            "ip_label": ip_label,
            "country": country,
            "expected_timezone": timezone_str,
            "expected_locale": locale,
            "current_time_at_ip": self.get_current_time_label(timezone_str),
            "profile_language": profile_language,
            "browser_language": browser_language,
            "browser_timezone": browser_timezone,
            "warnings": warnings,
            "actions_taken": {
                "windows_timezone_changed": False,
                "system_time_changed": False,
                "dns_changed": False,
                "browser_identity_mutated": False,
            },
        }

        self.alignment_history[int(profile_id)] = report
        return report

    def align_profile(self, profile_id, ip_info, cloak=None, browser_identity=None):
        """
        Backward-compatible entry point.

        Returns a read-only alignment report plus the browser config plan.
        """
        browser_config = self.get_browser_args(ip_info, profile_id)
        report = self.evaluate_profile(
            profile_id,
            ip_info,
            cloak=cloak,
            browser_identity=browser_identity
        )
        report["config"] = browser_config
        print(f"[Alignment {profile_id}] Alignment check complete. ok={report.get('ok')}")
        return report
