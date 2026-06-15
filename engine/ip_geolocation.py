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
        """Infer primary language from country code"""
        country_to_language = {
            'US': 'en-US',
            'CA': 'en-CA',
            'GB': 'en-GB',
            'AU': 'en-AU',
            'NZ': 'en-NZ',
            'DE': 'de-DE',
            'AT': 'de-AT',
            'CH': 'de-CH',
            'FR': 'fr-FR',
            'BE': 'fr-BE',
            'ES': 'es-ES',
            'MX': 'es-MX',
            'AR': 'es-AR',
            'IT': 'it-IT',
            'NL': 'nl-NL',
            'SE': 'sv-SE',
            'NO': 'nb-NO',
            'DK': 'da-DK',
            'PL': 'pl-PL',
            'RU': 'ru-RU',
            'JP': 'ja-JP',
            'KR': 'ko-KR',
            'CN': 'zh-CN',
            'HK': 'zh-HK',
            'SG': 'zh-SG',
            'TW': 'zh-TW',
            'IN': 'en-IN',
            'BR': 'pt-BR',
            'PT': 'pt-PT',
            'ZA': 'en-ZA',
            'AE': 'ar-AE',
            'IL': 'he-IL',
            'TH': 'th-TH',
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