"""
OPTION A: Browser-Only Anti-Detection
Pure JavaScript injection - no system-level changes
Safe for multi-profile automation
"""

import time


class BrowserAntiDetection:
    """Browser-level anti-detection via JavaScript injection"""
    
    def __init__(self, driver, profile_id):
        self.driver = driver
        self.profile_id = profile_id
        self.injected_scripts = []
    
    def inject_script(self, script_name, script_code):
        """
        Safely inject a JavaScript snippet
        
        Args:
            script_name (str): Name for logging
            script_code (str): JavaScript code to inject
        
        Returns:
            bool: Success status
        """
        try:
            self.driver.execute_script(script_code)
            self.injected_scripts.append(script_name)
            print(f"[BrowserAD {self.profile_id}] ✅ Injected: {script_name}")
            return True
        except Exception as e:
            print(f"[BrowserAD {self.profile_id}] ⚠️ Failed {script_name}: {e}")
            return False
    
    def hide_webdriver(self):
        """Hide navigator.webdriver to prevent automation detection"""
        script = """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => false,
        });
        """
        self.inject_script("hide_webdriver", script)
    
    def spoof_chrome_runtime(self):
        """Spoof chrome.runtime to look like real browser"""
        script = """
        Object.defineProperty(navigator, 'chrome', {
            get: () => ({
                runtime: {
                    onConnect: {
                        addListener: () => {}
                    },
                    id: 'chrome-runtime-id'
                }
            }),
        });
        """
        self.inject_script("spoof_chrome_runtime", script)
    
    def spoof_permissions(self):
        """Spoof Permissions API"""
        script = """
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        """
        self.inject_script("spoof_permissions", script)
    
    def randomize_canvas_fingerprint(self):
        """Add noise to canvas fingerprinting"""
        script = """
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type) {
            const canvas = this;
            const context = canvas.getContext('2d');
            
            // Add tiny random noise to prevent exact fingerprinting
            const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
            const data = imageData.data;
            
            for (let i = 0; i < data.length; i += 4) {
                data[i] = (data[i] + Math.floor(Math.random() * 3) - 1) & 255;
                data[i + 1] = (data[i + 1] + Math.floor(Math.random() * 3) - 1) & 255;
                data[i + 2] = (data[i + 2] + Math.floor(Math.random() * 3) - 1) & 255;
            }
            context.putImageData(imageData, 0, 0);
            return originalToDataURL.call(this, type);
        };
        """
        self.inject_script("randomize_canvas_fingerprint", script)
    
    def spoof_webgl_fingerprint(self):
        """Randomize WebGL parameters"""
        script = """
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel Iris OpenGL Engine';
            return getParameter.call(this, parameter);
        };
        
        const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel Iris OpenGL Engine';
            return getParameter2.call(this, parameter);
        };
        """
        self.inject_script("spoof_webgl_fingerprint", script)
    
    def spoof_plugins(self):
        """Spoof navigator.plugins"""
        script = """
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                { name: 'Chrome PDF Plugin', description: 'Portable Document Format' },
                { name: 'Chrome PDF Viewer', description: '' },
                { name: 'Native Client Executable', description: '' }
            ],
        });
        """
        self.inject_script("spoof_plugins", script)
    
    def spoof_languages(self, language='en-US'):
        """Spoof language settings"""
        script = f"""
        Object.defineProperty(navigator, 'language', {{
            get: () => '{language}',
        }});
        Object.defineProperty(navigator, 'languages', {{
            get: () => ['{language}', 'en'],
        }});
        """
        self.inject_script("spoof_languages", script)
    
    def disable_automation_features(self):
        """Disable features that reveal automation"""
        script = """
        // Disable headless detection
        window.chrome = { runtime: {} };
        
        // Spoof startup flags
        Object.defineProperty(navigator, 'vendor', {
            get: () => 'Google Inc.',
        });
        
        // Prevent detection via window properties
        delete window.webdriver;
        """
        self.inject_script("disable_automation_features", script)
    
    def inject_geolocation_spoof(self, latitude, longitude, accuracy=100):
        """
        Spoof browser geolocation
        
        Args:
            latitude (float): Fake latitude
            longitude (float): Fake longitude
            accuracy (float): Accuracy in meters
        """
        script = f"""
        const mockGeolocation = {{
            getCurrentPosition: function(success, error) {{
                success({{
                    coords: {{
                        latitude: {latitude},
                        longitude: {longitude},
                        accuracy: {accuracy}
                    }}
                }});
            }},
            watchPosition: function(success, error) {{
                success({{
                    coords: {{
                        latitude: {latitude},
                        longitude: {longitude},
                        accuracy: {accuracy}
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
        self.inject_script("inject_geolocation_spoof", script)
    
    def protect_against_detection_scripts(self):
        """Protect against detection by third-party scripts"""
        script = """
        // Override common detection methods
        window.navigator.toString = () => '[object Navigator]';
        window.document.documentElement.textContent = window.document.documentElement.textContent;
        
        // Spoof performance API
        if (window.performance) {
            const timings = window.performance.timing;
            timings.navigationStart = Date.now() - 60000;
            timings.loadEventEnd = Date.now();
        }
        """
        self.inject_script("protect_against_detection_scripts", script)
    
    def apply_all(self, language='en-US', latitude=40.7128, longitude=-74.0060):
        """
        Apply all anti-detection measures
        
        Args:
            language (str): Browser language to spoof
            latitude (float): Default latitude (New York)
            longitude (float): Default longitude (New York)
        """
        print(f"\n[BrowserAD {self.profile_id}] 🛡️ Applying browser-only anti-detection...")
        time.sleep(0.5)
        
        # Core stealth
        self.hide_webdriver()
        time.sleep(0.3)
        self.spoof_chrome_runtime()
        time.sleep(0.3)
        self.disable_automation_features()
        time.sleep(0.3)
        
        # Fingerprint protection
        self.randomize_canvas_fingerprint()
        time.sleep(0.3)
        self.spoof_webgl_fingerprint()
        time.sleep(0.3)
        
        # Navigator spoofing
        self.spoof_plugins()
        time.sleep(0.3)
        self.spoof_languages(language)
        time.sleep(0.3)
        
        # API spoofing
        self.spoof_permissions()
        time.sleep(0.3)
        self.inject_geolocation_spoof(latitude, longitude)
        time.sleep(0.3)
        
        # Detection protection
        self.protect_against_detection_scripts()
        time.sleep(0.3)
        
        print(f"[BrowserAD {self.profile_id}] ✅ All browser anti-detection injected ({len(self.injected_scripts)} scripts)")
        return True