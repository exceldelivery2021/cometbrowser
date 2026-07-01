"""
Page Analyzer — extracts DOM elements, ARIA tree, and visible text from
a live Selenium driver. Uses only JS injection; never navigates away.
Runs in the calling thread; no background threads spawned.
"""

import time
import base64
import os


_EXTRACT_JS = """
(function() {
    function safeText(el) {
        return (el.innerText || el.textContent || el.value || el.placeholder || el.alt || "").trim().slice(0, 120);
    }
    function safeSelector(el) {
        if (el.id) return "#" + CSS.escape(el.id);
        if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name + '"]';
        // Build nth-of-type path (max 3 levels)
        var parts = [];
        var node = el;
        for (var i = 0; i < 3 && node && node !== document.body; i++) {
            var tag = node.tagName.toLowerCase();
            var idx = 1;
            var sib = node.previousElementSibling;
            while (sib) { if (sib.tagName === node.tagName) idx++; sib = sib.previousElementSibling; }
            parts.unshift(tag + ":nth-of-type(" + idx + ")");
            node = node.parentElement;
        }
        return parts.join(" > ");
    }
    function visible(el) {
        var r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && window.getComputedStyle(el).visibility !== "hidden" && window.getComputedStyle(el).display !== "none";
    }

    var result = {
        title: document.title,
        url: window.location.href,
        buttons: [],
        links: [],
        inputs: [],
        selects: [],
        checkboxes: [],
        forms: [],
        labels: [],
        text_blocks: [],
        aria_roles: []
    };

    // Buttons
    document.querySelectorAll("button, [role=button], input[type=button], input[type=submit]").forEach(function(el) {
        if (!visible(el)) return;
        result.buttons.push({ text: safeText(el), selector: safeSelector(el), disabled: el.disabled || false, aria_label: el.getAttribute("aria-label") || "" });
    });

    // Links
    document.querySelectorAll("a[href]").forEach(function(el) {
        if (!visible(el)) return;
        result.links.push({ text: safeText(el), href: el.href || "", selector: safeSelector(el) });
    });

    // Inputs (text, email, password, search, number, tel, url)
    document.querySelectorAll("input:not([type=button]):not([type=submit]):not([type=checkbox]):not([type=radio]):not([type=hidden]), textarea").forEach(function(el) {
        if (!visible(el)) return;
        result.inputs.push({ type: el.type || "text", name: el.name || "", placeholder: el.placeholder || "", value: el.value || "", selector: safeSelector(el), label: el.getAttribute("aria-label") || el.getAttribute("aria-labelledby") || "" });
    });

    // Dropdowns
    document.querySelectorAll("select").forEach(function(el) {
        if (!visible(el)) return;
        var opts = [];
        el.querySelectorAll("option").forEach(function(o) { opts.push(o.text); });
        result.selects.push({ name: el.name || "", selector: safeSelector(el), options: opts.slice(0, 20), value: el.value || "" });
    });

    // Checkboxes / radios
    document.querySelectorAll("input[type=checkbox], input[type=radio]").forEach(function(el) {
        if (!visible(el)) return;
        result.checkboxes.push({ type: el.type, name: el.name || "", checked: el.checked, selector: safeSelector(el) });
    });

    // Forms
    document.querySelectorAll("form").forEach(function(el) {
        result.forms.push({ action: el.action || "", method: el.method || "get", id: el.id || "", selector: safeSelector(el) });
    });

    // Labels
    document.querySelectorAll("label").forEach(function(el) {
        if (!visible(el)) return;
        result.labels.push({ text: safeText(el), for_id: el.htmlFor || "" });
    });

    // Visible text blocks (headings + paragraphs)
    document.querySelectorAll("h1,h2,h3,h4,p").forEach(function(el) {
        if (!visible(el)) return;
        var t = safeText(el);
        if (t.length > 5) result.text_blocks.push({ tag: el.tagName.toLowerCase(), text: t });
    });

    // ARIA roles
    document.querySelectorAll("[role]").forEach(function(el) {
        if (!visible(el)) return;
        var role = el.getAttribute("role");
        if (role && role !== "none" && role !== "presentation") {
            result.aria_roles.push({ role: role, text: safeText(el), selector: safeSelector(el) });
        }
    });

    return result;
})();
"""


class PageAnalyzer:
    """Analyze the current page of a Selenium driver."""

    def __init__(self, driver, screenshots_dir: str = ""):
        self.driver = driver
        self.screenshots_dir = screenshots_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "screenshots"
        )
        os.makedirs(self.screenshots_dir, exist_ok=True)

    def analyze(self) -> dict:
        """
        Extract all interactive elements from the current page.
        Returns a structured dict. Never raises — errors returned in 'error' key.
        """
        try:
            data = self.driver.execute_script(_EXTRACT_JS)
            data["screenshot"] = self._take_screenshot("analyze")
            data["error"] = None
            return data
        except Exception as e:
            return {"error": str(e), "title": "", "url": "", "buttons": [], "links": [],
                    "inputs": [], "selects": [], "checkboxes": [], "forms": [],
                    "labels": [], "text_blocks": [], "aria_roles": [], "screenshot": ""}

    def _take_screenshot(self, tag: str = "") -> str:
        """Save a screenshot, return the file path (relative)."""
        try:
            ts = int(time.time())
            fname = f"wa_{tag}_{ts}.png"
            fpath = os.path.join(self.screenshots_dir, fname)
            self.driver.save_screenshot(fpath)
            return fpath
        except Exception:
            return ""

    def page_summary(self, data: dict) -> str:
        """Generate a compact text summary for the AI planner."""
        lines = [
            f"Title: {data.get('title', '')}",
            f"URL: {data.get('url', '')}",
            f"Buttons ({len(data.get('buttons', []))}): " +
                ", ".join(b['text'] or b['aria_label'] for b in data.get('buttons', [])[:10]),
            f"Links ({len(data.get('links', []))}): " +
                ", ".join(l['text'] for l in data.get('links', [])[:10]),
            f"Inputs ({len(data.get('inputs', []))}): " +
                ", ".join(i.get('placeholder') or i.get('name') or i.get('type','') for i in data.get('inputs', [])[:8]),
            f"Dropdowns ({len(data.get('selects', []))}): " +
                ", ".join(s.get('name', '') for s in data.get('selects', [])[:5]),
        ]
        return "\n".join(lines)
