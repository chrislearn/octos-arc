"""Task-neutral scheduling and diagnostics; no model or benchmark-specific policy."""
from __future__ import annotations

import statistics
import os
import re


def generation_tokens(nodes: list[dict], spec_chars: int) -> int:
    """Conservative planning estimate, not a tokenizer or a provider guarantee.

    Reserve shared wiring plus feature implementation and specification detail.
    Source context size alone says nothing about how much NEW code will fit.
    """
    details = sum(len(str(node.get("description", ""))) for node in nodes)
    return 3500 + 3500 * len(nodes) + (details + 3) // 4 + (spec_chars + 7) // 8


def phase_for_label(label: str) -> str:
    label = label.lower()
    if label in {'basic independent review', 'basic entry contract completion'}:
        return 'design'
    if label == 'business exhausted retention decision':
        return 'verify'
    return ("repair" if any(word in label for word in ("repair", "rewrite", "recovery")) else
            "verify" if "final check" in label else "design" if "design" in label else "implement")


def reasoning_for_phase(label: str, base: str, env=None) -> str:
    """Generation defaults off; repairs stay on across every execution path."""
    env = os.environ if env is None else env
    phase = phase_for_label(label)
    if phase == 'repair':
        requested = env.get('OCTOS_ARC_REPAIR_REASONING', base)
        return requested if requested in {'low', 'medium', 'high'} else 'medium'
    if phase == 'implement' and env.get('OCTOS_ARC_IMPLEMENT_REASONING_ALL', '1') == '1':
        requested = env.get('OCTOS_ARC_IMPLEMENT_REASONING') or 'none'
        if requested in {'none', 'off', 'disabled', 'low', 'medium', 'high'}:
            return requested
    return base


def is_test_infrastructure_error(error: str) -> bool:
    """An unfinished harness measurement is not evidence of broken app startup."""
    return bool(re.search(r'(?i)playwright|test (?:load|suite|runner)|acceptance time budget|'
                          r'no .*cases|suite integrity|suite origin|generated test load|'
                          r'incomplete .*verdict', str(error or '')))


def startup_failure_summary(summary) -> bool:
    if not summary.error or summary.killed or summary.load_errors:
        return False
    return (summary.error_kind in {'build_start', 'application_runtime'}
            or not summary.error_kind and not is_test_infrastructure_error(summary.error))


def _measurement_case_budgets(tests_dir, specs, timeout_ms):
    for rel in specs:
        try:
            source = (tests_dir / rel).read_text(encoding='utf8')
        except (OSError, TypeError, AttributeError):
            source = ''
        cases = max(1, len(re.findall(r'\btest\s*(?:\.\s*(?:only|skip|fixme))?\s*\(\s*[\'"`]', source)))
        overrides = [int(s.replace('_', '')) for s in re.findall(
            r'(?:setTimeout\s*\(|timeout\s*:)\s*([\d_]+)', source)]
        yield cases, max([timeout_ms, *overrides]) / 1000


def measurement_seconds(tests_dir, specs, timeout_ms=10000, workers=1) -> float:
    """Budget by case declarations and explicit spec timeout, never file count alone.

    This conservative ceiling sizes runner timeouts and explicit hard caps.
    Scheduling uses measurement_forecast_seconds or compatible measured runs;
    the actual runner roster remains the authority for identities and verdicts.
    """
    total = sum(cases * seconds for cases, seconds in
                _measurement_case_budgets(tests_dir, specs, timeout_ms))
    return 60 + 1.2 * total / max(1, workers)


def measurement_forecast_seconds(tests_dir, specs, timeout_ms=10000, workers=1) -> float:
    """Cold-start admission estimate, separate from the runner's hard timeout.

    A declared 60s test timeout is not an expected 60s duration. Until a complete
    compatible measurement exists, allow 10s per case plus 50% headroom and 60s
    startup. This grants repair opportunities; only an actual complete run can
    certify the result. The runner still uses measurement_seconds and the hard
    node/run deadlines, so an underestimated forecast cannot produce a pass.
    """
    total = sum(cases * min(seconds, 10.0) for cases, seconds in
                _measurement_case_budgets(tests_dir, specs, timeout_ms))
    return 60 + 1.5 * total / max(1, workers)


def repair_seconds(samples: list[float], minimum: float) -> float:
    """Recent successful turns of the SAME execution mode, not every model call."""
    recent = [x for x in samples[-12:] if x > 0]
    return max(minimum, statistics.median(recent) * 1.1) if recent else minimum


def node_seconds(remaining: float, jobs_left: int, cap: float, *, phase_budget: float,
                 total_jobs: int, completed: int, reserve: float = 0,
                 burst_cap: float | None = None) -> float:
    """Spend half of already banked savings, never borrow from future jobs.

    The phase starts AFTER generation for whole-app repair. Explicit user caps
    remain hard limits; the default may use earned surplus up to burst_cap.
    """
    usable = max(0.0, remaining - reserve)
    share = usable / max(1, jobs_left)
    budget = max(0.0, phase_budget - reserve)
    spent = max(0.0, phase_budget - remaining)
    earned = max(0.0, budget * completed / max(1, total_jobs) - spent)
    ceiling = cap if burst_cap is None else max(cap, burst_cap)
    return max(0.0, min(usable, ceiling, min(cap, max(240, share)) + earned / 2))
