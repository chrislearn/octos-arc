#!/usr/bin/env python3
"""Attribute a run's LLM usage to requirement nodes and phases.

usage: usage_by_node.py <output_dir or llm-usage.jsonl> [--json]

Reads `.arc/llm-usage.jsonl` (one record per provider request: exact billed
tokens, cache hits, elapsed, the turn label the flow set, the prompt hash and
the prefix shared with the previous request) and prints, per node, what the
platform is charged for: requests, prompt tokens split into cache hits and
misses, completion and reasoning tokens, wall time, whether the node passed on
its first implement turn (no repair or rewrite turn followed), and how much of
each request's prompt repeated the previous one. Cache-hit *rate* is not a goal
here: a fixed block repeated in every request raises it while raising every
other column too; the columns that matter are per passed node.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PHASES = ("design", "implement", "rewrite", "repair", "checkpoint", "final", "other")


def classify(label: str) -> tuple[str, str]:
    """(node, phase) from a turn label such as 'REQ-2.1.3 repair 1/3'."""
    label = label or ""
    node = label.split(" ")[0] if label.startswith("REQ-") else "_run"
    low = label.lower()
    if "application design" in low or low.endswith(" design"):
        phase = "design"
    elif low.startswith("checkpoint"):
        phase = "checkpoint"
    elif low.startswith("full-suite") or low.startswith("final"):
        phase = "final"
    elif "rewrite" in low:
        phase = "rewrite"
    elif "repair" in low:
        phase = "repair"
    elif "implement" in low:
        phase = "implement"
    else:
        phase = "other"
    return node, phase


def _bucket() -> dict:
    return {"requests": 0, "prompt_tokens": 0, "cache_hit_tokens": 0, "cache_miss_tokens": 0,
            "completion_tokens": 0, "reasoning_tokens": 0, "elapsed_ms": 0, "prefix_shared_chars": 0, "prompt_chars": 0}


def _add(bucket: dict, rec: dict) -> None:
    prompt = int(rec.get("prompt_tokens") or 0)
    hit = int(rec.get("prompt_cache_hit_tokens") or 0)
    bucket["requests"] += 1
    bucket["prompt_tokens"] += prompt
    bucket["cache_hit_tokens"] += hit
    bucket["cache_miss_tokens"] += max(0, prompt - hit)
    bucket["completion_tokens"] += int(rec.get("completion_tokens") or 0)
    bucket["reasoning_tokens"] += int(rec.get("reasoning_tokens") or 0)
    bucket["elapsed_ms"] += int(rec.get("elapsed_ms") or 0)
    bucket["prefix_shared_chars"] += int(rec.get("prefix_shared_chars") or 0)
    bucket["prompt_chars"] += int((rec.get("request") or {}).get("user_chars") or 0)


def summarize(records: list[dict]) -> dict:
    nodes: dict[str, dict] = {}
    run: dict[str, dict] = {}
    totals = _bucket()
    for rec in records:
        node, phase = classify(rec.get("label") or "")
        _add(totals, rec)
        if node == "_run":
            _add(run.setdefault(phase, _bucket()), rec)
            continue
        entry = nodes.setdefault(node, dict(_bucket(), by_phase={}))
        _add(entry, rec)
        _add(entry["by_phase"].setdefault(phase, _bucket()), rec)
    for entry in nodes.values():
        phases = entry["by_phase"]
        entry["first_pass"] = "implement" in phases and not any(p in phases for p in ("repair", "rewrite"))
    return {"nodes": nodes, "run": run, "totals": totals}


def render(summary: dict) -> str:
    def row(name: str, b: dict, extra: str = "") -> str:
        miss = b["cache_miss_tokens"]; comp = b["completion_tokens"]; reason = b["reasoning_tokens"]
        shared = f"{100 * b['prefix_shared_chars'] / b['prompt_chars']:.0f}%" if b["prompt_chars"] else "—"
        return (f"| {name} | {b['requests']} | {b['prompt_tokens']:,} | {miss:,} | {comp:,} | {reason:,} | "
                f"{b['elapsed_ms'] / 1000:.0f}s | {shared} |{extra}")
    lines = ["| node | req | prompt | cache-miss | completion | reasoning | wall | prefix reuse | first pass |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for node, b in summary["nodes"].items():
        lines.append(row(node, b, " ✓ |" if b.get("first_pass") else " ✗ |"))
    for phase, b in summary["run"].items():
        lines.append(row(f"_{phase}", b, " |"))
    lines.append(row("TOTAL", summary["totals"], " |"))
    nodes = summary["nodes"]
    if nodes:
        passed = [n for n, b in nodes.items() if b.get("first_pass")]
        lines.append(f"\nnodes: {len(nodes)}; first pass: {len(passed)}; "
                     f"cache-miss tokens per node: {summary['totals']['cache_miss_tokens'] // len(nodes):,}; "
                     f"requests per node: {summary['totals']['requests'] / len(nodes):.1f}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__); return 2
    path = Path(argv[1])
    if path.is_dir():
        path = path / ".arc" / "llm-usage.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    summary = summarize(records)
    print(json.dumps(summary, indent=1) if "--json" in argv else render(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
