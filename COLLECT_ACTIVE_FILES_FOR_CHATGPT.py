#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
COMET FLEET HQ - ACTIVE FILES COLLECTOR

This does NOT change your project.
It creates a ZIP containing only the active code files I need to inspect next.

It avoids:
- profiles
- databases
- screenshots
- logs
- old backup versions
- installers
- browser cache folders
"""

from __future__ import annotations

import hashlib
import json
import time
import zipfile
from pathlib import Path


ROOT_FILES = [
    "start_dashboard.py",
    "coordinator_server.py",
    "mobile_worker.py",
    "device_command_worker.py",
    "sync_updates_to_main.py",
    "health_check.py",
    "browser_window_watcher.py",
    "local_config.json",
    "mobile_worker_config.json",
    "sync_client_config.json",
    "RUN_LAPTOP_DASHBOARD.bat",
    "RUN_DEVICE_COMMAND_WORKER.bat",
    "RUN_LAPTOP_MOBILE_WORKER.bat",
    "RUN_LAPTOP_SYNC.bat",
    "START_LAPTOP_ALL.bat",
    "START_DASHBOARD_MASTER.bat",
    "START_MOBILE_WORKER_MASTER.bat",
]

FOLDERS_TO_INCLUDE = [
    ("engine", {".py"}),
    ("ui", {".html", ".css", ".js"}),
]

SENSITIVE_KEYS = {
    "SYNC_TOKEN",
    "TOKEN",
    "PASSWORD",
    "SECRET",
    "API_KEY",
}


def stamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def redact_json_bytes(raw: bytes) -> bytes:
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except Exception:
        return raw

    def redact(value):
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                if str(k).upper() in SENSITIVE_KEYS or "TOKEN" in str(k).upper():
                    out[k] = "***REDACTED***"
                else:
                    out[k] = redact(v)
            return out
        if isinstance(value, list):
            return [redact(v) for v in value]
        return value

    return json.dumps(redact(data), indent=2).encode("utf-8")


def latest_manifest(project: Path) -> Path | None:
    manifest_dir = project / "_archive" / "manifests"
    if not manifest_dir.exists():
        return None
    matches = sorted(manifest_dir.glob("cleanup_manifest_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def collect_files(project: Path) -> list[Path]:
    files = []

    for name in ROOT_FILES:
        path = project / name
        if path.exists() and path.is_file():
            files.append(path)

    for folder_name, exts in FOLDERS_TO_INCLUDE:
        root = project / folder_name
        if root.exists() and root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.is_file() and path.suffix.lower() in exts:
                    files.append(path)

    manifest = latest_manifest(project)
    if manifest:
        files.append(manifest)

    # de-duplicate while preserving order
    seen = set()
    out = []
    for path in files:
        resolved = str(path.resolve()).lower()
        if resolved not in seen:
            seen.add(resolved)
            out.append(path)

    return out


def main() -> None:
    project = Path(".").resolve()
    output_dir = project / "_for_chatgpt"
    output_dir.mkdir(exist_ok=True)

    zip_path = output_dir / f"COMET_ACTIVE_FILES_FOR_CHATGPT_{stamp()}.zip"
    report_lines = []
    files = collect_files(project)

    report_lines.append("COMET FLEET HQ ACTIVE FILES REPORT")
    report_lines.append(f"Project: {project}")
    report_lines.append(f"Created: {stamp()}")
    report_lines.append(f"File count: {len(files)}")
    report_lines.append("")
    report_lines.append("Included files:")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for path in files:
            rel = path.relative_to(project).as_posix()
            raw = path.read_bytes()

            # Redact JSON configs inside the ZIP only.
            if path.suffix.lower() == ".json" and path.name in {
                "sync_client_config.json",
                "local_config.json",
                "mobile_worker_config.json",
            }:
                zip_rel = rel.replace(".json", ".redacted.json")
                z.writestr(zip_rel, redact_json_bytes(raw))
            else:
                z.write(path, arcname=rel)

            report_lines.append(f"- {rel} | bytes={path.stat().st_size} | sha256={sha256_file(path)}")

        report_text = "\n".join(report_lines) + "\n"
        z.writestr("PROJECT_FILE_REPORT.txt", report_text)

    print("")
    print("=" * 70)
    print("COMET ACTIVE FILES COLLECTOR")
    print("=" * 70)
    print("DONE. I created this ZIP:")
    print(zip_path)
    print("")
    print("Upload that ZIP to ChatGPT next.")
    print("")
    input("Press Enter to close...")


if __name__ == "__main__":
    main()
