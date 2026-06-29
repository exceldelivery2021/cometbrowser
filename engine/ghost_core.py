import time
import random
import threading
import subprocess
import os
import shutil
import traceback
import ctypes
import re
import json
import urllib.request
import urllib.parse
try:
    import psutil
except Exception:
    psutil = None
try:
    import win32con
    import win32gui
    import win32process
except Exception:
    win32con = None
    win32gui = None
    win32process = None
try:
    from pyvda import AppView, VirtualDesktop, get_virtual_desktops
except Exception:
    AppView = None
    VirtualDesktop = None
    get_virtual_desktops = None
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium_stealth import stealth
from engine.session_recorder import SessionRecorder
from engine.platform_runners import get_runner

class GhostCore:
    def __init__(self, db_manager, comet_path, driver_path, vpn_path=None, home_ip=None, state_callback=None, ip_blacklist_callback=None):
        self.db = db_manager
        self.comet_path = comet_path
        self.driver_path = driver_path
        self.vpn_path = vpn_path
        self.home_ip = str(home_ip).strip() if home_ip else None
        self.is_running = False
        self.active_threads = []
        self.active_sessions = {}
        self.launch_queue_enabled = True
        self.random_shutdown_active = False
        self.random_shutdown_thread = None
        self.state_callback = state_callback
        self.ip_blacklist_callback = ip_blacklist_callback
        self.browser_layout_lock = threading.Lock()
        self.browser_layout_slots = {}
        self.browser_layout_used_slots = set()
        self.virtual_desktop_lock = threading.Lock()

        # Central audit trail for every profile run.
        self.session_recorder = SessionRecorder(self.db)

        print("[GhostCore] Initialized")
        print(f"[GhostCore] Comet path: {self.comet_path}")
        print(f"[GhostCore] ChromeDriver path: {self.driver_path}")
        print(f"[GhostCore] Proton extension path: {self.vpn_path}")
        print(f"[GhostCore] OPSEC Home IP Guard: ACTIVE ({self.home_ip})")

        if not os.path.exists(self.comet_path):
            print(f"[GhostCore] ❌ COMET_PATH does not exist: {self.comet_path}")

        if not os.path.exists(self.driver_path):
            print(f"[GhostCore] ❌ CHROMEDRIVER_PATH does not exist: {self.driver_path}")

        if self.vpn_path:
            manifest_path = os.path.join(self.vpn_path, "manifest.json")
            if not os.path.exists(manifest_path):
                print(f"[GhostCore] ❌ PROTON_VPN_PATH is invalid. Missing manifest.json: {manifest_path}")
            else:
                print(f"[GhostCore] ✅ Proton VPN extension manifest found: {manifest_path}")

    def _get_primary_work_area(self):
        """Return the usable primary monitor area, excluding the taskbar when Windows reports it."""
        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        rect = RECT()
        try:
            ok = ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
            if ok:
                width = max(1, int(rect.right - rect.left))
                height = max(1, int(rect.bottom - rect.top))
                return int(rect.left), int(rect.top), width, height
        except Exception:
            pass

        try:
            width = int(ctypes.windll.user32.GetSystemMetrics(0))
            height = int(ctypes.windll.user32.GetSystemMetrics(1))
            return 0, 0, max(1, width), max(1, height)
        except Exception:
            return 0, 0, 1920, 1080

    def _calculate_browser_tile(self, slot_index):
        """
        Desktop layout rule:
        - 10 browser windows per virtual desktop
        - 5 columns on the top row
        - 5 columns on the bottom row
        """
        left, top, work_width, work_height = self._get_primary_work_area()
        columns = 5
        rows = 2
        slot_index = int(slot_index) % (columns * rows)
        col = slot_index % columns
        row = slot_index // columns

        # Keep the right and bottom edges aligned even when the screen size does not divide evenly.
        x = left + (work_width * col // columns)
        y = top + (work_height * row // rows)
        next_x = left + (work_width * (col + 1) // columns)
        next_y = top + (work_height * (row + 1) // rows)
        width = max(100, next_x - x)
        height = max(100, next_y - y)

        return {
            "x": int(x),
            "y": int(y),
            "width": int(width),
            "height": int(height),
        }

    def _allocate_browser_layout(self, profile_id):
        """
        Reserve the next available tile.
        Browser desktops start at Windows virtual desktop #2 so the dashboard remains on desktop #1.
        """
        profile_id = int(profile_id)
        with self.browser_layout_lock:
            existing_slot = self.browser_layout_slots.get(profile_id)
            if existing_slot is not None:
                global_slot = int(existing_slot)
            else:
                global_slot = 0
                while global_slot in self.browser_layout_used_slots:
                    global_slot += 1
                self.browser_layout_used_slots.add(global_slot)
                self.browser_layout_slots[profile_id] = global_slot

        desktop_number = 2 + (global_slot // 10)
        slot_index = global_slot % 10
        tile = self._calculate_browser_tile(slot_index)
        tile.update({
            "desktop_number": int(desktop_number),
            "slot_index": int(slot_index),
            "global_slot": int(global_slot),
        })
        return tile

    def _release_browser_layout(self, profile_id):
        try:
            profile_id = int(profile_id)
        except Exception:
            return

        with self.browser_layout_lock:
            global_slot = self.browser_layout_slots.pop(profile_id, None)
            if global_slot is not None:
                self.browser_layout_used_slots.discard(global_slot)

    def _reset_browser_layouts(self):
        with self.browser_layout_lock:
            self.browser_layout_slots.clear()
            self.browser_layout_used_slots.clear()

    def _browser_window_args(self, layout):
        return [
            f"--window-position={layout['x']},{layout['y']}",
            f"--window-size={layout['width']},{layout['height']}",
        ]

    def _collect_process_tree_pids(self, root_pid):
        pids = {int(root_pid)}
        if psutil is None:
            return pids

        try:
            root = psutil.Process(int(root_pid))
            for child in root.children(recursive=True):
                pids.add(int(child.pid))
        except Exception:
            pass

        return pids

    def _collect_browser_identity_pids(self, proc=None, debug_port=None, profile_dir=None):
        pids = set()

        if proc is not None:
            try:
                pids.update(self._collect_process_tree_pids(proc.pid))
            except Exception:
                pass

        if psutil is None:
            return pids

        debug_token = f"--remote-debugging-port={int(debug_port)}" if debug_port else ""
        profile_token = ""
        if profile_dir:
            try:
                profile_token = os.path.normcase(os.path.normpath(str(profile_dir))).replace("\\", "/").lower()
            except Exception:
                profile_token = str(profile_dir).replace("\\", "/").lower()

        if not debug_token and not profile_token:
            return pids

        try:
            for item in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    name = str(item.info.get("name") or "").lower()
                    if "comet" not in name and "chrome" not in name:
                        continue

                    cmdline = item.info.get("cmdline") or []
                    raw_cmd = " ".join(str(part) for part in cmdline)
                    norm_cmd = raw_cmd.replace("\\", "/").lower()

                    if debug_token and debug_token.lower() in norm_cmd:
                        pids.add(int(item.info["pid"]))
                        continue

                    if profile_token and profile_token in norm_cmd:
                        pids.add(int(item.info["pid"]))
                except Exception:
                    continue
        except Exception as e:
            print(f"[WindowLayout] Process identity scan failed: {e}")

        return pids

    def _is_profile_browser_alive(self, proc=None, debug_port=None, profile_dir=None):
        if proc is not None:
            try:
                if proc.poll() is None:
                    return True
            except Exception:
                pass

        pids = self._collect_browser_identity_pids(
            proc=proc,
            debug_port=debug_port,
            profile_dir=profile_dir,
        )

        if psutil is None:
            return False

        for pid in pids:
            try:
                process = psutil.Process(int(pid))
                if process.is_running():
                    return True
            except Exception:
                continue

        return False

    def _find_browser_hwnds_for_process(self, proc, timeout=8.0, debug_port=None, profile_dir=None):
        if proc is None or win32gui is None or win32process is None:
            return []

        deadline = time.time() + float(timeout)
        best = []

        while time.time() < deadline:
            pids = self._collect_browser_identity_pids(
                proc=proc,
                debug_port=debug_port,
                profile_dir=profile_dir,
            )
            found = []

            def enum_callback(hwnd, _):
                try:
                    if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
                        return

                    _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
                    if int(window_pid) not in pids:
                        return

                    class_name = win32gui.GetClassName(hwnd) or ""
                    title = win32gui.GetWindowText(hwnd) or ""
                    if not title and "Chrome_WidgetWin" not in class_name:
                        return

                    score = 0
                    if class_name == "Chrome_WidgetWin_1":
                        score += 100
                    elif "Chrome_WidgetWin" in class_name:
                        score += 50
                    if title:
                        score += 10

                    found.append((score, hwnd, title, class_name))
                except Exception:
                    return

            try:
                win32gui.EnumWindows(enum_callback, None)
            except Exception:
                return []

            if found:
                found.sort(reverse=True)
                best = [item[1] for item in found]
                break

            time.sleep(0.25)

        return best

    def _get_or_create_virtual_desktop(self, desktop_number):
        if AppView is None or VirtualDesktop is None or get_virtual_desktops is None:
            return None

        with self.virtual_desktop_lock:
            try:
                desktops = list(get_virtual_desktops())
                while len(desktops) < int(desktop_number):
                    VirtualDesktop.create()
                    time.sleep(0.35)
                    desktops = list(get_virtual_desktops())
                return desktops[int(desktop_number) - 1]
            except Exception as e:
                print(f"[WindowLayout] Virtual desktop unavailable: {e}")
                return None

    def _move_window_to_virtual_desktop(self, hwnd, desktop_number):
        desktop = self._get_or_create_virtual_desktop(desktop_number)
        if desktop is None:
            return False

        try:
            AppView(hwnd=hwnd).move(desktop)
            return True
        except Exception as e:
            print(f"[WindowLayout] Could not move window {hwnd} to desktop {desktop_number}: {e}")
            return False

    def _apply_browser_window_layout(self, profile_id, proc, layout, debug_port=None, profile_dir=None, quiet=False):
        hwnds = self._find_browser_hwnds_for_process(
            proc,
            timeout=1.0,
            debug_port=debug_port,
            profile_dir=profile_dir,
        )
        if not hwnds:
            if not quiet:
                print(f"[Ghost {profile_id}] Window layout warning: browser window handle was not found.")
            return False

        moved_to_desktop = False
        for hwnd in hwnds:
            try:
                if win32gui is not None and win32con is not None:
                    win32gui.ShowWindow(hwnd, win32con.SW_SHOWNORMAL)
                    win32gui.SetWindowPos(
                        hwnd,
                        None,
                        int(layout["x"]),
                        int(layout["y"]),
                        int(layout["width"]),
                        int(layout["height"]),
                        win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE,
                    )
            except Exception as e:
                print(f"[Ghost {profile_id}] Window layout resize failed for {hwnd}: {e}")

            if self._move_window_to_virtual_desktop(hwnd, layout["desktop_number"]):
                moved_to_desktop = True

        if moved_to_desktop:
            print(
                f"[Ghost {profile_id}] Window moved to virtual desktop {layout['desktop_number']} "
                f"slot {layout['slot_index'] + 1}/10 "
                f"({layout['width']}x{layout['height']} at {layout['x']},{layout['y']})."
            )
        else:
            print(
                f"[Ghost {profile_id}] Window tiled on current desktop slot {layout['slot_index'] + 1}/10. "
                "Install/check pyvda on this PC for virtual desktop moves."
            )

        return True

    def _schedule_browser_window_layout(self, profile_id, proc, layout, debug_port=None, profile_dir=None):
        """
        Comet sometimes creates the real browser window after the launcher process returns.
        Keep retrying briefly so the window is moved once the final top-level window exists.
        """
        def worker():
            for attempt in range(1, 31):
                moved = self._apply_browser_window_layout(
                    profile_id,
                    proc,
                    layout,
                    debug_port=debug_port,
                    profile_dir=profile_dir,
                    quiet=attempt < 30,
                )
                if moved:
                    return
                time.sleep(1)

        t = threading.Thread(
            target=worker,
            name=f"BrowserLayout-{profile_id}",
            daemon=True,
        )
        t.start()
    
    def _update_profile_state(self, profile_id, status=None, ip_address=None, target_platform=None):
        """
        Single safe state update path.
        Updates local DB, then sends live status/IP to the dashboard/coordinator callback.
        """
        try:
            self.db.update_profile_state(
                profile_id,
                status=status,
                ip_address=ip_address,
                target_platform=target_platform
            )
        except Exception as e:
            print(f"[GhostCore] Local DB state update failed for Profile {profile_id}: {e}")

        callback = getattr(self, "state_callback", None)

        if callback:
            try:
                callback(
                    int(profile_id),
                    status=status,
                    ip_address=ip_address,
                    target_platform=target_platform
                )
            except Exception as e:
                print(f"[GhostCore] State callback failed for Profile {profile_id}: {e}")

    def _record_profile_alignment(self, pid, session_id, driver, ip_info, cloak, platform="Pending"):
        """Records a read-only profile/IP/browser alignment report."""
        try:
            from engine.anti_detection import AntiDetection
            from engine.profile_alignment import ProfileAligner

            identity_checker = AntiDetection(driver, pid)
            identity_report = identity_checker.apply_all_protections(
                ip_info=ip_info,
                timezone_str=None,
                cloak=cloak
            )
            browser_identity = identity_report.get("browser", {}) if isinstance(identity_report, dict) else {}

            aligner = ProfileAligner(self.db)
            alignment_report = aligner.align_profile(
                pid,
                ip_info,
                cloak=cloak,
                browser_identity=browser_identity
            )

            report = {
                "identity_ok": bool(identity_report.get("ok")) if isinstance(identity_report, dict) else False,
                "identity_mismatches": identity_report.get("mismatches", []) if isinstance(identity_report, dict) else [],
                "alignment_ok": bool(alignment_report.get("ok")) if isinstance(alignment_report, dict) else False,
                "alignment_warnings": alignment_report.get("warnings", []) if isinstance(alignment_report, dict) else [],
                "country": alignment_report.get("country", "") if isinstance(alignment_report, dict) else "",
                "expected_timezone": alignment_report.get("expected_timezone", "") if isinstance(alignment_report, dict) else "",
                "expected_locale": alignment_report.get("expected_locale", "") if isinstance(alignment_report, dict) else "",
                "actions_taken": alignment_report.get("actions_taken", {}) if isinstance(alignment_report, dict) else {},
            }

            if pid in self.active_sessions:
                self.active_sessions[pid]["alignment_report"] = report

            self.session_recorder.event(
                profile_id=pid,
                session_id=session_id,
                platform=platform,
                ip_label=(ip_info or {}).get("label", "") if isinstance(ip_info, dict) else "",
                ip_status="VERIFIED" if ip_info else "UNKNOWN",
                event_type="PROFILE_ALIGNMENT_CHECK",
                details=report
            )

            status = "OK" if report["identity_ok"] and report["alignment_ok"] else "WARN"
            print(f"[Ghost {pid}] Profile alignment check: {status} | timezone={report['expected_timezone']} | locale={report['expected_locale']}")
            return report

        except Exception as e:
            print(f"[Ghost {pid}] Profile alignment check failed: {e}")
            return {
                "identity_ok": False,
                "alignment_ok": False,
                "error": str(e)
            }

    def _run_platform_runner(self, driver, pid, target, session_id=""):
        """
        Runs the correct independent platform module with FULL DEBUG LOGGING
        """
        platform = str(target or "").strip().lower()
        print(f"[Ghost {pid}] 🔍 DEBUG: _run_platform_runner called with platform='{platform}'")
    
        runner = get_runner(
            platform,
            db=self.db,
            state_updater=self._update_profile_state
        )
    
        if runner is None:
            print(f"[Ghost {pid}] ❌ CRITICAL: No platform runner found for target={platform}")
            fallback_urls = {
                "youtube": "https://www.youtube.com",
                "twitch": "https://www.twitch.tv",
                "spotify": "https://open.spotify.com",
                "deezer": "https://www.deezer.com",
            }
            driver.get(fallback_urls.get(platform, "https://www.google.com"))
            return {
                "ok": False,
                "platform": platform,
                "error": "No runner found",
                "events": ["NO_RUNNER_FOUND"]
            }
    
        print(f"[Ghost {pid}] ✅ Runner found: {runner.__class__.__name__}")
    
        # Get targets
        targets = []
        try:
            # Try the database method
            if hasattr(self.db, "get_enabled_platform_targets"):
                print(f"[Ghost {pid}] 🔍 DEBUG: Calling db.get_enabled_platform_targets('{platform}')")
                targets = self.db.get_enabled_platform_targets(platform=platform)
                print(f"[Ghost {pid}] 🔍 DEBUG: Database returned {len(targets)} targets: {targets}")
            else:
                print(f"[Ghost {pid}] ⚠️ WARNING: db.get_enabled_platform_targets() doesn't exist!")
                targets = []
        except Exception as e:
            print(f"[Ghost {pid}] ❌ ERROR loading targets: {e}")
            print(f"[Ghost {pid}] 📋 TRACEBACK: {traceback.format_exc()}")
            targets = []
    
        print(f"[Ghost {pid}] 🚀 RUNNING: {platform.upper()} automation with {len(targets)} targets")
    
        try:
            result = runner.run(
                driver=driver,
                profile_id=pid,
                session_id=session_id,
                targets=targets
            )
            print(f"[Ghost {pid}] ✅ Runner completed: {result}")
            return result
        except Exception as e:
            print(f"[Ghost {pid}] ❌ RUNNER CRASHED: {e}")
            print(f"[Ghost {pid}] 📋 TRACEBACK:\n{traceback.format_exc()}")
            return {
                "ok": False,
                "platform": platform,
                "error": str(e),
                "events": ["RUNNER_EXCEPTION"]
            }
        
    def _attach_to_debugger(self, debug_port, retries=8, delay=1.5):
        """
        Attach Selenium to an already-running Comet/Chromium instance with retry.

        Uses the explicit CHROMEDRIVER_PATH from config to avoid Selenium Manager
        auto-selecting an incompatible ChromeDriver version.
        """
        from selenium.webdriver.chrome.service import Service

        last_error = None

        for attempt in range(1, retries + 1):
            try:
                opts = Options()
                opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{debug_port}")

                if self.driver_path and os.path.exists(self.driver_path):
                    service = Service(executable_path=self.driver_path)
                    driver = webdriver.Chrome(service=service, options=opts)
                else:
                    driver = webdriver.Chrome(options=opts)

                print(f"[GhostCore] ✅ Selenium attached on port {debug_port} after attempt {attempt}/{retries}")
                return driver

            except Exception as e:
                last_error = e
                print(f"[GhostCore] Attachment retry {attempt}/{retries} on port {debug_port} failed: {e}")
                time.sleep(delay)

        print(f"[GhostCore] ❌ Critical failure attaching Selenium on port {debug_port}: {last_error}")
        return None

    def _format_ip_info(self, data):
        """Convert IP lookup JSON into a dashboard-friendly live session label."""
        if not isinstance(data, dict):
            return None

        ip = str(data.get("ip") or "").strip()
        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
            return None

        city = str(data.get("city") or "").strip()
        region = str(data.get("region") or data.get("region_name") or data.get("regionName") or "").strip()
        country = str(data.get("country_name") or data.get("countryName") or data.get("country") or "").strip()

        connection = data.get("connection") if isinstance(data.get("connection"), dict) else {}
        org = str(
            data.get("org")
            or data.get("asn")
            or data.get("isp")
            or connection.get("isp")
            or connection.get("org")
            or ""
        ).strip()

        location_parts = [part for part in [city, region, country] if part]
        location = ", ".join(location_parts)

        if location and org:
            return f"{ip} | {location} | {org}"
        if location:
            return f"{ip} | {location}"
        return ip

    def _read_live_ip_info_from_browser(self, driver):
        """
        ONE-TIME browser IP read.

        Resource rule:
        - Do not open new tabs.
        - Do not navigate away from the current tab.
        - Use in-page fetch only.

        Returns:
            {"ip": "x.x.x.x", "label": "x.x.x.x | City, Region, Country | ISP", "raw": {...}}
            or None if no usable IP is found.
        """
        try:
            result = driver.execute_async_script("""
                const done = arguments[0];

                const timeout = (ms) => new Promise(resolve => setTimeout(() => resolve(null), ms));

                function normalizeIpwho(data) {
                    if (!data || data.success === false || !data.ip) return null;
                    return {
                        ip: data.ip,
                        city: data.city || "",
                        region: data.region || "",
                        country_name: data.country || "",
                        country_code: data.country_code || "",
                        timezone: data.timezone && data.timezone.id ? data.timezone.id : "",
                        org: data.connection && (data.connection.isp || data.connection.org) ? (data.connection.isp || data.connection.org) : ""
                    };
                }

                function normalizeFreeIpApi(data) {
                    if (!data || !data.ipAddress) return null;
                    return {
                        ip: data.ipAddress,
                        city: data.cityName || "",
                        region: data.regionName || "",
                        country_name: data.countryName || "",
                        country_code: data.countryCode || "",
                        timezone: data.timeZone || "",
                        org: data.asnOrganization || ""
                    };
                }

                async function fetchJson(url, ms) {
                    try {
                        const controller = new AbortController();
                        const timer = setTimeout(() => controller.abort(), ms);
                        const response = await fetch(url, {
                            cache: 'no-store',
                            signal: controller.signal
                        });
                        clearTimeout(timer);
                        if (!response.ok) return null;
                        return await response.json();
                    } catch (e) {
                        return null;
                    }
                }

                (async () => {
                    // Primary: full IP + city/region/country/org details.
                    let data = await fetchJson('https://ipapi.co/json/', 12000);
                    if (data && data.ip) {
                        done(data);
                        return;
                    }

                    data = normalizeIpwho(await fetchJson('https://ipwho.is/', 10000));
                    if (data && data.ip) {
                        done(data);
                        return;
                    }

                    data = normalizeFreeIpApi(await fetchJson('https://freeipapi.com/api/json/', 10000));
                    if (data && data.ip) {
                        done(data);
                        return;
                    }

                    // Fallback: IP only, still no tab opened.
                    data = await fetchJson('https://api.ipify.org?format=json', 8000);
                    if (data && data.ip) {
                        done(data);
                        return;
                    }

                    done(null);
                })();
            """)

            label = self._format_ip_info(result)
            if label:
                return {
                    "ip": str(result.get("ip")).strip(),
                    "label": label,
                    "raw": result
                }

        except Exception as e:
            print(f"[GhostCore] One-time browser IP lookup failed: {e}")

        return None


    def _resolve_live_ip_with_retries(self, pid, driver, retries=6, first_delay=5, delay=3):
        print(f"[Ghost {pid}] 🌍 Waiting {first_delay}s before first live IP check...")
        time.sleep(first_delay)

        for attempt in range(1, retries + 1):
            try:
                print(f"[Ghost {pid}] 🌍 Live IP check attempt {attempt}/{retries}...")
                ip_info = self._read_live_ip_info_from_browser(driver)

                if ip_info and ip_info.get("label"):
                    print(f"[Ghost {pid}] ✅ Live IP resolved: {ip_info['label']}")
                    return ip_info

            except Exception as e:
                print(f"[Ghost {pid}] ⚠️ Live IP check attempt {attempt}/{retries} failed: {e}")

            time.sleep(delay)

        print(f"[Ghost {pid}] ❌ Failed to resolve live IP after {retries} attempts.")
        return None

    def _is_ip_blacklisted(self, ip_info):
        """Checks local DB plus optional coordinator callback for persistent IP blacklist."""
        if not ip_info:
            return False, ""

        ip_label = str(ip_info.get("label") or ip_info.get("ip") or "").strip()
        ip_address = str(ip_info.get("ip") or "").strip()
        lookup_value = ip_label or ip_address

        try:
            if hasattr(self.db, "is_ip_blacklisted") and self.db.is_ip_blacklisted(lookup_value):
                return True, "Local blacklist"
        except Exception as e:
            print(f"[GhostCore] Local blacklist check failed for {lookup_value}: {e}")

        callback = getattr(self, "ip_blacklist_callback", None)
        if callback:
            try:
                result = callback(lookup_value)
                if isinstance(result, dict):
                    if result.get("blacklisted"):
                        return True, result.get("reason") or result.get("source") or "Coordinator blacklist"
                elif bool(result):
                    return True, "Coordinator blacklist"
            except Exception as e:
                print(f"[GhostCore] Coordinator blacklist check failed for {lookup_value}: {e}")

        return False, ""

    def _extract_ip_only(self, value):
        match = re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", str(value or ""))
        return match.group(0) if match else ""

    def _is_duplicate_active_ip(self, profile_id, ip_info):
        ip_address = self._extract_ip_only((ip_info or {}).get("ip") or (ip_info or {}).get("label"))
        if not ip_address:
            return False, ""

        try:
            profiles = self.db.get_all_profiles() if hasattr(self.db, "get_all_profiles") else []
        except Exception as e:
            print(f"[GhostCore] Duplicate IP check failed while loading profiles: {e}")
            return False, ""

        for profile in profiles or []:
            try:
                other_id = int(profile.get("id"))
            except Exception:
                continue

            if other_id == int(profile_id):
                continue

            status = str(profile.get("status") or "").upper()
            if status not in {"RUNNING", "STARTING"}:
                continue

            other_ip = self._extract_ip_only(
                profile.get("last_ip")
                or profile.get("ip_origin")
                or profile.get("ip")
                or ""
            )
            if other_ip and other_ip == ip_address:
                return True, f"Duplicate active IP with Profile {other_id}: {ip_address}"

        return False, ""

    def _shutdown_for_duplicate_ip(self, pid, driver, proc, ip_info, reason):
        ip_label = str((ip_info or {}).get("label") or (ip_info or {}).get("ip") or "").strip()
        print(f"[Ghost {pid}] 🛑 DUPLICATE IP DETECTED. Closing profile: {ip_label} | {reason}")

        session = self.active_sessions.get(pid, {}) if hasattr(self, "active_sessions") else {}
        session["closed_by_duplicate_ip"] = True
        session["duplicate_ip_label"] = ip_label
        session["duplicate_ip_reason"] = reason
        if hasattr(self, "active_sessions"):
            self.active_sessions[pid] = session

        try:
            if hasattr(self.db, "record_analytics_event"):
                self.db.record_analytics_event(
                    profile_id=pid,
                    platform="Duplicate IP",
                    ip_label=ip_label,
                    ip_status="DUPLICATE",
                    event_type="DUPLICATE_IP_BLOCKED",
                    details=reason
                )
        except Exception as e:
            print(f"[Ghost {pid}] Analytics duplicate IP event failed: {e}")

        self._update_profile_state(
            pid,
            status="OFFLINE",
            ip_address=ip_label,
            target_platform="Duplicate IP"
        )

        try:
            if driver:
                driver.quit()
        except Exception:
            pass

        try:
            if proc:
                proc.terminate()
        except Exception:
            pass

    def _shutdown_for_blacklisted_ip(self, pid, driver, proc, ip_info, target_platform="IP Blacklisted", reason="Blacklisted IP"):
        """Marks profile as blacklisted, records analytics, and closes the browser immediately."""
        ip_label = str((ip_info or {}).get("label") or (ip_info or {}).get("ip") or "").strip()
        print(f"[Ghost {pid}] 🛑 BLACKLISTED IP DETECTED. Closing profile immediately: {ip_label} | reason={reason}")

        session = self.active_sessions.get(pid, {}) if hasattr(self, "active_sessions") else {}
        session["closed_by_blacklist"] = True
        session["blacklisted_ip_label"] = ip_label
        session["blacklist_reason"] = reason
        if hasattr(self, "active_sessions"):
            self.active_sessions[pid] = session

        try:
            if hasattr(self.db, "record_analytics_event"):
                self.db.record_analytics_event(
                    profile_id=pid,
                    platform=target_platform,
                    ip_label=ip_label,
                    ip_status="BLACKLISTED",
                    event_type="IP_BLACKLISTED_BLOCKED",
                    details=f"Profile closed immediately because IP is blacklisted. Reason: {reason}"
                )
        except Exception as e:
            print(f"[Ghost {pid}] Analytics blacklist event failed: {e}")

        self._update_profile_state(
            pid,
            status="BLACKLISTED",
            ip_address=ip_label,
            target_platform=target_platform
        )

        try:
            if driver:
                driver.quit()
        except Exception:
            pass

        try:
            if proc:
                proc.terminate()
        except Exception:
            pass

    def _start_live_ip_tracker(self, pid, driver, first_delay=5, interval=30):
        """
        Disabled by design.

        IP verification must happen only once per browser launch.
        Do not start a background IP tracker and do not refresh IP every 30 seconds.
        """
        print(f"[Ghost {pid}] 🌍 Live IP tracker disabled. IP verification is one-time only.")
        return None

    def _press_escape_key(self):
        """Presses ESC at the Windows OS level to cancel native dialogs."""
        try:
            VK_ESCAPE = 0x1B
            KEYEVENTF_KEYUP = 0x0002
            ctypes.windll.user32.keybd_event(VK_ESCAPE, 0, 0, 0)
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)
            return True
        except Exception as e:
            return False

    def _cancel_proxy_signin_popup(self, pid, driver=None, burst_seconds=2.0, interval=0.35):
        """Bursts the ESC key to kill Windows-level popups."""
        cancelled = False
        end_time = time.time() + burst_seconds
        while time.time() < end_time:
            if self._press_escape_key():
                cancelled = True
            time.sleep(interval)
        if cancelled:
            print(f"[Ghost {pid}] ❌ Proxy sign-in popup cancel command sent via OS.")
        return cancelled

    def _start_proxy_cancel_watcher(self, pid, duration=8.0, interval=0.50):
        """Spawns a background thread to press ESC while Selenium is frozen."""
        def watcher():
            end_time = time.time() + duration
            while time.time() < end_time:
                self._press_escape_key()
                time.sleep(interval)
        t = threading.Thread(target=watcher, daemon=True)
        t.start()
        return t
    
    def _prepare_profile_for_clean_boot(self, pid, profile_dir):
        """
        Removes crash/restore state before Comet launches.
        This prevents the top-right 'Restore pages?' bubble without deleting cookies,
        extension storage, or ProtonVPN login state.
        """
        print(f"[Ghost {pid}] 🧼 Preparing clean browser boot...")

        paths_to_remove = []

        for base in [profile_dir, os.path.join(profile_dir, "Default")]:
            paths_to_remove.extend([
                os.path.join(base, "Sessions"),
                os.path.join(base, "Current Session"),
                os.path.join(base, "Current Tabs"),
                os.path.join(base, "Last Session"),
                os.path.join(base, "Last Tabs"),
            ])

        for path in paths_to_remove:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                    print(f"[Ghost {pid}] 🧼 Removed restore folder: {path}")
                elif os.path.isfile(path):
                    os.remove(path)
                    print(f"[Ghost {pid}] 🧼 Removed restore file: {path}")
            except Exception as e:
                print(f"[Ghost {pid}] ⚠️ Could not remove restore path {path}: {e}")

        for pref_path in [
            os.path.join(profile_dir, "Preferences"),
            os.path.join(profile_dir, "Default", "Preferences"),
        ]:
            if not os.path.exists(pref_path):
                continue

            try:
                with open(pref_path, "r", encoding="utf-8") as f:
                    prefs = json.load(f)

                prefs.setdefault("profile", {})
                prefs["profile"]["exit_type"] = "Normal"
                prefs["profile"]["exited_cleanly"] = True

                prefs.setdefault("session", {})
                prefs["session"]["restore_on_startup"] = 0

                with open(pref_path, "w", encoding="utf-8") as f:
                    json.dump(prefs, f)

                print(f"[Ghost {pid}] ✅ Preferences marked as clean exit: {pref_path}")

            except Exception as e:
                print(f"[Ghost {pid}] ⚠️ Could not update Preferences file {pref_path}: {e}")

    def _open_clean_working_tab(self, pid, driver):
        """
        Opens a fresh tab and uses it as the only automation tab.
        Does not close restored/extension tabs yet.
        """
        try:
            driver.switch_to.new_window("tab")
            driver.get("about:blank")
            print(f"[Ghost {pid}] ✅ Clean working tab opened.")
            return driver.current_window_handle
        except Exception as e:
            print(f"[Ghost {pid}] ⚠️ Could not open clean working tab: {e}")

        try:
            handles = driver.window_handles
            if handles:
                driver.switch_to.window(handles[-1])
                driver.get("about:blank")
                print(f"[Ghost {pid}] ✅ Reused existing tab as working tab.")
                return driver.current_window_handle
        except Exception as e:
            print(f"[Ghost {pid}] ❌ Could not reuse existing tab: {e}")

        return None

    def _purge_other_tabs_after_target_loaded(self, pid, driver, keep_handle):
        """
        Closes every tab except the final target tab.
        Runs multiple passes because ProtonVPN can open its tab late.
        """
        print(f"[Ghost {pid}] 🧹 Initiating final multi-pass tab purge...")

        for pass_num in range(1, 6):
            try:
                time.sleep(2)
                handles = driver.window_handles

                # Rescue the keep_handle if we lost it
                if keep_handle not in handles:
                    try:
                        keep_handle = driver.current_window_handle
                    except Exception:
                        if handles:
                            keep_handle = handles[-1]
                        else:
                            print(f"[Ghost {pid}] ⚠️ No tabs available during purge.")
                            return

                extra_tabs = [h for h in handles if h != keep_handle]

                if not extra_tabs:
                    print(f"[Ghost {pid}] ✅ Single-tab session confirmed on purge pass {pass_num}.")
                    try:
                        driver.switch_to.window(keep_handle)
                    except: pass
                    return

                print(f"[Ghost {pid}] 🧹 Purge pass {pass_num}: closing {len(extra_tabs)} extra tab(s).")

                for h in extra_tabs:
                    try:
                        # Switch to the rogue tab
                        driver.switch_to.window(h)
                        time.sleep(0.2)

                        # Grab info for logging safely
                        tab_url = driver.current_url or "unknown"
                        tab_title = driver.title or "unknown"
                        print(f"[Ghost {pid}] 🧹 Executing tab via JS: title='{tab_title[:60]}' url='{tab_url[:100]}'")

                        # 1. Neutralize any hidden "Are you sure you want to leave?" alerts
                        driver.execute_script("window.onbeforeunload = null;")
                        
                        # 2. Instantly execute the tab via JS instead of Selenium
                        driver.execute_script("window.close();")
                        
                        time.sleep(0.3)
                    except Exception as e:
                        pass # Tab is already dead or unreachable, just move on

                # Refocus the main YouTube/Twitch tab
                try:
                    remaining = driver.window_handles
                    if keep_handle in remaining:
                        driver.switch_to.window(keep_handle)
                    elif remaining:
                        keep_handle = remaining[-1]
                        driver.switch_to.window(keep_handle)
                except Exception as e:
                    print(f"[Ghost {pid}] ⚠️ Could not refocus main tab: {e}")

            except Exception as e:
                print(f"[Ghost {pid}] ⚠️ Final tab purge pass {pass_num} failed: {e}")

        # Final Status Audit
        try:
            remaining = driver.window_handles
            if len(remaining) > 1:
                print(f"[Ghost {pid}] ⚠️ Purge finished with {len(remaining)} tab(s) still open.")
            if keep_handle in remaining:
                driver.switch_to.window(keep_handle)
        except Exception:
            pass
    
    def _start_silent_alert_assassin(self, pid, driver, duration=10.0):
        """
        Spawns a background thread that constantly checks for proxy popups.
        Uses Selenium's internal API to dismiss them SILENTLY without stealing PC focus.
        """
        def watcher():
            end_time = time.time() + duration
            while time.time() < end_time:
                try:
                    # Look for the native browser alert
                    alert = driver.switch_to.alert
                    alert.dismiss() # Click 'Cancel' silently inside the browser
                    print(f"[Ghost {pid}] ❌ Silent Alert Assassin neutralized a proxy popup.")
                except Exception:
                    pass # No alert found, keep waiting
                time.sleep(0.5)
                
        t = threading.Thread(target=watcher, daemon=True)
        t.start()
        return t
    
    def _get_keep_terms_for_target(self, target):
        """Returns URL/title terms for the tab we want to keep."""
        target = str(target or "").lower().strip()

        rules = {
            "youtube": ["youtube.com", "youtube"],
            "twitch": ["twitch.tv", "twitch"],
            "spotify": ["open.spotify.com", "spotify"],
            "deezer": ["deezer.com", "deezer"],
        }

        return rules.get(target, [target])

    def _purge_non_target_tabs_via_debugger(self, pid, debug_port, target, passes=5, pause=2):
        """
        Closes all non-target tabs using Chrome/Comet remote debugging.
        This avoids Selenium driver.close(), which is currently hanging for 20 seconds.
        """
        keep_terms = self._get_keep_terms_for_target(target)

        for pass_num in range(1, passes + 1):
            try:
                time.sleep(pause)

                list_url = f"http://127.0.0.1:{debug_port}/json"
                with urllib.request.urlopen(list_url, timeout=4) as response:
                    targets = json.loads(response.read().decode("utf-8", errors="replace"))

                pages = [t for t in targets if t.get("type") == "page"]

                if not pages:
                    print(f"[Ghost {pid}] ⚠️ Debugger purge pass {pass_num}: no page tabs found.")
                    continue

                keep_target = None

                for t in pages:
                    url = str(t.get("url", "")).lower()
                    title = str(t.get("title", "")).lower()

                    if any(term in url or term in title for term in keep_terms):
                        keep_target = t
                        break

                if not keep_target:
                    print(f"[Ghost {pid}] ⚠️ Debugger purge pass {pass_num}: target tab not found for {target}.")
                    for t in pages:
                        print(f"[Ghost {pid}] 🔎 Seen tab: title='{t.get('title', '')[:70]}' url='{t.get('url', '')[:120]}'")
                    continue

                keep_id = keep_target.get("id")
                extras = [t for t in pages if t.get("id") != keep_id]

                if not extras:
                    print(f"[Ghost {pid}] ✅ Debugger purge pass {pass_num}: single {target.upper()} tab confirmed.")
                    return True

                print(f"[Ghost {pid}] 🧹 Debugger purge pass {pass_num}: closing {len(extras)} extra tab(s).")

                for t in extras:
                    target_id = t.get("id")
                    title = t.get("title", "")
                    url = t.get("url", "")

                    if not target_id:
                        continue

                    print(f"[Ghost {pid}] 🧹 Closing extra tab via debugger: title='{title[:70]}' url='{url[:120]}'")

                    close_url = f"http://127.0.0.1:{debug_port}/json/close/{urllib.parse.quote(target_id, safe='')}"
                    try:
                        urllib.request.urlopen(close_url, timeout=4).read()
                    except Exception as e:
                        print(f"[Ghost {pid}] ⚠️ Debugger close failed for tab {target_id}: {e}")

            except Exception as e:
                print(f"[Ghost {pid}] ⚠️ Debugger tab purge pass {pass_num} failed: {e}")

        print(f"[Ghost {pid}] ⚠️ Debugger tab purge finished, but extra tabs may still exist.")
        return False

    def _start_late_tab_purge_watcher(self, pid, debug_port, target, duration=30, interval=3):
        """
        Proton/Comet can open extension tabs after the first purge.
        This watcher keeps removing non-target tabs for a short window after navigation.
        """
        def watcher():
            end_time = time.time() + duration

            while time.time() < end_time and self.is_running:
                self._purge_non_target_tabs_via_debugger(
                    pid=pid,
                    debug_port=debug_port,
                    target=target,
                    passes=1,
                    pause=0
                )
                time.sleep(interval)

            print(f"[Ghost {pid}] 🧹 Late tab purge watcher finished.")

        t = threading.Thread(target=watcher, daemon=True)
        t.start()
        return t

    def _launches_allowed(self):
        return bool(self.is_running and getattr(self, "launch_queue_enabled", True))
        
    def _mobile_device_templates(self):
        """Real Android phone/tablet shapes used to create stable profile identities."""
        return [
            {"name": "Samsung Galaxy S24", "model": "SM-S921U", "manufacturer": "Samsung", "res": (360, 780), "scale": 3, "android": ["14", "15"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 750, OpenGL ES 3.2)"},
            {"name": "Samsung Galaxy S24+", "model": "SM-S926U", "manufacturer": "Samsung", "res": (384, 832), "scale": 3.5, "android": ["14", "15"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 750, OpenGL ES 3.2)"},
            {"name": "Samsung Galaxy S24 Ultra", "model": "SM-S928U", "manufacturer": "Samsung", "res": (384, 824), "scale": 3.5, "android": ["14", "15"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 750, OpenGL ES 3.2)"},
            {"name": "Samsung Galaxy S23", "model": "SM-S911U", "manufacturer": "Samsung", "res": (360, 780), "scale": 3, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 740, OpenGL ES 3.2)"},
            {"name": "Samsung Galaxy S23+", "model": "SM-S916U", "manufacturer": "Samsung", "res": (384, 832), "scale": 3.5, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 740, OpenGL ES 3.2)"},
            {"name": "Samsung Galaxy S23 Ultra", "model": "SM-S918U", "manufacturer": "Samsung", "res": (384, 824), "scale": 3.5, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 740, OpenGL ES 3.2)"},
            {"name": "Samsung Galaxy S22", "model": "SM-S901U", "manufacturer": "Samsung", "res": (360, 780), "scale": 3, "android": ["12", "13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 730, OpenGL ES 3.2)"},
            {"name": "Samsung Galaxy S22 Ultra", "model": "SM-S908U", "manufacturer": "Samsung", "res": (384, 824), "scale": 3.5, "android": ["12", "13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 730, OpenGL ES 3.2)"},
            {"name": "Samsung Galaxy A55 5G", "model": "SM-A556E", "manufacturer": "Samsung", "res": (360, 800), "scale": 3, "android": ["14", "15"], "renderer": "ANGLE (ARM, Mali-G68, OpenGL ES 3.2)"},
            {"name": "Samsung Galaxy A54 5G", "model": "SM-A546U", "manufacturer": "Samsung", "res": (360, 800), "scale": 3, "android": ["13", "14"], "renderer": "ANGLE (ARM, Mali-G68, OpenGL ES 3.2)"},
            {"name": "Samsung Galaxy A35 5G", "model": "SM-A356U", "manufacturer": "Samsung", "res": (360, 800), "scale": 3, "android": ["14", "15"], "renderer": "ANGLE (ARM, Mali-G68, OpenGL ES 3.2)"},
            {"name": "Samsung Galaxy A34 5G", "model": "SM-A346U", "manufacturer": "Samsung", "res": (360, 800), "scale": 3, "android": ["13", "14"], "renderer": "ANGLE (ARM, Mali-G68, OpenGL ES 3.2)"},
            {"name": "Samsung Galaxy Z Fold5", "model": "SM-F946U", "manufacturer": "Samsung", "res": (373, 812), "scale": 3, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 740, OpenGL ES 3.2)"},
            {"name": "Samsung Galaxy Z Flip5", "model": "SM-F731U", "manufacturer": "Samsung", "res": (412, 915), "scale": 2.625, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 740, OpenGL ES 3.2)"},
            {"name": "Google Pixel 8", "model": "Pixel 8", "manufacturer": "Google", "res": (412, 915), "scale": 2.625, "android": ["14", "15"], "renderer": "ANGLE (ARM, Mali-G715, OpenGL ES 3.2)"},
            {"name": "Google Pixel 8 Pro", "model": "Pixel 8 Pro", "manufacturer": "Google", "res": (448, 998), "scale": 2.625, "android": ["14", "15"], "renderer": "ANGLE (ARM, Mali-G715, OpenGL ES 3.2)"},
            {"name": "Google Pixel 8a", "model": "Pixel 8a", "manufacturer": "Google", "res": (412, 915), "scale": 2.625, "android": ["14", "15"], "renderer": "ANGLE (ARM, Mali-G715, OpenGL ES 3.2)"},
            {"name": "Google Pixel 7", "model": "Pixel 7", "manufacturer": "Google", "res": (412, 915), "scale": 2.625, "android": ["13", "14"], "renderer": "ANGLE (ARM, Mali-G710, OpenGL ES 3.2)"},
            {"name": "Google Pixel 7 Pro", "model": "Pixel 7 Pro", "manufacturer": "Google", "res": (412, 892), "scale": 3.5, "android": ["13", "14"], "renderer": "ANGLE (ARM, Mali-G710, OpenGL ES 3.2)"},
            {"name": "Google Pixel 7a", "model": "Pixel 7a", "manufacturer": "Google", "res": (412, 915), "scale": 2.625, "android": ["13", "14"], "renderer": "ANGLE (ARM, Mali-G710, OpenGL ES 3.2)"},
            {"name": "Google Pixel 6", "model": "Pixel 6", "manufacturer": "Google", "res": (412, 915), "scale": 2.625, "android": ["12", "13", "14"], "renderer": "ANGLE (ARM, Mali-G78, OpenGL ES 3.2)"},
            {"name": "Google Pixel Fold", "model": "Pixel Fold", "manufacturer": "Google", "res": (393, 851), "scale": 2.625, "android": ["13", "14"], "renderer": "ANGLE (ARM, Mali-G710, OpenGL ES 3.2)"},
            {"name": "OnePlus 12", "model": "CPH2583", "manufacturer": "OnePlus", "res": (450, 1000), "scale": 3.2, "android": ["14", "15"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 750, OpenGL ES 3.2)"},
            {"name": "OnePlus 12R", "model": "CPH2611", "manufacturer": "OnePlus", "res": (450, 1000), "scale": 3.2, "android": ["14", "15"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 740, OpenGL ES 3.2)"},
            {"name": "OnePlus 11", "model": "CPH2451", "manufacturer": "OnePlus", "res": (412, 919), "scale": 3.5, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 740, OpenGL ES 3.2)"},
            {"name": "OnePlus 10 Pro", "model": "NE2215", "manufacturer": "OnePlus", "res": (412, 919), "scale": 3.5, "android": ["12", "13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 730, OpenGL ES 3.2)"},
            {"name": "OnePlus Nord 3", "model": "CPH2493", "manufacturer": "OnePlus", "res": (393, 873), "scale": 2.75, "android": ["13", "14"], "renderer": "ANGLE (ARM, Mali-G710, OpenGL ES 3.2)"},
            {"name": "Xiaomi 14", "model": "23127PN0CG", "manufacturer": "Xiaomi", "res": (393, 873), "scale": 3, "android": ["14", "15"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 750, OpenGL ES 3.2)"},
            {"name": "Xiaomi 14 Ultra", "model": "24030PN60G", "manufacturer": "Xiaomi", "res": (393, 873), "scale": 3.5, "android": ["14", "15"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 750, OpenGL ES 3.2)"},
            {"name": "Xiaomi 13", "model": "2211133G", "manufacturer": "Xiaomi", "res": (393, 873), "scale": 3, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 740, OpenGL ES 3.2)"},
            {"name": "Xiaomi 13T Pro", "model": "23078PND5G", "manufacturer": "Xiaomi", "res": (393, 873), "scale": 3, "android": ["13", "14"], "renderer": "ANGLE (ARM, Immortalis-G715, OpenGL ES 3.2)"},
            {"name": "Redmi Note 13 Pro", "model": "2312DRA50G", "manufacturer": "Xiaomi", "res": (393, 873), "scale": 2.75, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 710, OpenGL ES 3.2)"},
            {"name": "Redmi Note 12 Pro", "model": "22101316G", "manufacturer": "Xiaomi", "res": (393, 873), "scale": 2.75, "android": ["12", "13"], "renderer": "ANGLE (ARM, Mali-G68, OpenGL ES 3.2)"},
            {"name": "POCO F6 Pro", "model": "23113RKC6G", "manufacturer": "Xiaomi", "res": (393, 873), "scale": 3, "android": ["14", "15"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 740, OpenGL ES 3.2)"},
            {"name": "POCO X6 Pro", "model": "2311DRK48G", "manufacturer": "Xiaomi", "res": (393, 873), "scale": 2.75, "android": ["14", "15"], "renderer": "ANGLE (ARM, Mali-G615, OpenGL ES 3.2)"},
            {"name": "Motorola Edge 40", "model": "XT2303-2", "manufacturer": "Motorola", "res": (393, 873), "scale": 2.75, "android": ["13", "14"], "renderer": "ANGLE (ARM, Mali-G610, OpenGL ES 3.2)"},
            {"name": "Motorola Edge 50 Pro", "model": "XT2403-2", "manufacturer": "Motorola", "res": (393, 873), "scale": 2.75, "android": ["14", "15"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 720, OpenGL ES 3.2)"},
            {"name": "Motorola Razr 40 Ultra", "model": "XT2321-1", "manufacturer": "Motorola", "res": (412, 915), "scale": 2.625, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 730, OpenGL ES 3.2)"},
            {"name": "Motorola Moto G Power 5G", "model": "XT2311-3", "manufacturer": "Motorola", "res": (393, 873), "scale": 2.75, "android": ["13", "14"], "renderer": "ANGLE (ARM, Mali-G57, OpenGL ES 3.2)"},
            {"name": "Nothing Phone (2)", "model": "A065", "manufacturer": "Nothing", "res": (412, 915), "scale": 2.625, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 730, OpenGL ES 3.2)"},
            {"name": "Nothing Phone (2a)", "model": "A142", "manufacturer": "Nothing", "res": (412, 915), "scale": 2.625, "android": ["14", "15"], "renderer": "ANGLE (ARM, Mali-G610, OpenGL ES 3.2)"},
            {"name": "Sony Xperia 1 V", "model": "XQ-DQ72", "manufacturer": "Sony", "res": (412, 915), "scale": 3.5, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 740, OpenGL ES 3.2)"},
            {"name": "Sony Xperia 5 V", "model": "XQ-DE72", "manufacturer": "Sony", "res": (393, 873), "scale": 3, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 740, OpenGL ES 3.2)"},
            {"name": "ASUS Zenfone 10", "model": "AI2302", "manufacturer": "ASUS", "res": (393, 873), "scale": 3, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 740, OpenGL ES 3.2)"},
            {"name": "ASUS ROG Phone 8", "model": "AI2401", "manufacturer": "ASUS", "res": (393, 873), "scale": 2.75, "android": ["14", "15"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 750, OpenGL ES 3.2)"},
            {"name": "OPPO Find X7 Ultra", "model": "PHY110", "manufacturer": "OPPO", "res": (412, 915), "scale": 3.5, "android": ["14", "15"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 750, OpenGL ES 3.2)"},
            {"name": "OPPO Reno 11 Pro", "model": "CPH2607", "manufacturer": "OPPO", "res": (393, 873), "scale": 2.75, "android": ["14", "15"], "renderer": "ANGLE (ARM, Mali-G610, OpenGL ES 3.2)"},
            {"name": "Vivo X100 Pro", "model": "V2309A", "manufacturer": "Vivo", "res": (412, 915), "scale": 3, "android": ["14", "15"], "renderer": "ANGLE (ARM, Immortalis-G720, OpenGL ES 3.2)"},
            {"name": "Vivo V30 Pro", "model": "V2319", "manufacturer": "Vivo", "res": (393, 873), "scale": 2.75, "android": ["14", "15"], "renderer": "ANGLE (ARM, Mali-G610, OpenGL ES 3.2)"},
            {"name": "Honor Magic6 Pro", "model": "BVL-N49", "manufacturer": "Honor", "res": (432, 932), "scale": 3, "android": ["14", "15"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 750, OpenGL ES 3.2)"},
            {"name": "Honor 90", "model": "REA-NX9", "manufacturer": "Honor", "res": (393, 873), "scale": 2.75, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 644, OpenGL ES 3.2)"},
            {"name": "Realme GT 5 Pro", "model": "RMX3888", "manufacturer": "Realme", "res": (412, 915), "scale": 3, "android": ["14", "15"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 750, OpenGL ES 3.2)"},
            {"name": "Realme 12 Pro+", "model": "RMX3840", "manufacturer": "Realme", "res": (393, 873), "scale": 2.75, "android": ["14", "15"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 710, OpenGL ES 3.2)"},
            {"name": "Nokia X30 5G", "model": "TA-1450", "manufacturer": "HMD Global", "res": (393, 873), "scale": 2.75, "android": ["12", "13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 619, OpenGL ES 3.2)"},
            {"name": "Fairphone 5", "model": "FP5", "manufacturer": "Fairphone", "res": (393, 873), "scale": 2.75, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 644, OpenGL ES 3.2)"},
            {"name": "Lenovo Tab P12", "model": "TB370FU", "manufacturer": "Lenovo", "res": (1024, 768), "scale": 2, "android": ["13", "14"], "renderer": "ANGLE (ARM, Mali-G68, OpenGL ES 3.2)"},
            {"name": "Samsung Galaxy Tab S9", "model": "SM-X710", "manufacturer": "Samsung", "res": (1024, 768), "scale": 2, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 740, OpenGL ES 3.2)"},
            {"name": "Google Pixel Tablet", "model": "Pixel Tablet", "manufacturer": "Google", "res": (1024, 768), "scale": 2, "android": ["13", "14"], "renderer": "ANGLE (ARM, Mali-G710, OpenGL ES 3.2)"},
            {"name": "Samsung Galaxy S21", "model": "SM-G991U", "manufacturer": "Samsung", "res": (360, 800), "scale": 3, "android": ["12", "13"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 660, OpenGL ES 3.2)"},
            {"name": "Samsung Galaxy S21 Ultra", "model": "SM-G998U", "manufacturer": "Samsung", "res": (384, 854), "scale": 3.5, "android": ["12", "13"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 660, OpenGL ES 3.2)"},
            {"name": "Samsung Galaxy A53 5G", "model": "SM-A536U", "manufacturer": "Samsung", "res": (360, 800), "scale": 3, "android": ["12", "13", "14"], "renderer": "ANGLE (ARM, Mali-G68, OpenGL ES 3.2)"},
            {"name": "Samsung Galaxy A52s 5G", "model": "SM-A528B", "manufacturer": "Samsung", "res": (360, 800), "scale": 3, "android": ["11", "12", "13"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 642L, OpenGL ES 3.2)"},
            {"name": "Google Pixel 6a", "model": "Pixel 6a", "manufacturer": "Google", "res": (412, 915), "scale": 2.625, "android": ["12", "13", "14"], "renderer": "ANGLE (ARM, Mali-G78, OpenGL ES 3.2)"},
            {"name": "Google Pixel 5", "model": "Pixel 5", "manufacturer": "Google", "res": (393, 851), "scale": 2.75, "android": ["11", "12", "13"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 620, OpenGL ES 3.2)"},
            {"name": "OnePlus 9 Pro", "model": "LE2125", "manufacturer": "OnePlus", "res": (412, 919), "scale": 3.5, "android": ["11", "12", "13"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 660, OpenGL ES 3.2)"},
            {"name": "Xiaomi 12", "model": "2201123G", "manufacturer": "Xiaomi", "res": (393, 873), "scale": 3, "android": ["12", "13"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 730, OpenGL ES 3.2)"},
            {"name": "Redmi Note 11 Pro", "model": "2201116TG", "manufacturer": "Xiaomi", "res": (393, 873), "scale": 2.75, "android": ["11", "12", "13"], "renderer": "ANGLE (ARM, Mali-G57, OpenGL ES 3.2)"},
            {"name": "POCO F5", "model": "23049PCD8G", "manufacturer": "Xiaomi", "res": (393, 873), "scale": 2.75, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 725, OpenGL ES 3.2)"},
            {"name": "Motorola Moto G Stylus 5G", "model": "XT2315-1", "manufacturer": "Motorola", "res": (393, 873), "scale": 2.75, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 619, OpenGL ES 3.2)"},
            {"name": "Motorola Edge 30 Pro", "model": "XT2201-1", "manufacturer": "Motorola", "res": (393, 873), "scale": 2.75, "android": ["12", "13"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 730, OpenGL ES 3.2)"},
            {"name": "Nothing Phone (1)", "model": "A063", "manufacturer": "Nothing", "res": (412, 915), "scale": 2.625, "android": ["12", "13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 642L, OpenGL ES 3.2)"},
            {"name": "Sony Xperia 10 V", "model": "XQ-DC72", "manufacturer": "Sony", "res": (393, 873), "scale": 2.75, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 619, OpenGL ES 3.2)"},
            {"name": "OPPO Find X5 Pro", "model": "CPH2305", "manufacturer": "OPPO", "res": (412, 915), "scale": 3.5, "android": ["12", "13"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 730, OpenGL ES 3.2)"},
            {"name": "Vivo X90 Pro", "model": "V2219", "manufacturer": "Vivo", "res": (412, 915), "scale": 3, "android": ["13", "14"], "renderer": "ANGLE (ARM, Immortalis-G715, OpenGL ES 3.2)"},
            {"name": "Honor Magic5 Pro", "model": "PGT-N19", "manufacturer": "Honor", "res": (432, 932), "scale": 3, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 740, OpenGL ES 3.2)"},
            {"name": "Realme GT Neo 5", "model": "RMX3706", "manufacturer": "Realme", "res": (393, 873), "scale": 2.75, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 730, OpenGL ES 3.2)"},
            {"name": "Xiaomi Pad 6", "model": "23043RP34G", "manufacturer": "Xiaomi", "res": (1024, 768), "scale": 2, "android": ["13", "14"], "renderer": "ANGLE (Qualcomm, Adreno (TM) 650, OpenGL ES 3.2)"},
            {"name": "OnePlus Pad", "model": "OPD2203", "manufacturer": "OnePlus", "res": (1024, 768), "scale": 2, "android": ["13", "14"], "renderer": "ANGLE (ARM, Mali-G710, OpenGL ES 3.2)"},
        ]

    def _desktop_device_templates(self):
        """Real desktop/laptop browser shapes used for the PC share of profiles."""
        return [
            {"name": "Windows 11 Desktop - RTX 4070", "os": "Windows", "platform": "Win32", "res": (1920, 1080), "scale": 1, "vendor": "Google Inc.", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0, D3D11)", "ua_os": "Windows NT 10.0; Win64; x64", "cores": [8, 12, 16], "memory": [8, 16, 32]},
            {"name": "Windows 11 Laptop - Intel Iris Xe", "os": "Windows", "platform": "Win32", "res": (1536, 864), "scale": 1.25, "vendor": "Google Inc.", "renderer": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)", "ua_os": "Windows NT 10.0; Win64; x64", "cores": [8, 12], "memory": [8, 16]},
            {"name": "Windows 11 Laptop - AMD Radeon", "os": "Windows", "platform": "Win32", "res": (1600, 900), "scale": 1.25, "vendor": "Google Inc.", "renderer": "ANGLE (AMD, AMD Radeon Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)", "ua_os": "Windows NT 10.0; Win64; x64", "cores": [8, 12, 16], "memory": [8, 16, 32]},
            {"name": "Windows 10 Desktop - GTX 1660", "os": "Windows", "platform": "Win32", "res": (1920, 1080), "scale": 1, "vendor": "Google Inc.", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 Direct3D11 vs_5_0 ps_5_0, D3D11)", "ua_os": "Windows NT 10.0; Win64; x64", "cores": [6, 8], "memory": [8, 16]},
            {"name": "Windows 11 Desktop - RX 7800 XT", "os": "Windows", "platform": "Win32", "res": (2560, 1440), "scale": 1, "vendor": "Google Inc.", "renderer": "ANGLE (AMD, AMD Radeon RX 7800 XT Direct3D11 vs_5_0 ps_5_0, D3D11)", "ua_os": "Windows NT 10.0; Win64; x64", "cores": [12, 16], "memory": [16, 32]},
            {"name": "Windows 11 Surface Laptop", "os": "Windows", "platform": "Win32", "res": (1504, 1003), "scale": 1.5, "vendor": "Google Inc.", "renderer": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)", "ua_os": "Windows NT 10.0; Win64; x64", "cores": [8, 10, 12], "memory": [8, 16]},
            {"name": "macOS MacBook Air M2", "os": "macOS", "platform": "MacIntel", "res": (1440, 900), "scale": 2, "vendor": "Google Inc.", "renderer": "ANGLE (Apple, Apple M2, OpenGL 4.1)", "ua_os": "Macintosh; Intel Mac OS X 10_15_7", "cores": [8], "memory": [8, 16]},
            {"name": "macOS MacBook Pro M3", "os": "macOS", "platform": "MacIntel", "res": (1512, 982), "scale": 2, "vendor": "Google Inc.", "renderer": "ANGLE (Apple, Apple M3, OpenGL 4.1)", "ua_os": "Macintosh; Intel Mac OS X 10_15_7", "cores": [8, 12], "memory": [16, 24, 32]},
            {"name": "macOS iMac M1", "os": "macOS", "platform": "MacIntel", "res": (2240, 1260), "scale": 2, "vendor": "Google Inc.", "renderer": "ANGLE (Apple, Apple M1, OpenGL 4.1)", "ua_os": "Macintosh; Intel Mac OS X 10_15_7", "cores": [8], "memory": [8, 16]},
            {"name": "Linux Desktop - Mesa Intel", "os": "Linux", "platform": "Linux x86_64", "res": (1920, 1080), "scale": 1, "vendor": "Google Inc.", "renderer": "ANGLE (Intel, Mesa Intel(R) UHD Graphics, OpenGL 4.6)", "ua_os": "X11; Linux x86_64", "cores": [8, 12], "memory": [8, 16, 32]},
            {"name": "Linux Laptop - AMD Radeon", "os": "Linux", "platform": "Linux x86_64", "res": (1600, 900), "scale": 1, "vendor": "Google Inc.", "renderer": "ANGLE (AMD, AMD Radeon Graphics, OpenGL 4.6)", "ua_os": "X11; Linux x86_64", "cores": [8, 16], "memory": [8, 16, 32]},
            {"name": "Dell XPS 13 Plus", "os": "Windows", "platform": "Win32", "res": (1536, 960), "scale": 1.5, "vendor": "Google Inc.", "renderer": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)", "ua_os": "Windows NT 10.0; Win64; x64", "cores": [8, 10, 12], "memory": [8, 16, 32]},
            {"name": "Dell XPS 15", "os": "Windows", "platform": "Win32", "res": (1920, 1200), "scale": 1.25, "vendor": "Google Inc.", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4050 Laptop GPU Direct3D11 vs_5_0 ps_5_0, D3D11)", "ua_os": "Windows NT 10.0; Win64; x64", "cores": [12, 16], "memory": [16, 32]},
            {"name": "HP Spectre x360", "os": "Windows", "platform": "Win32", "res": (1536, 864), "scale": 1.5, "vendor": "Google Inc.", "renderer": "ANGLE (Intel, Intel(R) Arc(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)", "ua_os": "Windows NT 10.0; Win64; x64", "cores": [8, 12], "memory": [16, 32]},
            {"name": "Lenovo ThinkPad X1 Carbon", "os": "Windows", "platform": "Win32", "res": (1536, 960), "scale": 1.25, "vendor": "Google Inc.", "renderer": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)", "ua_os": "Windows NT 10.0; Win64; x64", "cores": [8, 12], "memory": [16, 32]},
            {"name": "Lenovo ThinkCentre Desktop", "os": "Windows", "platform": "Win32", "res": (1920, 1080), "scale": 1, "vendor": "Google Inc.", "renderer": "ANGLE (Intel, Intel(R) UHD Graphics 770 Direct3D11 vs_5_0 ps_5_0, D3D11)", "ua_os": "Windows NT 10.0; Win64; x64", "cores": [8, 12, 16], "memory": [8, 16, 32]},
            {"name": "ASUS ROG Zephyrus G14", "os": "Windows", "platform": "Win32", "res": (1707, 960), "scale": 1.5, "vendor": "Google Inc.", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Laptop GPU Direct3D11 vs_5_0 ps_5_0, D3D11)", "ua_os": "Windows NT 10.0; Win64; x64", "cores": [12, 16], "memory": [16, 32]},
            {"name": "Acer Swift Go 14", "os": "Windows", "platform": "Win32", "res": (1536, 960), "scale": 1.5, "vendor": "Google Inc.", "renderer": "ANGLE (Intel, Intel(R) Arc(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)", "ua_os": "Windows NT 10.0; Win64; x64", "cores": [8, 12], "memory": [8, 16]},
            {"name": "MSI Stealth 16 Studio", "os": "Windows", "platform": "Win32", "res": (1707, 1067), "scale": 1.5, "vendor": "Google Inc.", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Laptop GPU Direct3D11 vs_5_0 ps_5_0, D3D11)", "ua_os": "Windows NT 10.0; Win64; x64", "cores": [16, 20], "memory": [16, 32]},
            {"name": "Framework Laptop 13", "os": "Windows", "platform": "Win32", "res": (1504, 1003), "scale": 1.5, "vendor": "Google Inc.", "renderer": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)", "ua_os": "Windows NT 10.0; Win64; x64", "cores": [8, 12], "memory": [8, 16, 32]},
            {"name": "Mac mini M2", "os": "macOS", "platform": "MacIntel", "res": (1920, 1080), "scale": 2, "vendor": "Google Inc.", "renderer": "ANGLE (Apple, Apple M2, OpenGL 4.1)", "ua_os": "Macintosh; Intel Mac OS X 10_15_7", "cores": [8], "memory": [8, 16, 24]},
            {"name": "Mac Studio M2 Max", "os": "macOS", "platform": "MacIntel", "res": (2560, 1440), "scale": 2, "vendor": "Google Inc.", "renderer": "ANGLE (Apple, Apple M2 Max, OpenGL 4.1)", "ua_os": "Macintosh; Intel Mac OS X 10_15_7", "cores": [12], "memory": [32, 64]},
            {"name": "macOS MacBook Pro M1", "os": "macOS", "platform": "MacIntel", "res": (1512, 982), "scale": 2, "vendor": "Google Inc.", "renderer": "ANGLE (Apple, Apple M1 Pro, OpenGL 4.1)", "ua_os": "Macintosh; Intel Mac OS X 10_15_7", "cores": [8, 10], "memory": [16, 32]},
            {"name": "Ubuntu ThinkPad T14", "os": "Linux", "platform": "Linux x86_64", "res": (1536, 864), "scale": 1, "vendor": "Google Inc.", "renderer": "ANGLE (AMD, AMD Radeon Graphics, OpenGL 4.6)", "ua_os": "X11; Linux x86_64", "cores": [8, 12, 16], "memory": [8, 16, 32]},
            {"name": "Ubuntu Desktop - RTX 3060", "os": "Linux", "platform": "Linux x86_64", "res": (1920, 1080), "scale": 1, "vendor": "Google Inc.", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060, OpenGL 4.6)", "ua_os": "X11; Linux x86_64", "cores": [8, 12, 16], "memory": [16, 32]},
            {"name": "Fedora Laptop - AMD Ryzen", "os": "Linux", "platform": "Linux x86_64", "res": (1600, 900), "scale": 1, "vendor": "Google Inc.", "renderer": "ANGLE (AMD, AMD Radeon Graphics, OpenGL 4.6)", "ua_os": "X11; Linux x86_64", "cores": [8, 12, 16], "memory": [8, 16, 32]},
            {"name": "ChromeOS Chromebook Plus", "os": "ChromeOS", "platform": "Linux x86_64", "res": (1366, 768), "scale": 1, "vendor": "Google Inc.", "renderer": "ANGLE (Intel, Intel(R) UHD Graphics, OpenGL 4.6)", "ua_os": "X11; CrOS x86_64 15662.0.0", "cores": [8], "memory": [8, 16]},
            {"name": "ChromeOS Pixelbook Go", "os": "ChromeOS", "platform": "Linux x86_64", "res": (1536, 864), "scale": 1, "vendor": "Google Inc.", "renderer": "ANGLE (Intel, Intel(R) UHD Graphics 615, OpenGL 4.6)", "ua_os": "X11; CrOS x86_64 14541.0.0", "cores": [4, 8], "memory": [8, 16]},
            {"name": "Windows 11 Desktop - RTX 4090", "os": "Windows", "platform": "Win32", "res": (2560, 1440), "scale": 1, "vendor": "Google Inc.", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4090 Direct3D11 vs_5_0 ps_5_0, D3D11)", "ua_os": "Windows NT 10.0; Win64; x64", "cores": [16, 24], "memory": [32, 64]},
            {"name": "macOS MacBook Air M3", "os": "macOS", "platform": "MacIntel", "res": (1470, 956), "scale": 2, "vendor": "Google Inc.", "renderer": "ANGLE (Apple, Apple M3, OpenGL 4.1)", "ua_os": "Macintosh; Intel Mac OS X 10_15_7", "cores": [8], "memory": [8, 16, 24]},
        ]

    def _generate_hardware_cloak(self, profile_id, existing_signatures=None, forced_type=None):
        """Creates a saved, unique device identity for one profile."""
        rng = random.SystemRandom()
        existing_signatures = set(existing_signatures or [])
        existing_device_names = {
            item.split("device:", 1)[1]
            for item in existing_signatures
            if isinstance(item, str) and item.startswith("device:")
        }
        languages = [
            ("en-US", ["en-US", "en"], "en-US,en;q=0.9"),
            ("en-GB", ["en-GB", "en"], "en-GB,en;q=0.9"),
            ("es-MX", ["es-MX", "es", "en-US"], "es-MX,es;q=0.9,en-US;q=0.7"),
            ("es-ES", ["es-ES", "es", "en-US"], "es-ES,es;q=0.9,en-US;q=0.7"),
            ("fr-FR", ["fr-FR", "fr", "en-US"], "fr-FR,fr;q=0.9,en-US;q=0.7"),
            ("pt-BR", ["pt-BR", "pt", "en-US"], "pt-BR,pt;q=0.9,en-US;q=0.7"),
        ]
        chrome_versions = [
            "148.0.7778.1018",
            "148.0.7778.1000",
            "147.0.7756.88",
            "146.0.7714.76",
        ]

        requested_type = str(forced_type or "").strip().lower()
        is_desktop = requested_type in {"pc", "desktop", "computer"}
        if not requested_type:
            is_desktop = rng.random() < 0.30

        templates = self._desktop_device_templates() if is_desktop else self._mobile_device_templates()
        template_device_names = {item["name"] for item in templates}
        profile_id = int(profile_id or 0)

        for _ in range(250):
            device = rng.choice(templates)
            used_template_names = existing_device_names & template_device_names
            if len(used_template_names) < len(templates) and device["name"] in used_template_names:
                continue

            language, language_list, accept_language = rng.choice(languages)
            chrome_version = rng.choice(chrome_versions)
            width, height = device["res"]

            if is_desktop:
                width = int(width + rng.choice([-120, -80, 0, 80, 120]))
                height = int(height + rng.choice([-80, -40, 0, 40, 80]))
                hardware_concurrency = rng.choice(device["cores"])
                device_memory = rng.choice(device["memory"])
                touch_points = 0
                signature = "|".join([
                    "Desktop",
                    device["name"],
                    device["os"],
                    device["platform"],
                    f"{width}x{height}",
                    language,
                    chrome_version,
                    str(hardware_concurrency),
                    str(device_memory),
                ])
            else:
                android_version = rng.choice(device["android"])
                # Small real-world viewport differences from display zoom / browser UI.
                width = int(width + rng.choice([-8, -4, 0, 4, 8]))
                height = int(height + rng.choice([-16, -8, 0, 8, 16]))
                hardware_concurrency = rng.choice([6, 8])
                device_memory = rng.choice([4, 6, 8])
                touch_points = rng.choice([5, 8, 10])
                signature = "|".join([
                    "Mobile",
                    device["name"],
                    device["model"],
                    android_version,
                    f"{width}x{height}",
                    language,
                    chrome_version,
                    str(hardware_concurrency),
                    str(device_memory),
                    str(touch_points),
                ])

            if signature not in existing_signatures:
                break
        else:
            signature = f"{templates[0]['name']}|fallback|{profile_id}|{time.time()}"
            device = templates[profile_id % len(templates)]
            language, language_list, accept_language = rng.choice(languages)
            chrome_version = rng.choice(chrome_versions)
            width, height = device["res"]
            if is_desktop:
                hardware_concurrency = rng.choice(device.get("cores", [8]))
                device_memory = rng.choice(device.get("memory", [8]))
                touch_points = 0
            else:
                android_version = rng.choice(device["android"])
                hardware_concurrency = 8
                device_memory = 6
                touch_points = 8

        if is_desktop:
            user_agent = (
                f"Mozilla/5.0 ({device['ua_os']}) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{chrome_version} Safari/537.36"
            )
            display = f"{device['name']} / {device['os']} / {width}x{height} / {language}"

            return {
                "schema": "comet_device_identity_v2",
                "type": "Desktop",
                "device_name": device["name"],
                "manufacturer": device["os"],
                "model": device["name"],
                "os": device["os"],
                "os_version": "",
                "resolution": [int(width), int(height)],
                "device_scale_factor": float(device["scale"]),
                "language": language,
                "languages": language_list,
                "accept_language": accept_language,
                "vendor": device.get("vendor", "Google Inc."),
                "platform": device["platform"],
                "renderer": device["renderer"],
                "user_agent": user_agent,
                "mobile": False,
                "touch_points": int(touch_points),
                "hardware_concurrency": int(hardware_concurrency),
                "device_memory": int(device_memory),
                "display_string": display,
                "fingerprint_signature": signature,
                "fingerprint_id": f"PC-{profile_id}-{int(time.time() * 1000)}-{rng.randrange(1000, 9999)}",
            }

        android_version = locals().get("android_version") or rng.choice(device["android"])
        user_agent = (
            f"Mozilla/5.0 (Linux; Android {android_version}; {device['model']}) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{chrome_version} Mobile Safari/537.36"
        )
        display = f"{device['name']} / Android {android_version} / {width}x{height} / {language}"

        return {
            "schema": "comet_device_identity_v2",
            "type": "Mobile",
            "device_name": device["name"],
            "manufacturer": device["manufacturer"],
            "model": device["model"],
            "os": "Android",
            "os_version": android_version,
            "resolution": [int(width), int(height)],
            "device_scale_factor": float(device["scale"]),
            "language": language,
            "languages": language_list,
            "accept_language": accept_language,
            "vendor": "Google Inc.",
            "platform": "Linux armv8l",
            "renderer": device["renderer"],
            "user_agent": user_agent,
            "mobile": True,
            "touch_points": int(touch_points),
            "hardware_concurrency": int(hardware_concurrency),
            "device_memory": int(device_memory),
            "display_string": display,
            "fingerprint_signature": signature,
            "fingerprint_id": f"MOB-{profile_id}-{int(time.time() * 1000)}-{rng.randrange(1000, 9999)}",
        }

    def _normalize_hardware_cloak(self, cloak, profile_id=None):
        if not isinstance(cloak, dict):
            return None

        normalized = dict(cloak)
        type_text = str(normalized.get("type") or "Mobile").strip()
        is_desktop = type_text.lower() in {"desktop", "pc", "computer"}
        normalized["type"] = "Desktop" if is_desktop else "Mobile"
        normalized.setdefault("os", "Windows" if is_desktop else "Android")
        normalized.setdefault("platform", "Win32" if is_desktop else "Linux armv8l")
        normalized.setdefault("vendor", "Google Inc.")
        normalized.setdefault("language", "en-US")
        normalized.setdefault("languages", [normalized["language"], "en"])
        normalized.setdefault("accept_language", ",".join(normalized["languages"]))
        normalized["mobile"] = False if is_desktop else bool(normalized.get("mobile", True))
        normalized.setdefault("touch_points", 0 if is_desktop else 8)
        normalized.setdefault("hardware_concurrency", 8)
        normalized.setdefault("device_memory", 8 if is_desktop else 6)

        resolution = normalized.get("resolution") or ([1920, 1080] if is_desktop else [412, 915])
        if isinstance(resolution, tuple):
            resolution = list(resolution)
        normalized["resolution"] = [int(resolution[0]), int(resolution[1])]
        normalized.setdefault("device_scale_factor", 1 if is_desktop else 3)

        if not normalized.get("user_agent"):
            if is_desktop:
                ua_os = "Macintosh; Intel Mac OS X 10_15_7" if normalized["platform"] == "MacIntel" else "Windows NT 10.0; Win64; x64"
                normalized["user_agent"] = (
                    f"Mozilla/5.0 ({ua_os}) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/148.0.7778.1018 Safari/537.36"
                )
            else:
                model = normalized.get("model") or normalized.get("device_name") or "Pixel 8"
                os_version = normalized.get("os_version") or "14"
                normalized["user_agent"] = (
                    f"Mozilla/5.0 (Linux; Android {os_version}; {model}) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/148.0.7778.1018 Mobile Safari/537.36"
                )

        if not normalized.get("display_string"):
            if is_desktop:
                normalized["display_string"] = (
                    f"{normalized.get('device_name', 'Desktop PC')} / "
                    f"{normalized.get('os', 'Windows')} / "
                    f"{normalized['resolution'][0]}x{normalized['resolution'][1]} / "
                    f"{normalized.get('language', 'en-US')}"
                )
            else:
                normalized["display_string"] = (
                    f"{normalized.get('device_name', 'Mobile Device')} / "
                    f"Android {normalized.get('os_version', '')} / "
                    f"{normalized['resolution'][0]}x{normalized['resolution'][1]} / "
                    f"{normalized.get('language', 'en-US')}"
                )

        return normalized

    def _profile_hardware_cloak(self, profile):
        profile = profile or {}
        profile_id = profile.get("id") or 0

        candidates = [
            profile.get("hardware_profile"),
            profile.get("hardware_profile_json"),
            profile.get("hardware_cloak"),
        ]

        for candidate in candidates:
            if isinstance(candidate, dict):
                normalized = self._normalize_hardware_cloak(candidate, profile_id=profile_id)
                if normalized:
                    return normalized
            elif isinstance(candidate, str) and candidate.strip().startswith("{"):
                try:
                    normalized = self._normalize_hardware_cloak(json.loads(candidate), profile_id=profile_id)
                    if normalized:
                        return normalized
                except Exception:
                    pass

        existing_sigs = self._collect_existing_fingerprint_signatures(exclude_profile_id=profile_id)
        return self._generate_hardware_cloak(profile_id, existing_signatures=existing_sigs)

    def _collect_existing_fingerprint_signatures(self, exclude_profile_id=None):
        """Fetches all saved fingerprint signatures from the DB to prevent duplicates.

        Returns a set using the same format as start_dashboard._used_device_signatures:
        - The raw fingerprint_signature string
        - "device:{device_name}" for device-level deduplication
        """
        sigs = set()
        try:
            profiles = self.db.get_all_profiles() if hasattr(self.db, "get_all_profiles") else []
            for p in profiles:
                if exclude_profile_id is not None and p.get("id") == exclude_profile_id:
                    continue
                hw = p.get("hardware_profile_json") or p.get("hardware_profile") or p.get("hardware_cloak") or ""
                if isinstance(hw, str) and hw.strip().startswith("{"):
                    try:
                        hw = json.loads(hw)
                    except Exception:
                        hw = {}
                if isinstance(hw, dict):
                    sig = hw.get("fingerprint_signature") or hw.get("fingerprint_id")
                    if sig:
                        sigs.add(str(sig))
                    device_name = hw.get("device_name")
                    if device_name:
                        sigs.add(f"device:{device_name}")
        except Exception as e:
            print(f"[GhostCore] Could not collect existing fingerprint signatures: {e}")
        return sigs

    def _apply_device_cloak_to_driver(self, driver, cloak, pid=None):
        """Applies the saved device identity through Chrome DevTools and selenium-stealth."""
        existing_sigs = self._collect_existing_fingerprint_signatures(exclude_profile_id=pid)
        cloak = self._normalize_hardware_cloak(cloak, profile_id=pid) or self._generate_hardware_cloak(pid or 0, existing_signatures=existing_sigs)
        width, height = cloak["resolution"]
        is_mobile = bool(cloak.get("mobile", True)) and str(cloak.get("type", "")).lower() != "desktop"

        try:
            driver.execute_cdp_cmd("Network.setUserAgentOverride", {
                "userAgent": cloak["user_agent"],
                "acceptLanguage": cloak.get("accept_language") or cloak.get("language", "en-US"),
                "platform": cloak.get("platform", "Linux armv8l"),
            })
        except Exception as e:
            print(f"[Ghost {pid}] ⚠️ Device user-agent override failed: {e}")

        try:
            driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
                "width": int(width),
                "height": int(height),
                "deviceScaleFactor": float(cloak.get("device_scale_factor", 3 if is_mobile else 1)),
                "mobile": bool(is_mobile),
            })
            driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {
                "enabled": bool(is_mobile),
                "maxTouchPoints": int(cloak.get("touch_points", 8 if is_mobile else 0)),
            })
        except Exception as e:
            print(f"[Ghost {pid}] ⚠️ Device viewport/touch override failed: {e}")

        try:
            stealth(
                driver,
                languages=cloak.get("languages") or [cloak.get("language", "en-US"), "en"],
                vendor=cloak.get("vendor", "Google Inc."),
                platform=cloak.get("platform", "Linux armv8l"),
                webgl_vendor=cloak.get("vendor", "Google Inc."),
                renderer=cloak.get("renderer", "ANGLE (Qualcomm, Adreno (TM) 740, OpenGL ES 3.2)" if is_mobile else "ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"),
                fix_hairline=True,
            )
        except Exception as e:
            print(f"[Ghost {pid}] ⚠️ Stealth device cloak failed: {e}")

        try:
            nav_script = f"""
                Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {int(cloak.get('hardware_concurrency', 8))} }});
                Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {int(cloak.get('device_memory', 6 if is_mobile else 8))} }});
                Object.defineProperty(navigator, 'maxTouchPoints', {{ get: () => {int(cloak.get('touch_points', 8 if is_mobile else 0))} }});
                Object.defineProperty(navigator, 'platform', {{ get: () => '{cloak.get('platform', 'Linux armv8l')}' }});
            """
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": nav_script})
            try:
                driver.execute_script(nav_script)
            except Exception:
                pass
        except Exception as e:
            print(f"[Ghost {pid}] ⚠️ Navigator device property override failed: {e}")

        print(f"[Ghost {pid}] Device profile active: {cloak.get('display_string')}")
        return cloak

    def _independent_ghost_thread(self, profile, platforms, ready_event=None):
        """Runs independently. Splits into Manual vs Automation modes."""
        pid = profile['id']
        ready_signaled = False

        def signal_queue_ready(reason):
            nonlocal ready_signaled
            if ready_event and not ready_signaled:
                print(f"[Ghost {pid}] {reason}. Green-lighting next profile in queue.")
                ready_event.set()
                ready_signaled = True

        mode = "manual" if not platforms else "automation"
        initial_platform = "Manual" if not platforms else "Pending"

        session_id = self.session_recorder.start(
            profile_id=pid,
            platform=initial_platform,
            mode=mode,
            details=f"Profile thread started. mode={mode}"
        )
        
        if not hasattr(self, 'active_sessions'):
            self.active_sessions = {}

        self.active_sessions[pid] = {
            'driver': None,
            'proc': None,
            'session_id': session_id,
            'mode': mode,
            'current_target': initial_platform
        }

        self.session_recorder.event(
            profile_id=pid,
            session_id=session_id,
            platform=initial_platform,
            event_type="PROFILE_THREAD_STARTED",
            details={
                "mode": mode,
                "platforms": platforms or []
            }
        )
        
        # ==========================================
        # 🛠️ MODE 1: MANUAL OVERRIDE (All Toggles OFF)
        # ==========================================
        if not platforms:
            print(f"[Ghost {pid}] 🛠️ MANUAL MODE: Opening raw browser for configuration...")
            self._update_profile_state(pid, status="RUNNING", target_platform="Manual")
            
            debug_port = 9300 + int(pid)
            profile_dir = os.path.join(os.getcwd(), f"comet_profiles/profile_{pid}")
            os.makedirs(profile_dir, exist_ok=True)
            self.active_sessions[pid]["debug_port"] = debug_port
            self.active_sessions[pid]["profile_dir"] = profile_dir
            self._prepare_profile_for_clean_boot(pid, profile_dir)
            cloak = self._profile_hardware_cloak(profile)
            window_layout = self._allocate_browser_layout(pid)
            self.active_sessions[pid]["window_layout"] = window_layout
        
            args = [
                self.comet_path, 
                f"--user-data-dir={profile_dir}", 
                f"--remote-debugging-port={debug_port}",
                f"--load-extension={self.vpn_path}",
                f"--user-agent={cloak['user_agent']}",
                f"--accept-lang={cloak.get('accept_language') or cloak['language']}",
                *self._browser_window_args(window_layout),
                "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                "--no-first-run", 
                "--no-default-browser-check"
            ]
            
            proc = None
            driver = None
            cached_ip_label = None
            try:
                proc = subprocess.Popen(args, creationflags=subprocess.CREATE_NO_WINDOW)
                self.active_sessions[pid]['proc'] = proc
                self._schedule_browser_window_layout(
                    pid,
                    proc,
                    window_layout,
                    debug_port=debug_port,
                    profile_dir=profile_dir,
                )

                self.session_recorder.browser_launched(
                    profile_id=pid,
                    session_id=session_id,
                    platform="Manual",
                    proc=proc,
                    debug_port=debug_port,
                    profile_dir=profile_dir
                )

                print(f"[Ghost {pid}] ✅ Manual browser opened and marked RUNNING.")

                # Attach Selenium to the manual browser so the dashboard can show the live VPN/session IP.
                last_ip_check = 0
                first_ip_check_done = False

                try:
                    time.sleep(4)
                    driver = self._attach_to_debugger(debug_port)

                    if driver is not None:
                        self._apply_browser_window_layout(
                            pid,
                            proc,
                            window_layout,
                            debug_port=debug_port,
                            profile_dir=profile_dir,
                            quiet=True,
                        )
                        self.active_sessions[pid]['driver'] = driver
                        self.active_sessions[pid]['current_target'] = "Manual"
                        self._apply_device_cloak_to_driver(driver, cloak, pid=pid)

                        self.session_recorder.selenium_attached(
                            profile_id=pid,
                            session_id=session_id,
                            platform="Manual",
                            driver=driver,
                            debug_port=debug_port
                        )

                        print(f"[Ghost {pid}] ✅ Selenium attached for live manual IP tracking.")
                        print(f"[Ghost {pid}] 🌍 First live IP check will run in 5 seconds.")
                    else:
                        self.session_recorder.event(
                            profile_id=pid,
                            session_id=session_id,
                            platform="Manual",
                            event_type="SELENIUM_ATTACH_FAILED",
                            details="Manual browser stayed open, but Selenium could not attach."
                        )
                        print(f"[Ghost {pid}] ⚠️ Selenium attach returned None. Browser stays open, but live IP cannot update yet.")

                except Exception as e:
                    driver = None
                    print(f"[Ghost {pid}] ⚠️ Could not attach Selenium for manual IP tracking: {e}")

                # Keep dashboard RUNNING as long as the browser window exists.
                # Resource rule: verify the IP only once per manual launch.
                if driver is not None:
                    print(f"[Ghost {pid}] 🌍 One-time manual IP verification will run in 5 seconds...")
                    time.sleep(5)

                    try:
                        self._start_proxy_cancel_watcher(pid, duration=2.5, interval=0.35)
                    except Exception:
                        pass

                    self.session_recorder.ip_checking(
                        profile_id=pid,
                        session_id=session_id,
                        platform="Manual"
                    )
                    
                    ip_info = self._resolve_live_ip_with_retries(
                        pid,
                        driver,
                        retries=6,
                        first_delay=0,
                        delay=3
                    )

                    if ip_info and ip_info.get("label"):
                        resolved_ip_string = ip_info["label"]
                        cached_ip_label = resolved_ip_string

                        is_blacklisted, blacklist_reason = self._is_ip_blacklisted(ip_info)
                        if is_blacklisted:
                            self._shutdown_for_blacklisted_ip(
                                pid,
                                driver,
                                proc,
                                ip_info,
                                target_platform="Manual",
                                reason=blacklist_reason
                            )
                            return

                        print(f"[Ghost {pid}] 🌍 One-time manual IP detected: {resolved_ip_string}")
                        
                        self.session_recorder.ip_verified(
                            profile_id=pid,
                            session_id=session_id,
                            platform="Manual",
                            ip_info=ip_info
                        )

                        self._record_profile_alignment(
                            pid,
                            session_id,
                            driver,
                            ip_info,
                            cloak,
                            platform="Manual"
                        )
                        
                        if self.home_ip and ip_info.get("ip") == self.home_ip:
                            print(f"[Ghost {pid}] 🛑 HOME IP DETECTED IN MANUAL MODE: {ip_info.get('ip')}")

                        self._update_profile_state(
                            pid,
                            status="RUNNING",
                            ip_address=resolved_ip_string,
                            target_platform="Manual"
                        )
                    else:
                        print(f"[Ghost {pid}] 🌍 One-time manual IP verification failed. Dashboard remains Checking...")

                        self.session_recorder.ip_failed(
                            profile_id=pid,
                            session_id=session_id,
                            platform="Manual",
                            reason="Manual mode IP verification failed"
                        )

                        self._update_profile_state(
                            pid,
                            status="RUNNING",
                            target_platform="Manual"
                        )
                else:
                    self._update_profile_state(
                        pid,
                        status="RUNNING",
                        target_platform="Manual"
                    )

                # No more IP checks after this point. Just keep the thread alive until the browser closes.
                while self.is_running and self._is_profile_browser_alive(proc, debug_port=debug_port, profile_dir=profile_dir):
                    time.sleep(2)
                    
            except Exception as e:
                print(f"[Ghost {pid}] ❌ Manual Mode Error: {e}")

                self.session_recorder.error(
                    profile_id=pid,
                    session_id=session_id,
                    platform="Manual",
                    error=e,
                    event_type="MANUAL_MODE_ERROR",
                    details="Manual mode failed",
                    driver=driver
                )
            finally:
                session = self.active_sessions.get(pid, {}) if hasattr(self, "active_sessions") else {}
                if session.get("closed_by_blacklist"):
                    print(f"[Ghost {pid}] 🛑 Manual browser closed because IP is blacklisted. Keeping BLACKLISTED status visible.")
                    self._update_profile_state(
                        pid,
                        status="BLACKLISTED",
                        ip_address=session.get("blacklisted_ip_label") or cached_ip_label,
                        target_platform="IP Blacklisted"
                    )
                else:
                    print(f"[Ghost {pid}] 🛑 Manual browser closed. Returning to OFFLINE.")
                    self._update_profile_state(pid, status="OFFLINE", target_platform="None")
                close_reason = "blacklisted_ip" if session.get("closed_by_blacklist") else "manual_browser_closed"
                final_ip = session.get("blacklisted_ip_label") or cached_ip_label or ""

                self.session_recorder.end(
                    profile_id=pid,
                    session_id=session_id,
                    final_ip=final_ip,
                    status="BLACKLISTED" if session.get("closed_by_blacklist") else "ENDED",
                    close_reason=close_reason,
                    platform="Manual"
                )

                if pid in self.active_sessions:
                    self.active_sessions.pop(pid, None)
                self._release_browser_layout(pid)
            return 

        # ==========================================
        # 🤖 MODE 2: FULL AUTOMATION 
        # ==========================================
        if not self.is_running: return

        print(f"[Ghost {pid}] 🚀 Launching Comet for Automation...")

        debug_port = 9300 + int(pid)
        profile_dir = os.path.join(os.getcwd(), f"comet_profiles/profile_{pid}")
        os.makedirs(profile_dir, exist_ok=True)
        self.active_sessions[pid]["debug_port"] = debug_port
        self.active_sessions[pid]["profile_dir"] = profile_dir

        self._prepare_profile_for_clean_boot(pid, profile_dir)
        cloak = self._profile_hardware_cloak(profile)
        window_layout = self._allocate_browser_layout(pid)
        self.active_sessions[pid]["window_layout"] = window_layout

        args = [
            self.comet_path,
            f"--user-data-dir={profile_dir}",
            f"--remote-debugging-port={debug_port}",
            f"--load-extension={self.vpn_path}",
            f"--user-agent={cloak['user_agent']}",
            f"--accept-lang={cloak.get('accept_language') or cloak['language']}",
            *self._browser_window_args(window_layout),
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-fre",
            "--disable-sync",
            "--disable-infobars",
            "--disable-search-engine-choice-screen",
            "--disable-session-crashed-bubble",
            "--hide-crash-restore-bubble",
            "--ignore-certificate-errors"
        ]
        
        try:
            proc = subprocess.Popen(args, creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception:
            self._release_browser_layout(pid)
            raise

        self.active_sessions[pid]['proc'] = proc
        self._schedule_browser_window_layout(
            pid,
            proc,
            window_layout,
            debug_port=debug_port,
            profile_dir=profile_dir,
        )

        self.session_recorder.browser_launched(
            profile_id=pid,
            session_id=session_id,
            platform="Pending",
            proc=proc,
            debug_port=debug_port,
            profile_dir=profile_dir
        )
        
        # Instantly update dashboard to STARTING
        self._update_profile_state(pid, status="STARTING", target_platform="Launching")
        time.sleep(5)

        try:
            driver = self._attach_to_debugger(debug_port)

            if driver is None:
                raise Exception(f"Could not attach Selenium to automation browser on port {debug_port}")

            self.active_sessions[pid]['driver'] = driver
            self.active_sessions[pid]['current_target'] = "Launching"
            self._apply_browser_window_layout(
                pid,
                proc,
                window_layout,
                debug_port=debug_port,
                profile_dir=profile_dir,
                quiet=True,
            )
            
            time.sleep(2)
            cloak = self._apply_device_cloak_to_driver(driver, cloak, pid=pid)
            
            self.session_recorder.selenium_attached(
                profile_id=pid,
                session_id=session_id,
                platform="Pending",
                driver=driver,
                debug_port=debug_port
            )
            
            # One-time IP verification only. No background live IP tracker.

            # --- THE STARTUP TAB ASSASSIN ---
            print(f"[Ghost {pid}] ⏳ Waiting 4s for ProtonVPN onboarding tab to spawn...")
            time.sleep(4) 
            
            main_tab = driver.current_window_handle
            for handle in driver.window_handles:
                if handle != main_tab:
                    try:
                        driver.switch_to.window(handle)
                        driver.close()
                    except: pass
            
            try: driver.switch_to.window(main_tab)
            except: pass

            # --- 4.5 SESSION-ONLY IP VERIFICATION ---
            print(f"[Ghost {pid}] 🕵️ Checking profile IP for active session...")

            self.session_recorder.ip_checking(
                profile_id=pid,
                session_id=session_id,
                platform="Pending"
            )
            
            self._start_silent_alert_assassin(pid, driver, duration=8.0)

            current_ip = ""
            current_ip_label = "IP not detected"
            ip_info = None

            ip_info = self._resolve_live_ip_with_retries(pid, driver, first_delay=8, retries=6, delay=5)

            if ip_info and ip_info.get("ip"):
                current_ip = str(ip_info["ip"]).strip()
                current_ip_label = str(ip_info.get("label") or current_ip).strip()
                print(f"[Ghost {pid}] 🌍 Detected live session IP: {current_ip_label}")

                is_blacklisted, blacklist_reason = self._is_ip_blacklisted(ip_info)
                if is_blacklisted:
                    self.session_recorder.blacklisted_ip_blocked(
                        profile_id=pid,
                        session_id=session_id,
                        platform="Pending",
                        ip_info=ip_info,
                        reason=blacklist_reason
                    )

                    self._shutdown_for_blacklisted_ip(
                        pid,
                        driver,
                        proc,
                        ip_info,
                        target_platform="IP Blacklisted",
                        reason=blacklist_reason
                    )
                    return

                is_duplicate, duplicate_reason = self._is_duplicate_active_ip(pid, ip_info)
                if is_duplicate:
                    self._shutdown_for_duplicate_ip(
                        pid,
                        driver,
                        proc,
                        ip_info,
                        duplicate_reason
                    )
                    return

                if self.home_ip and current_ip == self.home_ip:
                    print(f"[Ghost {pid}] 🛑 HOME IP DETECTED: {current_ip}")

                    self.session_recorder.home_ip_blocked(
                        profile_id=pid,
                        session_id=session_id,
                        platform="Pending",
                        ip_info=ip_info
                    )

                    self.session_recorder.end(
                        profile_id=pid,
                        session_id=session_id,
                        final_ip=current_ip_label,
                        status="BLOCKED",
                        close_reason="Home IP detected",
                        platform="Pending"
                    )

                    self._update_profile_state(pid, status="OFFLINE", ip_address=current_ip_label, target_platform="Failed")
                    try: driver.quit()
                    except: pass
                    try: proc.terminate()
                    except: pass
                    if pid in self.active_sessions: self.active_sessions.pop(pid)
                    return

                # IP passed. Update dashboard with live IP/location.
                print(f"[Ghost {pid}] ✅ Session IP verified: {current_ip_label}")

                self.session_recorder.ip_verified(
                    profile_id=pid,
                    session_id=session_id,
                    platform="Pending",
                    ip_info=ip_info
                )

                # --- ALIGNMENT CHECK & FIX ---
                print(f"[Ghost {pid}] 🔍 Checking timezone/language alignment...")
                alignment_passed = False
                geo_data = None
                
                try:
                    from engine.ip_geolocation import IPGeolocationQuery
                    from engine.browser_alignment_fixer import BrowserAlignmentFixer
                    from engine.alignment_verifier import AlignmentVerifier
                    
                    # Query IP geolocation
                    geo_query = IPGeolocationQuery(pid)
                    geo_data = geo_query.query_ip(current_ip)
                    
                    if geo_data:
                        print(f"[Ghost {pid}] 📊 IP Geolocation: {geo_data['country_name']} | TZ: {geo_data['timezone']} | Lang: {geo_data['language']}")
                        
                        # Apply fixes
                        fixer = BrowserAlignmentFixer(driver, pid)
                        fixer.apply_all_fixes(geo_data)
                        
                        # Refresh browser to apply fixes
                        fixer.refresh_browser()
                        
                        time.sleep(2)
                        
                        # Verify alignment after fixes
                        verifier = AlignmentVerifier(pid, self.db)
                        lang_aligned, tz_aligned, verify_data = verifier.verify_alignment(driver, geo_data)
                        
                        # Check if language AND timezone are aligned
                        if lang_aligned and tz_aligned:
                            print(f"[Ghost {pid}] ✅ ALIGNMENT PASSED: Language and Timezone match IP")
                            alignment_passed = True
                        else:
                            print(f"[Ghost {pid}] ❌ ALIGNMENT FAILED: Language={lang_aligned}, Timezone={tz_aligned}")
                            alignment_passed = False
                    else:
                        print(f"[Ghost {pid}] ⚠️ Could not query IP geolocation")
                        # Continue anyway - IP is verified, just can't check alignment
                        alignment_passed = True
                
                except Exception as e:
                    print(f"[Ghost {pid}] ⚠️ Alignment check error: {e}")
                    # Continue on error - don't let it block automation
                    alignment_passed = True
                
                # If alignment failed, close and retry
                if not alignment_passed:
                    print(f"[Ghost {pid}] 🛑 Alignment failed. Closing browser and retrying with next IP rotation...")
                    
                    self.session_recorder.event(
                        profile_id=pid,
                        session_id=session_id,
                        platform="Pending",
                        event_type="ALIGNMENT_FAILED",
                        details=f"Timezone/Language mismatch after fixes. IP: {current_ip}"
                    )
                    
                    self._update_profile_state(pid, status="RETRYING", ip_address=current_ip_label, target_platform="Misaligned")
                    
                    try:
                        driver.quit()
                    except:
                        pass
                    try:
                        proc.terminate()
                    except:
                        pass
                    
                    time.sleep(2)
                    
                    # Restart profile with next VPN rotation
                    print(f"[Ghost {pid}] 🔄 Restarting profile for next IP rotation...")
                    self.session_recorder.end(
                        profile_id=pid,
                        session_id=session_id,
                        final_ip=current_ip_label,
                        status="RETRYING",
                        close_reason="Timezone/Language misalignment after fixes",
                        platform="Pending"
                    )
                    
                    if pid in self.active_sessions:
                        self.active_sessions.pop(pid, None)
                    self._release_browser_layout(pid)
                    
                    # Restart the profile thread for next IP
                    time.sleep(3)
                    self._independent_ghost_thread(profile, platforms, ready_event)
                    return

                self._update_profile_state(pid, status="RUNNING", ip_address=current_ip_label, target_platform="Verified")
            else:
                print(f"[Ghost {pid}] ⚠️ Browser public IP was not detected. No home/blacklisted IP was confirmed, so the browser will stay open.")
                self.session_recorder.ip_failed(
                    profile_id=pid,
                    session_id=session_id,
                    platform="Pending",
                    reason="Browser public IP was not detected; continuing because no home/blacklisted IP was confirmed."
                )
                self._update_profile_state(pid, status="RUNNING", ip_address=current_ip_label, target_platform="IP Unknown")

            # --- 5. AUTONOMOUS PLATFORM ROUTING ---
            target = random.choice(platforms).lower()
            target_label = target.upper()
            self.active_sessions[pid]['current_target'] = target_label

            self.session_recorder.platform_selected(
                profile_id=pid,
                session_id=session_id,
                platform=target,
                active_platforms=platforms
            )

            print(f"[Ghost {pid}] 🎯 Engaging target independently: {target_label}")
            
            # Instantly update dashboard to the targeted platform (e.g. YOUTUBE)
            self._update_profile_state(pid, status="RUNNING", ip_address=current_ip_label, target_platform=target_label)
            
            self._start_silent_alert_assassin(pid, driver, duration=8.0)
            signal_queue_ready("Browser secured and routed")

            runner_result = self._run_platform_runner(
                driver=driver,
                pid=pid,
                target=target,
                session_id=self.active_sessions.get(pid, {}).get("session_id", "")
            )

            print(f"[Ghost {pid}] 🧭 Platform runner result: {runner_result}")
            
            # --- 6. FINAL TAB PURGE (JAVASCRIPT ASSASSIN) ---
            print(f"[Ghost {pid}] 🧹 Executing final JS Tab Purge...")
            try:
                time.sleep(5)
                safe_tab = driver.current_window_handle
                for h in driver.window_handles:
                    try:
                        driver.switch_to.window(h)
                        url = driver.current_url.lower()
                        if "youtube.com" in url or "twitch.tv" in url or "spotify" in url or "deezer.com" in url:
                            safe_tab = h
                            break
                    except: pass

                all_tabs = driver.window_handles
                for h in all_tabs:
                    if h != safe_tab:
                        try:
                            driver.switch_to.window(h)
                            driver.execute_script("window.onbeforeunload = null;")
                            driver.execute_script("window.close();")
                            time.sleep(0.5)
                        except Exception: pass 

                try: driver.switch_to.window(safe_tab)
                except: pass
            except Exception as e:
                print(f"[Ghost {pid}] ⚠️ Final JS purge failed: {e}")

            signal_queue_ready("Infiltration complete")

            # --- ALIVE MONITOR ---
            print(f"[Ghost {pid}] 🟢 Browser remains open. IP verification already completed once. No further IP checks will run.")

            # No more IP checks after this point. Just keep the thread alive until the browser closes.
            while self.is_running and self._is_profile_browser_alive(proc, debug_port=debug_port, profile_dir=profile_dir):
                time.sleep(2)

        except Exception as e:
            print(f"[Ghost {pid}] ❌ Error: {e}")

            self.session_recorder.error(
                profile_id=pid,
                session_id=session_id,
                platform=self.active_sessions.get(pid, {}).get("current_target", "Unknown"),
                error=e,
                event_type="AUTOMATION_THREAD_ERROR",
                details="Automation thread crashed"
            )

        finally:
            print(f"[Ghost {pid}] 👻 Reached the end of the thread.")
            signal_queue_ready("Thread cleanup reached")
                
            session = self.active_sessions.get(pid, {})
            proc_obj = session.get("proc")
            browser_alive = self._is_profile_browser_alive(
                proc_obj,
                debug_port=session.get("debug_port"),
                profile_dir=session.get("profile_dir"),
            ) if self.is_running else False

            if session.get("closed_by_blacklist"):
                self.session_recorder.end(
                    profile_id=pid,
                    session_id=session.get("session_id") or session_id,
                    final_ip=session.get("blacklisted_ip_label") or "",
                    status="BLACKLISTED",
                    close_reason=session.get("blacklist_reason") or "Blacklisted IP",
                    platform=session.get("current_target") or "IP Blacklisted"
                )

                self._update_profile_state(
                    pid,
                    status="BLACKLISTED",
                    ip_address=session.get("blacklisted_ip_label") or "",
                    target_platform="IP Blacklisted"
                )
                if pid in self.active_sessions:
                    self.active_sessions.pop(pid, None)
                self._release_browser_layout(pid)

            elif session.get("closed_by_duplicate_ip"):
                self.session_recorder.end(
                    profile_id=pid,
                    session_id=session.get("session_id") or session_id,
                    final_ip=session.get("duplicate_ip_label") or "",
                    status="BLOCKED",
                    close_reason=session.get("duplicate_ip_reason") or "Duplicate active IP",
                    platform="Duplicate IP"
                )

                self._update_profile_state(
                    pid,
                    status="OFFLINE",
                    ip_address=session.get("duplicate_ip_label") or "",
                    target_platform="Duplicate IP"
                )
                if pid in self.active_sessions:
                    self.active_sessions.pop(pid, None)
                self._release_browser_layout(pid)

            elif session.get("closed_by_stop_all"):
                if not session.get("stop_all_end_recorded"):
                    self.session_recorder.end(
                        profile_id=pid,
                        session_id=session.get("session_id") or session_id,
                        status="STOPPED",
                        close_reason=session.get("stop_all_close_reason") or "Stop All pressed",
                        platform=session.get("current_target") or "Unknown"
                    )

                self._update_profile_state(pid, status="OFFLINE", target_platform="None")
                if pid in self.active_sessions:
                    self.active_sessions.pop(pid, None)
                self._release_browser_layout(pid)

            # Only mark OFFLINE if the Windows process actually closed, or Stop All was pressed
            elif (not browser_alive) or (not self.is_running):
                self.session_recorder.end(
                    profile_id=pid,
                    session_id=session.get("session_id") or session_id,
                    final_ip=session.get("blacklisted_ip_label") or "",
                    status="ENDED" if self.is_running else "STOPPED",
                    close_reason="browser_closed" if self.is_running else "stop_all_pressed",
                    platform=session.get("current_target") or "Unknown"
                )

                self._update_profile_state(pid, status="OFFLINE", target_platform="None")
                if pid in self.active_sessions:
                    self.active_sessions.pop(pid, None)
                self._release_browser_layout(pid)
            else:
                self.session_recorder.event(
                    profile_id=pid,
                    session_id=session.get("session_id") or session_id,
                    platform=session.get("current_target") or "Unknown",
                    event_type="THREAD_EXITED_BUT_BROWSER_STILL_RUNNING",
                    details="Thread ended, but browser process still appears active."
                )

                self._update_profile_state(pid, status="RUNNING")

    def execute_fleet(self, platforms, specific_ids=None, instant=False):
        """
        Launch profiles.

        instant=False:
            Session mode. Uses strict sequential queue with random delays.

        instant=True:
            Manual open mode. Opens selected profile(s) immediately.
            No queue delay. No stagger delay.
        """
        if getattr(self, "random_shutdown_active", False):
            print("[Commander] START ignored: randomized STOP ALL shutdown is still running.")
            return

        self.is_running = True
        self.launch_queue_enabled = True

        if not hasattr(self, "active_threads"):
            self.active_threads = []

        all_profiles = self.db.get_all_profiles()

        if specific_ids:
            wanted_ids = {int(pid) for pid in specific_ids}
            launch_list = [p for p in all_profiles if int(p["id"]) in wanted_ids]
        else:
            launch_list = all_profiles

        if not launch_list:
            print("[Commander] No profiles available to launch.")
            return

        if instant:
            print(f"\n[Commander] ⚡ Instant manual launch for {len(launch_list)} profile(s)...")
            spawner = threading.Thread(
                target=self._instant_spawner,
                args=(launch_list, platforms),
                daemon=True
            )
            spawner.start()
            return

        # Session mode keeps the delay/random queue behavior.
        random.shuffle(launch_list)

        spawner = threading.Thread(
            target=self._sequential_spawner,
            args=(launch_list, platforms),
            daemon=True
        )
        spawner.start()
    
    def _instant_spawner(self, profiles, platforms):
        """
        Manual open launcher.
        Opens selected profiles immediately without the session queue delay.
        """
        mode = "Manual" if not platforms else "Automation"
        print(f"[Commander] ⚡ Instant {mode} launch started.")

        for profile in profiles:
            if not self._launches_allowed():
                print("[Commander] Instant launch aborted.")
                break

            pid = profile["id"]
            print(f"[Commander] ⚡ Opening Ghost {pid} immediately...")

            t = threading.Thread(
                target=self._independent_ghost_thread,
                args=(profile, platforms, None),
                daemon=True
            )
            t.start()
            self.active_threads.append(t)

        print("[Commander] ⚡ Instant launch dispatch complete.")
        
    def _sequential_spawner(self, profiles, platforms):
        """The Master Queue: Waits random time, launches Ghost, waits for success, repeats."""
        print(f"\n[Commander] 🚀 Initiating Strict Sequential Queue for {len(profiles)} profile(s)...")
        
        for profile in profiles:
            if not self._launches_allowed():
                print("[Commander] 🛑 Launch queue aborted.")
                break
                
            pid = profile['id']
            
            # Keep launches moving while still staggering browser startup.
            delay = random.randint(5, 15)
            print(f"[Commander] ⏳ Queueing Ghost {pid}. Waiting {delay} seconds...")
            
            # Sleep in 1-second chunks so your STOP ALL button still works instantly
            for _ in range(delay):
                if not self._launches_allowed(): return
                time.sleep(1)
                
            if not self._launches_allowed(): return
            
            # 2. CREATE THE GREEN LIGHT SIGNAL FLARE
            setup_complete = threading.Event()
            
            # 3. DEPLOY THE GHOST
            print(f"[Commander] 🟢 Deploying Ghost {pid}...")
            t = threading.Thread(target=self._independent_ghost_thread, args=(profile, platforms, setup_complete))
            t.daemon = True
            t.start()
            self.active_threads.append(t)
            
            # 4. WAIT FOR THE GHOST TO FINISH IP CHECK & ROUTING
            print(f"[Commander] 📡 Waiting for Ghost {pid} to secure the network...")
            # We give it a 5-minute timeout. If a browser completely freezes, 
            # this prevents the entire queue from being stuck forever.
            setup_deadline = time.time() + 300
            while self._launches_allowed() and not setup_complete.is_set() and time.time() < setup_deadline:
                setup_complete.wait(timeout=1)
            
        print("\n[Commander] ✅ All profiles deployed successfully.")

    def _close_stop_all_session(self, pid, session, close_reason="Stop All pressed"):
        """Close one active profile session and leave final cleanup to its worker thread."""
        try:
            pid = int(pid)
        except Exception:
            return False

        live_session = self.active_sessions.get(pid, {}) if hasattr(self, "active_sessions") else {}
        if live_session:
            live_session["closed_by_stop_all"] = True
            live_session["stop_all_close_reason"] = close_reason
            self.active_sessions[pid] = live_session
            merged = dict(session or {})
            merged.update(live_session)
            session = merged
        else:
            session = dict(session or {})
            session["closed_by_stop_all"] = True
            session["stop_all_close_reason"] = close_reason

        try:
            self.session_recorder.event(
                profile_id=pid,
                session_id=session.get("session_id", ""),
                platform=session.get("current_target", "Unknown"),
                event_type="STOP_ALL_PROFILE_CLOSING",
                details=close_reason
            )
        except Exception:
            pass

        try:
            driver = session.get("driver")
            if driver:
                driver.quit()
        except Exception:
            pass

        try:
            proc = session.get("proc")
            if proc:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            if pid in self.active_sessions:
                self.active_sessions[pid]["stop_all_end_recorded"] = True
            self.session_recorder.end(
                profile_id=pid,
                session_id=session.get("session_id", ""),
                status="STOPPED",
                close_reason=close_reason,
                platform=session.get("current_target", "Unknown")
            )
        except Exception:
            if pid in self.active_sessions:
                self.active_sessions[pid]["stop_all_end_recorded"] = False
            pass

        self._update_profile_state(pid, status="OFFLINE", target_platform="None")
        return True

    def _randomized_stop_all_worker(self, scheduled_sessions, min_delay, max_delay, on_complete=None):
        rng = random.SystemRandom()
        sessions = list(scheduled_sessions or [])
        original_order = [pid for pid, _ in sessions]
        rng.shuffle(sessions)
        if len(sessions) > 1 and [pid for pid, _ in sessions] == original_order:
            sessions = sessions[1:] + sessions[:1]
        total = len(sessions)

        print(
            f"[Commander] Random STOP ALL schedule started: "
            f"{total} profile(s), {min_delay}-{max_delay}s between closes."
        )

        for index, (pid, session_snapshot) in enumerate(sessions, start=1):
            if index > 1:
                delay = rng.randint(int(min_delay), int(max_delay))
                print(f"[Commander] STOP ALL waiting {delay}s before closing profile {pid} ({index}/{total}).")
                for _ in range(delay):
                    time.sleep(1)

            live_session = self.active_sessions.get(pid, {}) if hasattr(self, "active_sessions") else {}
            session = dict(session_snapshot or {})
            session.update(live_session)

            if not session:
                print(f"[Commander] STOP ALL skipped Profile {pid}; session already ended.")
                continue

            close_reason = f"Stop All pressed; randomized close {index} of {total}"
            print(f"[Commander] STOP ALL closing Profile {pid} ({index}/{total}).")
            self._close_stop_all_session(pid, session, close_reason=close_reason)

        self.random_shutdown_active = False
        self.is_running = False
        self._reset_browser_layouts()

        if on_complete:
            try:
                on_complete()
            except Exception as e:
                print(f"[Commander] STOP ALL completion callback failed: {e}")

        print("[Commander] Random STOP ALL shutdown complete.\n")

    def abort_fleet(self, randomized=False, min_delay=30, max_delay=180, on_complete=None):
        """Stops launches and closes active browsers."""
        self.launch_queue_enabled = False

        if not hasattr(self, 'active_sessions'):
            return {"ok": True, "scheduled": 0, "mode": "none"}

        if not randomized:
            self.is_running = False
            print("\n[Commander] 🛑 ABORT SIGNAL INITIATED. Terminating fleet immediately...")

            sessions = list(self.active_sessions.items())
            for pid, session in sessions:
                try:
                    self.session_recorder.event(
                        profile_id=pid,
                        session_id=session.get("session_id", ""),
                        platform=session.get("current_target", "Unknown"),
                        event_type="STOP_ALL_RECEIVED",
                        details="Immediate abort requested"
                    )
                except Exception:
                    pass

                self._close_stop_all_session(pid, session, close_reason="Immediate Stop All pressed")

            self.active_sessions.clear()
            self._reset_browser_layouts()

            if on_complete:
                try:
                    on_complete()
                except Exception as e:
                    print(f"[Commander] STOP ALL completion callback failed: {e}")

            print("[Commander] 💀 Fleet completely neutralized.\n")
            return {"ok": True, "scheduled": len(sessions), "mode": "immediate"}

        if self.random_shutdown_active:
            print("[Commander] Random STOP ALL is already running.")
            return {
                "ok": True,
                "scheduled": len(getattr(self, "active_sessions", {}) or {}),
                "mode": "random",
                "already_running": True,
                "min_delay": int(min_delay),
                "max_delay": int(max_delay)
            }

        sessions = list(self.active_sessions.items())
        if not sessions:
            self.is_running = False
            self._reset_browser_layouts()
            if on_complete:
                try:
                    on_complete()
                except Exception as e:
                    print(f"[Commander] STOP ALL completion callback failed: {e}")
            return {"ok": True, "scheduled": 0, "mode": "random"}

        self.random_shutdown_active = True
        min_delay = max(1, int(min_delay or 30))
        max_delay = max(min_delay, int(max_delay or 180))

        for pid, session in sessions:
            try:
                session["stop_all_pending"] = True
                session["closed_by_stop_all"] = True
                session["stop_all_close_reason"] = "Stop All pressed; randomized shutdown pending"
                self.active_sessions[pid] = session
                self.session_recorder.event(
                    profile_id=pid,
                    session_id=session.get("session_id", ""),
                    platform=session.get("current_target", "Unknown"),
                    event_type="STOP_ALL_RANDOM_SCHEDULED",
                    details=f"Randomized STOP ALL scheduled with {min_delay}-{max_delay}s between profile closes."
                )
                self._update_profile_state(pid, status="STOPPING", target_platform="Stop All")
            except Exception:
                pass

        worker = threading.Thread(
            target=self._randomized_stop_all_worker,
            args=(sessions, min_delay, max_delay, on_complete),
            daemon=True
        )
        self.random_shutdown_thread = worker
        worker.start()

        return {
            "ok": True,
            "scheduled": len(sessions),
            "mode": "random",
            "min_delay": min_delay,
            "max_delay": max_delay
        }
    
    
