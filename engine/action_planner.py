"""
Action Planner — decides the next browser action from page analysis + user task.
Rule-based first; Ollama AI second (if available).
Never blocks longer than 30s (Ollama timeout).
"""

import re
from engine.safety_guard import assess


_RULE_PRIORITY = [
    # (keyword in task, element type, keyword in element text, action)
    ("search",  "inputs",  "",          "fill"),
    ("login",   "inputs",  "password",  "fill"),
    ("login",   "buttons", "login|sign.?in", "click"),
    ("sign in", "buttons", "sign.?in",  "click"),
    ("sign up", "buttons", "sign.?up|register", "click"),
    ("next",    "buttons", "next|continue|proceed", "click"),
    ("submit",  "buttons", "submit|send|confirm",   "click"),
    ("close",   "buttons", "close|dismiss|x",       "click"),
    ("agree",   "buttons", "agree|accept|ok|got.?it", "click"),
    ("scroll",  "",        "",          "scroll"),
]


def _match_element(elements: list, keyword: str) -> dict:
    """Return first element whose text/label/placeholder matches keyword (case-insensitive)."""
    if not keyword:
        return elements[0] if elements else {}
    pat = re.compile(keyword, re.IGNORECASE)
    for el in elements:
        haystack = " ".join(str(v) for v in el.values())
        if pat.search(haystack):
            return el
    return elements[0] if elements else {}


def _rule_based(page_data: dict, task: str) -> dict:
    task_lower = task.lower()

    for task_kw, el_type, el_kw, action in _RULE_PRIORITY:
        if task_kw not in task_lower:
            continue
        if el_type and page_data.get(el_type):
            el = _match_element(page_data[el_type], el_kw)
            if el:
                text = el.get("text") or el.get("placeholder") or el.get("name") or ""
                return {
                    "action": action,
                    "selector": el.get("selector", ""),
                    "target_text": text,
                    "reason": f"Matched task keyword '{task_kw}' → {action} '{text}'",
                    "confidence": 0.70,
                    "source": "rule",
                }
        elif action == "scroll":
            return {
                "action": "scroll",
                "selector": "",
                "target_text": "",
                "reason": "Scroll requested",
                "confidence": 0.95,
                "source": "rule",
            }

    # Default: suggest first visible button
    buttons = page_data.get("buttons", [])
    if buttons:
        el = buttons[0]
        text = el.get("text") or el.get("aria_label") or ""
        return {
            "action": "click",
            "selector": el.get("selector", ""),
            "target_text": text,
            "reason": f"No strong match — suggesting first visible button: '{text}'",
            "confidence": 0.35,
            "source": "rule",
        }

    links = page_data.get("links", [])
    if links:
        el = links[0]
        return {
            "action": "navigate",
            "selector": el.get("selector", ""),
            "target_text": el.get("text", ""),
            "reason": f"No buttons found — suggesting first link: '{el.get('text', '')}'",
            "confidence": 0.30,
            "source": "rule",
        }

    return {
        "action": "read",
        "selector": "",
        "target_text": "",
        "reason": "No actionable elements found — read only",
        "confidence": 0.20,
        "source": "rule",
    }


def plan(page_data: dict, task: str, use_ai: bool = True, ai_model: str = "") -> dict:
    """
    Return the best next action for the given page and task.

    Returns:
        {
            action, selector, target_text, reason,
            confidence, source, safety_level,
            requires_approval, safety_reason, safety_category
        }
    """
    suggestion = {}

    if use_ai:
        try:
            from engine.ollama_client import suggest_action, best_model, is_available
            from engine.page_analyzer import PageAnalyzer
            if is_available():
                # Build page summary inline (no driver needed)
                lines = [
                    f"Title: {page_data.get('title', '')}",
                    f"URL: {page_data.get('url', '')}",
                    "Buttons: " + ", ".join(b.get("text","") for b in page_data.get("buttons",[])[:8]),
                    "Links: "   + ", ".join(l.get("text","") for l in page_data.get("links",[])[:8]),
                    "Inputs: "  + ", ".join(i.get("placeholder","") or i.get("name","") for i in page_data.get("inputs",[])[:6]),
                ]
                summary = "\n".join(lines)
                model = ai_model or best_model()
                ai_result = suggest_action(summary, task, model=model)
                if ai_result and ai_result.get("action"):
                    suggestion = {
                        "action":      ai_result.get("action", "read"),
                        "selector":    ai_result.get("selector", ""),
                        "target_text": ai_result.get("target_text", ""),
                        "reason":      ai_result.get("reason", "AI suggestion"),
                        "confidence":  float(ai_result.get("confidence", 0.5)),
                        "source":      "ai",
                    }
        except Exception:
            pass

    if not suggestion:
        suggestion = _rule_based(page_data, task)

    # Safety assessment
    safety = assess(
        action_type=suggestion.get("action", ""),
        selector=suggestion.get("selector", ""),
        text=suggestion.get("target_text", ""),
        url=page_data.get("url", ""),
    )

    suggestion["safety_level"]      = safety["safety_level"]
    suggestion["requires_approval"] = safety["requires_approval"]
    suggestion["safety_reason"]     = safety["reason"]
    suggestion["safety_category"]   = safety["category"]

    return suggestion
