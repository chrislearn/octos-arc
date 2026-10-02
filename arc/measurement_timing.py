"""Compose scheduling estimates without reusing or inventing test verdicts."""
from __future__ import annotations

from flow_policy import measurement_forecast_seconds


def padded_seconds(seconds):
    return max(30.0, seconds * 1.25 + 15.0)


def compose_window(scopes, timings, mode, tests_dir, timeout_ms, workers):
    """Cover a new union with disjoint, fully compatible measured subscopes.

    Do not split a measurement across cases or extrapolate a fast prefix. Each
    retained sample paid for a complete run, including startup/reset overhead.
    Summing disjoint samples conservatively pays that overhead again.
    """
    groups = {}
    for row in timings:
        measured = row.get('spec_scopes', {})
        if (row.get('timing_mode') != mode or not measured or row.get('seconds', 0) <= 0
                or not all(value is not None and scopes.get(spec) == value
                           for spec, value in measured.items())):
            continue
        key = tuple(sorted(measured))
        groups.setdefault(key, []).append(row['seconds'])
    remaining = set(scopes)
    seconds = 0.0
    covered = []
    # Large measured unions preserve their actual execution cost. Never charge
    # the same spec twice when historical samples overlap.
    for specs in sorted(groups, key=lambda names: (-len(names), names)):
        if set(specs) <= remaining:
            seconds += padded_seconds(max(groups[specs][-5:]))
            remaining.difference_update(specs)
            covered.extend(specs)
    if remaining:
        seconds += measurement_forecast_seconds(tests_dir, sorted(remaining), timeout_ms, workers)
    return seconds, sorted(covered), sorted(remaining)
