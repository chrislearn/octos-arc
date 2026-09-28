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
        owner = "app" if confirmed and kind in {"pageerror", "blank_page", "server_crash", "undefined_binding", "temporal_dead_zone", "runtime_fallback"} else "unknown"
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
                   dynamic_patterns=None, env=None, timeout: int = 35) -> dict:
    """Independent fresh-browser reproduction; never executes business spec code."""
    destination.mkdir(parents=True, exist_ok=True)
    config = {"module": str(root / "node_modules" / "@playwright" / "test"),
              "baseURL": base_url, "paths": paths or ["/"],
              "dynamicPatterns": dynamic_patterns or [], "destination": str(destination),
              "budgetMs": max(1, timeout - 2) * 1000}
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


def frontend_binding_health(frontend: Path, *, timeout: int = 20) -> dict:
    """Flag unresolved references and certain lexical reads before initialization."""
    try:
        completed = subprocess.run(
            ['node', str(Path(__file__).with_name('undefined_bindings.cjs')), str(frontend.resolve())],
            text=True, capture_output=True, timeout=timeout, check=False)
        report = json.loads(completed.stdout)
        if completed.returncode or report.get('status') not in {'passed', 'failed', 'unknown'}:
            raise ValueError('invalid binding-check response')
        return report
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return {'status': 'unknown', 'reason': str(exc)[:300]}


def binding_failure_observation(report: dict) -> dict | None:
    """Keep lexical failures visible in a bounded startup repair message."""
    if report.get('status') != 'failed':
        return None
    names = report.get('names')
    if not isinstance(names, list):
        groups: dict[tuple[str, str], list[dict]] = {}
        for row in report.get('diagnostics', []):
            if not isinstance(row, dict) or not isinstance(row.get('name'), str):
                continue
            groups.setdefault((row.get('kind', 'undefined_binding'), row['name']), []).append(row)
        names = [{'name': name, 'kind': kind, 'count': len(sites),
                  'file': sites[0].get('file', '?'), 'line': sites[0].get('line', '?'),
                  'declaration_line': sites[0].get('declaration_line', '?')}
                 for (kind, name), sites in groups.items()]
    if not names:
        return None
    entries = [
        (f"{row['name']} x{row['count']} ({row['file']}:{row['line']}; "
         f"declared at line {row.get('declaration_line', '?')})"
         if row.get('kind') == 'temporal_dead_zone' else
         f"{row['name']} x{row['count']} ({row['file']}:{row['line']})")
        for row in sorted(names, key=lambda item: (item.get('kind') != 'temporal_dead_zone',
                                                   -item['count'], item['name']))]
    details = ', '.join(entries)
    if len(details) > 800:
        kept = []
        for entry in entries:
            if len(', '.join(kept + [entry])) > 760:
                break
            kept.append(entry)
        details = ', '.join(kept) + f"; {len(entries) - len(kept)} more names in health.json"
    total = report.get('total', sum(row['count'] for row in names))
    has_tdz = any(row.get('kind') == 'temporal_dead_zone' for row in names)
    label = 'Frontend lexical failures' if has_tdz else 'Undefined frontend bindings'
    return {'kind': 'temporal_dead_zone' if has_tdz else 'undefined_binding', 'confirmed': True,
            'message': f"{label} ({total} references): {details}",
            'evidence': report}


def browser_failure_summary(report: dict, *, limit: int = 1100) -> str:
    """Put concrete causes before repeated fallbacks without altering raw evidence."""
    status = str(report.get('status', 'unknown'))
    rows = report.get('observations', [])
    priority = {'temporal_dead_zone': 0, 'undefined_binding': 1,
                'pageerror': 2, 'server_crash': 3, 'blank_page': 4,
                'runtime_fallback': 5}
    ordered = sorted((row for row in rows if isinstance(row, dict)),
                     key=lambda row: priority.get(row.get('kind'), 6))
    chunks = []
    seen = set()
    for row in ordered:
        kind = str(row.get('kind', 'unknown'))
        message = str(row.get('message') or kind).strip()
        first_line = message.splitlines()[0]
        key = (kind, first_line)
        if key in seen:
            continue
        seen.add(key)
        path = str(row.get('path') or '')
        detail = f"{kind} {path}: {message[:450]}".strip()
        if len('; '.join(chunks + [detail])) > limit - 190:
            continue
        chunks.append(detail)
    if not chunks:
        chunks.append(str(report.get('reason') or 'no actionable observation'))
    evidence = str(report.get('artifact_dir') or 'unavailable') + '/health.json'
    return f"Browser health {status}: {'; '.join(chunks)}; full evidence: {evidence}"
