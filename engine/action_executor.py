"""
Action Executor — carries out browser actions safely.
Takes before/after screenshots. Logs result. Never executes dangerous
actions unless approved=True is explicitly passed.
"""

import time
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from engine.safety_guard import assess, SAFETY_LEVELS


SCREENSHOTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "screenshots"
)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


def _screenshot(driver, tag: str) -> str:
    try:
        ts = int(time.time())
        fname = f"wa_{tag}_{ts}.png"
        fpath = os.path.join(SCREENSHOTS_DIR, fname)
        driver.save_screenshot(fpath)
        return fpath
    except Exception:
        return ""


def _find(driver, selector: str, timeout: int = 6):
    """Find element by CSS selector with timeout."""
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )
    except (TimeoutException, NoSuchElementException):
        return None


def execute(driver, action: dict, approved: bool = False) -> dict:
    """
    Execute a single browser action.

    Args:
        driver:   Selenium WebDriver
        action:   dict from action_planner.plan()
        approved: True if user explicitly approved a dangerous action

    Returns:
        {ok, action_type, selector, message, screenshot_before, screenshot_after, error}
    """
    action_type  = action.get("action", "read")
    selector     = action.get("selector", "")
    target_text  = action.get("target_text", "")
    fill_value   = action.get("fill_value", "")
    requires_approval = action.get("requires_approval", True)
    safety_level = action.get("safety_level", "caution")

    result = {
        "ok": False,
        "action_type": action_type,
        "selector": selector,
        "target_text": target_text,
        "message": "",
        "screenshot_before": "",
        "screenshot_after": "",
        "error": "",
    }

    # Block dangerous actions without approval
    if requires_approval and not approved:
        result["message"] = f"Action requires approval (safety: {safety_level}). Set approved=True to proceed."
        result["error"] = "APPROVAL_REQUIRED"
        return result

    result["screenshot_before"] = _screenshot(driver, "before")

    try:
        if action_type == "navigate":
            url = action.get("url") or action.get("target_text", "")
            if not url.startswith("http"):
                url = "https://" + url
            driver.get(url)
            time.sleep(2)
            result["message"] = f"Navigated to {url}"
            result["ok"] = True

        elif action_type == "click":
            el = _find(driver, selector)
            if el:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                time.sleep(0.3)
                el.click()
                time.sleep(1.5)
                result["message"] = f"Clicked '{target_text}' ({selector})"
                result["ok"] = True
            else:
                # Fallback: click by visible text
                els = driver.find_elements(By.XPATH, f"//*[contains(text(), '{target_text}')]")
                if els:
                    els[0].click()
                    time.sleep(1.5)
                    result["message"] = f"Clicked by text '{target_text}'"
                    result["ok"] = True
                else:
                    result["error"] = f"Element not found: {selector}"

        elif action_type == "fill":
            el = _find(driver, selector)
            if el:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                el.clear()
                el.send_keys(fill_value or target_text)
                time.sleep(0.5)
                result["message"] = f"Filled input '{selector}' with value"
                result["ok"] = True
            else:
                result["error"] = f"Input not found: {selector}"

        elif action_type == "select":
            el = _find(driver, selector)
            if el:
                sel = Select(el)
                try:
                    sel.select_by_visible_text(fill_value or target_text)
                except Exception:
                    sel.select_by_index(0)
                time.sleep(0.5)
                result["message"] = f"Selected '{fill_value or target_text}' in dropdown"
                result["ok"] = True
            else:
                result["error"] = f"Dropdown not found: {selector}"

        elif action_type == "scroll":
            amount = action.get("scroll_amount", 400)
            driver.execute_script(f"window.scrollBy(0, {amount});")
            time.sleep(0.5)
            result["message"] = f"Scrolled {amount}px"
            result["ok"] = True

        elif action_type == "key":
            key_name = action.get("key", "RETURN")
            el = _find(driver, selector) if selector else driver.find_element(By.TAG_NAME, "body")
            if el:
                key = getattr(Keys, key_name.upper(), Keys.RETURN)
                el.send_keys(key)
                time.sleep(1)
                result["message"] = f"Pressed key {key_name}"
                result["ok"] = True

        elif action_type == "read":
            result["message"] = "Read-only action — no browser interaction"
            result["ok"] = True

        else:
            result["error"] = f"Unknown action type: {action_type}"

    except Exception as e:
        result["error"] = str(e)

    result["screenshot_after"] = _screenshot(driver, "after")
    return result
