"""
Safety Guard — blocks or flags dangerous browser actions.
Runs synchronously in the calling thread; zero background work.
"""

import re

_DANGER_PATTERNS = [
    # Payments
    (r"pay|checkout|billing|credit.?card|debit|purchase|order.?now|buy.?now|complete.?order", "payment"),
    # Destructive
    (r"delete|remove|cancel.?account|close.?account|unsubscribe|deactivate", "destructive"),
    # Public posting
    (r"\btweet\b|post|publish|send.?message|submit.?comment|reply", "public_post"),
    # Auth changes
    (r"change.?password|reset.?password|update.?email|change.?email", "auth_change"),
    # File ops
    (r"upload|download|attach.?file|import.?file", "file_op"),
    # Form submit with personal data
    (r"submit|confirm|finalize|place.?order|sign.?up|register", "form_submit"),
]

_SAFE_PATTERNS = [
    r"search|find|look|next|previous|back|forward|home|menu|close|cancel|dismiss|ok|got.?it|accept.?cookies|learn.?more|read.?more|see.?more|expand|collapse|scroll|load.?more",
]

SAFETY_LEVELS = {
    "safe": 0,
    "caution": 1,
    "dangerous": 2,
}


def assess(action_type: str, selector: str, text: str, url: str = "") -> dict:
    """
    Assess the safety of a proposed action.

    Returns:
        {
            safety_level: "safe" | "caution" | "dangerous",
            requires_approval: bool,
            reason: str,
            category: str,
        }
    """
    combined = " ".join([action_type, selector, text, url]).lower()

    # Check safe patterns first — if it matches, short-circuit
    for pat in _SAFE_PATTERNS:
        if re.search(pat, combined):
            return {
                "safety_level": "safe",
                "requires_approval": False,
                "reason": "Matches safe navigation pattern",
                "category": "navigation",
            }

    # Check danger patterns
    for pat, category in _DANGER_PATTERNS:
        if re.search(pat, combined):
            level = "dangerous" if category in ("payment", "destructive", "auth_change") else "caution"
            return {
                "safety_level": level,
                "requires_approval": True,
                "reason": f"Detected '{category}' action — manual approval required",
                "category": category,
            }

    # Default: caution for anything that's a click/fill on unknown element
    if action_type in ("click", "fill", "submit"):
        return {
            "safety_level": "caution",
            "requires_approval": True,
            "reason": "Unknown action type — defaulting to require approval",
            "category": "unknown",
        }

    return {
        "safety_level": "safe",
        "requires_approval": False,
        "reason": "Read-only or navigation action",
        "category": "read",
    }
