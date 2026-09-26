#!/usr/bin/env python3
"""ARC-Bench custom agent bundle: Octos as the coding agent.

The ARC-Bench platform invokes this as:

    python main.py <requirement_path> [--output-dir DIR] [--web-port N]

Flow (one requirement node at a time, dependencies first):

    skeleton turn (create mode only)
    for node in topological order:
        design turn      -> .arc/design/<node>.json + traceability contract
        implement turn   -> code
        acceptance loop  -> run the node's Playwright specs locally, feed the
                            four-field failure digest back, K <= 5 repairs,
                            commit on improvement, roll back on regression
        traceability     -> design_done / implementation_done / test_passed|failed
    startup rehearsal (build + start exactly like the grader)

Evolution mode (ARCBENCH_TEMPLATE_DIR already holds frontend/ + backend/):
skip the skeleton, diff the requirement tree against the previous run's
`.arc/traceability/requirements.json`, implement only new/changed nodes and
regression-test the unchanged ones.

Environment (all optional):
    OPENAI_API_KEY / OPENAI_BASE_URL / MODEL   OpenAI-compatible endpoint
    OCTOS_BIN                 octos binary (default: ./bin/octos, PATH, download)
    OCTOS_NODE_TIMEOUT        seconds per model turn (default 1200)
    OCTOS_TIME_BUDGET         seconds for the whole generation (default max(3600, 1500 x nodes))
    OCTOS_SECONDS_PER_NODE    per-node allowance used for that default (1500)
    OCTOS_MIN_REPAIR_SECONDS  explicit repair admission floor (default tools 300s; codegen 60s + measured duration)
    OCTOS_NODE_TIME_BUDGET    explicit hard cap per node; default 1500 + earned surplus, at most 3000
    OCTOS_ARC_FINAL_PHASE_SECONDS  large-task time reserved inside the total budget for final suite repair
    OCTOS_REPAIR_ROUNDS       K, acceptance repair rounds per node (default 5 for <=2 nodes, otherwise 3)
    OCTOS_DESIGN_TURN         "0" disables the design turn
    OCTOS_DESIGN_MODE         inline (default) | separate (own read-only design turn)
    OCTOS_DESIGN_MIN_NODES    design only for trees with at least this many nodes (3)
    OCTOS_ARC_APP_DESIGN      "0" skips the one application-level design request that every codegen node's prompt carries
    OCTOS_ARC_APP_DESIGN_CHARS  budget of that design inside each node prompt (6000; routes/pages filtered by spec overlap)
    OCTOS_ARC_GRADER_WORKERS   expected grading concurrency (default 1, based on observed platform logs)
    OCTOS_ARC_FINAL_WORKERS    internal full-suite override (default GRADER_WORKERS; larger values are stress tests)
    OCTOS_ARC_SHARED_REPAIR    "0" disables the single shared runtime-error repair before leaf cycles
    OCTOS_SKELETON_MIN_NODES  separate skeleton turn only for trees with at least this many nodes (3)
    OCTOS_SMALL_TASK_NODES    trees up to this size get the minimal self-verification text (2)
    OCTOS_VERIFY_MODE         auto (default) | minimal | full
    OCTOS_ARC_REASONING       low (default; medium for glm-5.3-flash) | none | auto | medium | high | passthrough
    OCTOS_ARC_IMPLEMENT_REASONING  optional override for first implement turns of small tasks (default: base mode)
    OCTOS_ARC_INLINE_SPECS    "0" stops quoting the node's spec files into the prompt (default: quote up to 24k chars)
    OCTOS_ARC_DESTREAM        "0" lets streaming requests reach the platform as SSE (default: one JSON response upstream)
    OCTOS_ARC_TRIM_PROMPT     "0" keeps the kernel system prompt and all tool schemas (default: drop ARC-irrelevant sections/tools)
    OCTOS_ARC_DROP_SHELL      "0" leaves bash/shell available in minimal-verification turns (default: removed)
    OCTOS_ARC_IMPLEMENT_REQUESTS / OCTOS_ARC_REPAIR_REQUESTS  hard per-turn request caps enforced at the proxy (20 for small tasks; 0 for large tasks = off)
    OCTOS_ARC_REWRITE_ON_ZERO "0" disables the single full-rewrite turn when round 0 passes nothing
    OCTOS_ARC_INLINE_SOURCE_CHARS  budget for quoting the app's sources into repair/rewrite prompts (default codegen budget; 0 = off)
    OCTOS_ARC_MAX_TOKENS      minimum max_tokens the proxy enforces on chat requests (32768; kernel arc.11 sends 4096)
    OCTOS_ARC_CODEGEN         "0" disables one-request codegen turns for one-node tasks (default on)
    OCTOS_ARC_WHOLE_APP       auto (default: no-spec fresh builds) | 1 (also measured specs) | 0 (disabled)
    OCTOS_SESSION_SCOPE       turn (default) | node | run — when a fresh octos session starts
    OCTOS_ARC_INSTALL_PLAYWRIGHT  "0" never installs Playwright on the fly
    OCTOS_ARC_ALIAS_SPEC_IDS  "0" stops mirroring node states onto spec ids
    OCTOS_ARC_FINAL_CONFIRM_RUNS  unchanged-app full-suite runs required before acceptance (default 1)
    OCTOS_ARC_PARTIAL_CONFIRM_RATIO / OCTOS_ARC_PARTIAL_CONFIRM_MAX_FAILURES  near-green confirmation (0.9 / 3)
    OCTOS_ARC_NO_WRITE_SECONDS  elapsed structured-edit time before late read tools close (180; after half the requests)
    OCTOS_ARC_DEGENERATE_MAX_TOKENS  codegen ceiling after repeated/no-op output (8192; 0 disables)
    OCTOS_ARC_RECOVERY_REASONING  optional reasoning after degeneration (none by default)
    OCTOS_ARC_SIBLING_BATCH_SIZE  max independent sibling leaves per codegen request (default 1; no batching)
    OCTOS_ARC_SOURCE_STABILITY_ORDER  "0" restores path order instead of low-churn-first quoted sources
    OCTOS_ARC_GENERIC_TEMPLATE  "0" disables the task-neutral Express/store scaffold (default on in v4)
    OCTOS_ARC_REQUIREMENT_CONTRACT_CHARS  prompt budget for deterministic no-spec contracts (12000/node, 30000/final)
    OCTOS_ARC_NO_SPEC_EDIT_REQUESTS  structured-edit request budget without official specs (default 12)
    OCTOS_ARC_NO_SPEC_REVIEW_SECONDS  maximum focused repair time after a scenario/seed audit (default 180)
    OCTOS_ARC_DERIVED_SPEC_AUDIT  "0" disables requirement-grounded corrections of failing self-generated specs
    OCTOS_ARC_DERIVED_LLM_REQUESTS  cap on pre-implementation AI spec-plan batches (default at most 4)
    OCTOS_ARC_DERIVED_LLM_WALL_SECONDS  total AI spec-planning wall cap (default 480)
    OCTOS_ARC_DERIVED_CASE_REVIEW_REQUESTS / OCTOS_ARC_DERIVED_CASE_REVIEW_WALL_SECONDS  independent case-review caps (6 / 300)
    OCTOS_ARC_DERIVED_FAILURE_REVIEW  "0" disables independent review of failing generated behaviour specs
    OCTOS_ARC_DERIVED_FAILURE_REVIEW_PER_SUITE  maximum AI spec reviews per related/full suite (default 3)
    OCTOS_ARC_TRANSIENT_RETRY_SECONDS  time allowed after the first provider error for retries (default 240)
    OCTOS_ARC_TRANSIENT_ATTEMPT_SECONDS  cap for each request after the first provider error (default 180)
    OCTOS_ARC_WHOLE_APP_PROMPT_CHARS  input cap for each generation wave (default 96000)
    OCTOS_ARC_WHOLE_APP_SOURCE_CHARS  full-source budget inside a wave (default 60000)
    OCTOS_ARC_LLM_TIMEOUT_SECONDS  kernel HTTP timeout per LLM request; must exceed the proxy wait (default 900)
    OCTOS_ARC_BLOCK_ROUTE_WARNINGS  "1" makes a wave's own ROUTE_LINK warnings block completion (default advisory)
    OCTOS_ARC_PRIME_GENERATION_BUILD  "0" skips the one-time dependency/build preflight (default on)
    OCTOS_PERF_CONTRACT       "0" drops the performance rules from prompts
    OCTOS_GUARD               "0" logs guard findings without injecting them
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import re
import shutil
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from arcbench_agent_runtime import AgentRuntime  # noqa: E402
from acceptance import (  # noqa: E402
    workers_for_memory, process_cwd, workspace_contains, free_owned_ports,
    AcceptanceRunner, AppServer, RunSummary, acceptance_work_dir, clip_ends, container_memory_limit, ensure_playwright,
    failure_signature, failure_summaries, failure_source_context, locator_role_mismatch, find_playwright_by_search, find_playwright_root, map_specs_to_nodes,
    nodes_for_failures, playwright_candidates, playwright_version_hint, restore_tree,
    mutated_by_tests, store_changes_by_tests, restore_worktree, snapshot_worktree, tree_digest, workers_for_final, reap_workspace_processes,
    startup_error_digest, backend_error_digest, SharedFailureTracker)
from codegen import (FORMAT_INSTRUCTIONS, dedupe_nav_links, parse_edit_blocks, parse_file_blocks,  # noqa: E402
                     incomplete_blocks, normalize_bare_file_reply, normalize_paired_file_reply, prepare_edit_files, safe_relative_path,
                     source_protocol_errors, write_files)
from guard import TurnMonitor  # noqa: E402
from flow_policy import generation_tokens, node_seconds, phase_for_label, repair_seconds  # noqa: E402
from generation_policy import first_level_phases, phase_context, classify_observation  # noqa: E402
from derived_case_review import (collect_cases, parse_review_decisions, review_request_admissible,
                                 requirement_text, skip_category,
                                 validate_review, safe_records, sha as case_sha)  # noqa: E402
from reply_quality import prune_degenerate_edits  # noqa: E402
from repair_context import diagnosed_failure_evidence as balanced_failure_evidence  # noqa: E402
from generic_template import generic_entry_intact, generic_template_active, install_generic_template  # noqa: E402
from web_stack import recommended_capabilities, stack_note  # noqa: E402
from progress_timeout import ProgressDeadline
from llm_proxy import LlmProxy, configured_model_routes, default_reasoning_for_model, turn_reasoning_for_model  # noqa: E402
from requirement_order import ancestors_of, node_fingerprint, sibling_batches, topo_order  # noqa: E402
from dataclasses import replace as dc_replace  # noqa: E402
from scenario_tests import compile_suite as compile_derived_suite, suite_fixtures, write_suite  # noqa: E402
from scenario_review import (SYSTEM as REVIEW_SYSTEM, ancestor_context, append_tests, behavior_test_titles,  # noqa: E402
                             build_prompt as build_review_prompt, compile_reply as compile_review_reply,
                             folder_text, grounded_behavior_test, parse_failure_review, prioritize_review_targets,
                             retry_prompt as build_review_retry, review_targets)
from derived_spec_audit import repair_failed_generated_specs, replace_failed_test_preserving_oracle  # noqa: E402
from requirement_contracts import (compile_contracts, render_contracts, save_contracts,  # noqa: E402
                                   seed_gaps_by_node, source_literal_gaps, source_seed_gaps)
from web_checks import introduced_route_conflicts, route_table_note, scaffold_issues  # noqa: E402
from seed_facts import SeedResolution, resolve_seeds, seed_contract_note  # noqa: E402

BUNDLE_DIR = Path(__file__).resolve().parent


def log(msg: str) -> None:
    """Progress lines go to BOTH stdout and stderr (the platform truncates
    stdout on long runs but keeps stderr as a separate field)."""
    print(msg, flush=True)
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- postflight

def _postflight_structure_check(output_dir: Path) -> None:
    """Log the deliverable tree; lift a one-level-nested app into place."""
    tree_lines = []
    for root, dirs, files in os.walk(output_dir):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "dist", "__pycache__")]
        depth = Path(root).relative_to(output_dir).parts
        if len(depth) > 2:
            dirs[:] = []
            continue
        indent = "  " * len(depth)
        tree_lines.append(f"{indent}{Path(root).name}/")
        for f in sorted(files)[:8]:
            tree_lines.append(f"{indent}  {f}")
        if len(tree_lines) > 60:
            tree_lines.append("... (truncated)")
            break
    log("[postflight] workspace tree:\n" + "\n".join(tree_lines))
    if (output_dir / "frontend").is_dir() and (output_dir / "backend").is_dir():
        log("[postflight] frontend/ and backend/ present at workspace root")
        return
    for child in [p for p in output_dir.iterdir() if p.is_dir() and p.name not in (".git", ".arc", "requirements")]:
        if (child / "frontend").is_dir() and (child / "backend").is_dir():
            log(f"[postflight] app found nested at {child.name}/; lifting to root")
            for item in child.iterdir():
                dest = output_dir / item.name
                if not dest.exists():
                    shutil.move(str(item), str(dest))
            return
    log("[postflight] WARNING: no frontend/+backend/ found anywhere; runner will reject the template")


def _reap_stray_processes(tag: str, output_dir: Path) -> None:
    """Report resource use and stop matching descendants or workspace processes.

    A killed grader does not by itself establish memory exhaustion. Never
    attribute another run's processes merely from a browser or Node name.
    """
    me = os.getpid()
    def _run(cmd: list[str]) -> str:
        try:
            return subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=20).stdout
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f"<{cmd[0]} unavailable: {exc}>"
    log(f"[reap:{tag}] memory:\n" + _run(["free", "-m"]).rstrip())
    # `free` shows the host; cgroup counters help distinguish container
    # memory pressure from other causes of a killed grading process.
    cg = []
    for f in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current",
              "/sys/fs/cgroup/memory.peak", "/sys/fs/cgroup/memory.events",
              "/sys/fs/cgroup/memory/memory.limit_in_bytes",
              "/sys/fs/cgroup/memory/memory.max_usage_in_bytes",
              "/sys/fs/cgroup/memory/memory.failcnt", "/sys/fs/cgroup/pids.max"):
        try:
            cg.append(f"{f}={Path(f).read_text().strip().replace(chr(10), ' ')}")
        except OSError:
            pass
    log(f"[reap:{tag}] cgroup: " + ("; ".join(cg) or "<no cgroup files>"))
    ps = _run(["ps", "-eo", "pid,ppid,rss,etime,args", "--sort=-rss"])
    log(f"[reap:{tag}] top processes by RSS:\n"
        + "\n".join(ps.splitlines()[:20]))
    rows = []
    for line in ps.splitlines()[1:]:
        parts = line.split(None, 4)
        if len(parts) != 5 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        rows.append((int(parts[0]), int(parts[1]), parts[4]))
    descendants = {me}
    while True:
        expanded = descendants | {pid for pid, parent, _ in rows if parent in descendants}
        if expanded == descendants:
            break
        descendants = expanded
    victims = []
    for pid, _, args in rows:
        if pid in (me, os.getppid()):
            continue
        if not any(marker in args.lower() for marker in
                   ("chrom", "headless_shell", "playwright", "octos serve", "node ", "npm ", "/node")):
            continue
        if pid in descendants or workspace_contains(process_cwd(pid), output_dir):
            victims.append(pid)
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in victims:
            try:
                os.kill(pid, sig)
            except OSError:
                pass
        time.sleep(2 if sig == signal.SIGTERM else 0)
    if victims:
        log(f"[reap:{tag}] killed {len(victims)} stray process(es): {victims}")
        log(f"[reap:{tag}] memory after:\n" + _run(["free", "-m"]).rstrip())
    else:
        log(f"[reap:{tag}] nothing to kill")




def _free_web_port(web_port: int, output_dir: Path) -> None:
    """Release only listeners attributable to this workspace."""
    free_owned_ports([web_port], output_dir)



def _port_watchdog(web_port: int, output_dir: Path, stop: threading.Event) -> None:
    """Kill OUR processes that bind the grading port during generation (the
    runner terminates a run that serves the grading port early). Foreign
    listeners are left alone: the runner host is shared."""
    while not stop.is_set():
        try:
            pids = subprocess.run(["lsof", "-ti", f":{web_port}"], capture_output=True, text=True, timeout=10).stdout.split()
        except (OSError, subprocess.TimeoutExpired):
            pids = []
        for pid in pids:
            try:
                cwd = os.readlink(f"/proc/{pid}/cwd")
            except OSError:
                cwd = ""
            if workspace_contains(cwd, output_dir):
                log(f"[watchdog] port {web_port} bound by our process {pid} (cwd={cwd}); killing")
                try:
                    os.kill(int(pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError, ValueError):
                    pass
            else:
                log(f"[watchdog] port {web_port} held by foreign process {pid} (cwd={cwd or '?'}); leaving it")
        stop.wait(5)


# ---------------------------------------------------------------- requirements

def load_requirement_tree(req_dir: Path) -> dict:
    req_file = req_dir / "requirements.yaml"
    if not req_file.exists():
        req_file = req_dir / "requirements.yml"
    data = yaml.safe_load(req_file.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "id" not in data:
        for wrapper in ("root", "requirement"):
            if isinstance(data.get(wrapper), dict):
                data = data[wrapper]
                break
    if not isinstance(data, dict) or "id" not in data:
        raise ValueError(f"invalid requirements.yaml in {req_dir}")
    return data


def tree_outline(tree: dict, max_chars: int = 60000) -> str:
    """A complete structural catalog followed by fairly budgeted node details.

    Scenarios can contain unique business rules. Keep them when space allows;
    under pressure, reduce detail across nodes rather than lose the last modules.
    """
    heads: list[str] = []
    details: list[tuple[str, str]] = []
    compact_heads: list[tuple[str, str]] = []

    def walk(node: dict, depth: int) -> None:
        deps = [str(d) for d in (node.get("dependencies") or [])]
        head = f"{'  ' * depth}{node.get('id')} [{node.get('type', '')}] {node.get('name', '')}".rstrip()
        if deps:
            head += f" (depends on {', '.join(deps)})"
        heads.append(head)
        compact_heads.append((f"{node.get('id')} [{str(node.get('type', ''))[:1]}]"
                              + (" <-" + ",".join(deps) if deps else ""), str(node.get("name", ""))))
        desc = str(node.get("description") or "").strip()
        facts = [" ".join(desc.split())] if desc else []
        steps = [step for sc in node.get("scenarios") or [] if isinstance(sc, dict)
                 for step in sc.get("steps") or [] if isinstance(step, dict)]
        # Outcomes first, then actions/setup. De-duplicate verbatim repeated facts.
        steps.sort(key=lambda step: str(step.get("keyword", "")).upper() != "THEN")
        seen = set(facts)
        for step in steps:
            fact = " ".join(str(step.get("content", "")).split())
            if fact and fact not in seen and fact not in desc:
                facts.append(f"{step.get('keyword', '')} {fact}".strip())
                seen.add(fact)
        if facts:
            details.append((str(node.get("id")), "\n".join(facts)))
        for child in node.get("children") or []:
            walk(child, depth + 1)

    walk(tree, 0)
    catalog = "\n".join(heads)
    full = catalog + "\n\n" + "\n".join(f"{nid}: {body}" for nid, body in details)
    if len(full) <= max_chars:
        return full
    marker = "\n[outline truncated: detail omitted; consult the full requirement/spec before implementing]"
    budget = max(0, max_chars - len(marker))
    if len(catalog) > budget * 0.65:
        essential = sum(len(head) + 1 for head, _ in compact_heads)
        name_room = max(0, (int(budget * 0.75) - essential) // max(1, len(compact_heads)) - 1)
        catalog = "\n".join(head + (" " + name[:name_room] if name_room else "")
                            for head, name in compact_heads)
    if len(catalog) > budget:
        # Only tiny budgets reach here for current task trees; never imply full coverage.
        return catalog[:budget] + marker
    remaining = budget - len(catalog)
    rendered = []
    pending = len(details)
    for nid, body in details:
        quota = remaining // pending
        pending -= 1
        prefix = f"\n{nid}: "
        if quota <= len(prefix) + 4:
            continue
        room = quota - len(prefix)
        value = body if len(body) <= room else body[:room - 3] + "..."
        rendered.append(prefix + value)
        remaining -= len(prefix) + len(value)
    return catalog + "".join(rendered) + marker


def app_design_errors(design) -> list[dict]:
    """Schema errors with JSON pointers; never normalize requirement semantics."""
    errors = []
    def wrong(path, expected, actual):
        errors.append({"path": path, "expected": expected, "actual": actual})
    if not isinstance(design, dict):
        return [{"path": "/", "expected": "object", "actual": design}]
    model = design.get("data_model")
    if model is not None:
        if not isinstance(model, dict):
            wrong("/data_model", "object of collection objects", model)
        else:
            for key, value in model.items():
                if not isinstance(key, str) or not key or not isinstance(value, dict):
                    wrong("/data_model/" + str(key).replace("~", "~0").replace("/", "~1"), "collection object", value)
    for kind in ("routes", "pages", "contracts", "modules"):
        items = design.get(kind)
        if items is None:
            continue
        if not isinstance(items, list):
            wrong("/" + kind, "array of objects", items)
            continue
        seen = set()
        for index, item in enumerate(items):
            path = f"/{kind}/{index}"
            if not isinstance(item, dict):
                wrong(path, "object", item)
                continue
            if kind in {"routes", "pages", "modules"}:
                value = item.get("path")
                valid = isinstance(value, str) and (value.startswith(("frontend/", "backend/")) if kind == "modules"
                                                    else value.startswith("/") and not re.search(r"\s", value))
                if not valid:
                    wrong(path + "/path", "frontend/ or backend/ source path" if kind == "modules" else "absolute path without whitespace", value)
            if kind in {"routes", "pages"}:
                method = item.get("method", "")
                if not isinstance(method, str) or (kind == "routes" and method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}):
                    wrong(path + "/method", "HTTP method" if kind == "routes" else "string", method)
                identity = (str(method), str(item.get("path")))
                if identity in seen:
                    wrong(path, "unique method/path pair", item)
                seen.add(identity)
            if "requirements" in item or kind == "contracts":
                values = item.get("requirements")
                if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                    wrong(path + "/requirements", "array of requirement IDs", values)
            field = "owns" if kind == "modules" else "invariants" if kind == "contracts" else None
            if field:
                values = item.get(field)
                if not isinstance(values, list) or not values or not all(isinstance(v, str) and (v or kind == "contracts") for v in values):
                    wrong(path + "/" + field, "nonempty array of strings", values)
    if design.get("notes") is not None and not isinstance(design["notes"], str):
        wrong("/notes", "string", design["notes"])
    if not any(design.get(k) for k in ("data_model", "routes", "pages")):
        wrong("/", "at least one nonempty data_model, routes or pages", {})
    return errors


def valid_app_design(design) -> dict | None:
    return design if not app_design_errors(design) else None


def app_design_coverage(design: dict | None) -> set[str]:
    """Atomic requirement ids explicitly assigned to a design artifact."""
    covered: set[str] = set()
    for kind in ("routes", "pages", "contracts"):
        for item in (design or {}).get(kind) or []:
            if isinstance(item, dict):
                covered.update(str(value) for value in item.get("requirements") or [] if value)
    return covered


def _relaxed_json(text: str) -> str:
    """Remove only common JSON presentation mistakes outside string values.

    Design replies are still schema-validated by ``valid_app_design``. This is
    deliberately narrower than accepting JavaScript: comments and dangling
    commas are recoverable, while single quotes, identifiers and expressions
    are not. The scanner is string-aware so URLs containing ``//`` survive.
    """
    out: list[str] = []
    index = 0
    quoted = False
    escaped = False
    while index < len(text):
        char = text[index]
        if quoted:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            index += 1
            continue
        if char == '"':
            quoted = True
            out.append(char)
            index += 1
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index + 2)
            index = len(text) if newline < 0 else newline
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                return text
            index = end + 2
            continue
        out.append(char)
        index += 1
    uncommented = "".join(out)
    out = []
    quoted = False
    escaped = False
    for index, char in enumerate(uncommented):
        if quoted:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == ",":
            following = index + 1
            while following < len(uncommented) and uncommented[following].isspace():
                following += 1
            if following < len(uncommented) and uncommented[following] in "}]":
                continue
        out.append(char)
    return "".join(out)


def parse_app_design_reply(reply: str, *, validate: bool = True) -> dict | None:
    """Find and validate one design object, with a bounded local recovery pass."""
    candidates: list[str] = []
    for match in re.finditer(r"```(?:json)?\s*(.*?)\s*```", reply or "", re.S | re.I):
        candidates.append(match.group(1))

    # Code fences are optional. Extract balanced top-level objects instead of
    # greedily joining unrelated braces in surrounding prose.
    start = None
    depth = 0
    quoted = False
    escaped = False
    for index, char in enumerate(reply or ""):
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                candidates.append(reply[start:index + 1])
                start = None

    seen: set[str] = set()
    raw_fallback = None
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        for serialized in (candidate, _relaxed_json(candidate)):
            try:
                parsed = json.loads(serialized)
                design = valid_app_design(parsed) if validate else parsed if isinstance(parsed, dict) else None
            except (json.JSONDecodeError, TypeError):
                continue
            if design is not None:
                if not validate and not any(key in design for key in ("data_model", "routes", "pages", "modules", "contracts")):
                    raw_fallback = design
                    continue
                return design
    return raw_fallback if not validate else None


def _design_catalog(design: dict) -> list[str]:
    """One compact line per route and page: `R3 POST /api/orders`, `P2 /login`.
    Every node sees the whole set of names, at ~20 chars each, without the
    detail text; the details a node needs travel in its slice."""
    lines = []
    for i, route in enumerate(design.get("routes") or [], 1):
        if isinstance(route, dict):
            lines.append(f"R{i} {route.get('method', '')} {route.get('path', '')}".strip())
    for i, page in enumerate(design.get("pages") or [], 1):
        if isinstance(page, dict):
            lines.append(f"P{i} {page.get('path', '')}".strip())
    return lines


def app_design_blocks(design: dict | None, spec_text: str, cap: int) -> tuple[str, str]:
    """(stable, node_slice): the design text a codegen prompt carries, split by
    where it may sit. Keys are sorted so equal designs render identically.

    A design that fits `cap` whole is identical for every node and goes BEFORE
    the sources, so the prefix every node shares stays byte-identical. A larger
    one is compiled into two layers: a stable CORE (everything but routes and
    pages: data model, conventions, notes) plus a CATALOG (compact route/page
    names, whole entries only) -- the same for every node, before the sources -- and a
    node SLICE with relevant complete entries AFTER the sources. The combined
    layers fit cap; serialized JSON is never cut in the middle of a field."""
    if not design or cap < 120:
        return "", ""
    header = "Application design (shared contract):\n"

    def render(doc: dict) -> str:
        return header + json.dumps(doc, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"

    whole = render(design)
    if len(whole) <= cap:
        return whole, ""
    core = {"omitted": "design truncated; see .arc/design/app.json"}
    slice_header = "Design entries for this requirement:\n"
    detail: dict = {}
    stable_cap = max(len(render(core)), int(cap * 0.65))

    def size() -> int:
        return len(render(core)) + (len(slice_header) + len(json.dumps(
            detail, ensure_ascii=False, separators=(",", ":"), sort_keys=True)) + 1 if detail else 0)

    def append_entry(doc: dict, key: str, value) -> bool:
        entries = doc.setdefault(key, [])
        entries.append(value)
        if size() <= (stable_cap if doc is core else cap):
            return True
        entries.pop()
        if not entries:
            del doc[key]
        return False

    # Stable structure takes precedence. Append only complete JSON values.
    for entry in _design_catalog(design):
        append_entry(core, "catalog", entry)
    for name, shape in sorted((design.get("data_model") or {}).items()):
        core.setdefault("data_model", {})[name] = shape
        if size() > stable_cap:
            del core["data_model"][name]
    for module in design.get("modules") or []:
        if not append_entry(core, "modules", module):
            break
    # Stable fields are selected before consulting the current requirement.
    if design.get("notes"):
        core["notes"] = design["notes"]
        if size() > stable_cap:
            del core["notes"]
    for contract in design.get("contracts") or []:
        if not contract.get("requirements"):
            append_entry(core, "contracts", contract)
    terms = spec_terms(spec_text)
    # Public exercises use dotted IDs while the hackathon catalogue uses
    # hyphenated descendants (REQ-2-3, REQ-2-3-1).  Both must select the
    # routes/pages explicitly owned by the active requirement.
    req_ids = set(re.findall(r"\bREQ-\d+(?:(?:\.|-)\d+)*\b", spec_text))

    def related(item) -> bool:
        owners = set(item.get("requirements") or [])
        if owners and req_ids:
            return bool(owners & req_ids)
        low = json.dumps(item, ensure_ascii=False).lower()
        return any(term in low for term in terms)

    for key in ("contracts", "routes", "pages"):
        items = design.get(key) or []
        for item in items:
            if related(item):
                append_entry(detail, key, item)
    node_slice = ""
    if detail:
        node_slice = slice_header \
            + json.dumps(detail, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    stable = render(core)
    return (stable, node_slice) if len(stable) + len(node_slice) <= cap else ("", "")


def app_design_context(design: dict | None, spec_text: str, cap: int) -> str:
    """Stable design plus relevant complete entries, jointly bounded by cap.

    Any omissions are explicit; full design remains on disk. Empty without a design.
    """
    stable, node_slice = app_design_blocks(design, spec_text, cap)
    return stable + node_slice


def describe_node(node: dict, *, include_scenarios: bool = True) -> str:
    lines = [f"ID: {node.get('id')}", f"Name: {node.get('name', '')}"]
    if node.get("description"):
        lines.append(f"Description: {node['description']}")
    scenarios = (node.get("scenarios") or []) if include_scenarios else []
    if scenarios:
        lines.append("Scenarios:")
        for sc in scenarios:
            lines.append(f"  - {sc.get('name', 'scenario')}")
            for step in sc.get("steps") or []:
                if isinstance(step, dict):
                    lines.append(f"      {step.get('keyword', '')} {str(step.get('content', '')).strip()}")
    deps = node.get("dependencies") or []
    if deps:
        lines.append(f"Depends on: {', '.join(map(str, deps))}")
    return "\n".join(lines)


def folder_descendants(tree: dict) -> dict[str, list[str]]:
    """Non-atomic node id -> ids of its ATOMIC descendants (document order)."""
    out: dict[str, list[str]] = {}

    def walk(node: dict) -> list[str]:
        children = [c for c in (node.get("children") or []) if isinstance(c, dict)]
        node_type = str(node.get("type") or "").upper()
        node_id = str(node.get("id") or "")
        if node_type == "ATOMIC" or (not children and node_type != "FOLDER"):
            return [node_id]
        ids: list[str] = []
        for child in children:
            ids.extend(walk(child))
        if node_id:
            out[node_id] = ids
        return ids

    walk(tree)
    return out


def previous_requirement_records(output_dir: Path) -> dict[str, dict]:
    """The previous run's requirement table (committed with the template)."""
    path = output_dir / ".arc" / "traceability" / "requirements.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


def unchanged_node_ids(nodes: list[dict], previous: dict[str, dict]) -> set[str]:
    out = set()
    for node in nodes:
        prev = previous.get(str(node.get("id")))
        if prev and node_fingerprint(prev) == node_fingerprint(node):
            out.add(str(node.get("id")))
    return out


CODEGEN_MANIFESTS = {
    # Preserve source filenames and nested assets. Routes belong to the application;
    # extensionless aliases can shadow HTML routes and acquire a binary MIME type.
    "frontend/package.json": {"name": "f", "private": True, "scripts": {"build": "node -e \"const f=require('fs');f.rmSync('dist',{recursive:true,force:true});f.cpSync('src','dist',{recursive:true})\""}},
    # "type": "commonjs" pins the loader: Node 20.19 module detection treated a server.js mixing
    # import and require as ESM (cloud 3e425ce2ebf6: "require is not defined in ES module scope").
    "backend/package.json": {"name": "b", "private": True, "type": "commonjs", "scripts": {"start": "node server.js"},
                             "dependencies": {"express": "5.2.1"}},
}


def write_codegen_manifests(output_dir: Path) -> list[str]:
    """Write initial manifests; generated code may extend them for task needs.

    The lightweight frontend build copies src/ into dist/. A framework or CSS
    compiler must replace that script with a real production build.
    """
    written = []
    for rel, data in CODEGEN_MANIFESTS.items():
        path = output_dir / rel
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        written.append(rel)
    return written


SOURCE_EXTS = (".html", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts",
               ".vue", ".css", ".scss", ".json", ".svg")
LOCKFILES = {"package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock"}


def inline_sources(output_dir: Path, max_chars: int = 90000, exts: tuple = SOURCE_EXTS) -> str:
    """Quote the app's source files (frontend sources, backend JS) so a repair
    turn edits immediately instead of spending its request budget on reads.

    Bounded, largest first: whatever has to be dropped should be the file least
    likely to need editing, and quoting smallest first made that the largest
    one. In cloud e767e871a6c6 the seed data, the lockfiles and the secondary
    pages were quoted and `frontend/src/index.html` — the whole UI, and where
    nearly every failure lives — was the one file omitted.
    """
    files = app_source_files(output_dir, exts)
    parts, total = [], 0
    for path in sorted(files, key=lambda p: (-p.stat().st_size, str(p))):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(path.relative_to(output_dir))
        shared = {"frontend/build.mjs": "frontend-build.mjs",
                  "frontend/vite.config.mjs": "vite.config.mjs",
                  "frontend/src/shared/dom.js": "frontend-dom.js",
                  "frontend/src/shared/request.js": "frontend-request.js",
                  "frontend/src/shared/router.js": "frontend-router.js"}.get(rel)
        if shared:
            try:
                if text == (BUNDLE_DIR / "blueprints" / shared).read_text(encoding="utf-8"):
                    continue  # the public build contract is in the prompt; read this file only if needed
            except OSError:
                pass
        if total + len(text) > max_chars:
            # A task with a hundred nodes grows one dominant UI file past the
            # whole budget on its own. Dropping it left the prompt quoting the
            # stylesheet and the seed data and not the file every repair edits,
            # which is the failure the largest-first order was meant to prevent.
            # Give any file too big to quote whole a share of the budget instead
            # of nothing, capped at half so one file cannot crowd out the rest;
            # the elision marker keeps it from reading as the complete file.
            room = min(max_chars // 2, max_chars - total)
            if room >= 2000:
                total += room
                parts.append(f"--- {path.relative_to(output_dir)} --- (too large to quote whole, "
                             f"{len(text)} chars; the part shown is clipped, read it for the rest)\n"
                             f"{clip_ends(text, room)}\n")
                continue
            parts.append(f"--- {path.relative_to(output_dir)} --- (omitted, {len(text)} chars; read it if you must change it)\n")
            continue
        total += len(text)
        parts.append(f"--- {path.relative_to(output_dir)} ---\n{text.rstrip()}\n")
    return ("Current source files (quoted; edit them directly, no need to read):\n" + "".join(parts)) if parts else ""


def app_source_files(output_dir: Path, exts: tuple | None = SOURCE_EXTS) -> list[Path]:
    files: list[Path] = []
    for part in ("frontend", "backend"):
        base = output_dir / part
        if not base.is_dir():
            continue
        found = []
        for directory, dirs, names in os.walk(base):
            dirs[:] = sorted(name for name in dirs if name not in {"node_modules", "dist", ".git", "coverage", ".vite"})
            for name in names:
                path = Path(directory) / name
                if path.is_file() and (exts is None or path.suffix in exts) and name not in LOCKFILES:
                    found.append(path)
        files.extend(sorted(found))
    return files


def spec_terms(spec_text: str) -> set[str]:
    """Identifiers, paths and quoted strings a spec mentions (≥ 3 chars), lower-cased."""
    terms = set(re.findall(r"[A-Za-z_][A-Za-z0-9_-]{2,}", spec_text))
    terms |= set(re.findall(r"['\"`](/[^'\"`\s]{1,60})['\"`]", spec_text))
    terms |= set(re.findall(r"['\"`]([^'\"`\n]{3,40})['\"`]", spec_text))
    stop = {"await", "page", "expect", "const", "test", "async", "import", "from", "playwright", "toBeVisible",
            "toHaveText", "getByRole", "getByTestId", "getByLabel", "getByText", "click", "fill", "goto", "name",
            "button", "link", "true", "false", "null", "let", "var", "return", "function"}
    return {t.lower() for t in terms if t not in stop}


_HELPER_DECL = re.compile(
    r"^(?:export\s+(?:default\s+)?)?(?:async\s+)?(?:function\*?|const|let|var|class|type|interface|enum)\s+"
    r"([A-Za-z_$][\w$]*)", re.M)
_IDENT = re.compile(r"[A-Za-z_$][\w$]*")


def trim_helper_to_references(helper: str, referenced: set[str]) -> str:
    """The top-level declarations of a test helper file that `referenced`
    identifiers reach, transitively, plus its import lines; "" when none do.

    A shared helpers.ts is written for the whole suite (12306: 54 exports,
    25k chars) while one spec uses a handful (median 4). Quoting the file
    whole into every node's prompt made every spec look 25k chars long: the
    reasoning-off rule never fired and ~7k tokens of unrelated code rode
    along in each request. A file with no recognisable top-level
    declarations is returned whole -- better too much than a broken quote."""
    decls = list(_HELPER_DECL.finditer(helper))
    if not decls:
        return helper
    # An export the parser cannot name -- `export { a, b }`, a destructuring
    # `export const { x } = ...`, `export default { ... }` -- would be dropped
    # silently by the closure below. Quote the whole file instead.
    if any(not _HELPER_DECL.match(line) for line in re.findall(r"^export\b.*$", helper, re.M)):
        return helper
    starts = [d.start() for d in decls] + [len(helper)]
    spans = {d.group(1): helper[starts[i]:starts[i + 1]] for i, d in enumerate(decls)}
    include: set[str] = set()
    frontier = set(spans) & referenced
    while frontier:
        include |= frontier
        reached = set()
        for name in frontier:
            reached |= set(_IDENT.findall(spans[name])) & set(spans)
        frontier = reached - include
    if not include:
        return ""
    header = [line for line in helper[:starts[0]].splitlines() if line.startswith("import ")]
    kept = [spans[d.group(1)].rstrip() for d in decls if d.group(1) in include]
    return "\n".join(header + [""] + kept).strip() + "\n"


def quoted_paths(prompt: str) -> set[str]:
    """Files a codegen prompt shows whole: `--- path ---` headers with nothing
    after them. A header annotated `(omitted, ...)` or `(too large to quote
    whole, ...)` shows nothing or only a part, and the name-only listing
    render_source_selection puts last shows nothing; none of those count."""
    return {match.group(1) for match in re.finditer(r"^--- (\S+) ---[ \t]*$", prompt, re.M)}


def outlined_paths(prompt: str) -> set[str]:
    """Files a codegen prompt shows as an outline: anchored EDIT blocks on them
    are safe (the anchor must match once), whole-file rewrites are not."""
    return {match.group(1) for match in re.finditer(r"^--- (\S+) --- \(outline\b", prompt, re.M)}


OUTLINE_LINE = re.compile(
    r"^\s*(?:import\b|export\b|module\.exports\b|(?:app|router)\.(?:get|post|put|patch|delete|use)\(|"
    r"<Route\b|(?:async\s+)?function\s+\w+|const\s+\w+\s*=\s*(?:\(|async\b|React\.|require\()|"
    r"\w+\.route\()")


def outline_source(text: str, max_chars: int = 6000) -> str:
    """The lines that carry a file's interface -- imports, exports, route
    registrations, component and handler signatures -- verbatim, so they can
    serve as exact EDIT anchors. Bounded; a trailing marker says what was cut."""
    lines = [line for line in text.splitlines() if OUTLINE_LINE.match(line) or "<Route" in line]
    out: list[str] = []
    total = 0
    for line in lines:
        if total + len(line) + 1 > max_chars - 40:
            out.append("... (outline truncated)")
            break
        out.append(line)
        total += len(line) + 1
    return "\n".join(out)


def backend_entry(output_dir: Path) -> Path | None:
    """The backend file `npm start` runs: the one module every node's request has
    to see, because it is what mounts everything else. Read from the start script
    so a renamed entry still ranks first; fall back to the contract's server.js."""
    name = "server.js"
    try:
        start = json.loads((output_dir / "backend" / "package.json").read_text(encoding="utf-8"))
        match = re.search(r"([\w./-]+\.[cm]?js)", str(start.get("scripts", {}).get("start", "")))
        if match:
            name = match.group(1)
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    path = output_dir / "backend" / name
    return path if path.is_file() else None


def missing_backend_entry(output_dir: Path) -> str | None:
    """Report a missing entry only for the known direct Node startup layout.

    A framework/build command may create its entry later; do not invent a
    server.js requirement for those applications.
    """
    manifest = output_dir / "backend/package.json"
    if not manifest.exists():
        script = "node server.js"  # the manifest the codegen harness will write
    else:
        try:
            script = json.loads(manifest.read_text()).get("scripts", {}).get("start", "")
        except (OSError, ValueError, AttributeError, TypeError):
            return None
    if not isinstance(script, str):
        return None
    match = re.fullmatch(r"\s*node\s+([\w./-]+\.[cm]?js)\s*", script)
    if not match:
        return None
    relative = Path(match[1])
    if relative.is_absolute() or ".." in relative.parts:
        return None
    path = output_dir / "backend" / relative
    return str(Path("backend") / relative) if not path.is_file() else None


def navigation_targets(spec_text: str, files) -> set[str]:
    """Map literal test navigation to pages in the codegen source layout.

    Only the helpers reachable by the current spec are normally supplied here.
    Dynamic URLs remain unknown; an arbitrary slash or navigation label is not
    evidence that a particular page is involved.
    """
    candidates = set()
    for match in re.finditer(r"\.goto\(\s*(['\"`])([^'\"`\r\n]*)\1\s*[,)]", spec_text):
        url = match[2]
        if not url.startswith("/") or url.startswith("//") or "${" in url:
            continue
        route = re.split(r"[?#]", url, maxsplit=1)[0].strip("/")
        if ".." in Path(route).parts:
            continue
        pages = ["index.html"] if not route else ([route] if route.endswith(".html") else
                                                   [f"{route}.html", f"{route}/index.html"])
        candidates.update(f"{base}/{page}" for base in ("frontend/src", "frontend") for page in pages)
    return candidates & {str(rel) for rel in files}


def spec_targets(spec_text: str, files) -> set[str]:
    """Source files whose name the spec mentions: a file stem of five or more
    alphanumerics (`ticket-orders` -> `ticketorders`) found inside the spec text
    with separators and case removed (`openTicketOrders`, `/ticket-orders`,
    "Ticket Orders"). Helper names complement explicit navigation paths."""
    files = list(files)
    flat = re.sub(r"[^a-z0-9]", "", spec_text.lower())
    targets = navigation_targets(spec_text, files)
    for rel in files:
        stem = re.sub(r"[^a-z0-9]", "", Path(str(rel)).stem.lower())
        if len(stem) >= 5 and stem in flat:
            targets.add(str(rel))
    return targets


def scored_sources(output_dir: Path, spec_text: str, entry: Path | None = None,
                   must_include=()) -> list[tuple]:
    """Read and rank a source snapshot once; rendering does not reread disk.

    Rank: the backend entry (what every node extends) first; then the files the
    node is known to need -- `must_include` (a path the last reply was refused
    for: the model told us which file it edits), explicit navigation, then the
    spec's name-based targets; then the remaining sources -- pages and backend modules
    alike -- by how many of the spec's terms (locators, texts, routes) they
    contain, smaller files breaking ties; JSON state follows code.

    Cloud fcec6ac02a95: with 44 files the term ranking is noisy (every page
    carries the navigation words) and the size tie-break filled the budget with
    small files, so the page a node was about was skipped, the guard refused
    the rewrite, and 28 nodes went to tool mode -- 93% of the run's requests.

    Ranking every backend file ahead of the pages was right while the backend was
    one server.js. Once feature code sits in backend/routes/<area>.js, quoting all
    of them first would push out the page the spec actually names, so only the
    entry keeps its place and the modules compete on overlap like the pages."""
    terms = spec_terms(spec_text)
    entry = entry or backend_entry(output_dir)
    files = app_source_files(output_dir)
    certain = set(str(rel) for rel in must_include)          # the model named it: it edits this file
    guessed = spec_targets(spec_text, [p.relative_to(output_dir) for p in files])   # the spec names it
    navigated = navigation_targets(spec_text, [p.relative_to(output_dir) for p in files])
    scored = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        low = text.lower()
        hits = sum(1 for term in terms if term in low)
        rel = path.relative_to(output_dir)
        if path == entry:
            priority = 0
        elif str(rel) in certain:
            priority = 1
        elif str(rel) in navigated:
            priority = 2
        elif str(rel) in guessed:
            priority = 3
        elif path.suffix == ".json":
            priority = 5
        else:
            priority = 4
        scored.append((priority, -hits, len(text), rel, text))
    from source_index import SourceIndex
    index = SourceIndex({str(row[3]): row[4] for row in scored})
    related = index.related(certain | guessed | navigated)
    scored = [(3.5 if row[0] >= 4 and str(row[3]) in related else row[0], *row[1:]) for row in scored]
    return sorted(scored, key=lambda item: item[:3])


def render_source_selection(scored: list[tuple], selected: list[int], stable_order: bool,
                            change_counts: dict[str, int] | None = None) -> str:
    if not scored:
        return ""
    chosen = set(selected)
    quoted = [(priority, rel, text) for i, (priority, _, _, rel, text) in enumerate(scored) if i in chosen]
    omitted = [f"{rel} ({size} chars, {-neg_hits} spec terms)"
               for i, (_, neg_hits, size, rel, _) in enumerate(scored) if i not in chosen]
    if stable_order:
        counts = change_counts or {}
        # Selection remains relevance-based. Presentation puts the stable entry
        # first, then files with fewer edits earlier so a frequently rewritten
        # page does not invalidate the unchanged source prefix after it.
        quoted.sort(key=lambda item: (0 if item[0] == 0 else 1, counts.get(str(item[1]), 0), str(item[1])))
        omitted.sort()
    out = "Current source files (quoted; preserve unchanged behavior):\n"
    out += "".join(f"--- {rel} ---\n{text.rstrip()}\n" for _, rel, text in quoted)
    if omitted:
        out += "Other files, unchanged unless the requirement needs them: " + "; ".join(omitted) + "\n"
    return out


def select_source_snapshot(scored: list[tuple], max_chars: int, *, stable_order: bool = False,
                           max_output_chars: int | None = None,
                           change_counts: dict[str, int] | None = None,
                           max_priority: float | None = None) -> str | None:
    """Select by relevance/content budget, then enforce the serialized budget.

    `max_chars` counts file contents; `max_output_chars` (when given) bounds the
    rendered block, headings and omission list included. Each overflow step
    removes one least-priority quoted file, so the entry -- ranked first -- is
    the last to go. There are at most len(scored) + 1 renders, all using the same
    in-memory snapshot. `stable_order` changes presentation only, keeping the same
    relevance selection but quoting the entry and low-churn files first for prefix reuse.
    """
    selected, total = [], 0
    for i, (priority, _, size, _, _) in enumerate(scored):
        if max_priority is not None and priority > max_priority:
            continue
        if total + size <= max_chars:
            selected.append(i)
            total += size
    while True:
        out = render_source_selection(scored, selected, stable_order, change_counts)
        if max_output_chars is None or len(out) <= max_output_chars:
            return out
        if not selected:
            return None
        selected.pop()


def source_listing(output_dir: Path, limit: int = 60) -> str:
    """Short, stable listing of the app sources for evolution prompts."""
    lines = []
    for part in ("frontend", "backend"):
        base = output_dir / part
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            rel = path.relative_to(output_dir)
            if any(seg in ("node_modules", "dist", ".git") for seg in rel.parts):
                continue
            if path.is_file():
                lines.append(f"{rel} ({path.stat().st_size} B)")
            if len(lines) >= limit:
                lines.append("...")
                return "\n".join(lines)
    return "\n".join(lines)


CHECKPOINT_NOTE = (
    "Previously passing behavior failed when checked together after recent changes. "
    "Repair the observed failures while preserving other working behavior. "
    "Tests ran together against one server; use this evidence when implementing the next node.\n")
CHECKPOINT_ELISION = "\n… checkpoint evidence elided to fit this request …\n"


class CheckpointEvidence(str):
    """Only the observation body is truncatable; node identities stay intact."""
    def __new__(cls, evidence: str, failing_ids: list[str]):
        prefix = CHECKPOINT_NOTE + "Failing requirements: " + ", ".join(failing_ids or ["unattributed"]) + "\n"
        value = super().__new__(cls, prefix + evidence)
        value.prefix = prefix
        value.evidence = evidence
        value.failing_ids = failing_ids
        return value

    def clipped(self, body_limit: int):
        if len(self.evidence) <= body_limit:
            return self
        if body_limit < len(CHECKPOINT_ELISION):
            return None
        room = body_limit - len(CHECKPOINT_ELISION)
        head = room * 2 // 3
        tail = room - head
        body = self.evidence[:head] + CHECKPOINT_ELISION + (self.evidence[-tail:] if tail else "")
        return CheckpointEvidence(body, self.failing_ids)


class HarnessCorrections(str):
    """String-compatible corrections that retain the truncatable evidence type."""
    def __new__(cls, entries: list[str]):
        text = "Corrections from the harness:\n" + "\n".join(f"- {entry}" for entry in entries) + "\n"
        value = super().__new__(cls, text)
        value.entries = list(entries)
        return value

    def fit(self, max_chars: int):
        if len(self) <= max_chars:
            return self
        entries = list(self.entries)
        excess = len(self) - max_chars
        for i in sorted(range(len(entries)), key=lambda index: len(entries[index]), reverse=True):
            entry = entries[i]
            if not isinstance(entry, CheckpointEvidence):
                continue
            body_limit = max(len(CHECKPOINT_ELISION), len(entry.evidence) - excess)
            clipped = entry.clipped(body_limit)
            if clipped is not None:
                excess -= len(entry) - len(clipped)
                entries[i] = clipped
            if excess <= 0:
                return HarnessCorrections(entries)
        return None


# ---------------------------------------------------------------- octos driver

OCTOS_RELEASE_URL = (
    "https://github.com/octos-org/octos-arc/releases/download/v2.0.3-rc.11-arc.13/"
    "octos-bundle-x86_64-unknown-linux-gnu.tar.gz"
)


def _cached_runtime_matches(cache_dir: Path, url: str) -> bool:
    try:
        return (cache_dir / "source-url.txt").read_text() == url
    except OSError:
        return False


def _download_octos(dest_dir: Path) -> str:
    """Fetch the Linux octos binary at runtime via gh-proxy mirrors first (the
    runner's path to GitHub stalls / kills HTTP/2 streams)."""
    import tarfile
    import urllib.request

    dest_dir.mkdir(parents=True, exist_ok=True)
    tarball = dest_dir / "octos-bundle.tar.gz"
    url = os.environ.get("OCTOS_RELEASE_URL", OCTOS_RELEASE_URL)
    if not _cached_runtime_matches(dest_dir, url):
        # A complete archive from an older URL must not satisfy a new download.
        tarball.unlink(missing_ok=True)


    def tarball_ok() -> bool:
        try:
            with tarfile.open(tarball) as tf:
                return tf.getmember("octos") is not None
        except Exception:  # noqa: BLE001
            return False

    ok = tarball_ok()
    mirrors = [f"{prefix}/{url}" for prefix in ("https://ghfast.top", "https://gh-proxy.com")] + [url]
    for attempt in range(1, 13):
        if ok:
            break
        mirror = mirrors[(attempt - 1) % len(mirrors)]
        log(f"[octos] download attempt {attempt} ({mirror}) ...")
        if shutil.which("curl"):
            try:
                subprocess.run(["curl", "-fsSL", "--http1.1", "-C", "-", "--connect-timeout", "30",
                                "--speed-limit", "10240", "--speed-time", "60", "--retry", "2",
                                "-o", str(tarball), mirror], check=False, timeout=600)
            except subprocess.TimeoutExpired:
                log(f"[octos] attempt {attempt} killed after 600s stall; rotating mirror")
        else:
            try:
                urllib.request.urlretrieve(mirror, tarball)
            except Exception as exc:  # noqa: BLE001
                log(f"[octos] download error: {exc}")
        ok = tarball_ok()
    if not ok:
        raise RuntimeError("failed to download octos binary after 12 attempts")
    with tarfile.open(tarball) as tf:
        for member in ("octos", "octos-sandbox"):
            try:
                tf.extract(member, dest_dir, filter="data")
            except KeyError:
                pass
    binary = dest_dir / "octos"
    binary.chmod(0o755)
    if (dest_dir / "octos-sandbox").exists():
        (dest_dir / "octos-sandbox").chmod(0o755)
    marker = dest_dir / f"source-url-{os.getpid()}.tmp"
    try:
        marker.write_text(url)
        marker.replace(dest_dir / "source-url.txt")
    finally:
        marker.unlink(missing_ok=True)
    return str(binary)


def executable_or_none(path: Path) -> Path | None:
    """A binary shipped inside the bundle only counts if it can actually be spawned.
    Python's zipfile drops the Unix mode on extract, so `bin/octos` can be present
    and still not executable; restore the bit. A bundle we cannot chmod (read-only
    mount) has to fall through to the download rather than hand back a path the OS
    refuses."""
    if not path.is_file():
        return None
    try:
        if not os.access(path, os.X_OK):
            path.chmod(path.stat().st_mode | 0o755)
    except OSError:
        return None
    return path if os.access(path, os.X_OK) else None


def find_octos() -> str:
    env_bin = os.environ.get("OCTOS_BIN")
    if env_bin and Path(env_bin).exists():
        return env_bin
    bundled = executable_or_none(BUNDLE_DIR / "bin" / "octos")
    if bundled:
        executable_or_none(BUNDLE_DIR / "bin" / "octos-sandbox")  # optional helper
        log(f"[octos] using the binary shipped in the bundle: {bundled}")
        return str(bundled)
    found = shutil.which("octos")
    if found:
        return found
    cache_dir = Path(os.environ.get("OCTOS_CACHE_DIR", "/tmp/octos-bin"))
    url = os.environ.get("OCTOS_RELEASE_URL", OCTOS_RELEASE_URL)
    if (cache_dir / "octos").is_file() and _cached_runtime_matches(cache_dir, url):
        return str(cache_dir / "octos")
    return _download_octos(cache_dir)


def protected_hooks(protected_dirs: list[Path] | None) -> list[dict]:
    """before_tool_call hook denying file writes into the official tests /
    requirements directories (exit 1 = deny). Shell commands are redacted by
    the kernel and cannot be checked here; the harness restores the trees
    after every turn as the second layer."""
    hook_script = BUNDLE_DIR / "hooks" / "deny_protected.py"
    if not protected_dirs or not hook_script.is_file():
        return []
    return [{
        "event": "before_tool_call",
        "command": [sys.executable, str(hook_script), *[str(p) for p in protected_dirs]],
        "timeout_ms": 4000,
        "tool_filter": ["write_file", "edit_file", "diff_edit", "apply_patch", "create_file", "append_file"],
    }]


def write_profile_defaults(data_dir: Path, config_dir: Path, hooks: list[dict]) -> None:
    """Belt and braces: the solo ProfileRuntime builds its HookExecutor from
    the profile's own config (the stdio driver patches `hooks` into the
    profile registry file — the mechanism verified to deny with a real turn);
    a `profile-defaults.json` covers code paths that merge store defaults."""
    if not hooks:
        return
    for root in (data_dir, config_dir):
        try:
            root.mkdir(parents=True, exist_ok=True)
            (root / "profile-defaults.json").write_text(json.dumps({"hooks": hooks}, indent=2), encoding="utf-8")
        except OSError:
            pass


def llm_timeout_secs() -> int:
    """Kernel HTTP timeout for one non-streaming completion.

    It must outlast the proxy's own upstream wait (at most 600 s): at the
    kernel's 300 s default a slow but healthy generation was abandoned
    client-side and replayed after a backoff.
    """
    return max(60, int(os.environ.get("OCTOS_ARC_LLM_TIMEOUT_SECONDS", "900")))


def build_octos_env(config_dir: Path, protected_dirs: list[Path] | None = None) -> dict:
    """Prepare env + minimal config.json for non-interactive octos.

    `protected_dirs` (official tests, requirements) get a before_tool_call
    hook that denies write_file/edit_file into them (exit 1 = deny)."""
    env = os.environ.copy()
    api_key = env.get("OPENAI_API_KEY", "")
    base_url = env.get("OPENAI_BASE_URL", "")
    model = os.environ.get("OCTOS_MODEL") or env.get("MODEL", "")
    provider = os.environ.get("OCTOS_PROVIDER")
    if not provider:
        provider = "deepseek" if "deepseek" in base_url else "anthropic" if "anthropic" in base_url else "openai"
    key_env = "OPENAI_API_KEY"
    if provider == "deepseek" and api_key:
        env.setdefault("DEEPSEEK_API_KEY", api_key)
        key_env = "DEEPSEEK_API_KEY"
    elif provider == "anthropic" and api_key:
        env.setdefault("ANTHROPIC_API_KEY", api_key)
        key_env = "ANTHROPIC_API_KEY"
    elif provider not in ("openai", "deepseek", "anthropic") and api_key:
        env.setdefault(f"{provider.upper()}_API_KEY", api_key)
        key_env = f"{provider.upper()}_API_KEY"
    config = {
        "provider": provider,
        "model": model,
        "sandbox": {"allow_network": True},
        "memory": {"refresh": {"enabled": False}},
        # deepseek-v4 spends its default 4096 output budget on reasoning and
        # returns empty content; give it real headroom.
        "gateway": {"max_output_tokens": 65536, "llm_timeout_secs": llm_timeout_secs()},
    }
    if provider not in ("openai", "deepseek", "anthropic") and base_url:
        config["base_url"] = base_url
    reasoning = default_reasoning_for_model(model)
    if reasoning in ("none", "off", "disabled"):
        config["gateway"]["reasoning_effort"] = "none"
    elif reasoning in ("low", "medium", "high"):
        config["gateway"]["reasoning_effort"] = reasoning
    elif provider == "deepseek":
        config["gateway"]["reasoning_effort"] = "low"
    hooks = protected_hooks(protected_dirs)
    if hooks:
        config["hooks"] = hooks
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    env["OCTOS_CONFIG_DIR"] = str(config_dir)
    env.setdefault("OCTOS_DISABLE_STREAMING", "1")   # platform proxies reject SSE
    env.setdefault("OCTOS_DANGER_FULL_ACCESS", "1")  # the container is the sandbox
    env.setdefault("npm_config_registry", "https://registry.npmmirror.com")
    env.setdefault("NPM_CONFIG_REGISTRY", "https://registry.npmmirror.com")
    rules_file = BUNDLE_DIR / "EXTRA_RULES.md"
    if rules_file.is_file() and "OCTOS_ARC_EXTRA_RULES" not in env:
        env["OCTOS_ARC_EXTRA_RULES"] = rules_file.read_text(encoding="utf-8")[:8000]
    env["_ARC_PROVIDER"] = provider
    env["_ARC_MODEL"] = model
    env["_ARC_BASE_URL"] = base_url
    env["_ARC_KEY_ENV"] = key_env
    env["_ARC_LLM_TIMEOUT_SECS"] = str(llm_timeout_secs())
    return env


_CHAT_FLAGS_CACHE: dict[str, set[str]] = {}


def _chat_supported_flags(octos_bin: str) -> set[str]:
    if octos_bin not in _CHAT_FLAGS_CACHE:
        try:
            proc = subprocess.run([octos_bin, "chat", "--help"], capture_output=True, text=True, timeout=30)
            help_text = (proc.stdout or "") + (proc.stderr or "")
        except Exception:  # noqa: BLE001
            help_text = ""
        _CHAT_FLAGS_CACHE[octos_bin] = {
            flag for flag in ("--json", "--cwd", "--data-dir", "--sandbox", "--profile",
                              "--max-iterations", "--no-session-persistence") if flag in help_text}
    return _CHAT_FLAGS_CACHE[octos_bin]


def run_octos(octos_bin: str, cwd: Path, prompt: str, env: dict, data_dir: Path,
              timeout: int, max_iterations: int) -> tuple[bool, str]:
    """One non-interactive `octos chat` turn (fallback driver)."""
    flags = _chat_supported_flags(octos_bin)
    cmd = [octos_bin, "chat", "-m", prompt]
    if "--json" in flags:
        cmd.append("--json")
    if "--cwd" in flags:
        cmd += ["--cwd", str(cwd)]
    if "--data-dir" in flags:
        cmd += ["--data-dir", str(data_dir)]
    if "--max-iterations" in flags:
        cmd += ["--max-iterations", str(max_iterations)]
    if "--no-session-persistence" in flags:
        cmd.append("--no-session-persistence")
    if "--sandbox" in flags and env.get("OCTOS_DANGER_FULL_ACCESS") == "1":
        cmd += ["--sandbox", "danger-full-access"]
    if "--profile" in flags:
        cmd += ["--profile", os.environ.get("OCTOS_CHAT_PROFILE", "coding")]
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True,
                              timeout=timeout, errors="replace")
    except subprocess.TimeoutExpired:
        return False, f"octos timed out after {timeout}s"
    out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return False, f"octos exited {proc.returncode}: {out or (proc.stderr or '').strip()[-2000:]}"
    try:
        payload = json.loads(out)
        if isinstance(payload, dict) and payload.get("error"):
            return False, str(payload["error"])
        return True, str(payload.get("text", "")) if isinstance(payload, dict) else out
    except json.JSONDecodeError:
        return True, out[-4000:]


DRYRUN_FILES = """\
<<<FILE frontend/src/index.html>>>
<!DOCTYPE html><html><head><meta charset="utf-8"><title>dry run</title></head>
<body><!--NAV--><main data-testid="dryrun">dry run placeholder</main></body></html>
<<<END FILE>>>
<<<FILE backend/server.js>>>
const http = require('http'); const fs = require('fs'); const path = require('path');
const dist = path.join(__dirname, '..', 'frontend', 'dist');
const handler = (req, res) => { try {
  const file = path.join(dist, req.url === '/' ? 'index.html' : req.url.split('?')[0]);
  if (!file.startsWith(dist) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); return res.end('not found'); }
  res.writeHead(200, {'Content-Type': 'text/html; charset=utf-8'}); res.end(fs.readFileSync(file));
} catch (e) { res.writeHead(500); res.end('error'); } };
http.createServer(handler).listen(process.env.PORT || 3000);
process.on('uncaughtException', () => {});
<<<END FILE>>>
"""


class DryRunDriver:
    """OCTOS_ARC_DRYRUN=1: no kernel, no model. Every turn returns a fixed reply
    (file blocks for codegen prompts, a sentence otherwise) so the whole flow —
    tree order, mode selection, probes, acceptance, repair/budget logic, events —
    runs end to end for structural parity checks. Real-path behaviour is untouched."""

    def __init__(self) -> None:
        self.hooks: list = []
        self.turns = 0

    def run(self, prompt: str, timeout: int, monitor: TurnMonitor | None = None) -> tuple[bool, str]:
        self.turns += 1
        time.sleep(0.05)
        if "<<<FILE" in prompt:
            return True, DRYRUN_FILES
        if "page markup only" in prompt:
            return True, "<!DOCTYPE html><html><head><meta charset=\"utf-8\"></head><body><main>dry run</main></body></html>"
        return True, "dry run: no model call; nothing written."

    @contextmanager
    def without_tools(self):
        """codegen_turn runs inside this scope; without it every codegen tree
        aborted on its first node and the walk never reached the codegen path."""
        yield

    def end_scope(self, *args, **kwargs) -> None:
        pass

    def close(self, *args, **kwargs) -> None:
        pass


class PermanentProviderError(RuntimeError):
    """Account failures require external action, not another generation attempt."""


def permanent_provider_error(text: str) -> bool:
    lowered = text.lower()
    codes = re.findall(r"\bhttp(?:/\d(?:\.\d)?)?\s+(\d{3})\b", lowered)
    return any(code in {"401", "402", "403"} for code in codes) or any(term in lowered for term in (
        "insufficient_balance", "insufficient_quota", "quota exhausted", "balance is exhausted", "invalid_api_key",
        "authentication failed", "unauthorized"))


class OctosDriver:
    """stdio UI-protocol session (default) or one-shot chat turns.

    By default every turn gets a fresh session: the per-turn prompt already
    carries all the state the model needs, and a short, byte-stable prefix
    (system prompt + tool schemas) is what the provider's prefix cache keys on.
    """

    def __init__(self, octos_bin: str, cwd: Path, env: dict, data_dir: Path,
                 max_iterations: int, events_log: Path) -> None:
        self.mode = os.environ.get("OCTOS_DRIVER", "stdio")
        # "turn": new session every turn; "node": one session per requirement
        # node (design -> implement -> repairs share context); "run": one session.
        # Default "turn" since specs are quoted into every prompt: a repair turn
        # is self-contained, while a shared node session made each repair
        # request carry the whole implement history (v8-tb: 49 requests, 1.1M
        # prompt tokens for 7 repairs).
        self.session_scope = os.environ.get("OCTOS_SESSION_SCOPE", "turn")
        if os.environ.get("OCTOS_SESSION_PER_TURN") == "0" and "OCTOS_SESSION_SCOPE" not in os.environ:
            self.session_scope = "run"
        self.octos_bin = octos_bin
        self.cwd = cwd
        self.env = env
        self.data_dir = data_dir
        self.max_iterations = max_iterations
        self.events_log = events_log
        self._session = None
        self.monitor: TurnMonitor | None = None
        self.hooks: list = []  # profile hooks (protected-directory deny), set by the flow
        self.tools_disabled = False

    @contextmanager
    def without_tools(self):
        """Tool policy belongs to the kernel profile, so never reuse a profile across modes."""
        previous = self.tools_disabled
        if not previous:
            self.close()
        self.tools_disabled = True
        try:
            yield
        finally:
            if not previous:
                self.close()
            self.tools_disabled = previous

    def _log_event(self, method: str, params: dict) -> None:
        if method == "core/marker":
            log(f"[core-mod] {params.get('line', '')}")
        if self.monitor is not None and method in ("tool/started", "tool/completed"):
            try:
                self.monitor.observe(method, params)
            except Exception:  # noqa: BLE001 - guard must never break a turn
                pass
        try:
            with self.events_log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"method": method, "params": params}, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _get_session(self):
        if self._session is None:
            from octos_stdio import OctosStdioSession
            self._session = OctosStdioSession(self.octos_bin, self.cwd, self.env, self.data_dir,
                                              on_event=self._log_event)
            self._session.bootstrap_profile(
                provider=self.env.get("_ARC_PROVIDER", "openai"),
                model=self.env.get("_ARC_MODEL", ""),
                base_url=self.env.get("_ARC_BASE_URL") or None,
                api_key_env=self.env.get("_ARC_KEY_ENV") or None,
                hooks=self.hooks,
                tools_disabled=self.tools_disabled,
                llm_timeout_secs=int(self.env.get("_ARC_LLM_TIMEOUT_SECS") or 0) or None,
            )
            self._session.open()
        return self._session

    def run(self, prompt: str, timeout: int, monitor: TurnMonitor | None = None) -> tuple[bool, str]:
        self.monitor = monitor
        if self.mode == "chat" and not self.tools_disabled:
            fn = lambda remaining: run_octos(self.octos_bin, self.cwd, prompt, self.env, self.data_dir,  # noqa: E731
                                   remaining, self.max_iterations)
        else:
            fn = lambda remaining: self._run_stdio(prompt, remaining)  # noqa: E731
        try:
            ok, text = self._run_with_heartbeat(lambda: self._run_with_retries(fn, timeout))
        finally:
            self.monitor = None
            if self.session_scope == "turn":
                self.close()
        if monitor is not None:
            monitor.finish(text)
        return ok, text

    @staticmethod
    def _run_with_heartbeat(fn) -> tuple[bool, str]:
        """Run a turn in a thread, logging a keepalive every 30s (the runner
        kills silent processes)."""
        box: dict = {}

        def target() -> None:
            try:
                box["r"] = fn()
            except Exception as exc:  # pragma: no cover - defensive
                box["r"] = (False, f"turn raised: {exc}"[:500])

        th = threading.Thread(target=target, daemon=True)
        th.start()
        t0 = time.time()
        while True:
            th.join(30)
            if not th.is_alive():
                break
            log(f"[flow] turn still running ({int(time.time() - t0)}s elapsed)")
        return box.get("r", (False, "turn thread ended without result"))

    @staticmethod
    def _transient(text: str) -> bool:
        lowered = text.lower()
        if "octos turn timed out" in lowered or "octos timed out after" in lowered:
            return False  # our own wall-clock cap, not a provider hiccup: never replay the turn
        if permanent_provider_error(text):
            return False
        codes = re.findall(r"\bhttp(?:/\d(?:\.\d)?)?\s+(\d{3})\b", lowered)
        if codes:
            return any(code in {"408", "425", "429", "500", "502", "503", "504"} for code in codes)
        return any(k in lowered for k in (
            "temporarily unavailable", "rate limit", "timeout", "timed out",
            "connection reset", "overloaded", "failed to send", "streaming request"))

    def _run_with_retries(self, fn, timeout: float, attempts: int = 3) -> tuple[bool, str]:
        deadline = time.monotonic() + max(0, timeout)
        retry_deadline = None
        ok, text = False, "octos turn timed out"
        for attempt in range(1, attempts + 1):
            outer_remaining = (self.progress_deadline.remaining()
                               if getattr(self, "progress_deadline", None) else deadline - time.monotonic())
            remaining = min(outer_remaining, retry_deadline - time.monotonic()) \
                if retry_deadline is not None else outer_remaining
            if retry_deadline is not None:
                # A failed large wave should not replay the same oversized
                # request for another several minutes.  The outer recovery
                # window controls the series; this cap controls each fresh
                # request inside it.  The caller can then split the wave.
                retry_attempt = max(30, int(os.environ.get(
                    "OCTOS_ARC_TRANSIENT_ATTEMPT_SECONDS", "180")))
                remaining = min(remaining, retry_attempt)
            if remaining <= 0:
                break
            ok, text = fn(remaining)
            if ok or not self._transient(text) or attempt == attempts:
                break
            if retry_deadline is None:
                # Do not shorten a healthy first request. Once the provider has
                # failed, however, bound all fresh-session recovery attempts so
                # one node cannot occupy most of the dependency queue's budget.
                recovery = max(0, int(os.environ.get("OCTOS_ARC_TRANSIENT_RETRY_SECONDS", "240")))
                retry_deadline = min(deadline, time.monotonic() + recovery)
            wait = 30 * attempt
            pending = getattr(self, "upstream_pending", None)
            if callable(pending) and pending():
                # The kernel client timed out while the provider is still
                # generating this request. The replay joins that pending
                # completion; a backoff would only add idle time.
                wait = 1
            available = min(
                self.progress_deadline.remaining() if getattr(self, "progress_deadline", None)
                else deadline - time.monotonic(),
                retry_deadline - time.monotonic(),
            )
            if wait >= available:
                log("[driver] remaining turn budget cannot accommodate retry backoff")
                break
            log(f"[driver] transient error, retry {attempt + 1}/{attempts} after {wait}s: {text[:200]}")
            time.sleep(wait)
            self.close()
        return ok, text

    def _run_stdio(self, prompt: str, timeout: float) -> tuple[bool, str]:
        deadline = time.monotonic() + timeout
        try:
            session = self._get_session()
            session.progress_deadline = getattr(self, "progress_deadline", None)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False, "octos turn timed out"
            result = session.run_turn(prompt, timeout=remaining)
            if not result[0] and "octos turn timed out" in result[1].lower():
                # A persistent session must not keep generating after its lease ends.
                self.close()
            return result
        except Exception as exc:  # noqa: BLE001
            self.close()
            if self.tools_disabled:
                return False, f"tool-free stdio driver error: {exc}"[:1000]
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False, "octos turn timed out"
            chat_ok, chat_text = run_octos(self.octos_bin, self.cwd, prompt, self.env, self.data_dir,
                                           remaining, self.max_iterations)
            if chat_ok:
                return True, chat_text
            return False, f"stdio driver error: {exc}; chat fallback: {chat_text}"[:1000]

    def end_scope(self, scope: str) -> None:
        """Called by the flow at node boundaries; closes the session when the
        configured scope ends."""
        if scope == self.session_scope or self.session_scope == "turn":
            self.close()

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None


# ---------------------------------------------------------------- prompts
#
# Prompt text is deliberately static (no timestamps, fixed section order) so
# that identical turns share the provider's prefix cache.

# Measured on cloud 6e82a7ff571c's own app (32 official specs, 3 runs each, a
# pristine store per run). Its note actions were `visibility: hidden; opacity: 0`
# revealed on hover, and every one of the twelve graded failures was a note-card
# action, so a clause telling the model not to hide them looked obvious. It is
# wrong. Baseline 16/16/16; fading opacity alone 15/14/15; leaving the controls
# always visible 15/15/15. Both alternatives fixed REQ-2.5.4 and REQ-2.7.4 and
# broke REQ-2.6.1, REQ-2.7.2 and REQ-2.8.3. Hiding an item's controls until the
# pointer arrives is what keeps a name-based lookup landing on the hovered card,
# which is what the per-item bullet below already says. Do not add a clause
# against hover-hiding without measuring it on a real app first.
UI_CONTRACT_CORE = """\
UI behavior follows the requirement and the current application:
- Use semantic controls, accessible names and labels appropriate to each action. Preserve required routes, text, visibility, enabled states and interactions. Choose input types and validation behavior from the requirements; hidden views, dialogs and dynamic rendering are allowed when needed.
- Keep IDs unique and label associations correct. Repeated text and links can be valid. If an actual locator is ambiguous, inspect its scope and the intended interaction instead of deleting unrelated content.
- A control repeated once per item needs an accessible name that says which item it acts on. Identical names across items leave a name-based lookup resolving to an arbitrary one, and a control that stays exposed after the pointer leaves its item makes that worse.
- Keep simultaneously available controls independently operable by pointer and keyboard. When adding controls, update their shared layout so their hit areas do not overlap and intercept each other's input.
- Derive state ownership and persistence from requirements: distinguish per-view, per-session and shared data. Do not reset persisted user data on startup. For persistent data, initialize required records only for a new store or an explicit migration. Later startups must preserve user edits, deletions and archive state; a missing record does not mean the store is new. Reset data only when the requirements explicitly demand it. Provide a loading state when initialization is asynchronous.
- Treat required built-in/default records and their accessible navigation names as invariants when the requirements say they are fixed. If users may rename or remove other records, distinguish those from the protected record in both server validation and UI; do not let an edit to shared data silently rename an unrelated required destination.
- Treat a UI action as a state transition: mount usable editor/dialog controls synchronously before the first await. Isolate background controls for modal dialogs, not ordinary inline editors or non-modal menus. A browser click does not await an async event listener. After a mutation, await persistence and refresh (or apply a consistent optimistic update) before exposing stale state as final; handle failure without losing the user's edits. Derive Save/Cancel/autosave transitions from requirements; cancelling a draft must not commit it.
- For nested editors, menus and dialogs, define which layer owns outside click, Escape and focus transitions. A child's Escape should not close or save its parent unless that is the required action. A controlled dialog's onOpenChange must not turn an incidental close/open signal into a premature commit; verify the editor remains mounted and editable after its entry gesture.
- Use local assets where practical. Add styling, animation, asynchronous updates or external services when required; keep interactions responsive and report failures clearly.
- Specify ownership/keys and atomic command effects (including undo) from requirements; related mutations must commit together in one store update or database transaction, not separate file writes. Validate authoritatively on the server. Date-only values are calendar dates, not UTC instants; persist expiry deadlines across reloads, anchor countdowns to server time, and use a task-provided reference date only when explicitly required. Keep editable rich-text regions labeled (role=textbox, aria-multiline=true); use native select for a native selection contract, not a visually similar custom menu.
- Use supplied visual references when relevant. Public tests are examples of required behavior, not permission to hardcode test outcomes or omit untested requirements.
"""

# Bump when APP_DESIGN_PROMPT or the design schema changes: a stored design made
# with another version is regenerated, not reused.
APP_DESIGN_PROMPT_VERSION = "19-schema-repair-active-ownership"

COLLECTION_MIGRATION_CONTRACT = (
    "Installed helper interfaces are fixed: backend/lib/store exports read, write, update, migrate, onReset, reset; "
    "backend/lib/collection exports collection. Frontend shared/request.js exports requestJson (raw JSON). "
    "Reuse these exact APIs; do not invent load/save aliases or plan replacement helpers. "
    "Assign one canonical module per collection: it owns initial records, migrations and shared access. "
    "Reuse that owner across routes; do not create independent fallbacks for the same store. "
    "Trace explicitly required initial records to requirements, not arbitrary test examples. "
    "Verify fresh-store prerequisites and existing-store upgrades separately; restarts must preserve user edits/deletions.\n"
    "migrations is an array of objects with unique nonempty string id and synchronous up(data), not functions. "
    "Optional collection(...) migration up(data) receives a storage OBJECT; the record array is data.items, "
    "NOT data itself. Mutate data.items synchronously, return undefined, and preserve __arcMigrations. "
    "Direct store.migrate receives its own fallback-shaped object. Do not change these shared APIs.\n")

# Router/composition modules every feature wave may extend; always quoted whole.
COMPOSITION_FILES = frozenset({"App.jsx", "App.tsx", "app.js", "router.js"})

APP_DESIGN_SYSTEM = "You are the architect of a small web application. Reply with one JSON object only."

APP_DESIGN_PROMPT = COLLECTION_MIGRATION_CONTRACT + """\
Design the application that satisfies this whole requirement tree (do NOT implement anything):

{outline}

Preserve the installed stack. Fresh complex applications use React/Vite/Radix/React Router with local bundled assets and Express routes. Existing applications keep their architecture. frontend/src/index.html is the shell; backend/server.js is a small Express entry serving frontend/dist and registering backend/routes/<area>.js modules; shared persistence lives in backend modules. Reuse the provided request/interaction helpers and cohesive React components; do not invent another DOM/widget framework. Use one owner per draft/dialog state, stable record IDs, and ignore stale async responses. Render shared navigation consistently; preserve focus and drafts during unrelated updates.
Reply with ONE JSON object (at most 150 lines, no prose) that every requirement will be implemented against:
{{"data_model": {{"collection": {{"field": "type"}}}},
 "routes": [{{"method": "GET|POST|PUT|DELETE", "path": "/api/...", "purpose": "one line", "requirements": ["REQ-..."]}}],
 "pages": [{{"path": "/...", "purpose": "one line", "requirements": ["REQ-..."]}}],
 "modules": [{{"path": "frontend/src/...|backend/routes/...", "owns": ["cohesive page/layout/editor/API concern"]}}],
 "contracts": [{{"requirements": ["REQ-..."], "invariants": ["ownership/key scope", "command: preconditions -> atomic effects and undo", "draft/save/cancel semantics", "date-only/clock/deadline rules", "control and validation semantics"]}}],
 "notes": "session handling, seed data, versioned migrations, validation conventions, naming conventions"}}
Name every collection, field, route and page once and consistently; requirements that share data must share the record shape. For each HTTP method, place literal paths before overlapping parameter paths (for example, DELETE /api/items/trash before DELETE /api/items/:id). In notes, state the shared interaction lifecycle: when controls become usable, what commits an edit, and when the list reflects the committed record. Do not enumerate test-only cases.
For each lifecycle view, specify which records the API returns and which filters the client applies; a client cannot recover records already excluded by the server. Specify absent versus false query values, compatible filter combinations, and inverse transitions (remove/restore, assign/unassign). For composite editors, state whether selection commits immediately or on Save, how Done/Cancel/Escape behave, and which owner retains the draft after a failed save. Do not invent lifecycle states not required by the task.
In contracts, identify required built-in records and stable accessible destinations separately from user-editable records. For nested menus/dialogs, assign ownership of Escape, outside click and focus changes; closing a child must not commit or dismiss its parent unless explicitly required. Include a short interaction sequence that a full-suite run should preserve after another feature mutates shared state.
Give every expanded editor a visible completion action: Save for explicit commits or Close/Done for autosave; Escape/outside click supplements that action, never replaces it. Moving focus within the editor is not completion. Distinguish raw response JSON from Response objects; no helper-invented result envelope unless explicitly implemented on the backend.
In notes, preserve required entry gestures and action placement (record click, direct action, menu action). Distinguish available catalogue choices from initially selected values; optional actions must follow user intent, not unconditional fixture-derived defaults.
Identify shared layout and component owners: routes with the same navigation/header reuse one layout; repeated record editors and actions reuse one implementation. Put those owners in modules. Every atomic requirement ID must appear in at least one route, page or contract requirements list. Give every API resource prefix exactly one backend route module (for example all /api/<resource>/... handlers in backend/routes/<resource>.js, listed in modules) and never register the same method and path in two modules; a feature extends its owner module instead of appending handlers to an unrelated one. App.jsx owns routing/composition; normally keep each application module below 12000 characters by extracting cohesive pages, reusable record views/editors and API/state modules before they become a monolith. Split layouts only when requirements differ; do not create pass-through modules merely to meet a number. Keep this concrete and minimal, not a configurable application framework.
"""

CODEGEN_SYSTEM = """You write complete, minimal web apps. Reply only with <<<FILE relative/path>>> ... <<<END FILE>>> blocks using exact delimiters, or exactly <<<NO CHANGE>>> when already satisfied.
Return each changed file once, with complete contents. No EDIT blocks, diffs, unchanged files or iterative self-review. Implement the active requirements and their prerequisites; the shared design is a contract, not a request to regenerate every other feature. Preserve existing behavior. Stop immediately when complete."""

CODEGEN_RULES = """\
Files: frontend/src/index.html is a small shell; put substantial CSS/JS in local modules. backend/server.js serves ../frontend/dist on process.env.PORT||{port}; put routes in backend/routes/<area>.js.{ports} Keep the entry stable. For each HTTP method, register literal paths before overlapping :parameter paths (DELETE /api/items/trash before DELETE /api/items/:id). For pushState links set frontend/package.json arc.spa=true. Preserve the installed frontend stack, exact dependency versions and lockfile; add task-required packages to the correct package.json. Local assets only: no CDN URLs or remote browser imports. npm install may download packages. JSX/TSX must be bundled, not copied to dist.
Packages: update package.json and the build script only for required dependencies.
Data: seed only a new store or migration; preserve edits/deletions across restarts. Use atomic aggregate updates for related state and server-side validation. Persist deadlines, distinguish calendar dates from timestamps. Label rich-text textbox regions; use native select when native selection is required.
Rules: handle general inputs and preserve working behavior. Use accessible controls and unique IDs. Per-item actions target their item; hidden menus must not intercept input. Use distinct names for menu triggers versus destinations. Put each named control where the requirement places it (page/settings/menu/dialog), exact text; a control said to show a value (username) shows it. No two visible controls with the same role and name. Closing an editor saves pending fields/options only if required; explicit Cancel discards the draft. Navigation renders the selected view; visual options visibly change the item. Derive behavior from requirements, not test outputs.
Async: clicks do not await handlers. Mount usable editor/dialog controls before the first await; isolate background only for modal overlays. Await save and list refresh (or update optimistically); retain edits on failure.
Output: complete FILE blocks for changed files only. Never rewrite an existing file without its full current source quoted here; request that path. Keep package and lock versions aligned. No changes: <<<NO CHANGE>>>.
"""

GENERIC_TEMPLATE_NOTE = COLLECTION_MIGRATION_CONTRACT + """\
JSX (including Context providers) needs .jsx/.tsx, not .js/.ts; update imports. Fix source parse errors before changing build config.
Collection API: const {collection} = require('../lib/collection'); do not call the module object. Pass initial: [{id:'example'}], NOT initial: {items:[...]}. Only migration callbacks receive the envelope {items:[...]}. Correct callers rather than changing shared exports. Invalid stored shapes require an explicit preserving migration, never deletion/reset of persisted data.
Shared task-neutral files already exist. backend/server.js is an Express 5 entry: JSON/form parsers, frontend/dist, and automatic backend/routes/*.js registration. Route modules export (app) => { app.get/post/patch/delete(...); }; use req.body/params, res.json/status. Register literal paths before :parameter paths; keep server.js unchanged for ordinary routes. Each METHOD+path is registered once across all route files: change an existing route in the file that owns it. Express 5 wildcards are named: '/files/*path' gives req.params.path (an array of segments); req.params[0] is undefined.
From backend/routes/: require('../lib/store') exports read(name,fallback), write(name,value), update(name,fallback,synchronousChange). Prefer require('../lib/collection').collection(name,{idKey,initial,migrations,normalize}) for ordinary CRUD instead of regenerating persistence; it exports all/list/get/create/patch/remove/transact. initial applies only to a new store; persist changes to existing data via versioned migrations up(data) mutating data.items synchronously, preserving __arcMigrations. Never reseed deleted records. Optional normalize(record) returns an object with the SAME id on reads/create/patch and before/after transact; choose defaults from requirements, not fixtures. Reads do not persist normalization. transact(items => result) synchronously mutates one collection in one write; duplicate/missing IDs and async callbacks fail. Atomicity is single-store/single-process only; cross-store effects need one aggregate or transactional storage. require('../lib/errors').HttpError(status,message) gives explicit 4xx {error:message}; 5xx details are hidden. Define domain validation, authorization and messages from requirements. Seed records live in code (collection initial); backend/data/ is runtime state (tests run on a private copy; it is deleted before grading), so never hand-write it. Module-level in-memory state (undo stacks, caches) must clear on require('../lib/store').onReset(() => ...).
Optional require('../lib/query') exports optionalBoolean(value) (missing/true/false, invalid => 400) and matchesFlags(record,flags) (strict booleans, undefined ignored). Whitelist fields, resolve view defaults once, combine filters, and enforce ownership separately; clients cannot recover server-excluded rows.
Frontend ./shared/request.js exports requestJson(url,options): raw parsed JSON (empty successful response => null), or throws an Error with server message and numeric status on HTTP/JSON failure; no Response methods or {ok,value} envelope. Plain object/array request bodies are JSON-encoded; FormData/URLSearchParams bodies keep their native encoding. React uses main.jsx/App.jsx. Plain scaffold uses app.js, shared/dom.js (escapeHtml) and shared/router.js (startRouter(render), arc.spa=true). Optional build.mjs/vite.config.mjs: build is "node build.mjs"; bundle JSX/local assets. frontend/public copies to dist root. Define fields, pages, sessions and seed data from the task. Do not output FILE blocks for unchanged shared helpers.
"""

# Text-only turns outside the build-turn cap (see Flow.note_turn).
NON_BUILD_TURN_LABELS = ("derived scenario review", "derived failed-spec review", "application design")

TASK_NEUTRAL_HELPERS = {
    "backend/lib/arc.js": "arc-runtime.js",
    "backend/lib/query.js": "query.js",
    "frontend/src/shared/interactions.jsx": "react-interactions.jsx",
    "backend/lib/store.js": "store.js",
    "backend/lib/collection.js": "collection.js",
    "backend/lib/errors.js": "errors.js",
    "frontend/build.mjs": "frontend-build.mjs",
    "frontend/vite.config.mjs": "vite.config.mjs",
    "frontend/src/shared/dom.js": "frontend-dom.js",
    "frontend/src/shared/request.js": "frontend-request.js",
    "frontend/src/shared/router.js": "frontend-router.js",
}


def seed_contract_text(flow) -> str:
    """The resolved seed contract for prompts ("" without a resolved conflict)."""
    resolution = getattr(flow, "seed_resolution", None)
    return seed_contract_note(resolution) if isinstance(resolution, SeedResolution) else ""


def read_text_or_empty(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def unchanged_task_neutral_helpers(output_dir: Path, paths: set[str]) -> bool:
    """Only defer writes to installed, still-pristine shared infrastructure."""
    if not paths or not paths <= TASK_NEUTRAL_HELPERS.keys():
        return False
    try:
        return all((output_dir / rel).read_text(encoding="utf-8") ==
                   (BUNDLE_DIR / "blueprints" / TASK_NEUTRAL_HELPERS[rel]).read_text(encoding="utf-8")
                   for rel in paths)
    except OSError:
        return False

CODEGEN_TASK = """\
Requirement {node_id}: {description}

Public acceptance example (implement the full requirement):
{spec}
Before returning files, trace each supplied GIVEN -> WHEN -> THEN: prerequisites/explicit initial records ->
handler/API/state -> visible/persisted/error outcome. Fix missing links; never invent seed data from navigation setup.
{size_rule}
"""

CODEGEN_PROMPT = CODEGEN_RULES + "\n" + CODEGEN_TASK

CODEGEN_SIZE_SMALL = 'Prefer a small implementation, but do not omit required behavior, accessibility, styling or validation to meet an arbitrary line count.'
CODEGEN_SIZE_FULL = "Keep the implementation concise while preserving all required behavior and the existing architecture. Derive navigation, authentication, storage and validation from the requirements. Public tests illustrate contracts; handle other valid inputs too. Do not force a navigation placeholder, cookie name, redirect, validation message or rendering strategy. Fix actual ambiguous controls in their intended scope without deleting legitimate repeated links or text. Keep simultaneously available controls independently operable by pointer and keyboard. When adding controls, update their shared layout so their hit areas do not overlap and intercept each other's input."

TRUNCATED_CODEGEN_RETRY = """\
The previous codegen reply exceeded its output limit. Inspect current sources: some complete files may already have been applied. Finish only the missing changes and do not reproduce unchanged modules. If already satisfied, reply exactly <<<NO CHANGE>>>.
"""

TRUNCATED_RETRY = """\
YOUR PREVIOUS RESPONSE WAS TRUNCATED BY THE OUTPUT LIMIT. Inspect the current files before continuing; do not assume the previous response was applied. Use tools to make the smallest targeted edits needed for this requirement. Preserve existing behavior and avoid re-emitting large unchanged files. Create missing files only when needed, one file at a time. Verify the affected behavior and finish.
"""

# Tiny-spec tier (OCTOS_ARC_TINY_SPEC_CHARS, default 1500; OCTOS_ARC_TINY=0 disables): the prompt is the
# spec's own statements only, the reply is one HTML file, the server is a fixed harness scaffold (no task
# logic), thinking is off. First-pass failure falls back to the compact codegen tier for the same node.
TINY_SYSTEM = 'Reply with HTML only. Honor supplied selectors and accessible names. getByTestId targets data-testid; it does not target id.'

TINY_PROMPT = """\
Task and public acceptance example (implement general behavior):
{spec}
Reply with the page markup only: a concise self-contained page implementing the full task, including required styling, controls and state. Do not hardcode test outputs or load browser assets from a CDN.
"""

TINY_PROMPT_EVOLUTION = """\
Current index.html:
{page}
Task and additional acceptance example (preserve existing behavior):
{spec}
Reply with the complete updated page markup only: a concise self-contained page implementing the full task, including required styling, controls and state. Do not hardcode test outputs or load browser assets from a CDN.
"""

TINY_SERVER_JS = """\
const http = require('http'); const fs = require('fs'); const path = require('path');
const dist = path.join(__dirname, '..', 'frontend', 'dist');
const handler = (req, res) => {{ try {{
  const url = req.url.split('?')[0];
  const name = url === '/' ? 'index.html' : url.replace(/^\\//, '');
  const candidates = [name, name + '.html'].map(n => path.join(dist, n));
  const file = candidates.find(f => f.startsWith(dist) && fs.existsSync(f) && fs.statSync(f).isFile());
  if (!file) {{ res.writeHead(404); return res.end('not found'); }}
  const type = file.endsWith('.js') ? 'application/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html; charset=utf-8';
  res.writeHead(200, {{ 'Content-Type': type }}); res.end(fs.readFileSync(file));
}} catch (e) {{ res.writeHead(500); res.end('error'); }} }};
http.createServer(handler).listen(process.env.PORT || {port});
if (process.env.ARC_EXTRA_PORTS !== '0') for (const p of {extra_ports}) if (String(p) !== String(process.env.PORT || {port})) http.createServer(handler).listen(p);
process.on('uncaughtException', () => {{}}); process.on('unhandledRejection', () => {{}});
"""


def looks_like_markup(text: str) -> bool:
    """A bare page or page fragment (the tiny tier asks for markup without doctype/head)."""
    return bool(re.search(r"<(html|body|main|div|section|form|button|script|span|p|h[1-6]|input|label|ul|table)\b", text, re.IGNORECASE))


def strip_code_fences(text: str) -> str:
    text = text.strip()
    m = re.search(r"```[a-zA-Z]*\n(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text


def compact_spec_lines(text: str) -> str:
    """The spec's statements without imports, blank lines, `await` and closing
    braces — what a page must satisfy, in the spec's own words."""
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("import ", "//", "/*", "*")) or line in ("});", "})", "}"):
            continue
        line = re.sub(r"^await\s+", "", line)
        line = re.sub(r"^test\((['\"])(.*?)\1,\s*async\s*\(\{[^}]*\}\)\s*=>\s*\{$", r"test: \2", line)
        out.append(line)
    return "\n".join(out)


UI_CONTRACT_DATA = """\
- Treat examples as examples unless the requirement explicitly identifies initial records or enumerated values. Implement general handling for other valid inputs. Preserve required initial data without overwriting existing user data; do not invent broad lists or fixed sample accounts.
- Give each collection one canonical owner for initialization, migrations and shared access. Check explicitly required initial records on an empty store; check upgrades separately on an existing store, preserving user edits and deletions. Changing initial/fallback data is not a migration. Do not maintain competing fallbacks in separate routes.
"""

UI_CONTRACT_SESSION = """\
- Derive authentication routes, redirects, labels and session lifetime from the requirements and existing app. Keep authentication state isolated between users; preserve sessions only as required. Failed authentication must not create a session or mutate protected data. Choose error disclosure appropriate to the security requirements.
- Persistence is not a UI notification. Shared React state needs state/context or a subscribed external store, not storage reads alone. Check login/logout update mounted consumers without reload, reload restores only intended state, and failure does not publish success. Browser-stored profile fields are not server authorization.
"""

UI_CONTRACT = UI_CONTRACT_CORE + UI_CONTRACT_DATA + UI_CONTRACT_SESSION  # full set (multi-node tasks)

PERFORMANCE_CONTRACT = """\
Performance and robustness:
- Measure slow operations using observed timings and the configured runtime budgets; do not assume a fixed CPU slowdown or browser count. A timeout can reflect a missing element, incorrect state or an unresolved request; inspect the actual failure before changing performance settings.
- Keep request handlers responsive and avoid unnecessary work. Do not introduce password-hashing implementations or reduce cryptographic strength to improve timings. Follow the required authentication behavior, using an existing authentication service when available; do not replace authentication with plaintext password storage or bypass credential checks.
- Set cookie flags, scope and lifetime from the deployment protocol and session requirements. Use HttpOnly for session cookies and Secure on HTTPS; do not hardcode a host or lifetime. Preserve required client-side interactions and persistent storage semantics.
"""

ARCHITECTURE_CONTRACT = """\
Runtime integration:
- Resolve relative imports from the importing file's directory, not the project root; reuse the exact exported helper API. Do not add extra parent segments or change shared exports to fit an incorrect caller.
- Preserve the platform contract: frontend/ has npm run build producing frontend/dist/; backend/ has npm start and reads PORT (default {port}). Within that contract, preserve the existing application architecture and choose libraries or storage appropriate to the requirements and available environment.
- Keep every source file under 12000 characters (about 300 lines). A page or route module that would grow past that is split by feature into sibling modules (pages/<area>/<Feature>.jsx, routes/<area>-<feature>.js) that the area module imports or the router mounts; App.jsx holds only imports and <Route> entries. Never put every feature of an area into one file.
- Preserve the installed stack and exact dependency pins. Fresh complex apps use React/Vite/Radix/React Router and Express routes; reuse the installed components instead of inventing a custom widget framework. Existing apps keep their architecture. Use native semantic controls and local libraries only for actual requirements. Declare dependencies and make npm run build produce all pages and assets. Browser pages must load scripts, styles, fonts and media from local output, never a CDN or remote import. Registry downloads during npm install are allowed.
- Handle expected request errors with appropriate responses, including 404 for missing resources. Log unexpected failures; do not suppress uncaught exceptions and continue serving potentially corrupt state. Preserve data integrity and use the runtime's recovery mechanism.
"""

VERIFY_FULL = """\
Verify briefly before you finish — the harness runs the official acceptance tests for this node right after your turn and hands you the failures, so do not build your own test suite: `npm run build` in frontend/, start the backend with `ARC_EXTRA_PORTS=0 PORT={smoke} npm start`, one curl per new endpoint (one success, one error case), stop the server.
"""

VERIFY_MINIMAL = """\
You have no shell in this turn. The harness runs `npm run build`, starts the backend and runs the official Playwright specs after your turn, then supplies any failures. Work within the configured request and output budgets. Preserve the existing application structure and create or edit the files needed by the requirements; do not combine unrelated modules merely to reduce file count. Use the supplied file listing and source evidence first, and inspect additional files when needed to resolve uncertainty. Batch independent small edits where practical, split changes that would exceed the response budget, and avoid rereading unchanged files without a reason. Check syntax and imports before finishing, then give a brief summary.
"""

PORT_RULES = """\
Ports: run your own smoke servers ONLY with `ARC_EXTRA_PORTS=0 PORT={smoke} npm start` (port {smoke}). NEVER bind port {port} — the runner watches it and terminates the run. Stop every server you started before you finish. Do not run git; the harness commits.
For a background server in a one-shot shell, redirect the entire command group, including stdin, so descendants cannot hold the tool's capture pipes open:
```sh
(cd backend && exec env ARC_EXTRA_PORTS=0 PORT={smoke} npm start) < /dev/null > smoke-server.log 2>&1 &
echo $!
```
Set the shell tool workdir to the application directory and run this command unchanged. Keep every cd inside the redirected parentheses; prepending cd ... && outside them creates another background shell that retains the capture pipes. Retain the printed PID for cleanup; inspect smoke-server.log and confirm HTTP readiness before testing. Do not assume a successful background launch means the app is ready. Rebuild frontend/ after source changes. Stop your server before ending the turn so the harness can start its own.
"""

SKELETON_PROMPT = """\
Build the skeleton of a full-stack web application in the current working directory. The requirement tree is at {req_dir} (skim it; individual features come in later turns).

""" + ARCHITECTURE_CONTRACT + """
{tests}
Steps: create frontend/ and backend/ as specified with a home page and a health endpoint, seed the JSON store, run `npm run build` in frontend/, start the backend with `ARC_EXTRA_PORTS=0 PORT={smoke} npm start`, `curl http://127.0.0.1:{smoke}/` to confirm the page is served, then stop it.
""" + PORT_RULES

NUDGE_PROMPT = """\
You ended your last turn before creating any files. Stop analysing. In your very next actions CREATE the project files with your file-writing tools: frontend/package.json (build script), the frontend page sources, backend/package.json (start script) and the backend server with the JSON store and seed data. Do not describe the plan — write the files now.\
"""

DESIGN_PROMPT = """\
Design — do NOT implement yet — requirement node {node_id} of the web application in the current directory.

{node_spec}
{ancestors}
{tests}
Read the acceptance spec files for this node in full and the existing code they will exercise. Then write ONE JSON object (at most 80 lines) to the file .arc/design/{node_id}.json AND repeat it in your reply inside a ```json fence. Shape:
{{"routes": [{{"method": "POST", "path": "/api/...", "request": {{}}, "response": {{}}, "errors": []}}],
 "pages": [{{"path": "/...", "elements": [{{"role": "textbox|button|link|combobox|checkbox|radio|alert", "name": "exact accessible name", "notes": ""}}]}}],
 "data_model": {{"collection": {{"field": "type"}}}},
 "files": ["backend/server.js", "frontend/src/..."],
 "notes": "validation rules, session handling, seed data, performance decisions"}}
Copy every accessible name verbatim from the specs. Keep App.jsx for routing/composition; when the planned feature would make one application module exceed roughly 18000 characters, list cohesive page/component/state modules instead of one monolith. Do not split tiny cohesive code. This is a reading turn: use only file reading, listing and grep — no builds, servers, curl or other shell commands — and do not create or modify any other file.\
"""

NODE_PROMPT = """\
{preamble}
{node_spec}
{design}{ancestors}
{tests}
{ui}{performance}
{verify}
""" + PORT_RULES

NODE_PREAMBLE_EXTEND = """\
Implement requirement node {node_id} in the existing application (frontend/ built by `npm run build` into frontend/dist/; backend/ started by `npm start` with PORT). Extend the app; do not rewrite or break existing features. Use existing packages when suitable; add a declared dependency only when it simplifies or enables the requirement. Never load browser assets from a CDN.
"""

NODE_PREAMBLE_CREATE = """\
Build a full-stack web application in the current working directory that implements requirement node {node_id} (the whole requirement tree is at {req_dir}; further nodes, if any, come in later turns — leave room for them but implement only this one).

""" + ARCHITECTURE_CONTRACT + """
Mandatory files (all in this turn): frontend/package.json (with a working production `build` script), frontend page sources, backend/package.json (with `start` and any needed dependencies) and backend/server.js. Keep all browser assets local in frontend/dist/ after the build.
"""


INLINE_DESIGN_NOTE = """\
Before writing code, write your design for this node as ONE JSON object to .arc/design/{node_id}.json ({{"routes": [...], "pages": [{{"path", "elements": [{{"role", "name"}}]}}], "data_model": {{}}, "files": [...], "notes": ""}}; accessible names copied verbatim from the specs), then implement it.
"""

EVOLUTION_NOTE = """\
This is an EXISTING application that already passed its previous acceptance tests. Current sources:
{listing}
Read the files you need before changing them, keep every existing route, label and behaviour intact, and change only what this node requires.
"""

CODEGEN_REPAIR_SUFFIX = """
Use the supplied acceptance specification and helpers below as read-only evidence. Preserve unrelated behavior. The harness executes acceptance after your response.
{spec}
"""

REPAIR_PROMPT = """\
Classify the observed failure before editing: build/load, runtime exception, HTTP failure, missing requirement precondition, stale UI, or locator timing/semantics. A timeout alone cannot distinguish these. Compare prior actions, responses, the rendered snapshot and any persisted-store change summary. Store changes describe the whole run, not which test caused them. Keep unknown causes unknown; combine failures only with concrete shared exception/source/data-owner/locator-gate evidence, not a common helper line. When a quoted spec explicitly selects a role and accessible name, that role/name is part of the interaction contract: use a native control that matches it instead of overriding the evidence with a preferred semantic element. When no requirement or spec selects a role, do not change semantics merely because a generic helper tried a fallback. Check storage-to-state-to-consumer updates without reload; verify fresh and existing stores separately without resetting data.
Fix frontend/ and/or backend/ so the failing tests listed below pass without breaking the passing ones. Work within the configured request budget. Use the supplied evidence to identify the cause, read relevant sources when needed, and make focused edits. For a failed post-action assertion, trace the preceding actions and identify the element and record actually acted on. With repeated controls, inspect locator scope, ordering, visibility, and hover/focus state before assuming a storage or rendering failure. Preserve keyboard access and the required interaction semantics when resolving ambiguity. Preserve behavior beyond the tested inputs. The harness rebuilds and re-runs the official tests right after your turn. The spec files are read-only ground truth.
If one behavior passes alone but fails in the suite, inspect shared-state mutations and protected default records before changing selectors. For an editor that disappears or saves old content, inspect its entry click, onOpenChange, nested menu Escape and focus transitions in order. Under a hard request cap, prioritize one causal source edit with existing evidence before broad additional reading; a diagnosis with no changed source cannot be verified by the next acceptance run.
For persistent data, initialize required records only for a new store or an explicit migration. Later startups must preserve user edits, deletions and archive state; a missing record does not mean the store is new. Reset data only when the requirements explicitly demand it.
""" + PORT_RULES + """
{sources}
The official acceptance tests for requirement node {node_id} just ran against your app: {passed}/{total} passed. Failing tests (Feature / where it failed / what was observed / the last steps before failure):
{failures}
{test_location}
{corrections}{slow}
"""

DERIVED_REPAIR_PROMPT = (REPAIR_PROMPT.replace(
    "The harness rebuilds and re-runs the official tests right after your turn. "
    "The spec files are read-only ground truth.",
    "The harness rebuilds and re-runs generated acceptance tests after your turn. "
    "These specs are protected implementation evidence; requirements.yaml is the behavior authority. "
    "A disputed or unreviewed generated assertion must not drive application repair.")
    .replace("The official acceptance tests", "The generated acceptance tests"))

COMPLETENESS_PROMPT = """\
Requirement completeness check for {node_id}. The derived Playwright checks for this requirement only prove that its
entry points exist; they cannot judge the behavior below. Verify it yourself against the running app and fix
every gap you find, preserving all other features:
1. `npm run build` in frontend/, then start the backend with `ARC_EXTRA_PORTS=0 PORT={smoke} npm start`.
2. For EACH scenario below: reproduce it end to end (curl the API and inspect the built page/DOM); confirm every
   quoted control name, role, value and message exists exactly as written; confirm the result persists after a
   reload of the same page state.
3. Fix confirmed gaps with focused edits; do not rewrite unrelated files. Stop every server you started.
{contract}
{ui}"""

FINAL_CHECK_PROMPT = """\
Final end-to-end check of the web application in the current directory:
1. `npm run build` in frontend/ — fix any error.
2. Kill leftover servers, start the backend with `ARC_EXTRA_PORTS=0 PORT={smoke} npm start`, confirm `curl http://127.0.0.1:{smoke}/` serves the app and every API endpoint answers (success and error cases).
3. Audit required flows and states against the contracts below. Check accessible names, unique IDs and correct label associations. Resolve observed locator ambiguity in its intended scope; repeated text and destinations can be legitimate.
{tests}
{ui}{performance}
""" + PORT_RULES

REHEARSAL_REPAIR_PROMPT = """\
The app failed the pre-grading startup rehearsal. The runner executes exactly:
1. cd frontend && npm install && npm run build   (must exit 0)
2. cd backend && npm install && npm start        (must bind PORT and stay up)
Rehearsal error:
{error}
Fix the project so this sequence works (typical causes: a require() path that does not match a real file, a file referenced but never written, a startup syntax error, a dependency missing from package.json). Verify: build the frontend, start the backend with `ARC_EXTRA_PORTS=0 PORT={smoke} npm start`, confirm it binds, stop it. Never bind {port}. Write the fix now.\
"""

DERIVED_SPECS_NOTE = (
    "NOTE: the specs below were derived from requirements.yaml by the harness (mechanical compilation plus "
    "model proposals validated against the requirement's own literals); they are NOT the official tests. "
    "Some cases are unreviewed, disputed, smoke-only, or skipped. The requirement text is authoritative: "
    "do not change product behavior just to satisfy a generated assertion that conflicts with it. "
    "Implement the full requirement, including branches absent from these examples.\n")

ACCEPTANCE_TESTS_PROMPT = """\
PUBLIC ACCEPTANCE TESTS (examples to validate the full requirement; report conflicts instead of silently discarding requirements) live under {tests_dir}. Files: {files}. They define routes, hrefs, accessible names, option labels, exact texts, error wording and action order. Never modify, copy or delete them.
"""

INLINE_SPEC_HEADER = """\
The spec files are quoted below in full — do NOT spend tool calls reading them or the requirement again:
"""


def inline_spec_text(tests_dir: Path, files: list[str], max_chars: int) -> str:
    """Quote spec + helper files into the prompt (bounded). Each read_file the
    model would otherwise issue is a full-context round trip (~11k tokens)."""
    parts = []
    total = 0
    for rel in files:
        path = tests_dir / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if total + len(text) > max_chars:
            return ""  # too big to inline; let the model read selectively
        total += len(text)
        parts.append(f"--- {rel} ---\n{text.rstrip()}\n")
    return INLINE_SPEC_HEADER + "".join(parts) if parts else ""


def locate_acceptance_tests(tree: dict, bundle_dir: Path) -> Path | None:
    """ARCBENCH_TESTS_DIR, then the runner's /workspace/tests, then the public
    specs shipped in the bundle (matched by requirement root name)."""
    candidates: list[Path] = []
    env_dir = os.environ.get("ARCBENCH_TESTS_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.append(Path("/workspace/tests"))
    bundled = bundle_dir / "public-tests"
    manifest = bundled / "manifest.json"
    if manifest.is_file():
        try:
            mapping = json.loads(manifest.read_text(encoding="utf-8"))
            root_name = str(tree.get("name", "")).strip()
            for req_id, title in mapping.items():
                if str(title).strip() == root_name and (bundled / req_id).is_dir():
                    candidates.append(bundled / req_id)
        except Exception as exc:  # noqa: BLE001
            log(f"[tests] manifest unreadable: {exc}")
    for cand in candidates:
        try:
            if cand.is_dir() and any(cand.rglob("*.spec.ts")):
                return cand.resolve()
            log(f"[tests] candidate {cand}: {'no *.spec.ts' if cand.is_dir() else 'absent'}")
        except Exception as exc:  # noqa: BLE001
            log(f"[tests] candidate {cand} unreadable: {exc}")
    return None


def spec_base_ports(tests_dir: Path | None) -> list[int]:
    """Ports the specs hard-code as their default base URL (e.g. 3301)."""
    if not tests_dir:
        return []
    ports: set[int] = set()
    for path in tests_dir.rglob("*.ts"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in re.finditer(r"https?://(?:127\.0\.0\.1|localhost):(\d{2,5})", text):
            ports.add(int(m.group(1)))
    return sorted(ports)


def acceptance_tests_prompt(tests_dir: Path | None, web_port: int, smoke_port: int,
                            files: list[str] | None = None, inline: bool = False) -> str:
    if not tests_dir:
        return ""
    if files is None:
        files = sorted(str(p.relative_to(tests_dir)) for p in tests_dir.rglob("*.ts"))
    text = ACCEPTANCE_TESTS_PROMPT.format(tests_dir=tests_dir, files=", ".join(files[:40]) or "(none)")
    if inline:
        text += inline_spec_text(tests_dir, files, int(os.environ.get("OCTOS_ARC_INLINE_SPEC_CHARS", "24000")))
    extra = [p for p in spec_base_ports(tests_dir) if p != web_port]
    if extra:
        ports = ", ".join(map(str, extra))
        text += (f"PORT CONTRACT (mandatory): the specs default to port(s) {ports} while the grader starts the "
                 f"backend with PORT={web_port}. Serve the identical app on BOTH the PORT value and port(s) {ports}: "
                 f"create a SEPARATE http.createServer(handler) for each port (one Server can listen only once — "
                 f"calling listen() twice throws ERR_SERVER_ALREADY_LISTEN and the process dies), binding the extra "
                 f"port(s) only when process.env.ARC_EXTRA_PORTS is not '0'. The grader sets ONLY PORT, so the "
                 f"extra port(s) ARE bound during grading.\n")
    return text


# ---------------------------------------------------------------- flow

def regression_checkpoint_due(index: int, total: int, start: int) -> bool:
    """Start with short checks, then cap gaps at twice the interval; skip the final node.

    The last interval always checks. Cloud 3ffe9702bf15 / 746c81a2b5aa run 32
    nodes, so the doubling leaves nodes 25-32 unchecked until the full suite --
    the widest gap, over the most layered state, right where a regression costs
    the most to find.
    """
    if start <= 0 or index < start or index >= total or index % start:
        return False
    multiple = index // start
    return multiple == 1 or multiple % 2 == 0 or index + start >= total


class Flow:
    def __init__(self, args, output_dir: Path, req_dir: Path) -> None:
        self.args = args
        self.output_dir = output_dir
        self.req_dir = req_dir
        self.web_port = args.web_port
        self.smoke_port = int(os.environ.get("OCTOS_SMOKE_PORT", "3100"))
        if self.smoke_port == self.web_port:
            self.smoke_port += 1
        self.node_timeout = int(os.environ.get("OCTOS_NODE_TIMEOUT", "1200"))
        self.design_timeout = int(os.environ.get("OCTOS_DESIGN_TIMEOUT", "420"))
        self.budget = int(os.environ["OCTOS_TIME_BUDGET"]) if os.environ.get("OCTOS_TIME_BUDGET") else 3600
        self.budget_explicit = bool(os.environ.get("OCTOS_TIME_BUDGET"))
        # keep-local-3 (workflow C): with 480 s/node, 16 of 17 implement/repair
        # turns were cut at 283 s; Web nodes need 10-20 min of implementation.
        self.seconds_per_node = int(os.environ.get("OCTOS_SECONDS_PER_NODE", "1500"))
        self.min_repair_seconds = int(os.environ.get("OCTOS_MIN_REPAIR_SECONDS", "300"))
        self.node_budget_cap = int(os.environ.get("OCTOS_NODE_TIME_BUDGET", "1500"))
        self.repair_rounds = int(os.environ.get("OCTOS_REPAIR_ROUNDS", "5"))
        self.repair_rounds_explicit = bool(os.environ.get("OCTOS_REPAIR_ROUNDS"))
        # Run-wide cost guard. Defaults scale with the tree and sit ~3x above a normal run
        # (calibration: cloud keep 2224a9013528, 32 nodes, PASSED 32/32, 9,038 s, ¥16.58 ≈ 26M
        # platform tokens ≈ 0.8M tokens and ~1.1 turns per node), so they never truncate a
        # healthy run; they only stop repair loops that have gone pathological. Explicit env
        # values override (0 = off). OCTOS_ARC_MAX_TOTAL_TOKENS_ABS is the optional absolute
        # ceiling for a per-run spend rule (e.g. ¥50 ≈ 75M tokens at the observed ¥0.63/M).
        self.max_total_tokens = int(os.environ.get("OCTOS_ARC_MAX_TOTAL_TOKENS", "-1"))
        self.max_turns = int(os.environ.get("OCTOS_ARC_MAX_TURNS", "-1"))
        self.max_total_tokens_abs = int(os.environ.get("OCTOS_ARC_MAX_TOTAL_TOKENS_ABS", "0"))
        self.turn_count = 0
        self._wound_down_logged = False
        self.design_enabled = os.environ.get("OCTOS_DESIGN_TURN", "1") != "0"
        self.design_min_nodes = int(os.environ.get("OCTOS_DESIGN_MIN_NODES", "3"))
        self.skeleton_min_nodes = int(os.environ.get("OCTOS_SKELETON_MIN_NODES", "3"))
        self.small_task_nodes = int(os.environ.get("OCTOS_SMALL_TASK_NODES", "2"))
        # "separate": own read-only turn before implementing; "inline": the
        # implement turn writes .arc/design/<node>.json first, then codes.
        self.design_mode = os.environ.get("OCTOS_DESIGN_MODE", "inline")
        self.implement_fraction = float(os.environ.get("OCTOS_IMPLEMENT_FRACTION", "0.6"))
        self.alias_states = os.environ.get("OCTOS_ARC_ALIAS_SPEC_IDS", "1") != "0"
        self.perf_contract = os.environ.get("OCTOS_PERF_CONTRACT", "1") != "0"
        self.guard_enabled = os.environ.get("OCTOS_GUARD", "1") != "0"
        self.t_start = time.time()
        self.runtime = None
        self.events = None
        self.driver: OctosDriver | None = None
        self.tests_dir: Path | None = None
        self.requirement_contracts: dict = {"version": 2, "nodes": []}
        self.spec_map: dict = {None: []}
        self.probe_summaries: dict = {}
        self.probe_count = 0  # nodes actually probed against the existing app
        self.aliases: dict[str, str] = {}
        self.runner: AcceptanceRunner | None = None
        self.designs: dict[str, dict] = {}
        # One application-level design per run (app_design); None when skipped or unparsable.
        self.app_design_doc: dict | None = None
        self.generic_template_installed = False
        # Paths the write guard refused in this node: the model named the file it
        # needs; the next codegen prompt quotes it whole (must_include).
        self.refused_paths: set[str] = set()
        self.test_verdict: dict[str, bool | None] = {}
        # Source progress and test observations are independent state axes.
        self.generation_state: dict[str, str] = {}
        self.test_state: dict[str, str] = {}
        self.phase_plan: dict | None = None
        # Batch generation still verifies every leaf. Record its first-pass
        # yield so subsequent runs can distinguish batching cost from repairs.
        self.batched_groups: dict[str, tuple[str, ...]] = {}
        self.batch_first_pass: dict[str, bool] = {}
        self.checkpoint_regressions: set[str] = set()
        # Last checkpoint where every tracked, previously verified behaviour
        # passed together.  `last_checkpoint_sha` is also the diff baseline;
        # this richer record lets a later catastrophic checkpoint restore that
        # measured tree instead of building more features on broad damage.
        self.healthy_checkpoint: dict | None = None
        self.impl_failed: list[str] = []
        self.pending_corrections: list[str] = []
        # Why the last codegen prompt could not be built; read by log_codegen_fallback.
        self.codegen_budget: dict = {}
        self.evolution = False
        self.folder_children: dict[str, list[str]] = {}
        self.repair_durations: dict[str, list[float]] = {"codegen": [], "tools": []}

    def metric(self, kind: str, **fields) -> None:
        """Compact outcomes, separate from traceability commits and billed tokens."""
        root = getattr(self, "output_dir", None)
        if not isinstance(root, Path):
            return
        try:
            path = root / ".arc" / "flow-metrics.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"kind": kind, **fields}, ensure_ascii=False) + "\n")
        except OSError as exc:
            log(f"[flow] could not record metric: {exc}")

    def record_quality_observation(self, node_id: str, title: str, message: str, *,
                                   source: str = "derived", reliable: bool = False,
                                   source_hash: str | None = None) -> str:
        """Persist evidence grade separately from source-generation progress."""
        node = getattr(self, "requirement_nodes", {}).get(node_id, {})
        requirement = (str(node.get("description") or "") + " "
                       + json.dumps(node.get("scenarios") or [], ensure_ascii=False))
        core = bool(re.search(r"sign.?in|sign.?out|password|permission|access|persist|save|formula|delete",
                              requirement, re.I))
        minor = str(node.get("priority") or "").lower() == "low" or bool(re.search(
            r"\b(optional|secondary|edge case|noncritical|cosmetic|tooltip)\b", requirement, re.I))
        severity, confidence = classify_observation(message, source=source, reliable=reliable,
                                                    core=core, minor=minor)
        action = {"F0": "bounded_critical_repair", "F1": "bounded_targeted_repair",
                  "F2": "defer_and_self_audit", "T": "skip_test_repair_and_self_audit",
                  "I": "diagnose_infrastructure"}[severity]
        path = getattr(self, "tests_dir", None)
        spec = path / f"{node_id}.spec.ts" if isinstance(path, Path) else None
        try:
            spec_hash = case_sha(spec.read_text(encoding="utf-8")) if spec and spec.is_file() else ""
        except OSError:
            spec_hash = ""
        source_hash = source_hash or self.app_source_digest()
        key = (node_id, title, case_sha(message), spec_hash, source_hash)
        seen = getattr(self, "_quality_observations_seen", set())
        if key not in seen:
            self._quality_observations_seen = seen | {key}
            row = {"node_id": node_id, "case": title, "severity": severity, "confidence": confidence,
                   "action": action, "requirement_hash": node_fingerprint(node) if node else "",
                   "spec_hash": spec_hash, "source_hash": source_hash, "message_hash": case_sha(message),
                   "generation_state": getattr(self, "generation_state", {}).get(node_id, "not_started"),
                   "test_state": getattr(self, "test_state", {}).get(node_id, "not_run")}
            if severity == "T" and re.search(r"unauthorized|cross.user|data loss|deleted another|permission bypass",
                                             message, re.I):
                row["risk"] = "critical_suspected_unverified"
            findings = getattr(self, "quality_observations", {})
            findings[(node_id, title)] = row
            self.quality_observations = findings
            ledger = self.output_dir / ".arc" / "quality-observations.jsonl"
            try:
                ledger.parent.mkdir(parents=True, exist_ok=True)
                with ledger.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            except OSError as exc:
                self.metric("quality_observation", node_id=node_id, outcome="ledger_unavailable",
                            reason=str(exc)[:160])
            self.metric("quality_observation", **row)
        return severity

    def self_audit_node(self, node_id: str, reason: str) -> None:
        """One read-only source/contract audit when a test cannot guide repair."""
        if not isinstance(getattr(self, "output_dir", None), Path):
            return
        seen = getattr(self, "_self_audited_versions", set())
        source_hash = self.app_source_digest()
        key = (node_id, source_hash)
        if key in seen:
            return
        self._self_audited_versions = seen | {key}
        try:
            gaps = self.whole_app_wave_gaps([node_id])
            index = self.repair_source_index()
            artifacts = [item for phase in (getattr(self, "phase_plan", None) or {}).get("phases", [])
                         if node_id in phase.get("leaves", []) for item in phase.get("artifacts", [])]
            paths = index.planned_artifact_candidates(artifacts)
            source_contracts = index.render(paths, limit=2500) if paths else "unmapped"
            from generation_checks import missing_backend_export_errors
            export_gaps = missing_backend_export_errors(index.sources, paths or index.sources.keys())
            gaps.extend("source advisory: " + issue for issue in export_gaps[:8])
        except Exception as exc:  # advisory audit failure must not become a generation gate
            gaps, paths, source_contracts = [f"audit unavailable: {str(exc)[:160]}"], [], "unavailable"
        requirement = getattr(self, "requirement_nodes", {}).get(node_id, {"id": node_id})
        row = {"node_id": node_id, "source_hash": source_hash,
               "requirement_hash": node_fingerprint(requirement),
               "requirement_excerpt": str(requirement.get("description") or "")[:1000],
               "source_paths": paths, "source_contracts": source_contracts,
               "source_mapping": "heuristic_candidates_unverified" if paths else "unmapped",
               "reason": reason[:200], "static_gaps": gaps[:12],
               "status": "reviewed_unverified"}
        path = self.output_dir / ".arc" / "review" / "source-self-audit.jsonl"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError as exc:
            self.metric("source_self_audit", node_id=node_id, status="unavailable", reason=str(exc)[:160])
            return
        self.metric("source_self_audit", node_id=node_id, gaps=len(gaps), status="reviewed_unverified")

    def write_quality_summary(self, *, startable: bool, node_ids: list[str]) -> None:
        reviews = getattr(self, "derived_case_reviews", {})
        current_source = self.app_source_digest()
        findings = list(getattr(self, "quality_observations", {}).values())
        phase_rows = []
        for phase in (getattr(self, "phase_plan", None) or {}).get("phases", []):
            leaves = phase["leaves"]
            written = sum(self.generation_state.get(leaf) == "source_written" for leaf in leaves)
            phase_rows.append({"id": phase["id"], "leaves": len(leaves), "source_written": written,
                               "status": "source_written_startable_unverified" if written == len(leaves) and startable else
                               "integrated_unverified" if written == len(leaves) else "partially_written"})
        summary = {"version": 1, "startable": startable, "leaves": len(node_ids),
                   "generation": {state: sum(self.generation_state.get(node, "not_started") == state for node in node_ids)
                                  for state in ("not_started", "attempted", "source_written", "attempted_with_risk")},
                   "test": {"passed": sum(self.test_verdict.get(node) is True for node in node_ids),
                            "failed": sum(self.test_verdict.get(node) is False for node in node_ids),
                            "unverified": sum(self.test_verdict.get(node) is None for node in node_ids),
                            "states": {state: sum(self.test_state.get(node, "not_run") == state for node in node_ids)
                                       for state in ("not_run", "passed", "failed", "disputed",
                                                     "skipped_low_signal", "measurement_unavailable")}},
                   "derived_cases": {state: sum(row.get("status") == state for row in reviews.values())
                                     for state in ("approved_behavior", "approved_smoke_only", "needs_correction",
                                                   "disputed", "unreviewed", "skipped_unreviewed", "unverified_gap",
                                                   "skipped_with_reason")},
                   "quality_findings": {level: sum(row["severity"] == level and row["source_hash"] == current_source
                                                   for row in findings)
                                        for level in ("F0", "F1", "F2", "T", "I")},
                   "critical_suspected_unverified": sum(row.get("risk") == "critical_suspected_unverified"
                                                        and row["source_hash"] == current_source for row in findings),
                   "stale_findings": sum(row["source_hash"] != current_source for row in findings),
                   "phases": phase_rows,
                   "note": "Derived tests are internal diagnostics, not official benchmark scores."}
        path = self.output_dir / ".arc" / "quality-summary.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def phase_integration_audit(self) -> None:
        """Bounded cross-leaf source review and representative trusted smoke.

        A phase is a coordination unit; its review never admits the next phase.
        Missing or failing tests remain evidence gaps, not generation gates.
        """
        plan = getattr(self, "phase_plan", None) or {}
        phases = plan.get("phases") or []
        if not phases:
            return
        started = time.monotonic()
        smoke_cap = max(0, int(os.environ.get("OCTOS_ARC_PHASE_SMOKE_SECONDS", "300")))
        reports = []
        for phase in phases:
            leaves = phase["leaves"]
            gaps = self.whole_app_wave_gaps(leaves)[:12]
            row = {"id": phase["id"], "leaves": leaves, "source_written": [leaf for leaf in leaves
                   if self.generation_state.get(leaf) == "source_written"],
                   "cross_dependencies": phase.get("cross_dependencies", []),
                   "static_gaps": gaps, "smoke": "not_run"}
            if (self.runner is not None and self.tests_dir is not None and self.remaining() > 300
                    and time.monotonic() - started < smoke_cap):
                candidates = []
                for leaf in leaves:
                    for spec in self.spec_map.get(leaf, []):
                        path = self.tests_dir / spec
                        if not path.is_file():
                            continue
                        source = path.read_text(encoding="utf-8")
                        titles = [m.group(1).replace("\\'", "'") for m in re.finditer(
                            r"(?m)^test\('((?:\\.|[^'\\])*)',", source)]
                        if not titles or len(titles) > 4:
                            continue
                        if getattr(self, "derived_as_specs", False) and not all(
                                self.trusted_derived_case(leaf, title) for title in titles):
                            continue
                        candidates.append((len(titles), leaf, spec))
                if candidates:
                    count, leaf, spec = min(candidates)
                    timeout_s = max(1, getattr(self.runner, "timeout_ms", 30000) / 1000)
                    estimated = 60 + count * timeout_s
                    if (estimated <= smoke_cap - (time.monotonic() - started)
                            and self.remaining() > estimated + self.final_measurement_reserve()):
                        observed = self.run_specs([spec], workers=1, grader_like=True)
                        active = self.uncontested_derived_results(observed)
                        row["smoke"] = ("passed" if active.all_passed and self.suite_is_measured(observed, [spec])
                                        else "failed" if active.total and self.suite_is_measured(observed, [spec])
                                        else "unverified")
                        row["smoke_spec"] = spec
                        row["smoke_passed"] = active.passed
                        row["smoke_total"] = active.total
            reports.append(row)
        path = self.output_dir / ".arc" / "design" / "phase-integration.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 1, "source_hash": self.app_source_digest(),
                                    "phases": reports}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.metric("phase_integration", phases=len(reports),
                    smoke_run=sum(row["smoke"] != "not_run" for row in reports),
                    gaps=sum(len(row["static_gaps"]) for row in reports))

    def repair_minimum(self) -> float:
        mode = "codegen" if self.codegen_mode() else "tools"
        minimum = self.min_repair_seconds
        if mode == "codegen" and "OCTOS_MIN_REPAIR_SECONDS" not in os.environ:
            minimum = min(minimum, 60)
        return repair_seconds(getattr(self, "repair_durations", {}).get(mode, []), minimum)

    def final_phase_reserve(self, phase_budget: float | None = None) -> float:
        """Time large tasks keep for final measurement and clustered repairs.

        Per-leaf acceptance is useful evidence, but spending the last minute on
        one leaf prevents the full suite from exposing and repairing a shared
        cause.  The reserve is scheduling capacity, not extra runtime: explicit
        run budgets remain hard limits.  Small tasks keep their direct loop.
        """
        if getattr(self, "n_nodes", 0) <= 2 or self.runner is None or not self.tests_dir:
            return 0.0
        available = max(0.0, float(self.budget if phase_budget is None else phase_budget))
        configured = os.environ.get("OCTOS_ARC_FINAL_PHASE_SECONDS")
        if configured is not None:
            return min(available, max(0.0, float(configured)))
        measurement = self.final_measurement_reserve()
        desired = max(600.0, 2 * measurement + 2 * self.repair_minimum())
        return min(desired, available * 0.25)

    def final_phase_due(self) -> bool:
        """Stop admitting leaves when their reserved full-suite window begins."""
        reserve = self.final_phase_reserve()
        return bool(reserve and self.remaining() <= reserve)

    def final_retry_admission(self) -> float:
        """Budget needed to measure, repair, then preserve a final measurement."""
        return 2 * self.final_measurement_reserve() + self.repair_minimum()

    # -- helpers ----------------------------------------------------------
    def resolve_seed_conflicts(self, tree: dict) -> dict:
        """Choose one seed when the GIVENs describe the seeded records differently
        (see seed_facts); conflicting scenarios enter their own starting values."""
        resolution = resolve_seeds(tree)
        self.seed_resolution = resolution
        if not resolution.conflicting:
            return tree
        detail = "; ".join(f"{v.scenarios} scenario(s) set " + ", ".join(
            f"{ref}={mine!r} (seed {theirs!r})" for ref, (mine, theirs) in list(v.conflicts.items())[:4])
            for v in resolution.conflicting.values())
        log(f"[seed] {len(resolution.variants)} seed descriptions; canonical seed has "
            f"{len(resolution.canonical)} cell value(s); {resolution.rewritten} scenario(s) rewritten to enter "
            f"their own starting values: {detail}")
        self.metric("seed_resolution", variants=len(resolution.variants), canonical_cells=len(resolution.canonical),
                    conflicting=len(resolution.conflicting), rewritten=resolution.rewritten)
        return resolution.tree

    def note_turn(self, label: str) -> None:
        """The turn cap bounds build turns (implement/repair). Spec reviews and
        the design turn are short, text-only and bounded by their own count:
        v10.0 sheet 819388a5f77b spent 38 of its 96 turns on reviews and hit
        the cap with 21743s and 53M tokens left."""
        if label.startswith(NON_BUILD_TURN_LABELS):
            self.review_turn_count = getattr(self, "review_turn_count", 0) + 1
        else:
            self.turn_count += 1

    def review_budget_spent(self) -> bool:
        return self.max_turns > 0 and getattr(self, "review_turn_count", 0) >= self.max_turns

    def wound_down(self) -> bool:
        """True once the run has spent its token or turn allowance: no more repair
        turns, remaining nodes get one implement turn each, one final suite, done."""
        proxy = getattr(self, "llm_proxy", None)
        tokens = proxy.total_tokens if proxy is not None else 0
        over = getattr(self, "local_budget_exhausted", False) or \
               (self.max_total_tokens > 0 and tokens >= self.max_total_tokens) or \
               (self.max_turns > 0 and self.turn_count >= self.max_turns) or \
               (self.max_total_tokens_abs > 0 and tokens >= self.max_total_tokens_abs)
        if over and not self._wound_down_logged:
            self._wound_down_logged = True
            log(f"[guard] cost guard tripped: {tokens} observed/reserved tokens, {self.turn_count} turns "
                f"(limits {self.max_total_tokens} / {self.max_turns} / abs {self.max_total_tokens_abs}); no further repair turns")
        return bool(over)

    def remaining(self) -> float:
        return self.budget - (time.time() - self.t_start)

    def time_up(self) -> bool:
        return self.remaining() <= 0

    def mark(self, kind: str, node_id: str, message: str | None = None) -> None:
        if kind == "design_started":
            if node_id in getattr(self, "_design_started_ids", set()) or node_id in getattr(self, "_designed_ids", set()):
                return
            self._design_started_ids = getattr(self, "_design_started_ids", set()) | {node_id}
        elif kind == "design_done":
            if node_id in getattr(self, "_designed_ids", set()):
                return
            self._designed_ids = getattr(self, "_designed_ids", set()) | {node_id}
        if kind == "implementation_started":
            self.generation_state[node_id] = "attempted"
        elif kind == "implementation_done":
            self.generation_state[node_id] = "source_written"
        elif kind == "implementation_failed":
            self.generation_state[node_id] = "attempted_with_risk"
        elif kind == "test_passed":
            self.test_state[node_id] = "passed"
        elif kind == "test_failed":
            self.test_state[node_id] = "failed"
        fn = getattr(self.events, f"mark_{kind}")
        fn(node_id, message)
        if self.alias_states:
            for alias, target in self.aliases.items():
                if target == node_id:
                    fn(alias, message)

    def protected_prefixes(self) -> list[str]:
        prefixes = [".arc/", str(self.output_dir / ".arc"), "requirements/", str(self.req_dir)]
        if self.tests_dir:
            prefixes.append(str(self.tests_dir))
        return prefixes

    def inline_source_chars(self) -> int:
        """How much of the app to quote into a turn that edits with tools.

        This is an input budget and the context window bounds it;
        `codegen_context_chars` is an output budget, bounding what a tool-free
        turn is asked to re-emit. They default to the same number and are easy
        to mistake for one thing, but raising that one to quote more source
        would also start asking codegen turns for larger files than they should
        be asked for. Keep them separate so either can move on its own.

        The default is unchanged. Whether a larger share of a 1048576 token
        window helps a repair more than it dilutes it is not something the
        harness can answer offline; it needs a cloud run against the same task.

        What is measured, on the four large tasks of 2026-09-16, each about
        halfway through its nodes:

            task           nodes    files  source   quoted  omitted  seen
            stackoverflow  32/66    14     152050   4       10       63%
            prestashop     44/86    15     115636   7        8       79%
            12306          48/117   10     110394   5        5       86%
            ctrip          58/125    7     109559   3        4       86%

        Every repair prompt on those tasks already hides four to ten files, and
        the sources roughly double again by the last node. The budget they are
        competing for is about 22000 tokens of a 1048576 token window. The
        number was chosen as an output budget for codegen re-emission, not as
        an input budget, so raising it would not overturn a measured decision --
        but it would still be a guess until a cloud A/B says otherwise.

        Scope, before that A/B is priced: `sources_text` is read at three call
        sites and all three are repairs. A tool-mode implement turn is given no
        quoted source, but it is not left blind: it gets `source_listing` --
        every app file with its size -- and is told to read backend/server.js
        and the page it extends. That is deliberate, and the tool events match
        it exactly, so do not "fix" implement turns by quoting sources into
        them. On the same stackoverflow run the split was 33
        implement turns to 4 repairs, so the omission above reaches about a
        tenth of the turns -- the ones that decide the score, but a tenth. Its
        tool events show 148 reads, and `backend/server.js` alone accounts for
        28 of the last 60; most of those fall in implement turns that were
        never handed the file, so they are not the prompt failing to save a
        read.
        """
        return int(os.environ.get("OCTOS_ARC_INLINE_SOURCE_CHARS", str(self.codegen_context_chars())))

    def sources_text(self) -> str:
        # A repair has to understand the code before editing it, so it cannot be
        # quoted less than the turn that wrote the code was.
        limit = self.inline_source_chars()
        return stack_note(self.output_dir) + (inline_sources(self.output_dir, limit) + "\n" if limit > 0 else "")

    def corrections_text(self) -> str:
        if not self.pending_corrections:
            return ""
        text = HarnessCorrections(self.pending_corrections)
        self.pending_corrections = []
        return text

    def turn(self, prompt: str, timeout: int, label: str, expect_verification: bool = True,
             request_budget: int | None = None) -> tuple[bool, str]:
        if timeout <= 0:
            self.last_turn_changed = False
            return False, "turn time allowance exhausted before execution"
        proxy = getattr(self, "llm_proxy", None)
        # `verify_text` has the proxy drop the shell tools in minimal mode. A turn
        # that cannot run a command must not then be told off for not running one.
        no_shell = bool(getattr(proxy, "extra_drop_tools", None))
        monitor = TurnMonitor(self.protected_prefixes(),
                              expect_verification=expect_verification and not no_shell,
                              allowed_prefixes=[".arc/design/", str(self.output_dir / ".arc" / "design")])
        if proxy is not None:
            # Per-turn reasoning: OCTOS_ARC_IMPLEMENT_REASONING (e.g. "none") applies
            # to first implement turns of small tasks; rewrite/repair keep the base mode.
            base_mode = getattr(self, "base_reasoning_mode", proxy.mode)
            impl_mode = os.environ.get("OCTOS_ARC_IMPLEMENT_REASONING", "")  # auto already gives "none" to 1-node tasks
            is_implement = label.endswith(" implement") or label.startswith("skeleton")
            impl_all = os.environ.get('OCTOS_ARC_IMPLEMENT_REASONING_ALL') == '1'
            proxy.mode = impl_mode if (impl_mode and is_implement and
                                       (impl_all or self.minimal_mode(getattr(self, "n_nodes", 99)))) else base_mode
            current_model = os.environ.get("OCTOS_MODEL") or os.environ.get("MODEL", "")
            if proxy.mode == default_reasoning_for_model(current_model):
                proxy.mode = turn_reasoning_for_model(current_model, label)
            if request_budget is None:
                # Repairs are measured after bounded work, not allowed unlimited
                # context growth. Creation keeps its independent default.
                default = "12" if "repair" in label else "20" if self.minimal_mode(getattr(self, "n_nodes", 99)) else "0"
                request_budget = int(os.environ.get("OCTOS_ARC_REPAIR_REQUESTS", default)) if "repair" in label else \
                    int(os.environ.get("OCTOS_ARC_IMPLEMENT_REQUESTS", default))
            proxy.label = label
            proxy.phase = phase_for_label(label)
            proxy.begin_turn(request_budget)
            proxy.turn_deadline = time.monotonic() + timeout
        # A model turn may change application files, even when it later fails.
        getattr(self, "probe_summaries", {}).clear()
        t0 = time.time()
        execution_mode = "codegen" if proxy is not None and getattr(proxy, "no_tools", False) else "tools"
        before_sources = self.app_source_digest() if execution_mode == "tools" else None
        self.note_turn(label)
        # Only the guarded tool-free SSE path exposes trustworthy upstream progress.
        lease = None
        if (proxy is not None and getattr(proxy, "no_tools", False)
                and proxy.phase in {"implement", "repair"}
                and os.environ.get("OCTOS_ARC_STREAM_GUARD", "1") != "0"):
            slack = max(0, self.remaining() - self.final_measurement_reserve() - timeout)
            extension = min(120, timeout * 0.25, slack)
            lease = ProgressDeadline(timeout, extension=extension)
            log(f"[flow] {label}: streaming progress grace ≤{extension:.0f}s; idle limit 120s")
        self.driver.progress_deadline = lease
        if proxy is not None:
            proxy.progress_deadline = lease
        try:
            ok, text = self.driver.run(prompt, max(1, int(timeout)), monitor)
        finally:
            if lease is not None:
                lease.close()
            self.driver.progress_deadline = None
            if proxy is not None:
                proxy.progress_deadline = None
            if sys.exc_info()[0] is not None:
                self.restore_protected()
        if proxy is not None and getattr(proxy, "hard_budget_exhausted", False) is True:
            ok, text = False, "local_turn_budget_exhausted: partial edits retained; acceptance must measure them."
        if proxy is not None and getattr(proxy, "no_action_exhausted", False) is True:
            ok, text = False, "local_no_action_limit: node incomplete; partial edits retained for independent checks."
        elapsed = time.time() - t0
        log(f"[flow] {label} {'ok' if ok else 'FAILED'} in {time.time()-t0:.0f}s "
            f"(tools={monitor.tool_calls} wrote={monitor.wrote_files} verified={monitor.verified}): {text[-240:]!r}")
        if proxy is not None and getattr(proxy, "hard_budget_exhausted", False) is True:
            log(f"[guard] {label}: hard request budget {proxy.turn_budget} hit; turn incomplete")
        for c in monitor.corrections():
            log(f"[guard] {label}: {c[:160]}")
            if self.guard_enabled:
                self.pending_corrections.append(c)
        restored = self.restore_protected()
        if restored:
            self.pending_corrections.append(
                "You changed official test/requirement files; the harness restored them: "
                + ", ".join(restored[:5]) + ". They are read-only ground truth — fix the app instead.")
        if getattr(self, "generic_template_installed", False) and monitor.wrote_files:
            self.generic_template_installed = generic_template_active(self.output_dir)
        self.last_turn_changed = (self.app_source_digest() != before_sources) if before_sources is not None else False
        if ok and self.last_turn_changed and phase_for_label(label) == "repair":
            durations = getattr(self, "repair_durations", {})
            durations.setdefault(execution_mode, []).append(elapsed)
            durations[execution_mode] = durations[execution_mode][-12:]
            self.repair_durations = durations
        self.metric("turn", label=label, phase=phase_for_label(label), mode=execution_mode,
                    ok=ok, elapsed_seconds=round(elapsed, 3),
                    changed=self.last_turn_changed if execution_mode == "tools" else None,
                    tools=monitor.tool_calls)
        # Fatal provider responses still require protected-file restoration and
        # an accounting event. Do not jump past the common turn cleanup.
        if not ok and "local_token_budget_exhausted" in text:
            # This is our admission guard, not a provider outage. Stop model
            # calls but allow reserved acceptance time to measure these edits.
            self.local_budget_exhausted = True
            self.metric("budget_stop", reason="local_token_budget_exhausted")
            return False, text
        if not ok and permanent_provider_error(text):
            raise PermanentProviderError(text[:1000])
        return ok, text

    def slow_test_ms(self) -> int:
        """Half the budget a test is graded against.

        The threshold was a flat 3000 ms, tuned when the harness also imposed a
        4000 ms action deadline — a test near 3 s was then near failing. With the
        deadlines matched to the grader (10 s per test) it is not: in cloud
        3ffe9702bf15 three of the twenty-five tests the grader passed ran between
        3.4 s and 3.9 s, and each was handed to the model as something to
        optimise. Editing passing code to make it faster is a regression risk
        taken for nothing. Above half the budget there is real cause to look.
        """
        configured = os.environ.get("OCTOS_ARC_SLOW_MS")
        if configured:
            return int(configured)
        timeout = getattr(getattr(self, "runner", None), "timeout_ms", 10000)
        return max(1000, timeout // 2)

    def perf_text(self) -> str:
        return PERFORMANCE_CONTRACT if self.perf_contract and self.needs_session else ""

    def classify_tree(self, tree: dict) -> None:
        """Keyword-gate the optional contract blocks so a counter never reads
        session/performance rules; derive behavior from the supplied requirements."""
        text = json.dumps(tree, ensure_ascii=False).lower()
        self.needs_session = bool(re.search(r"login|log in|sign in|password|session|register|注册|登录|密码|会话", text))
        self.needs_data = bool(re.search(r"seed|published|fixture|option|select|dropdown|nationalit|车次|train|选项|下拉|预置", text))

    def ui_contract(self) -> str:
        blocks = [UI_CONTRACT_CORE]
        if getattr(self, "needs_data", True):
            blocks.append(UI_CONTRACT_DATA)
        if getattr(self, "needs_session", True):
            blocks.append(UI_CONTRACT_SESSION)
        return "".join(blocks)

    SHELL_TOOLS = {"bash", "shell", "exec_command"}

    def minimal_mode(self, total_nodes: int) -> bool:
        mode = os.environ.get("OCTOS_VERIFY_MODE", "auto")
        return mode == "minimal" or (mode != "full" and total_nodes <= self.small_task_nodes)

    def verify_text(self, total_nodes: int) -> str:
        minimal = self.minimal_mode(total_nodes)
        # Prompt budgets alone are ignored often enough (v9-tb-a: 41 tool calls
        # incl. servers in a "no shell" repair turn); in minimal mode the proxy
        # removes the shell tools so commands are impossible, the harness builds.
        proxy = getattr(self, "llm_proxy", None)
        if proxy is not None and os.environ.get("OCTOS_ARC_DROP_SHELL", "1") != "0":
            proxy.extra_drop_tools = set(self.SHELL_TOOLS) if minimal else set()
        guidance = VERIFY_MINIMAL if minimal else VERIFY_FULL.format(smoke=self.smoke_port)
        if getattr(self, "derived_as_specs", False):
            guidance = (guidance.replace("official acceptance tests", "generated acceptance tests")
                        .replace("official Playwright specs", "generated Playwright specs"))
            guidance += (" The generated specs are checked against requirements.yaml if they fail; "
                         "requirements.yaml determines the required behavior.\n")
        return guidance

    def codegen_mode(self, *, node_block: bool = True) -> bool:
        """One-request generation per node (OCTOS_ARC_CODEGEN=0 disables; OCTOS_ARC_CODEGEN_MAX_NODES caps the
        tree size, default unlimited). Per node, `codegen_implement_prompt` decides it: a complete user
        message it cannot build within the budget returns None and that node uses tool mode.
        `codegen_blocked` is the current node's escalation; a suite repair (node_block=False) is not
        bound by it."""
        return (os.environ.get("OCTOS_ARC_CODEGEN", "1") != "0" and getattr(self, "llm_proxy", None) is not None
                and not (node_block and getattr(self, "codegen_blocked", False))
                and getattr(self, "n_nodes", 99) <= int(os.environ.get("OCTOS_ARC_CODEGEN_MAX_NODES", "999")))

    def all_specs_tiny(self, node_ids: list[str]) -> bool:
        """True when every node that has specs falls in the tiny tier (and at least one does)."""
        sizes = [len(self.spec_bodies(n)) for n in node_ids if self.spec_map.get(n)]
        return bool(sizes) and all(self.tiny_mode(n) for n in sizes)

    def maybe_probe(self, node_ids: list[str]) -> None:
        """Endpoint probe policy: none in dry runs; none when the whole task is tiny-tier
        (the first real request is the probe — a failure there is diagnosed by the normal
        turn error path); otherwise the token-free GET /models probe with a minimal fallback."""
        if os.environ.get("OCTOS_ARC_DRYRUN") == "1":
            log("[probe] skipped (OCTOS_ARC_DRYRUN=1)")
        elif self.all_specs_tiny(node_ids):
            log("[probe] skipped (tiny-tier task: the first real request doubles as the probe)")
        else:
            probe_endpoint()

    def codegen_context_chars(self) -> int:
        return int(os.environ.get("OCTOS_ARC_CODEGEN_CONTEXT_CHARS", "96000"))

    def source_change_counts(self) -> dict[str, int]:
        """Historical app-file edits, used only to order already selected quotes.

        A missing git history leaves the old deterministic path order intact.
        This never changes which sources fit the prompt or the write guard.
        """
        if os.environ.get("OCTOS_ARC_SOURCE_STABILITY_ORDER", "1") == "0":
            return {}
        runtime = getattr(self, "runtime", None)
        if runtime is None:
            return {}
        try:
            result = runtime.git.run(["log", "--format=", "--name-only", "--", "frontend", "backend"], check=False)
        except Exception:  # noqa: BLE001
            return {}
        if result.returncode != 0:
            return {}
        counts: dict[str, int] = {}
        for path in (result.stdout or "").splitlines():
            path = path.strip()
            if path.startswith(("frontend/", "backend/")):
                counts[path] = counts.get(path, 0) + 1
        return counts

    def omit_unchanged_template_libraries(self, scored: list[tuple], must_include=()) -> list[tuple]:
        """Keep unchanged shared helper/build implementations out of node prompts.

        Their short public API is in GENERIC_TEMPLATE_NOTE. If a response names
        one for editing, the write guard refuses it and the next prompt quotes
        that entire file through must_include. Modified libraries are never
        omitted, so application-specific changes remain visible.
        """
        if not getattr(self, "generic_template_installed", False):
            return scored
        required = set(must_include)
        defaults = {}
        for rel, asset in TASK_NEUTRAL_HELPERS.items():
            try:
                defaults[rel] = (BUNDLE_DIR / "blueprints" / asset).read_text(encoding="utf-8")
            except OSError:
                return scored
        return [row for row in scored if str(row[3]) in required
                or str(row[3]) not in defaults or row[4] != defaults[str(row[3])]]

    def codegen_implement_prompt(self, node: dict, spec: str, corrections: str = "", *, evidence: str = "",
                                 must_include: set[str] | None = None,
                                 context_limit: int | None = None,
                                 source_limit: int | None = None,
                                 focused_sources: bool = False) -> str | None:
        """Budget a complete user message, preserving rules and critical corrections.

        Fixed rules/source order precede node-specific text and size rules. Only
        typed checkpoint observations can be clipped to keep the entry quoted.
        The spec may take at most 60% of the budget; the backend entry -- the file
        every node extends -- must still be quotable once everything else is
        counted. Nothing else has to fit: the omitted files are listed by name,
        and codegen_turn refuses a block for an existing file the model was not
        shown whole, so an omitted file is kept rather than rewritten blind.

        Until 2026-09-17 the whole app had to fit, which sent every app over ~82k
        chars -- every Web task, keep's own 86k included -- to tool mode
        wholesale, 36 requests a node (dev-docs/token-reduction-plan.md §3.1).
        """
        limit = self.codegen_context_chars()
        if context_limit is not None:
            limit = max(12000, int(context_limit))  # input cap is independent of rewrite/output planning
        if len(spec) >= limit * 0.6:
            # Cheapest refusal there is; decided before any source file is read.
            self.codegen_budget = dict(spec=len(spec), entry=0, room=0, limit=limit,
                                       reason="spec_at_or_above_60_percent")
            return None
        gate = getattr(self, '_generation_gate_evidence', '')
        if gate:
            evidence += '\nPrevious batch checks (fix confirmed errors; verify advisory hypotheses before editing):\n' + gate[:4000]
        small = self.codegen_reasoning(len(spec)) == "none"
        rules = CODEGEN_RULES.format(port=self.web_port, ports=self.codegen_ports_clause())
        if getattr(self, "generic_template_installed", False):
            rules += GENERIC_TEMPLATE_NOTE + route_table_note(self.output_dir)
        rules += stack_note(self.output_dir) + seed_contract_text(self)
        # The harness has already written package.json, which is enough for
        # has_app() but not for a runnable backend. Keep existing sources while
        # explicitly requiring the missing entry in this generation request.
        missing_entry = missing_backend_entry(self.output_dir)
        if missing_entry:
            rules += f"Startup prerequisite: {missing_entry} is missing. Create it in this response so the configured backend start command can run.\n"
        derived_contract = "DERIVED REQUIREMENT VERIFICATION CONTRACT" in spec
        task = CODEGEN_TASK.format(node_id=str(node.get("id")),
            description=describe_node(node, include_scenarios=not derived_contract)
            if node.get("scenarios") or node.get("dependencies")
            else str(node.get("description") or "").strip(), spec=spec,
            size_rule=CODEGEN_SIZE_SMALL if small else CODEGEN_SIZE_FULL)
        # A wave uses a synthetic node id; its active requirement ids are
        # explicitly listed in the description. Single-node turns use their id.
        node_id = str(node.get("id"))
        active_ids = ([node_id] if node_id in (getattr(self, "phase_plan", None) or {}).get("leaf_phase", {})
                      else re.findall(r"\b[A-Za-z][A-Za-z0-9_-]*-\d+(?:-\d+)*\b",
                                      str(node.get("description") or "").split("ACTIVE DETAILS:", 1)[0]))
        task = phase_context(getattr(self, "phase_plan", None), active_ids, limit=2400) + task
        existing = self.has_app()
        if existing:
            rules = rules.replace("Files:", "Existing app below; preserve working behavior. Files:", 1)
        entry = backend_entry(self.output_dir) if existing else None
        if must_include is None:
            must_include = set(getattr(self, "refused_paths", ()))
        else:
            must_include = set(must_include)
        # A small manifest is cheaper to quote than to lose and regenerate a
        # multi-file reply. The atomic write guard remains the authority.
        manifest = self.output_dir / "frontend/package.json"
        if (manifest.is_file() and manifest.stat().st_size <= 2500
                and limit >= 12000 and len(spec) < limit * 0.45):
            must_include.add("frontend/package.json")
        scored = scored_sources(self.output_dir, spec + "\n" + evidence, entry, must_include=must_include) if existing else []
        scored = Flow.omit_unchanged_template_libraries(self, scored, must_include)
        entry_indexes = [i for i, row in enumerate(scored)
                         if entry is not None and row[3] == entry.relative_to(self.output_dir)]
        entry_size = scored[entry_indexes[0]][2] if entry_indexes else 0
        # getattr: tests build bare Flows without __init__, like base_reasoning_mode above.
        design_stable, design_slice = app_design_blocks(getattr(self, "app_design_doc", None), spec,
                                                        int(os.environ.get("OCTOS_ARC_APP_DESIGN_CHARS", "6000")))
        fixed = (len(rules) + len(design_stable) + len(design_slice) + len(task) + len(evidence)
                 + len(FORMAT_INSTRUCTIONS) + 2)
        room = limit - fixed - len(corrections)
        self.codegen_budget = dict(spec=len(spec), entry=entry_size, room=room, limit=limit, reason="")
        if entry is not None and not entry_indexes:
            self.codegen_budget["reason"] = "backend_entry_unreadable"
            return None
        change_counts = self.source_change_counts()
        minimum_sources = render_source_selection(scored, entry_indexes, True, change_counts)
        correction_room = limit - fixed - len(minimum_sources)
        if len(corrections) > correction_room:
            fitted = corrections.fit(correction_room) if isinstance(corrections, HarnessCorrections) else None
            if fitted is None:
                self.codegen_budget["reason"] = "fixed_prompt_entry_or_critical_corrections_exceed_budget"
                return None
            log(f"[codegen] {node.get('id')}: checkpoint corrections clipped "
                f"{len(corrections)} -> {len(fitted)} chars; critical corrections preserved")
            corrections = fitted
            room = limit - fixed - len(corrections)
            self.codegen_budget["room"] = room
        source_room = room if source_limit is None else min(room, max(8000, int(source_limit)))
        sources = select_source_snapshot(scored, source_room, stable_order=True, max_output_chars=source_room,
                                         change_counts=change_counts,
                                         max_priority=3.5 if focused_sources else None)
        if sources is None or (entry is not None and str(entry.relative_to(self.output_dir)) not in quoted_paths(sources)):
            self.codegen_budget["reason"] = "serialized_sources_or_entry_exceed_budget"
            return None
        missing_required = set(must_include) - quoted_paths(sources)
        if missing_required:
            self.codegen_budget["reason"] = "required_wave_sources_exceed_budget"
            self.codegen_budget["missing_required"] = sorted(missing_required)
            return None
        self.codegen_budget.update(
            fixed=fixed, source_block=len(sources), quoted_sources=len(quoted_paths(sources)),
            required_sources=len(must_include), source_limit=source_room)
        # Rules, a design that fits whole (identical for every node), the sources in
        # stability order -- unchanged low-churn files precede frequently edited
        # ones for prefix reuse -- then the per-node design slice, if any, with the
        # other node-specific text.
        prompt = rules + design_stable + sources + "\n" + design_slice + corrections + evidence + task
        self.bind_edit_scope(prompt, spec + '\n' + evidence, must_include)
        return prompt

    def render_outlines(self, paths: list[str], room: int) -> str | None:
        """Outline blocks for files that cannot be quoted whole, or None when
        even the outlines do not fit."""
        per_file = max(1500, min(6000, room // max(1, len(paths))))
        blocks = []
        for rel in paths:
            path = self.output_dir / rel
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return None
            outline = outline_source(text, per_file)
            if not outline:
                return None
            blocks.append(f"--- {rel} --- (outline, {len(text)} chars; too large to quote whole. Change it ONLY "
                          f"with <<<EDIT>>> blocks whose SEARCH text is copied exactly from the lines below, "
                          f"or leave it unchanged)\n{outline}\n")
        rendered = "".join(blocks)
        return rendered if len(rendered) <= room else None

    def bind_edit_scope(self, prompt, evidence, priority=()):
        root = getattr(self, 'output_dir', None)
        paths = [p.relative_to(root) for p in app_source_files(root)] if isinstance(root, Path) else []
        scope = set(priority or ()) | spec_targets(evidence, paths) | navigation_targets(evidence, paths)
        scopes = getattr(self, '_edit_scopes', {})
        scopes[hashlib.sha256(prompt.encode()).hexdigest()] = scope
        self._edit_scopes = dict(list(scopes.items())[-4:])

    def edit_scope(self, prompt):
        return getattr(self, '_edit_scopes', {}).get(hashlib.sha256(prompt.encode()).hexdigest()) or quoted_paths(prompt)

    def log_codegen_fallback(self, node_id: str) -> None:
        budget = self.codegen_budget
        log(f"[flow] {node_id}: codegen budget exceeded; tool mode "
            f"spec={budget.get('spec', '?')} entry={budget.get('entry', '?')} room={budget.get('room', '?')} "
            f"limit={budget.get('limit', '?')} reason={budget.get('reason') or 'unrecorded'}")

    def codegen_repair_prompt(self, node_id: str, prompt: str, failures: str = "") -> str | None:
        spec = self.spec_bodies(node_id)
        if not spec or spec == "(none)":
            return None
        if failures and failures in prompt:
            prompt = prompt.replace(failures, balanced_failure_evidence(failures, 6000), 1)
        patched = self._patched_repair_prompt(node_id, spec, prompt)
        if patched is not None:
            self.bind_edit_scope(patched, spec + '\n' + failures, getattr(self, 'refused_paths', ()))
            return patched
        # The tool-mode prompt could not be requoted within the budget (cloud
        # fcec6ac02a95: 15 repairs went straight to tools this way). Build the
        # repair the way an implement turn is built -- rules, design, ranked
        # sources with the refused/target files first, then the failures as
        # evidence -- before giving the node to tools.
        node = getattr(self, "requirement_nodes", {}).get(node_id)
        if node is None:
            return None
        evidence = ("The current application fails these acceptance checks; fix them without breaking the "
                    "passing ones:\n" + balanced_failure_evidence(failures or "(no detail)", 6000) + "\n")
        return self.codegen_implement_prompt(node, spec, "", evidence=evidence)

    def _patched_repair_prompt(self, node_id: str, spec: str, prompt: str) -> str | None:
        # Tool-free repairs must see the source instead of instructions to read it.
        # Requote within the room the rest of the prompt leaves (evidence,
        # requirements, the repair suffix, the format block), so the result fits
        # by construction. A clipped or omitted file no longer sends the repair to
        # tool mode: codegen_turn refuses a block for any existing file not shown
        # whole, so the model can only fix what it was shown -- which is the point.
        suffix = CODEGEN_REPAIR_SUFFIX.format(spec=spec)
        # Every turn is a fresh session, so the repair sees the run-wide design
        # only if this prompt carries it; counted against the requote room.
        design = app_design_context(getattr(self, "app_design_doc", None), spec,
                                    int(os.environ.get("OCTOS_ARC_APP_DESIGN_CHARS", "6000")))
        suffix = stack_note(getattr(self, "output_dir", None)) + design + suffix
        limit = self.codegen_context_chars()
        current_sources = self.sources_text()
        if current_sources.strip() and current_sources in prompt:
            room = limit - (len(prompt) - len(current_sources)) - len(suffix) - len(FORMAT_INSTRUCTIONS) - 2000
            if room < 8000:
                return None
            ranked = scored_sources(self.output_dir, spec, must_include=getattr(self, "refused_paths", ()))
            ranked = Flow.omit_unchanged_template_libraries(self, ranked, getattr(self, "refused_paths", ()))
            sources = select_source_snapshot(ranked, room, stable_order=True, max_output_chars=room,
                                             change_counts=self.source_change_counts())
            if sources is None:
                return None
            prompt = prompt.replace(current_sources, sources + "\n", 1)
        full = prompt + suffix
        if len(full) + len(FORMAT_INSTRUCTIONS) + 1 > limit:
            return None
        return full

    def tiny_mode(self, spec_chars: int) -> bool:
        """Tiny tier by spec size -- never once an application design exists:
        its fixed static server and design-free prompt would let that node pick
        its own routes and records, which is what the design is there to stop."""
        if getattr(self, "app_design_doc", None) or stack_note(getattr(self, "output_dir", None)):
            return False
        if getattr(self, "derived_as_specs", False):
            # A short derived spec (one reach check) is not evidence that a single
            # static page satisfies the requirement.
            return False
        threshold = int(os.environ.get("OCTOS_ARC_TINY_SPEC_CHARS", "1500"))
        return os.environ.get("OCTOS_ARC_TINY", "1") != "0" and 0 < spec_chars < threshold

    def tiny_turn(self, node_id: str, specs: list[str], timeout: int, requirement: dict) -> bool:
        """Tiny-spec tier: harness writes the manifests and a fixed static server, the
        model returns one index.html for the spec's statements. Returns True only when
        the node's specs pass right away; otherwise the caller falls back to the compact tier."""
        write_codegen_manifests(self.output_dir)
        server = self.output_dir / "backend" / "server.js"
        if not server.exists():
            server.parent.mkdir(parents=True, exist_ok=True)
            extra = [p for p in spec_base_ports(self.tests_dir) if p != self.web_port]
            server.write_text(TINY_SERVER_JS.format(port=self.web_port, extra_ports=json.dumps(extra)), encoding="utf-8")
        spec = "Requirement:\n" + describe_node(requirement) + "\nPublic example:\n" + self.spec_bodies(node_id)
        page = self.output_dir / "frontend" / "src" / "index.html"
        if page.is_file():
            prompt = TINY_PROMPT_EVOLUTION.format(page=page.read_text(encoding="utf-8", errors="replace").strip(), spec=spec)
        else:
            prompt = TINY_PROMPT.format(spec=spec)
        ok, _ = self.codegen_turn(prompt, timeout, f"{node_id} implement (tiny)", spec_chars=len(spec),
                                  system=TINY_SYSTEM, format_instructions="", raw_target="frontend/src/index.html")
        if not ok or not page.is_file() or self.runner is None or not specs:
            log(f"[flow] {node_id}: tiny tier produced no page; compact tier next")
            return False
        summary = self.run_specs(specs)
        passed = (not summary.error) and summary.total and summary.passed == summary.total
        log(f"[flow] {node_id}: tiny tier {'passed' if passed else 'failed'} its specs"
            f" ({summary.passed}/{summary.total})" if not summary.error else f"[flow] {node_id}: tiny tier could not run specs")
        if not passed:
            log(f"[acceptance] {node_id} first-attempt failure: {summary.error or failure_summaries(summary)}")
        return bool(passed)

    def codegen_reasoning(self, spec_chars: int) -> str | None:
        """Reasoning effort for a codegen turn, derived from the size of the spec it
        must satisfy (OCTOS_ARC_CODEGEN_REASONING_CHARS, default 5000): small specs are
        generated without reasoning; large ones keep the base mode. Retain the
        compact size rule when thinking is disabled by default too."""
        if default_reasoning_for_model(os.environ.get("OCTOS_MODEL") or os.environ.get("MODEL", "")) not in {"auto", "none", "off", "disabled"}:
            return None
        threshold = int(os.environ.get("OCTOS_ARC_CODEGEN_REASONING_CHARS", "5000"))
        return "none" if spec_chars and spec_chars < threshold else None

    def text_turn(self, prompt: str, timeout: int, label: str, *, system: str = CODEGEN_SYSTEM,
                  spec_chars: int = 0, request_budget: int | None = None) -> tuple[bool, str]:
        """One tool-less request; the reply is returned as text. Tool policy and
        the system prompt live on the proxy/driver for the duration and are
        restored whatever happens. codegen_turn parses file blocks out of it;
        app_design parses a JSON object."""
        proxy = getattr(self, "llm_proxy", None)
        if proxy is None:
            return False, "model proxy unavailable"
        proxy.no_tools = True
        proxy.system_override = system
        mode_override = self.codegen_reasoning(spec_chars)
        saved_cap = getattr(proxy, "codegen_max_tokens", 0)
        phase = phase_for_label(label)
        if phase == 'implement' and os.environ.get('OCTOS_ARC_IMPLEMENT_REASONING_ALL') == '1':
            experiment_mode = os.environ.get('OCTOS_ARC_IMPLEMENT_REASONING', '')
            if experiment_mode in {'none', 'low', 'medium', 'high'}:
                mode_override = experiment_mode
        recovering = getattr(self, "codegen_degenerated", False) and phase != "design"
        phase_cap = max(0, int(os.environ.get("OCTOS_ARC_REPAIR_MAX_TOKENS", "8192"))) if phase == "repair" else 0
        if phase == "design":
            # v9.2.2 github (e5ab5dab91c4): the 47-node design was cut at 8192
            # tokens; 256 tokens per leaf covers a route+page+contract entry.
            design_default = max(8192, min(16384, 256 * getattr(self, "n_nodes", 32)))
            phase_cap = max(0, int(os.environ.get("OCTOS_ARC_DESIGN_MAX_TOKENS", str(design_default))))
        recovery_cap = self.generation_recovery_cap() if recovering and phase == "implement" else (
            max(0, int(os.environ.get("OCTOS_ARC_DEGENERATE_MAX_TOKENS", "8192"))) if recovering else 0)
        proxy.codegen_max_tokens = min([cap for cap in (phase_cap, recovery_cap) if cap] or [0])
        recovery_mode = os.environ.get("OCTOS_ARC_RECOVERY_REASONING", "none")
        if recovering and recovery_mode in {"low", "medium", "high"}:
            mode_override = recovery_mode  # opt-in; otherwise retain the base effort
        saved_base = getattr(self, "base_reasoning_mode", proxy.mode)
        if mode_override:
            self.base_reasoning_mode = mode_override
        try:
            turn_budget = int(os.environ.get("OCTOS_ARC_CODEGEN_REQUESTS", "3"))
            if request_budget is not None:
                turn_budget = min(turn_budget, max(1, request_budget))
            with self.driver.without_tools():
                return self.turn(prompt, timeout, label, expect_verification=False,
                                 request_budget=turn_budget)
        finally:
            proxy.no_tools = False
            proxy.system_override = None
            self.base_reasoning_mode = saved_base
            proxy.codegen_max_tokens = saved_cap

    def prepare_build(self, tree: dict, ordered: list[dict]) -> None:
        """What happens before the first node: the application design (loaded
        or, on a fresh build, generated) or the skeleton turn, and the tree the
        first suite repair diffs against.

        The design is looked up in evolution mode too. Until 2026-09-19 only a
        fresh build called app_design, so a rerun over an existing app -- which
        is every rerun -- could never reuse the design it had stored; app_design
        itself only ever generates on a fresh build."""
        build_dir = getattr(self, "output_dir", None)
        if (not self.evolution and build_dir is not None and not app_source_files(build_dir) and self.codegen_mode()
                and os.environ.get("OCTOS_ARC_GENERIC_TEMPLATE", "1") != "0"):
            extra_ports = [p for p in spec_base_ports(self.tests_dir) if p != self.web_port]
            written = install_generic_template(build_dir, BUNDLE_DIR, self.web_port, extra_ports,
                                               react=os.environ.get("OCTOS_ARC_REACT", "1") == "1" and len(ordered) >= 3,
                                               capabilities=recommended_capabilities(tree))
            written += write_codegen_manifests(build_dir)
            if written:
                self.commit("chore: install task-neutral web scaffold")
                log(f"[flow] generic template: installed {written}")
            self.generic_template_installed = generic_template_active(build_dir)
        if self.codegen_mode() and os.environ.get("OCTOS_SKELETON_ALWAYS") != "1":
            if not self.evolution:
                log(f"[flow] {len(ordered)}-node tree: codegen mode, harness manifests replace the skeleton turn")
            if self.app_design(tree, ordered) and not getattr(self, "derived_as_specs", False):
                self.mark_designed(ordered)
        elif not self.evolution and (len(ordered) >= self.skeleton_min_nodes
                                     or os.environ.get("OCTOS_SKELETON_ALWAYS") == "1"):
            self.skeleton(tree)
            self.driver.end_scope("node")
        elif not self.evolution:
            log(f"[flow] {len(ordered)}-node tree: skeleton folded into the first node turn")
        # Reuse the global design to coordinate each top-level category. A
        # missing model design still yields a useful tree-derived contract.
        try:
            self.phase_plan = first_level_phases(tree, getattr(self, "app_design_doc", None))
        except (TypeError, ValueError) as exc:
            self.phase_plan = None
            self.metric("phase_plan", outcome="unavailable", reason=str(exc)[:300])
        if self.phase_plan and isinstance(getattr(self, "output_dir", None), Path):
            phase_path = self.output_dir / ".arc" / "design" / "phases.json"
            phase_path.parent.mkdir(parents=True, exist_ok=True)
            phase_path.write_text(json.dumps(self.phase_plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # The tree before any node of this run: the first suite repair quotes
        # what changed since it.
        self.last_checkpoint_sha = self.head()

    def prime_generation_dependencies(self) -> None:
        """Install/stamp dependencies once so per-wave checks can really build.

        This is a task-neutral preflight, not acceptance: a failure is recorded
        for the next generation turn and never substitutes for official specs.
        """
        if (os.environ.get("OCTOS_ARC_PRIME_GENERATION_BUILD", "1") == "0"
                or os.environ.get("OCTOS_ARC_DRYRUN") == "1" or not self.has_app()
                or self.wound_down() or self.remaining() < self.min_repair_seconds + 120):
            return
        started = time.monotonic()
        error = self.app_server(False).build()
        elapsed = round(time.monotonic() - started, 3)
        from generation_checks import preflight_failure_evidence
        failure = preflight_failure_evidence(error) if error else {}
        self.metric("generation_build_preflight", outcome="failed" if error else "ready",
                    elapsed_seconds=elapsed, **failure)
        if error:
            evidence = failure["error_excerpt"]
            if failure["cause_class"] == "source_or_module":
                self.pending_corrections.append(
                    "Generation build preflight found a source/module error. Verify before editing:\n" + evidence)
                self._generation_gate_evidence = evidence
            log(f"[flow] generation build preflight failed after {elapsed}s "
                f"({failure['cause_class']}); evidence recorded without treating infrastructure as app source")
        else:
            log(f"[flow] generation build preflight ready in {elapsed}s; per-wave frontend builds enabled")

    def app_design(self, tree: dict, ordered: list[dict]) -> dict | None:
        """One request over the tree's outline -> routes, pages and data model
        the whole run implements against (OCTOS_ARC_APP_DESIGN=0 disables).
        Only for a fresh codegen run of a tree at least design_min_nodes big:
        an existing app IS its design, and tool-mode nodes read the code.
        The document is kept on the flow and in .arc/design/app.json; a reply
        without a JSON object just leaves the run without one."""
        if os.environ.get("OCTOS_ARC_APP_DESIGN", "1") == "0" or not self.codegen_mode() \
                or len(ordered) < self.design_min_nodes:
            return None
        outline = tree_outline(tree, int(os.environ.get("OCTOS_ARC_APP_DESIGN_OUTLINE_CHARS", "60000")))
        # Cache identity includes omitted detail too, not just a budgeted outline.
        tree_sha = hashlib.sha256(json.dumps(tree, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        stored = self.stored_app_design(tree_sha)
        if stored is not None:
            self.app_design_doc = stored
            log("[flow] application design: reused .arc/design/app.json (same requirement tree and prompt version)")
            return stored
        if self.evolution:
            # An existing app is its own design; only a stored design made for
            # this exact tree is trusted over the code.
            return None
        prompt = stack_note(self.output_dir) + seed_contract_text(self) + APP_DESIGN_PROMPT.format(outline=outline)
        deadline = time.monotonic() + self.design_timeout
        ok, text = self.text_turn(prompt, self.design_timeout, "application design", system=APP_DESIGN_SYSTEM,
                                  spec_chars=len(outline))
        design = parse_app_design_reply(text) if ok else None
        if design is None:
            self.save_rejected_reply("application design", "invalid_json" if ok else "failed", text or "")
        wanted = {str(node.get("id")) for node in ordered if node.get("id")}
        coverage_floor = max(3, int(os.environ.get("OCTOS_ARC_DESIGN_COVERAGE_MIN_NODES", "8")))
        missing = wanted - app_design_coverage(design)
        # v9.2.2 (cce3f5ad4f21): the compact retry timed out at 120s; the model
        # needs ~90s for the first reply, the retry deserves as much.
        retry_seconds = min(240, int(deadline - time.monotonic()), int(self.remaining()))
        if ((ok and not design) or (not ok and 'output_truncated' in text)
                or (design and len(wanted) >= coverage_floor and missing)) \
                and retry_seconds >= 30 and not self.wound_down():
            invalid = parse_app_design_reply(text, validate=False) if ok and design is None else None
            schema_errors = app_design_errors(invalid) if invalid is not None else []
            reason = ("incomplete requirement ownership" if design and missing
                      else "schema errors" if schema_errors else "incomplete or invalid JSON")
            log(f"[flow] application design: {reason}; one bounded contract retry")
            # Repeating the full 60k-character outline encourages another
            # oversized reply. A compact shared contract is more useful than
            # losing the entire design because one leaf was too detailed.
            compact_outline = tree_outline(tree, max_chars=8000)
            retry_prompt = (stack_note(self.output_dir) +
                            'Create a compact shared web application contract for this requirement tree. '
                            'Return ONLY one valid JSON object, at most 12000 characters, with keys '
                            'data_model (object of collection objects), routes (array), pages (array), modules (array), '
                            'contracts (array), notes (string). Each module is {"path":"frontend/src/X.jsx","owns":["responsibility"]}; '
                            'backend module paths start backend/. Each contract has nonempty invariants (string array) '
                            'and requirements (ID array). Each route needs method, absolute path, '
                            'purpose and requirements; each page needs absolute path, purpose and requirements. '
                            'Every atomic requirement ID must appear in at least one route, page or contract '
                            'requirements list. Use one consistent, requirement-derived naming scheme and '
                            'cohesive module owners: exactly one backend route module per API resource prefix. '
                            'No markdown or prose.\n'
                            + compact_outline)
            if schema_errors:
                repair_context = ("\nCorrect only the invalid fields, preserving valid contracts and ownership."
                                  "\nSCHEMA ERRORS:\n" + json.dumps(schema_errors[:12], ensure_ascii=False)
                                  + "\nPREVIOUS OBJECT:\n" + json.dumps(invalid, ensure_ascii=False))
                if len(retry_prompt) + len(repair_context) <= self.codegen_context_chars():
                    retry_prompt += repair_context
                else:
                    retry_prompt += "\nSCHEMA ERRORS:\n" + json.dumps(schema_errors[:12], ensure_ascii=False)[:4000]
            elif design and missing:
                retry_prompt += "\nMissing ownership IDs: " + json.dumps(sorted(missing))
            self.metric("design_retry", reason=reason, schema_errors=schema_errors[:12])
            ok, text = self.text_turn(
                retry_prompt,
                retry_seconds, "application design (format retry)", system=APP_DESIGN_SYSTEM,
                spec_chars=len(compact_outline))
            retried = parse_app_design_reply(text) if ok else None
            if retried is None:
                self.save_rejected_reply("application design (format retry)", "invalid_json" if ok else "failed", text or "")
            if retried is not None and (design is None or
                    len(app_design_coverage(retried) & wanted) >= len(app_design_coverage(design) & wanted)):
                design = retried
        if not design:
            log("[flow] application design: no usable JSON object in the reply; nodes proceed without one")
            return None
        self.app_design_doc = design
        missing = wanted - app_design_coverage(design)
        if missing and len(wanted) >= coverage_floor:
            log(f"[flow] application design: {len(missing)}/{len(wanted)} requirement ids have no explicit "
                "artifact owner; implementation prompts retain their full contracts")
        design_dir = self.output_dir / ".arc" / "design"
        design_dir.mkdir(parents=True, exist_ok=True)
        (design_dir / "app.json").write_text(json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8")
        meta = {"tree_sha256": tree_sha, "prompt_version": APP_DESIGN_PROMPT_VERSION,
                "model": os.environ.get("MODEL") or os.environ.get("OCTOS_MODEL") or "",
                "design_sha256": hashlib.sha256(json.dumps(design, sort_keys=True).encode("utf-8")).hexdigest()}
        (design_dir / "app.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        log(f"[flow] application design: {len(design.get('routes') or [])} routes, {len(design.get('pages') or [])} pages, "
            f"{len(design.get('data_model') or {})} collections ({len(json.dumps(design, ensure_ascii=False))} chars)")
        return design

    def stored_app_design(self, tree_sha: str) -> dict | None:
        """The design persisted by an earlier run of the same requirement tree
        with the same prompt version, when its content still matches its
        recorded hash; None otherwise (missing, another tree, another prompt
        version, edited, or malformed)."""
        design_dir = self.output_dir / ".arc" / "design"
        try:
            meta = json.loads((design_dir / "app.meta.json").read_text(encoding="utf-8"))
            design = json.loads((design_dir / "app.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(meta, dict) or meta.get("tree_sha256") != tree_sha \
                or meta.get("prompt_version") != APP_DESIGN_PROMPT_VERSION:
            return None
        if hashlib.sha256(json.dumps(design, sort_keys=True).encode("utf-8")).hexdigest() != meta.get("design_sha256"):
            return None
        return valid_app_design(design)

    # -- suite repairs (regression checkpoints and the full suite) ------------
    def changed_files_since(self, sha: str | None) -> set[str]:
        """App files that differ from the tree at `sha`; empty without one or when git cannot answer."""
        if not sha:
            return set()
        try:
            result = self.runtime.git.run(["diff", "--name-only", sha, "--", "frontend", "backend"], check=False)
        except Exception as exc:  # noqa: BLE001
            log(f"[git] diff --name-only {sha[:8]} failed: {exc}")
            return set()
        if getattr(result, "returncode", 1) != 0:
            return set()
        return {line.strip() for line in (result.stdout or "").splitlines()
                if line.strip().startswith(("frontend/", "backend/")) and Path(line.strip()).name not in LOCKFILES}

    def suite_repair_prompt(self, failing_ids: list[str], failures: str) -> str | None:
        """One codegen prompt for the nodes a suite run found failing.

        Built like an implement turn -- rules, design, ranked sources, then the
        failures as evidence -- for the failing nodes together. The files changed
        since the tree the suite last agreed with are quoted first: a regression
        lives in what changed. None when nothing fits the budget; the caller
        then uses tool mode. Until 2026-09-19 every checkpoint and full-suite
        repair went straight to tool mode: 166-351 tool calls and 0.9-2.8 h per
        big run (temp-logs, seven cloud runs), with the per-turn timeout cutting
        many of them mid-edit.
        """
        nodes = getattr(self, "requirement_nodes", {}) or {}
        chosen = [n for n in failing_ids if n in nodes and self.spec_map.get(n)]
        if not chosen:
            return None
        limit = self.codegen_context_chars()
        specs = ""
        names: list[str] = []
        for node_id in chosen:
            # Helpers are shared by the candidate set, not copied once per
            # failing node. Keep full spec files and their reachable helpers.
            body = self.batch_spec_bodies([*names, node_id])
            if not body or body == "(none)":
                continue
            if len(body) > limit * 0.45:
                break
            specs = body
            names.append(node_id)
        if not specs:
            return None
        # Reasoning for the codegen turn is sized by these specs together, not by
        # the last single node's (which could put a multi-node repair at none).
        self.suite_spec_chars = len(specs)
        omitted = [n for n in chosen if n not in names]
        description = ("Repair the failing behaviours found by acceptance, preserving the original requirements:\n"
                       + "\n\n".join(describe_node(nodes[n]) for n in names))
        if omitted:
            description += f". Also failing, specs not shown: {', '.join(omitted)}"
        evidence = ("The current application fails these acceptance checks; fix them without breaking the "
                    "passing ones:\n" + balanced_failure_evidence(failures or "(no detail)", 8000) + "\n")
        changed = self.changed_files_since(getattr(self, "last_checkpoint_sha", None))
        # A concrete application refusal is stronger evidence than the whole
        # historical diff (which can include almost every file on the first
        # final suite). Otherwise retrying still crowds out the named target.
        must = set(getattr(self, "refused_paths", ())) or changed
        index = self.repair_source_index()
        localized = spec_targets(specs + '\n' + failures, [Path(p) for p in index.sources])
        if localized and not getattr(self, "refused_paths", ()):
            # Historical diffs may contain the entire generated application.
            # Prefer current failure ownership and its direct callers instead.
            must = localized | (changed & index.related(localized))
        node = {"id": ", ".join(names), "description": description}
        prompt = self.codegen_implement_prompt(node, specs, "", evidence=evidence, must_include=must)
        if prompt is None or not must:
            return prompt
        # must_include only ranks the changed files first; a file too big for the
        # room is still omitted, and the guard would refuse the rewrite the model
        # then attempts. With none of them quoted the request is that refusal.
        missing = sorted(must - quoted_paths(prompt))
        if len(missing) == len(must):
            log(f"[flow] suite repair: none of the priority files ({', '.join(missing)}) fit the codegen budget")
            return None
        if missing:
            log(f"[flow] suite repair: priority files not quoted whole: {', '.join(missing)}")
        return prompt

    def repair_source_index(self):
        from source_index import SourceIndex
        if not isinstance(getattr(self, 'output_dir', None), Path):
            return SourceIndex({})
        index = SourceIndex({str(p.relative_to(self.output_dir)): p.read_text(encoding="utf-8", errors="replace")
                             for p in app_source_files(self.output_dir)})
        versioned = app_source_files(self.output_dir, exts=None)
        versioned += [self.output_dir / part / name for part in ('frontend', 'backend')
                      for name in LOCKFILES if (self.output_dir / part / name).is_file()]
        index.versions = {str(p.relative_to(self.output_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in versioned}
        return index

    def repair_memory_context(self, prompt):
        current = self.repair_source_index().versions
        paths = quoted_paths(prompt)
        history = [r for r in getattr(self, '_repair_history', [])
                   if r['versions'] == current and (not paths or paths & set(r['paths']))]
        if not history:
            return ''
        lines = ['Recent harness observations for this exact source/dependency state (not a diagnosis):']
        for record in history[-3:]:
            lines.append(f"{record['label']}: {record['outcome']}; changed={', '.join(record['changed']) or 'none'}; "
                         f"verification={record.get('verification', 'not yet measured')}")
        return '\n' + '\n'.join(lines)[:2200] + '\nDo not repeat an unchanged attempt; use the current failure evidence.\n'

    def remember_repair(self, label, prompt, outcome):
        if phase_for_label(label) != 'repair':
            return
        changed = list(getattr(self, 'last_codegen_written', []))
        record = {'label': label, 'outcome': outcome, 'changed': changed,
                  'paths': sorted(quoted_paths(prompt) | set(changed)),
                  'versions': self.repair_source_index().versions}
        self._repair_history = (getattr(self, '_repair_history', []) + [record])[-8:]
        self.metric('repair_memory', label=label, outcome=outcome, changed=changed)

    def verify_repair_memory(self, summary, measured):
        current = self.repair_source_index().versions
        for record in getattr(self, '_repair_history', []):
            if record['versions'] == current:
                # A targeted run is explicitly not evidence of global success.
                record['verification'] = (f"{summary.passed}/{summary.total} observed in the latest test scope; "
                                          "not a claim about untested features") if measured else 'incomplete test verdict'

    def repair_tool_turn(self, prompt, timeout, label, request_budget: int | None = None):
        before = self.repair_source_index().versions
        prompt += self.repair_memory_context(prompt)
        ok, text = self.turn(prompt, timeout, label, request_budget=request_budget)
        after = self.repair_source_index().versions
        self.last_codegen_written = sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))
        self.generation_batch_check(label)
        self.remember_repair(label, prompt, 'applied' if self.last_codegen_written else 'unchanged' if ok else 'tool_incomplete')
        return ok, text

    def requirement_source_targets(self):
        paths = [p.relative_to(self.output_dir) for p in app_source_files(self.output_dir)]
        targets = {}
        for node, specs in self.spec_map.items():
            texts = []
            for spec in specs or []:
                path = self.tests_dir / spec
                if path.is_file():
                    texts.append(path.read_text(encoding="utf-8", errors="replace"))
            text = "\n".join(texts)
            targets[node] = spec_targets(text, paths) | navigation_targets(text, paths)
        return targets

    def affected_regression_specs(self, changed, already_run):
        """Retest affected proven behavior, not requirements still awaiting implementation.

        Shared changes run the proven set together with the current target.
        Final acceptance independently measures every requirement.
        """
        if not changed or not self.tests_dir:
            return []
        proven = {node for node, verdict in self.test_verdict.items() if verdict is True}
        current = set(already_run)
        prior_specs = {spec for node in proven for spec in self.spec_map.get(node, [])}
        if not prior_specs - current:
            return []
        all_specs = sorted(prior_specs | current)
        index = self.repair_source_index()
        affected = index.affected(changed)
        targets = {node: paths for node, paths in self.requirement_source_targets().items()
                   if node in proven or current & set(self.spec_map.get(node, []))}
        global_change = any(p.startswith('backend/') or p.endswith(('.json', '.html', '.css'))
                            or '/shared/' in p or Path(p).name in {'App.jsx', 'App.tsx', 'main.jsx', 'main.tsx'}
                            for p in changed)
        covered = set().union(*targets.values()) if targets else set()
        if global_change or not affected & covered or any(not v for v in targets.values()):
            return all_specs  # shared state requires testing together, including target
        return sorted({s for n, paths in targets.items() if paths & affected
                       for s in self.spec_map.get(n, [])} - set(already_run))

    def compact_tool_repair_prompt(self, prompt: str, failures: str = "") -> str:
        """Tools read current files on demand instead of carrying a 90k snapshot."""
        sources = self.sources_text()
        if sources.strip() and sources in prompt:
            replacement = (stack_note(self.output_dir) + "\nApplication source index (read the relevant files before editing):\n"
                           + source_listing(self.output_dir) + "\n")
            prompt = prompt.replace(sources, replacement, 1)
        if failures and failures in prompt:
            prompt = prompt.replace(failures, balanced_failure_evidence(failures, 12000), 1)
        return prompt

    def suite_repair_turn(self, label: str, failing_ids: list[str], failures: str, timeout: int, *,
                          tool_prompt: str, prefer_codegen: bool = True) -> tuple[str, str]:
        """Repair what a suite run found: one codegen request first, tool mode only
        when no codegen prompt fits or the caller wants a changed approach.
        Returns (mode, reply text); the codegen reply is file blocks, so its
        text is not an unfinished plan and comes back empty."""
        deadline = time.monotonic() + timeout
        reason = ""
        self.last_repair_changed = False
        round_spent = 0
        proxy = getattr(self, "llm_proxy", None)
        tool_prompt = self.compact_tool_repair_prompt(tool_prompt, failures)
        if prefer_codegen and self.codegen_mode(node_block=False):
            prompt = self.suite_repair_prompt(failing_ids, failures)
            if prompt is not None:
                spec_chars = getattr(self, "suite_spec_chars", 0)
                for attempt in range(2):
                    left = deadline - time.monotonic()
                    round_cap = max(1, int(os.environ.get("OCTOS_ARC_REPAIR_ROUND_REQUESTS", "12")))
                    allowance = round_cap - round_spent
                    if left <= 0 or self.wound_down() or allowance <= 0:
                        break
                    ok, reason = self.codegen_turn(prompt, left, label if not attempt else label + " (protocol retry)",
                                                   spec_chars=spec_chars, request_budget=allowance)
                    round_spent += getattr(proxy, "turn_upstream_requests", 0)
                    refused = set(getattr(self, "last_codegen_refused", set()))
                    self.last_repair_changed = self.last_repair_changed or bool(getattr(self, "last_codegen_written", []))
                    if getattr(self, "last_codegen_written", []) and not refused:
                        # A partial patch is evidence to measure, not proof that
                        # another model turn is needed before testing.
                        return "codegen", ""
                    if attempt or getattr(self, "last_codegen_degenerated", False) or deadline - time.monotonic() < 30:
                        break
                    if refused:
                        retry_evidence = failures
                        if getattr(self, "last_codegen_outcome", "") == "anchor_failed":
                            retry_evidence += "\nPatch application error (no edits applied):\n" + reason[:1200]
                        retry = self.suite_repair_prompt(failing_ids, retry_evidence)
                        if retry is None or not refused <= quoted_paths(retry):
                            break
                        prompt = retry
                    elif reason.startswith(("codegen reply contained no ", "mixed FILE and EDIT blocks")):
                        correction = ("\nPrevious reply was not applied: " + reason[:240] +
                                      "\nReturn only complete FILE blocks with exact terminators; one block per path.\n")
                        if len(prompt) + len(correction) + len(FORMAT_INSTRUCTIONS) + 1 > self.codegen_context_chars():
                            break
                        prompt += correction
                    else:
                        break
                log(f"[flow] {label}: codegen repair not fully applied; using tools with remaining budget")
            else:
                log(f"[flow] {label}: no codegen repair prompt within the budget; using tools")
        left = deadline - time.monotonic()
        if left < 30 or "local_turn_budget_exhausted" in reason or self.wound_down():
            # Do not restart a fresh tool allowance after a hard cap, or issue
            # a request that has no useful execution window left. The caller
            # retains current files and owns acceptance/next-round admission.
            log(f"[flow] {label}: no viable fallback window or request budget exhausted; returning to acceptance")
            return "unapplied", ""
        round_cap = max(1, int(os.environ.get("OCTOS_ARC_REPAIR_ROUND_REQUESTS", "12")))
        allowance = round_cap - round_spent
        if allowance <= 0:
            self.metric("repair_round_budget", label=label, spent=round_spent, cap=round_cap,
                        decision="no_fallback")
            return "unapplied", ""
        if reason:
            tool_prompt += "\nCodegen repair did not fully apply; inspect current files before editing. " + reason[:300] + "\n"
        self.last_turn_changed = None
        _, text = self.repair_tool_turn(tool_prompt, left, label, request_budget=allowance)
        changed = getattr(self, "last_turn_changed", None)
        self.last_repair_changed = True if self.last_repair_changed else changed
        return "tools", text

    def save_rejected_reply(self, label: str, outcome: str, reply: str) -> None:
        """Retain an unapplied model reply for local format diagnosis."""
        if not reply.strip():
            return
        try:
            folder = self.output_dir / '.arc' / 'rejected-replies'
            folder.mkdir(parents=True, exist_ok=True)
            name = re.sub(r'[^\w.-]+', '-', label).strip('-')[:80] or 'reply'
            path = folder / f'{time.time_ns()}-{name}-{outcome}.txt'
            path.write_text(reply, encoding='utf-8')
            log(f'[codegen] rejected reply retained at {path.relative_to(self.output_dir)}')
        except OSError as exc:
            log(f'[codegen] could not retain rejected reply: {exc}')

    def codegen_turn(self, prompt: str, timeout: int, label: str, spec_chars: int = 0,
                     system: str = CODEGEN_SYSTEM, format_instructions: str = FORMAT_INSTRUCTIONS,
                     raw_target: str | None = None, defer_shared_refusals: bool = False,
                     force_files: bool = False, request_budget: int | None = None) -> tuple[bool, str]:
        """Run a tool-less turn; apply complete files or exact anchored edits.
        `raw_target`: when the reply is a bare HTML document (tiny tier), write it there."""
        self.last_codegen_refused = set()
        self.last_codegen_deferred = set()
        self.last_codegen_written = []
        self.last_codegen_no_change = False
        self.last_codegen_degenerated = False
        if not raw_target and not force_files and self.use_structured_edits(prompt, label):
            return self.structured_edit_turn(prompt, timeout, label, request_budget=request_budget)
        if phase_for_label(label) == 'repair':
            memory = self.repair_memory_context(prompt)
            if len(prompt) + len(memory) + len(format_instructions) <= self.codegen_context_chars():
                prompt += memory
        started = time.monotonic()
        raw_reply = ""
        def result(ok: bool, text: str, outcome: str):
            self.last_codegen_outcome = outcome
            paths = set(self.last_codegen_written) | set(self.last_codegen_refused)
            application = {"label": label, "outcome": outcome,
                           "applied": list(self.last_codegen_written), "refused": sorted(self.last_codegen_refused),
                           "hashes": {rel: hashlib.sha256((self.output_dir / rel).read_bytes()).hexdigest()
                                      for rel in paths if (self.output_dir / rel).is_file()}}
            self.last_codegen_application = application
            self.metric("codegen_application", **application)
            if not ok and raw_reply:
                self.save_rejected_reply(label, outcome, raw_reply)
            self.remember_repair(label, prompt, outcome)
            if self.last_codegen_written:
                self.generation_batch_check(label)
            if phase_for_label(label) == "implement" and getattr(self, "codegen_degenerated", False):
                clean = ok and outcome == "applied" and not self.last_codegen_degenerated
                self.clean_codegen_streak = getattr(self, "clean_codegen_streak", 0) + 1 if clean else 0
                if self.clean_codegen_streak >= 2:
                    self.codegen_degenerated = False
                    self.metric("generation_recovered", label=label)
            elapsed = time.monotonic() - started
            if outcome == "applied" and phase_for_label(label) == "repair":
                durations = getattr(self, "repair_durations", {})
                durations.setdefault("codegen", []).append(elapsed)
                durations["codegen"] = durations["codegen"][-12:]
                self.repair_durations = durations
            self.metric("codegen", label=label, outcome=outcome,
                        elapsed_seconds=round(elapsed, 3),
                        changed_files=len(self.last_codegen_written), refused_files=len(self.last_codegen_refused))
            return ok, text
        ok, text = self.text_turn((prompt + "\n" + format_instructions) if format_instructions else prompt,
                                  timeout, label, system=system, spec_chars=spec_chars,
                                  request_budget=request_budget)
        truncated = False
        proxy = getattr(self, "llm_proxy", None)
        if (not ok and ("output_truncated" in text or "failed to parse response" in text)
                and isinstance(proxy, LlmProxy)):
            # A stream the guard cut (degenerate repetition, deadline) reaches the
            # kernel as a length-terminated completion, or as a parse failure when
            # the completion was malformed; either way the proxy retained the
            # text, and its terminated blocks are still worth applying.
            retained = proxy.take_truncated_reply(label)
            if retained:
                text, truncated = retained, True
                log(f"[codegen] {label}: recovering only terminated blocks from truncated response")
        raw_reply = text if ok or truncated else ""
        if (ok or truncated) and not raw_target:
            text, quality = prune_degenerate_edits(text)
            degenerated = (quality['cycle_trimmed'] or quality['repeated_edit_blocks'] >= 8
                          or quality['noop_edits'] >= 8 and quality['noop_chars'] >= 2048)
            if degenerated:
                self.codegen_degenerated = True
                self.last_codegen_degenerated = True
                log(f"[codegen] {label}: repetitive output detected; bounded future codegen replies")
            if quality['noop_edits'] or degenerated:
                self.metric("reply_quality", label=label, **quality)
            truncated = truncated or quality['cycle_trimmed']
            if ok and not truncated and not text.strip() and quality['noop_edits']:
                text = "<<<NO CHANGE>>>"
        files = parse_file_blocks(text) if ok or truncated else {}
        edits = parse_edit_blocks(text) if ok or truncated else []
        if ok and not files and not edits:
            normalized = normalize_paired_file_reply(text) or normalize_bare_file_reply(text)
            if normalized:
                text = normalized
                files = parse_file_blocks(text)
                self.metric("protocol_normalized", label=label, format="paired_or_bare_file_sections", files=len(files))
                log(f"[codegen] {label}: normalized complete FILE sections; applying normal write guards")
        if ok and not files and not edits and text.strip() == "<<<NO CHANGE>>>":
            self.last_codegen_no_change = True
            log(f"[codegen] {label}: existing implementation declared complete; acceptance will verify it")
            return result(True, text, "unchanged")
        if ok and not files and not edits and raw_target:
            html = strip_code_fences(text)
            if looks_like_markup(html):
                files = {raw_target: html}
        if (not raw_target and (ok or truncated) and getattr(self, "_atomic_codegen_response", False)
                and (truncated or incomplete_blocks(text))):
            error = "Incomplete FILE/EDIT output: no changes were applied; retry the complete active contract."
            self.pending_corrections.append(error)
            return result(False, error, "incomplete_blocks")
        if ok and not truncated and not raw_target and incomplete_blocks(text):
            error = ("Incomplete FILE/EDIT output: no changes were applied. "
                     "Return complete blocks with exact terminators; never nest FILE headers.")
            self.pending_corrections.append(error)
            return result(False, error, "incomplete_blocks")
        if files or edits:
            overlap = set(files) & {rel for rel, _, _ in edits}
            if overlap:
                error = f"mixed FILE and EDIT blocks for {', '.join(sorted(overlap))}; use one format per path"
                self.pending_corrections.append(error)
                log(f"[codegen] {label}: {error}")
                return result(False, error, "format_error")
            # A block for an existing file the prompt did not show whole is a blind
            # rewrite: the model cannot preserve what it never saw. Keep the file on
            # disk, tell the next turn, and let the specs decide what is still
            # missing. New files and files quoted whole are written as before; the
            # tiny tier's page is quoted in its own format, hence raw_target.
            shown = quoted_paths(prompt)
            outlined = outlined_paths(prompt)
            refused = sorted({rel for rel in files
                              if rel != raw_target and rel not in shown and (self.output_dir / rel).exists()}
                             | {rel for rel, _, _ in edits
                                if rel not in shown and rel not in outlined and (self.output_dir / rel).exists()})
            self.last_codegen_refused = set(refused)
            # A fresh scaffold can provoke the model to re-emit its unquoted
            # task-neutral helpers. When application files were also generated,
            # measure those files before spending another request to rewrite the
            # helpers. A failing acceptance round still requotes refused_paths.
            valid = [rel for rel in files if rel not in refused]
            valid += [rel for rel, _, _ in edits if rel not in refused]
            if (defer_shared_refusals and valid and refused
                    and getattr(self, "generic_template_installed", False)
                    and unchanged_task_neutral_helpers(self.output_dir, set(refused))):
                self.last_codegen_deferred = set(refused)
            for rel in refused:
                files.pop(rel, None)
                log(f"[codegen] {label}: refused {rel}: the file exists and the prompt did not show it whole")
            edits = [edit for edit in edits if edit[0] not in refused]
            if refused and hasattr(self, "refused_paths"):
                self.refused_paths.update(refused)
            if self.last_codegen_deferred:
                log(f"[codegen] {label}: deferred shared helper rewrite until acceptance: "
                    f"{', '.join(sorted(self.last_codegen_deferred))}")
            elif refused:
                self.pending_corrections.append(
                    f"Your previous reply changed {', '.join(refused)} without having been shown the file whole; "
                    "the block was discarded and the file kept as it was. Change only files quoted whole in the "
                    "prompt, or add new files.")
            if refused and not self.last_codegen_deferred and getattr(self, "_atomic_codegen_response", False):
                error = ("Atomic response not applied: required existing files were not quoted whole: "
                         + ", ".join(refused) + ". No caller/callee changes from this response were written.")
                self.pending_corrections.append(error)
                return result(False, error, "guard_refused")
            if edits:
                staged, errors = prepare_edit_files(self.output_dir, edits)
                if errors:
                    error = "Exact EDIT failed; no changes from this response were applied: " + "; ".join(errors[:4])
                    self.pending_corrections.append(error)
                    # No file was written. Let the normal one-retry path requote
                    # these targets with the concrete anchor failure instead of
                    # first running acceptance against unchanged source.
                    targets = {rel for rel, _, _ in edits if any(e.startswith(rel + ': ') for e in errors)}
                    self.last_codegen_refused.update(targets)
                    if hasattr(self, "refused_paths"):
                        self.refused_paths.update(targets)
                    log(f"[codegen] {label}: {error}")
                    return result(False, error, "anchor_failed")
                files.update(staged)
            if (getattr(self, "generic_template_installed", False) and "backend/server.js" in files
                    and not generic_entry_intact(files["backend/server.js"])
                    and generic_entry_intact(read_text_or_empty(self.output_dir / "backend/server.js"))):
                files.pop("backend/server.js")
                self.pending_corrections.append(
                    "backend/server.js is the installed generic entry; your rewrite dropped its header or its "
                    "route registry (require('./lib/arc'), mountTestHooks, trackRoutes, finishRegistration) and was "
                    "discarded. Register routes in backend/routes/*.js and keep the entry as it is.")
                log(f"[codegen] {label}: refused backend/server.js: rewrite drops the generic entry runtime")
                if not files:
                    return result(False, "codegen reply only rewrote the installed generic entry", "guard_refused")
            if not files:
                return result(False, f"codegen reply only changed files it was not shown: {', '.join(refused)}", "guard_refused")
            if getattr(self, "generic_template_installed", False):
                conflicts = introduced_route_conflicts(self.output_dir, files)
                if conflicts:
                    error = ("Route conflict; no changes from this response were applied:\n"
                             + "\n".join("- " + c["message"] for c in conflicts[:4]))
                    self.pending_corrections.append(error)
                    # Requote the owning files so the retry changes the existing handler.
                    targets = {rel for c in conflicts for rel in (c["owner_file"], c["file"])
                               if (self.output_dir / rel).is_file()}
                    self.last_codegen_refused.update(targets)
                    if hasattr(self, "refused_paths"):
                        self.refused_paths.update(targets)
                    log(f"[codegen] {label}: {error.splitlines()[0]} {conflicts[0]['message'][:200]}")
                    return result(False, error, "route_conflict")
            protocol_errors = source_protocol_errors(files)
            if protocol_errors:
                error = "Invalid source envelope; no changes were applied: " + "; ".join(protocol_errors[:4])
                self.pending_corrections.append(error)
                return result(False, error, "format_error")
            from generation_checks import helper_import_errors, placeholder_overwrites
            existing_sources = self.repair_source_index().sources
            placeholders = placeholder_overwrites(existing_sources, files)
            if placeholders:
                return result(False, "; ".join(placeholders), "placeholder_overwrite")
            candidates = dict(self.repair_source_index().sources)
            candidates.update(files)
            interface_errors = helper_import_errors(candidates, files)
            if interface_errors:
                error = 'Invalid installed-helper imports; no changes applied: ' + '; '.join(interface_errors[:4])
                self.pending_corrections.append(error)
                return result(False, error, 'helper_contract_error')
            from generation_checks import missing_export_errors, missing_local_import_errors
            export_errors = missing_export_errors(candidates, files)
            if getattr(self, "_atomic_codegen_response", False):
                export_errors += missing_local_import_errors(candidates, files)
            if export_errors:
                # Writing half of an interface change breaks the build for every
                # later batch (v10.2 github: api.js). Requote both ends instead.
                error = ('Broken module interface; no changes from this response were applied:\n'
                         + "\n".join("- " + e for e in export_errors[:4]))
                self.pending_corrections.append(error)
                targets = {rel for e in export_errors
                           for rel in re.findall(r"frontend/[\w./-]+\.(?:jsx?|tsx?|mjs)", e)
                           if (self.output_dir / rel).is_file()}
                self.last_codegen_refused.update(targets)
                if hasattr(self, "refused_paths"):
                    self.refused_paths.update(targets)
                log(f"[codegen] {label}: {error.splitlines()[0]} {export_errors[0][:200]}")
                return result(False, error, "export_contract")
            written = write_files(self.output_dir, files)
            self.last_codegen_written = written
            self.last_codegen_no_change = not written and not refused
            if "backend/server.js" in written:
                self.generic_template_installed = "Generic web entry" in files["backend/server.js"][:200]
            log(f"[codegen] {label}: wrote {len(written)} file(s): {written[:8]}")
            deduped = dedupe_nav_links(self.output_dir)
            if deduped:
                log(f"[codegen] {label}: removed static nav links duplicating the NAV placeholder in {deduped}")
            if truncated or incomplete_blocks(text):
                return result(False, "Incomplete FILE/EDIT output: complete blocks were applied; "
                              "inspect current files and finish only the missing changes.", "incomplete_blocks")
            return result(True, text, "partial" if refused else "applied" if written else "unchanged")
        if truncated:
            return result(False, "Truncated response contained no complete FILE/EDIT blocks", "incomplete_blocks")
        if ok:
            log(f"[codegen] {label}: reply contained no FILE or EDIT blocks")
            outcome = "incomplete_blocks" if re.search(r"(?m)^<<<(?:FILE|EDIT)\s", text) else "no_blocks"
            return result(False, "codegen reply contained no complete <<<FILE>>> or <<<EDIT>>> blocks", outcome)
        return result(ok, text, "generation_failed")

    def use_structured_edits(self, prompt: str, label: str) -> bool:
        """Full files for creation/small apps; tools for repairs/large existing files.

        The threshold concerns application code, not installed blueprint libraries
        or the size of the acceptance specification. Legacy mode remains available
        for controlled protocol comparisons.
        """
        if os.environ.get("OCTOS_ARC_STRUCTURED_EDITS", "1") == "0":
            return False
        if getattr(self, "llm_proxy", None) is None or not getattr(self, "output_dir", None):
            return False
        phase = phase_for_label(label)
        if phase not in {"implement", "repair"}:
            return False
        limit = max(1000, int(os.environ.get("OCTOS_ARC_EDIT_FILE_CHARS", "12000")))
        paths = self.edit_scope(prompt)
        broad_limit = max(1, int(os.environ.get("OCTOS_ARC_STRUCTURED_SCOPE_FILES", "3")))
        if phase == "implement" and len(paths) > broad_limit:
            # Iterative tools scale poorly for a broad feature wave and can hit
            # a hard request cap with mutually dependent files half-written.
            # The bounded FILE protocol is atomic at response granularity; a
            # focused repair can still switch back to tools afterwards.
            return False
        for path in app_source_files(self.output_dir):
            rel = str(path.relative_to(self.output_dir))
            if path.suffix not in {".js", ".jsx", ".ts", ".tsx", ".html", ".css"}:
                continue
            if "/shared/" in rel or path.name in {"build.mjs", "vite.config.mjs"}:
                continue
            if phase == "repair" and rel in paths and path.stat().st_size >= 1500:
                return True
            if rel in paths and path.stat().st_size >= limit:
                return True
        return False

    def structured_edit_turn(self, prompt: str, timeout: int, label: str,
                             request_budget: int | None = None) -> tuple[bool, str]:
        """Use the native read/edit/write loop, bounded by the caller's deadline.

        Keep requirements and test evidence; replace only verified whole-source
        quotations with an index. Native calls get individual application results.
        The protected-file hook rejects unsafe fuzzy/no-op edits before execution.
        """
        before = {str(p.relative_to(self.output_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in app_source_files(self.output_dir, exts=None)}
        # Scope is keyed by the original prompt, before memory/index additions.
        scope = self.edit_scope(prompt)
        if phase_for_label(label) == 'repair':
            prompt += self.repair_memory_context(prompt)
        from source_index import SourceIndex
        sources = {str(p.relative_to(self.output_dir)): p.read_text(encoding="utf-8", errors="replace")
                   for p in app_source_files(self.output_dir)}
        index = SourceIndex(sources)
        prompt += "\n" + index.render(scope) + "\n"
        related = index.related(scope)
        retained = 0
        # Select by relevance, but leave retained quotations in their original
        # stable order for prefix reuse. Never discard failure/spec evidence.
        for rel in sorted(quoted_paths(prompt), key=lambda p: (p not in scope, p not in related, p)):
            path = self.output_dir / rel
            if path.is_file():
                content = path.read_text(encoding="utf-8", errors="replace").rstrip()
                quoted = f"--- {rel} ---\n{content}\n"
                # Preserve small, already localized files instead of paying for
                # another read. Large files remain available through range reads.
                if quoted in prompt and retained + len(content) <= 16000:
                    retained += len(content)
                else:
                    prompt = prompt.replace(quoted, f"--- {rel} --- (read current file before editing)\n")
        prompt = prompt.replace("Return only requested file blocks.", "Use the supplied file tools.")
        prompt = prompt.replace("Output: complete FILE blocks for changed files only; do not re-emit unchanged modules. If already satisfied, reply exactly <<<NO CHANGE>>>.",
                                "Use tools for necessary changes only; finish when the requirements are satisfied.")
        prompt += ("\nThis is a tool-editing turn, not a text codegen response. Do not emit FILE/EDIT blocks or diffs. "
                   "Use the relevant acceptance spec/helper quotations when present. If they are not quoted, "
                   "read only the named active spec and its imported helpers; never scan future acceptance files. "
                   "Quoted source is the current disk snapshot; use it directly without redundant reads. "
                   "For unquoted files read current ranges, then use edit_file with path, old_string, new_string for small changes; "
                   "use write_file for new files or a necessary short full rewrite. Batch independent small calls. "
                   "If an edit fails, inspect the current source excerpt or read the file; do not guess the anchor. "
                   "Do not repeat identical or no-op edits. Preserve unrelated behavior and stop after the changes. "
                   "Use targeted grep and line-range reads; do not reread unchanged files to confirm an edit that succeeded. "
                   "Before changing a shared prop/callback, locate every caller and update all rendering branches. "
                   "Keep seed/create/update/read record shapes consistent; optional collections must not crash rendering. "
                   "Do not narrate a long diagnosis: issue the necessary edits and finish with a short summary. "
                   "The harness builds and runs acceptance immediately afterwards; no shell is available.\n")
        proxy = self.llm_proxy
        saved = set(getattr(proxy, "extra_drop_tools", set()))
        saved_cap = getattr(proxy, "tool_max_tokens", 0)
        saved_compaction = getattr(proxy, "compact_reads", False)
        saved_bounded = getattr(proxy, "bounded_edits", False)
        proxy.bounded_edits = True
        proxy.compact_reads = True
        # SourceIndex already supplies the complete app file catalog. Glob was
        # used in a measured repair only to scan all future acceptance specs,
        # exhausting its deadline without an edit; targeted grep/read remains.
        proxy.extra_drop_tools = saved | self.SHELL_TOOLS | {"diff_edit", "apply_patch", "glob"}
        proxy.tool_max_tokens = max(1024, int(os.environ.get("OCTOS_ARC_EDIT_MAX_TOKENS", "4096")))
        started = time.monotonic()
        try:
            configured = os.environ.get("OCTOS_ARC_EDIT_REQUESTS")
            if configured is None and phase_for_label(label) == 'implement':
                configured = os.environ.get("OCTOS_ARC_IMPLEMENT_REQUESTS")
            if configured is not None:
                turn_budget = int(configured)
            else:
                turn_budget = 8
            if request_budget is not None:
                turn_budget = min(turn_budget, max(1, request_budget))
            before_progress = self.app_source_digest()
            proxy.turn_progress = (lambda: self.app_source_digest() != before_progress) if configured is None else None
            extension_cap = max(8, int(os.environ.get("OCTOS_ARC_NO_SPEC_EDIT_REQUESTS", "12")))
            proxy.turn_extension_limit = (min(extension_cap, request_budget) if request_budget is not None
                                          else extension_cap) if configured is None else 0
            ok, text = self.turn(prompt, timeout, label + " (structured edits)", expect_verification=False,
                                 request_budget=max(1, turn_budget))
        finally:
            proxy.turn_progress = None
            proxy.turn_extension_limit = 0
            proxy.extra_drop_tools = saved
            proxy.tool_max_tokens = saved_cap
            proxy.compact_reads = saved_compaction
            proxy.bounded_edits = saved_bounded
        after = {str(p.relative_to(self.output_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in app_source_files(self.output_dir, exts=None)}
        self.last_codegen_written = sorted(rel for rel in before.keys() | after.keys() if before.get(rel) != after.get(rel))
        self.last_codegen_no_change = ok and not self.last_codegen_written
        self.last_codegen_outcome = "applied" if ok and self.last_codegen_written else "unchanged" if ok else "tool_incomplete"
        self.remember_repair(label, prompt, self.last_codegen_outcome)
        if self.last_codegen_written:
            self.generation_batch_check(label)
        self.metric("structured_edit", label=label, outcome=self.last_codegen_outcome,
                    elapsed_seconds=round(time.monotonic() - started, 3),
                    changed_files=len(self.last_codegen_written),
                    retained_source_chars=retained, scope_files=len(scope))
        # Do not feed final tool prose into the FILE protocol-retry detector.
        return ok, "" if ok else "Structured editing incomplete; inspect current files before continuing. " + text[-300:]

    def codegen_ports_clause(self) -> str:
        if getattr(self, "generic_template_installed", False):
            # The scaffold already binds every discovered test port. Repeating
            # the implementation instruction can provoke a needless server rewrite.
            return ""
        extra = [p for p in spec_base_ports(self.tests_dir) if p != self.web_port]
        if not extra:
            return ""
        ports = ", ".join(map(str, extra))
        return (f" The tests default to port(s) {ports} while the grader sets only PORT: ALSO listen on {ports} with a "
                f"separate http.createServer(handler) (same handler) unless process.env.ARC_EXTRA_PORTS === '0'.")

    def spec_bodies(self, node_id: str | None) -> str:
        """The node's spec files, plus the parts of the shared helper files
        those specs reach (see trim_helper_to_references). Without spec files
        for the node -- a suite-wide repair -- the helpers are quoted whole."""
        if not self.tests_dir:
            ids = None if node_id is None else [node_id]
            return render_contracts(self.requirement_contracts, ids,
                                    int(os.environ.get("OCTOS_ARC_REQUIREMENT_CONTRACT_CHARS", "12000")),
                                    include_steps=True, require_all=ids is not None)
        specs = list(self.spec_map.get(node_id) or [])
        if (node_id is not None and not specs and getattr(self, "derived_as_specs", False)
                and self.has_requirement_contract(node_id)):
            return render_contracts(self.requirement_contracts, [node_id],
                                    int(os.environ.get("OCTOS_ARC_REQUIREMENT_CONTRACT_CHARS", "12000")),
                                    include_steps=True, require_all=True)
        helpers = sorted(str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob("*.ts")
                         if not p.name.endswith(".spec.ts") and str(p.relative_to(self.tests_dir)) not in specs)
        texts: dict[str, str] = {}
        for rel in specs + helpers:
            try:
                texts[rel] = (self.tests_dir / rel).read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                continue
        if specs:
            referenced = set()
            for rel in specs:
                referenced |= set(_IDENT.findall(texts.get(rel, "")))
            for rel in helpers:
                if rel in texts:
                    texts[rel] = trim_helper_to_references(texts[rel], referenced).strip()
        files = [rel for rel in specs + helpers if texts.get(rel)]
        parts = [texts[rel] if len(files) == 1 else f"--- {rel} ---\n{texts[rel]}" for rel in files]
        body = "\n".join(parts)
        return (self.derived_note() + body) if body else "(none)"

    def derived_note(self) -> str:
        return DERIVED_SPECS_NOTE if getattr(self, "derived_as_specs", False) else ""

    def has_requirement_contract(self, node_id: str) -> bool:
        return any(str(node.get("id")) == node_id
                   for node in (self.requirement_contracts or {}).get("nodes", []))

    def batch_spec_bodies(self, node_ids: list[str]) -> str:
        """Quote a batch's specs and reachable helpers once, not once per leaf."""
        if not self.tests_dir:
            return render_contracts(self.requirement_contracts, node_ids,
                                    int(os.environ.get("OCTOS_ARC_REQUIREMENT_CONTRACT_CHARS", "30000")),
                                    include_steps=True, require_all=True)
        specs = list(dict.fromkeys(path for node_id in node_ids for path in (self.spec_map.get(node_id) or [])))
        missing = ([node_id for node_id in node_ids
                    if not self.spec_map.get(node_id) and self.has_requirement_contract(node_id)]
                   if getattr(self, "derived_as_specs", False) else [])
        if not specs and getattr(self, "derived_as_specs", False):
            if not missing:
                return "(none)"
            return render_contracts(self.requirement_contracts, node_ids,
                                    int(os.environ.get("OCTOS_ARC_REQUIREMENT_CONTRACT_CHARS", "30000")),
                                    include_steps=True, require_all=True)
        helpers = sorted(str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob("*.ts")
                         if not p.name.endswith(".spec.ts") and str(p.relative_to(self.tests_dir)) not in specs)
        texts: dict[str, str] = {}
        for rel in specs + helpers:
            try:
                texts[rel] = (self.tests_dir / rel).read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                continue
        referenced = {ident for rel in specs for ident in _IDENT.findall(texts.get(rel, ""))}
        for rel in helpers:
            if rel in texts:
                texts[rel] = trim_helper_to_references(texts[rel], referenced).strip()
        body = "\n".join(f"--- {rel} ---\n{texts[rel]}" for rel in specs + helpers if texts.get(rel))
        if body and missing:
            contracts = render_contracts(self.requirement_contracts, missing,
                                         int(os.environ.get("OCTOS_ARC_REQUIREMENT_CONTRACT_CHARS", "30000")),
                                         include_steps=True, require_all=True)
            body += "\n\n--- Nodes without generated specs: requirement contracts ---\n" + contracts
        if not body and getattr(self, "derived_as_specs", False):
            if not missing:
                return "(none)"
            return render_contracts(self.requirement_contracts, node_ids,
                                    int(os.environ.get("OCTOS_ARC_REQUIREMENT_CONTRACT_CHARS", "30000")),
                                    include_steps=True, require_all=True)
        return (self.derived_note() + body) if body else "(none)"

    def repair_requirements(self, node_id: str | None = None) -> str:
        nodes = getattr(self, "requirement_nodes", {})
        selected = [nodes[node_id]] if node_id in nodes else ([] if node_id is not None else nodes.values())
        text = "\n\n".join(describe_node(node) for node in selected)
        if not text:
            return ""
        return ("Original requirements (read-only; preserve details even when acceptance does not assert them):\n"
                + text + "\n")

    def repair_test_location(self, specs: list[str] | None = None) -> str:
        if not self.tests_dir:
            return ""
        context = (f"Application directory: {self.output_dir.resolve()}. "
                   f"Read-only acceptance directory: {self.tests_dir.resolve()}. "
                   "Relative spec paths in failure reports refer to this directory. "
                   "Read relevant specs and helpers here when needed.\n")
        runner = getattr(self, "runner", None)
        if runner:
            helper = BUNDLE_DIR / "verify_app.py"
            binary = runner.root / "node_modules" / ".bin" / "playwright"
            if helper.is_file() and binary.is_file():
                args = ["env"]
                browsers = getattr(runner, "env_extra", {}).get("PLAYWRIGHT_BROWSERS_PATH")
                if browsers is not None:
                    args.append(f"PLAYWRIGHT_BROWSERS_PATH={browsers}")
                args.extend([sys.executable, str(helper), "--app", str(self.output_dir.resolve()),
                             "--tests", str(self.tests_dir.resolve()), "--playwright", str(runner.root)])
                workers = runner.workers if specs else workers_for_final(
                    getattr(self, "mem_limit", None), self.final_workers())
                args.extend(["--workers", str(workers)])
                for spec in specs or []:
                    args.extend(["--spec", spec])
                context += ("Isolated acceptance entry (builds and starts a disposable application copy):\n"
                            f"```sh\n{shlex.join(args)}\n```\n"
                            "Use this command for acceptance checks so test writes do not alter the source application's data. "
                            "Edit the source application, not the disposable copy or read-only tests. "
                            "The command prints failures and a report path. The harness re-runs acceptance after your edits.\n")
        return context

    def app_repair_prompt(self, **fields) -> str:
        template = DERIVED_REPAIR_PROMPT if getattr(self, "derived_as_specs", False) else REPAIR_PROMPT
        return template.format(**fields)

    def tests_prompt_for(self, node_id: str | None, skeleton: bool = False) -> str:
        if not self.tests_dir:
            ids = None if node_id is None else [node_id]
            cap_default = "30000" if node_id is None else "12000"
            return render_contracts(self.requirement_contracts, ids,
                                    int(os.environ.get("OCTOS_ARC_REQUIREMENT_CONTRACT_CHARS", cap_default)),
                                    include_steps=True, require_all=ids is not None)
        if skeleton:
            support = sorted(str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob("*.ts")
                             if not p.name.endswith(".spec.ts"))
            n_specs = len(list(self.tests_dir.rglob("*.spec.ts")))
            return self.derived_note() + (
                    f"The {'derived' if getattr(self, 'derived_as_specs', False) else 'official'} Playwright specs "
                    f"({n_specs} files) live under {self.tests_dir}; each later turn "
                    f"receives the spec files for its own node. In THIS turn read only the shared helpers "
                    f"({', '.join(support[:10]) or 'none'}) and at most two spec files to learn the base URL, "
                    f"navigation and header conventions; do not implement the features yet.\n"
                    + acceptance_tests_prompt(self.tests_dir, self.web_port, self.smoke_port, []).split("\n", 1)[-1])
        files = list(self.spec_map.get(node_id) or [])
        if (node_id is not None and not files and getattr(self, "derived_as_specs", False)
                and self.has_requirement_contract(node_id)):
            return render_contracts(self.requirement_contracts, [node_id],
                                    int(os.environ.get("OCTOS_ARC_REQUIREMENT_CONTRACT_CHARS", "12000")),
                                    include_steps=True, require_all=True)
        support = sorted(str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob("*.ts")
                         if not p.name.endswith(".spec.ts"))
        if not files:  # node without its own spec: show everything
            files = sorted(str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob("*.spec.ts"))
        return self.derived_note() + acceptance_tests_prompt(
            self.tests_dir, self.web_port, self.smoke_port, files + support,
            inline=os.environ.get("OCTOS_ARC_INLINE_SPECS", "1") != "0")

    def ancestors_text(self, node_id: str, ordered: list[dict]) -> str:
        anc = ancestors_of(node_id, ordered)
        if not anc:
            return ""
        parts = []
        for dep in anc:
            design = self.designs.get(dep)
            if design:
                slim = {k: design.get(k) for k in ("routes", "pages", "data_model") if design.get(k)}
                parts.append(f"{dep}: {json.dumps(slim, ensure_ascii=False)[:1500]}")
            else:
                parts.append(f"{dep}: implemented (see code)")
        return "Already implemented dependencies — reuse their routes/data, never break them:\n" + "\n".join(parts) + "\n"

    # -- git --------------------------------------------------------------
    def head(self) -> str | None:
        runtime = getattr(self, "runtime", None)
        return runtime.git.current_head() if runtime is not None else None

    def commit(self, message: str) -> bool:
        try:
            return self.runtime.git.commit(message)
        except Exception as exc:  # noqa: BLE001
            log(f"[git] commit failed: {exc}")
            return False

    def last_repair_diff(self, max_chars: int = 900) -> str:
        """What the previous repair commit actually changed.

        The harness commits after every repair, so when a round reproduces the
        round before it, git can say whether anything moved and where. Cloud
        e767e871a6c6 ran four rounds over eleven failures that never budged, and
        the in-repo record of 91aaecaf31af and 5747e6bcf530 is that repeated
        repairs re-emit the same files. "You changed these and nothing moved" is
        a different instruction from "it failed again".
        """
        git = getattr(getattr(self, "runtime", None), "git", None)
        if git is None:
            return ""  # a diagnostic must never be what breaks the repair loop
        try:
            result = git.run(["diff", "HEAD~1", "HEAD", "--stat", "--", "frontend", "backend"], check=False)
        except Exception as exc:  # noqa: BLE001
            log(f"[git] could not read the last repair: {exc}")
            return ""
        stat = (getattr(result, "stdout", "") or "").strip()
        if not stat:
            return ("\n\nThe previous repair left frontend/ and backend/ unchanged, so this result is the "
                    "same code measured twice. Make an edit this time.")
        return ("\n\nThe previous repair changed this and the failures did not move:\n"
                + clip_ends(stat, max_chars))

    def unfinished_repair_note(self, text: str, max_chars: int = 700) -> str:
        """Hand the previous repair turn's closing words to the next round.

        A repair turn can end before it edits anything: reading one large source
        file eats the turn, or the per-turn timeout lands mid-plan. Cloud
        e767e871a6c6 lost all three full-suite rounds that way and finished at
        20/32 -- "No files were modified ... Next step is to apply those edits to
        frontend/src/index.html", then "Need one more turn to read the note-action
        click handlers". That run was capped at ten requests per repair, a cap
        since lifted, but the waste it exposed is not about the cap: each round
        said exactly where it had got to, the message was dropped, and the next
        round paid to read the same file again. Hand it forward. The conclusion
        sits at the end of the message, so keep the tail.
        """
        text = (text or "").strip()
        if not text:
            return ""
        if len(text) > max_chars:
            text = "… " + text[-max_chars:].lstrip()
        return ("\n\nWhere the last repair attempt stopped, in its own closing words. It ran on a tool "
                "budget and may have run out before it could edit anything, so treat this as work already "
                "done: continue from it rather than reading the same files again.\n" + text)

    def restore_app(self, sha: str) -> None:
        git = self.runtime.git
        for part in ("frontend", "backend"):
            if (self.output_dir / part).exists():
                # Unlike checkout's overlay mode, restore also removes tracked
                # files introduced by the rejected repair after this snapshot.
                git.run(["restore", f"--source={sha}", "--staged", "--worktree", "--", part])
        git.run(["clean", "-fd", "-e", "node_modules", "-e", "dist", "--", "frontend", "backend"], check=False)
        log(f"[flow] restored frontend/ and backend/ to best commit {sha[:8]}")

    # -- acceptance -------------------------------------------------------
    def setup_playwright(self) -> None:
        """Prefer the Playwright already on the machine (the runner image ships
        one). A private install is the last resort and never touches shared
        state: own npm cache, own browser dir, pinned version, removed at exit.
        Run da9a64b32c09: an unisolated install made the platform's own
        `npx playwright test` resolve a different version whose chromium build
        was missing, and every graded test failed."""
        if not self.tests_dir:
            return
        self.runner = self.playwright_runner(self.tests_dir)

    def playwright_runner(self, tests_dir: Path) -> AcceptanceRunner | None:
        env_extra: dict = {}
        root = find_playwright_root(playwright_candidates(BUNDLE_DIR, tests_dir, self.output_dir))
        if root is None:
            root = find_playwright_by_search(log)
        if root is None and os.environ.get("OCTOS_ARC_INSTALL_PLAYWRIGHT", "1") != "0":
            version = playwright_version_hint(tests_dir)
            log(f"[acceptance] no preinstalled Playwright found; private install of @playwright/test@{version}")
            self.private_playwright = Path(tempfile.mkdtemp(prefix="octos-arc-playwright-"))
            installed = ensure_playwright(self.private_playwright, log, version=version)
            if installed:
                root, env_extra = installed
        if root is None:
            log("[acceptance] Playwright unavailable; nodes will be judged by the final check only")
            return None
        limit = container_memory_limit()
        self.mem_limit = limit
        workers = workers_for_memory(limit, int(os.environ.get("OCTOS_ARC_TEST_WORKERS", "2")))
        runner = AcceptanceRunner(root, tests_dir, acceptance_work_dir(root), log,
                                  timeout_ms=int(os.environ.get("OCTOS_ARC_TEST_TIMEOUT_MS", "10000")),
                                  workers=workers, env_extra=env_extra)
        log(f"[acceptance] using Playwright at {root}; workers={workers}"
            + (f" (container memory limit {limit // (1024 * 1024)} MiB)" if limit else ""))
        return runner

    def snapshot_protected(self) -> None:
        """Copy the official tests dir (and requirements) so any edit the model
        sneaks past the hook (e.g. via a shell redirect) is undone after the
        turn — the platform grades with THESE files."""
        for _, snapshot, _ in getattr(self, 'protected_snapshots', []):
            shutil.rmtree(snapshot.parent, ignore_errors=True)
        self.protected_snapshots = []
        control = self.output_dir / '.arc' / 'test-control'
        control.mkdir(parents=True, exist_ok=True)
        for live in (self.tests_dir, self.req_dir, control):
            if not live or not live.is_dir():
                continue
            snap = Path(tempfile.mkdtemp(prefix="octos-protected-"))
            shutil.copytree(live, snap / "tree", ignore=shutil.ignore_patterns("node_modules"))
            self.protected_snapshots.append((live, snap / "tree", tree_digest(live)))

    def restore_protected(self) -> list[str]:
        fixed_all: list[str] = []
        for live, snap, digest in getattr(self, "protected_snapshots", []):
            try:
                fixed = restore_tree(live, snap, digest)
            except OSError as exc:
                log(f"[guard] could not restore {live}: {exc}")
                continue
            if fixed:
                log(f"[guard] restored {len(fixed)} protected file(s) under {live}: {fixed[:5]}")
                fixed_all.extend(f"{live}/{rel}" for rel in fixed)
        return fixed_all

    def start_llm_proxy(self) -> None:
        """Default to model-specific reasoning; explicit settings take priority.
        Exact per-request usage lands in .arc/llm-usage.jsonl."""
        mode = default_reasoning_for_model(os.environ.get("OCTOS_MODEL") or os.environ.get("MODEL", ""))
        if mode == "auto":
            # Thinking off is safe for one-node builds and one-node evolutions
            # (v10: Counter/Dice/Evolution all pass, completion 0.5-1.9k tokens)
            # but TB repairs without thinking looped 22 calls with no write.
            mode = "none" if getattr(self, "nodes_to_implement", 2) <= 1 else "low"
        upstream = os.environ.get("OPENAI_BASE_URL", "")
        routes_configured = bool(json.loads(configured_model_routes() or "[]"))
        if mode == "passthrough" and not routes_configured:
            return
        if not upstream.startswith("http"):
            if routes_configured:
                raise ValueError("model routing requires an HTTP provider endpoint")
            return
        try:
            dump = (self.output_dir / ".arc" / "llm-requests") if os.environ.get("OCTOS_ARC_PROXY_DUMP") == "1" else None
            self.llm_proxy = LlmProxy(upstream, mode, self.output_dir / ".arc" / "llm-usage.jsonl", dump_dir=dump,
                                      destream=os.environ.get("OCTOS_ARC_DESTREAM", "1") != "0",
                                      trim=os.environ.get("OCTOS_ARC_TRIM_PROMPT", "1") != "0",
                                      min_max_tokens=int(os.environ.get("OCTOS_ARC_MAX_TOKENS", "32768"))).start()
        except OSError as exc:
            if routes_configured:
                raise
            log(f"[proxy] could not start local LLM proxy ({exc}); using the endpoint directly")
            return
        self.base_reasoning_mode = mode
        os.environ["OCTOS_ARC_EDIT_ARGUMENTS_DIR"] = self.llm_proxy.enable_edit_preflight()
        os.environ["OPENAI_BASE_URL"] = self.llm_proxy.base_url
        log(f"[proxy] LLM requests via {self.llm_proxy.base_url} -> {upstream} (reasoning={mode}, "
            f"destream={'on' if self.llm_proxy.destream else 'off'}, trim={'on' if self.llm_proxy.trim else 'off'})")

    def stop_llm_proxy(self) -> None:
        proxy = getattr(self, "llm_proxy", None)
        if proxy:
            proxy.stop()
            blocked = getattr(proxy, 'terminal_blocked_requests', 0)
            if blocked:
                log(f'[usage] terminal account guard blocked {blocked} local retries; no upstream requests sent')
        self.log_usage_summary()

    def log_usage_summary(self) -> None:
        """Print proxy-observed usage and missing-usage requests for reconciliation.

        Platform metering can differ from these provider response records, so
        neither a high cache-hit percentage nor a zero-valued missing record
        should be mistaken for a complete billable-token account.
        """
        path = self.output_dir / ".arc" / "llm-usage.jsonl"
        if not path.is_file():
            return
        tot = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0,
               "prompt_cache_hit_tokens": 0, "total_tokens": 0, "request_bytes": 0, "response_bytes": 0,
               "sse_chunks": 0, "no_usage": 0, "guard_token_estimate": 0}
        missing: list[dict] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            tot["requests"] += 1
            for k in list(tot)[1:]:
                tot[k] += int(rec.get(k) or 0)
            if rec.get("no_usage"):
                missing.append({key: rec.get(key) for key in
                                ("label", "phase", "status", "elapsed_ms", "request_bytes", "response_bytes",
                                 "guard_token_estimate")})
        log(f"[usage] provider totals: {json.dumps(tot)}")
        prompt = tot["prompt_tokens"]
        hit = tot["prompt_cache_hit_tokens"]
        if prompt:
            log(f"[usage] observed prompt cache: hit={hit}/{prompt} ({hit / prompt:.1%}), "
                f"miss={max(0, prompt - hit)}; completion={tot['completion_tokens']}")
        if missing:
            log(f"[usage] {len(missing)} request(s) lacked provider usage; "
                f"not counted as zero-cost: {json.dumps(missing[:8])}")

    def cleanup_playwright(self) -> None:
        private = getattr(self, "private_playwright", None)
        if private and Path(private).exists():
            shutil.rmtree(private, ignore_errors=True)
            log(f"[acceptance] removed private Playwright install {private}")

    def runtime_data_dir(self, purpose: str) -> Path:
        """Where a local server keeps its JSON stores: under .arc (git-ignored,
        never shipped), one directory per purpose, never backend/data."""
        return self.output_dir / ".arc" / "runtime-data" / purpose

    def app_server(self, grader_like: bool, test_hooks: bool = True) -> AppServer:
        """Acceptance servers start from the code seeds in a private data
        directory and expose POST /__arc/reset, which every derived test calls
        first. The startup rehearsal passes test_hooks=False: exactly the
        grader's environment except where the data lives."""
        purpose = "acceptance" if test_hooks else "rehearsal"
        env = {"ARC_DATA_DIR": str(self.runtime_data_dir(purpose))}
        if test_hooks:
            env["ARC_TEST_HOOKS"] = "1"
        return AppServer(self.output_dir, self.smoke_port, log, env_extra=env, grader_like=grader_like,
                         extra_ports=[p for p in spec_base_ports(self.tests_dir) if p != self.web_port])

    def generated_load_errors(self, specs: list[str]) -> list[str]:
        if (not getattr(self, "derived_as_specs", False)
                or self.tests_dir != getattr(self, "derived_tests_dir", None)):
            return []
        try:
            data = json.loads((self.output_dir / ".arc/test-control/load-errors/blocked-files.json").read_text())
        except (OSError, ValueError):
            return []
        if not isinstance(data, dict):
            return []
        errors = []
        for rel in specs:
            row = data.get(rel)
            if not isinstance(row, dict):
                continue
            try:
                current = hashlib.sha256((self.tests_dir / rel).read_bytes()).hexdigest()
            except OSError:
                continue
            if current == row.get("file_hash"):
                errors.append(f"{rel}: {row.get('reason', 'generated test does not load')}")
        return errors

    def run_specs(self, specs: list[str], workers: int | None = None, grader_like: bool = False,
                  runner: AcceptanceRunner | None = None) -> RunSummary:
        """Build, start, run the specs, then undo whatever the test run mutated
        (a persisted counter at -1 would otherwise be committed as the seed).
        `grader_like` starts the backend with only PORT set, as the platform does."""
        started = time.monotonic()
        blocked = self.generated_load_errors(specs)
        if blocked:
            return RunSummary(error="generated test load blocked: " + "; ".join(blocked), load_errors=blocked)
        if self.time_up():
            return RunSummary(error="acceptance time budget exhausted")
        git_run = lambda args: self.runtime.git.run(args, check=False)  # noqa: E731
        snapshot_worktree(git_run)
        server = self.app_server(grader_like)
        summary: RunSummary | None = None
        try:
            err = server.build()
            if err is None:
                err = server.start()
            if err is not None:
                return RunSummary(error=err)
            self.note_startable_commit(git_run)
            # A derived suite has one spec file per leaf (47 for the GitHub task);
            # a fixed 900s wall would kill the full run before its verdict.
            policy = self.generated_test_policy()
            active_runner = runner or self.runner
            active_runner.derived_policy = policy
            wall = max(900, 30 * len(specs))
            if getattr(self, "derived_as_specs", False):
                # Derived scripts mutate the shared seeds (rename the seeded
                # workbook, import, delete); two workers made "Q3 Sales" vanish
                # under a concurrent entry check (v9.2.3 03a2e937517e). Sequential.
                workers = max(1, int(os.environ.get("OCTOS_ARC_DERIVED_WORKERS", "1")))
            if (getattr(self, "derived_as_specs", False) and len(specs) > 1
                    and os.environ.get("OCTOS_ARC_DERIVED_ISOLATE", "1") != "0"):
                summary = self.run_isolated(runner or self.runner, specs, server, git_run, workers)
            else:
                summary = (runner or self.runner).run(specs, f"http://127.0.0.1:{self.smoke_port}", workers=workers,
                                          wall_timeout=max(1, min(wall, int(self.remaining()))))
            if not summary.all_passed:
                summary.server_errors = backend_error_digest(server.tail(5000))
            warnings = list(getattr(server, "warnings", None) or [])
            summary.scaffold_warnings = warnings
            if warnings and warnings != getattr(self, "_logged_scaffold_warnings", None):
                self._logged_scaffold_warnings = warnings
                log(f"[acceptance] {len(warnings)} source warning(s), not blocking: "
                    + " | ".join(w[:160] for w in warnings[:3]))
            expected = sorted(str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob("*.spec.ts")) if self.tests_dir else []
            if grader_like and sorted(specs) == expected and self.suite_is_measured(summary, specs):
                self.last_suite_seconds = time.monotonic() - started
            return summary
        finally:
            server.stop()
            # Ask before restoring: afterwards there is nothing left to compare.
            if summary is not None:
                # Keep the per-file mutation record of an isolated run; add what
                # the last file left behind.
                summary.stores_written = sorted(set(summary.stores_written) | set(mutated_by_tests(git_run)))
                summary.store_changes = store_changes_by_tests(git_run, self.output_dir,
                                                               summary.stores_written)
            restore_worktree(git_run)

    def run_isolated(self, runner: AcceptanceRunner, specs: list[str], server, git_run, workers) -> RunSummary:
        """One spec file at a time; the store is reset whenever a file mutated it.

        Derived scripts change the seeded state on purpose (REQ-1-3 changes
        alice-dev's password, REQ-1-2-2 renames `Q3 Sales`): in one shared run
        every later sign-in or entry check then fails and the harness reads a
        false regression (v9.2.4: 1307196473c1 rolled REQ-2-2-3/REQ-2-2-4 back,
        1d804e9973c6 lost 5 entry checks at checkpoint 8). Workers stay at one.
        """
        merged = RunSummary()
        url = f"http://127.0.0.1:{self.smoke_port}"
        for index, spec in enumerate(specs):
            if self.time_up():
                merged.error = merged.error or "acceptance time budget exhausted"
                break
            part = runner.run([spec], url, workers=workers,
                              wall_timeout=max(60, min(600, int(self.remaining()))))
            if part.error and not part.results:
                merged.error, merged.killed = part.error, part.killed
                break
            merged.passed += part.passed
            merged.total += part.total
            merged.results += part.results
            merged.load_errors += part.load_errors
            if index < len(specs) - 1:
                status = git_run(["status", "--porcelain", "--", "frontend", "backend"])
                dirty = bool((getattr(status, "stdout", "") or "").strip())
                if dirty:
                    merged.stores_written = sorted(set(merged.stores_written) | {spec})
                    restore_worktree(git_run)
                    server.stop()
                    err = server.start()
                    if err is not None:
                        merged.error = err
                        break
        return merged

    def record_tests(self, node_id: str, specs: list[str], summary: RunSummary) -> None:
        source_hash = self.app_source_digest() if any(not row.ok for row in summary.results) else None
        for row in summary.results:
            if getattr(self, "derived_as_specs", False) and not self.trusted_derived_case(node_id, row.title):
                self.test_state[node_id] = "disputed"
            if not row.ok:
                self.record_quality_observation(
                    node_id, row.title, row.message or row.status,
                    source="derived" if getattr(self, "derived_as_specs", False) else "official",
                    reliable=(not getattr(self, "derived_as_specs", False)
                              or self.trusted_derived_case(node_id, row.title)), source_hash=source_hash)
        try:
            for r in summary.results:
                if getattr(self, "derived_as_specs", False) and not self.trusted_derived_case(node_id, r.title):
                    continue  # an unreviewed pass/failure is not a product verdict
                test_id = re.sub(r"[^A-Za-z0-9._-]+", "-", r.title)[:120]
                self.runtime.traceability.upsert_test(test_id=test_id, req_id=node_id, type="e2e",
                                                      file_path=r.file or None, passed=r.ok, emit_event=False)
        except Exception as exc:  # noqa: BLE001
            log(f"[trace] test rows not recorded: {exc}")

    def can_rewrite_from_scratch(self) -> bool:
        """A failing node does not justify replacing previously verified behavior."""
        return not (any(v is True for v in getattr(self, "test_verdict", {}).values())
                    or any(r.passed > 0 for r in getattr(self, "probe_summaries", {}).values()))

    def node_repair_turn(self, node_id: str, failures: str, timeout: float, label: str,
                         build_prompt) -> bool:
        """Apply a repair before charging another acceptance round.

        A guard refusal is missing context, not an ineffective code change.
        Requote once, then use tools if necessary, sharing one time allowance.
        Rebuild from disk after partial writes so the retry never sees stale
        sources. False means no repair was applied and the allowance is exhausted.
        """
        deadline = time.monotonic() + timeout
        prompt = build_prompt()
        compact = self.codegen_repair_prompt(node_id, prompt, failures=failures) if self.codegen_mode() else None
        applied = False
        round_spent = 0
        proxy = getattr(self, "llm_proxy", None)
        if compact is not None:
            for attempt in range(2):
                left = deadline - time.monotonic()
                default_cap = 16 if applied and getattr(self, "last_codegen_refused", set()) else 12
                round_cap = max(1, int(os.environ.get("OCTOS_ARC_REPAIR_ROUND_REQUESTS", str(default_cap))))
                allowance = round_cap - round_spent
                if left <= 0 or self.wound_down() or allowance <= 0:
                    return applied
                self.last_codegen_refused = set()
                self.last_codegen_written = []
                ok, reason = self.codegen_turn(compact, left, label if attempt == 0 else f"{label} (application retry)",
                                          spec_chars=getattr(self, "current_spec_chars", 0),
                                          force_files="Failed at: build/start" in failures,
                                          request_budget=allowance)
                round_spent += getattr(proxy, "turn_upstream_requests", 0)
                applied = applied or bool(self.last_codegen_written)
                refused = self.last_codegen_refused
                if self.last_codegen_written and not refused:
                    return True
                if attempt or getattr(self, "last_codegen_degenerated", False):
                    break
                if not refused:
                    outcome = getattr(self, "last_codegen_outcome", "")
                    if not applied and outcome in {"no_blocks", "incomplete_blocks", "format_error"}:
                        correction = ("\nPrevious repair was not applied: " + reason[:240] +
                                      "\nReturn complete FILE blocks with exact terminators, one block per path.\n")
                        if (deadline - time.monotonic() >= 30 and
                                len(compact + correction) + len(FORMAT_INSTRUCTIONS) + 1 <= self.codegen_context_chars()):
                            compact += correction
                            continue
                    break
                prompt = build_prompt()
                if getattr(self, "last_codegen_outcome", "") == "anchor_failed":
                    correction = "\nPatch application error (no edits applied):\n" + reason[:1200]
                    failures += correction
                    prompt += correction
                compact = self.codegen_repair_prompt(node_id, prompt, failures=failures)
                if compact is None or not refused <= quoted_paths(compact):
                    break
                log(f"[flow] {label}: retrying codegen with {', '.join(sorted(refused))} quoted whole")
        left = deadline - time.monotonic()
        if left < 30 or self.wound_down() or getattr(getattr(self, "llm_proxy", None), "hard_budget_exhausted", False) is True:
            return applied
        default_cap = 16 if applied and getattr(self, "last_codegen_refused", set()) else 12
        round_cap = max(1, int(os.environ.get("OCTOS_ARC_REPAIR_ROUND_REQUESTS", str(default_cap))))
        allowance = round_cap - round_spent
        if allowance <= 0:
            self.metric("repair_round_budget", node_id=node_id, label=label,
                        spent=round_spent, cap=round_cap, decision="no_fallback")
            return applied
        if self.codegen_mode():
            self.codegen_blocked = True
            log(f"[flow] {label}: codegen repair unavailable or not fully applied; using tools before retesting")
        outcome = getattr(self, "last_codegen_outcome", "unapplied")
        if compact is not None:
            self.pending_corrections.append(
                f"Previous codegen repair outcome: {outcome}. The reported failure is still unresolved. "
                "Inspect current files; apply a concrete fix before rerunning acceptance. "
                "An unapplied or unchanged reply is not evidence that the proposed fix failed.")
        self.last_turn_changed = None
        self.repair_tool_turn(self.compact_tool_repair_prompt(build_prompt(), failures), left, label,
                              request_budget=allowance)
        changed = getattr(self, "last_turn_changed", None)
        if changed is False and not applied:
            log(f"[flow] {label}: no source changes after repair fallback; skipping duplicate acceptance")
            return False
        return True

    def audit_failed_derived_specs(self, node_id: str, specs: list[str], summary: RunSummary) -> RunSummary | None:
        """Correct provably wrong generated assertions before repairing the app.

        This branch never touches platform/public specs. Keep the old source for
        inspection, load-check the replacement, then measure the unchanged app
        again. The app repair loop consumes that new measurement if it still
        fails; a passing replacement is not inferred from the spec edit alone.
        """
        if (not getattr(self, "derived_as_specs", False)
                or self.tests_dir != getattr(self, "derived_tests_dir", None)
                or os.environ.get("OCTOS_ARC_DERIVED_SPEC_AUDIT", "1") == "0"
                or os.environ.get("OCTOS_ARC_DERIVED_SPEC_REPAIR", "1") == "0"
                or not self.suite_is_measured(summary, specs)
                or summary.all_passed):
            return None
        node = getattr(self, "requirement_nodes", {}).get(node_id)
        runner = getattr(self, "runner", None)
        if not node or runner is None or not hasattr(runner, "list_specs"):
            return None
        fixtures = suite_fixtures(getattr(self, "derived_nodes", [node]))
        changes: list[tuple[Path, str, str, tuple[str, ...]]] = []
        changed_titles: set[str] = set()
        for rel in specs:
            path = self.tests_dir / rel
            if not path.is_file():
                continue
            suffix = rel.replace("\\", "/")
            failures = [row.title for row in summary.results if not row.ok and (
                str(row.file or "").replace("\\", "/") == suffix or
                str(row.file or "").replace("\\", "/").endswith("/" + suffix))]
            if not failures:
                continue
            original = path.read_text(encoding="utf-8")
            repair = repair_failed_generated_specs(original, failures, node, fixtures)
            if repair.changed_titles:
                changes.append((path, original, repair.source, repair.reasons))
                changed_titles.update(repair.changed_titles)
        if not changes:
            self.metric("derived_spec_audit", node_id=node_id, outcome="no_provable_spec_error",
                        failed_tests=sum(not row.ok for row in summary.results))
            return None
        archive = self.output_dir / ".arc" / "spec-audit" / node_id
        archive.mkdir(parents=True, exist_ok=True)
        for path, original, corrected, reasons in changes:
            digest = hashlib.sha256(original.encode("utf-8")).hexdigest()[:12]
            (archive / f"{path.stem}-{digest}.spec.ts").write_text(original, encoding="utf-8")
            path.write_text(corrected, encoding="utf-8")
            log(f"[derived] {node_id}: corrected generated spec {path.name}: {'; '.join(reasons)}")
        loads, detail = runner.list_specs(specs)
        if not loads:
            for path, original, _, _ in changes:
                path.write_text(original, encoding="utf-8")
            self.metric("derived_spec_audit", node_id=node_id, outcome="rejected_load_error",
                        detail=str(detail)[-300:])
            log(f"[derived] {node_id}: corrected spec did not load; original restored: {str(detail)[-200:]}")
            return None
        # Model turns restore protected paths from this snapshot. Refresh it
        # only after the harness itself has accepted the generated-spec edit.
        self.snapshot_protected()
        for title in changed_titles:
            self.clear_derived_spec_dispute(node_id, title)
        self.metric("derived_spec_audit", node_id=node_id, outcome="corrected",
                    files=[str(path.name) for path, _, _, _ in changes],
                    reasons=[reason for _, _, _, reasons in changes for reason in reasons])
        observed = self.run_specs(specs)
        self.write_derived_coverage(observed)
        log(f"[derived] {node_id}: unchanged app after spec correction: "
            f"{observed.passed}/{observed.total} passed"
            + (f"; {observed.error}" if observed.error else ""))
        return observed

    def generated_test_policy(self):
        from test_policy import TestPolicy, digest
        directory = getattr(self, "derived_tests_dir", None)
        if (not getattr(self, "derived_as_specs", False) or directory is None
                or self.tests_dir != directory):
            return None
        helpers = {str(p.relative_to(directory)): p.read_text()
                   for p in directory.rglob("*.ts") if not p.name.endswith(".spec.ts")}
        policy = TestPolicy(directory, getattr(self, "requirement_tree", None)
                            or getattr(self, "derived_nodes", []), digest(helpers))
        self.derived_spec_disputes = {(Path(row["file"]).stem, row["title"]): row["evidence"]
                                    for row in policy.valid_records() if row["state"] in {"invalid", "unresolved"}}
        return policy

    def disputed_generated_failures(self, summary: RunSummary) -> list[tuple[str, str]]:
        """Failed generated tests whose oracle is not safe for application repair."""
        disputes = getattr(self, "derived_spec_disputes", {})
        found = []
        for row in summary.results:
            filename = Path(row.file or "").name
            node_id = filename[:-len(".spec.ts")] if filename.endswith(".spec.ts") else ""
            if not row.ok and ((node_id, row.title) in disputes
                               or not self.trusted_derived_case(node_id, row.title)
                               or classify_observation(row.message or row.status,
                                                       source="derived", reliable=True)[0] == "T"):
                found.append((node_id, row.title))
        return found

    def trusted_derived_case(self, node_id: str, title: str) -> bool:
        reviews = getattr(self, "derived_case_reviews", None)
        if reviews is None:  # older or official-spec flows do not have this ledger
            return True
        row = reviews.get((node_id, title))
        if not row or row.get("status") != "approved_behavior":
            return False
        path = (getattr(self, "derived_tests_dir", None) or self.tests_dir) / f"{node_id}.spec.ts"
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            return False
        from test_policy import test_block
        block = test_block(source, title)
        try:
            target = next((item for item in self.planned_derived_scenarios()
                           if item.get("node_id") == node_id and item.get("id") == row.get("scenario_id")), None)
            requirement = requirement_text(target, ancestor_context(getattr(self, "requirement_tree", None)).get(node_id, ""))
            helper = path.parent / "helpers.ts"
            helper_hash = case_sha(helper.read_text(encoding="utf-8")) if helper.is_file() else ""
            fixture_hash = case_sha(str(suite_fixtures(getattr(self, "derived_nodes", []))))
        except (OSError, ValueError, TypeError):
            return False
        return bool(block and row.get("file_hash") == case_sha(source)
                    and row.get("case_hash") == case_sha(block)
                    and target and row.get("requirements_hash") == case_sha(requirement)
                    and row.get("helper_hash") == helper_hash
                    and row.get("fixture_hash") == fixture_hash)

    def uncontested_derived_results(self, summary: RunSummary) -> RunSummary:
        """Exclude disputed oracles from repair evidence while retaining the full measurement."""
        if not getattr(self, "derived_as_specs", False):
            return summary
        disputes = getattr(self, "derived_spec_disputes", {})
        reviews = getattr(self, "derived_case_reviews", None)
        if not disputes and reviews is None:
            return summary
        rows = [row for row in summary.results if (
            Path(row.file or "").name.removesuffix(".spec.ts"), row.title) not in disputes
            and self.trusted_derived_case(Path(row.file or "").name.removesuffix(".spec.ts"), row.title)
            and (row.ok or classify_observation(row.message or row.status, source="derived", reliable=True)[0] != "T")]
        return dc_replace(summary, results=rows, total=len(rows), passed=sum(row.ok for row in rows))

    def flag_derived_spec_dispute(self, node_id: str, title: str, reason: str) -> None:
        disputes = getattr(self, "derived_spec_disputes", {})
        disputes[(node_id, title)] = reason[:600]
        self.derived_spec_disputes = disputes
        self.metric("derived_spec_dispute", node_id=node_id, title=title, reason=reason[:300])
        self.write_derived_coverage()

    def clear_derived_spec_dispute(self, node_id: str, title: str) -> None:
        getattr(self, "derived_spec_disputes", {}).pop((node_id, title), None)

    def oracle_review_turn(self, prompt: str, label: str):
        stage = getattr(self, "_repair_stage", None)
        allowance = max(0, (stage[0] if stage else self.budget) * .10)
        spent = getattr(self, "_oracle_review_seconds", 0)
        available = min(180, allowance - spent, self.remaining() - self.final_phase_reserve())
        if available < 30:
            return False, "generated-test oracle review allowance exhausted"
        started = time.monotonic()
        try:
            return self.text_turn(prompt, available, label, system=REVIEW_SYSTEM, spec_chars=len(prompt))
        finally:
            self._oracle_review_seconds = spent + time.monotonic() - started

    def review_failed_derived_spec_with_model(self, node_id: str, specs: list[str],
                                              summary: RunSummary,
                                              failure_title: str | None = None) -> RunSummary | None:
        """Independently review one failing generated script before app repair.

        The reviewer may reorder or add prerequisites, but every original
        assertion must survive. A changed oracle needs requirement proof that
        this generic review cannot establish, so it is not applied here.
        """
        if (getattr(self, "derived_as_specs", False) is not True
                or getattr(self, "driver", None) is None
                or os.environ.get("OCTOS_ARC_DERIVED_FAILURE_REVIEW", "1") == "0"
                or not self.suite_is_measured(summary, specs) or summary.all_passed
                or self.wound_down() or self.review_budget_spent()
                or self.remaining() < self.final_phase_reserve() + 240):
            return None
        node = getattr(self, "requirement_nodes", {}).get(node_id)
        runner = getattr(self, "runner", None)
        if not node or runner is None or not hasattr(runner, "list_specs"):
            return None
        candidates = [row for row in summary.results if not row.ok and row.status != "quarantined"
                      and (failure_title is None or row.title == failure_title)]
        if not candidates:
            return None
        row = candidates[0]
        policy = self.generated_test_policy()
        from test_policy import digest, test_block, grounded_verdict
        version_key = digest({"context": policy.context if policy else "",
                              "files": {rel: (self.tests_dir / rel).read_text() for rel in specs}})
        key = (node_id, row.title, failure_signature(summary), version_key)
        reviewed = getattr(self, "derived_failure_reviews", set())
        if key in reviewed:
            return None
        reviewed.add(key)
        self.derived_failure_reviews = reviewed
        fixtures = suite_fixtures(getattr(self, "derived_nodes", [node]))
        targets = review_targets(getattr(self, "derived_nodes", [node]), fixtures,
                                 ancestor_context(getattr(self, "requirement_tree", None)),
                                 folder_text(getattr(self, "requirement_tree", None)), include_all=True,
                                 dependency_tree=getattr(self, "requirement_tree", None))
        target = next((item for item in targets if item["node_id"] == node_id
                       and (row.title in {f"{item['title']} [model]", f"{item['title']} [script]"}
                            or row.title.startswith(item['title'] + " [reach]")
                            or row.title.startswith(item['title'] + " [entry]")
                            or row.title.startswith(item['title'] + " [case "))), None)
        rel = next((path for path in specs if str(row.file or "").replace("\\", "/").endswith(path)), None)
        if rel is None:
            return None
        if target is None:
            # Some entry checks have no one-to-one scenario title. The complete
            # test and original node still permit a grounded oracle decision.
            from scenario_review import allowed_literals
            target = {"id": "audit", "node_id": node_id, "title": row.title, "name": node.get("name", node_id),
                      "description": str(node.get("description") or ""), "steps": [],
                      "allowed": allowed_literals(node, fixtures), "controls": [], "seeds": []}
        if " [case " in row.title:
            target = dict(target, title=row.title.removesuffix(" [model]"))
        path = self.tests_dir / rel
        original = path.read_text(encoding="utf-8")
        requirement = (json.dumps(node, ensure_ascii=False, sort_keys=True) + "\n" + str(node.get("description") or "")
                       + "\n" + ancestor_context(getattr(self, "requirement_tree", None)).get(node_id, ""))
        block = test_block(original, row.title)
        if block is None:
            return None
        failure = failure_summaries(RunSummary(results=[row], total=1, passed=0),
                                    max_observation=3000, max_snapshots=7000)
        # A bounded crawl exhausting its own depth/time is not evidence that
        # the app lacks the feature. Do not buy an application edit to satisfy
        # a helper limit (for example, by adding an inert shallow shortcut).
        if (policy and (' [reach] ' in row.title or ' [entry] ' in row.title)
                and re.search(r'not reachable (?:within \d+ navigation clicks|after \d+s)',
                              row.message, re.I)):
            reason = ("Generated navigation helper exhausted its search; the target may exist on a "
                      "deeper or different valid path. Verify the requirement precondition and an explicit "
                      "navigation path before changing application UI. " + failure[:1800])
            policy.decide(rel, row.title, original, "unresolved", reason,
                          failure_hash=digest(sorted(map(str, failure_signature(summary)))))
            self.snapshot_protected()
            self.flag_derived_spec_dispute(node_id, row.title, reason)
            return None
        prompt = ("Review one failed generated TEST against the authoritative requirement; do not edit the app. "
                  "Return exactly one JSON object with this schema: "
                  '{"verdict":"app_error|spec_error|oracle_dispute|uncertain",'
                  '"evidence":"concrete observed facts and cause",'
                  '"reason_code":"requirement_conflict|unsupported_constraint|fixture_error|wrong_action|null",'
                  '"requirement_quote":"verbatim requirement passage or empty for app_error",'
                  '"test_quote":"verbatim offending await/expect statement or empty for app_error",'
                  '"scenarios":[]}. '
                  "For spec_error/oracle_dispute all three grounding fields are mandatory; copy exact source text. "
                  "For a missing or misordered action, scenarios may contain a corrected proposal, preserving "
                  "every valid original assertion. Never change an expected result to match the current app. "
                  "A missing UI, timeout, HTTP 401 or unimplemented behavior alone is not a test error. "
                  "Distinguish planned input from observed DOM value and actual network request. "
                  "Compare the target failure with any related passing behavior; label unmeasured claims.\n\n"
                  + build_review_prompt([target], fixtures)
                  + "\n\nTARGET FAILURE EVIDENCE:\n" + failure
                  + "\nCOMPLETE OFFENDING TEST:\n" + block
                  + "\nAUTHORITATIVE REQUIREMENT:\n" + requirement)
        helper = self.tests_dir / "helpers.ts"
        if helper.is_file():
            prompt += "\nCOMPLETE TEST HELPER:\n" + helper.read_text(encoding="utf-8")
        if len(prompt) > self.codegen_context_chars():
            self.metric("derived_spec_failure_review", node_id=node_id, title=row.title, verdict="evidence_exceeds_context")
            return None  # Never adjudicate with missing requirement/helper evidence.
        # Harness files committed since the preceding model turn must be protected now.
        self.snapshot_protected()
        ok, reply = self.oracle_review_turn(prompt, "derived failed-spec review")
        if not ok:
            return None
        review = parse_failure_review(reply)
        confirmed_test_error = False
        if review is None:
            self.metric("derived_spec_failure_review", node_id=node_id, title=row.title,
                        verdict="invalid_response")
            self.pending_corrections.append(
                f"Generated-test reviewer returned no valid verdict for {row.title}; the observed failure "
                "remains active. Do not infer a bad test from reviewer formatting alone.")
            return None
        if review["verdict"] in {"spec_error", "oracle_dispute"} and not grounded_verdict(review, requirement, block):
            # One format-only retry, with the same original evidence. A new
            # opinion without exact source quotes is not a safe skip or edit.
            if self.remaining() >= self.final_phase_reserve() + 240 and not self.review_budget_spent():
                correction = ("\nFORMAT CORRECTION ONLY: keep the original verdict and evidence. Supply valid "
                              "reason_code, requirement_quote, and test_quote copied verbatim from the above "
                              "sources. If no such pair exists, return uncertain.\nPREVIOUS JSON:\n"
                              + json.dumps(review, ensure_ascii=False)[:3000])
                ok_retry, reply_retry = self.oracle_review_turn(prompt + correction, "generated-test review schema retry")
                retried = parse_failure_review(reply_retry) if ok_retry else None
                if retried and retried.get("verdict") == review["verdict"]:
                    review = retried
            if not grounded_verdict(review, requirement, block):
                reason = "Generated-test error claim lacked exact requirement/test grounding: " + review["evidence"][:1000]
                self.pending_corrections.append(reason + "; the observed application failure remains active.")
                return None
        if policy and block and grounded_verdict(review, requirement, block):
            # A fresh, read-only request receives the original evidence, never the first verdict.
            if self.remaining() < self.final_phase_reserve() + 240 or self.review_budget_spent():
                return None
            ok2, reply2 = self.oracle_review_turn(prompt, "independent generated-test oracle review")
            second = parse_failure_review(reply2) if ok2 else None
            agreed = (grounded_verdict(second, requirement, block)
                      and second["verdict"] == review["verdict"]
                      and second["reason_code"] == review["reason_code"]
                      and second["requirement_quote"] == review["requirement_quote"]
                      and second["test_quote"] == review["test_quote"])
            if not agreed or review["verdict"] == "oracle_dispute":
                policy.decide(rel, row.title, original, "invalid" if agreed else "unresolved",
                              review["evidence"], [review, second],
                              digest(sorted(map(str, failure_signature(summary)))))
                self.snapshot_protected()
                self.metric("derived_test_decision", node_id=node_id, title=row.title,
                            state="invalid" if agreed else "unresolved", independent_reviews=2)
                self.flag_derived_spec_dispute(node_id, row.title,
                                               review["evidence"] if agreed else
                                               "Independent generated-test reviews disagreed")
                if agreed:
                    observed = self.run_specs(specs)
                    self.write_derived_coverage(observed)
                    return observed
                return None
            # An agreed wrong-action test still has a valid oracle. Apply a
            # verified action-order correction below before considering any
            # quarantine; its existing assertions must remain byte-identical.
            confirmed_test_error = True
        label = review["verdict"]
        evidence = review["evidence"]
        self.metric("derived_spec_failure_review", node_id=node_id, title=row.title,
                    verdict=label, evidence=str(evidence)[:300])
        if label != "spec_error":
            if label == "app_error" and evidence:
                self.clear_derived_spec_dispute(node_id, row.title)
                self.pending_corrections.append(f"Independent generated-spec review for {node_id}: {evidence[:500]}")
            elif label == "oracle_dispute" and evidence:
                self.pending_corrections.append("Unproven generated-test concern: " + str(evidence)[:500])
            elif label == "uncertain" and evidence:
                if policy:
                    policy.decide(rel, row.title, original, "unresolved", evidence, [review],
                                  digest(sorted(map(str, failure_signature(summary)))))
                    self.snapshot_protected()
                    self.flag_derived_spec_dispute(node_id, row.title, evidence)
                self.pending_corrections.append(
                    f"Generated-spec review for {node_id} was inconclusive: {str(evidence)[:500]}. "
                    "Check the requirement and observed behavior before changing the app.")
            return None
        if (os.environ.get("OCTOS_ARC_DERIVED_SPEC_REPAIR", "1") == "0"
                or not row.title.endswith((" [model]", " [script]"))):
            if confirmed_test_error and policy:
                policy.decide(rel, row.title, original, "invalid", review["evidence"], [review, second],
                              digest(sorted(map(str, failure_signature(summary)))))
                self.snapshot_protected()
                self.flag_derived_spec_dispute(node_id, row.title, review["evidence"])
                observed = self.run_specs(specs)
                self.write_derived_coverage(observed)
                return observed
            return None  # Mechanical tests are audited, never converted to weaker model tests.
        scripts, dropped = compile_review_reply(json.dumps(review, ensure_ascii=False), [target], fixtures)
        replacement = next((test for test in scripts.get(node_id, [])
                            if f"{target['title']} [model]" in test.split("\n", 1)[0]), None)
        corrected = replace_failed_test_preserving_oracle(original, row.title, replacement) if replacement else None
        if not corrected:
            self.metric("derived_spec_failure_review", node_id=node_id, title=row.title,
                        verdict="rejected_unsafe_patch", reasons=dropped[:2])
            if confirmed_test_error and policy:
                policy.decide(rel, row.title, original, "invalid", review["evidence"], [review, second],
                              digest(sorted(map(str, failure_signature(summary)))))
                self.snapshot_protected()
                self.flag_derived_spec_dispute(node_id, row.title, review["evidence"])
                observed = self.run_specs(specs)
                self.write_derived_coverage(observed)
                return observed
            # An unsupported opinion must never suppress an application failure.
            return None
        archive = self.output_dir / ".arc" / "spec-audit" / node_id
        archive.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(original.encode("utf-8")).hexdigest()[:12]
        (archive / f"{path.stem}-{digest}.spec.ts").write_text(original, encoding="utf-8")
        path.write_text(corrected, encoding="utf-8")
        loads, detail = runner.list_specs(specs)
        if not loads:
            path.write_text(original, encoding="utf-8")
            self.metric("derived_spec_failure_review", node_id=node_id, title=row.title,
                        verdict="rejected_load_error", detail=str(detail)[-300:])
            return None
        self.snapshot_protected()
        self.clear_derived_spec_dispute(node_id, row.title)
        observed = self.run_specs(specs)
        self.write_derived_coverage(observed)
        self.metric("derived_spec_failure_review", node_id=node_id, title=row.title,
                    verdict="corrected_and_remeasured", passed=observed.passed, total=observed.total)
        return observed

    def audit_related_derived_specs(self, specs: list[str], summary: RunSummary,
                                    owner_specs: dict[str, list[str]] | None = None) -> RunSummary:
        """Audit newly failing related specs before blaming a shared app edit.

        A correction is first checked against the unchanged app by the node
        auditor. Then the combined suite is measured again, because a pass in
        isolation cannot establish that two features coexist correctly.
        """
        if (getattr(self, "derived_as_specs", False) is not True or summary.all_passed
                or not self.suite_is_measured(summary, specs)):
            return summary
        owners = self.spec_map if owner_specs is None else owner_specs
        single_owner = len(owners) == 1 and set(next(iter(owners.values()))) == set(specs)
        corrected = False
        single_result = None
        model_limit = max(0, int(os.environ.get("OCTOS_ARC_DERIVED_FAILURE_REVIEW_PER_SUITE", "3")))
        for node_id, paths in owners.items():
            if not node_id or not paths or not set(paths) <= set(specs):
                continue
            rows = [row for row in summary.results if any(
                str(row.file or "").replace("\\", "/") == path or
                str(row.file or "").replace("\\", "/").endswith("/" + path) for path in paths)]
            local = RunSummary(results=rows, total=len(rows), passed=sum(row.ok for row in rows))
            if local.all_passed or not self.suite_is_measured(local, paths):
                continue
            if not any(not row.ok and self.trusted_derived_case(node_id, row.title)
                       and classify_observation(row.message or row.status,
                                                source="derived", reliable=True)[0] != "T" for row in rows):
                continue
            result = self.audit_failed_derived_specs(node_id, paths, local)
            corrected = result is not None or corrected
            if result is not None and single_owner:
                single_result = result
        if corrected:
            summary = single_result if single_result is not None else self.run_specs(specs, grader_like=True)
            self.metric("derived_spec_audit", outcome="related_suite_remeasured",
                        passed=summary.passed, total=summary.total, specs=len(specs))
        model_reviews = 0
        while (model_reviews < model_limit and not summary.all_passed
               and self.suite_is_measured(summary, specs)):
            model_corrected = False
            for node_id, paths in owners.items():
                if not node_id or not paths or not set(paths) <= set(specs):
                    continue
                rows = [row for row in summary.results if any(
                    str(row.file or "").replace("\\", "/") == path or
                    str(row.file or "").replace("\\", "/").endswith("/" + path) for path in paths)]
                local = RunSummary(results=rows, total=len(rows), passed=sum(row.ok for row in rows))
                if local.all_passed or not self.suite_is_measured(local, paths):
                    continue
                for row in rows:
                    if (row.ok or row.status == "quarantined" or not self.trusted_derived_case(node_id, row.title)
                            or classify_observation(row.message or row.status,
                                                    source="derived", reliable=True)[0] == "T"):
                        continue
                    if model_reviews >= model_limit:
                        break
                    model_reviews += 1
                    result = self.review_failed_derived_spec_with_model(
                        node_id, paths, local, failure_title=row.title)
                    if result is not None:
                        summary = result if single_owner else self.run_specs(specs, grader_like=True)
                        model_corrected = True
                        break
                if model_corrected:
                    break
            if not model_corrected:
                break
        return summary

    def acceptance_loop(self, node_id: str, specs: list[str], deadline: float,
                        rebuild_prompt=None, initial_summary: RunSummary | None = None,
                        source_versions: dict | None = None) -> bool | None:
        """Returns True/False for a real verdict, None when no local run happened.
        `rebuild_prompt(failures)` (optional) yields a full re-implementation
        prompt; it is used only before any behavior has passed verification.
        A failing extension is repaired without replacing working features."""
        if self.runner is None or not specs:
            return None
        best_passed, best_sha, regressions, stalls = -1, self.head(), 0, 0
        rewrite_used = False
        previous_failures = None
        repair_applied = False
        prior_regressed = False
        checked_failed_versions = set()
        initial_versions = source_versions if source_versions is not None else self.repair_source_index().versions
        self.codegen_blocked = False  # same failure twice in codegen mode -> tool mode for this node
        for attempt in range(self.repair_rounds + 1):
            levels: list[str] = []
            summary = initial_summary if attempt == 0 and initial_summary is not None else self.run_specs(specs)
            if getattr(self, "derived_as_specs", False):
                summary = self.audit_related_derived_specs(
                    specs, summary, owner_specs={node_id: specs})
                disputed = self.disputed_generated_failures(summary)
                if disputed:
                    raw = summary
                    self.write_derived_coverage(raw)
                    summary = self.uncontested_derived_results(raw)
                    self.metric("derived_spec_dispute", scope="node", node_id=node_id,
                                tests=[title for _, title in disputed], active=summary.total)
                    if not summary.total or summary.all_passed:
                        self.record_tests(node_id, specs, raw)
                        self.self_audit_node(node_id, "generated tests were disputed, unreviewed or low-signal")
                        return None  # All active tests pass; invalid tests leave a coverage gap.
            if summary.error and summary.error.startswith("generated test load blocked:"):
                self.metric("acceptance", scope="node", node_id=node_id, verdict="blocked_test_file")
                return None
            if summary.error and summary.killed:
                log(f"[acceptance] {node_id}: test runner killed ({summary.error[:120]}); no verdict from this round")
                return None
            infrastructure_error = summary.error or ("\n".join(summary.load_errors) if summary.load_errors else "")
            measured = not infrastructure_error and not summary.killed and summary.total > 0
            self._unresolved_startup_error = infrastructure_error
            self.verify_repair_memory(summary, measured)
            if infrastructure_error:
                log(f"[acceptance] {node_id} infrastructure error: {startup_error_digest(infrastructure_error, 1200)}")
                self.record_quality_observation(node_id, "build/start/load", infrastructure_error,
                                                source="runtime", reliable=True)
                failures = f"- Feature: app startup\n  Failed at: build/start\n  Observation: {startup_error_digest(infrastructure_error, 2200)}\n  Steps: npm run build -> npm start"
                passed = 0
            else:
                passed = summary.passed
                failures = failure_summaries(summary) + failure_source_context(summary, self.tests_dir)
                if measured:
                    self.record_tests(node_id, specs, summary)
                    tracker = getattr(self, "shared_failures", None)
                    if tracker is None:
                        tracker = self.shared_failures = SharedFailureTracker()
                    shared = tracker.note(node_id, summary)
                    if shared:
                        failures += shared
                        log(f"[acceptance] {node_id}: failure shared with earlier requirements; "
                            f"repair targets the common cause ({shared.splitlines()[2][:200]})")
            log(f"[acceptance] {node_id} round {attempt}: {passed}/{summary.total}")
            self.last_node_own_pass = bool(measured and passed == summary.total
                                           and not self.derived_review_needed(node_id))
            self.metric("acceptance", scope="node", node_id=node_id, round=attempt,
                        passed=passed, total=summary.total, after_applied_repair=repair_applied,
                        verdict="measured" if measured else "unknown", error=infrastructure_error or None)
            if attempt == 0 and node_id in getattr(self, "batched_groups", {}):
                self.batch_first_pass[node_id] = bool(measured and passed == summary.total)
                group = self.batched_groups[node_id]
                if all(member in self.batch_first_pass for member in group):
                    first_pass = sum(self.batch_first_pass[member] for member in group)
                    log(f"[flow] sibling batch {list(group)}: first-pass {first_pass}/{len(group)} leaves")
            was_codegen = self.codegen_mode()
            normalized = failure_signature(summary) if summary.results else failures
            if repair_applied and normalized and normalized == previous_failures:
                # Cloud 91aaecaf31af: three codegen rounds, identical observation.
                self.codegen_blocked = True
                self.pending_corrections.append(
                    'Repeated attempts produced the same observed failure. Recheck the assumptions behind the repair: inspect expected and received values, preceding actions, locator scope, and actual application state. Change the cause supported by this evidence. Do not manufacture the expected output or bypass the underlying operation; preserve behavior for other inputs.')
                log(f"[flow] {node_id}: identical failure twice; switching repairs to tool mode")
            previous_failures = normalized
            if attempt >= int(os.environ.get("OCTOS_ARC_CODEGEN_REPAIRS", "2")) and passed < summary.total \
                    and self.codegen_mode():
                # Cloud 91aaecaf31af / 5747e6bcf530: repeated codegen repairs re-emit the same files.
                # One cheap codegen repair (failure digest + quoted sources) is allowed; then tools.
                self.codegen_blocked = True
                log(f"[flow] {node_id}: codegen attempt {attempt} still failing; repairs use tool mode")
            for line in (failures or "").splitlines():
                if line.strip().startswith(("Failed at:", "Observation:")):
                    log(f"[acceptance]   {' '.join(line.strip().split())[:360]}")
            # A new feature can fail while its shared-file edit also breaks an
            # already proven feature. Probe each new source version, rather
            # than waiting for the new feature to pass or for a checkpoint.
            if measured:
                current_versions = self.repair_source_index().versions
                changed = {p for p in initial_versions.keys() | current_versions.keys()
                           if initial_versions.get(p) != current_versions.get(p)}
                regression_specs = self.affected_regression_specs(changed, specs) if repair_applied or source_versions is not None else []
                if passed < summary.total:
                    version_key = tuple(sorted((p, current_versions.get(p)) for p in changed))
                    if version_key in checked_failed_versions:
                        regression_specs = []
                    else:
                        checked_failed_versions.add(version_key)
                affected_count = len(regression_specs)
                if passed < summary.total and regression_specs:
                    # The current spec was just measured. Probe a rotating,
                    # bounded set of proven specs so a failing global edit does
                    # not consume the entire node budget; checkpoints cover the
                    # remaining proven behavior together.
                    prior_specs = sorted(set(regression_specs) - set(specs))
                    cap = max(1, int(os.environ.get('OCTOS_ARC_FAILED_EXTENSION_REGRESSION_SPECS', '16')))
                    if len(prior_specs) > cap:
                        cursor = getattr(self, '_failed_regression_cursor', 0) % len(prior_specs)
                        regression_specs = (prior_specs[cursor:] + prior_specs[:cursor])[:cap]
                        self._failed_regression_cursor = cursor + cap
                    else:
                        regression_specs = prior_specs
                if regression_specs and not self.wound_down() and self.remaining() > self.final_measurement_reserve():
                    regression = self.run_specs(regression_specs, grader_like=True)
                    if getattr(self, "derived_as_specs", False) is True:
                        regression = self.audit_related_derived_specs(regression_specs, regression)
                        disputed = self.disputed_generated_failures(regression)
                        if disputed:
                            for prior, _ in disputed:
                                self.test_verdict[prior] = None
                            regression = self.uncontested_derived_results(regression)
                    self.metric("acceptance", scope="affected_regression", node_id=node_id,
                                passed=regression.passed, total=regression.total,
                                checked_specs=len(regression_specs), affected_specs=affected_count,
                                changed_files=sorted(changed))
                    if not regression.all_passed or not self.suite_is_measured(regression, regression_specs):
                        prior_regressed = False
                        for prior, paths in self.spec_map.items():
                            if not prior or not paths or not set(paths) <= set(regression_specs):
                                continue
                            rows = [r for r in regression.results if any(
                                str(r.file or '').replace('\\', '/') == p or
                                str(r.file or '').replace('\\', '/').endswith('/' + p) for p in paths)]
                            local = RunSummary(results=rows, total=len(rows), passed=sum(r.ok for r in rows),
                                               error=regression.error, killed=regression.killed,
                                               load_errors=regression.load_errors)
                            if self.suite_is_measured(local, paths):
                                self.test_verdict[prior] = (None if local.all_passed
                                                             and self.derived_review_needed(prior)
                                                             else local.all_passed)
                                self.record_tests(prior, paths, local)
                                if not local.all_passed:
                                    if prior != node_id and self.test_verdict.get(prior) is False:
                                        prior_regressed = True
                                    self.mark('test_failed', prior, 'affected behavior failed after application changes')
                            else:
                                self.test_verdict[prior] = None
                        regression_evidence = balanced_failure_evidence(
                            failure_summaries(regression) or regression.error or "Incomplete regression verdict", 4000)
                        self.pending_corrections.append("Related regression checks after the targeted repair:\n" +
                                                        regression_evidence)
                        if passed == summary.total:
                            # Do not certify a repair that broke its surrounding behaviour.
                            return False
                        if prior_regressed:
                            failures += "\nPreviously passing behavior regressed after this edit:\n" + regression_evidence
                            log(f"[acceptance] {node_id}: shared-file edit regressed proven behavior; "
                                "including it in the local repair")
                if passed == summary.total:
                    if self.derived_review_needed(node_id):
                        log(f"[acceptance] {node_id}: generated reach/entry checks pass, "
                            "but no behavioural spec can verify the feature")
                        self.metric("derived_spec_coverage", node_id=node_id, outcome="unverified",
                                    passed=passed, total=summary.total)
                        self.self_audit_node(node_id, "derived oracle coverage or independent review incomplete")
                        return None
                    self.commit(f"{node_id} (accepted): {passed}/{summary.total} acceptance tests pass")
                    return True
            # A helper that chooses a role before a route/list finishes loading
            # can wait for the wrong element even though the requested name is
            # visible at failure. Confirm the same spec once before a costly
            # repair. Repeated identical evidence is deferred to the suite,
            # where related loading failures can be diagnosed together.
            failed_rows = [row for row in summary.results if not row.ok]
            if measured and failed_rows:
                source = "derived" if getattr(self, "derived_as_specs", False) else "official"
                requirement_node = getattr(self, "requirement_nodes", {}).get(node_id, {})
                core_text = (str(requirement_node.get("description") or "") + " "
                             + json.dumps(requirement_node.get("scenarios") or [], ensure_ascii=False))
                core = (not core_text and source == "official") or bool(re.search(
                    r"sign.?in|sign.?out|password|permission|access|persist|save|formula|delete", core_text, re.I))
                node = getattr(self, "requirement_nodes", {}).get(node_id, {})
                minor = str(node.get("priority") or "").lower() == "low" or bool(re.search(
                    r"\b(optional|secondary|edge case|noncritical|cosmetic|tooltip)\b", core_text, re.I))
                levels = [classify_observation(row.message or row.status, source=source,
                                               reliable=True, core=core, minor=minor)[0] for row in failed_rows]
                if all(level in {"F2", "T"} for level in levels):
                    self.test_state[node_id] = ("skipped_low_signal" if "T" in levels else "failed")
                    self.self_audit_node(node_id, "local or low-signal failure deferred after source review")
                    self.metric("acceptance_deferred", node_id=node_id, levels=levels,
                                decision="continue_generation")
                    return False if "F2" in levels else None
            if (attempt == 0 and measured and failed_rows and not prior_regressed and len(specs) <= 2
                    and all(locator_role_mismatch(row) for row in failed_rows)
                    and deadline - time.time() >= 90
                    and self.remaining() >= self.final_phase_reserve() + self.repair_minimum() + 90):
                confirmation = self.run_specs(specs)
                confirmed = self.suite_is_measured(confirmation, specs)
                self.metric('locator_race_recheck', node_id=node_id,
                            first_passed=summary.passed, recheck_passed=confirmation.passed,
                            confirmed=confirmed)
                if confirmed and confirmation.all_passed:
                    # One lucky pass is not enough to certify a flaky route.
                    if (deadline - time.time() >= 30 and
                            self.remaining() >= self.final_phase_reserve() + 30):
                        stable = self.run_specs(specs)
                        stable_measured = self.suite_is_measured(stable, specs)
                        self.metric('locator_race_recheck', node_id=node_id, repeat=True,
                                    recheck_passed=stable.passed, confirmed=stable_measured)
                        if stable_measured and stable.all_passed:
                            self.record_tests(node_id, specs, stable)
                            log(f"[acceptance] {node_id}: two independent rechecks passed after a "
                                "locator-role race; accepting with later suite coverage")
                            self.commit(f"{node_id} (accepted after recheck): {stable.passed}/{stable.total}")
                            return True
                        confirmation = stable
                        confirmed = stable_measured
                    else:
                        self.pending_corrections.append(
                            f"{node_id}: locator-role failure passed one independent recheck, but there was "
                            "insufficient time for a second confirmation. Preserve the UI and remeasure it "
                            "with the later suite before treating this as fixed.")
                        return False
                if (confirmed and confirmation.passed == summary.passed
                        and all(locator_role_mismatch(row) for row in confirmation.results if not row.ok)):
                    self.pending_corrections.append(
                        f"{node_id}: repeated locator-role mismatch while the named target was visible. "
                        "Check route/data readiness and the actual accessible role before changing feature logic. "
                        "The local repair was deferred to leave time for shared checkpoint diagnosis.")
                    log(f"[acceptance] {node_id}: repeated locator-role mismatch; deferring local repair")
                    return False
                if confirmed:
                    failures += "\nIndependent recheck (use the newer evidence when diagnosing):\n" + failure_summaries(confirmation)
            if measured and passed > best_passed:
                if best_passed >= 0:
                    self.commit(f"{node_id} (repair {attempt}): {passed}/{summary.total} pass")
                best_passed, best_sha, regressions, stalls = passed, self.head(), 0, 0
            elif measured and passed == best_passed and attempt > 0:
                stalls += 1
                if stalls >= 2 and not (was_codegen and self.codegen_blocked):
                    # Let a newly selected repair strategy run once, within existing budgets.
                    # Cloud f9f0026819f1: six rounds oscillating 4/6 <-> 3/6.
                    log(f"[flow] {node_id}: no improvement for two repairs; keeping the best state")
                    break
            elif measured and passed < best_passed:
                regressions += 1
                if regressions >= 2 and best_sha:
                    self.restore_app(best_sha)
                    self.pending_corrections.append(
                        f"Your last two repairs made the tests worse; the harness restored frontend/ and backend/ "
                        f"to the best state ({best_passed}/{summary.total}). Start from that code.")
                    regressions = 0
            repair_cap = min(self.repair_rounds, 2 if infrastructure_error or "F0" in levels else
                             max(0, int(os.environ.get("OCTOS_ARC_F1_REPAIR_ROUNDS", "1"))))
            if attempt >= repair_cap or self.wound_down():
                break
            left = deadline - time.time()
            needed = self.repair_minimum()
            reserve = self.final_phase_reserve()
            if left < needed or (reserve and self.remaining() < needed + reserve) or self.time_up():
                # A repair turn that starts with only a couple of minutes left
                # times out too (keep-local-3). On a large task, leave enough
                # global time to repair related failures together in the suite.
                reason = (f"{self.remaining():.0f}s run time leaves the {reserve:.0f}s final-phase reserve"
                          if reserve and self.remaining() < needed + reserve else
                          f"{left:.0f}s node time is below the {needed:.0f}s a repair needs")
                log(f"[flow] {node_id}: {reason}; keeping the best state for full-suite repair")
                break
            self.snapshot_sources(node_id, attempt)
            slow = summary.slow(self.slow_test_ms())
            slow_text = ("These tests exceeded the configured slow-test threshold: " + "; ".join(slow) +
                         ". Inspect the failed operations and measured timings before optimizing.\n" + self.perf_text()) if slow else ""
            if measured and passed == 0 and rebuild_prompt is not None and not rewrite_used \
                    and not getattr(self, "derived_as_specs", False) \
                    and best_passed <= 0 and self.can_rewrite_from_scratch() \
                    and os.environ.get("OCTOS_ARC_REWRITE_ON_ZERO", "1") != "0":
                rewrite_used = True
                log(f"[flow] {node_id}: nothing passed; one full rewrite turn instead of a patch")
                prompt = rebuild_prompt(failures or "(no detail)")
                if self.codegen_mode():
                    self.codegen_turn(prompt, min(self.node_timeout, left), f"{node_id} rewrite (repair {attempt + 1})",
                                      spec_chars=getattr(self, "current_spec_chars", 0))
                    repair_applied = bool(self.last_codegen_written)
                else:
                    self.last_turn_changed = None
                    self.turn(prompt, min(self.node_timeout, left), f"{node_id} rewrite (repair {attempt + 1})",
                              request_budget=int(os.environ.get("OCTOS_ARC_IMPLEMENT_REQUESTS", "20")))
                    repair_applied = self.last_turn_changed is not False
                if repair_applied:
                    continue
                self.pending_corrections.append("The rewrite did not change application sources. Apply the pending fix before retesting.")
                left = deadline - time.time()
                if left < self.repair_minimum() or self.wound_down():
                    break
            corrections = self.corrections_text()
            if not measured:
                corrections = str(corrections) + (
                    "\nNo functional acceptance verdict was obtained. Fix the reported build/start/load failure "
                    "in place; preserve the generated application instead of rewriting it from scratch.\n")
            def repair_prompt():
                nonlocal corrections
                corrections = str(corrections) + str(self.corrections_text())
                return self.app_repair_prompt(node_id=node_id, passed=passed, total=summary.total,
                                           failures=failures or "(no detail)", test_location=self.repair_test_location(specs),
                                           corrections=corrections,
                                           slow=slow_text, smoke=self.smoke_port, port=self.web_port,
                                           sources=self.repair_requirements(node_id) + self.sources_text())
            if not self.node_repair_turn(node_id, failures, min(self.node_timeout, left),
                                         f"{node_id} repair {attempt + 1}/{self.repair_rounds}", repair_prompt):
                break
            repair_applied = True
        # Failed repairs can leave dirty files without changing HEAD. Restore the files,
        # even when the current commit already equals the best recorded commit.
        startup_regression = bool(getattr(self, '_unresolved_startup_error', '') and best_passed >= 0)
        if best_sha and (best_passed > 0 or startup_regression):
            self.restore_app(best_sha)
            self.commit(f"{node_id}: keep best acceptance state {best_passed}")
            if startup_regression:
                # A buildable 0/N state still protects the rest of the app.
                # Restoring source is not itself a measured recovery verdict.
                self.pending_corrections.append(
                    "The last repair broke application startup. Restored the last measured buildable "
                    "state; the current feature may still fail. Preserve shared imports and exports.")
                if self.time_up() or self.remaining() < 30:
                    return None
                restored = self.run_specs(specs)
                complete = self.suite_is_measured(restored, specs)
                self._unresolved_startup_error = '' if complete else (
                    restored.error or '\n'.join(restored.load_errors) or 'Incomplete rollback verification')
                self.metric('startup_rollback', node_id=node_id, measured=complete,
                            passed=restored.passed, total=restored.total)
                if complete:
                    self.record_tests(node_id, specs, restored)
                    return restored.passed == restored.total
                return None
        return False if best_passed >= 0 else None

    # -- per node ---------------------------------------------------------
    def design(self, node: dict, ordered: list[dict], deadline: float) -> dict | None:
        node_id = str(node.get("id"))
        template = DESIGN_PROMPT
        if getattr(self, "derived_as_specs", False):
            template = template.replace(
                "Copy every accessible name verbatim from the specs.",
                "Use accessible names stated in requirements.yaml; generated specs are provisional evidence.")
        prompt = template.format(node_id=node_id, node_spec=describe_node(node),
                                      ancestors=self.ancestors_text(node_id, ordered),
                                      tests=self.tests_prompt_for(node_id))
        ok, text = self.turn(prompt, min(self.design_timeout, deadline - time.time()), f"{node_id} design",
                             expect_verification=False)
        design = None
        m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S) or re.search(r"(\{.*\})", text, re.S)
        if ok and m:
            try:
                design = json.loads(m.group(1))
            except json.JSONDecodeError:
                design = None
        if not isinstance(design, dict):
            written = self.output_dir / ".arc" / "design" / f"{node_id}.json"
            if written.is_file():
                try:
                    design = json.loads(written.read_text(encoding="utf-8"))
                    log(f"[flow] {node_id}: design read from {written.relative_to(self.output_dir)}")
                except (OSError, json.JSONDecodeError):
                    design = None
        if not isinstance(design, dict):
            log(f"[flow] {node_id}: design turn produced no JSON; continuing with prose design")
            return {"notes": text.strip()[-1500:]} if text.strip() else None
        return design

    def save_design(self, node_id: str, design: dict) -> None:
        design_dir = self.output_dir / ".arc" / "design"
        design_dir.mkdir(parents=True, exist_ok=True)
        (design_dir / f"{node_id}.json").write_text(json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            self.runtime.traceability.upsert_node_contract(node_id, design)
            for i, route in enumerate(design.get("routes") or []):
                if isinstance(route, dict):
                    self.runtime.traceability.upsert_interface(
                        interface_id=f"{node_id}:route:{i}", req_ids=[node_id], type="http",
                        content=f"{route.get('method', '')} {route.get('path', '')}".strip(), emit_event=False)
        except Exception as exc:  # noqa: BLE001
            log(f"[trace] design not recorded: {exc}")

    def batch_codegen(self, nodes: list[dict]) -> bool:
        """One source snapshot and one codegen request for independent siblings.

        Only the generation turn is shared. Each leaf still receives its own
        acceptance loop, repair budget, traceability and checkpoint. A batch
        whose prompt cannot fit falls back to the original per-node flow.
        """
        ids = [str(node.get("id")) for node in nodes]
        if (len(ids) < 2 or self.evolution or self.design_mode != "inline" or self.runner is None
                or not self.codegen_mode() or self.pending_corrections or self.wound_down()
                or self.remaining() < self.min_repair_seconds + 120
                or any(not self.spec_map.get(node_id) for node_id in ids)):
            return False
        spec = self.batch_spec_bodies(ids)
        if spec == "(none)":
            return False
        combined = {"id": ", ".join(ids),
                    "description": "Implement each independent requirement below, preserving their separate "
                                   "behaviours:\n" + "\n\n".join(describe_node(node) for node in nodes)}
        prompt = self.codegen_implement_prompt(combined, spec)
        if prompt is None:
            log(f"[flow] sibling batch {ids}: prompt did not fit; using per-node turns")
            return False
        self.refused_paths = set()
        write_codegen_manifests(self.output_dir)
        label = f"sibling batch {', '.join(ids)} implement"
        timeout = min(self.node_timeout, max(120, self.remaining() - self.min_repair_seconds))
        ok, _ = self.codegen_turn(prompt, timeout, label, spec_chars=len(spec))
        refused = set(self.refused_paths)
        if refused and self.codegen_mode():
            retry = self.codegen_implement_prompt(combined, spec)
            if retry is not None and refused <= quoted_paths(retry):
                log(f"[flow] sibling batch {ids}: retrying with {', '.join(sorted(refused))} quoted whole")
                ok, _ = self.codegen_turn(retry, timeout, label + " (retry)", spec_chars=len(spec))
        if not ok or not (getattr(self, "last_codegen_written", []) or getattr(self, "last_codegen_no_change", False)) \
                or getattr(self, "last_codegen_refused", set()):
            log(f"[flow] sibling batch {ids}: no complete write; using per-node turns")
            return False
        if getattr(self, "last_codegen_written", []):
            self.commit(f"sibling batch {', '.join(ids)} (implement)")
        group = tuple(ids)
        for node_id in group:
            self.batched_groups[node_id] = group
        log(f"[flow] sibling batch {ids}: generated once or declared no-change; validating each leaf separately")
        return True

    @staticmethod
    def generation_recovery_cap() -> int:
        return max(0, int(os.environ.get("OCTOS_ARC_DEGENERATE_GENERATION_MAX_TOKENS",
                           os.environ.get("OCTOS_ARC_DEGENERATE_MAX_TOKENS", "16384"))))

    def generation_output_budget(self) -> int:
        # Leave room for reasoning/protocol overhead and estimation error. A
        # deployment with a smaller routed model can explicitly lower this.
        maximum = max(1, int(os.environ.get("OCTOS_ARC_MAX_TOKENS", "32768")))
        recovery_cap = self.generation_recovery_cap()
        if getattr(self, "codegen_degenerated", False) and recovery_cap > 0:
            maximum = min(maximum, recovery_cap)
        routes = getattr(getattr(self, "llm_proxy", None), "routes", [])
        # Rules can override the proxy's default limit after routing. Use the
        # smallest possible implement-route cap, without guessing model names.
        if isinstance(routes, list):
            for rule in routes:
                if "implement" in rule.get("phases", ["implement"]):
                    options = rule.get("parameters", {})
                    limit = options.get("max_completion_tokens", options.get("max_tokens"))
                    if isinstance(limit, int) and limit > 0:
                        maximum = min(maximum, limit)
        return max(1, min(maximum, int(os.environ.get("OCTOS_ARC_CODEGEN_OUTPUT_TOKENS",
                                                     str(int(maximum * 0.6))))))

    def whole_app_codegen(self, tree: dict, ordered: list[dict]) -> bool:
        """Experimental v5: generate the fresh app whole or in a few waves.

        A single architecture design already precedes this turn. The tree and
        public specs are quoted once, not once per leaf. An oversized or
        truncated whole-app reply falls through to bounded multi-node waves.
        """
        ids = [str(node.get("id")) for node in ordered]
        setting = os.environ.get("OCTOS_ARC_WHOLE_APP", "auto").strip().lower()
        has_executable_specs = bool(self.tests_dir)
        has_official_specs = has_executable_specs and not getattr(self, "derived_as_specs", False)
        # A generated suite remains distinct from official specs after it is
        # installed as tests_dir. Auto uses waves for no-official-spec tasks;
        # explicit opt-in may use one generation turn when the output fits.
        enabled = setting == "1" or setting == "auto" and not has_official_specs
        has_generation_contract = (has_official_specs and self.runner is not None
                                   and all(self.spec_map.get(node_id) for node_id in ids)) \
            or (not has_official_specs and bool(self.requirement_contracts.get("nodes")))
        if (not enabled or self.evolution or len(ids) < 3 or not self.codegen_mode()
                or not has_generation_contract
                or self.wound_down() or self.remaining() < self.min_repair_seconds + 180):
            return False
        spec = self.batch_spec_bodies(ids)
        if spec == "(none)":
            return False
        if setting == "auto":
            log(f"[flow] no official specs: generating {len(ids)} leaves in bounded waves")
            return self.whole_app_waves(tree, ordered)
        self.prepare_derived_spec_batch(ordered)
        spec = self.batch_spec_bodies(ids)
        # A large input can fit while the corresponding application cannot fit
        # in one output. Keep the one-shot experiment for smaller trees; the
        # 32-leaf Keep run spent 170s on a prose-only whole-app reply.
        max_one_shot = max(1, int(os.environ.get("OCTOS_ARC_WHOLE_APP_MAX_NODES", "12")))
        estimated = generation_tokens(ordered, len(spec))
        if len(ids) > max_one_shot or estimated > self.generation_output_budget():
            log(f"[flow] whole-app experiment: {len(ids)} leaves exceed the {max_one_shot}-leaf "
                f"or estimated output budget ({estimated}/{self.generation_output_budget()} tokens); "
                "planning generation waves")
            return self.whole_app_waves(tree, ordered)
        description = ("Implement the COMPLETE application, not just one feature. "
                       "All listed atomic requirements must work together. Keep the "
                       "shared data model, routes and interaction lifecycle consistent.\n\n"
                       + tree_outline(tree) + "\n\nAtomic requirement details:\n"
                       + "\n\n".join(describe_node(node) for node in ordered))
        prompt = self.codegen_implement_prompt({"id": "whole application", "description": description}, spec)
        if prompt is None:
            log("[flow] whole-app experiment: shared prompt did not fit; planning generation waves")
            return self.whole_app_waves(tree, ordered)
        write_codegen_manifests(self.output_dir)
        timeout = min(int(os.environ.get("OCTOS_ARC_WHOLE_APP_TIMEOUT", "1800")),
                      max(120, self.remaining() - self.min_repair_seconds))
        log(f"[flow] whole-app experiment: one generation turn for {len(ids)} nodes "
            f"({len(prompt)} prompt chars, {len(spec)} spec chars, timeout {timeout}s)")
        ok, text = self.whole_app_generation_turn(prompt, timeout, "whole application implement",
                                                   spec_chars=len(spec))
        if not ok or not (getattr(self, "last_codegen_written", [])
                          or getattr(self, "last_codegen_no_change", False) is True):
            log(f"[flow] whole-app experiment: no complete application write ({text[-120:]}); "
                "planning smaller generation waves")
            return self.whole_app_waves(tree, ordered)
        self.commit("whole application (experimental implement)")
        self.whole_app_generated_ids = set(ids)
        return True

    def whole_app_generation_turn(self, prompt: str, timeout: int, label: str,
                                  *, spec_chars: int) -> tuple[bool, str]:
        """Retry a format refusal once at the same size; only output/context
        failures justify splitting a feature group. The retry shares the stable
        prompt prefix with the first request and names the exact protocol error.
        """
        deadline = time.monotonic() + timeout
        self.whole_app_generation_requests = getattr(self, "whole_app_generation_requests", 0) + 1
        def generate(*args, **kwargs):
            saved = getattr(self, "_atomic_codegen_response", False)
            self._atomic_codegen_response = True
            try:
                return self.codegen_turn(*args, **kwargs)
            finally:
                self._atomic_codegen_response = saved
        ok, text = generate(prompt, timeout, label, spec_chars=spec_chars,
                                     force_files='startup repair' in label)
        self.generation_batch_check(label)
        if ok and (getattr(self, "last_codegen_written", [])
                   or getattr(self, "last_codegen_no_change", False) is True):
            return ok, text
        format_error = (text.startswith("codegen reply contained no ")
                        or text.startswith("mixed FILE and EDIT blocks")
                        or text.startswith("Incomplete FILE/EDIT output"))
        if getattr(self, "last_codegen_written", []):
            # Any tool edit/legacy recovery changed the snapshot. The wave caller
            # rebuilds a fresh prompt; never retry an old full-file quotation.
            self.pending_corrections.append("Partial application retained: " + ", ".join(self.last_codegen_written)
                                            + ". Rebuild the next prompt from current disk; " + text[:600])
            return ok, text
        correction = ("\nNo application files from the preceding response were written: " + text[:600] +
                      "\nReturn ONLY complete <<<FILE ...>>> blocks, with exact "
                      "<<<END FILE>>> terminators. One block per path. "
                      "Do not explain the implementation.\n")
        retry_seconds = min(360, int(deadline - time.monotonic()))
        if (format_error and not getattr(self, "last_codegen_degenerated", False)
                and retry_seconds >= 30 and not self.wound_down()
                and self.remaining() >= self.min_repair_seconds + 120
                and len(prompt) + len(correction) + len(FORMAT_INSTRUCTIONS) + 1
                <= min(self.codegen_context_chars(), getattr(self, "_whole_app_prompt_cap",
                                                              self.codegen_context_chars()))):
            log(f"[flow] {label}: format rejected; one corrected reply before splitting")
            self.whole_app_generation_requests += 1
            result = generate(prompt + correction, retry_seconds, label + " (format retry)",
                                       spec_chars=spec_chars, force_files='startup repair' in label)
            self.generation_batch_check(label)
            return result
        return ok, text

    def mark_designed(self, ordered: list[dict], message: str = "covered by the application design") -> None:
        """One application design covers every leaf: show them all as designed,
        in dependency order, before any implementation starts. Otherwise the
        Canvas lists only the leaves a wave happened to reach (v10.2 sheet
        17d24626341c: 10 of 24 leaves visible, in wave order)."""
        if getattr(self, "events", None) is None:
            return  # no platform event client (unit tests, dry runs)
        for node in ordered:
            node_id = str(node.get("id"))
            if node_id in getattr(self, "_designed_ids", set()):
                continue
            self.mark("design_started", node_id)
            self.mark("design_done", node_id, message)

    def repair_wave_build(self, errors: list[str]) -> bool:
        """A confirmed build/source error left by an earlier wave breaks every
        later wave's completion check. Repair it before the next group instead
        of deferring each following leaf (v10.2 github 5d65674359a4: one missing
        api.js export deferred every wave after 01:23)."""
        digest = "\n".join(errors)[:3000]
        log(f"[flow] whole-app waves: build/source check still failing before the next group; "
            f"focused repair first: {errors[0].splitlines()[0][:200] if errors[0] else ''}")
        self.metric("wave_build_repair", errors=len(errors))
        self.whole_app_startup_repair("source check failed:\n" + digest)
        # Re-check the tree as it is now, whichever path (codegen or tools) repaired it.
        self.last_codegen_written = sorted(set(getattr(self, "_generation_gate_paths", ()) or ())
                                           | {"frontend/package.json"})
        self._generation_checked_versions = None
        self._generation_gate_result = None
        self.generation_batch_check("wave build repair check")
        gate = getattr(self, "_generation_gate_result", None)
        repaired = not (isinstance(gate, dict) and gate.get("errors"))
        log(f"[flow] whole-app waves: build repair {'cleared the check' if repaired else 'did not clear the check'}")
        return repaired

    def generation_batch_check(self, label):
        changed = getattr(self, 'last_codegen_written', [])
        if not changed or not hasattr(self, 'max_total_tokens'):
            return  # No configured execution budget: do not launch subprocesses.
        if self.wound_down() or self.remaining() < self.min_repair_seconds + 120:
            return
        from generation_checks import check_batch
        index = self.repair_source_index()
        versions = index.versions
        if versions == getattr(self, '_generation_checked_versions', None):
            return
        paths = set(changed) | set(getattr(self, '_generation_gate_paths', ()))
        result = check_batch(self.output_dir, paths, budget=30, sources=index.sources)
        self._generation_gate_result = result
        # Confirmed errors must remain visible until changed. Deferred checks
        # are environment/budget state, not source evidence; carrying their
        # paths forever makes every later wave re-audit unrelated files.
        self._generation_gate_paths = paths if result['errors'] else set()
        self._generation_checked_versions = versions
        self._generation_gate_evidence = '\n'.join(result['errors'])[:4000]
        backend_advisories = [str(item) for item in result.get('deferred') or []
                              if str(item).startswith(('backend module:', 'backend export:'))]
        if backend_advisories:
            self._generation_gate_evidence += ('\nCurrent backend startup/interface risks '
                                               '(advisory; continue feature generation):\n' +
                                               '\n'.join(backend_advisories[:8]))[:2200]
        if result.get('warnings'):
            self._generation_gate_evidence += ('\nAdvisory contract checks (not confirmed errors):\n' +
                                              '\n'.join(result['warnings']))[:2200]
        self.metric('generation_gate', label=label, **result)
        if result['errors']:
            log(f"[flow] {label}: early checks found {len(result['errors'])} issue(s); exact evidence queued for next batch")

    def retain_safe_no_spec_partial(self, node_id: str) -> bool:
        """Keep useful writes from a capped turn when no local suite exists.

        A hard request cap means that the conversation is incomplete, not that
        every written file is invalid. Preserve a partial result only after the
        deterministic syntax/import/build gate found no source error. Confirmed
        errors and all official-spec paths retain the established rollback and
        acceptance behaviour.
        """
        changed = list(getattr(self, "last_codegen_written", ()))
        if getattr(self, "tests_dir", None) or not changed or not self.has_app():
            return False
        result = getattr(self, "_generation_gate_result", None)
        if not isinstance(result, dict) or result.get("errors"):
            return False
        if any(str(item).startswith("backend module:") for item in result.get("deferred") or []):
            return False  # a truncated turn must not be retained as a safe startup snapshot
        checked = set(result.get("checked") or [])
        if any(path.startswith("frontend/") for path in changed) and "frontend build" not in checked:
            return False
        backend_code = [path for path in changed
                        if path.startswith("backend/") and Path(path).suffix in {".js", ".mjs", ".cjs"}]
        if any("syntax " + path not in checked for path in backend_code):
            return False
        if any(path.endswith("package.json") for path in changed):
            return False
        self.pending_corrections.append(
            f"{node_id}: the previous structured-edit turn reached its request limit after changing "
            f"{', '.join(changed[:8])}. Early syntax/import/build checks found no source error. "
            "Continue from the current files and finish the remaining requirement details; do not restart the module."
        )
        self.metric("incomplete_node_retained", node_id=node_id, changed_files=changed,
                    checked=result.get("checked", []), deferred=result.get("deferred", []))
        log(f"[flow] {node_id}: retaining {len(changed)} partial file edit(s); "
            "early checks found no source error and official specs are unavailable")
        return True

    def whole_app_wave_design_items(self, ids: list[str]) -> dict[str, list[dict]]:
        """Return design artifacts explicitly owned by this wave's leaves."""
        design = getattr(self, "app_design_doc", None) or {}
        wanted = set(map(str, ids))
        selected: dict[str, list[dict]] = {"routes": [], "pages": []}
        for kind in selected:
            for item in design.get(kind) or []:
                owners = set(map(str, item.get("requirements") or []))
                if owners & wanted:
                    selected[kind].append(item)
        return selected

    def whole_app_wave_targets(self, ids: list[str], spec: str, details: str) -> set[str]:
        """Existing sources a feature wave is reasonably expected to edit.

        Source ranking used to see only the acceptance/derived contract.  The
        relevant route/page slice is appended later in the prompt, so shared
        files such as App.jsx, style.css and repositories.js could be omitted
        and then rejected by the write guard.  Promote those targets before
        serializing the snapshot; this changes visibility, never write safety.
        """
        paths = [path.relative_to(self.output_dir) for path in app_source_files(self.output_dir)]
        available = {str(path) for path in paths}
        artifacts = self.whole_app_wave_design_items(ids)
        design_text = json.dumps(artifacts, ensure_ascii=False)
        evidence = spec + "\n" + details + "\n" + design_text
        targets = spec_targets(evidence, paths) | navigation_targets(evidence, paths)
        # App/router is the composition boundary every feature wave may extend.
        # Quoting it consistently is cheaper than a refusal plus a replay and
        # prevents later waves from silently dropping earlier routes.
        targets |= {path for path in available
                    if Path(path).name in COMPOSITION_FILES}
        if artifacts["pages"]:
            targets |= {path for path in available
                        if Path(path).name == "style.css"}
        active_terms = {term for term in spec_terms(evidence) if len(term) >= 4}
        for module in (getattr(self, "app_design_doc", None) or {}).get("modules") or []:
            rel = str(module.get("path") or "")
            owned = json.dumps(module.get("owns") or [], ensure_ascii=False)
            if rel in available and active_terms & spec_terms(owned + " " + rel):
                targets.add(rel)
        targets |= set(getattr(self, "refused_paths", ()))
        return targets & available

    def api_call_planned_later(self, warning: str, ids: list[str]) -> bool:
        """An unmatched call whose design route belongs only to a later leaf.

        Forward calls to planned features are expected during dependency-
        ordered waves; the owning leaf's own guard requires the route.
        """
        match = re.search(r"\bcalls (GET|POST|PUT|PATCH|DELETE) (/api/\S+?),? but", warning)
        if not match:
            return False
        method, call = match.group(1), match.group(2).rstrip(",")

        def shape(value: str) -> list[str]:
            value = re.sub(r"\$\{[^}]+\}", ":", value.split("?", 1)[0])
            return [":" if part.startswith(":") else part for part in value.strip("/").split("/") if part]

        settled = set(map(str, ids)) | set(getattr(self, "whole_app_generated_ids", ()) or ())
        for route in (getattr(self, "app_design_doc", None) or {}).get("routes") or []:
            if not isinstance(route, dict) or str(route.get("method") or "").upper() != method:
                continue
            if shape(str(route.get("path") or "")) != shape(call):
                continue
            owners = set(map(str, route.get("requirements") or []))
            return bool(owners) and not owners & settled
        return False

    def whole_app_wave_gaps(self, ids: list[str]) -> list[str]:
        """Deterministic reasons a wave cannot yet be declared complete.

        This is deliberately narrower than functional acceptance.  It blocks
        confirmed source errors, refused rewrites, exact design routes/pages
        that are absent, and concrete route/API link warnings.  It does not
        invent tests or promote advisory literal guesses into failures.
        """
        gaps: list[str] = []
        refused = sorted(getattr(self, "last_codegen_refused", set()))
        if refused:
            gaps.append("write guard refused required existing file(s): " + ", ".join(refused))
        gate = getattr(self, "_generation_gate_result", None)
        if isinstance(gate, dict):
            gaps.extend("source check: " + str(error) for error in gate.get("errors") or [])
            current = set(getattr(self, "last_codegen_written", ()))
            for warning in gate.get("warnings") or []:
                value = str(warning)
                owned = any(f": {path} " in value for path in current)
                if value.startswith("API_CALL ") and owned:
                    if not self.api_call_planned_later(value, ids):
                        self.metric("wave_api_advisory", node_ids=ids, warning=value,
                                    verification="requires_runtime_evidence")
                        if os.environ.get("OCTOS_ARC_BLOCK_API_WARNINGS", "0") == "1":
                            gaps.append(value)
                elif value.startswith("ROUTE_CONFLICT") and any(path in value for path in current):
                    # Statically certain: Express serves only the first
                    # registration, so the later handler is dead code.
                    gaps.append(value)
                elif (value.startswith("ROUTE_LINK ") and owned and
                      os.environ.get("OCTOS_ARC_BLOCK_ROUTE_WARNINGS", "0") == "1"):
                    gaps.append(value)

        sources = {str(path.relative_to(self.output_dir)):
                   path.read_text(encoding="utf-8", errors="replace")
                   for path in app_source_files(self.output_dir)}
        if sources:
            contracts = getattr(self, "requirement_contracts", None)
            if (not self.tests_dir or any(self.derived_review_needed(node_id) for node_id in ids)) \
                    and isinstance(contracts, dict):
                # A source substring cannot establish runtime seed semantics.
                # Keep this evidence advisory and let browser checks decide.
                hints = source_seed_gaps(contracts, sources, ids)
                if hints:
                    self.metric("seed_source_hint", node_ids=ids, advisory=True, hints=hints[:8])
            artifacts = self.whole_app_wave_design_items(ids)
            backend = "\n".join(text for path, text in sources.items() if path.startswith("backend/"))
            frontend_routes = "\n".join(
                text for path, text in sources.items()
                if path.startswith("frontend/") and Path(path).name.lower() in {
                    "app.jsx", "app.tsx", "app.js", "app.ts", "router.js", "router.ts", "routes.jsx", "routes.tsx"})
            for route in artifacts["routes"]:
                method = str(route.get("method") or "").lower()
                path = str(route.get("path") or "")
                pattern = r"\.(?:" + re.escape(method) + r")\s*\(\s*['\"]" + re.escape(path) + r"['\"]"
                if method and path and not re.search(pattern, backend):
                    gaps.append(f"design route missing: {method.upper()} {path}")
            for page in artifacts["pages"]:
                path = str(page.get("path") or "")
                pattern = r"<Route\b[^>]{0,600}\bpath\s*=\s*['\"]" + re.escape(path) + r"['\"]"
                if path and frontend_routes and not re.search(pattern, frontend_routes):
                    gaps.append(f"design page route missing: {path}")
        return list(dict.fromkeys(gaps))[:16]

    def no_spec_feature_review(self, node: dict, deadline: float) -> list[str]:
        """Review one just-written feature against its derived scenarios.

        Every no-spec feature gets the deterministic audit. A second model
        request is conditional on concrete source/design/seed evidence, which
        avoids doubling token use merely to ask the author whether its own code
        is correct. The corrective turn sees the full active scenarios and the
        exact focused source closure.
        """
        node_id = str(node.get("id"))
        if getattr(self, "tests_dir", None) and not self.derived_review_needed(node_id):
            return []
        contracts = getattr(self, "requirement_contracts", None)
        if not isinstance(contracts, dict) or not any(
                str(item.get("id")) == node_id for item in contracts.get("nodes") or []):
            return []
        try:
            gaps = self.whole_app_wave_gaps([node_id])
        except Exception as exc:  # an advisory audit cannot stop generation
            gaps = ["source audit unavailable: " + str(exc)[:200]]
        self.metric("no_spec_feature_review", node_id=node_id,
                    outcome="needs_repair" if gaps else "clean", gaps=gaps[:8])
        if not gaps:
            log(f"[flow] {node_id}: scenario/seed self-check found no deterministic gap")
            return []

        details = describe_node(node)
        spec = self.spec_bodies(node_id)
        targets = self.whole_app_wave_targets([node_id], spec, details)
        relationships = self.repair_source_index().render(targets, limit=4000) if targets else ""
        evidence = (
            "Post-write no-spec scenario review found the concrete gaps below. Inspect the current implementation "
            "and fix confirmed gaps only. Trace every GIVEN -> WHEN -> THEN path. For explicit initial records, "
            "verify a fresh store contains them and an existing store is never reset or reseeded after deletion.\n"
            + "\n".join(gaps[:10])
            + ("\n\nCurrent feature dependency/interface map:\n" + relationships if relationships else "")
        )
        prompt_cap, source_cap = self.whole_app_budgets()
        prompt = self.codegen_implement_prompt(
            node, spec, evidence=evidence, must_include=targets,
            context_limit=prompt_cap, source_limit=source_cap, focused_sources=True)
        if prompt is None:
            # Keep the router and the files the gaps name; the rest are quoted
            # when they fit. Previously every such repair was skipped.
            named = {rel for rel in targets if any(rel in gap for gap in gaps)}
            minimal = {rel for rel in targets if Path(rel).name in COMPOSITION_FILES} | named
            if minimal < targets:
                prompt = self.codegen_implement_prompt(
                    node, spec, evidence=evidence, must_include=minimal,
                    context_limit=prompt_cap, source_limit=source_cap, focused_sources=True)
        review_cap = max(30, int(os.environ.get("OCTOS_ARC_NO_SPEC_REVIEW_SECONDS", "180")))
        available = min(review_cap, max(0, int(deadline - time.time())), max(0, int(self.remaining())))
        if prompt is None or available < 30 or self.wound_down():
            reason = self.codegen_budget.get("reason") if prompt is None else "insufficient review budget"
            self.pending_corrections.append(
                f"{node_id}: no-spec scenario review remains pending ({reason}): " + "; ".join(gaps[:6]))
            log(f"[flow] {node_id}: scenario self-check found {len(gaps)} gap(s); repair deferred ({reason})")
            return gaps

        write_codegen_manifests(self.output_dir)
        log(f"[flow] {node_id}: scenario self-check found {len(gaps)} concrete gap(s); "
            f"running one focused repair ({len(prompt)} prompt chars)")
        self.codegen_turn(prompt, available, f"{node_id} requirement contract repair", spec_chars=len(spec))
        remaining = self.whole_app_wave_gaps([node_id])
        self.metric("no_spec_feature_review", node_id=node_id,
                    outcome="repaired" if not remaining else "still_incomplete", gaps=remaining[:8])
        if remaining:
            self.pending_corrections.append(
                f"{node_id}: no-spec scenario review still has concrete gaps: " + "; ".join(remaining[:6]))
            log(f"[flow] {node_id}: {len(remaining)} scenario/seed gap(s) remain for final review")
        else:
            log(f"[flow] {node_id}: focused scenario/seed repair cleared the deterministic gaps")
        return remaining

    # -- derived scenario checks (no official specs) ------------------------
    def prepare_derived_tests(self, ordered: list[dict]) -> bool:
        """Compile static Playwright checks from requirements.yaml, once.

        They live under .arc/ (protected from model writes) and are re-run
        unchanged by every derived acceptance round; no model tokens are spent.
        """
        if self.tests_dir or os.environ.get("OCTOS_ARC_DERIVED_TESTS", "1") == "0":
            return False
        if self.events is not None:
            for node in ordered:
                self.mark("design_started", str(node.get("id")),
                          "generating requirement-derived tests before implementation")
        tree = getattr(self, "requirement_tree", None)
        log(f"[derived] compiling requirement specs for {len(ordered)} node(s)")
        def progress(node_id: str, index: int, total: int, scripts: int,
                     entries: int, kept: int) -> None:
            status = "behavior" if scripts else "entry_only" if kept else "no_check"
            log(f"[derived] spec {index}/{total} {node_id}: mechanical={status}, "
                f"behavior={scripts}, entry={entries}, kept={kept}")
            self.metric("derived_spec_node", node_id=node_id, phase="mechanical", status=status,
                        index=index, total=total, behavior=scripts, entry=entries, kept=kept)
        files = compile_derived_suite(ordered, ancestor_context(tree), folder_text(tree), progress=progress)
        specs = sorted(rel for rel in files if rel.endswith(".spec.ts"))
        if not specs:
            log("[derived] no scenario yielded a mechanical check; AI will plan the first behavioural specs")
        directory = self.output_dir / ".arc" / "derived-tests"
        if directory.exists():
            shutil.rmtree(directory)
        write_suite(directory, files)
        self.derived_tests_dir = directory
        self.derived_spec_map = {rel[:-len(".spec.ts")]: [rel] for rel in specs}
        self.derived_nodes = list(ordered)
        self._derived_scenario_targets = None
        self.derived_spec_disputes: dict[tuple[str, str], str] = {}
        self.derived_case_reviews: dict[tuple[str, str], dict] = {}
        self.derived_augmented = False
        self.derived_augmented_nodes: set[str] = set()
        self.derived_augmentation_attempts: dict[str, int] = {}
        self.derived_specs_frozen = False
        self.derived_llm_seconds = 0.0
        self.derived_review_requests = 0
        self.derived_case_review_requests = 0
        self.derived_node_results: dict[str, tuple[int, int] | None] = {}
        checks = sum(source.count("\ntest(") + source.startswith("test(") for rel, source in files.items()
                     if rel.endswith(".spec.ts"))
        scripts = sum(source.count("[script]'") for source in files.values())
        entries = sum(source.count("[entry]'") for source in files.values())
        log(f"[derived] compiled {checks} static check(s) ({scripts} scenario script(s), {entries} entry script(s)) "
            f"for {len(specs)}/{len(ordered)} leaves into {directory}")
        return True

    def verify_derived_suite(self) -> None:
        """Every generated spec must load in Playwright.

        Preserve and archive unloadable originals. A top-level import/parse
        failure is a blocked file, never a collection of invalid test oracles.
        """
        runner = getattr(self, "runner", None)
        directory = self.derived_tests_dir
        if runner is None or not hasattr(runner, "list_specs"):
            return
        specs = sorted(str(p.relative_to(directory)) for p in directory.rglob("*.spec.ts"))
        if not specs:
            return
        helper_digest = hashlib.sha256()
        for path in sorted(directory.rglob("*.ts")):
            if path.name.endswith(".spec.ts"):
                continue
            helper_digest.update(str(path.relative_to(directory)).encode("utf-8"))
            helper_digest.update(hashlib.sha256(path.read_bytes()).digest())
        helpers = helper_digest.hexdigest()
        hashes = {rel: hashlib.sha256((directory / rel).read_bytes()).hexdigest() for rel in specs}
        previous = getattr(self, "_derived_verified_hashes", {})
        changed = (specs if helpers != getattr(self, "_derived_verified_helpers", None)
                   else [rel for rel in specs if previous.get(rel) != hashes[rel]])
        blocked_path = self.output_dir / ".arc/test-control/load-errors/blocked-files.json"
        try:
            blocked = json.loads(blocked_path.read_text(encoding="utf-8")) if blocked_path.is_file() else {}
        except (OSError, ValueError):
            blocked = {}
        if not isinstance(blocked, dict):
            blocked = {}
        if not changed:
            self.derived_suite_verified = not bool(blocked or getattr(self, "_derived_suite_global_error", ""))
            self._derived_suite_load_blocked = not self.derived_suite_verified
            return
        ok, detail = runner.list_specs(changed)
        if ok:
            for rel in changed:
                blocked.pop(rel, None)
            self._derived_verified_hashes = hashes
            self._derived_verified_helpers = helpers
            self._derived_suite_global_error = ""
            if blocked_path.exists():
                blocked_path.write_text(json.dumps(blocked, ensure_ascii=False, indent=2) + "\n")
                self.snapshot_protected()
            self._derived_suite_load_blocked = bool(blocked)
            self.derived_suite_verified = not bool(blocked)
            log(f"[derived] checked {len(changed)} changed spec file(s) in Playwright; "
                f"{len(blocked)} unchanged file(s) remain blocked")
            return
        log(f"[derived] generated suite does not load; isolating the failing file(s): {detail[-300:]}")
        archive = self.output_dir / ".arc" / "test-control" / "load-errors"
        archive.mkdir(parents=True, exist_ok=True)
        verified = dict(previous)
        for rel in changed:
            loads, failure = runner.list_specs([rel])
            if loads:
                blocked.pop(rel, None)
                verified[rel] = hashes[rel]
            else:
                source = (directory / rel).read_bytes()
                (archive / (hashlib.sha256(source).hexdigest()[:12] + "-" + Path(rel).name)).write_bytes(source)
                blocked[rel] = {"execution": "blocked", "reason": str(failure)[-1500:],
                                "file_hash": hashlib.sha256(source).hexdigest()}
                verified[rel] = hashes[rel]
        (archive / "blocked-files.json").write_text(json.dumps(blocked, ensure_ascii=False, indent=2) + "\n")
        self._derived_verified_hashes = verified
        self._derived_verified_helpers = helpers
        self._derived_suite_global_error = str(detail)[-500:] if not blocked else ""
        self.derived_suite_verified = False
        self._derived_suite_load_blocked = bool(blocked or self._derived_suite_global_error)
        self.metric("derived_suite_verification", blocked=list(blocked), checked=len(changed), total=len(specs))
        self.snapshot_protected()
        log(f"[derived] {len(blocked)} generated file(s) blocked by load errors; originals preserved, no passing verdict")

    def planned_derived_scenarios(self) -> list[dict]:
        """One stable target per distinct requirements.yaml scenario."""
        cached = getattr(self, "_derived_scenario_targets", None)
        if cached is None:
            nodes = list(getattr(self, "derived_nodes", []))
            tree = getattr(self, "requirement_tree", None)
            cached = review_targets(nodes, suite_fixtures(nodes), ancestor_context(tree),
                                    folder_text(tree), include_all=True, dependency_tree=tree)
            self._derived_scenario_targets = cached
        return cached

    def derived_scenario_coverage(self, node_id: str) -> dict:
        """Match each scenario to a concrete action-then-assertion test."""
        directory = getattr(self, "derived_tests_dir", None)
        path = directory / f"{node_id}.spec.ts" if directory else None
        source = path.read_text(encoding="utf-8") if path and path.is_file() else ""
        valid = behavior_test_titles(source)
        disputes = getattr(self, "derived_spec_disputes", {})
        rows = []
        for target in self.planned_derived_scenarios():
            if target["node_id"] != node_id:
                continue
            candidates = [f"{target['title']} [script]", f"{target['title']} [model]"]
            candidates += sorted(title for title in valid if re.fullmatch(re.escape(target['title']) + r" \[case [1-8]\] \[model\]", title))
            matched = [title for title in candidates if title in valid and (node_id, title) not in disputes
                       and grounded_behavior_test(source, title, target)]
            disputed = [title for title in candidates if (node_id, title) in disputes]
            rows.append({"id": target["id"], "title": target["title"],
                         "status": "covered" if matched else "disputed" if disputed else "missing",
                         "tests": matched,
                         "disputes": {title: disputes[(node_id, title)] for title in disputed}})
        from scenario_review import contract_outcomes, positive_contract_evidence
        from test_policy import test_block
        node = next((node for node in getattr(self, "derived_nodes", []) if str(node.get("id")) == node_id), {})
        outcomes = []
        for outcome in contract_outcomes(str(node.get("description") or "")):
            matched = []
            for title in valid:
                if (node_id, title) in disputes:
                    continue
                block = test_block(source, title)
                if block and positive_contract_evidence(source, title, outcome["literal"]):
                    matched.append(title)
            outcomes.append({**outcome, "tests": sorted(matched), "status": "covered" if matched else "missing"})
        from scenario_review import semantic_contract_evidence
        semantic = []
        for target in self.planned_derived_scenarios():
            if target["node_id"] != node_id:
                continue
            for contract in target.get("semantic_contracts") or []:
                # Another scenario in the same leaf can prove the same branch;
                # the witness itself must contain the whole transition in one
                # independently reset test block.
                matched = [title for title in valid if (node_id, title) not in disputes
                           and semantic_contract_evidence(source, title, contract["kind"])]
                semantic.append({"scenario": target["title"], **contract,
                                 "tests": sorted(matched), "status": "covered" if matched else "missing"})
        return {"node_id": node_id, "total": len(rows),
                "covered": sum(row["status"] == "covered" for row in rows), "scenarios": rows,
                "contract_outcomes": outcomes, "missing_contract_outcomes": sum(not row["tests"] for row in outcomes),
                "semantic_contracts": semantic, "missing_semantic_contracts": sum(not row["tests"] for row in semantic)}

    def write_derived_coverage(self, summary: RunSummary | None = None) -> None:
        """Persist scenario coverage separately from raw Playwright pass counts."""
        if not getattr(self, "derived_as_specs", False):
            return
        nodes = list(getattr(self, "derived_nodes", []))
        features = [self.derived_scenario_coverage(str(node.get("id"))) for node in nodes]
        from test_policy import digest
        cache = getattr(self, "_derived_runtime_cache", {})
        versions = {p.name: digest(p.read_text()) for p in self.derived_tests_dir.glob("*.spec.ts")}
        for row in summary.results if summary else []:
            filename = Path(row.file or "").name
            cache[(filename, row.title)] = (versions.get(filename), row.status)
        cache = {key: value for key, value in cache.items() if versions.get(key[0]) == value[0]}
        self._derived_runtime_cache = cache
        outcomes = {key: value[1] for key, value in cache.items()}
        for feature in features:
            filename = f"{feature['node_id']}.spec.ts"
            for scenario in feature["scenarios"]:
                titles = scenario["tests"] + list(scenario["disputes"])
                checks = [outcomes[(filename, title)] for title in titles
                          if (filename, title) in outcomes]
                scenario["runtime"] = ("quarantined" if "quarantined" in checks else
                                       "passed" if checks and len(checks) == len(titles) and all(status == "passed" for status in checks) else
                                       "failed" if checks else "unmeasured")
            for contract in feature.get("contract_outcomes", []) + feature.get("semantic_contracts", []):
                checks = [outcomes[(filename, title)] for title in contract["tests"]
                          if (filename, title) in outcomes]
                contract["runtime"] = ("passed" if "passed" in checks else
                                       "failed" if checks else "unmeasured")
        report = {"kind": "derived_scenario_coverage", "features": features,
                  "totals": {"scenarios": sum(item["total"] for item in features),
                             "covered": sum(item["covered"] for item in features),
                             "missing": sum(row["status"] == "missing" for item in features
                                            for row in item["scenarios"]),
                             "disputed": sum(row["status"] == "disputed" for item in features
                                             for row in item["scenarios"]),
                             "semantic_contracts": sum(len(item.get("semantic_contracts", [])) for item in features),
                             "missing_semantic_contracts": sum(item.get("missing_semantic_contracts", 0)
                                                               for item in features)}}
        if summary is not None:
            quarantined = sum(row.status == "quarantined" for row in summary.results)
            active_total = sum(row.status != "quarantined" for row in summary.results)
            self._derived_execution_report = {"scope": "latest_run", "discovered": summary.total,
                "files": sorted({Path(row.file or "").name for row in summary.results}),
                "active_total": active_total, "active_passed": summary.passed,
                "active_rate": summary.passed / active_total if active_total else None,
                "quarantined": quarantined, "failed": sum(row.status in {"failed", "timedOut"} for row in summary.results),
                "blocked": bool(summary.error or summary.load_errors or summary.killed)}
        report["execution"] = getattr(self, "_derived_execution_report", None)
        path = self.output_dir / ".arc" / "derived-coverage.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def weak_derived_leaves(self, ordered: list[dict]) -> list[str]:
        """Leaves whose scenarios lack concrete behavioral checks."""
        if not getattr(self, "derived_tests_dir", None):
            return []
        return [str(node.get("id")) for node in ordered if self.derived_review_needed(str(node.get("id")))]

    def derived_review_needed(self, node_id: str) -> bool:
        """Every scenario needs an action-then-assertion test for verification."""
        if not getattr(self, "derived_as_specs", False):
            return False
        coverage = self.derived_scenario_coverage(node_id)
        reviews = getattr(self, "derived_case_reviews", None)
        targets = {str(target.get("id")) for target in self.planned_derived_scenarios()
                   if target.get("node_id") == node_id} if reviews is not None else set()
        approved = {str(row.get("scenario_id")) for row in reviews.values()
                    if row.get("node_id") == node_id and row.get("status") == "approved_behavior"
                    and self.trusted_derived_case(node_id, str(row.get("title") or ""))} if reviews is not None else set()
        unreviewed = bool(targets - approved)
        return (unreviewed or coverage["total"] == 0 or coverage["covered"] < coverage["total"]
                or bool(coverage.get("missing_contract_outcomes"))
                or bool(coverage.get("missing_semantic_contracts")))

    def derived_completeness_pass(self, ordered: list[dict]) -> None:
        """Read-only code audit for weak or unreviewed generated-test coverage.

        A reach-only check is not evidence that application logic is broken.
        This pass never edits source and never promotes an untested feature to
        passed. Its findings remain explicit coverage gaps in the final report.
        """
        if not getattr(self, "derived_as_specs", False):
            return
        weak = self.weak_derived_leaves(ordered)
        for node_id in weak:
            self.self_audit_node(node_id, "generated test coverage is weak or unreviewed")
        if weak:
            log(f"[flow] read-only completeness audit: {len(weak)} weak leaf/leaves remain unverified")
        self.metric("completeness_pass", checked=weak, outcome="reviewed_unverified", app_edits=0)

    def adopt_derived_specs(self, node_ids: list[str]) -> None:
        """Make the derived spec directory the acceptance suite of this run."""
        directory = self.derived_tests_dir
        self.verify_derived_suite()
        specs = sorted(str(p.relative_to(directory)) for p in directory.rglob("*.spec.ts"))
        # One spec file per leaf, named after it: no heuristic mapping needed.
        self.spec_map = {node_id: [rel for rel in specs if rel == f"{node_id}.spec.ts"] for node_id in node_ids}
        self.spec_map[None] = [rel for rel in specs if rel[:-len(".spec.ts")] not in set(node_ids)]
        self.aliases = {}
        self.tests_dir = directory
        self.derived_as_specs = True
        self.write_derived_coverage()
        log(f"[tests] {len(specs)} derived spec files at {directory} are internal diagnostics; mapping "
            f"{ {k: v for k, v in self.spec_map.items() if v} }")

    def augment_derived_tests(self, ordered: list[dict]) -> int:
        """Plan and propose behavioural specs for a pre-implementation category.

        Bounded in requests and validated literal by literal (scenario_review):
        the model contributes navigation order and which requirement literal
        is the assertion; it cannot name a control or value the requirement
        does not. Each node is planned once; returns the number of tests added.
        """
        directory = getattr(self, "derived_tests_dir", None)
        if not directory or os.environ.get("OCTOS_ARC_DERIVED_LLM", "1") == "0":
            return 0
        selected = {str(node.get("id")) for node in ordered}
        selected = {node_id for node_id in selected
                    if node_id not in getattr(self, "derived_augmented_nodes", set())
                    and getattr(self, "derived_augmentation_attempts", {}).get(node_id, 0) < 2}
        if not selected:
            return 0
        for node_id in selected:
            self.derived_augmentation_attempts[node_id] = self.derived_augmentation_attempts.get(node_id, 0) + 1
        self.derived_augmented = True
        fixtures = suite_fixtures(getattr(self, "derived_nodes", ordered))
        all_targets = self.planned_derived_scenarios()
        targets = prioritize_review_targets([target for target in all_targets
                                             if target["node_id"] in selected])
        batch = max(1, int(os.environ.get("OCTOS_ARC_DERIVED_LLM_BATCH", "6")))
        # Node batches may be smaller than the scenario batch (including one
        # leaf at a time), so the default must not exhaust before later nodes.
        phase_plan = getattr(self, "phase_plan", None) or {}
        phase_order = [phase["id"] for phase in phase_plan.get("phases", [])]
        default_requests = min(8, max(2, len(phase_order), (len(all_targets) + batch - 1) // batch))
        max_requests = max(0, int(os.environ.get("OCTOS_ARC_DERIVED_LLM_REQUESTS", str(default_requests))))
        reserved_phases = phase_order[:max_requests]
        phase_counts = getattr(self, "derived_model_phase_requests", {})
        self.derived_model_phase_requests = phase_counts
        wall_cap = max(0, int(os.environ.get("OCTOS_ARC_DERIVED_LLM_WALL_SECONDS", "480")))
        # A six-scenario batch took 389s locally (33k reasoning tokens): 300s cut
        # whole batches off online.
        timeout = max(30, int(os.environ.get("OCTOS_ARC_DERIVED_LLM_SECONDS", "240")))
        review_dir = directory / "review"
        review_dir.mkdir(parents=True, exist_ok=True)
        plan_path = review_dir / "plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.is_file() else {
            "phase": "before_implementation", "targets": [
            {"id": t["id"], "node_id": t["node_id"], "title": t["title"], "steps": t["steps"],
             "status": "pending", "leaf_has_mechanical_behavior": "[script]" in (
                 (directory / f"{t['node_id']}.spec.ts").read_text(encoding="utf-8")
                 if (directory / f"{t['node_id']}.spec.ts").is_file() else "")}
            for t in all_targets]}
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        plan_rows = {row["id"]: row for row in plan["targets"]}
        phase_by_id = {phase["id"]: phase for phase in phase_plan.get("phases", [])}
        all_nodes = {str(node.get("id")): node for node in getattr(self, "derived_nodes", ordered)}
        phase_contexts: dict[str, str] = {}
        for phase_id, phase in phase_by_id.items():
            siblings = [all_nodes[node_id] for node_id in phase.get("leaves", []) if node_id in all_nodes]
            per_node = max(60, min(300, 6000 // max(1, len(siblings))))
            phase_contexts[phase_id] = json.dumps({
                "category": phase.get("name") or phase_id,
                "requirements": [{"id": str(node.get("id")), "name": str(node.get("name") or ""),
                                  "description": str(node.get("description") or "")[:per_node]}
                                 for node in siblings],
                "cross_dependencies": phase.get("cross_dependencies", [])[:20],
            }, ensure_ascii=False)
        def report_nodes(chunk: list[dict], batch_number: int, status: str) -> None:
            counts: dict[str, int] = {}
            for target in chunk:
                node_id = str(target["node_id"])
                counts[node_id] = counts.get(node_id, 0) + 1
            for node_id, count in counts.items():
                coverage = self.derived_scenario_coverage(node_id)
                log(f"[derived] spec AI batch {batch_number} {node_id}: {status}, "
                    f"scenarios_in_batch={count}, covered={coverage['covered']}/{coverage['total']}")
                self.metric("derived_spec_node", node_id=node_id, phase="ai", status=status,
                            batch=batch_number, scenarios_in_batch=count,
                            covered=coverage["covered"], total=coverage["total"])
        added = 0
        dropped_total: list[str] = []
        for index in range(0, len(targets), batch):
            preflight_left = getattr(self, "derived_preflight_deadline", float("inf")) - time.monotonic()
            if (self.derived_review_requests >= max_requests or self.derived_llm_seconds >= wall_cap - 30
                    or preflight_left < 30 or self.derived_preflight_tokens_spent()):
                log("[derived] model review stopped: preflight request, token, or time limit reached")
                break
            if self.wound_down() or self.remaining() < self.final_phase_reserve() + 600:
                log("[derived] model review stopped: time reserved for the final phases")
                break
            chunk = targets[index:index + batch]
            phase_id = (phase_plan.get("leaf_phase", {}) or {}).get(str(chunk[0]["node_id"]), "")
            if (reserved_phases and phase_id not in reserved_phases) or (
                    phase_id in reserved_phases and not review_request_admissible(
                        phase_id, reserved_phases, phase_counts, self.derived_review_requests, max_requests)):
                break
            self.derived_review_requests += 1
            if phase_id:
                phase_counts[phase_id] = phase_counts.get(phase_id, 0) + 1
            batch_number = self.derived_review_requests
            for target in chunk:
                plan_rows[target["id"]]["status"] = "attempted"
            plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            report_nodes(chunk, batch_number, "generating")
            prompt = build_review_prompt(chunk, fixtures, phase_contexts.get(phase_id, ""))
            self.snapshot_protected()  # commit harness plan/spec writes before calling the model
            started = time.monotonic()
            ok, text = self.text_turn(prompt, max(1, int(min(
                timeout, max(1, wall_cap - self.derived_llm_seconds), preflight_left))),
                                      "derived scenario review", system=REVIEW_SYSTEM, spec_chars=len(prompt))
            self.derived_llm_seconds += time.monotonic() - started
            (review_dir / f"batch-{batch_number}.txt").write_text(
                f"# ok={ok}\n# scenarios={[t['title'] for t in chunk]}\n{text}", encoding="utf-8")
            if not ok:
                log(f"[derived] model review batch {batch_number}: no usable reply ({str(text)[:120]})")
                report_nodes(chunk, batch_number, "unavailable")
                continue
            scripts, dropped, retryable = compile_review_reply(text, chunk, fixtures, with_retryable=True)
            retry_left = getattr(self, "derived_preflight_deadline", float("inf")) - time.monotonic()
            if (retryable and not self.wound_down()
                    and self.derived_llm_seconds + 30 < wall_cap and retry_left >= 30
                    and not self.derived_preflight_tokens_spent()
                    and self.derived_review_requests < max_requests
                    and (phase_id not in reserved_phases or review_request_admissible(
                        phase_id, reserved_phases, phase_counts, self.derived_review_requests, max_requests))):
                # One correction round: the model sees exactly which rule each
                # rejected script broke; anything still invalid is dropped.
                prompt = build_review_retry(retryable, chunk, fixtures)
                self.snapshot_protected()  # includes accepted earlier batches and this review artifact
                self.derived_review_requests += 1
                if phase_id:
                    phase_counts[phase_id] = phase_counts.get(phase_id, 0) + 1
                started = time.monotonic()
                ok, text = self.text_turn(prompt, max(1, int(min(
                    timeout, max(1, wall_cap - self.derived_llm_seconds), retry_left))),
                                          "derived scenario review (retry)", system=REVIEW_SYSTEM,
                                          spec_chars=len(prompt))
                self.derived_llm_seconds += time.monotonic() - started
                (review_dir / f"batch-{batch_number}-retry.txt").write_text(
                    f"# ok={ok}\n# rejected={[r['title'] for r in retryable]}\n{text}", encoding="utf-8")
                if ok:
                    fixed, dropped_again = compile_review_reply(text, chunk, fixtures)
                    for node_id, tests in fixed.items():
                        scripts.setdefault(node_id, []).extend(tests)
                    fixed_titles = {t.split("test('", 1)[1].split(" [model]")[0] for ts in fixed.values() for t in ts}
                    fixed_titles = {re.sub(r" \[case [1-8]\]$", "", title) for title in fixed_titles}
                    dropped = [d for d in dropped if not any(d.startswith(title + ": ") for title in fixed_titles)] + dropped_again
            dropped_total += dropped
            accepted_titles: set[str] = set()
            for node_id, tests in scripts.items():
                rel = f"{node_id}.spec.ts"
                path = directory / rel
                current = path.read_text(encoding="utf-8") if path.exists() else ""
                updated = append_tests(current, tests, node_id)
                if updated == current:
                    continue
                path.write_text(updated, encoding="utf-8")
                self.derived_spec_map.setdefault(node_id, [rel])
                titles_before = set(re.findall(r"^test\('((?:\\.|[^'\\])*)'", current, re.M))
                titles_after = set(re.findall(r"^test\('((?:\\.|[^'\\])*)'", updated, re.M))
                new_titles = {title.replace("\\'", "'") for title in titles_after - titles_before}
                accepted_titles.update(new_titles)
                added += sum(title.endswith(" [model]") for title in new_titles)
            for target in chunk:
                if (f"{target['title']} [model]" in accepted_titles
                        or any(re.fullmatch(re.escape(target['title']) + r" \[case [1-8]\] \[model\]", title)
                               for title in accepted_titles)):
                    plan_rows[target["id"]]["status"] = "accepted"
                else:
                    skip = next((item for item in dropped
                                 if item.startswith(target["title"] + ": skipped by the model:")), None)
                    if skip:
                        plan_rows[target["id"]]["status"] = "skipped_unreviewed"
                        plan_rows[target["id"]]["skip_reason"] = skip[:400]
                        plan_rows[target["id"]]["skip_category"] = skip_category(skip)
            plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            report_nodes(chunk, batch_number, "validated")
        for node_id in dict.fromkeys(str(node.get("id")) for node in ordered if str(node.get("id")) in selected):
            coverage = self.derived_scenario_coverage(node_id)
            status = "covered" if coverage["total"] and coverage["covered"] == coverage["total"] else "incomplete"
            log(f"[derived] spec {node_id}: {status}, "
                f"covered={coverage['covered']}/{coverage['total']}; implementation may proceed, "
                "but unverified scenarios cannot pass acceptance")
            self.metric("derived_spec_node", node_id=node_id, phase="ready", status=status,
                        covered=coverage["covered"], total=coverage["total"])
        planned_features = {row["node_id"] for row in plan["targets"] if row["status"] == "accepted"}
        self.derived_augmented_nodes.update(planned_features & selected)
        self.metric("derived_spec_plan", features=len({row["node_id"] for row in plan["targets"]}),
                    accepted_features=len(planned_features), accepted_tests=added,
                    pending=sum(row["status"] == "pending" for row in plan["targets"]))
        log(f"[derived] model review: {added} validated script(s) added for {len(targets)} planned scenario(s); "
            f"{len(dropped_total)} proposal(s) rejected")
        self.metric("derived_model_review", added=added, targets=len(targets), rejected=len(dropped_total),
                    rejected_reasons=dropped_total[:12])
        return added

    def review_derived_cases(self, node_ids: set[str]) -> None:
        """Review generated cases before application behavior can bias the review.

        Every case gets a versioned deterministic record. A separate, read-only
        model turn may approve behavioral cases with exact requirement and
        assertion witnesses. Budget exhaustion leaves cases unreviewed; it
        never delays implementation or converts a missing oracle into a pass.
        """
        directory = getattr(self, "derived_tests_dir", None)
        if directory is None or not node_ids:
            return
        targets = self.planned_derived_scenarios()
        rows = collect_cases(directory, targets, node_ids,
                             ancestor_context(getattr(self, "requirement_tree", None)))
        helper = directory / "helpers.ts"
        helper_hash = case_sha(helper.read_text(encoding="utf-8")) if helper.is_file() else ""
        fixtures_text = str(suite_fixtures(getattr(self, "derived_nodes", [])))
        fixture_hash = case_sha(fixtures_text)
        for row in rows:
            row["helper_hash"] = helper_hash
            row["fixture_hash"] = fixture_hash
        review_dir = directory / "review"
        review_dir.mkdir(parents=True, exist_ok=True)
        plan_path = review_dir / "plan.json"
        if plan_path.is_file():
            try:
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                plan = {}
            for target in targets:
                if target["node_id"] not in node_ids:
                    continue
                entry = next((item for item in plan.get("targets", []) if item.get("id") == target["id"]), None)
                if entry and entry.get("status") == "skipped_unreviewed":
                    rows.append({"id": case_sha([target["node_id"], target["id"], "skip"])[:24],
                                 "node_id": target["node_id"], "scenario_id": target["id"],
                                 "title": target["title"] + " [skip]", "file": "",
                                 "requirements_hash": case_sha(target), "file_hash": "",
                                 "case_hash": "", "helper_hash": helper_hash, "fixture_hash": fixture_hash,
                                 "status": "skipped_unreviewed", "requirement": str(target.get("description") or ""),
                                 "case": str(entry.get("skip_reason") or ""),
                                 "skip_category": entry.get("skip_category") or skip_category(entry.get("skip_reason") or "")})
        candidates = [row for row in rows if row["status"] in {"unreviewed", "skipped_unreviewed"}]
        phase_plan = getattr(self, "phase_plan", None) or {}
        leaf_phase = phase_plan.get("leaf_phase", {})
        phase_order = [phase["id"] for phase in phase_plan.get("phases", [])]
        phase_counts = getattr(self, "derived_case_review_phase_requests", {})
        self.derived_case_review_phase_requests = phase_counts
        def phase_of(row):
            return leaf_phase.get(row["node_id"], row["node_id"])
        candidates.sort(key=lambda row: (phase_order.index(phase_of(row)) if phase_of(row) in phase_order else len(phase_order),
                                         not bool(re.search(r"sign.?in|sign.?out|password|permission|delete|persist|access", row["requirement"], re.I)),
                                         row["node_id"], row["title"]))
        spent = getattr(self, "derived_case_review_requests", 0)
        cap = max(0, int(os.environ.get("OCTOS_ARC_DERIVED_CASE_REVIEW_REQUESTS", "6")))
        batch_size = max(1, min(6, int(os.environ.get("OCTOS_ARC_DERIVED_CASE_REVIEW_BATCH", "4"))))
        wall_cap = max(0, int(os.environ.get("OCTOS_ARC_DERIVED_CASE_REVIEW_WALL_SECONDS", "300")))
        review_started = time.monotonic()
        chunks = []
        for row in candidates:
            if not chunks or len(chunks[-1]) >= batch_size or phase_of(chunks[-1][0]) != phase_of(row):
                chunks.append([])
            chunks[-1].append(row)
        for chunk in chunks:
            preflight_left = getattr(self, "derived_preflight_deadline", float("inf")) - time.monotonic()
            if (spent >= cap or time.monotonic() - review_started >= wall_cap
                    or self.wound_down() or self.review_budget_spent()
                    or preflight_left < 30 or self.derived_preflight_tokens_spent()
                    or self.remaining() < self.final_phase_reserve() + 300
                    or os.environ.get("OCTOS_ARC_DRYRUN") == "1"):
                break
            current_phase = phase_of(chunk[0])
            future_reserve = sum(phase != current_phase and not phase_counts.get(phase, 0)
                                 for phase in phase_order)
            if not review_request_admissible(current_phase, phase_order, phase_counts, spent, cap):
                self.metric("derived_case_review", outcome="phase_reserved", phase=current_phase,
                            requests=spent, reserved=future_reserve)
                continue
            shown = [{"id": row["id"], "requirement": row["requirement"][:3000],
                      "case": row["case"][:4500], "kind": "skip" if row["status"] == "skipped_unreviewed" else "test"}
                     for row in chunk]
            prompt = ("Independently audit each generated Playwright case against its authoritative requirement. "
                      "You have no application code or test results. Check GIVEN setup, identity, WHEN action order, "
                      "THEN oracle, opposite branches and case isolation. Do not approve a reach/entry-only check "
                      "as behavioral. A skip must be justified by an impossible fixture, not a difficult assertion. "
                      "Return ONLY a JSON array, one item per id: {id,status,requirement_quote,test_quote,reason}. "
                      "status is approved_behavior, approved_smoke_only, needs_correction, disputed, or "
                      "skipped_with_reason. Quotes must be verbatim. requirement_quote must come from the "
                      "leaf description or a THEN step, not GIVEN/WHEN; test_quote must be an assertion that "
                      "proves that outcome. Do not approve entry-only checks.\n"
                      + "\nAuthoritative seed fixtures: " + fixtures_text[:3000]
                      + "\nShared test helper: " + (helper.read_text(encoding="utf-8")[:3500] if helper.is_file() else "absent")
                      + "\nCases: " + json.dumps(shown, ensure_ascii=False))
            decisions = []
            parse_error = None
            for attempt in range(2):
                preflight_left = getattr(self, "derived_preflight_deadline", float("inf")) - time.monotonic()
                if (spent >= cap or time.monotonic() - review_started >= wall_cap
                        or not review_request_admissible(current_phase, phase_order, phase_counts, spent, cap)
                        or preflight_left < 30 or self.derived_preflight_tokens_spent()
                        or self.wound_down() or self.review_budget_spent()
                        or self.remaining() < self.final_phase_reserve() + 300):
                    break
                spent += 1
                phase_counts[current_phase] = phase_counts.get(current_phase, 0) + 1
                self.derived_case_review_requests = spent
                allowance = max(1, int(min(
                    120, max(1, wall_cap - (time.monotonic() - review_started)),
                    max(1, self.remaining() - self.final_phase_reserve() - 180), preflight_left)))
                review_prompt = prompt if attempt == 0 else prompt + (
                    "\nThe previous reply had an invalid JSON envelope. Return exactly one JSON array "
                    "with no prose and unique IDs; do not change requirements or tests.")
                ok, reply = self.text_turn(review_prompt, allowance,
                                           "derived case independent review" + (" (format retry)" if attempt else ""),
                                           system="You are an independent read-only test auditor. Return valid JSON only.",
                                           spec_chars=len(review_prompt))
                decisions, parse_error = (parse_review_decisions(reply, {row["id"] for row in chunk})
                                          if ok else ([], "unavailable"))
                self.metric("derived_case_review_parse", outcome=parse_error or "parsed", request=spent,
                            cases=len(decisions))
                if parse_error != "format_invalid":
                    break
            by_id = {item.get("id"): item for item in decisions if isinstance(item, dict)} if isinstance(decisions, list) else {}
            for row in chunk:
                decision = by_id.get(row["id"], {})
                if validate_review(row, decision):
                    row["status"] = "approved_behavior"
                    row["outcome_quote"] = decision["requirement_quote"]
                    row["assertion_quote"] = decision["test_quote"]
                elif row["status"] == "skipped_unreviewed":
                    quote = decision.get("requirement_quote")
                    if row.get("skip_category") in {"harness_unsupported", "fixture_unavailable"}:
                        row["status"] = "unverified_gap"
                    elif (decision.get("status") == "skipped_with_reason" and isinstance(quote, str)
                            and len(quote.strip()) >= 12 and quote in row["requirement"]
                            and isinstance(decision.get("reason"), str) and len(decision["reason"]) >= 20):
                        row["status"] = "skipped_with_reason"
                elif decision.get("status") in {"needs_correction", "disputed", "approved_smoke_only"}:
                    row["status"] = decision["status"]
                row["reason"] = str(decision.get("reason") or "review unavailable")[:500]
                row["review_request"] = spent
                self.metric("derived_case_review_decision", case_id=row["id"], status=row["status"],
                            outcome="quote_invalid" if decision.get("status") == "approved_behavior"
                            and row["status"] != "approved_behavior" else row["status"])
        for row in rows:
            self.derived_case_reviews[(row["node_id"], row["title"])] = row
        (review_dir / "cases.json").write_text(json.dumps({"version": 1, "cases": safe_records(
            list(self.derived_case_reviews.values()))},
                                                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.metric("derived_case_review", cases=len(rows), approved=sum(r["status"] == "approved_behavior" for r in rows),
                    unreviewed=sum(r["status"] in {"unreviewed", "skipped_unreviewed", "unverified_gap"} for r in rows),
                    requests=spent)

    def derived_preflight_tokens_spent(self) -> bool:
        cap = getattr(self, "derived_preflight_token_cap", None)
        if cap is None:
            return False
        proxy = getattr(self, "llm_proxy", None)
        used = getattr(proxy, "total_tokens", 0) if proxy is not None else 0
        return used - getattr(self, "derived_preflight_start_tokens", 0) >= cap

    def preflight_derived_specs(self, ordered: list[dict]) -> None:
        """Review generated specs by top-level category, then leave code turns alone.

        The complete deterministic suite already exists. Model augmentation and
        independent audit get a bounded startup window; any unfinished case
        stays unreviewed and cannot withhold source generation.
        """
        if not getattr(self, "derived_as_specs", False):
            return
        phase_plan = getattr(self, "phase_plan", None) or {}
        owners = phase_plan.get("leaf_phase", {})
        groups: dict[str, list[dict]] = {}
        for node in ordered:
            node_id = str(node.get("id"))
            groups.setdefault(owners.get(node_id, node_id), []).append(node)
        ordered_phases = [phase["id"] for phase in phase_plan.get("phases", [])]
        ordered_phases += [phase for phase in groups if phase not in ordered_phases]
        requested = max(0, int(os.environ.get(
            "OCTOS_ARC_DERIVED_PREFLIGHT_SECONDS", str(min(600, int(self.budget * .15))))))
        code_reserve = max(600, int(self.budget * .4))
        allowance = min(requested, max(0, int(self.remaining() - self.final_phase_reserve() - code_reserve)))
        proxy = getattr(self, "llm_proxy", None)
        self.derived_preflight_start_tokens = getattr(proxy, "total_tokens", 0) if proxy is not None else 0
        token_default = min(1_000_000, self.max_total_tokens // 10) if self.max_total_tokens > 0 else 600_000
        token_cap = max(0, int(os.environ.get(
            "OCTOS_ARC_DERIVED_PREFLIGHT_TOKENS", str(token_default))))
        self.derived_preflight_token_cap = token_cap
        self.derived_preflight_deadline = time.monotonic() + allowance
        attempted: list[str] = []
        failed: list[str] = []
        try:
            for phase in ordered_phases:
                if phase not in groups:
                    continue
                if (self.derived_preflight_deadline - time.monotonic() < 30 or self.wound_down()
                        or self.derived_preflight_tokens_spent()
                        or self.remaining() < self.final_phase_reserve() + code_reserve + 30):
                    break
                try:
                    self.prepare_derived_spec_batch(groups[phase])
                except Exception as exc:  # generated tests are never a source-generation gate
                    self.metric("derived_preflight", phase=phase, outcome="unavailable", reason=str(exc)[:300])
                    failed.append(phase)
                attempted.append(phase)
        finally:
            # Later wave/leaf paths still call prepare_derived_spec_batch. They
            # must read the frozen suite instead of reopening paid test turns.
            self.derived_specs_frozen = True
            self.derived_preflight_deadline = float("inf")
            self.derived_preflight_token_cap = None
            self.metric("derived_preflight", attempted=attempted, failed=failed,
                        pending=[phase for phase in ordered_phases if phase in groups and phase not in attempted],
                        decision="frozen_for_code", allowance_seconds=allowance,
                        token_cap=token_cap)
            log(f"[derived] preflight attempted {len(attempted)}/{len(groups)} categories "
                f"({len(failed)} unavailable); "
                "remaining cases stay unreviewed, proceeding with source generation")

    def prepare_derived_spec_batch(self, ordered: list[dict]) -> None:
        """Finish a category's generated specs before the code stage begins."""
        if (getattr(self, "derived_specs_frozen", False)
                or not getattr(self, "derived_as_specs", False) or not ordered
                or not getattr(self, "derived_tests_dir", None)):
            return
        pending = [node for node in ordered if str(node.get("id")) not in
                   getattr(self, "derived_augmented_nodes", set())]
        if not pending:
            return
        ids = [str(node.get("id")) for node in pending]
        log(f"[derived] preparing spec batch for nodes {ids}")
        for node_id in ids:
            self.metric("derived_spec_node", node_id=node_id, phase="batch", status="preparing")
        if (os.environ.get("OCTOS_ARC_DRYRUN") != "1"
                and os.environ.get("OCTOS_ARC_DERIVED_LLM", "1") != "0"):
            try:
                self.augment_derived_tests(pending)
            except Exception as exc:  # missing AI tests never block application generation
                self.metric("derived_spec_generation", outcome="unavailable", reason=str(exc)[:300])
        else:
            self.derived_augmented_nodes.update(ids)
        # The proposal compiler and plan writer above are harness-owned writes.
        # Review uses a separate model turn, whose cleanup restores protected
        # trees; it must see the accepted suite as the new protected baseline.
        self.snapshot_protected()
        try:
            self.review_derived_cases(set(ids))
        except Exception as exc:  # review failures remain unreviewed, never a gate
            self.metric("derived_case_review", outcome="unavailable", reason=str(exc)[:300])
        node_ids = [str(node.get("id")) for node in getattr(self, "derived_nodes", ordered)]
        try:
            self.adopt_derived_specs(node_ids)
        except Exception as exc:
            self.metric("derived_spec_adoption", outcome="unavailable", reason=str(exc)[:300])
        # The generated suite is protected during code turns. Refresh the
        # snapshot only after the harness has accepted this batch's files.
        self.snapshot_protected()
        for node_id in ids:
            coverage = self.derived_scenario_coverage(node_id)
            log(f"[derived] spec batch {node_id}: ready, covered={coverage['covered']}/{coverage['total']}")
            self.metric("derived_spec_node", node_id=node_id, phase="batch", status="ready",
                        covered=coverage["covered"], total=coverage["total"])

    @staticmethod
    def final_check_verdict(ok: bool, text: str):
        """A final check that ran out of time or requests measured nothing."""
        if ok:
            return True
        lowered = str(text or "").lower()
        if any(marker in lowered for marker in ("timed out", "local_turn_budget_exhausted",
                                                 "time allowance exhausted")):
            return None
        return False

    @staticmethod
    def no_spec_node_verdict(node_id: str, rehearsed: bool, final_ok, seed_failures: dict,
                             derived: dict | None = None) -> tuple[bool, str]:
        """Final verdict for a leaf without official specs.

        A missing requirement-declared seed fails only the leaf that declares
        it; the heuristic seed audit must never fail unrelated leaves.
        """
        if not rehearsed or final_ok is False:
            return False, "final check or startup rehearsal failed"
        gaps = seed_failures.get(node_id) or []
        if gaps:
            return False, "requirement-declared initial data still missing: " + "; ".join(gaps[:3])
        result = (derived or {}).get(node_id)
        if result is False:
            return False, "derived scenario checks still failing; official acceptance specs unavailable"
        if result is True:
            return True, "derived scenario checks pass and startup rehearsal completed; official specs unavailable"
        return True, ("derived requirement-contract review and startup rehearsal completed; "
                      "official acceptance specs unavailable")

    def split_oversized_hub(self, rel: str, reason: str) -> bool:
        """One bounded refactor turn: split a hub file by feature, behavior unchanged.

        Why a hub grows: every leaf that touches an area re-emits the area's
        page or route module whole with its additions (v9.0: Repository.jsx 22
        rewrites). Once it exceeds the quoting budget no later leaf can be
        shown it whole, so it is either refused or rewritten blind. The split
        is gated: build errors or a regression of previously passing specs
        restore the tree. Each file is attempted once per run, at most
        OCTOS_ARC_HUB_SPLITS (3) files.
        """
        attempted = getattr(self, "hub_splits_attempted", None)
        if attempted is None:
            attempted = self.hub_splits_attempted = set()
        cap = max(4000, int(os.environ.get("OCTOS_ARC_HUB_SPLIT_CHARS", "24000")))
        limit = max(0, int(os.environ.get("OCTOS_ARC_HUB_SPLITS", "3")))
        path = self.output_dir / rel
        if rel in attempted or len(attempted) >= limit or not path.is_file() or "/shared/" in rel:
            return False
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        if len(text) < cap or len(text) > self.codegen_context_chars() * 0.6:
            return False
        if self.wound_down() or self.remaining() < self.min_repair_seconds + 300:
            return False
        attempted.add(rel)
        index = self.repair_source_index()
        importers = sorted(p for p, deps in index.dependencies.items() if rel in deps)
        quoted = [f"--- {rel} ---\n{text.rstrip()}\n"]
        budget = int(self.codegen_context_chars() * 0.8) - len(text) - 3000
        for importer in importers:
            source = index.sources.get(importer, "")
            if source and len(source) <= budget:
                quoted.append(f"--- {importer} ---\n{source.rstrip()}\n")
                budget -= len(source)
        target = max(2000, cap // 3)
        prompt = (stack_note(self.output_dir) +
                  f"Refactor ONLY the module structure ({reason}): {rel} is {len(text)} chars and can no longer be "
                  f"edited safely. Split it into sibling feature modules of at most {target} chars each in the same "
                  f"directory (for example pages/<area>/<Feature>.jsx or routes/<area>-<feature>.js), keeping every "
                  f"exported name, route path, element id, accessible name, text and behavior IDENTICAL. Keep {rel} as "
                  f"a thin module that re-exports or composes the pieces so existing importers keep working, and update "
                  f"the importers shown here only where an import path must change ({', '.join(importers) or 'none'}). "
                  f"Do not add, remove or change features. Return complete <<<FILE>>> blocks for every new and changed "
                  f"file.\nCurrent source files (quoted whole):\n" + "".join(quoted))
        before = self.head()
        self.last_codegen_written = []
        label = f"split {rel} (refactor)"
        timeout = min(900, max(120, int(self.remaining() - self.min_repair_seconds)))
        ok, _ = self.codegen_turn(prompt, timeout, label, spec_chars=0, force_files=True)
        written = list(getattr(self, "last_codegen_written", []) or [])
        if not ok or not written:
            log(f"[flow] hub split of {rel} produced no files; keeping the tree")
            return False
        self._generation_gate_result = None
        self.generation_batch_check(label)
        gate = getattr(self, "_generation_gate_result", None)
        if gate is None:
            # The batch check was skipped (no budget configured): build directly.
            build_error = self.app_server(False).build()
            gate = {"errors": [build_error] if build_error else []}
        errors = list(gate.get("errors") or [])
        regressed = False
        proven = sorted({spec for node, verdict in getattr(self, "test_verdict", {}).items() if verdict is True
                         for spec in (getattr(self, "spec_map", {}) or {}).get(node, [])})
        if not errors and proven and getattr(self, "runner", None) is not None:
            summary = self.run_specs(proven)
            regressed = bool(summary.error) or summary.passed < summary.total or summary.total < len(proven)
        if errors or regressed:
            log(f"[flow] hub split of {rel} rolled back: "
                + (errors[0][:200] if errors else f"{len(proven)} previously passing spec(s) regressed"))
            if before:
                self.restore_app(before)
            self.metric("hub_split", path=rel, outcome="rolled_back", errors=errors[:3], regressed=regressed)
            return False
        self.commit(f"refactor: split {rel} into feature modules")
        self.metric("hub_split", path=rel, outcome="applied", files=written[:12])
        log(f"[flow] hub split of {rel} applied: {len(written)} file(s) written")
        return True

    def whole_app_budgets(self) -> tuple[int, int]:
        """Input and full-source caps for one feature wave.

        Experimental 96k/60k input caps address observed closure omissions.
        Output caps remain independent; provider context is checked by the proxy.
        """
        prompt_cap = min(self.codegen_context_chars(), max(12000, int(os.environ.get(
            "OCTOS_ARC_WHOLE_APP_PROMPT_CHARS", "96000"))))
        source_cap = max(8000, int(os.environ.get("OCTOS_ARC_WHOLE_APP_SOURCE_CHARS", "60000")))
        return prompt_cap, source_cap

    def whole_app_waves(self, tree: dict, ordered: list[dict]) -> bool:
        """Generate contiguous, dependency-ordered feature groups before testing.

        The planner halves a group when its shared prompt exceeds the input
        budget or its reply exceeds the output limit. A single unfittable leaf
        hands control back to the established per-node tool fallback. The
        application design is the common contract across waves. If the model's
        design turn failed, a bounded whole-tree outline supplies that context
        instead. No task- or test-specific code is preloaded.
        """
        self._dependency_tree = tree
        global_context = ""
        if not getattr(self, "app_design_doc", None):
            global_context = ("BACKGROUND ONLY: Whole-tree requirement map. Do not implement inactive leaves; "
                              "reuse names only to preserve shared contracts:\n" + tree_outline(tree, max_chars=12000) + "\n\n")
            log("[flow] whole-app waves: design reply unavailable; using bounded requirement map")
        max_nodes = max(1, int(os.environ.get("OCTOS_ARC_WHOLE_APP_WAVE_NODES", "6")))
        configured_max_nodes = max_nodes
        clean_waves = 0
        max_spec = min(30000, int(self.codegen_context_chars() * 0.35))
        max_details = min(24000, int(self.codegen_context_chars() * 0.25))
        prompt_cap, source_cap = self.whole_app_budgets()
        self._whole_app_prompt_cap = prompt_cap
        parents = {}

        def index_parents(node, parent=None):
            parents[str(node.get("id"))] = parent
            for child in node.get("children") or []:
                index_parents(child, str(node.get("id")))

        index_parents(tree)
        start = 0
        wave = 0
        self.whole_app_generated_ids = set()
        self.whole_app_partial_ids = set()
        self.whole_app_deferred_ids = set()
        self.whole_app_waiting_ids = set()
        self.whole_app_tool_ids = set()
        attempts = 0
        requests_before = getattr(self, "whole_app_generation_requests", 0)
        # Files a reply rewrote without seeing them, per wave position: one
        # refused in two different waves is a shared owner the model keeps
        # extending, so later waves quote it instead of paying a requote.
        refusal_starts: dict[str, set[int]] = {}
        phase_recent_paths: dict[str, list[str]] = {}
        # Files named by a confirmed source-check error stay quoted until a
        # later check clears them; otherwise their fix is refused forever.
        self._wave_error_files = set()
        marked: set[str] = set()
        # Waves pay off only while groups keep landing. A run of leaves that
        # cannot fit or finish goes to node flow (v10.2 sheet: 18 of 24 leaves
        # deferred one by one over 53 minutes).
        max_deferrals = max(1, int(os.environ.get("OCTOS_ARC_WAVE_MAX_DEFERRALS", "3")))
        deferred_run = 0
        repaired_builds: set[str] = set()
        while start < len(ordered):
            if self.remaining() < self.min_repair_seconds + 120 or self.wound_down():
                log("[flow] whole-app waves: insufficient budget; measuring any partial application")
                return wave > 0
            gate = getattr(self, "_generation_gate_result", None)
            gate_errors = list(gate.get("errors") or []) if isinstance(gate, dict) else []
            if wave and gate_errors:
                digest = "\n".join(gate_errors)[:3000]
                if digest in repaired_builds or not self.repair_wave_build(gate_errors):
                    rest = [str(node.get("id")) for node in ordered[start:]]
                    log(f"[flow] whole-app waves: build still failing after a focused repair; handing "
                        f"{len(rest)} remaining leaves to node flow")
                    self.whole_app_deferred_ids.update(rest)
                    break
                repaired_builds.add(digest)
            if deferred_run >= max_deferrals:
                rest = [str(node.get("id")) for node in ordered[start:]]
                log(f"[flow] whole-app waves: {deferred_run} consecutive leaves deferred; handing the "
                    f"remaining {len(rest)} leaves to node flow")
                self.metric("wave_early_stop", deferred_run=deferred_run, remaining=len(rest))
                self.whole_app_deferred_ids.update(rest)
                break
            landed_before = len(self.whole_app_generated_ids)
            start_before = start
            # Files an earlier attempt at this position wrote or had refused:
            # a split or same-wave retry must see them whole, or its rewrite
            # of a file it never saw is refused again.
            carry: set[str] = set()      # written by an earlier attempt here: quote when it fits
            required: set[str] = set()   # refused here: the retry must see it whole
            requoted: set[tuple[str, ...]] = set()
            size = min(max_nodes, len(ordered) - start)
            phase_ids = (getattr(self, "phase_plan", None) or {}).get("leaf_phase", {})
            first_phase = phase_ids.get(str(ordered[start].get("id")))
            if first_phase:
                for offset in range(1, size):
                    if phase_ids.get(str(ordered[start + offset].get("id"))) != first_phase:
                        size = offset
                        break
            if start + size < len(ordered):
                # Prefer a module boundary, without changing dependency order.
                parent = parents.get(str(ordered[start + size]["id"]))
                boundary = size
                while boundary > 0 and parents.get(str(ordered[start + boundary - 1]["id"])) == parent:
                    boundary -= 1
                if boundary:
                    size = boundary
            while size:
                group = ordered[start:start + size]
                ids = [str(node.get("id")) for node in group]
                # Missing or failing prerequisite tests cannot withhold a
                # generation wave. Cross-wave interfaces come from the global
                # and phase contracts; runtime confidence is tracked apart.
                for item in group:
                    unresolved = self.pending_dependencies(item, within=set(ids), wave=True)
                    if unresolved:
                        self.metric("wave_dependency_unverified", node_id=str(item.get("id")),
                                    dependencies=unresolved)
                self.prepare_derived_spec_batch(group)
                spec = self.batch_spec_bodies(ids)
                # The derived contract already carries the full scenarios.
                # Avoid a duplicate copy while keeping official-spec waves
                # paired with their complete requirement semantics.
                details = "\n\n".join(describe_node(node, include_scenarios=bool(self.tests_dir))
                                      for node in group)
                estimated = generation_tokens(group, len(spec))
                if (len(spec) > max_spec or len(details) > max_details
                        or estimated > self.generation_output_budget()) and size > 1:
                    size = max(1, size // 2)
                    continue
                combined = {"id": f"application wave {wave + 1}",
                            "description": "ACTIVE REQUIREMENT IDs: " + ", ".join(ids) +
                                           ". Implement only these active contracts as one coherent group. "
                                           "Reuse required shared dependencies; do not implement other leaves in the background map. "
                                           "Preserve existing routes, state and module owners. Every changed file must serve "
                                           "an active contract or its necessary shared dependency.\n\nACTIVE DETAILS:\n" + details +
                                           "\n\n" + global_context}
                # Hot files are preferred, never required: the set only grows,
                # and requiring it collapsed every later wave (v7.18 d629f86de409).
                hot = {rel for rel, starts in refusal_starts.items() if len(starts) >= 2}
                required_now = {rel for rel in required | self._wave_error_files
                                if (self.output_dir / rel).is_file()}
                targets = set(self.whole_app_wave_targets(ids, spec, details))
                targets |= {rel for rel in carry | hot if (self.output_dir / rel).is_file()} | required_now
                required_targets = set(targets)
                # Recent files in this top-level category are the most likely
                # shared owners of the next leaf, even when a templated
                # scenario has no useful filename terms. Cap the extra context.
                recent_room = 24000
                for rel in reversed(phase_recent_paths.get(first_phase, [])):
                    path = self.output_dir / rel
                    if rel in targets or not path.is_file():
                        continue
                    size_chars = path.stat().st_size
                    if size_chars <= recent_room:
                        targets.add(rel)
                        recent_room -= size_chars
                relationships = ""
                if targets:
                    relationships = ("\nCurrent wave dependency/interface map. Files outside the exact target "
                                     "closure are listed but must remain unchanged:\n" +
                                     self.repair_source_index().render(targets, limit=4000) + "\n")
                prompt = self.codegen_implement_prompt(
                    combined, spec, evidence=relationships, must_include=required_targets,
                    context_limit=prompt_cap, source_limit=source_cap, focused_sources=True)
                if (prompt is None and size == 1 and os.environ.get("OCTOS_ARC_ADAPTIVE_WAVE_CONTEXT") == "1"):
                    proxy = getattr(self, "llm_proxy", None)
                    capacities = getattr(proxy, "model_contexts", {})
                    # A route can change after tools/history are serialized. Require
                    # declared capacities for every eligible route, plus fallback.
                    declared = [r.get("model") for r in getattr(proxy, "routes", [])
                                if "implement" in r.get("phases", ["implement", "repair", "verify", "design"])]
                    fallback = os.environ.get("OPENAI_MODEL")
                    declared.append(fallback)
                    if declared and all(model in capacities for model in declared):
                        capacity = min(capacities[model] for model in declared)
                        for enlarged_prompt, enlarged_source in ((128000, 80000), (192000, 128000)):
                            if enlarged_prompt <= prompt_cap or enlarged_prompt + 32768 > capacity * .85:
                                continue
                            prompt = self.codegen_implement_prompt(
                                combined, spec, evidence=relationships, must_include=required_targets,
                                context_limit=enlarged_prompt, source_limit=enlarged_source, focused_sources=True)
                            if prompt is not None:
                                prompt_cap, source_cap = enlarged_prompt, enlarged_source
                                self._whole_app_prompt_cap = prompt_cap
                                self.metric("wave_context_growth", node_ids=ids, prompt_cap=prompt_cap,
                                            source_cap=source_cap, declared_capacity=capacity)
                                break
                if prompt is None:
                    if size > 1:
                        log(f"[flow] whole-app wave {wave + 1}: focused source closure for {ids} "
                            f"did not fit {prompt_cap}/{source_cap} prompt/source chars; splitting group")
                        max_nodes = min(max_nodes, (size + 1) // 2)
                        size = max(1, size // 2)
                        continue
                    # Last resort before giving the leaf to node flow: a hub file
                    # too large for any budget is split once, then the leaf retried.
                    blocking = self.codegen_budget.get("missing_required") or []
                    largest = max(blocking, key=lambda p: (self.output_dir / p).stat().st_size
                                  if (self.output_dir / p).is_file() else 0, default=None)
                    if largest and self.split_oversized_hub(largest, f"closure of {ids[0]} did not fit"):
                        continue
                    log(f"[flow] whole-app waves: {ids[0]} cannot fit its focused source closure; using node flow")
                    self.whole_app_deferred_ids.update(ids)
                    self.whole_app_tool_ids.update(ids)
                    start += size
                    break
                # A previously refused file is now shown whole. Do not carry it
                # into unrelated later waves unless this response refuses it again.
                self.refused_paths.difference_update(quoted_paths(prompt))
                write_codegen_manifests(self.output_dir)
                timeout = min(int(os.environ.get("OCTOS_ARC_WHOLE_APP_TIMEOUT", "1800")),
                              max(120, self.remaining() - self.min_repair_seconds))
                log(f"[flow] whole-app wave {wave + 1}: generating {ids} "
                    f"({len(prompt)} prompt chars, {len(spec)} spec chars, {len(targets)} focused sources, "
                    f"{self.codegen_budget.get('quoted_sources', '?')} quoted / "
                    f"{self.codegen_budget.get('source_block', '?')} source chars, "
                    f"estimated output {estimated}/{self.generation_output_budget()} tokens)")
                self.metric("wave_prompt", wave=wave + 1, node_ids=ids, prompt_chars=len(prompt),
                            spec_chars=len(spec), focused_sources=len(targets),
                            quoted_sources=self.codegen_budget.get("quoted_sources"),
                            source_chars=self.codegen_budget.get("source_block"),
                            prompt_cap=prompt_cap, source_cap=source_cap)
                attempts += 1
                for node_id in ids:
                    if node_id not in marked:
                        marked.add(node_id)
                        if node_id not in getattr(self, "_designed_ids", set()):
                            self.mark("design_started", node_id)
                            self.mark("design_done", node_id, "covered by whole-application design")
                        self.mark("implementation_started", node_id, f"whole-app wave {wave + 1}")
                self._generation_gate_result = None
                before_wave = self.head()
                ok, text = self.whole_app_generation_turn(prompt, timeout,
                                                          f"whole application wave {wave + 1}",
                                                          spec_chars=len(spec))
                hard_incomplete = (getattr(self, "last_codegen_outcome", "") == "tool_incomplete"
                                   or "local_turn_budget_exhausted" in text)
                if (hard_incomplete and getattr(self, "last_codegen_written", [])
                        and not self.retain_safe_no_spec_partial(", ".join(ids))):
                    # A capped multi-request edit without a clean early gate is
                    # not a usable feature result. Roll back only this group;
                    # later feature groups keep their wave.
                    self.restore_app(before_wave)
                    self.last_codegen_written = []
                    self.last_codegen_no_change = False
                    self.metric("wave_failover", wave=wave + 1, reason="hard_incomplete", node_ids=ids)
                    if size > 1:
                        log(f"[flow] whole-app wave {wave + 1}: capped structured edit rolled back; "
                            "splitting the group")
                        max_nodes = min(max_nodes, (size + 1) // 2)
                        size = max(1, size // 2)
                        continue
                    log(f"[flow] whole-app wave {wave + 1}: capped structured edit rolled back; "
                        f"deferring {ids[0]} to targeted node flow")
                    self.whole_app_deferred_ids.update(ids)
                    self.whole_app_tool_ids.update(ids)
                    start += size
                    break
                gate = getattr(self, "_generation_gate_result", None)
                if self.runtime is not None and isinstance(gate, dict) and gate.get("errors") and getattr(self, "last_codegen_written", []):
                    self.restore_app(before_wave)
                    self.last_codegen_written = []
                    self.last_codegen_no_change = False
                    ok = False
                    self.metric("wave_rollback", node_ids=ids, errors=gate["errors"][:6])
                carry |= set(getattr(self, "last_codegen_written", ()) or ())
                if first_phase and getattr(self, "last_codegen_written", None):
                    recent = phase_recent_paths.setdefault(first_phase, [])
                    for rel in self.last_codegen_written:
                        if rel in recent:
                            recent.remove(rel)
                        recent.append(rel)
                    del recent[:-12]
                gate = getattr(self, "_generation_gate_result", None)
                if isinstance(gate, dict):
                    self._wave_error_files = {
                        match.group(1) for error in gate.get("errors") or []
                        if (match := re.match(r"\s*([\w@./-]+\.[A-Za-z0-9]+):", str(error)))}
                for rel in getattr(self, "last_codegen_refused", ()) or ():
                    refusal_starts.setdefault(rel, set()).add(start)
                applied = bool(getattr(self, "last_codegen_written", [])
                               or getattr(self, "last_codegen_no_change", False) is True)
                gaps = self.whole_app_wave_gaps(ids) if applied else []
                complete = ok and applied and not gaps
                if not complete:
                    clean_waves = 0
                    if gaps:
                        digest = "; ".join(gaps[:6])
                        self.pending_corrections.append(
                            f"Wave {', '.join(ids)} was retained but is not complete: {digest}. "
                            "Finish only these missing contracts against the current files.")
                        self._generation_gate_evidence = (
                            "Wave completion guard (must resolve before declaring these requirements complete):\n" +
                            "\n".join(gaps[:8]))[:4000]
                        log(f"[flow] whole-app wave {wave + 1}: completion guard found "
                            f"{len(gaps)} gap(s): {digest[:1000]}")
                    if getattr(self, "last_codegen_written", []):
                        self.commit(f"whole application wave {wave + 1} (partial; requires verification)")
                    refused_now = set(getattr(self, "last_codegen_refused", ()) or ())
                    if refused_now and tuple(ids) not in requoted:
                        # The reply needed existing files it was not shown.
                        # Quote them whole and ask again now, while the
                        # feature context is hot, instead of a later repair.
                        requoted.add(tuple(ids))
                        required |= refused_now
                        self.metric("wave_requote", wave=wave + 1, node_ids=ids, paths=sorted(refused_now))
                        log(f"[flow] whole-app wave {wave + 1}: requoting {', '.join(sorted(refused_now))} "
                            "whole for one same-wave retry")
                        continue
                    if size > 1:
                        log(f"[flow] whole-app wave {wave + 1}: incomplete group retained where safe; "
                            "splitting requirements and checking each leaf against the current files")
                        max_nodes = min(max_nodes, (size + 1) // 2)
                        size = max(1, size // 2)
                        continue
                    if getattr(self, "last_codegen_written", []):
                        self.whole_app_partial_ids.update(ids)
                        wave += 1
                        log(f"[flow] partial single-leaf wave retained for {ids}; targeted node repair remains pending")
                    else:
                        log(f"[flow] whole-app wave {wave + 1}: no complete write ({text[-120:]})")
                    log(f"[flow] whole-app wave {wave + 1}: deferring {ids[0]} to targeted repair; "
                        "continuing remaining feature groups")
                    self.whole_app_deferred_ids.update(ids)
                    self.whole_app_tool_ids.update(ids)
                    start += size
                    break
                if (getattr(self, "runner", None) is not None and self.runtime is not None
                        and (not getattr(self, "derived_as_specs", False)
                             or os.environ.get("OCTOS_ARC_WAVE_DERIVED_TESTS", "0") == "1")
                        and self.remaining() > self.final_phase_reserve() + 180):
                    own_specs = sorted({p for nid in ids for p in self.spec_map.get(nid, [])})
                    affected = self.affected_regression_specs(set(getattr(self, "last_codegen_written", [])), own_specs)
                    gate_specs = sorted(set(own_specs + affected))
                    if gate_specs:
                        measured = self.run_specs(gate_specs)
                        self.record_full_suite(measured, {}, scope=gate_specs)
                        active = self.uncontested_derived_results(measured)
                        self.metric("wave_behavior_gate", node_ids=ids, passed=active.passed,
                                    total=active.total, quarantined=len(measured.results) - len(active.results))
                        if not active.all_passed or not self.suite_is_measured(measured, gate_specs):
                            self.metric("wave_behavior_risk", node_ids=ids, decision="continue_generation")
                            log("[flow] wave behavior incomplete; recording risk and continuing later feature groups")
                self.commit(f"whole application wave {wave + 1} (experimental implement)")
                self.whole_app_generated_ids.update(ids)
                for node_id in ids:
                    self.mark("implementation_done", node_id,
                              f"implemented by whole-app wave {wave + 1}; verification pending")
                clean_waves += 1
                if clean_waves >= 2:
                    max_nodes = min(configured_max_nodes, max_nodes * 2)
                    clean_waves = 0
                start += size
                wave += 1
                break
            if start != start_before:
                deferred_run = 0 if len(self.whole_app_generated_ids) > landed_before else deferred_run + 1
        log(f"[flow] whole-app waves: {len(self.whole_app_generated_ids)} source-written, "
            f"{len(self.whole_app_partial_ids)} partial, {len(self.whole_app_deferred_ids)} deferred leaves "
            f"in {wave} applied waves "
            f"({attempts} group attempts, "
            f"{getattr(self, 'whole_app_generation_requests', 0) - requests_before} model turns); "
            "measurement follows the trust and budget policy")
        return wave > 0

    def pending_dependencies(self, node: dict, *, within: set[str] | None = None, wave: bool = False) -> list[str]:
        """Declared dependencies lacking a passing verdict, for context only.

        The result must never decide whether source generation is admitted.
        A cycle can be co-constructed without pretending its tests passed.
        """
        within = within or set()
        pending = []
        tree = getattr(self, "_dependency_tree", None) or getattr(self, "requirement_tree", None)
        cyclic = set()
        if tree:
            from requirement_order import dependency_graph, dependency_signature, cyclic_dependency_ids
            signature = dependency_signature(tree)
            cached = getattr(self, "_dependency_graph_cache", None)
            if cached is None or cached[0] != signature:
                cached = (signature, dependency_graph(tree), {})
                self._dependency_graph_cache = cached
            graph, cycles = cached[1:]
            dependencies = list(graph.get(str(node.get("id")), []))
            nid = str(node.get("id"))
            if nid not in cycles:
                cycles[nid] = cyclic_dependency_ids(tree, node, graph=graph)
            cyclic = cycles[nid]
            if cyclic:
                for nid in sorted(cyclic):
                    for external in graph[nid]:
                        if external != str(node.get("id")) and external not in dependencies:
                            dependencies.append(external)
        else:
            dependencies = [str(dep) for dep in node.get("dependencies") or [] if str(dep) != str(node.get("id"))]
        if cyclic:
            signature = (str(node.get("id")), tuple(sorted(cyclic)))
            reported = getattr(self, "_reported_dependency_cycles", set())
            if signature not in reported:
                self.metric("dependency_cycle", node_id=signature[0], jointly_constructed_dependencies=sorted(cyclic),
                            verification="combined_measurement_required")
                self._reported_dependency_cycles = reported | {signature}
        for dependency in dependencies:
            nid = str(dependency)
            if nid in cyclic:
                # Permit construction of mutually dependent contracts. This is
                # never a verification verdict; the combined suite still gates
                # every member after the group has been built.
                continue
            if nid in within:
                continue
            incomplete = nid in getattr(self, "whole_app_deferred_ids", set())
            verdict = getattr(self, "test_verdict", {}).get(nid)
            if verdict is True and not incomplete:
                continue
            if (wave and not incomplete and (getattr(self, "runner", None) is None or getattr(self, "runtime", None) is None)
                    and nid in getattr(self, "whole_app_generated_ids", set())):
                # Generation-only mode can compose code; it cannot claim verification.
                continue
            pending.append(nid)
        return pending

    def admit_node(self, node: dict, *, within: set[str] | None = None, wave: bool = False) -> bool:
        """Always admit source generation; record unresolved prerequisites."""
        node_id = str(node.get("id"))
        blocked = self.pending_dependencies(node, within=within, wave=wave)
        if blocked:
            self.metric("implementation_dependency_unverified", node_id=node_id,
                        dependencies=blocked, decision="admitted")
        getattr(self, "whole_app_deferred_ids", set()).discard(node_id)
        return True

    def implement_sequential(self, tree: dict, ordered: list[dict], unchanged: set[str]) -> None:
        """Keep the dependency-ordered queue alive across bounded startup recovery."""
        self._dependency_tree = tree
        batch_size = int(os.environ.get("OCTOS_ARC_SIBLING_BATCH_SIZE", "1"))
        batch_starts = {group[0]: group for group in sibling_batches(tree, ordered, batch_size)}
        preimplemented: set[str] = set()
        for index, node in enumerate(ordered, 1):
            node_id = str(node.get("id"))
            proxy = getattr(self, 'llm_proxy', None)
            if isinstance(proxy, LlmProxy) and proxy.provider_unavailable:
                allowance = max(0, min(90, self.remaining() - self.final_phase_reserve()))
                until = time.monotonic() + allowance
                while proxy.provider_unavailable and time.monotonic() < until:
                    if proxy.probe_provider(timeout=min(10, max(1, until - time.monotonic()))):
                        log('[proxy] upstream recovered; resuming node queue')
                        break
                    log('[proxy] upstream unavailable; leaving new nodes pending while probing /models')
                    time.sleep(min(15, max(0, until - time.monotonic())))
                if proxy.provider_unavailable:
                    self.metric('provider_circuit', decision='defer', after_nodes=index - 1,
                                pending_nodes=[str(n.get('id')) for n in ordered[index - 1:]])
                    break
            if self.final_phase_due():
                self.metric("final_phase_reserve_reassigned", node_id=node_id,
                            remaining_seconds=round(self.remaining(), 3),
                            decision="continue_generation")
            if self.time_up():
                log(f"[flow] time budget exhausted; skipping {node_id}")
                self.mark("implementation_started", node_id)
                self.mark("implementation_failed", node_id, "skipped: time budget exhausted")
                self.impl_failed.append(node_id)
                continue
            self.admit_node(node)
            group = batch_starts.get(node_id)
            group_nodes = ([ordered[index - 1 + offset] for offset in range(len(group))]
                           if group and not any(member in unchanged for member in group) else [node])
            self.prepare_derived_spec_batch(group_nodes)
            if node_id in unchanged:
                self.regression_cycle(node)
            else:
                if group and not any(member in unchanged for member in group):
                    if self.batch_codegen(group_nodes):
                        preimplemented.update(group)
                self.node_cycle(node, ordered, index, len(ordered),
                                preimplemented=node_id in preimplemented)
            if getattr(self, '_unresolved_startup_error', ''):
                self.driver.end_scope("node")
                if (self.recover_sequential_startup(node_id)
                        or self.recover_deferred_startup(node_id)):
                    self.regression_checkpoint(index, len(ordered))
                    self.driver.end_scope("node")
                    continue
                log("[flow] startup still broken after bounded recovery; continuing source generation offline")
                self.metric("startup_risk", reason="unresolved_startup", after_node=node_id,
                            remaining_nodes=[str(n.get('id')) for n in ordered[index:]],
                            decision="continue_generation")
                self.driver.end_scope("node")
                continue
            if not (isinstance(proxy, LlmProxy) and proxy.provider_unavailable):
                self.regression_checkpoint(index, len(ordered))
            self.driver.end_scope("node")

        # Dependency verdicts never create a waiting subqueue. Only hard time
        # or provider unavailability may leave a node unattempted.

    def recover_sequential_startup(self, node_id: str) -> bool:
        """Repair infrastructure locally, measure the active node, then resume.

        No full-suite repair of unimplemented features. Functional assertion
        failures do not block further implementation; incomplete/load verdicts do.
        """
        specs = self.spec_map.get(node_id, [])
        if not specs or self.runner is None:
            return False
        for attempt in range(2):
            error = getattr(self, '_unresolved_startup_error', '')
            if not error:
                return True
            if not self.whole_app_startup_repair(error):
                break
            if self.time_up() or self.remaining() < 30:
                break
            summary = self.run_specs(specs)
            complete = self.suite_is_measured(summary, specs)
            self.metric('startup_recovery', node_id=node_id, attempt=attempt + 1,
                        resumed=complete, passed=summary.passed, total=summary.total,
                        error=summary.error, load_errors=summary.load_errors)
            if complete:
                self._unresolved_startup_error = ''
                self.record_tests(node_id, specs, summary)
                self.test_verdict[node_id] = (None if summary.all_passed and self.derived_review_needed(node_id)
                                              else summary.passed == summary.total)
                log(f"[flow] startup recovered at {node_id}; resuming remaining requirements")
                return True
            self._unresolved_startup_error = summary.error or '\n'.join(summary.load_errors) or 'Incomplete startup recovery verdict'
        return False

    def whole_app_startup_repair(self, error: str) -> bool:
        """Fix one concrete build/start failure without reimplementing all nodes."""
        reserve = self.final_measurement_reserve()
        if self.remaining() < self.repair_minimum() + reserve or self.wound_down():
            return False
        deadline = time.monotonic() + min(self.node_timeout, 360, max(0, self.remaining() - reserve))
        self.last_codegen_written = []
        digest = startup_error_digest(error, 2200)
        names = list(dict.fromkeys(re.findall(
            r"(?:frontend|backend)/[A-Za-z0-9_./-]+\.(?:jsx?|tsx?|[cm][jt]s|vue|s?css|html|json)\b", error)))
        # Vite usually reports paths relative to frontend, not the app root.
        names.extend("frontend/" + path for path in re.findall(
            r"(?<![\w/])(?:src/[A-Za-z0-9_./-]+\.(?:[jt]sx?|[cm][jt]s|vue|s?css)|vite\.config\.[cm]?[jt]s)\b", error))
        names = list(dict.fromkeys(names))
        index = self.repair_source_index()
        names.extend(sorted({dependency for name in names for dependency in index.dependencies.get(name, ())
                             if dependency.startswith('backend/lib/')} - set(names)))
        if not names:
            if "client-side links" in error or "pushState" in error:
                names = ["frontend/package.json", "frontend/src/index.html", "frontend/src/app.js"]
            else:
                names = ["backend/server.js", "backend/package.json", "frontend/package.json"]
        sources = []
        for raw in names[:4]:
            rel = safe_relative_path(raw)
            if rel is None or not rel.startswith(("frontend/", "backend/")):
                continue
            path = self.output_dir / rel
            try:
                if path.resolve().is_relative_to(self.output_dir.resolve()) and path.is_file() \
                        and path.stat().st_size <= 50000:
                    sources.append(f"--- {rel} ---\n{path.read_text(encoding='utf-8', errors='replace')}\n")
            except OSError:
                continue
        prompt = (stack_note(self.output_dir) + "The generated application failed its build/start preflight. Fix ONLY this concrete error; "
                  "preserve every implemented feature. For a literal route shadowed by a :parameter route "
                  "of the same method, register the literal handler first; for a duplicate route keep one handler "
                  "in the file that registers it first and never stub out a route file. Do not rewrite unrelated files.\n"
                  f"Error:\n{digest}\nCurrent source files (quoted whole):\n{''.join(sources)}")
        if sources and len(prompt) + len(FORMAT_INSTRUCTIONS) + 1 <= self.codegen_context_chars():
            ok, _ = self.whole_app_generation_turn(prompt, max(0, deadline - time.monotonic()),
                                                    "whole application startup repair", spec_chars=0)
            if ok and getattr(self, "last_codegen_written", []):
                self.commit("fix: whole application startup preflight")
                return True
        # A failed file-block response is not a reason to revisit every leaf.
        # Give tool mode only this startup error and the small implicated source.
        tool_prompt = ("Fix the application's build/start error below with a focused source edit. "
                       "Preserve existing features and do not run the full test suite; the harness will.\n"
                       f"Error:\n{digest}\n{''.join(sources) or source_listing(self.output_dir)}")
        left = deadline - time.monotonic()
        if left <= 0 or self.wound_down():
            return bool(getattr(self, "last_codegen_written", []))
        self.last_turn_changed = None
        self.turn(tool_prompt, left, "whole application startup repair (tools)")
        committed = self.commit("fix: whole application startup preflight (tools)")
        return self.last_turn_changed if isinstance(self.last_turn_changed, bool) else committed

    def recover_deferred_startup(self, node_id: str) -> bool:
        """Recheck build/start only; incomplete feature tests cannot gate source."""
        if self.time_up():
            return False
        server = self.app_server(grader_like=True, test_hooks=False)
        error = server.build() or server.start()
        server.stop()
        recovered = error is None
        if recovered:
            self._unresolved_startup_error = ''
        self.metric('startup_recovery', node_id=node_id, strategy='build_start', resumed=recovered,
                    error=(str(error)[:300] if error else None))
        if recovered:
            log(f"[flow] build/start recovered at {node_id}; resuming remaining requirements")
        return recovered

    def whole_app_first_suite(self, ordered: list[dict]) -> set[str] | None:
        """Measure the generated app once; return only leaves needing repair.

        None means the suite could not give a reliable verdict. No test is skipped on
        the strength of a model's claim that the whole app is complete.
        """
        self.whole_app_summary = None
        if self.runner is None or not self.tests_dir:
            return None
        specs = sorted(str(path.relative_to(self.tests_dir)) for path in self.tests_dir.rglob("*.spec.ts"))
        workers = workers_for_final(getattr(self, "mem_limit", None),
                                    self.final_workers())
        issues = scaffold_issues(self.output_dir)
        attempted_errors = set()
        if issues:
            preflight = "generic scaffold checks failed:\n" + "\n".join(issues[:8])
            attempted_errors.add(preflight)
            self.whole_app_startup_repair(preflight)
        measurement = 0
        def measure():
            nonlocal measurement
            observed = self.run_specs(specs, workers=workers, grader_like=True)
            self.metric("acceptance", scope="whole_app", round=measurement,
                        passed=observed.passed, total=observed.total,
                        error=observed.error, killed=observed.killed,
                        generated_leaves=len(getattr(self, "whole_app_generated_ids", ())),
                        partial_leaves=len(getattr(self, "whole_app_partial_ids", ())),
                        deferred_leaves=len(getattr(self, "whole_app_deferred_ids", ())))
            measurement += 1
            return observed
        summary = measure()
        while summary.error and summary.killed and workers > 1:
            workers = max(1, workers // 2)
            log(f"[flow] whole-app first suite: runner killed; retrying with {workers} worker(s)")
            summary = measure()
        for attempt in range(2):
            if (not summary.error or summary.killed or summary.error in attempted_errors
                    or summary.error.startswith("generated test load blocked:")):
                break
            attempted_errors.add(summary.error)
            if not self.whole_app_startup_repair(summary.error):
                break
            log(f"[flow] whole-app first suite: repaired startup failure {attempt + 1}/2; retrying full suite")
            summary = measure()
        if getattr(self, "derived_as_specs", False):
            summary = self.audit_related_derived_specs(specs, summary)
        observed_files = {Path(result.file or "").name for result in summary.results}
        if (summary.error or summary.load_errors or not summary.results or summary.total != len(summary.results)
                or any(Path(spec).name not in observed_files for spec in specs)):
            log(f"[flow] whole-app first suite: no reliable verdict "
                f"({(summary.error or 'incomplete results')[:150]}); preserving app for final repair")
            return None
        grouped = nodes_for_failures(self.uncontested_derived_results(summary).results, self.spec_map)
        if self.disputed_generated_failures(summary):
            log("[flow] whole-app first suite: generated oracle disputed; "
                "only uncontested failures enter application repair")
        ids = {str(node.get("id")) for node in ordered}
        if any(node_id not in ids for node_id in grouped):
            log("[flow] whole-app first suite: unmapped failure; using node flow")
            return None
        self.record_full_suite(summary, grouped)
        self.remember_delivery_checkpoint(summary, grouped)
        self.whole_app_summary = summary
        failing = set(grouped)
        log(f"[flow] whole-app first suite: {summary.passed}/{summary.total}; "
            f"repair only {sorted(failing)}")
        return failing

    def whole_app_shared_repair(self, ordered: list[dict], failing: set[str]) -> set[str]:
        """One evidence-driven shared-error repair before per-leaf cycles.

        Identical timeouts/assertions are not sufficient evidence. Always rerun
        the full suite after a real edit and roll back newly broken behaviours.
        """
        summary = getattr(self, "whole_app_summary", None)
        reserve = max(self.final_measurement_reserve(), self.final_phase_reserve())
        if (summary is None or len(failing) < 2 or self.wound_down()
                or self.remaining() < self.repair_minimum() + reserve
                or os.environ.get("OCTOS_ARC_SHARED_REPAIR", "1") == "0"):
            return failing
        grouped = nodes_for_failures(self.uncontested_derived_results(summary).results, self.spec_map)
        clusters: dict[str, set[str]] = {}
        for nid, outcomes in grouped.items():
            for result in outcomes:
                # Keep identifiers/values intact; do not merge all failures of a type.
                diagnostics = "\n".join([result.message, *result.action_errors])
                for line in diagnostics.splitlines():
                    if re.search(r"\b(?:ReferenceError: .+ is not defined|Cannot find module|"
                                 r"ERR_MODULE_NOT_FOUND|SyntaxError:|TypeError:|"
                                 r"Minified React error #\d+|Element type is invalid:)", line):
                        signature = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
                        clusters.setdefault(signature, set()).add(nid)
                        break
        candidates = [ids for ids in clusters.values() if len(ids) >= 2]
        if not candidates:
            return failing
        ids = sorted(max(candidates, key=lambda ids: (len(ids), sorted(ids))))
        relevant = [result for nid in ids for result in grouped[nid]]
        evidence = RunSummary(results=relevant)
        failures = failure_summaries(evidence) + failure_source_context(evidence, self.tests_dir)
        instruction = ("Multiple features report the same concrete runtime error. Inspect their shared cause; "
                       "do not assume every affected feature needs reimplementation. Fix only the demonstrated "
                       "cause, preserve passed behaviour, and do not run tests; the harness verifies all specs.\n")
        before = self.head()
        if not before:
            return failing  # A speculative shared repair needs a rollback point.
        before_sources = self.app_source_digest()
        log(f"[flow] shared runtime-error repair before leaf cycles: {ids}")
        self.suite_repair_turn("shared runtime-error repair", ids, instruction + failures,
                               min(360, self.remaining() - reserve),
                               tool_prompt=instruction + failures + self.repair_test_location()
                               + stack_note(self.output_dir) + "\n".join(self.repair_requirements(nid) for nid in ids))
        if self.app_source_digest() == before_sources:
            return failing  # No source change: do not pay for an identical suite.
        self.commit("fix: shared runtime error before leaf repairs")
        observed = self.whole_app_first_suite(ordered)
        if observed is None or observed - failing:
            self.restore_app(before)
            self.whole_app_summary = summary
            self.record_full_suite(summary, grouped)
            log("[flow] shared repair could not preserve the verified baseline; rolled back")
            return failing
        return observed

    def app_source_digest(self) -> str:
        """Source content, not traceability/log commits, determines effective repair."""
        digest = hashlib.sha256()
        # Include local images/fonts and other inputs: fixing an asset is not a no-op.
        files = app_source_files(self.output_dir, exts=None)
        files += [self.output_dir / part / name for part in ("frontend", "backend") for name in LOCKFILES
                  if (self.output_dir / part / name).is_file()]
        for path in sorted(files):
            digest.update(str(path.relative_to(self.output_dir)).encode())
            digest.update(b"\0")
            with path.open("rb") as fh:
                digest.update(hashlib.file_digest(fh, "sha256").digest())
        return digest.hexdigest()

    def whole_app_experiment(self, tree: dict, ordered: list[dict]) -> bool:
        """Attempt every leaf before broad measurement and bounded repair."""
        if not self.whole_app_codegen(tree, ordered):
            return False
        generated = getattr(self, "whole_app_generated_ids", None)
        if generated is None:
            generated = {str(node.get("id")) for node in ordered}
        attempted_fallback_ids: set[str] = set()
        # A wave can defer leaves because of an output/context limit. Do not
        # pay for a broad suite while those leaves have never been attempted.
        for index, node in enumerate(ordered, 1):
            node_id = str(node.get("id"))
            if node_id in generated or self.time_up():
                continue
            self.admit_node(node)
            self.prepare_derived_spec_batch([node])
            attempted_fallback_ids.add(node_id)
            if node_id in getattr(self, "whole_app_partial_ids", ()) and self.tests_dir:
                self.node_cycle(node, ordered, index, len(ordered), preimplemented=True)
            else:
                self.node_cycle(node, ordered, index, len(ordered))
            if self.generation_state.get(node_id) == "source_written":
                generated.add(node_id)
            if self.driver:
                self.driver.end_scope("node")
        # Generated specs are advisory until their independent case review is
        # complete. Running their entire suite here duplicated the final pass
        # and could spend thousands of seconds before source generation was
        # finished. The budgeted final admission handles them after generation.
        if getattr(self, "derived_as_specs", False):
            self.metric("acceptance", scope="whole_app_first_suite", decision="deferred_generated_specs")
            failing = None
        else:
            failing = self.whole_app_first_suite(ordered)
        if failing:
            failing = self.whole_app_shared_repair(ordered, failing)
        if failing is None:
            # The application has already been written. A build/start problem is
            # not evidence that all features need regenerating. Preserve the
            # tree for the final suite's targeted startup-repair path.
            log("[flow] whole-app first suite deferred for generated specs; preserving source for "
                "budgeted checks and final startup rehearsal" if getattr(self, "derived_as_specs", False)
                else "[flow] whole-app first suite unavailable; preserving generated app for final targeted repair")
            no_official_specs = not self.tests_dir or getattr(self, "derived_as_specs", False)
            for index, node in enumerate(ordered, 1):
                node_id = str(node.get("id"))
                if node_id not in generated and node_id not in attempted_fallback_ids:
                    if self.time_up():
                        self.mark("implementation_failed", node_id, "wave did not reach this node: time budget exhausted")
                        self.impl_failed.append(node_id)
                    elif not self.admit_node(node):
                        continue
                    else:
                        if node_id in getattr(self, "whole_app_partial_ids", ()) and self.tests_dir:
                            # Official specs decide what a partial leaf still
                            # lacks. Without them nothing would ever finish it.
                            self.node_cycle(node, ordered, index, len(ordered), preimplemented=True)
                        else:
                            self.node_cycle(node, ordered, index, len(ordered))
                        self.driver.end_scope("node")
                    continue
                if node_id in attempted_fallback_ids:
                    self.test_verdict.setdefault(node_id, None)
                    continue
                self.mark("design_started", node_id)
                self.mark("design_done", node_id, "covered by whole-application design")
                self.mark("implementation_started", node_id)
                self.mark("implementation_done", node_id, "implemented by whole-app generation")
                if no_official_specs:
                    # A generated or unavailable suite gave no safe verdict.
                    # Keep this leaf pending without discarding any other
                    # node verdict already measured by that suite.
                    self.test_verdict.setdefault(node_id, None)
                else:
                    self.mark("test_failed", node_id, "first full suite could not report reliable results")
                    self.test_verdict[node_id] = False
            return True
        repair_budget = self.remaining()
        repair_count = sum(str(node.get("id")) in failing for node in ordered)
        repairs_done = 0
        for index, node in enumerate(ordered, 1):
            node_id = str(node.get("id"))
            if node_id in attempted_fallback_ids:
                continue  # Its own node cycle already ran after the waves.
            if node_id not in failing:
                self.mark("design_started", node_id)
                self.mark("design_done", node_id, "covered by whole-application design")
                self.mark("implementation_started", node_id)
                self.mark("implementation_done", node_id, "implemented by whole-app generation")
                if (not getattr(self, "derived_as_specs", False)
                        or self.test_verdict.get(node_id) is True):
                    self.mark("test_passed", node_id, "passed the first full acceptance suite")
                    try:
                        for iface in self.runtime.traceability.list_interfaces(req_id=node_id):
                            self.runtime.traceability.set_interface_implemented(iface["interface_id"], True,
                                                                                 emit_event=False)
                    except Exception:  # noqa: BLE001
                        pass
                continue
            if self.time_up():
                self.mark("implementation_started", node_id)
                self.mark("implementation_failed", node_id, "skipped repair: time budget exhausted")
                self.impl_failed.append(node_id)
                continue
            if not self.admit_node(node):
                continue
            self._repair_stage = (repair_budget, repair_count, repairs_done)
            try:
                self.node_cycle(node, ordered, index, len(ordered),
                                preimplemented=node_id in generated or
                                node_id in getattr(self, "whole_app_partial_ids", ()))
            finally:
                self._repair_stage = None
            repairs_done += 1
            self.driver.end_scope("node")
        return True

    def node_cycle(self, node: dict, ordered: list[dict], index: int, total: int,
                   *, preimplemented: bool = False) -> None:
        node_id = str(node.get("id"))
        specs = list(self.spec_map.get(node_id) or [])
        before_sha = self.head()
        proven_before = {prior for prior, value in self.test_verdict.items() if value is True}
        self.last_codegen_written = []
        self.last_turn_changed = False
        self._generation_gate_result = None
        self.codegen_blocked = node_id in getattr(self, "whole_app_tool_ids", set())
        source_versions = dict(self.repair_source_index().versions)
        self.refused_paths = set()
        if index > 1:
            reap_workspace_processes(self.output_dir, log)
        nodes_left = total - index + 1
        stage = getattr(self, "_repair_stage", None)
        phase_budget, jobs, completed = stage or (getattr(self, "budget", self.remaining()), total, index - 1)
        if stage:
            nodes_left = jobs - completed
        reserve = self.final_phase_reserve(phase_budget) if stage else 0
        node_budget = node_seconds(self.remaining(), nodes_left, self.node_budget_cap,
                                   phase_budget=phase_budget, total_jobs=jobs, completed=completed,
                                   reserve=reserve,
                                   burst_cap=None if "OCTOS_NODE_TIME_BUDGET" in os.environ else 3000)
        deadline = time.time() + node_budget
        log(f"[flow] node {index}/{total} {node_id} starting (budget {node_budget:.0f}s, specs={specs})")

        self.mark("design_started", node_id)
        design = None
        design_wanted = self.design_enabled and total >= self.design_min_nodes
        inline_design = design_wanted and self.design_mode == "inline"
        if design_wanted and not inline_design:
            design = self.design(node, ordered, deadline)
        if design:
            self.designs[node_id] = design
            self.save_design(node_id, design)
            self.mark("design_done", node_id, "design JSON written to .arc/design/" + node_id + ".json")
        elif not inline_design:
            self.mark("design_done", node_id, "design folded into the implementation prompt")

        self.mark("implementation_started", node_id)
        design_text = ("Design contract for this node (follow it):\n"
                       + json.dumps(design, ensure_ascii=False)[:4000] + "\n") if design else ""
        if inline_design:
            design_text = INLINE_DESIGN_NOTE.format(node_id=node_id)
        if self.evolution:
            design_text = EVOLUTION_NOTE.format(listing=source_listing(self.output_dir)) + design_text
        elif self.has_app():
            design_text = ("Current application files (read only backend/server.js and the page you extend):\n"
                           + source_listing(self.output_dir) + "\n") + design_text
        if getattr(self, "generic_template_installed", False):
            design_text = GENERIC_TEMPLATE_NOTE + design_text
            if not (self.output_dir / "frontend" / "src" / "index.html").is_file():
                design_text += "Only shared infrastructure exists so far; create the required frontend page(s).\n"
        design_text = stack_note(self.output_dir) + seed_contract_text(self) + design_text
        design_text += phase_context(getattr(self, "phase_plan", None), [node_id], limit=2400)
        if self.has_app():
            preamble = NODE_PREAMBLE_EXTEND.format(node_id=node_id)
        else:  # single-node tree without a skeleton turn: create the app in this turn
            preamble = NODE_PREAMBLE_CREATE.format(node_id=node_id, req_dir=self.req_dir, port=self.web_port)
        prompt = NODE_PROMPT.format(node_id=node_id, node_spec=describe_node(node), design=design_text,
                                    preamble=preamble, ancestors=self.ancestors_text(node_id, ordered),
                                    tests=self.tests_prompt_for(node_id), smoke=self.smoke_port, port=self.web_port,
                                    performance=self.perf_text(), ui=self.ui_contract(), verify=self.verify_text(total))
        corrections = self.corrections_text()
        prompt = corrections + prompt
        codegen_prompt = None
        implement_timeout = min(self.node_timeout, self.implement_fraction * node_budget, deadline - time.time())
        tiny_ok = preimplemented
        if preimplemented:
            # The shared generation turn already wrote the app. Keep the normal
            # per-leaf acceptance and repair path, including a codegen rebuild
            # prompt if this leaf fails every check.
            self.current_spec_chars = len(self.spec_bodies(node_id))
            codegen_prompt = self.codegen_implement_prompt(node, self.spec_bodies(node_id), corrections)
        elif (not corrections and self.runner is not None and self.codegen_mode()
              and self.tiny_mode(len(self.spec_bodies(node_id)))):
            tiny_ok = self.tiny_turn(node_id, specs, implement_timeout, node)
            self.current_spec_chars = len(self.spec_bodies(node_id))
        if tiny_ok:
            ok, text = True, "sibling batch implementation" if preimplemented else "tiny tier: specs pass"
        else:
            spec_text = self.spec_bodies(node_id)
            if self.codegen_mode():
                codegen_prompt = self.codegen_implement_prompt(node, spec_text, corrections)
            if codegen_prompt is not None:
                self.current_spec_chars = len(spec_text)
                write_codegen_manifests(self.output_dir)
                before = set(self.refused_paths)
                ok, text = self.codegen_turn(codegen_prompt, implement_timeout, f"{node_id} implement",
                                            spec_chars=self.current_spec_chars, defer_shared_refusals=True)
                # Requote an unshown application file immediately: cloud
                # fcec6ac02a95 showed that waiting there can cost 30-80 tool
                # requests. Only pristine shared helpers with other valid
                # output defer that request until acceptance proves it needed.
                refused = self.refused_paths - before
                if refused and refused == getattr(self, "last_codegen_deferred", set()):
                    log(f"[flow] {node_id}: testing generated app before requoting shared helpers")
                elif refused and self.codegen_mode():
                    retry_prompt = self.codegen_implement_prompt(node, spec_text, self.corrections_text())
                    if retry_prompt is not None and refused <= quoted_paths(retry_prompt):
                        names = ", ".join(sorted(refused))
                        log(f"[flow] {node_id}: retrying codegen with {names} quoted whole")
                        ok, text = self.codegen_turn(retry_prompt, min(implement_timeout, max(60, deadline - time.time())),
                                                    f"{node_id} implement (retry with {names})",
                                                    spec_chars=self.current_spec_chars)
                    else:
                        largest = max(refused, key=lambda p: (self.output_dir / p).stat().st_size
                                      if (self.output_dir / p).is_file() else 0)
                        if self.split_oversized_hub(largest, f"{node_id} could not be shown {largest} whole"):
                            retry_prompt = self.codegen_implement_prompt(node, spec_text, self.corrections_text())
                        if retry_prompt is not None and refused <= quoted_paths(retry_prompt):
                            names = ", ".join(sorted(refused))
                            log(f"[flow] {node_id}: retrying codegen with {names} quoted whole after the split")
                            ok, text = self.codegen_turn(retry_prompt, min(implement_timeout, max(60, deadline - time.time())),
                                                        f"{node_id} implement (retry with {names})",
                                                        spec_chars=self.current_spec_chars)
                        else:
                            log(f"[flow] {node_id}: {', '.join(sorted(refused))} cannot be quoted whole within the budget; no retry")
            else:
                if self.codegen_mode():
                    self.log_codegen_fallback(node_id)
                fallback_proxy = getattr(self, "llm_proxy", None)
                if isinstance(fallback_proxy, LlmProxy) and fallback_proxy.provider_unavailable:
                    ok, text = False, "HTTP 503 temporarily unavailable; no fallback request sent"
                elif (self.has_app() and fallback_proxy is not None
                        and os.environ.get("OCTOS_ARC_CODEGEN", "1") != "0"
                        and os.environ.get("OCTOS_ARC_IMPLEMENT_REQUESTS") != "0"):
                    focused_prompt = (prompt.replace(self.verify_text(total), "").replace(PORT_RULES, "") + "\nCurrent scope: " + node_id + ". This is an existing application. "
                                      "Read only missing contract owners, preserve every required outcome, and apply focused edits. "
                                      "If a generated test conflicts with requirements, report validator_dispute with exact quotes; "
                                      "do not change tests or claim behavior verified from a build.\n")
                    self.bind_edit_scope(focused_prompt, describe_node(node) + "\n" + spec_text, set(self.refused_paths))
                    ok, text = self.structured_edit_turn(focused_prompt, implement_timeout, f"{node_id} implement")
                else:
                    ok, text = self.turn(prompt, implement_timeout, f"{node_id} implement")
        if not ok and "truncated" in text.lower():
            # A truncated response made no write. Check the already generated app
            # before paying for a tool turn: later nodes can be satisfied by a
            # shared earlier feature (v4.2 grid-by-default: 20 needless tools).
            if self.has_app() and self.runner is not None and specs:
                probe = self.run_specs(specs)
                if not probe.error and probe.total and probe.passed == probe.total:
                    log(f"[flow] {node_id}: truncated output discarded; existing app already passes its specs")
                    ok, text = True, "existing app passes after truncated response"
            if not ok and codegen_prompt is not None and self.codegen_mode():
                # A short, single-request edit is cheaper than jumping straight
                # from a too-long file reply to dozens of tool calls. Rebuild the
                # prompt from disk so its source budget remains valid.
                focused = self.codegen_implement_prompt(node, spec_text, self.corrections_text(),
                                                         evidence=TRUNCATED_CODEGEN_RETRY)
                if focused is not None:
                    retry_time = min(self.node_timeout, deadline - time.time())
                    if retry_time > 0:
                        log(f"[flow] {node_id}: truncated output; one bounded retry (tools for large existing files)")
                        ok, text = self.codegen_turn(focused, retry_time, f"{node_id} implement (compact retry)",
                                                     spec_chars=self.current_spec_chars)
            if not ok and "truncated" in text.lower():
                # Only a second truncated response falls back to tool editing.
                log(f"[flow] {node_id}: compact output also truncated; using targeted tool edits")
                self.driver.close()
                retry = prompt + "\n" + TRUNCATED_RETRY
                retry_time = min(self.node_timeout, deadline - time.time())
                if retry_time > 0:
                    ok, text = self.turn(retry, retry_time, f"{node_id} implement (retry)")
        proxy = getattr(self, 'llm_proxy', None)
        if (not ok and isinstance(proxy, LlmProxy) and proxy.provider_unavailable
                and not self.last_codegen_written and self.last_turn_changed is not True):
            self.test_verdict[node_id] = None
            self.metric('implementation_deferred', reason='provider_unavailable', node_id=node_id)
            log(f'[flow] {node_id}: upstream unavailable before any source edit; node remains pending')
            return
        timed_out = (not ok) and "timed out" in text.lower()
        if ok and not self.has_app():
            # v6-counter: one package.json missing after the turn. Do not give
            # up — the acceptance loop's build error becomes the repair prompt.
            log(f"[flow] {node_id}: app layout incomplete after the turn; acceptance loop will drive the repair")
            self.pending_corrections.append(
                "Your turn ended without both frontend/package.json and backend/package.json (with `build` and "
                "`start` scripts) on disk; the harness could not even build the app. Create the missing files.")
        can_verify_existing = self.has_app() and self.runner is not None and bool(specs)
        if not ok and not can_verify_existing:
            if Flow.retain_safe_no_spec_partial(self, node_id):
                # Continue through the normal commit/traceability path. The
                # verdict remains unknown until final contract review and the
                # grader-like startup rehearsal.
                ok = True
                text = "partial structured edit retained after clean early checks; final verification pending"
            else:
                # No executable acceptance and no clean generation gate means
                # there is still no evidence that the partial node is safe.
                if before_sha and self.has_app():
                    self.restore_app(before_sha)
                    self.metric('incomplete_node_rollback', node_id=node_id,
                                reason='no_local_acceptance', restored=before_sha)
                self.mark("implementation_failed", node_id, text[-500:])
                self.impl_failed.append(node_id)
                return
        if not ok and not timed_out:
            log(f"[flow] {node_id}: generation did not complete; testing the existing app")
            self.pending_corrections.append(
                "The implementation turn did not complete. Judge the existing files using acceptance results; "
                "preserve working behavior and repair only failures supported by those results.")
        if timed_out:
            # The files written so far stay on disk; let the acceptance loop judge them.
            log(f"[flow] {node_id}: implement turn hit its {implement_timeout:.0f}s cap; testing what exists")
            self.driver.close()
            self.pending_corrections.append(
                "Your implementation turn ran out of time; work in smaller steps and verify with curl early.")
        review_gaps = (Flow.no_spec_feature_review(self, node, deadline)
                       if ok and (not getattr(self, "tests_dir", None)
                                  or self.derived_review_needed(node_id)) else [])
        if review_gaps:
            text = ((text or "") + "\nNo-spec scenario review remains pending: "
                    + "; ".join(review_gaps[:6]))[-2000:]
        if inline_design:
            written = self.output_dir / ".arc" / "design" / f"{node_id}.json"
            try:
                design = json.loads(written.read_text(encoding="utf-8")) if written.is_file() else None
            except (OSError, json.JSONDecodeError):
                design = None
            if isinstance(design, dict):
                self.designs[node_id] = design
                self.save_design(node_id, design)
                self.mark("design_done", node_id, "design JSON written inline to .arc/design/" + node_id + ".json")
            else:
                self.mark("design_done", node_id, "design folded into the implementation turn (no JSON file)")
        self.mark("implementation_done", node_id, (text[-500:] or None) if ok else "implementation incomplete; existing code awaiting acceptance")
        self.commit(f"{node_id} (implement): {node.get('name', '')}")

        def rebuild_prompt(failures: str) -> str:
            if self.codegen_mode() and codegen_prompt:
                evidence = ("Your previous files failed every test. Failures:\n" + failures
                            + "\nFix the root causes while preserving unrelated behavior; "
                              "do not re-emit unchanged files.\n")
                # Rebuild from current disk contents; never append a second,
                # conflicting copy of the files quoted before implementation.
                rebuilt = self.codegen_implement_prompt(node, self.spec_bodies(node_id), corrections, evidence=evidence)
                if rebuilt is not None:
                    return rebuilt
                self.codegen_blocked = True
                self.log_codegen_fallback(node_id)
            return (prompt + "\nYOUR PREVIOUS ATTEMPT FAILED EVERY ACCEPTANCE TEST — the failures (Feature / where / "
                    "observation / steps):\n" + failures + "\n" + self.sources_text()
                    + app_design_context(getattr(self, "app_design_doc", None), self.spec_bodies(node_id),
                                         int(os.environ.get("OCTOS_ARC_APP_DESIGN_CHARS", "6000")))
                    + "Rewrite the files for this node completely (full write_file for each file, not edits), "
                    "fixing the root causes above.\n")

        self.last_node_own_pass = False
        verdict = self.acceptance_loop(node_id, specs, deadline, rebuild_prompt=rebuild_prompt,
                                       source_versions=source_versions)
        self.test_verdict[node_id] = verdict
        regressed_proven = sorted(prior for prior in proven_before if self.test_verdict.get(prior) is False)
        if verdict is not True and regressed_proven and before_sha:
            self.settle_failed_extension(node_id, before_sha, regressed_proven,
                                         node_passed=bool(getattr(self, "last_node_own_pass", False)))
            verdict = self.test_verdict.get(node_id)
        if verdict is True:
            self.mark("test_passed", node_id, f"{len(specs)} acceptance spec file(s) pass locally")
            try:
                for iface in self.runtime.traceability.list_interfaces(req_id=node_id):
                    self.runtime.traceability.set_interface_implemented(iface["interface_id"], True, emit_event=False)
            except Exception:  # noqa: BLE001
                pass
        elif verdict is False:
            self.mark("test_failed", node_id, "acceptance specs still failing after repair rounds")

    def snapshot_sources(self, node_id: str, attempt: int) -> Path | None:
        """Copy the app sources that the next repair will overwrite into
        .arc/codegen/<node>-r<attempt>/ (the platform keeps the workspace but not
        our git history, so the first-pass code was unrecoverable: cloud 27de75de0cd0)."""
        dest = self.output_dir / ".arc" / "codegen" / f"{node_id}-r{attempt}"
        try:
            if dest.exists():
                shutil.rmtree(dest)
            count = 0
            files = app_source_files(self.output_dir)
            # Lockfiles matter for reproduction, but never consume model context.
            files += [self.output_dir / part / name for part in ("frontend", "backend")
                      for name in LOCKFILES if (self.output_dir / part / name).is_file()]
            for path in files:
                target = dest / path.relative_to(self.output_dir)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                count += 1
            log(f"[flow] {node_id}: {count} source file(s) snapshotted to {dest.relative_to(self.output_dir)}")
            return dest
        except OSError as exc:
            log(f"[flow] {node_id}: source snapshot failed: {exc}")
            return None

    def discard_template(self) -> Path | None:
        """Move frontend/ and backend/ of a non-working existing app to
        .arc/template-discarded/ so the fresh build starts from our own layout."""
        dest = self.output_dir / ".arc" / "template-discarded"
        try:
            if dest.exists():
                shutil.rmtree(dest)
            dest.mkdir(parents=True, exist_ok=True)
            moved = []
            for name in ("frontend", "backend"):
                src = self.output_dir / name
                if src.exists():
                    shutil.move(str(src), str(dest / name))
                    moved.append(name)
            log(f"[flow] existing app passes no spec; moved {moved} to {dest.relative_to(self.output_dir)} and building fresh")
            return dest
        except OSError as exc:
            log(f"[flow] could not set the existing app aside: {exc}")
            return None

    def already_passing_nodes(self, node_ids: list[str]) -> set[str]:
        """Evolution probe: run each candidate node's specs against the existing app
        (no LLM); nodes that fully pass need no implementation turn."""
        out: set[str] = set()
        for node_id in node_ids:
            specs = list(self.spec_map.get(node_id) or [])
            if not specs:
                continue
            summary = self.run_specs(specs)
            self.probe_count += 1
            if summary.error:
                log(f"[acceptance] probe {node_id}: existing app does not build/start/serve ({summary.error[:160]})")
                continue
            if not summary.total:
                continue
            log(f"[acceptance] probe {node_id}: {summary.passed}/{summary.total} against the existing app")
            if summary.all_passed:
                if not self.derived_review_needed(node_id):
                    out.add(node_id)
                    self.probe_summaries[node_id] = summary  # regression_cycle reuses it
        return out

    def probe_existing_app(self, node_ids: list[str], unchanged: set[str]) -> set[str]:
        """Judge an existing app against the finalized acceptance suite."""
        if not self.evolution or self.runner is None:
            return unchanged
        unchanged |= self.already_passing_nodes([node for node in node_ids if node not in unchanged])
        if self.probe_count and not unchanged:
            # A template satisfying none of the final specs is not a useful base.
            self.discard_template()
            self.evolution = False
        self.nodes_to_implement = len([node for node in node_ids if node not in unchanged])
        log(f"[flow] {'evolution' if self.evolution else 'fresh build'} after probing the existing app: "
            f"unchanged {sorted(unchanged)}, to implement {[node for node in node_ids if node not in unchanged]}")
        return unchanged

    def regression_cycle(self, node: dict) -> None:
        """Evolution: unchanged node — carry the design/impl over, re-run its specs."""
        node_id = str(node.get("id"))
        specs = list(self.spec_map.get(node_id) or [])
        self.mark("design_started", node_id)
        self.mark("design_done", node_id, "unchanged since the previous requirement version; carried over")
        self.mark("implementation_started", node_id)
        self.mark("implementation_done", node_id, "carried over from the template application")
        verdict = None
        if self.runner is not None and specs:
            summary = self.probe_summaries.pop(node_id, None) or self.run_specs(specs)
            if summary.error:
                log(f"[acceptance] regression {node_id} infrastructure error: {summary.error[:300]}")
            else:
                self.record_tests(node_id, specs, summary)
                verdict = None if summary.all_passed and self.derived_review_needed(node_id) else summary.all_passed
                log(f"[acceptance] regression {node_id}: {summary.passed}/{summary.total}")
                if not verdict:
                    deadline = time.time() + min(self.node_budget_cap, max(240, self.remaining() / 2))
                    self.pending_corrections.append(
                        "This requirement is unchanged, but its current acceptance check failed. "
                        "Repair the observed failure without removing other behavior.")
                    verdict = self.acceptance_loop(node_id, specs, deadline, initial_summary=summary)
        self.test_verdict[node_id] = verdict
        if verdict is True:
            self.mark("test_passed", node_id, "regression specs pass locally")
        elif verdict is False:
            self.mark("test_failed", node_id, "regression specs fail after repair rounds")

    def settle_failed_extension(self, node_id: str, before_sha: str, regressed_proven: list[str],
                                node_passed: bool) -> bool:
        """Roll a failed extension back -- unless the "regression" reproduces without it.

        A failed extension has no verified value that justifies shipping known
        damage to previously passing behavior, so the tree returns to the exact
        pre-node commit. But v9.1 (run 2a839b37d3e8) rolled REQ-1-1-2 back for a
        REQ-1-1-1 check that still failed on the restored source: a prior that
        fails without the node's changes is flaky or stateful, not regressed by
        the node. When every "regressed" prior still fails after the restore and
        the node's own specs had passed, the node's work is re-applied and kept.
        Returns True when the extension was kept.
        """
        after_sha = self.head()
        self.restore_app(before_sha)
        self.commit(f"{node_id}: restore verified behavior after failed extension")
        restored_sha = before_sha  # restore_app returns this exact source tree
        prior_specs = sorted({spec for prior in regressed_proven for spec in self.spec_map.get(prior, [])})
        restored = (self.run_specs(prior_specs, grader_like=True) if prior_specs
                    and self.remaining() > self.final_measurement_reserve() + 30 else None)
        still_failing: list[str] = []
        if restored is not None and self.suite_is_measured(restored, prior_specs):
            for prior in regressed_proven:
                paths = self.spec_map.get(prior, [])
                rows = [row for row in restored.results if any(
                    str(row.file or '').replace('\\', '/') == path or
                    str(row.file or '').replace('\\', '/').endswith('/' + path) for path in paths)]
                local = RunSummary(results=rows, total=len(rows), passed=sum(row.ok for row in rows))
                verdict = ((None if local.all_passed
                                             and getattr(self, "derived_as_specs", False) is True
                                             and self.derived_review_needed(prior)
                                             else local.all_passed)
                                            if self.suite_is_measured(local, paths) else None)
                self.test_verdict[prior] = verdict
                if verdict is not None:
                    self.record_tests(prior, paths, local)
                self.mark("test_passed" if verdict is True else "test_failed" if verdict is False
                          else "test_unverified", prior,
                          f"restored source {restored_sha}: " + (f"{local.passed}/{local.total} measured"
                                                                 if verdict is not None else "measurement incomplete"))
                if verdict is False:
                    still_failing.append(prior)
                    failing = [row.title for row in rows if not row.ok]
                    log(f"[acceptance] {prior} still fails on the pre-node source: {failing[:4]}")
        else:
            for prior in regressed_proven:
                self.test_verdict[prior] = None  # source restored; behavior not remeasured
                self.mark("test_unverified", prior,
                          f"restored source {restored_sha}; previous result needs remeasurement")
        if still_failing and len(still_failing) == len(regressed_proven) and node_passed and after_sha:
            self.restore_app(after_sha)
            self.commit(f"{node_id}: keep extension; prior failures reproduce without it")
            self.test_verdict[node_id] = True
            self.mark("test_passed", node_id, f"extension source {after_sha}; node passed on this source")
            for prior in regressed_proven:
                self.test_verdict[prior] = None
                self.mark("test_unverified", prior,
                          f"extension source {after_sha}; restored-source measurement is stale")
            self.metric('failed_extension_kept', node_id=node_id, restored=after_sha,
                        flaky_priors=regressed_proven)
            log(f"[acceptance] {node_id}: {regressed_proven} fail without this node's changes too; "
                f"not a regression -- extension kept ({after_sha[:8]})")
            return True
        self.metric('failed_extension_rollback', node_id=node_id, restored=before_sha,
                    regressed_nodes=regressed_proven)
        log(f"[acceptance] {node_id}: failed extension regressed {regressed_proven}; "
            f"restored pre-node source {before_sha[:8]}")
        return False

    def regression_checkpoint(self, index: int, total: int) -> None:
        if (getattr(self, "_generation_active", False)
                and os.environ.get("OCTOS_ARC_POST_GENERATION_CHECKPOINT", "0") != "1"):
            # Repeated broad tests may consume the remaining implementation
            # budget. Explicit opt-in keeps the older checkpoint diagnostics
            # available for controlled runs and tests.
            return
        start = int(os.environ.get("OCTOS_ARC_REGRESSION_CHECKPOINT", "4"))
        reserve = self.final_phase_reserve()
        if (not regression_checkpoint_due(index, total, start) or self.runner is None
                or not self.tests_dir or self.remaining() < self.min_repair_seconds + reserve):
            return
        tracked = getattr(self, "checkpoint_regressions", set())
        self.checkpoint_regressions = tracked
        verified = {node: self.spec_map.get(node, []) for node, verdict in self.test_verdict.items()
                    if verdict is True or node in tracked}
        # Revisit a bounded rotating backlog: otherwise an early failure can
        # disappear from every checkpoint until the final suite.
        backlog = [node for node, verdict in self.test_verdict.items()
                   if verdict is False and node not in verified and self.spec_map.get(node)]
        cursor = getattr(self, '_checkpoint_backlog_cursor', 0)
        limit = max(0, int(os.environ.get('OCTOS_ARC_CHECKPOINT_BACKLOG', '4')))
        selected = (backlog[cursor % len(backlog):] + backlog[:cursor % len(backlog)])[:limit] if backlog else []
        self._checkpoint_backlog_cursor = cursor + len(selected)
        verified.update({node: self.spec_map[node] for node in selected})
        specs = sorted({spec for paths in verified.values() for spec in paths})
        if len(specs) < 2:
            return
        workers = workers_for_final(getattr(self, "mem_limit", None),
                                    self.final_workers())
        summary = self.run_specs(specs, workers=workers, grader_like=True)
        if getattr(self, "derived_as_specs", False) is True:
            summary = self.audit_related_derived_specs(specs, summary)
        if not self.suite_is_measured(summary, specs):
            log(f"[acceptance] checkpoint {index}: no reliable verdict; {summary.error or 'incomplete, interrupted or unloaded results'}")
            return
        disputed = self.disputed_generated_failures(summary) if getattr(self, "derived_as_specs", False) else []
        if disputed:
            for node_id, _ in disputed:
                self.test_verdict[node_id] = None
            log(f"[acceptance] checkpoint {index}: excluding invalid generated oracles from repair evidence")
            self.metric("derived_spec_dispute", scope="checkpoint", checkpoint=index,
                        tests=[list(item) for item in disputed])
        all_specs = {spec for paths in self.spec_map.values() for spec in paths}
        self.metric('checkpoint_coverage', checkpoint=index, checked_specs=len(specs),
                    total_specs=len(all_specs), unobserved_specs=len(all_specs - set(specs)),
                    backlog_selected=selected, backlog_remaining=max(0, len(backlog) - len(selected)))
        log(f'[acceptance] checkpoint {index} coverage: {len(specs)}/{len(all_specs)} specs; '
            f'{len(all_specs - set(specs))} not observed in this checkpoint')
        for node in selected:
            tracked.add(node)
        grouped = nodes_for_failures(self.uncontested_derived_results(summary).results, verified)
        log(f"[acceptance] checkpoint {index}: {summary.passed}/{summary.total}; "
            f"regressed nodes {sorted(node for node in grouped if node)}")
        for row in [r for r in summary.results if not r.ok][:8]:
            # The checkpoint's own evidence used to stay inside the repair prompt;
            # the log then showed which nodes regressed but never why.
            first = (row.message or "").strip().splitlines()[:1]
            log(f"[acceptance]   {row.title[:90]} :: {' '.join(first)[:220] if first else row.status}")
        for node in grouped:
            if node in verified:
                tracked.add(node)
                self.test_verdict[node] = False
                self.mark("test_failed", node, "previously passing behavior failed a regression checkpoint")
        for node in list(tracked):
            paths = verified.get(node, [])
            observed = [[r for r in summary.results if Path(r.file or "").name == Path(path).name]
                        for path in paths]
            if observed and all(rows and all(r.ok for r in rows) for rows in observed):
                tracked.remove(node)
                if self.derived_review_needed(node):
                    self.test_verdict[node] = None
                else:
                    self.test_verdict[node] = True
                    self.mark("test_passed", node, "previously regressed behavior passed its checkpoint specs")
        regressed = bool(grouped)
        if grouped:
            self.queue_checkpoint_evidence(summary)
            regressed = self.repair_regressions(index, specs, verified, tracked, summary, grouped, workers)
            latest_summary = getattr(self, "_checkpoint_repair_summary", summary)
            latest_grouped = getattr(self, "_checkpoint_repair_grouped", grouped)
            # A successful repair's measurement, rather than the failing
            # pre-repair observation, becomes the next healthy baseline.
            summary, grouped = latest_summary, latest_grouped
            tracked.difference_update(selected)  # rotating backlog is not a permanent regression set
            if not self.suite_is_measured(summary, specs):
                # A repair changed the tree, but its report is incomplete.
                # Neither old passes nor the apparent score drop describe it.
                tracked.update(verified)
                for node in verified:
                    self.test_verdict[node] = None
                return
            if regressed and self.restore_catastrophic_checkpoint(
                    index, latest_summary, latest_grouped, verified, tracked):
                # The healthy baseline is deliberately retained.  Nodes added
                # since it are marked unresolved and will be measured/repaired
                # by later checkpoints or the final suite.
                return
        tracked.difference_update(selected)
        if not regressed:
            # The tree the suite agreed with: the next suite repair quotes what
            # changed since it first. A checkpoint still regressed keeps the
            # previous baseline, so the files that introduced the regression
            # stay in the diff until it is fixed.
            self.last_checkpoint_sha = self.head()
            sha = self.last_checkpoint_sha
            if sha:
                self.healthy_checkpoint = {
                    "sha": sha,
                    "summary": summary,
                    "verified": {node: list(paths) for node, paths in verified.items()},
                }
        self.remember_delivery_checkpoint(summary, grouped)

    def restore_catastrophic_checkpoint(self, index: int, summary: RunSummary, grouped: dict,
                                        verified: dict, tracked: set) -> bool:
        """Restore a measured healthy checkpoint after a broad failed repair.

        Losing one or two checks may be flakiness or a productive intermediate
        edit.  A large drop below the *absolute pass count* of the previous
        healthy checkpoint is different: even counting every newly introduced
        spec as lost, the older tree is known to pass more behaviours.  The
        default threshold is 25% of that healthy pass count (at least four), so
        normal oscillation keeps its chance to recover while failures such as
        68 -> 39 do not poison all later work.
        """
        healthy = getattr(self, "healthy_checkpoint", None)
        if not healthy or not healthy.get("sha") or summary.error or summary.killed:
            return False
        baseline = healthy["summary"]
        minimum_drop = int(os.environ.get(
            "OCTOS_ARC_CHECKPOINT_ROLLBACK_DROP",
            str(max(4, (baseline.passed + 3) // 4))))
        drop = baseline.passed - summary.passed
        newly_broken = {node for node in grouped if node and node not in healthy["verified"]}
        if drop < minimum_drop or len(grouped) < 3:
            return False
        self.restore_app(healthy["sha"])
        self.commit(f"chore: restore healthy checkpoint after regression {index}")
        healthy_nodes = set(healthy["verified"])
        for node in healthy_nodes:
            tracked.discard(node)
            self.test_verdict[node] = (None if self.derived_review_needed(node)
                                               or any(owner == node for owner, _ in self.disputed_generated_failures(summary))
                                               else True)
            if node in grouped and self.test_verdict[node] is True:
                self.mark("test_passed", node, "restored the last healthy checkpoint after broad regression")
        rolled_back = sorted(node for node in verified if node not in healthy_nodes)
        for node in rolled_back:
            tracked.add(node)
            self.test_verdict[node] = False
            self.mark("test_failed", node, "rolled back with a catastrophic regression; requires remeasurement")
        self.pending_corrections.append(
            f"Checkpoint {index} fell {drop} passes below the last healthy checkpoint after repair. "
            f"The harness restored that measured tree. Re-implement the rolled-back behaviours with targeted "
            f"edits and preserve the restored contracts: {', '.join(rolled_back) or 'none'}."
        )
        self.metric("checkpoint_rollback", checkpoint=index, drop=drop,
                    baseline_passed=baseline.passed, observed_passed=summary.passed,
                    failing_nodes=sorted(node for node in grouped if node),
                    newly_broken=sorted(newly_broken), rolled_back=rolled_back)
        log(f"[acceptance] checkpoint {index}: catastrophic regression {baseline.passed} -> "
            f"{summary.passed}; restored healthy checkpoint {healthy['sha'][:8]}")
        return True

    def queue_checkpoint_evidence(self, summary: RunSummary) -> None:
        """Bound checkpoint evidence, keeping both ends when source context is large."""
        summary = self.uncontested_derived_results(summary)
        budget = int(os.environ.get("OCTOS_ARC_CHECKPOINT_EVIDENCE", "12000"))
        evidence = (failure_summaries(summary, max_snapshots=budget // 2)
                    + failure_source_context(summary, self.tests_dir))
        grouped = nodes_for_failures(summary.results, self.spec_map)
        failing_ids = sorted(node for node in grouped if node)
        self.pending_corrections.append(CheckpointEvidence(clip_ends(evidence, budget), failing_ids))

    def repair_regressions(self, index: int, specs: list[str], verified: dict, tracked: set,
                           summary: RunSummary, grouped: dict, workers: int) -> bool:
        """Fix what a checkpoint found before building anything else on top.
        Returns whether a regression remains.

        Queueing the evidence for the next node's turn does not work: that turn
        is busy with its own node, and its acceptance run only covers its own
        spec, so nothing re-checks the regression until the next checkpoint. In
        cloud e767e871a6c6 checkpoint 8 reported REQ-2.3.1, REQ-2.3.2 and
        REQ-2.3.3 broken; by checkpoint 16 the same three were still broken and
        four more had joined them, with no recovery recorded in between.
        """
        # Two rounds: one codegen request, then tools only if it did not take.
        # Seven cloud runs of 2026-09-18 spent 111-307 tool calls (1.0-1.5 h) per
        # big task on checkpoint repairs, all in tool mode, and 19 of 26 of them
        # cleared every regression -- the tool round stays for the cases the
        # single request misses, so the fix rate is kept at the price of one
        # extra request where codegen fails.
        rounds = int(os.environ.get("OCTOS_ARC_CHECKPOINT_REPAIRS", "2"))
        repaired = False
        focused = set()
        for attempt in range(rounds):
            reserve = self.final_phase_reserve()
            if (not grouped or self.remaining() < self.repair_minimum() + reserve
                    or self.wound_down()):
                break
            # Re-read after admission so time consumed between rounds cannot be
            # lent to this turn by a stale sample.
            available = self.remaining() - reserve
            failing_ids = sorted(node for node in grouped if node)
            cap = max(1, int(os.environ.get('OCTOS_ARC_CHECKPOINT_REPAIR_NODES', '4')))
            # A broad suite failure does not fit a single bounded edit turn.
            # Rotate focus when a previous group remains stuck; always verify
            # the entire checkpoint afterwards to detect collateral regressions.
            failing_ids = sorted(failing_ids, key=lambda node: (node in focused, node))[:cap]
            focused.update(failing_ids)
            failing = failing_ids or ["the regressed behaviours"]
            outcomes = [row for node in failing_ids for row in grouped[node]]
            evidence = RunSummary(results=outcomes) if outcomes else summary
            failures = failure_summaries(evidence) + failure_source_context(evidence, self.tests_dir)
            failures += self.store_change_note(summary)
            before_passed, before_signature = summary.passed, failure_signature(summary)
            repaired = True
            tool_prompt = self.app_repair_prompt(
                node_id=", ".join(failing), passed=summary.passed, total=summary.total, failures=failures,
                test_location=self.repair_test_location(),
                sources=self.repair_requirements() + self.sources_text(),
                corrections=self.corrections_text(), slow="",
                smoke=self.smoke_port, port=self.web_port)
            # The first round is one codegen request; a second round, if configured,
            # is the changed approach.
            # A checkpoint interrupts implementation; past runs spent 5-15
            # minutes in one no-change tool turn. Keep each attempt bounded so
            # the next nodes and the reserved final measurement still run.
            checkpoint_cap = max(60, int(os.environ.get('OCTOS_ARC_CHECKPOINT_REPAIR_TIMEOUT', '300')))
            outcome = self.suite_repair_turn(f"checkpoint {index} repair {attempt + 1}/{rounds}", failing_ids, failures,
                                             min(self.suite_repair_timeout(), checkpoint_cap, max(1, available)),
                                             tool_prompt=tool_prompt, prefer_codegen=attempt == 0)
            mode = outcome[0] if isinstance(outcome, tuple) else ""
            self.commit(f"fix: checkpoint {index} regression repair {attempt + 1}")
            if getattr(self, "last_repair_changed", None) is False:
                if mode == "unapplied" and attempt + 1 < rounds:
                    # v9.2.6 (919e1def62e0): the codegen attempt timed out with
                    # nothing written and the loop ended here, so the tool-mode
                    # round never ran and REQ-1-3 stayed regressed.
                    log(f"[acceptance] checkpoint {index}: repair {attempt + 1} did not apply; trying the changed approach")
                    continue
                log(f"[acceptance] checkpoint {index}: no source changes; skipping duplicate acceptance")
                break
            observed = self.run_specs(specs, workers=workers, grader_like=True)
            if getattr(self, "derived_as_specs", False) is True:
                observed = self.audit_related_derived_specs(specs, observed)
                disputed = self.disputed_generated_failures(observed)
                if disputed:
                    for node_id, _ in disputed:
                        self.test_verdict[node_id] = None
            if not self.suite_is_measured(observed, specs):
                self.queue_checkpoint_evidence(summary)
                self._checkpoint_repair_summary = observed
                self._checkpoint_repair_grouped = grouped
                return True
            summary = observed
            grouped = nodes_for_failures(self.uncontested_derived_results(summary).results, verified)
            log(f"[acceptance] checkpoint {index} after repair: {summary.passed}/{summary.total}; "
                f"still regressed {sorted(node for node in grouped if node)}")
            for node in verified:
                previous = self.test_verdict.get(node)
                if node and node not in grouped:
                    tracked.discard(node)
                    self.test_verdict[node] = (None if self.derived_review_needed(node)
                                               or any(owner == node for owner, _ in self.disputed_generated_failures(summary))
                                               else True)
                    if self.test_verdict[node] is True and previous is not True:
                        self.mark("test_passed", node,
                                  "previously regressed behavior passed after checkpoint repair")
                elif node:
                    tracked.add(node)
                    self.test_verdict[node] = False
                    if previous is not False:
                        self.mark("test_failed", node,
                                  "behavior failed after checkpoint repair")
            if (grouped and set(grouped).issubset(focused) and summary.passed <= before_passed
                    and failure_signature(summary) == before_signature):
                log(f"[acceptance] checkpoint {index}: repair changed files but the same failures remain; "
                    "saving the next repair turn for later evidence")
                break

        self._checkpoint_repair_summary = summary
        self._checkpoint_repair_grouped = grouped
        if repaired and grouped:
            # corrections_text consumed the initial checkpoint evidence. Keep
            # the latest still-failing observations for the next implementation.
            self.queue_checkpoint_evidence(summary)
        return bool(grouped)

    def final_acceptance(self, *, initial_summary: RunSummary | None = None,
                         startup_recovery_only: bool = False) -> None:
        """Run EVERY spec file together against one server with the configured workers.
        Per-node runs cannot see cross-node interference through shared server
        state; this pass can, and it repairs the nodes whose tests fail.
        Startup-only recovery returns at the first complete measurement so the
        caller can resume implementation. A retry may reuse a failure report
        only after its caller has verified the application sources are unchanged.
        """
        self.final_repair_no_change = False
        self.final_suite_progress = False
        self.final_suite_green = False
        self.final_spec_dispute = False
        self.final_safe_failures_remaining = False
        self.final_startup_recovered = False
        self._final_retry_measurement = None
        force_tool_repair = bool(getattr(self, "_force_final_tool_repair", False))
        self._force_final_tool_repair = False
        if self.runner is None or not self.tests_dir:
            return
        all_specs = sorted(str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob("*.spec.ts"))
        unverified = [n for n, v in self.test_verdict.items() if v is not True] or \
            [n for n in self.spec_map if n and self.spec_map[n] and n not in self.test_verdict]
        if len(all_specs) < 2 and not unverified:
            return  # single spec already judged by the node run
        # One more round than the identical-failure escalation needs, so the
        # changed approach actually gets to run.
        rounds = int(os.environ.get("OCTOS_FINAL_REPAIR_ROUNDS", "0"))
        confirm_runs = max(1, int(os.environ.get("OCTOS_ARC_FINAL_CONFIRM_RUNS", "1")))
        workers = workers_for_final(getattr(self, "mem_limit", None), self.final_workers())
        def measured_suite() -> RunSummary:
            nonlocal workers
            observed = self.run_specs(all_specs, workers=workers, grader_like=True)
            while observed.error and observed.killed and workers > 1:
                workers = max(1, workers // 2)
                log(f"[acceptance] full suite runner was killed; retrying with {workers} worker(s)")
                observed = self.run_specs(all_specs, workers=workers, grader_like=True)
            return observed

        previous_failing: frozenset | None = None
        repeated = False  # the last round reproduced the round before it
        # Which behaviours the per-node runs judged good, before this pass starts
        # overwriting the verdicts with full-suite ones.
        passed_alone = {node for node, verdict in self.test_verdict.items() if verdict is True}
        passed_a_round: set = set()  # nodes this pass has already seen pass once
        # Measured, not yet acted on: a repair killed at the per-turn timeout can
        # leave the tree part edited. Cloud 6e82a7ff571c went 27/32, had its
        # repair cut at 1200s, and measured 17/32 next round, so the rounds after
        # it repair the damage rather than the five failures it started with. The
        # restore below still delivers the best round, so only the intervening
        # rounds are spent. Repairing from `best` instead was tried and reverted:
        # the evidence then comes from a round where the flaky specs passed, which
        # silently drops the intermittent note. Any retry needs to keep both.
        best: dict | None = None  # L17: best full-suite round (passed, sha, summary, grouped)
        regressions = 0  # consecutive rounds behind the best one
        last_passed = -1
        unfinished = ""  # what the previous repair turn said it had left to do
        wrote_last = False  # whether that turn got as far as committing an edit
        last_repair_mode = ""
        for attempt in range(rounds + 1):
            restored_this_round = False
            reused_measurement = attempt == 0 and initial_summary is not None
            summary = initial_summary if reused_measurement else measured_suite()
            if getattr(self, "derived_as_specs", False) is True:
                summary = self.audit_related_derived_specs(all_specs, summary)
                disputed = self.disputed_generated_failures(summary)
                if disputed:
                    self.final_spec_dispute = True
                    log("[acceptance] full suite: generated oracle disputed; "
                        "repair will use only uncontested failures")
                    self.metric("derived_spec_dispute", scope="final_suite",
                                tests=[list(item) for item in disputed])
            if summary.error and summary.error.startswith("generated test load blocked:"):
                self._derived_suite_load_blocked = True
                self.final_suite_green = False
                for node_id, paths in self.spec_map.items():
                    if self.generated_load_errors(paths):
                        self.test_verdict[node_id] = None
                self.metric("acceptance", scope="final_suite", verdict="blocked_test_file",
                            load_errors=summary.load_errors)
                return
            repair_summary = self.uncontested_derived_results(summary)
            score = repair_summary.passed
            if best is not None:
                best_repair = self.uncontested_derived_results(best["summary"])
                best["passed"] = best_repair.passed
                best["grouped"] = nodes_for_failures(best_repair.results, self.spec_map)
            if reused_measurement:
                log("[acceptance] reusing unchanged application measurement for a changed repair approach")
            if startup_recovery_only and self.suite_is_measured(summary, all_specs):
                # Functional failures in unimplemented leaves must not consume
                # the recovery budget or prevent the sequential queue resuming.
                grouped = nodes_for_failures(summary.results, self.spec_map)
                self.record_full_suite(summary, grouped)
                self.remember_delivery_checkpoint(summary, grouped)
                self.metric('acceptance', scope='startup_suite', round=attempt,
                            passed=summary.passed, total=summary.total, verdict='measured')
                self._unresolved_startup_error = ''
                self.final_startup_recovered = True
                return
            if (best is not None and last_repair_mode == "codegen" and wrote_last
                    and self.suite_is_measured(summary, all_specs) and best["passed"] - score >= 3):
                # A one-request rewrite that breaks several previously passing
                # behaviours is different from a single flaky spec or a tool
                # turn interrupted halfway through. Keep the measured evidence,
                # but repair from the last good tree rather than spending another
                # codegen round on the damage (Keep 62886df9bde1: 31 -> 25).
                damaged = nodes_for_failures(repair_summary.results, self.spec_map)
                newly_broken = {n for n in damaged if n and n not in best["grouped"]}
                if len(newly_broken) >= 2 and best["sha"]:
                    log(f"[acceptance] full suite: codegen repair regressed {best['passed']} -> "
                        f"{score}, newly failing {sorted(newly_broken)}; restoring best state")
                    self.restore_app(best["sha"])
                    restored_this_round = True
                    self.pending_corrections.append(
                        f"The last broad codegen repair broke {', '.join(sorted(newly_broken))}. "
                        "The harness restored frontend/ and backend/ to the best state. "
                        "Repair the original failure with a targeted edit; preserve passing behaviours.")
                    summary = measured_suite()
                    if getattr(self, "derived_as_specs", False):
                        summary = self.audit_related_derived_specs(all_specs, summary)
                    repair_summary = self.uncontested_derived_results(summary)
                    score = repair_summary.passed
                    force_tool_repair = True
                    last_repair_mode = ""
            initially_green = summary.all_passed and self.suite_is_measured(summary, all_specs)
            reviewed_summary = summary
            if initially_green:
                # A single lucky 32/32 did not reproduce in the platform's next
                # clean run (Keep 62886df9bde1: 32/32 -> 30/32). Confirmation
                # uses the unchanged app and costs no model tokens.
                for confirmation in range(1, confirm_runs):
                    confirmed = measured_suite()
                    if not confirmed.all_passed or not self.suite_is_measured(confirmed, all_specs):
                        owners = {Path(path).name: node for node, paths in self.spec_map.items()
                                  for path in (paths or [])}
                        passed_a_round.update(owners.get(Path(r.file or "").name)
                                              for r in self.uncontested_derived_results(summary).results if r.ok)
                        passed_a_round.discard(None)
                        log(f"[acceptance] full suite confirmation {confirmation + 1}/{confirm_runs}: "
                            f"{confirmed.passed}/{confirmed.total}; first green run was not stable")
                        summary = confirmed
                        break
                    log(f"[acceptance] full suite confirmation {confirmation + 1}/{confirm_runs}: "
                        f"{confirmed.passed}/{confirmed.total}")
            # A near-green suite can be flaky without ever producing a lucky
            # all-green round. Confirm the first high-scoring partial result on
            # the unchanged tree before spending a repair turn. Limit this to
            # a few failures and require enough time to confirm, repair and
            # remeasure; ordinary low-scoring suites keep their existing path.
            partial_ratio = float(os.environ.get("OCTOS_ARC_PARTIAL_CONFIRM_RATIO", "0.9"))
            partial_max = max(0, int(os.environ.get("OCTOS_ARC_PARTIAL_CONFIRM_MAX_FAILURES", "3")))
            partial_failed = max(0, repair_summary.total - repair_summary.passed)
            if (attempt == 0 and not reused_measurement and attempt < rounds
                    and not initially_green and 0 < partial_ratio <= 1
                    and not summary.all_passed and self.suite_is_measured(summary, all_specs)
                    and repair_summary.total
                    and repair_summary.passed / repair_summary.total >= partial_ratio
                    and 0 < partial_failed <= partial_max
                    and self.remaining() >= self.final_retry_admission()):
                first_partial = summary
                confirmed = measured_suite()
                if self.suite_is_measured(confirmed, all_specs):
                    owners = {Path(path).name: node for node, paths in self.spec_map.items()
                              for path in (paths or [])}
                    passed_a_round |= {owners.get(Path(r.file or "").name)
                                       for r in first_partial.results if r.ok} - {None}
                    changed = failure_signature(first_partial) != failure_signature(confirmed)
                    log(f"[acceptance] near-green unchanged confirmation: "
                        f"{confirmed.passed}/{confirmed.total}; failing set "
                        f"{'changed (unstable)' if changed else 'reproduced'}")
                    self.metric("acceptance_confirmation", scope="final_suite", confirmation="near_green",
                                first_passed=first_partial.passed, confirmed_passed=confirmed.passed,
                                total=confirmed.total, failing_set_changed=changed)
                    summary = confirmed
                else:
                    log("[acceptance] near-green unchanged confirmation had no complete verdict; "
                        "retaining the first measured result")
            if summary is not reviewed_summary and getattr(self, "derived_as_specs", False):
                summary = self.audit_related_derived_specs(all_specs, summary)
            repair_summary = self.uncontested_derived_results(summary)
            score = repair_summary.passed
            if self.disputed_generated_failures(summary):
                self.final_spec_dispute = True
            if summary.error and summary.killed:
                log(f"[acceptance] full suite could not run ({summary.error[:120]}); keeping per-node verdicts")
                break
            measured = self.suite_is_measured(summary, all_specs)
            self.verify_repair_memory(summary, measured)
            if not measured:
                error = summary.error or "\n".join(summary.load_errors) or "Incomplete acceptance report; not all specs produced results"
                log(f"[acceptance] full suite has no complete verdict: {error[:300]}")
                if summary.killed or re.search(r'time(?:d)?\s*out|budget exhausted|exceeded', error, re.I):
                    # A timed-out 0/0 says nothing about application behavior.
                    # Keep individually measured verdicts and the last safe
                    # source; repairing from an empty functional report would
                    # risk replacing working features.
                    self.metric('acceptance', scope='final_suite', round=attempt,
                                passed=0, total=0, verdict='unknown', error=error[:300])
                    break
                for node_id in self.spec_map:
                    if node_id:
                        self.test_verdict[node_id] = None
                grouped = {None: []}
                failures = (f"- Feature: application startup exactly as the grader runs it (only PORT set)\n"
                            f"  Failed at: build/start/test loading\n  Observation: {startup_error_digest(error)}\n"
                            "  No complete functional verdict. Fix the reported infrastructure problem in place; do not rewrite the app.")
            else:
                grouped = nodes_for_failures(repair_summary.results, self.spec_map)
                failures = failure_summaries(repair_summary) + failure_source_context(repair_summary, self.tests_dir)
                failures += self.interference_note(grouped, passed_alone, summary.stores_written)
                failures += self.intermittent_note(grouped, passed_a_round)
                failures += self.worker_parity_note(workers)
                owners = {Path(path).name: node for node, paths in self.spec_map.items()
                          for path in (paths or [])}
                passed_a_round |= {owners.get(Path(r.file or "").name)
                                   for r in repair_summary.results if r.ok} - {None}
                if (best is not None and wrote_last and not restored_this_round and best.get("sha")
                        and score == best["passed"]):
                    current_failed = frozenset((Path(r.file or "").name, r.title)
                                               for r in repair_summary.results if not r.ok)
                    best_failed = frozenset((Path(r.file or "").name, r.title)
                                            for r in self.uncontested_derived_results(best["summary"]).results
                                            if not r.ok)
                    if current_failed != best_failed:
                        newly_broken = sorted(current_failed - best_failed)
                        newly_fixed = sorted(best_failed - current_failed)
                        self.restore_app(best["sha"])
                        restored_this_round = True
                        force_tool_repair = True
                        last_repair_mode = ""
                        self.pending_corrections.append(
                            "The previous repair kept the same pass count but exchanged failures: it fixed "
                            f"{', '.join(f'{f}:{t}' for f, t in newly_fixed[:4]) or 'some prior failures'} while "
                            f"breaking {', '.join(f'{f}:{t}' for f, t in newly_broken[:4]) or 'other passing tests'}. "
                            "The harness restored the previously measured best state. Target its remaining failure "
                            "without regressing the passing set.")
                        log("[acceptance] full suite: equal-score repair exchanged failing tests; "
                            "restoring the previously measured best state")
                        self.metric("repair_oscillation", scope="final_suite", passed=summary.passed,
                                    newly_broken=[list(x) for x in newly_broken],
                                    newly_fixed=[list(x) for x in newly_fixed])
                        summary, grouped = best["summary"], best["grouped"]
                        repair_summary = self.uncontested_derived_results(summary)
                        score = repair_summary.passed
                        failures = failure_summaries(repair_summary) + failure_source_context(repair_summary, self.tests_dir)
                        failures += self.interference_note(grouped, passed_alone, summary.stores_written)
                        failures += self.intermittent_note(grouped, passed_a_round)
                        failures += self.worker_parity_note(workers)
            log(f"[acceptance] full suite round {attempt}: {summary.passed}/{summary.total}; failing nodes "
                f"{sorted(k for k in grouped if k) or ('all' if None in grouped and not summary.results else [])}")
            self.metric("acceptance", scope="final_suite", round=attempt, passed=summary.passed,
                        total=summary.total, after_applied_repair=wrote_last and not restored_this_round,
                        reused_measurement=reused_measurement,
                        restored_before_measurement=restored_this_round,
                        verdict="measured" if measured else "unknown", error=summary.error,
                        load_errors=summary.load_errors)
            self.record_full_suite(summary, grouped)
            self.remember_delivery_checkpoint(summary, grouped)
            last_passed = score if measured else -1
            if measured and (best is None or score > best["passed"]):
                if best is not None and wrote_last and not restored_this_round:
                    self.final_suite_progress = True
                if attempt > 0:
                    self.commit(f"chore: full acceptance suite {summary.passed}/{summary.total} (best so far)")
                best = {"passed": score, "sha": self.head(), "summary": summary, "grouped": grouped}
                regressions = 0
            elif measured and best is not None and score < best["passed"]:
                # The per-node loop already does this; the full-suite pass did not.
                # A repair cut at the per-turn timeout leaves the tree part
                # written: cloud 6e82a7ff571c went 27/32 -> repair killed at 1200s
                # -> 17/32, and the rounds after it repair that instead of the
                # five failures the pass began with. Two rounds behind the best
                # is a trend rather than one flaky spec, which is the same
                # threshold the node loop uses.
                #
                # Two and not one, and the same run shows why: 6e82a7ff571c went
                # 27/32, lost a repair to the timeout, measured 17/32, lost the
                # next repair to the timeout as well -- and then measured 28/32,
                # past the best it had. A rollback on the first dip would have
                # returned to 27 and never reached 28. Damage from a cut turn is
                # recoverable, so this waits for a trend and the pass still
                # delivers its best round either way.
                regressions += 1
                if regressions >= 2 and best["sha"]:
                    self.restore_app(best["sha"])
                    self.pending_corrections.append(
                        f"Your last two full-suite repairs made the tests worse; the harness restored frontend/ and "
                        f"backend/ to the best state ({best['passed']}/{best['summary'].total}). Start from that code.")
                    log(f"[acceptance] full suite: two rounds behind {best['passed']}/{best['summary'].total}; "
                        f"restored the best state")
                    # The tree is the best round's again, so the verdicts have to be
                    # too, and the restore at the end of the pass has nothing left
                    # to do.
                    self.record_full_suite(best["summary"], best["grouped"])
                    last_passed = best["passed"]
                    regressions = 0
            self.final_safe_failures_remaining = measured and bool(grouped)
            if measured and not grouped and self.disputed_generated_failures(summary):
                log("[acceptance] full suite: only disputed generated failures remain; "
                    "their scenarios stay unverified")
                return
            if measured and not grouped:
                weak = [node for node, paths in self.spec_map.items()
                        if node and paths and self.derived_review_needed(node)]
                self.final_suite_green = True
                if weak:
                    log(f"[acceptance] full suite passes, but {len(weak)} derived leaf/leaves "
                        "have no behavioural spec and remain unverified")
                    self.metric("derived_spec_coverage", outcome="unverified",
                                nodes=weak, passed=summary.passed, total=summary.total)
                self.commit(f"chore: full acceptance suite {summary.passed}/{summary.total} "
                            + ("green; derived scenario coverage unresolved" if weak else "pass (full suite)"))
                return
            # A spec that has passed once in this pass and fails now is unstable;
            # letting it count as progress hides a stall in everything else.
            unstable = frozenset(spec for node in passed_a_round
                                 for spec in (self.spec_map.get(node) or []))
            failing_signature = failure_signature(repair_summary, unstable)
            if wrote_last and previous_failing is not None and failing_signature == previous_failing:
                if repeated:
                    log("[acceptance] full suite: failures unchanged after a changed approach; stopping repairs")
                    break
                # Cloud 3ffe9702bf15: the suite stalled at 26/32 and the run ended
                # with most of its budget unspent. One identical round means the
                # repair missed the cause, not that the cause cannot be fixed --
                # tell it so, the way the per-node path already does, and retry.
                repeated = True
                failures += self.last_repair_diff()
                # A repair that ran out before editing has an unfinished plan worth
                # continuing; one that edited and moved nothing does not -- there the
                # instruction below is to change the cause, so carrying its reasoning
                # forward would argue against the correction in the same prompt.
                if wrote_last:
                    unfinished = ""
                log("[acceptance] full suite: same failures as the previous round; changing repair approach")
                self.pending_corrections.append(
                    'Repeated attempts produced the same observed failure. Recheck the assumptions behind the repair: inspect expected and received values, preceding actions, locator scope, and actual application state. Change the cause supported by this evidence. Do not manufacture the expected output or bypass the underlying operation; preserve behavior for other inputs.')
            else:
                repeated = False
            previous_failing = failing_signature
            if (attempt == rounds or self.remaining() < self.final_measurement_reserve() + self.repair_minimum()
                    or self.wound_down()):
                break
            failing = sorted(k for k in grouped if k) or ["all nodes"]
            if measured and len(failing) > 1:
                from source_index import failure_groups, select_repair_groups
                clusters = failure_groups({k: v for k, v in grouped.items() if k}, self.requirement_source_targets())
                visits = getattr(self, "_repair_group_visits", {})
                active = select_repair_groups(clusters, visits, rounds - attempt)
                self._repair_group_visits = visits
                if len(clusters) > 1:
                    overview = f"All failing requirement IDs: {', '.join(failing)}. Active repair group: {', '.join(active)}. Other groups are deferred, not passed.\n"
                    focused = RunSummary(results=[r for n in active for r in grouped[n]])
                    failures = overview + failure_summaries(focused) + failure_source_context(focused, self.tests_dir)
                    active_grouped = {n: grouped[n] for n in active}
                    failures += self.interference_note(active_grouped, passed_alone, summary.stores_written)
                    failures += self.intermittent_note(active_grouped, passed_a_round)
                    failures += self.worker_parity_note(workers)
                    failing = active
                    self.metric("repair_group", active=active, groups=clusters)
            failures += self.store_change_note(summary)
            failures += self.unfinished_repair_note(unfinished)
            prompt = self.app_repair_prompt(
                node_id=", ".join(failing), passed=summary.passed, total=summary.total, failures=failures,
                test_location=self.repair_test_location(),
                sources=self.repair_requirements() + self.sources_text(),
                corrections=self.corrections_text() + "The full suite runs all spec files against one "
                "server; tests from different files must not interfere through shared server state "
                "(e.g. a counter that every browser session shares). Keep persisted data only where the "
                "requirement demands persistence.\n",
                slow="", smoke=self.smoke_port, port=self.web_port)
            # One codegen request first; a round that reproduced the previous failures
            # is the changed approach, and that one uses tools.
            before_repair_digest = self.app_source_digest()
            last_repair_mode, unfinished = self.suite_repair_turn(
                f"full-suite repair {attempt + 1}/{rounds}", failing if measured else [], failures,
                min(self.suite_repair_timeout(), max(1, self.remaining() - self.final_measurement_reserve())),
                tool_prompt=prompt, prefer_codegen=not repeated and not force_tool_repair)
            force_tool_repair = False
            committed = self.commit(f"fix: full-suite repair {attempt + 1}")
            effective = getattr(self, "last_repair_changed", None)
            wrote_last = effective if isinstance(effective, bool) else committed
            if effective is False:
                self.final_repair_no_change = True
                if self.app_source_digest() == before_repair_digest:
                    self._final_retry_measurement = (summary, before_repair_digest)
                self._force_final_tool_repair = True
                self.pending_corrections.append(
                    "The previous full-suite repair changed no application source. Do not only describe a fix: "
                    "inspect the current implementation and apply a concrete, targeted source edit before verification.")
                log("[acceptance] full suite: repair changed no application sources; "
                    "deferring remeasurement and changing approach on the next pass")
                break
        # L17 (ported from the Rust harness): deliver the best full-suite round, not the last one.
        if best is not None and best["sha"] and last_passed < best["passed"]:
            self._final_retry_measurement = None
            log(f"[acceptance] full suite: last round {last_passed} < best {best['passed']}; restoring the best state")
            self.restore_app(best["sha"])
            self.record_full_suite(best["summary"], best["grouped"])
            self.commit(f"chore: keep best full-suite state {best['passed']}/{best['summary'].total}")

    def suite_repair_timeout(self) -> int:
        """How long a repair that answers the whole suite at once may take.

        `node_timeout` bounds a turn about one node; this bounds a turn about
        every failing node together, and the two are not the same size of job.
        They default to the same number. Measured on the runs of 2026-09-16, an
        hour apart, because the first reading was misleading. At 207 node-phase
        turns not one had reached the 1200s cap, longest 1049s, while both of
        6e82a7ff571c's full-suite repairs were cut at it -- which looked like
        the suite repairs being the long ones. By 261 turns prestashop had a
        node-phase turn cut at 1200s on a 2 GiB container, and six turns sat
        past 890s. So the long turns are not particular to the full suite, nor
        to 6e82a7ff571c's 512 MiB box; six runs sharing one provider queue
        behind each other. Keep the two separate anyway, so the suite one can
        move without shortening or lengthening every node turn with it.
        """
        return int(os.environ.get("OCTOS_SUITE_REPAIR_TIMEOUT", str(self.node_timeout)))

    def final_measurement_reserve(self) -> float:
        configured = os.environ.get("OCTOS_ARC_FINAL_MEASUREMENT_SECONDS")
        if configured:
            return max(30, float(configured))
        return max(120, 1.25 * getattr(self, "last_suite_seconds", 0) + 10)

    @staticmethod
    def suite_is_measured(summary: RunSummary, specs: list[str]) -> bool:
        observed = {str(r.file or "").replace("\\", "/") for r in summary.results}
        return bool(specs and not summary.error and not summary.killed and not summary.load_errors
                    and summary.results and summary.total == len(summary.results)
                    and all(r.status in {"passed", "failed", "timedOut", "quarantined"} for r in summary.results)
                    and all(any(path == spec or path.endswith("/" + spec) for path in observed) for spec in specs))

    def final_acceptance_passes(self) -> None:
        """Admit at most one affordable full suite after generation is attempted."""
        if getattr(self, "_final_suite_attempted", False):
            return
        self._final_suite_attempted = True
        if self.runner is None or not self.tests_dir:
            log('[acceptance] no local specs available; skipping unmeasured full-suite repair passes')
            return
        if getattr(self, "derived_as_specs", False):
            # A generated suite has smoke, disputed, and unreviewed cases in
            # the same files. Choose a small number of files with at least one
            # independently approved behavior case; filter their results before
            # any product verdict. Never run every generated file by default.
            candidates = []
            for path in sorted(self.tests_dir.glob("*.spec.ts")):
                node_id = path.name.removesuffix(".spec.ts")
                source = path.read_text(encoding="utf-8")
                titles = [match.group(1).replace("\\'", "'") for match in re.finditer(
                    r"(?m)^\s*test\('((?:\\.|[^'\\])*)',", source)]
                if any(self.trusted_derived_case(node_id, title) for title in titles):
                    risk = bool(re.search(r"sign.?in|sign.?out|password|permission|access|persist|save|formula|delete",
                                          str(getattr(self, "requirement_nodes", {}).get(node_id, {}).get("description") or ""), re.I))
                    candidates.append((not risk, node_id, path.name, max(1, len(titles))))
            candidates.sort()
            timeout_s = max(1, getattr(self.runner, "timeout_ms", 30000) / 1000)
            allowance = min(300.0, max(0.0, self.remaining() - self.final_measurement_reserve()))
            selected, estimate = [], 30.0
            for _, _, spec, count in candidates:
                cost = 30.0 + count * timeout_s
                if estimate + cost <= allowance:
                    selected.append(spec)
                    estimate += cost
            if not selected:
                self.metric("acceptance", scope="derived_focused_admission", decision="deferred",
                            reviewed_files=len(candidates), remaining_seconds=round(self.remaining()))
                return
            observed = self.run_specs(selected, workers=1, grader_like=True)
            measured = self.suite_is_measured(observed, selected)
            self.metric("acceptance", scope="derived_focused_admission", decision="measured" if measured else "unknown",
                        selected=selected, passed=observed.passed, total=observed.total)
            if measured:
                self.record_full_suite(observed, {}, scope=selected)
            return
        configured_passes = os.environ.get("OCTOS_FINAL_SUITE_PASSES")
        # A large implementation allowance is not permission for hundreds of
        # full-suite repair passes. Each pass already contains several repairs.
        passes = max(1, int(configured_passes)) if configured_passes is not None else 1
        stalled_passes = 0
        unchanged_passes = 0
        retry_measurement = None
        if self.runner is not None and self.tests_dir:
            all_specs = sorted(str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob('*.spec.ts'))
            proven_specs = sorted({spec for node, verdict in self.test_verdict.items() if verdict is True
                                   for spec in self.spec_map.get(node, [])})
            timeout_s = max(1, getattr(self.runner, 'timeout_ms', 30000) / 1000)
            workers = max(1, self.final_workers())
            def estimate(paths: list[str]) -> float:
                cases = 0
                for rel in paths:
                    try:
                        cases += len(re.findall(r"(?m)^\s*test\('", (self.tests_dir / rel).read_text(encoding="utf-8")))
                    except OSError:
                        cases += 1
                return max(30, 60 + 1.2 * max(len(paths), cases) * timeout_s / workers)
            proven_estimated = estimate(proven_specs)
            if (proven_specs and len(proven_specs) < len(all_specs)
                    and self.remaining() >= proven_estimated + 20):
                observed = self.run_specs(proven_specs, workers=self.final_workers(), grader_like=True)
                measured = self.suite_is_measured(observed, proven_specs)
                self.metric('acceptance', scope='entered_final_checkpoint', passed=observed.passed,
                            total=observed.total, checked_specs=len(proven_specs),
                            unentered_specs=len(all_specs) - len(proven_specs),
                            verdict='measured' if measured else 'unknown')
                if measured:
                    for node, verdict in list(self.test_verdict.items()):
                        if verdict is not True:
                            continue
                        paths = self.spec_map.get(node, [])
                        rows = [row for row in observed.results if any(
                            str(row.file or '').replace('\\', '/') == path or
                            str(row.file or '').replace('\\', '/').endswith('/' + path) for path in paths)]
                        local = RunSummary(results=rows, total=len(rows), passed=sum(row.ok for row in rows))
                        self.test_verdict[node] = (None if local.all_passed and self.derived_review_needed(node)
                                                   else local.all_passed) if self.suite_is_measured(local, paths) else None
                        if self.test_verdict[node] is not None:
                            self.record_tests(node, paths, local)
                log(f'[acceptance] entered final checkpoint: {observed.passed}/{observed.total} '
                    f'over {len(proven_specs)} previously passing specs')
            proxy = getattr(self, 'llm_proxy', None)
            if isinstance(proxy, LlmProxy) and proxy.provider_unavailable:
                log('[acceptance] provider circuit open; preserving measured source without final model repairs')
                return
            estimated = estimate(all_specs)
            cap = max(60, int(os.environ.get("OCTOS_ARC_FULL_SUITE_SECONDS_CAP", "900")))
            final_startup_buffer = min(120.0, max(30.0, self.remaining() * .30))
            if estimated > min(cap, max(0, self.remaining() - final_startup_buffer)):
                log(f'[acceptance] full suite deferred: {len(all_specs)} specs, estimated '
                    f'{estimated:.0f}s from case count; cap {cap}s, {self.remaining():.0f}s remains')
                self.metric('acceptance', scope='full_suite_admission', decision='deferred',
                            specs=len(all_specs), estimated_seconds=round(estimated), cap_seconds=cap,
                            remaining_seconds=round(self.remaining()))
                return
        for attempt in range(passes):
            # Admission for measurement is distinct from admission for repair.
            # The old 3 * 300s floor skipped even the first measurement in a
            # 600s run. Reserve time for a measured delivery, not another turn.
            if self.time_up() or self.remaining() < self.final_measurement_reserve():
                break
            if attempt:
                if self.wound_down():
                    break
                if (getattr(self, "final_suite_green", False)
                        or (self.test_verdict and all(verdict is True for verdict in self.test_verdict.values()))):
                    break
                log(f"[flow] full suite still failing with {self.remaining():.0f}s left; "
                    f"pass {attempt + 1}/{passes}")
            if retry_measurement and retry_measurement[1] == self.app_source_digest():
                self.final_acceptance(initial_summary=retry_measurement[0])
            else:
                self.final_acceptance()
            retry_measurement = None
            if getattr(self, "_derived_suite_load_blocked", False):
                break
            if self.driver:
                self.driver.end_scope("node")
            if (getattr(self, "final_spec_dispute", False)
                    and not getattr(self, "final_safe_failures_remaining", False)):
                break
            if (getattr(self, "final_suite_green", False)
                    or (self.test_verdict and all(verdict is True for verdict in self.test_verdict.values()))):
                break
            if self.wound_down():
                log(f"[flow] full suite still failing, but the cost guard is spent ({self.turn_count} build "
                    f"turns / limit {self.max_turns}); {self.remaining():.0f}s left unused")
                break
            if self.remaining() < self.final_retry_admission():
                log(f"[flow] full suite still failing, but {self.remaining():.0f}s is below the "
                    f"{self.final_retry_admission():.0f}s needed to measure, repair, and remeasure")
                break
            if getattr(self, "final_repair_no_change", False) is True:
                unchanged_passes = (1 if getattr(self, 'final_suite_progress', False) is True
                                    else unchanged_passes + 1)
                if unchanged_passes >= 2:
                    log("[flow] two final passes ended without effective edits; stopping repair loop")
                    break
                retry_measurement = getattr(self, '_final_retry_measurement', None)
                self._force_final_tool_repair = True
                self.pending_corrections.append(
                    "The previous final repair made no effective application edit. Use the retained failure "
                    "evidence to fix one concrete blocking cause with a targeted edit; avoid broad rereads.")
                if getattr(self, 'final_suite_progress', False) is True:
                    stalled_passes = 0
                log("[flow] final repair unchanged; allowing one bounded changed approach")
                continue
            unchanged_passes = 0
            if getattr(self, "final_suite_progress", False) is not True:
                stalled_passes += 1
                if stalled_passes >= 2:
                    log("[flow] two full-suite passes without measured improvement; stopping repair loop")
                    break
                self._force_final_tool_repair = True
                self.pending_corrections.append(
                    "The previous full-suite pass did not increase the measured pass count. Reinspect the failing "
                    "interaction end to end and use a different targeted repair approach; preserve the best state.")
                log("[flow] full-suite pass made no measured pass-count improvement; "
                    "allowing one changed approach before stopping")
            else:
                stalled_passes = 0

    GRADER_WORKERS = 1  # observed platform logs; configurable for other graders

    @classmethod
    def grader_workers(cls) -> int:
        return max(1, int(os.environ.get("OCTOS_ARC_GRADER_WORKERS", str(cls.GRADER_WORKERS))))

    @classmethod
    def final_workers(cls) -> int:
        return max(1, int(os.environ.get("OCTOS_ARC_FINAL_WORKERS", str(cls.grader_workers()))))

    @classmethod
    def worker_parity_note(cls, workers: int) -> str:
        """Say so when the suite could not be run the way it will be graded.

        A memory limit can force the count below the grader's (`workers_for_final`),
        and then this run is not the run that scores the app.

        An earlier version of this note claimed the count decides *which* tests
        fail, from two runs at each of one and four workers. More repeats
        disproved it: the same two nodes swap places between repeats at a fixed
        count as well, so that difference is the flakiness #175 reports, not the
        worker count. What is left is the parity gap itself, which is reason
        enough not to read the list as the set that will be scored.
        """
        expected = cls.grader_workers()
        if workers == expected:
            return ""
        return (f"\n\nThis suite ran with {workers} worker(s); expected grading concurrency is {expected} against one "
                "server, so concurrency is not matched. Fix the cause these failures share "
                "rather than the exact list, which a differently loaded run need not reproduce.")

    @staticmethod
    def intermittent_note(grouped: dict, passed_a_round: set) -> str:
        """Name the behaviours that already passed once in this pass.

        Running the same 32 specs three times over one unchanged app gave 25,
        24 and 25: REQ-2.7.1 failed once and passed twice. A repair told only
        that it failed goes looking for a missing feature, when what it has is a
        race — and the grader runs with retries off, so it stays worth fixing.
        """
        flaky = sorted(node for node in grouped if node and node in passed_a_round)
        if not flaky:
            return ""
        return ("\n\nThese already passed in an earlier round of this same pass and fail now: "
                f"{', '.join(flaky)}. The behaviour exists; what is missing is that it settles "
                "reliably. Look for a race, an unawaited update or state left over from another "
                "session rather than for an unimplemented feature.")

    @staticmethod
    def interference_note(grouped: dict, passed_alone: set, stores_written: list | None = None) -> str:
        """Name the behaviours that only fail in company.

        Cloud 746c81a2b5aa lost REQ-5.1 this way: it passed on its own and failed
        in the suite, where every spec drives the same server. Saying which
        failures are of that kind separates "the behaviour is wrong" from "the
        behaviour does not survive another session touching the same state" —
        the evidence for both looks identical otherwise.

        The claim is only as fresh as the per-node verdict it rests on, and later
        nodes change the app. Measured on one delivered app, seven of its eight
        suite failures also failed with the rest of the suite removed, so the note
        asks for the check rather than asserting the conclusion.
        """
        solo = sorted(node for node in grouped if node and node in passed_alone)
        if not solo:
            return ""
        note = ("\n\nThese passed their own node run earlier and fail now that every spec drives one "
                f"server: {', '.join(solo)}. That earlier result is from before the later nodes were "
                "built, so check the behaviour still works on its own: if it does, the difference is "
                "state shared with the other sessions; if it does not, it was broken since.")
        if stores_written:
            note += (" The suite run left these files changed on disk: "
                     f"{', '.join(stores_written)} — whatever one session writes there is still there for "
                     "the next.")
        return note

    @staticmethod
    def store_change_note(summary: RunSummary) -> str:
        """Make suite side effects visible to repair without exposing values."""
        changes = getattr(summary, 'store_changes', None) or []
        if not changes:
            return ""
        return ("\n\nPersisted JSON changed during this test run (structural diff from the "
                "pre-run snapshot, not attribution to a particular test): " +
                "; ".join(changes) + ". Compare these records with required initial "
                "state and the actions that preceded each failure; do not reset user data to fix a collision.")

    def remember_delivery_checkpoint(self, summary: RunSummary, grouped: dict) -> None:
        """Keep a source snapshot only after a complete, usable suite observation.

        Node passes are not comparable to a full suite. Build errors, missing
        spec files and interrupted runners must never replace this checkpoint.
        """
        if (getattr(self, "runtime", None) is None or not self.tests_dir
                or summary.error or summary.killed or summary.load_errors):
            return
        expected = {str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob("*.spec.ts")}
        observed = {str(r.file or "").replace("\\", "/") for r in summary.results}
        if (not expected or not summary.results or summary.total != len(summary.results)
                or any(r.status not in {"passed", "failed", "timedOut"} for r in summary.results)
                or not all(any(path == spec or path.endswith("/" + spec) for path in observed)
                           for spec in expected)):
            return
        best = getattr(self, "delivery_checkpoint", None)
        trusted_passed = self.uncontested_derived_results(summary).passed
        if ((getattr(self, "derived_as_specs", False) and trusted_passed <= 0)
                or (best and trusted_passed <=
                    self.uncontested_derived_results(best["summary"]).passed)):
            return
        self.commit(f"chore: verified delivery checkpoint {summary.passed}/{summary.total}")
        sha = self.head()
        if not sha:
            return
        # A failed commit could otherwise attach new verdicts to an old tree.
        try:
            dirty = self.runtime.git.run(["status", "--porcelain", "--", "frontend", "backend"], check=False)
        except Exception as exc:
            log(f"[flow] delivery checkpoint skipped: could not inspect git status: {exc}")
            return
        if dirty.returncode or dirty.stdout.strip():
            log("[flow] delivery checkpoint skipped: application snapshot is not clean")
            return
        self.delivery_checkpoint = {"sha": sha, "summary": summary, "grouped": grouped}

    def recover_provider_stop(self, error: Exception) -> bool:
        """No model calls: retain interrupted edits in git, deliver measured code.

        Returning true means an artifact can be graded, NOT all tests passed.
        The run still emits a failure event with the provider's original error.
        """
        best = getattr(self, "delivery_checkpoint", None)
        if not best or self.uncontested_derived_results(best["summary"]).passed <= 0:
            return self.measure_provider_stop(error)
        try:
            self.commit("chore: preserve interrupted repair before provider-stop recovery")
            dirty = self.runtime.git.run(["status", "--porcelain", "--", "frontend", "backend"], check=False)
            if dirty.returncode or dirty.stdout.strip():
                log("[flow] provider-stop recovery skipped: interrupted edits could not be preserved")
                return False
            self.restore_app(best["sha"])
            self.test_verdict.clear()
            self.record_full_suite(best["summary"], best["grouped"])
            self.commit("chore: deliver verified checkpoint after provider stop")
            self.metric("provider_stop", recovered=True, passed=best["summary"].passed,
                        total=best["summary"].total, error=str(error)[:300])
            log(f"[flow] provider stopped; restored verified checkpoint "
                f"{best['summary'].passed}/{best['summary'].total}; no further model calls")
            return True
        except Exception as exc:  # recovery must not hide the original provider error
            log(f"[flow] provider-stop recovery failed: {exc}")
            return False

    def measure_provider_stop(self, error: Exception) -> bool:
        """Turn sequential progress into a delivery observation without an LLM.

        Partial checkpoint scores are never promoted to full-suite verdicts.
        Preserve interrupted work before considering the older healthy tree.
        """
        if self.runner is None or not self.tests_dir or self.runtime is None:
            return False
        specs = sorted(str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob('*.spec.ts'))
        if not specs or self.remaining() < 30:
            return False
        original = None
        restored = False
        try:
            self.commit('chore: preserve interrupted implementation before provider-stop measurement')
            dirty = self.runtime.git.run(['status', '--porcelain', '--', 'frontend', 'backend'], check=False)
            original = self.head()
            if not original or dirty.returncode or dirty.stdout.strip():
                return False
            healthy = getattr(self, 'healthy_checkpoint', None)
            candidates = [original]
            if healthy and healthy.get('sha') and healthy['sha'] != original:
                candidates.append(healthy['sha'])
            for sha in candidates:
                if self.remaining() < 30:
                    break
                if sha != original:
                    restored = True
                    self.restore_app(sha)
                summary = self.run_specs(specs, workers=1, grader_like=True)
                if (not self.suite_is_measured(summary, specs)
                        or self.uncontested_derived_results(summary).passed <= 0):
                    continue
                grouped = nodes_for_failures(summary.results, self.spec_map)
                self.remember_delivery_checkpoint(summary, grouped)
                self.test_verdict.clear()
                self.record_full_suite(summary, grouped)
                self.commit('chore: deliver measured implementation after provider stop')
                self.metric('provider_stop', recovered=True, measured=True,
                            passed=summary.passed, total=summary.total, error=str(error)[:300])
                log(f'[flow] provider stopped; measured delivery {summary.passed}/{summary.total}; no model calls')
                restored = False  # The measured fallback is now the delivery artifact.
                return True
        except Exception as exc:
            log(f'[flow] provider-stop measurement failed: {exc}')
        finally:
            if restored and original:
                try:
                    self.restore_app(original)
                except Exception as exc:
                    log(f'[flow] provider-stop original source restore failed: {exc}')
        return False

    def record_full_suite(self, summary: RunSummary, grouped: dict, *, scope: list[str] | None = None) -> None:
        """Per-node verdicts and traceability from one full-suite round."""
        if summary.error or summary.killed or summary.load_errors:
            return
        for node_id, specs in self.spec_map.items():
            if scope is not None and not set(specs) <= set(scope):
                continue
            if node_id and specs and summary.results:
                rows = [r for r in summary.results if any(
                    str(r.file or "").replace("\\", "/") == p or
                    str(r.file or "").replace("\\", "/").endswith("/" + p) for p in specs)]
                local = RunSummary(results=rows, total=len(rows), passed=sum(r.ok for r in rows))
                if self.suite_is_measured(local, specs):
                    self.record_tests(node_id, specs, local)
                    active = self.uncontested_derived_results(local)
                    self.test_verdict[node_id] = (False if any(not r.ok for r in active.results) else
                                                  None if self.disputed_generated_failures(local)
                                                  or not active.total or self.derived_review_needed(node_id)
                                                  else active.all_passed)
                else:
                    self.test_verdict[node_id] = None
        self.write_derived_coverage(summary)

    # -- skeleton ---------------------------------------------------------
    def skeleton(self, tree: dict) -> None:
        log("[flow] skeleton turn starting")
        prompt = SKELETON_PROMPT.format(req_dir=self.req_dir, port=self.web_port, smoke=self.smoke_port,
                                        tests=self.tests_prompt_for(None, skeleton=True))
        for attempt in range(1, 5):
            if self.time_up():
                raise RuntimeError("time budget exhausted before the skeleton existed")
            ok, text = self.turn(prompt, self.node_timeout, f"skeleton attempt {attempt}")
            if ok and not self.has_app():
                log("[flow] skeleton turn wrote no frontend/backend; nudging")
                for nudge in range(1, 3):
                    self.turn(NUDGE_PROMPT, 600, f"nudge {nudge}/2")
                    if self.has_app():
                        break
            if self.has_app():
                self.commit("chore: scaffold web application skeleton")
                return
            time.sleep(30)
        raise RuntimeError("skeleton scaffolding failed: no frontend/ and backend/ after 4 attempts")

    def has_app(self) -> bool:
        return (self.output_dir / "frontend" / "package.json").is_file() and \
            (self.output_dir / "backend" / "package.json").is_file()

    def note_startable_commit(self, git_run) -> None:
        """Remember HEAD when the app just built and started from it unchanged
        (run_specs staged the worktree; an empty cached diff means HEAD == tree)."""
        try:
            same = getattr(git_run(["diff", "--cached", "--quiet", "HEAD", "--", "frontend", "backend"]),
                           "returncode", 1) == 0
            if same:
                self.last_startable_sha = self.head()
        except Exception:  # noqa: BLE001 - bookkeeping must never fail a measurement
            pass

    def restore_startable_commit(self) -> bool:
        """After a failed rehearsal, ship the last commit that built and started
        rather than a tree that does not (v10.0 sheet: "giving up; submitting as-is")."""
        sha = getattr(self, "last_startable_sha", None)
        if not sha or sha == self.head():
            return False
        # A busy port or a slow npm can fail one attempt; never trade features for a transient error.
        server = self.app_server(grader_like=True, test_hooks=False)
        err = server.build() or server.start()
        server.stop()
        if err is None:
            log("[rehearsal] current tree builds and starts on a second check; keeping it")
            return True
        self.restore_app(sha)
        self.commit("fix: restore last startable commit after failed rehearsal")
        server = self.app_server(grader_like=True, test_hooks=False)
        err = server.build() or server.start()
        server.stop()
        if err is not None:
            log(f"[rehearsal] restored {sha[:8]} also fails: {err.splitlines()[0][:200]}")
            return False
        log(f"[rehearsal] restored last startable commit {sha[:8]}; it builds and starts cleanly")
        self.test_verdict = {key: None for key in self.test_verdict}
        return True

    # -- final ------------------------------------------------------------
    def rehearsal(self) -> bool:
        for attempt in range(1, 4):
            log(f"[rehearsal] startup rehearsal {attempt}/3 (smoke port {self.smoke_port}, grader-like env)")
            server = self.app_server(grader_like=True, test_hooks=False)
            err = server.build() or server.start()
            server.stop()
            if err is None:
                log("[rehearsal] app builds and starts cleanly")
                return True
            log(f"[rehearsal] FAILED: {err.splitlines()[0][:200]}")
            if attempt == 3 or self.remaining() < self.repair_minimum() or self.wound_down():
                if self.restore_startable_commit():
                    return True
                log("[rehearsal] giving up; submitting as-is")
                return False
            self.turn(REHEARSAL_REPAIR_PROMPT.format(error=clip_ends(err, 1200), port=self.web_port, smoke=self.smoke_port),
                      min(self.node_timeout, max(1, self.remaining())), f"rehearsal repair {attempt}")
            # Any post-acceptance edit invalidates the earlier verdicts.
            if self.last_turn_changed:
                self.test_verdict = {key: None for key in self.test_verdict}
            self.commit("fix: startup rehearsal repair")
        return self.restore_startable_commit()

    def discard_runtime_store(self) -> bool:
        """Remove the scaffold's JSON store written by our own local runs.

        Grading must start from the requirement seeds, not from records our
        self-checks created (v7.18 shipped a self-test fork repository). Only
        the task-neutral scaffold's store is removed; an existing user app
        keeps its data.
        """
        from generic_template import generic_template_active
        runtime = self.output_dir / ".arc" / "runtime-data"
        if runtime.is_dir():
            shutil.rmtree(runtime, ignore_errors=True)
        data = self.output_dir / "backend" / "data"
        if not generic_template_active(self.output_dir):
            return False
        if not data.is_dir():
            log("[flow] backend/data absent; grading starts from code seeds")
            return False
        shutil.rmtree(data, ignore_errors=True)
        log("[flow] discarded backend/data written by local runs; grading starts from seeds")
        return True

    def postflight(self) -> None:
        """Hand the box back before grading starts.

        The grader launches four Chromium workers in this cgroup the moment the
        harness returns. Cloud 746c81a2b5aa left 512 MiB to share: the suite the
        harness had just measured at 30/32 was killed four tests in and all 32
        scored as skipped. Servers a model turn left running are memory we can
        still give back, and reaping only between nodes leaves the last ones
        alive for exactly the run that cannot afford them.
        """
        if self.driver:
            self.driver.close()
        self.cleanup_playwright()
        self.stop_llm_proxy()
        strays = reap_workspace_processes(self.output_dir, log)
        if strays:
            log(f"[flow] reaped {strays} leftover process(es) before grading")
        if getattr(self, "output_dir", None) is not None:
            self.discard_runtime_store()

    # -- run --------------------------------------------------------------
    def run(self) -> int:
        self.runtime = AgentRuntime.from_env(project_dir=str(self.output_dir))
        self.events = self.runtime.events
        self.events.mark_run_started("octos bundle started")
        ordered: list[dict] = []
        watchdog_stop = threading.Event()
        try:
            from generation_checks import adapter_fingerprint
            provenance = adapter_fingerprint(BUNDLE_DIR)
            self.metric('adapter_provenance', **provenance)
            log(f"[flow] adapter source sha256={provenance['sha256']} ({provenance['scope']})")
            previous = previous_requirement_records(self.output_dir)
            tree = load_requirement_tree(self.req_dir)
            self.runtime.traceability.store_requirement_tree(tree)
            # Generation reads one consistent seed; the platform keeps the original tree.
            tree = self.resolve_seed_conflicts(tree)
            self.requirement_tree = tree
            ordered = topo_order(tree)
            self.requirement_nodes = {str(node.get("id")): node for node in ordered}
            if not ordered:
                raise ValueError("no ATOMIC requirement nodes found")
            self.classify_tree(tree)
            node_ids = [str(n.get("id")) for n in ordered]
            if not self.budget_explicit:
                # 32-node trees need hours, not the 1-hour smoke default.
                self.budget = max(self.budget, self.seconds_per_node * len(ordered))
            log(f"[flow] {len(ordered)} atomic nodes in dependency order: {node_ids}; time budget {self.budget}s")
            self.folder_children = folder_descendants(tree)

            self.evolution = self.has_app()
            unchanged: set[str] = set()
            if self.evolution:
                unchanged = unchanged_node_ids(ordered, previous)
                log(f"[flow] evolution mode: existing app detected; unchanged nodes {sorted(unchanged)}, "
                    f"to implement {[i for i in node_ids if i not in unchanged]}")
            self.nodes_to_implement = len([n for n in node_ids if n not in unchanged])
            self.n_nodes = len(ordered)
            if not self.repair_rounds_explicit and self.n_nodes > 2:
                self.repair_rounds = 3  # big trees: identical-failure/no-improvement stops make 5 rounds rare anyway
            if self.max_total_tokens < 0:
                self.max_total_tokens = max(6_000_000, 2_500_000 * self.n_nodes)   # ~3x the calibrated 0.8M/node
            if self.max_turns < 0:
                self.max_turns = max(24, 4 * self.n_nodes)                          # ~3.5x the calibrated 1.1/node
            log(f"[guard] cost guard: {self.max_total_tokens} tokens / {self.max_turns} turns"
                + (f" / absolute {self.max_total_tokens_abs}" if self.max_total_tokens_abs else ""))

            self.tests_dir = locate_acceptance_tests(tree, BUNDLE_DIR)
            if self.tests_dir:
                specs = sorted(str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob("*.spec.ts"))
                self.spec_map, self.aliases = map_specs_to_nodes(specs, node_ids)
                log(f"[tests] {len(specs)} spec files at {self.tests_dir}; mapping "
                    f"{ {k: v for k, v in self.spec_map.items() if v} }; aliases {self.aliases}")
            else:
                self.requirement_contracts = compile_contracts(ordered)
                contract_path = self.output_dir / ".arc" / "requirement-contracts.json"
                save_contracts(contract_path, self.requirement_contracts)
                log(f"[tests] no acceptance specs found; wrote deterministic requirement contract for "
                    f"{len(ordered)} node(s) to {contract_path}")
                # No official specs: compile specs from requirements.yaml and run
                # the SAME measured flow as with official specs. The only extra
                # step is the spec generation (plus a bounded model review below).
                if self.prepare_derived_tests(ordered):
                    self.adopt_derived_specs(node_ids)

            self.maybe_probe(node_ids)
            self.runtime.git.ensure_repo()
            self.setup_playwright()
            if not getattr(self, "derived_as_specs", False):
                unchanged = self.probe_existing_app(node_ids, unchanged)

            dry_run = os.environ.get("OCTOS_ARC_DRYRUN") == "1"
            if dry_run:
                octos_bin = "(dry run: no kernel)"
                log("[octos] OCTOS_ARC_DRYRUN=1: fixed placeholder replies, no model calls")
            else:
                octos_bin = find_octos()
            log(f"[octos] binary {octos_bin}")
            data_dir = Path(tempfile.mkdtemp(prefix="octos-data-"))
            protected = [p for p in (self.tests_dir, self.req_dir) if p and p.is_dir()]
            config_dir = Path(tempfile.mkdtemp(prefix="octos-config-"))
            self.start_llm_proxy()
            env = build_octos_env(config_dir, protected)
            write_profile_defaults(data_dir, config_dir, protected_hooks(protected))
            env["PORT"] = str(self.smoke_port)  # a bare `npm start` inside a turn must not hit the grading port
            # ...nor write its records into backend/data, where a later snapshot would take them for seeds.
            env["ARC_DATA_DIR"] = str(self.runtime_data_dir("tools"))
            self.driver = DryRunDriver() if dry_run else OctosDriver(
                octos_bin, self.output_dir, env, data_dir, int(os.environ.get("OCTOS_MAX_ITERATIONS", "500")),
                events_log=self.output_dir / ".arc" / "octos-events.jsonl")
            self.driver.hooks = protected_hooks(protected)
            proxy = getattr(self, "llm_proxy", None)
            if isinstance(proxy, LlmProxy):
                self.driver.upstream_pending = lambda: proxy.upstream_pending
            # The mechanical suite already exists. Model augmentation and
            # review run in one bounded startup stage after design.
            self.snapshot_protected()
            threading.Thread(target=_port_watchdog, args=(self.web_port, self.output_dir, watchdog_stop),
                             daemon=True).start()
            try:
                self.prepare_build(tree, ordered)
                self.prime_generation_dependencies()
                try:
                    self.preflight_derived_specs(ordered)
                except Exception as exc:  # test planning cannot block the application
                    self.derived_specs_frozen = True
                    self.metric("derived_preflight", outcome="unavailable", reason=str(exc)[:300])
                if getattr(self, "derived_as_specs", False):
                    self.mark_designed(ordered, "requirement/test design preflight ended; unreviewed gaps remain advisory")
                self._generation_active = True
                if (self.evolution and self.runner is not None and self.tests_dir
                        and unchanged == set(node_ids) and len(node_ids) > 1):
                    # Repair-only evolution has no new leaves to generate. One
                    # full baseline reveals shared failures and establishes a
                    # comparable delivery checkpoint before spending model tokens.
                    self.prepare_derived_spec_batch(ordered)
                    log("[flow] unchanged requirements: measure and repair the existing application as one suite")
                    for node_id in node_ids:
                        self.mark("design_started", node_id)
                        self.mark("design_done", node_id, "unchanged requirement; carried over")
                        self.mark("implementation_started", node_id)
                        self.mark("implementation_done", node_id, "existing application; acceptance pending")
                elif not self.whole_app_experiment(tree, ordered):
                    self.implement_sequential(tree, ordered, unchanged)

                self._generation_active = False
                try:
                    self.phase_integration_audit()
                except Exception as exc:  # source and final rehearsal still proceed
                    self.metric("phase_integration", outcome="unavailable", reason=str(exc)[:300])
                self.final_acceptance_passes()
                if getattr(self, "derived_as_specs", False):
                    self.derived_completeness_pass(ordered)
                undecided = [i for i in node_ids if self.test_verdict.get(i) is None and i not in self.impl_failed]
                final_ok = None
                seed_failures: dict[str, list[str]] = {}
                if undecided and self.runner is None and not self.time_up() and not self.wound_down():
                    log(f"[flow] final check turn for nodes without a local verdict: {undecided}")
                    # With no executable specs, an unbounded verification turn
                    # cannot produce a measured verdict. Preserve time for the
                    # deterministic startup rehearsal and final grading.
                    check_cap = max(30, int(os.environ.get('OCTOS_ARC_NO_SPEC_FINAL_CHECK_SECONDS', '600')))
                    from generation_checks import contract_warnings
                    sources = self.repair_source_index().sources
                    wiring = [item for item in contract_warnings(sources, sources)
                              if item.startswith(('ROUTE_LINK', 'API_CALL', 'ROUTE_CONFLICT'))]
                    literals = source_literal_gaps(self.requirement_contracts, sources) if not self.tests_dir else []
                    seeds = source_seed_gaps(self.requirement_contracts, sources) if not self.tests_dir else []
                    if wiring:
                        log(f'[flow] final static wiring audit: {len(wiring)} potential gap(s)')
                    if literals:
                        log(f'[flow] final requirement-literal audit: {len(literals)} potential gap(s)')
                    if seeds:
                        log(f'[flow] final required-seed audit: {len(seeds)} concrete gap(s)')
                    findings = wiring + literals + seeds
                    audit = ('\nStatic findings to inspect and fix only if confirmed (advisory, not test verdicts):\n' +
                             '\n'.join(findings) + '\n') if findings else ''
                    final_prompt = FINAL_CHECK_PROMPT.format(smoke=self.smoke_port, port=self.web_port,
                                                             tests=self.tests_prompt_for(None),
                                                             performance=self.perf_text(), ui=self.ui_contract()) + audit
                    final_ok, final_text = self.turn(final_prompt,
                                                     min(self.node_timeout, check_cap, max(1, self.remaining())),
                                                     "final check")
                    final_ok = self.final_check_verdict(final_ok, final_text)
                    if final_ok is None:
                        log("[flow] final check did not finish; its outcome is not a failure verdict")
                    self.commit("chore: final verification pass")
                    if not self.tests_dir:
                        seed_failures = seed_gaps_by_node(
                            self.requirement_contracts, self.repair_source_index().sources)
                    if seed_failures:
                        log(f"[flow] final required-seed audit: {len(seed_failures)} leaf/leaves still lack "
                            f"declared initial data: {', '.join(sorted(seed_failures))}")
                rehearsed = self.rehearsal()
                if rehearsed and any(value is None for value in self.test_verdict.values()) and self.runner is not None:
                    self.final_acceptance_passes()
                for node_id in undecided:
                    if getattr(self, "derived_as_specs", False):
                        # A missing generated spec or unavailable runner cannot
                        # become a feature pass from startup alone.
                        if not self.spec_map.get(node_id):
                            log(f"[flow] {node_id}: no executable derived spec; verdict remains unverified")
                        elif self.runner is None:
                            log(f"[flow] {node_id}: derived spec was not measured; verdict remains unverified")
                        continue
                    if self.runner is not None and self.spec_map.get(node_id):
                        # Starting the server is not proof that a feature works.
                        continue
                    passed, detail = self.no_spec_node_verdict(node_id, rehearsed, final_ok, seed_failures)
                    self.mark("test_passed" if passed else "test_failed", node_id, detail)
                    self.test_verdict[node_id] = passed
            finally:
                watchdog_stop.set()
                self.postflight()
            for node_id in node_ids:  # final per-node verdicts (full-suite run may have changed them)
                if self.test_verdict.get(node_id) is True:
                    detail = ("acceptance specs pass (node run and full parallel suite)" if self.tests_dir else
                              "derived requirement-contract review and startup rehearsal completed; "
                              "official acceptance specs unavailable")
                    self.mark("test_passed", node_id, detail)
                elif self.test_verdict.get(node_id) is False:
                    detail = ("acceptance specs failing" if self.tests_dir else
                              "derived requirement-contract review or startup rehearsal failed; "
                              "official acceptance specs unavailable")
                    self.mark("test_failed", node_id, detail)
            self.write_quality_summary(startable=rehearsed, node_ids=node_ids)
            self.mark_folders()
            self.commit("chore: traceability and acceptance state")
            failed = [i for i in node_ids if self.test_verdict.get(i) is not True]
            if not rehearsed:
                self.events.mark_run_failed("generated application did not pass final build/start rehearsal")
            elif failed:
                self.events.mark_run_completed(f"completed; nodes not verified: {', '.join(failed)}")
            elif not self.tests_dir:
                self.events.mark_run_completed(
                    "all requirement nodes implemented; derived contract review and startup rehearsal completed; "
                    "official acceptance specs unavailable")
            else:
                self.events.mark_run_completed("all requirement nodes implemented and verified")
            _reap_stray_processes("postflight", self.output_dir)
            _postflight_structure_check(self.output_dir)
            _free_web_port(self.web_port, self.output_dir)
            if rehearsed:
                self.write_preview_ready()
                return 0
            return 1  # an unstartable app must not have a successful process exit
        except Exception as exc:  # the platform judges by events, not exit code
            log(f"[flow] aborted: {exc!r}")
            watchdog_stop.set()
            if self.driver:
                self.driver.close()
            self.cleanup_playwright()
            self.stop_llm_proxy()
            recovered = isinstance(exc, PermanentProviderError) and self.recover_provider_stop(exc)
            for node in ordered:
                node_id = str(node.get("id"))
                if node_id not in self.test_verdict:
                    self.mark("test_failed", node_id, f"run aborted: {str(exc)[:200]}")
            try:
                self.mark_folders()
            except Exception:  # noqa: BLE001
                pass
            _reap_stray_processes("exception", self.output_dir)
            _postflight_structure_check(self.output_dir)
            _free_web_port(self.web_port, self.output_dir)
            self.events.mark_run_failed(str(exc)[:1000])
            # A valid measured artifact may still be graded; keep run_failed
            # above and never report an interrupted generation as completed.
            return 1 if isinstance(exc, PermanentProviderError) and not recovered else 0

    def mark_folders(self) -> None:
        """The platform counts FOLDER nodes as requirements too ("45 requirements
        and 32 scenarios" for a 32-leaf tree); derive their state from their
        atomic descendants so the functional-rate denominator is covered."""
        for folder_id, leaves in self.folder_children.items():
            if not leaves:
                continue
            verdicts = [self.test_verdict.get(leaf) for leaf in leaves]
            self.events.mark_design_started(folder_id)
            self.events.mark_design_done(folder_id, f"{len(leaves)} atomic children designed")
            self.events.mark_implementation_started(folder_id)
            if all(v is not None for v in verdicts) or any(leaf in self.impl_failed for leaf in leaves):
                done = [leaf for leaf in leaves if leaf not in self.impl_failed]
                if done:
                    self.events.mark_implementation_done(folder_id, f"{len(done)}/{len(leaves)} atomic children implemented")
                else:
                    self.events.mark_implementation_failed(folder_id, "no atomic child implemented")
            if all(v is True for v in verdicts):
                self.events.mark_test_passed(folder_id, f"all {len(leaves)} atomic children pass")
            else:
                failing = [leaf for leaf, v in zip(leaves, verdicts) if v is not True]
                self.events.mark_test_failed(folder_id, f"children not verified: {', '.join(failing)}")

    def write_preview_ready(self) -> None:
        artifacts_dir = os.environ.get("ARCBENCH_ARTIFACTS_DIR")
        if artifacts_dir:
            try:
                Path(artifacts_dir).mkdir(parents=True, exist_ok=True)
                (Path(artifacts_dir) / "preview-ready.json").write_text(
                    json.dumps({"ready": True, "reason": "octos bundle completed"}) + "\n", encoding="utf-8")
            except OSError:
                pass


# ---------------------------------------------------------------- main

def minimal_probe_body(model: str) -> bytes:
    """Fallback chat probe that cannot bill reasoning: thinking disabled, one output token."""
    return json.dumps({"model": model, "messages": [{"role": "user", "content": "OK"}], "max_tokens": 1,
                       "thinking": {"type": "disabled"}}).encode()


def endpoint_is_up(status: int) -> bool:
    """Any non-5xx HTTP answer proves the endpoint is reachable (401/404 included)."""
    return status < 500


def probe_endpoint() -> None:
    """Wait out endpoint/proxy outages (up to 10 min) without spending tokens:
    GET /models first (unbilled; any non-5xx answer = up). Only if that never
    answers, one chat request with thinking disabled and max_tokens=1.
    The old probe ("Reply with exactly: OK", max_tokens=4) let the model reason
    before its 4-token answer — about ¥0.0008 per run, a third of a Smoke task."""
    key = os.environ.get("OPENAI_API_KEY", "")
    base = os.environ.get("OPENAI_BASE_URL")
    if not (key and base):
        return
    import urllib.request as _ur
    import urllib.error as _ue
    from llm_proxy import open_upstream
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + key}
    deadline = time.time() + 600
    attempt = 0
    while True:
        attempt += 1
        try:
            with open_upstream(_ur.Request(base.rstrip("/") + "/models", headers=headers), timeout=30) as resp:
                log(f"[probe] GET /models -> HTTP {resp.status} (endpoint up, no tokens spent)")
                return
        except _ue.HTTPError as exc:
            if endpoint_is_up(exc.code):
                log(f"[probe] GET /models -> HTTP {exc.code} (endpoint up, no tokens spent)")
                return
            log(f"[probe] attempt {attempt}: GET /models -> HTTP {exc.code}")
        except Exception as exc:  # noqa: BLE001
            log(f"[probe] attempt {attempt}: GET /models -> {exc}")
            # Some gateways expose only chat/completions: one minimal, reasoning-free request.
            try:
                req = _ur.Request(base.rstrip("/") + "/chat/completions", headers=headers, method="POST",
                                  data=minimal_probe_body(os.environ.get("MODEL", "deepseek-chat")))
                with open_upstream(req, timeout=60) as resp:
                    log(f"[probe] minimal chat probe -> HTTP {resp.status}")
                    return
            except _ue.HTTPError as exc2:
                if endpoint_is_up(exc2.code):
                    log(f"[probe] minimal chat probe -> HTTP {exc2.code} (endpoint up)")
                    return
                log(f"[probe] attempt {attempt}: chat -> HTTP {exc2.code}")
            except Exception as exc2:  # noqa: BLE001
                log(f"[probe] attempt {attempt}: chat -> {exc2}")
        if time.time() >= deadline:
            log("[probe] endpoint still failing after 10min; proceeding anyway")
            return
        time.sleep(30)


def main() -> int:
    parser = argparse.ArgumentParser(description="Octos agent bundle for ARC-Bench")
    parser.add_argument("requirement_path", nargs="?", default=os.environ.get("ARCBENCH_TASK_DIR", "/workspace/task"))
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--type", "--app-type", dest="app_type", default="web")
    parser.add_argument("--web-port", type=int,
                        default=int(os.environ.get("ARCBENCH_WEB_PORT", os.environ.get("ARC_WEB_PORT", "3000"))))
    args = parser.parse_args()

    if os.environ.get("OCTOS_ARC_ENGINE") == "rust":
        # Kernel harness (`octos arc run`); this module keeps the default Python path.
        import rust_engine
        return rust_engine.main(args)

    key = os.environ.get("OPENAI_API_KEY", "")
    print(f"[env] OPENAI_BASE_URL={os.environ.get('OPENAI_BASE_URL', '<unset>')}", flush=True)
    print(f"[env] MODEL={os.environ.get('MODEL', '<unset>')}", flush=True)
    print(f"[env] OPENAI_API_KEY={'set(len=%d)' % len(key) if key else '<unset>'}", flush=True)
    print(f"[env] ARCBENCH_TEMPLATE_DIR={os.environ.get('ARCBENCH_TEMPLATE_DIR', '<unset>')}", flush=True)
    print(f"[env] ARCBENCH_TASK_DIR={os.environ.get('ARCBENCH_TASK_DIR', '<unset>')}", flush=True)
    print(f"[env] argv requirement_path={args.requirement_path}", flush=True)
    req_src = Path(args.requirement_path).resolve()
    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    elif os.environ.get("ARCBENCH_TEMPLATE_DIR"):
        output_dir = Path(os.environ["ARCBENCH_TEMPLATE_DIR"]).resolve()
    else:
        output_dir = Path.cwd() / "workspace" / f"run-{time.strftime('%Y%m%d-%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)

    on_platform = bool(os.environ.get("ARCBENCH_TEMPLATE_DIR"))
    if on_platform:
        req_dir = req_src
    else:
        req_dir = output_dir / "requirements"
        if req_dir.exists():
            shutil.rmtree(req_dir)
        shutil.copytree(req_src, req_dir)
    return Flow(args, output_dir, req_dir).run()


if __name__ == "__main__":
    sys.exit(main())
