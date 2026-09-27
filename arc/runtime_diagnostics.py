"""Runtime evidence is independent of a generated business assertion's approval."""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import time
from pathlib import Path


def diagnose(summary) -> list[dict]:
    issues = []
    for observation in getattr(summary, "runtime_observations", []):
        kind = observation.get("kind", "unknown")
        confirmed = observation.get("confirmed") is True
        owner = "app" if confirmed and kind in {"pageerror", "blank_page", "server_crash"} else "unknown"
        if kind in {"collector_error", "browser_unavailable"}:
            owner = "harness" if kind == "collector_error" else "environment"
        message = str(observation.get("message") or kind)
        issues.append({"id": hashlib.sha256((kind + message).encode()).hexdigest()[:16],
                       "owner": owner, "kind": kind,
                       "state": "confirmed" if confirmed else "suspected",
                       "impact": "runtime" if owner == "app" else "diagnostic",
                       "message": message, "evidence": observation})
    return issues


def application_failures(summary) -> list[str]:
    return [issue["message"] for issue in diagnose(summary)
            if issue["owner"] == "app" and issue["state"] == "confirmed"]


def browser_health(root: Path, base_url: str, destination: Path, *, paths=None,
                   env=None, timeout: int = 35) -> dict:
    """Independent fresh-browser reproduction; never executes business spec code."""
    destination.mkdir(parents=True, exist_ok=True)
    config = {"module": str(root / "node_modules" / "@playwright" / "test"),
              "baseURL": base_url, "paths": paths or ["/"], "destination": str(destination), "budgetMs": max(1, timeout - 2) * 1000}
    started = time.monotonic()
    try:
        process = subprocess.Popen(["node", str(Path(__file__).with_name("browser_health.cjs"))],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, env=env, start_new_session=True)
        try:
            stdout, _ = process.communicate(json.dumps(config), timeout=max(1, timeout))
        except BaseException:
            # Node timeout alone leaves its Chromium children alive. The probe
            # owns this new process group; never kill another task's browsers.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise
        report = json.loads(stdout)
        if not isinstance(report, dict) or not isinstance(report.get("observations"), list):
            raise ValueError("invalid browser health report")
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        report = {"status": "unknown", "observations": [{"kind": "browser_unavailable",
                  "confirmed": False, "message": f"browser health unavailable: {str(exc)[:400]}"}]}
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    report["artifact_dir"] = str(destination)
    (destination / "health.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report
