"""
Ollama Client — optional local AI suggestions via localhost:11434.
If Ollama is not running, every call returns a graceful fallback.
Never raises; never blocks the main thread longer than timeout_sec.
"""

import json
import urllib.request
import urllib.error

OLLAMA_BASE = "http://localhost:11434"
PREFERRED_MODELS = ["qwen2.5-coder:32b", "qwen2.5-coder:7b", "llama3", "mistral", "llava"]


def _post(path: str, payload: dict, timeout: int = 20) -> dict:
    url = f"{OLLAMA_BASE}{path}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return {}


def _get(path: str, timeout: int = 5) -> dict:
    url = f"{OLLAMA_BASE}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return {}


def is_available() -> bool:
    try:
        data = _get("/api/tags", timeout=3)
        return bool(data)
    except Exception:
        return False


def list_models() -> list:
    data = _get("/api/tags", timeout=5)
    return [m["name"] for m in data.get("models", [])]


def best_model() -> str:
    available = list_models()
    if not available:
        return ""
    for preferred in PREFERRED_MODELS:
        for m in available:
            if m.startswith(preferred.split(":")[0]):
                return m
    return available[0]


def suggest_action(page_summary: str, task: str, model: str = "") -> dict:
    """
    Ask the local model to suggest the next browser action.
    Returns dict with keys: action, selector, reason, confidence.
    Falls back to empty dict if Ollama unavailable.
    """
    if not model:
        model = best_model()
    if not model:
        return {}

    prompt = f"""You are a browser automation assistant.

Current page summary:
{page_summary}

User task: {task}

Respond in JSON only with these keys:
- action: one of "click", "fill", "select", "scroll", "navigate", "read"
- selector: CSS selector or empty string
- target_text: visible text of the element (if any)
- reason: one sentence why
- confidence: 0.0 to 1.0

JSON response:"""

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1, "num_predict": 256},
    }

    result = _post("/api/generate", payload, timeout=30)
    raw = result.get("response", "")

    try:
        return json.loads(raw)
    except Exception:
        # Try to extract JSON substring
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end])
            except Exception:
                pass
    return {}


def vision_analyze(image_path: str, task: str = "Describe visible buttons and links") -> str:
    """
    Send a screenshot to a vision model (llava or similar).
    Returns text description or empty string.
    """
    import base64, os
    if not os.path.exists(image_path):
        return ""

    available = list_models()
    vision_model = next((m for m in available if "llava" in m or "vision" in m or "minicpm" in m), "")
    if not vision_model:
        return ""

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    payload = {
        "model": vision_model,
        "prompt": task,
        "images": [img_b64],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 512},
    }
    result = _post("/api/generate", payload, timeout=60)
    return result.get("response", "")
