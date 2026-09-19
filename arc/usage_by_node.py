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
            "completion_tokens": 0, "reasoning_tokens": 0, "elapsed_ms": 0, "prefix_shared_chars": 0, "prompt_chars": 0,
            "no_usage": 0}


def _add(bucket: dict, rec: dict) -> None:
    prompt = int(rec.get("prompt_tokens") or 0)
    hit = int(rec.get("prompt_cache_hit_tokens") or 0)
    bucket["requests"] += 1
    bucket["no_usage"] += 1 if rec.get("no_usage") else 0
    bucket["prompt_tokens"] += prompt
    bucket["cache_hit_tokens"] += hit
    bucket["cache_miss_tokens"] += max(0, prompt - hit)
    bucket["completion_tokens"] += int(rec.get("completion_tokens") or 0)
    bucket["reasoning_tokens"] += int(rec.get("reasoning_tokens") or 0)
    bucket["elapsed_ms"] += int(rec.get("elapsed_ms") or 0)
    bucket["prefix_shared_chars"] += int(rec.get("prefix_shared_chars") or 0)
    bucket["prompt_chars"] += int((rec.get("request") or {}).get("user_chars") or 0)


def load_records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def node_states(output_dir: Path) -> dict[str, str]:
    """Final per-node verdicts from .arc/traceability/node_states.json ({node: 'PASSED'|'FAILED'|...})."""
    path = output_dir / ".arc" / "traceability" / "node_states.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(k): str(v.get("state")) for k, v in data.items() if isinstance(v, dict) and v.get("state")}


def summarize(records: list[dict], states: dict[str, str] | None = None) -> dict:
    """`no_node_repair`: the node's own turns were implement only (checkpoint and
    full-suite repairs are run-level and do not count). `first_pass`: that, and the
    node's final verdict is PASSED -- None without verdicts, because a node that
    never got a repair may simply have failed."""
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
    for node, entry in nodes.items():
        phases = entry["by_phase"]
        entry["no_node_repair"] = "implement" in phases and not any(p in phases for p in ("repair", "rewrite"))
        entry["first_pass"] = (entry["no_node_repair"] and states.get(node) == "PASSED") if states else None
    return {"nodes": nodes, "run": run, "totals": totals}


def render(summary: dict) -> str:
    def row(name: str, b: dict, extra: str = "") -> str:
        miss = b["cache_miss_tokens"]; comp = b["completion_tokens"]; reason = b["reasoning_tokens"]
        shared = f"{100 * b['prefix_shared_chars'] / b['prompt_chars']:.0f}%" if b["prompt_chars"] else "—"
        return (f"| {name} | {b['requests']} | {b['prompt_tokens']:,} | {miss:,} | {comp:,} | {reason:,} | "
                f"{b['elapsed_ms'] / 1000:.0f}s | {shared} |{extra}")
    def flag(value) -> str:
        return " ? |" if value is None else (" ✓ |" if value else " ✗ |")
    lines = ["| node | req | prompt | cache-miss | completion | reasoning | wall | prefix reuse | no node repair | first pass |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---|---|"]
    for node, b in summary["nodes"].items():
        lines.append(row(node, b, flag(b.get("no_node_repair")) + flag(b.get("first_pass"))))
    for phase, b in summary["run"].items():
        lines.append(row(f"_{phase}", b, " | |"))
    lines.append(row("TOTAL", summary["totals"], " | |"))
    if summary["totals"].get("no_usage"):
        lines.append(f"\nexchanges without a usage block (errors, timeouts, empty streams): "
                     f"{summary['totals']['no_usage']} -- the meter may still have billed them")
    nodes = summary["nodes"]
    if nodes:
        no_repair = [n for n, b in nodes.items() if b.get("no_node_repair")]
        known = any(b.get("first_pass") is not None for b in nodes.values())
        passed = [n for n, b in nodes.items() if b.get("first_pass")]
        lines.append(f"\nnodes: {len(nodes)}; no node repair: {len(no_repair)}; "
                     f"first pass: {len(passed) if known else 'unknown (no node_states.json)'}; "
                     f"cache-miss tokens per node: {summary['totals']['cache_miss_tokens'] // len(nodes):,}; "
                     f"requests per node: {summary['totals']['requests'] / len(nodes):.1f}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__); return 2
    path = Path(argv[1])
    if path.is_dir():
        path = path / ".arc" / "llm-usage.jsonl"
    records = load_records(path)
    summary = summarize(records, node_states(path.parent.parent))
    print(json.dumps(summary, indent=1) if "--json" in argv else render(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
