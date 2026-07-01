"""
Web Agent — standalone browser analysis and control session.
Runs in its OWN thread, completely isolated from ghost profile threads.
Opens a dedicated clean Chrome session using the same Selenium + Comet
setup already configured in ghost_core, so no new browser dependencies.
"""

import os
import time
import threading
import subprocess
import sqlite3
import json
import random
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "web_agent.db")
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "data", "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def _init_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wa_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            url TEXT,
            action_type TEXT,
            selector TEXT,
            target_text TEXT,
            result TEXT,
            message TEXT,
            screenshot_before TEXT,
            screenshot_after TEXT,
            safety_level TEXT,
            approved INTEGER DEFAULT 0,
            error TEXT,
            ts TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wa_page_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            url TEXT,
            title TEXT,
            snapshot_json TEXT,
            screenshot TEXT,
            ts TEXT
        )
    """)
    conn.commit()
    conn.close()

_init_db()


class WebAgent:
    """
    Controls a dedicated browser for page analysis and safe action execution.
    One instance per agent session. All ghost profiles are unaffected.
    """

    def __init__(self, comet_path: str, driver_path: str, log_callback=None):
        self.comet_path = comet_path
        self.driver_path = driver_path
        self.log_callback = log_callback or (lambda msg: print(f"[WebAgent] {msg}"))

        self.driver = None
        self.proc = None
        self.session_id = datetime.now().strftime("wa_%Y%m%d_%H%M%S")
        self.debug_port = random.randint(9300, 9399)

        self._auto_mode = False
        self._pause_event = threading.Event()
        self._stop_event = threading.Event()
        self._pause_event.set()  # not paused by default

        self._current_page_data = {}
        self._last_suggestion = {}
        self._pending_approval = None  # action waiting for approval
        self._auto_thread = None

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------

    def start_browser(self) -> dict:
        """Open a dedicated clean Chrome session."""
        if self.driver:
            return {"ok": False, "error": "Browser already running"}
        try:
            profile_dir = os.path.join(BASE_DIR, "data", "web_agent_profile")
            os.makedirs(profile_dir, exist_ok=True)

            cmd = [
                self.comet_path,
                f"--remote-debugging-port={self.debug_port}",
                f"--user-data-dir={profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
                "--window-size=1280,800",
            ]
            self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(3)

            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service

            opts = Options()
            opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{self.debug_port}")
            svc = Service(executable_path=self.driver_path)
            self.driver = webdriver.Chrome(service=svc, options=opts)

            self._stop_event.clear()
            self.log_callback("Browser started")
            return {"ok": True, "port": self.debug_port}
        except Exception as e:
            self.log_callback(f"Start failed: {e}")
            return {"ok": False, "error": str(e)}

    def stop_browser(self) -> dict:
        """Close the agent browser. Does NOT affect ghost profiles."""
        self._stop_event.set()
        self._auto_mode = False
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass
        try:
            if self.proc:
                self.proc.terminate()
        except Exception:
            pass
        self.driver = None
        self.proc = None
        self.log_callback("Browser stopped")
        return {"ok": True}

    def emergency_stop(self) -> dict:
        """Immediately halt all automation."""
        self._stop_event.set()
        self._auto_mode = False
        self._pause_event.set()
        self.log_callback("EMERGENCY STOP triggered")
        return self.stop_browser()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def navigate(self, url: str) -> dict:
        if not self.driver:
            return {"ok": False, "error": "Browser not started"}
        try:
            if not url.startswith("http"):
                url = "https://" + url
            self.driver.get(url)
            time.sleep(2)
            self.log_callback(f"Navigated to {url}")
            return {"ok": True, "url": self.driver.current_url, "title": self.driver.title}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def analyze_page(self) -> dict:
        if not self.driver:
            return {"ok": False, "error": "Browser not started"}
        try:
            from engine.page_analyzer import PageAnalyzer
            analyzer = PageAnalyzer(self.driver, SCREENSHOTS_DIR)
            data = analyzer.analyze()
            self._current_page_data = data
            self._save_snapshot(data)
            self.log_callback(f"Page analyzed: {data.get('title', '')} | {len(data.get('buttons',[]))} buttons, {len(data.get('links',[]))} links, {len(data.get('inputs',[]))} inputs")
            return {"ok": True, "data": data}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def take_screenshot(self) -> dict:
        if not self.driver:
            return {"ok": False, "error": "Browser not started"}
        try:
            ts = int(time.time())
            fpath = os.path.join(SCREENSHOTS_DIR, f"wa_manual_{ts}.png")
            self.driver.save_screenshot(fpath)
            return {"ok": True, "path": fpath}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def run_ocr(self, image_path: str = "") -> dict:
        """Run PaddleOCR on the latest screenshot. Graceful fallback if not installed."""
        if not image_path:
            result = self.take_screenshot()
            if not result["ok"]:
                return result
            image_path = result["path"]
        try:
            from paddleocr import PaddleOCR
            ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
            lines = ocr.ocr(image_path, cls=True)
            text = "\n".join(w[1][0] for line in (lines or []) for w in (line or []) if w and len(w) > 1)
            return {"ok": True, "text": text, "image": image_path}
        except ImportError:
            return {"ok": False, "error": "PaddleOCR not installed. Run: pip install paddleocr"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Planning & Execution
    # ------------------------------------------------------------------

    def suggest_action(self, task: str = "", use_ai: bool = True, model: str = "") -> dict:
        if not self._current_page_data:
            result = self.analyze_page()
            if not result["ok"]:
                return result
        try:
            from engine.action_planner import plan
            suggestion = plan(self._current_page_data, task or "navigate the page", use_ai=use_ai, ai_model=model)
            self._last_suggestion = suggestion
            self.log_callback(
                f"Suggestion: {suggestion['action']} '{suggestion['target_text']}' "
                f"(confidence={suggestion['confidence']:.0%}, safety={suggestion['safety_level']})"
            )
            return {"ok": True, "suggestion": suggestion}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def execute_action(self, action: dict = None, approved: bool = False) -> dict:
        if not self.driver:
            return {"ok": False, "error": "Browser not started"}
        action = action or self._last_suggestion
        if not action:
            return {"ok": False, "error": "No action to execute. Call suggest_action first."}
        try:
            from engine.action_executor import execute
            result = execute(self.driver, action, approved=approved)
            self._log_action(action, result)
            if result["ok"]:
                self.log_callback(f"Executed: {result['message']}")
            else:
                self.log_callback(f"Execute failed: {result.get('error','')}")
            return {"ok": result["ok"], "result": result}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Auto mode
    # ------------------------------------------------------------------

    def start_auto_mode(self, task: str = "", interval: float = 5.0, model: str = "") -> dict:
        if self._auto_mode:
            return {"ok": False, "error": "Auto mode already running"}
        self._auto_mode = True
        self._stop_event.clear()
        self._pause_event.set()

        def _loop():
            self.log_callback("Auto mode started")
            while self._auto_mode and not self._stop_event.is_set():
                self._pause_event.wait()
                if self._stop_event.is_set():
                    break
                try:
                    self.analyze_page()
                    result = self.suggest_action(task, use_ai=True, model=model)
                    if not result["ok"]:
                        break
                    suggestion = result["suggestion"]
                    # Only auto-execute safe actions
                    if suggestion["safety_level"] == "safe" and not suggestion["requires_approval"]:
                        self.execute_action(suggestion, approved=False)
                    else:
                        self.log_callback(
                            f"Auto mode paused — action requires approval: "
                            f"{suggestion['action']} '{suggestion['target_text']}'"
                        )
                        self._pause_event.clear()
                        self._pending_approval = suggestion
                except Exception as e:
                    self.log_callback(f"Auto mode error: {e}")
                time.sleep(interval)
            self._auto_mode = False
            self.log_callback("Auto mode stopped")

        self._auto_thread = threading.Thread(target=_loop, daemon=True)
        self._auto_thread.start()
        return {"ok": True}

    def stop_auto_mode(self) -> dict:
        self._auto_mode = False
        self._pause_event.set()
        self._stop_event.set()
        return {"ok": True}

    def pause_auto_mode(self) -> dict:
        self._pause_event.clear()
        self.log_callback("Auto mode paused")
        return {"ok": True}

    def resume_auto_mode(self) -> dict:
        self._pending_approval = None
        self._pause_event.set()
        self.log_callback("Auto mode resumed")
        return {"ok": True}

    def approve_pending(self) -> dict:
        """Approve the pending action and resume auto mode."""
        if not self._pending_approval:
            return {"ok": False, "error": "No pending action"}
        result = self.execute_action(self._pending_approval, approved=True)
        self._pending_approval = None
        self._pause_event.set()
        return result

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        browser_alive = False
        current_url = ""
        current_title = ""
        try:
            if self.driver:
                current_url = self.driver.current_url
                current_title = self.driver.title
                browser_alive = True
        except Exception:
            pass

        return {
            "browser_running": browser_alive,
            "current_url": current_url,
            "current_title": current_title,
            "auto_mode": self._auto_mode,
            "paused": not self._pause_event.is_set(),
            "pending_approval": self._pending_approval,
            "session_id": self.session_id,
        }

    def get_logs(self, limit: int = 100) -> list:
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM wa_sessions ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def clear_logs(self) -> dict:
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            conn.execute("DELETE FROM wa_sessions")
            conn.execute("DELETE FROM wa_page_snapshots")
            conn.commit()
            conn.close()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def diagnostics(self) -> dict:
        checks = {}

        # Selenium
        try:
            import selenium
            checks["selenium"] = {"ok": True, "version": selenium.__version__}
        except ImportError:
            checks["selenium"] = {"ok": False, "error": "Not installed"}

        # PaddleOCR
        try:
            import paddleocr
            checks["paddleocr"] = {"ok": True}
        except ImportError:
            checks["paddleocr"] = {"ok": False, "error": "Not installed (optional)"}

        # Ollama
        try:
            from engine.ollama_client import is_available, list_models, best_model
            if is_available():
                models = list_models()
                checks["ollama"] = {"ok": True, "models": models, "best": best_model()}
            else:
                checks["ollama"] = {"ok": False, "error": "Not running at localhost:11434 (optional)"}
        except Exception as e:
            checks["ollama"] = {"ok": False, "error": str(e)}

        # Comet browser
        checks["comet_browser"] = {"ok": os.path.exists(self.comet_path), "path": self.comet_path}

        # ChromeDriver
        checks["chromedriver"] = {"ok": os.path.exists(self.driver_path), "path": self.driver_path}

        # Screenshots dir
        checks["screenshots_dir"] = {"ok": os.path.isdir(SCREENSHOTS_DIR), "path": SCREENSHOTS_DIR}

        # DB
        checks["database"] = {"ok": os.path.exists(DB_PATH), "path": DB_PATH}

        return checks

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _save_snapshot(self, data: dict):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            conn.execute(
                "INSERT INTO wa_page_snapshots (session_id, url, title, snapshot_json, screenshot, ts) VALUES (?,?,?,?,?,?)",
                (self.session_id, data.get("url",""), data.get("title",""),
                 json.dumps(data), data.get("screenshot",""), datetime.now().isoformat())
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _log_action(self, action: dict, result: dict):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            conn.execute("""
                INSERT INTO wa_sessions
                (session_id, url, action_type, selector, target_text, result,
                 message, screenshot_before, screenshot_after, safety_level,
                 approved, error, ts)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                self.session_id,
                self._current_page_data.get("url", ""),
                action.get("action", ""),
                action.get("selector", ""),
                action.get("target_text", ""),
                "ok" if result.get("ok") else "fail",
                result.get("message", ""),
                result.get("screenshot_before", ""),
                result.get("screenshot_after", ""),
                action.get("safety_level", ""),
                1 if result.get("ok") else 0,
                result.get("error", ""),
                datetime.now().isoformat(),
            ))
            conn.commit()
            conn.close()
        except Exception:
            pass
