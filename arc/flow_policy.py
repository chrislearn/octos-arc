"""Task-neutral scheduling and diagnostics; no model or benchmark-specific policy."""
from __future__ import annotations

import statistics


def generation_tokens(nodes: list[dict], spec_chars: int) -> int:
    """Conservative planning estimate, not a tokenizer or a provider guarantee.

    Reserve shared wiring plus feature implementation and specification detail.
    Source context size alone says nothing about how much NEW code will fit.
    """
    details = sum(len(str(node.get("description", ""))) for node in nodes)
    return 3500 + 3500 * len(nodes) + (details + 3) // 4 + (spec_chars + 7) // 8


def phase_for_label(label: str) -> str:
    label = label.lower()
    return ("repair" if any(word in label for word in ("repair", "rewrite")) else
            "verify" if "final check" in label else "design" if "design" in label else "implement")


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
