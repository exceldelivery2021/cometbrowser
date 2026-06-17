"""
BaseRunner - Abstract base class for all platform runners
"""

import time


class BaseRunner:
    """Base class providing shared state and helpers for all platform runners."""

    def __init__(self, db=None, state_updater=None):
        self.db = db
        self.state_updater = state_updater
        self.driver = None
        self.profile_id = None
        self.session_id = None
        self.targets = []
        self.platform = "unknown"

    def run(self, driver, profile_id, session_id="", targets=None):
        """Override in subclass. Must return a result dict."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement run()")

    def update_state(self, status=None, ip_address=None, target_platform=None):
        if self.state_updater and self.profile_id is not None:
            try:
                self.state_updater(
                    self.profile_id,
                    status=status,
                    ip_address=ip_address,
                    target_platform=target_platform
                )
            except Exception:
                pass

    def safe_sleep(self, seconds):
        time.sleep(max(0, float(seconds)))

    def _ok(self, events=None):
        return {"ok": True, "platform": self.platform, "events": events or []}

    def _fail(self, error="", events=None):
        return {"ok": False, "platform": self.platform, "error": error, "events": events or []}
