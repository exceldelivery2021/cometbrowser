import ctypes
import os
import re
import time
import traceback

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


MUTEX_NAME = "Local\\CometFleetBrowserWindowWatcher"
WINDOWS_PER_DESKTOP = 10
COLUMNS = 5
ROWS = 2

# Prevent the watcher from writing the same "moved window" line every loop.
LOG_COOLDOWN_SECONDS = 60
LAST_LOGGED_LAYOUT = {}


def log(message):
    print(f"[BrowserWindowWatcher] {message}", flush=True)


def acquire_single_instance():
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return None
    if kernel32.GetLastError() == 183:
        log("Already running. Exiting duplicate watcher.")
        return None
    return handle


def get_primary_work_area():
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
            return (
                int(rect.left),
                int(rect.top),
                max(1, int(rect.right - rect.left)),
                max(1, int(rect.bottom - rect.top)),
            )
    except Exception:
        pass

    try:
        return (
            0,
            0,
            max(1, int(ctypes.windll.user32.GetSystemMetrics(0))),
            max(1, int(ctypes.windll.user32.GetSystemMetrics(1))),
        )
    except Exception:
        return 0, 0, 1920, 1080


def calculate_tile(slot_index):
    left, top, work_width, work_height = get_primary_work_area()
    slot_index = int(slot_index) % WINDOWS_PER_DESKTOP
    col = slot_index % COLUMNS
    row = slot_index // COLUMNS

    x = left + (work_width * col // COLUMNS)
    y = top + (work_height * row // ROWS)
    next_x = left + (work_width * (col + 1) // COLUMNS)
    next_y = top + (work_height * (row + 1) // ROWS)

    return {
        "x": int(x),
        "y": int(y),
        "width": max(100, int(next_x - x)),
        "height": max(100, int(next_y - y)),
    }


def get_or_create_desktop(desktop_number):
    if AppView is None or VirtualDesktop is None or get_virtual_desktops is None:
        return None

    try:
        desktops = list(get_virtual_desktops())
        while len(desktops) < int(desktop_number):
            VirtualDesktop.create()
            time.sleep(0.35)
            desktops = list(get_virtual_desktops())
        return desktops[int(desktop_number) - 1]
    except Exception as exc:
        log(f"Virtual desktop unavailable: {exc}")
        return None


def parse_profile_id_from_pid(pid):
    if psutil is None:
        return None

    try:
        proc = psutil.Process(int(pid))
        name = (proc.name() or "").lower()
        if name != "comet.exe":
            return None
        cmd = " ".join(proc.cmdline())
    except Exception:
        return None

    if "comet_profiles" not in cmd.lower() or "--remote-debugging-port=93" not in cmd.lower():
        return None

    match = re.search(r"profile[_/\\](\d+)", cmd, re.IGNORECASE)
    if not match:
        return None

    try:
        return int(match.group(1))
    except Exception:
        return None


def visible_comet_windows():
    if win32gui is None or win32process is None:
        return []

    windows = []

    def callback(hwnd, _):
        try:
            if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
                return

            class_name = win32gui.GetClassName(hwnd) or ""
            if "Chrome_WidgetWin" not in class_name:
                return

            title = win32gui.GetWindowText(hwnd) or ""
            if "Comet" not in title:
                return

            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            profile_id = parse_profile_id_from_pid(pid)
            if profile_id is None:
                return

            windows.append({
                "hwnd": int(hwnd),
                "pid": int(pid),
                "profile_id": int(profile_id),
                "title": title,
            })
        except Exception:
            return

    win32gui.EnumWindows(callback, None)
    return windows


def current_desktop_number(hwnd):
    if AppView is None:
        return None
    try:
        return int(AppView(hwnd=hwnd).desktop.number)
    except Exception:
        return None


def move_window(hwnd, profile_id, global_slot):
    if win32gui is None or win32con is None:
        return False

    desktop_number = 2 + (int(global_slot) // WINDOWS_PER_DESKTOP)
    slot_index = int(global_slot) % WINDOWS_PER_DESKTOP
    tile = calculate_tile(slot_index)

    desktop = get_or_create_desktop(desktop_number)
    before_desktop = current_desktop_number(hwnd)
    before_rect = win32gui.GetWindowRect(hwnd)
    needs_move = (
        before_desktop != desktop_number
        or abs(before_rect[0] - tile["x"]) > 4
        or abs(before_rect[1] - tile["y"]) > 4
        or abs((before_rect[2] - before_rect[0]) - tile["width"]) > 4
        or abs((before_rect[3] - before_rect[1]) - tile["height"]) > 4
    )

    try:
        win32gui.ShowWindow(hwnd, win32con.SW_SHOWNORMAL)
        win32gui.SetWindowPos(
            hwnd,
            None,
            tile["x"],
            tile["y"],
            tile["width"],
            tile["height"],
            win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE,
        )
    except Exception as exc:
        log(f"Profile {profile_id}: resize failed for hwnd={hwnd}: {exc}")

    moved_desktop = False
    if desktop is not None and AppView is not None:
        try:
            AppView(hwnd=hwnd).move(desktop)
            moved_desktop = True
        except Exception as exc:
            log(f"Profile {profile_id}: desktop move failed for hwnd={hwnd}: {exc}")

    after_desktop = current_desktop_number(hwnd)

    layout_key = (int(hwnd), int(profile_id))
    layout_signature = (
        int(desktop_number),
        int(slot_index),
        int(tile["x"]),
        int(tile["y"]),
        int(tile["width"]),
        int(tile["height"]),
    )
    last_signature, last_time = LAST_LOGGED_LAYOUT.get(layout_key, (None, 0))
    should_log = bool(needs_move) and (
        last_signature != layout_signature
        or (time.time() - float(last_time or 0)) >= LOG_COOLDOWN_SECONDS
    )

    if should_log:
        LAST_LOGGED_LAYOUT[layout_key] = (layout_signature, time.time())
        log(
            f"Profile {profile_id}: hwnd={hwnd} -> desktop {desktop_number}, "
            f"slot {slot_index + 1}/10 ({tile['width']}x{tile['height']} at {tile['x']},{tile['y']})"
        )

    return moved_desktop


def run():
    mutex = acquire_single_instance()
    if mutex is None:
        return

    if psutil is None or win32gui is None or AppView is None:
        log("Missing psutil/win32/pyvda support. Watcher cannot move windows.")
        return

    log("Started.")
    profile_slots = {}
    used_slots = set()

    while True:
        try:
            windows = visible_comet_windows()
            active_profiles = {item["profile_id"] for item in windows}

            for profile_id in list(profile_slots):
                if profile_id not in active_profiles:
                    used_slots.discard(profile_slots.pop(profile_id))

            for profile_id in sorted(active_profiles):
                if profile_id not in profile_slots:
                    slot = 0
                    while slot in used_slots:
                        slot += 1
                    profile_slots[profile_id] = slot
                    used_slots.add(slot)

            for item in windows:
                slot = profile_slots.get(item["profile_id"])
                if slot is not None:
                    move_window(item["hwnd"], item["profile_id"], slot)

        except Exception:
            log(traceback.format_exc())

        time.sleep(2)


if __name__ == "__main__":
    run()
