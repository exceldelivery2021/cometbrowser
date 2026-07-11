"""
hermes_boot.py — the self-healing launcher for Comet Fleet.

This REPLACES the direct `python start_dashboard.py` call in the .bat file.
Instead of launching the dashboard blindly, it:

  1. Runs Hermes preflight  -> analyzes + heals known startup problems.
  2. Launches start_dashboard.py as a child process, capturing its output.
  3. If the dashboard crashes, Hermes captures the crash, diagnoses it,
     heals the cause, and RELAUNCHES automatically — up to MAX_ATTEMPTS.

That is what makes "if it crashes, reopening fixes itself" literally true:
the fix runs between the crash and the next launch, with no human in the loop.

Everything Hermes does is written to logs/hermes_log.txt and hermes_status.json
so you can see exactly what happened.
"""

import os
import sys
import subprocess
from datetime import datetime

from engine.hermes import Hermes

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DASHBOARD = os.path.join(BASE_DIR, "start_dashboard.py")

# How many times Hermes will heal-and-retry before giving up in one launch.
# Bounded so a genuinely unfixable fault can't spin forever.
MAX_ATTEMPTS = 3

# A dashboard that stays up at least this long is considered a real launch,
# not a boot-time crash. (The pywebview window normally runs until closed.)
MIN_HEALTHY_SECONDS = 20


def _run_dashboard():
    """
    Launch the dashboard and stream its output to our console while keeping a
    tail buffer for crash diagnosis. Returns (exit_code, captured_tail).
    """
    tail = []
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")

    proc = subprocess.Popen(
        [sys.executable, DASHBOARD],
        cwd=BASE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        tail.append(line)
        if len(tail) > 400:      # keep memory bounded; last ~400 lines is plenty
            tail.pop(0)

    proc.wait()
    return proc.returncode, "".join(tail)


def main():
    hermes = Hermes()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        hermes.log(f"##### Launch attempt {attempt}/{MAX_ATTEMPTS} #####")

        # Heal known problems BEFORE every attempt (idempotent, so it's cheap).
        hermes.preflight(allow_install=True, recover_crash=True)

        started = datetime.now()
        exit_code, output_tail = _run_dashboard()
        ran_seconds = (datetime.now() - started).total_seconds()

        if exit_code == 0:
            hermes.log("Dashboard exited cleanly. Done.")
            return 0

        if ran_seconds >= MIN_HEALTHY_SECONDS:
            # It launched fine and ran for a while, then exited non-zero later.
            # That's a runtime issue, not a boot fault Hermes should retry-loop.
            hermes.log(
                f"Dashboard ran {int(ran_seconds)}s then exited (code {exit_code}); "
                "treating as runtime exit, not a boot crash.",
                level="WARN",
            )
            hermes.record_crash(exit_code, output_tail)
            return exit_code

        # Boot-time crash: record it so the next preflight heals the cause.
        hermes.record_crash(exit_code, output_tail)
        hermes.log(
            f"Dashboard crashed at boot after {ran_seconds:.1f}s "
            f"(exit {exit_code}); Hermes will heal and retry.",
            level="ERROR",
        )

    hermes.log(
        f"Gave up after {MAX_ATTEMPTS} attempts. See logs/hermes_last_crash.json "
        "for the unresolved failure.",
        level="ERROR",
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
