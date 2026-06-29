"""
IP Geolocation Query System
Extracts detailed location/timezone/language data from IP addresses
"""

import requests
import json
import time


class IPGeolocationQuery:
    """Query detailed geolocation data from IP addresses"""
    
    def __init__(self, profile_id, timeout=5):
        self.profile_id = profile_id
        self.timeout = timeout
        self.last_query = None
    
    def query_ipapi_co(self, ip_address):
        """
        Query ip-api.co for geolocation
        Free tier: fast, good accuracy
        
        Args:
            ip_address (str): IP to query
        
        Returns:
            dict: Geolocation data or None
        """
        try:
            url = f"https://ipapi.co/{ip_address}/json/"
            response = requests.get(url, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                self.last_query = data
                return {
                    'ip': ip_address,
                    'country_code': data.get('country_code', '').upper(),
                    'country_name': data.get('country_name', ''),
                    'city': data.get('city', ''),
                    'timezone': data.get('timezone', 'UTC'),
                    'language': self._infer_language_from_country(data.get('country_code', '')),
                    'latitude': float(data.get('latitude', 0)),
                    'longitude': float(data.get('longitude', 0)),
                    'org': data.get('org', ''),
                    'provider': 'ipapi.co'
                }
        except Exception as e:
            print(f"[GeoQuery {self.profile_id}] ⚠️ ipapi.co failed: {e}")
            return None
    
    def query_ipwhois_io(self, ip_address):
        """
        Query ipwhois.io for geolocation
        Alternative provider for redundancy
        
        Args:
            ip_address (str): IP to query
        
        Returns:
            dict: Geolocation data or None
        """
        try:
            url = f"https://ipwhois.io/api/json/ip"
            params = {'ip': ip_address}
            response = requests.get(url, params=params, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    country_code = data.get('country_code', '').upper()
                    self.last_query = data
                    return {
                        'ip': ip_address,
                        'country_code': country_code,
                        'country_name': data.get('country', ''),
                        'city': data.get('city', ''),
                        'timezone': data.get('timezone', 'UTC'),
                        'language': self._infer_language_from_country(country_code),
                        'latitude': float(data.get('latitude', 0)),
                        'longitude': float(data.get('longitude', 0)),
                        'org': data.get('org', ''),
                        'provider': 'ipwhois.io'
                    }
        except Exception as e:
            print(f"[GeoQuery {self.profile_id}] ⚠️ ipwhois.io failed: {e}")
            return None
    
    def _infer_language_from_country(self, country_code):
        """Map ISO 3166-1 alpha-2 country code to primary BCP-47 language tag."""
        country_to_language = {
            # English
            'US': 'en-US', 'CA': 'en-CA', 'GB': 'en-GB', 'AU': 'en-AU',
            'NZ': 'en-NZ', 'IE': 'en-IE', 'ZA': 'en-ZA', 'IN': 'en-IN',
            'NG': 'en-NG', 'GH': 'en-GH', 'KE': 'en-KE', 'PH': 'en-PH',
            'SG': 'en-SG', 'MY': 'ms-MY',
            # German
            'DE': 'de-DE', 'AT': 'de-AT', 'CH': 'de-CH', 'LI': 'de-LI',
            'LU': 'lb-LU',
            # French
            'FR': 'fr-FR', 'BE': 'fr-BE', 'MC': 'fr-MC',
            # Spanish
            'ES': 'es-ES', 'MX': 'es-MX', 'AR': 'es-AR', 'CO': 'es-CO',
            'CL': 'es-CL', 'PE': 'es-PE', 'VE': 'es-VE', 'EC': 'es-EC',
            'BO': 'es-BO', 'PY': 'es-PY', 'UY': 'es-UY', 'CR': 'es-CR',
            'GT': 'es-GT', 'HN': 'es-HN', 'SV': 'es-SV', 'NI': 'es-NI',
            'PA': 'es-PA', 'DO': 'es-DO', 'CU': 'es-CU',
            # Portuguese
            'BR': 'pt-BR', 'PT': 'pt-PT', 'AO': 'pt-AO', 'MZ': 'pt-MZ',
            # Dutch
            'NL': 'nl-NL', 'SR': 'nl-SR',
            # Italian
            'IT': 'it-IT', 'SM': 'it-SM', 'VA': 'it-VA',
            # Nordic
            'SE': 'sv-SE', 'NO': 'nb-NO', 'DK': 'da-DK', 'FI': 'fi-FI',
            'IS': 'is-IS',
            # Eastern European
            'PL': 'pl-PL', 'CZ': 'cs-CZ', 'SK': 'sk-SK', 'HU': 'hu-HU',
            'RO': 'ro-RO', 'BG': 'bg-BG', 'HR': 'hr-HR', 'SI': 'sl-SI',
            'RS': 'sr-RS', 'UA': 'uk-UA', 'BY': 'be-BY',
            # Russian / CIS
            'RU': 'ru-RU', 'KZ': 'ru-KZ', 'UZ': 'uz-UZ', 'GE': 'ka-GE',
            'AM': 'hy-AM', 'AZ': 'az-AZ',
            # Middle East / North Africa
            'AE': 'ar-AE', 'SA': 'ar-SA', 'EG': 'ar-EG', 'IQ': 'ar-IQ',
            'JO': 'ar-JO', 'KW': 'ar-KW', 'LB': 'ar-LB', 'LY': 'ar-LY',
            'MA': 'ar-MA', 'QA': 'ar-QA', 'SY': 'ar-SY', 'TN': 'ar-TN',
            'YE': 'ar-YE', 'IL': 'he-IL', 'TR': 'tr-TR', 'IR': 'fa-IR',
            # South / Southeast Asia
            'TH': 'th-TH', 'VN': 'vi-VN', 'ID': 'id-ID', 'MM': 'my-MM',
            'KH': 'km-KH', 'LA': 'lo-LA', 'BD': 'bn-BD', 'PK': 'ur-PK',
            'LK': 'si-LK', 'NP': 'ne-NP',
            # East Asia
            'CN': 'zh-CN', 'HK': 'zh-HK', 'TW': 'zh-TW', 'JP': 'ja-JP',
            'KR': 'ko-KR', 'MN': 'mn-MN',
            # Africa
            'DZ': 'ar-DZ', 'ET': 'am-ET', 'TZ': 'sw-TZ', 'UG': 'sw-UG',
            # Americas (other)
            'HT': 'ht-HT', 'JM': 'en-JM', 'TT': 'en-TT',
        }
        country_code = str(country_code).upper()
        return country_to_language.get(country_code, 'en-US')
    
    def query_ip(self, ip_address):
        """
        Query IP geolocation with fallback providers
        
        Args:
            ip_address (str): IP to query
        
        Returns:
            dict: Complete geolocation data or None
        """
        print(f"[GeoQuery {self.profile_id}] 🌍 Querying geolocation for IP: {ip_address}")
        
        # Try primary provider
        result = self.query_ipapi_co(ip_address)
        if result:
            print(f"[GeoQuery {self.profile_id}] ✅ Geolocation: {result['country_name']} ({result['country_code']}) - {result['timezone']}")
            return result
        
        time.sleep(1)
        
        # Try fallback provider
        result = self.query_ipwhois_io(ip_address)
        if result:
            print(f"[GeoQuery {self.profile_id}] ✅ Geolocation (fallback): {result['country_name']} ({result['country_code']}) - {result['timezone']}")
            return result
        
        print(f"[GeoQuery {self.profile_id}] ❌ Could not query geolocation for {ip_address}")
        return None
    
    def extract_from_driver_result(self, driver_ip_info):
        """
        Extract geolocation from existing driver IP info
        If it has 'label' field with location, parse it
        
        Args:
            driver_ip_info (dict): IP info from driver whoer check
        
        Returns:
            dict: Geolocation data or None
        """
        if not driver_ip_info:
            return None
        
        ip = driver_ip_info.get('ip')
        if not ip:
            return None
        
        # Try to query for detailed info
        return self.query_ip(ip)