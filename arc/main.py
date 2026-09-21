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
    OCTOS_ARC_REASONING       none (default: thinking disabled) | auto | low | medium | high | passthrough
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
    OCTOS_SESSION_SCOPE       turn (default) | node | run — when a fresh octos session starts
    OCTOS_ARC_INSTALL_PLAYWRIGHT  "0" never installs Playwright on the fly
    OCTOS_ARC_ALIAS_SPEC_IDS  "0" stops mirroring node states onto spec ids
    OCTOS_ARC_FINAL_CONFIRM_RUNS  unchanged-app full-suite runs required before acceptance (default 2)
    OCTOS_ARC_DEGENERATE_MAX_TOKENS  codegen ceiling after repeated/no-op output (8192; 0 disables)
    OCTOS_ARC_RECOVERY_REASONING  optional reasoning after degeneration (none by default)
    OCTOS_ARC_SIBLING_BATCH_SIZE  max independent sibling leaves per codegen request (default 3; 0 disables)
    OCTOS_ARC_SOURCE_STABILITY_ORDER  "0" restores path order instead of low-churn-first quoted sources
    OCTOS_ARC_GENERIC_TEMPLATE  "0" disables the task-neutral Express/store scaffold (default on in v4)
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
    failure_signature, failure_summaries, failure_source_context, find_playwright_by_search, find_playwright_root, map_specs_to_nodes,
    nodes_for_failures, playwright_candidates, playwright_version_hint, restore_tree,
    mutated_by_tests, restore_worktree, snapshot_worktree, tree_digest, workers_for_final, reap_workspace_processes,
    startup_error_digest)
from codegen import (FORMAT_INSTRUCTIONS, dedupe_nav_links, parse_edit_blocks, parse_file_blocks,  # noqa: E402
                     incomplete_blocks, normalize_bare_file_reply, prepare_edit_files, safe_relative_path, write_files)
from guard import TurnMonitor  # noqa: E402
from flow_policy import generation_tokens, node_seconds, phase_for_label, repair_seconds  # noqa: E402
from reply_quality import prune_degenerate_edits  # noqa: E402
from repair_context import balanced_failure_evidence  # noqa: E402
from generic_template import generic_template_active, install_generic_template  # noqa: E402
from web_stack import recommended_capabilities, stack_note  # noqa: E402
from llm_proxy import LlmProxy, configured_model_routes  # noqa: E402
from requirement_order import ancestors_of, node_fingerprint, sibling_batches, topo_order  # noqa: E402
from web_checks import scaffold_issues  # noqa: E402

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


def valid_app_design(design) -> dict | None:
    """The design if its fields have the shapes the consumers index: data_model a
    dict, routes and pages lists of dicts, notes a string, and at least one of
    the three structural fields present. Anything else -- legal JSON with the
    wrong types -- is no design at all; raising later (len() on an int) would
    abort the run before its first node."""
    if not isinstance(design, dict):
        return None
    data_model, routes, pages, notes = (design.get(k) for k in ("data_model", "routes", "pages", "notes"))
    if data_model is not None and not isinstance(data_model, dict):
        return None
    for items in (routes, pages):
        if items is not None and (not isinstance(items, list) or not all(isinstance(i, dict) for i in items)):
            return None
    for key, items in (("routes", routes), ("pages", pages)):
        seen = set()
        for item in items or []:
            path = item.get("path")
            method = item.get("method", "")
            if not isinstance(method, str):
                return None
            if not isinstance(path, str) or not path.startswith("/") or re.search(r"\s", path):
                return None
            if key == "routes" and method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
                return None
            identity = (method, path)
            if identity in seen:
                return None
            seen.add(identity)
            if "requirements" in item and (not isinstance(item["requirements"], list)
                    or not all(isinstance(nid, str) for nid in item["requirements"])):
                return None
    if data_model is not None and not all(isinstance(k, str) and k and isinstance(v, dict)
                                          for k, v in data_model.items()):
        return None
    contracts = design.get("contracts")
    if contracts is not None and (not isinstance(contracts, list)
            or not all(isinstance(c, dict) and isinstance(c.get("invariants"), list)
                       and c["invariants"] and all(isinstance(v, str) for v in c["invariants"])
                       and isinstance(c.get("requirements"), list)
                       and all(isinstance(v, str) for v in c["requirements"]) for c in contracts)):
        return None
    modules = design.get("modules")
    if modules is not None and (not isinstance(modules, list)
            or not all(isinstance(module, dict)
                       and isinstance(module.get("path"), str)
                       and module["path"].startswith(("frontend/", "backend/"))
                       and isinstance(module.get("owns"), list) and module["owns"]
                       and all(isinstance(owner, str) and owner for owner in module["owns"])
                       for module in modules)):
        return None
    if notes is not None and not isinstance(notes, str):
        return None
    if not any(design.get(k) for k in ("data_model", "routes", "pages")):
        return None
    return design


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
    req_ids = set(re.findall(r"\bREQ-\d+(?:\.\d+)*\b", spec_text))

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


def describe_node(node: dict) -> str:
    lines = [f"ID: {node.get('id')}", f"Name: {node.get('name', '')}"]
    if node.get("description"):
        lines.append(f"Description: {node['description']}")
    scenarios = node.get("scenarios") or []
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
                           change_counts: dict[str, int] | None = None) -> str | None:
    """Select by relevance/content budget, then enforce the serialized budget.

    `max_chars` counts file contents; `max_output_chars` (when given) bounds the
    rendered block, headings and omission list included. Each overflow step
    removes one least-priority quoted file, so the entry -- ranked first -- is
    the last to go. There are at most len(scored) + 1 renders, all using the same
    in-memory snapshot. `stable_order` changes presentation only, keeping the same
    relevance selection but quoting the entry and low-churn files first for prefix reuse.
    """
    selected, total = [], 0
    for i, (_, _, size, _, _) in enumerate(scored):
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
        "gateway": {"max_output_tokens": 65536},
    }
    if provider not in ("openai", "deepseek", "anthropic") and base_url:
        config["base_url"] = base_url
    reasoning = os.environ.get("OCTOS_ARC_REASONING", "none")
    if reasoning in ("none", "off", "disabled"):
        config["gateway"]["reasoning_effort"] = "none"
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
        "insufficient_balance", "quota exhausted", "balance is exhausted", "invalid_api_key",
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
        ok, text = False, "octos turn timed out"
        for attempt in range(1, attempts + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            ok, text = fn(remaining)
            if ok or not self._transient(text) or attempt == attempts:
                break
            wait = 30 * attempt
            if wait >= deadline - time.monotonic():
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
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False, "octos turn timed out"
            return session.run_turn(prompt, timeout=remaining)
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
- Treat a UI action as a state transition: mount usable editor/dialog controls synchronously before the first await. Isolate background controls for modal dialogs, not ordinary inline editors or non-modal menus. A browser click does not await an async event listener. After a mutation, await persistence and refresh (or apply a consistent optimistic update) before exposing stale state as final; handle failure without losing the user's edits. Derive Save/Cancel/autosave transitions from requirements; cancelling a draft must not commit it.
- Use local assets where practical. Add styling, animation, asynchronous updates or external services when required; keep interactions responsive and report failures clearly.
- Specify ownership/keys and atomic command effects (including undo) from requirements; related mutations must commit together in one store update or database transaction, not separate file writes. Validate authoritatively on the server. Date-only values are calendar dates, not UTC instants; persist expiry deadlines across reloads, anchor countdowns to server time, and use a task-provided reference date only when explicitly required. Keep editable rich-text regions labeled (role=textbox, aria-multiline=true); use native select for a native selection contract, not a visually similar custom menu.
- Use supplied visual references when relevant. Public tests are examples of required behavior, not permission to hardcode test outcomes or omit untested requirements.
"""

# Bump when APP_DESIGN_PROMPT or the design schema changes: a stored design made
# with another version is regenerated, not reused.
APP_DESIGN_PROMPT_VERSION = "12"

COLLECTION_MIGRATION_CONTRACT = (
    "Optional collection(...) migration up(data) receives a storage OBJECT; the record array is data.items, "
    "NOT data itself. Mutate data.items synchronously, return undefined, and preserve __arcMigrations. "
    "Direct store.migrate receives its own fallback-shaped object. Do not change these shared APIs.\n")

APP_DESIGN_SYSTEM = "You are the architect of a small web application. Reply with one JSON object only."

APP_DESIGN_PROMPT = COLLECTION_MIGRATION_CONTRACT + """\
Design the application that satisfies this whole requirement tree (do NOT implement anything):

{outline}

Preserve the installed stack: complex fresh applications use React/Vite/Radix/React Router with local bundled assets and SPA routes (frontend/package.json arc.spa=true). Simple or existing applications keep their architecture. frontend/src/index.html is the shell; backend/server.js is a small Express entry serving frontend/dist and registering backend/routes/<area>.js modules; shared persistence lives in backend modules. Use the provided exact dependency pins and capability recommendations; do not invent another DOM/widget framework.
Reply with ONE JSON object (at most 150 lines, no prose) that every requirement will be implemented against:
{{"data_model": {{"collection": {{"field": "type"}}}},
 "routes": [{{"method": "GET|POST|PUT|DELETE", "path": "/api/...", "purpose": "one line", "requirements": ["REQ-..."]}}],
 "pages": [{{"path": "/...", "purpose": "one line", "requirements": ["REQ-..."]}}],
 "modules": [{{"path": "frontend/src/...|backend/routes/...", "owns": ["cohesive page/layout/editor/API concern"]}}],
 "contracts": [{{"requirements": ["REQ-..."], "invariants": ["ownership/key scope", "command: preconditions -> atomic effects and undo", "draft/save/cancel semantics", "date-only/clock/deadline rules", "control and validation semantics"]}}],
 "notes": "session handling, seed data, versioned migrations, validation conventions, naming conventions"}}
Name every collection, field, route and page once and consistently; requirements that share data must share the record shape. For each HTTP method, place literal paths before overlapping parameter paths (for example, DELETE /api/items/trash before DELETE /api/items/:id). In notes, state the shared interaction lifecycle: when controls become usable, what commits an edit, and when the list reflects the committed record. Do not enumerate test-only cases.
For each lifecycle view, specify which records the API returns and which filters the client applies; a client cannot recover records already excluded by the server. Specify absent versus false query values, compatible filter combinations, and inverse transitions (remove/restore, assign/unassign). For composite editors, state whether selection commits immediately or on Save, how Done/Cancel/Escape behave, and which owner retains the draft after a failed save. Do not invent lifecycle states not required by the task.
Give every expanded editor a visible completion action: Save for explicit commits or Close/Done for autosave; Escape/outside click supplements that action, never replaces it. Moving focus within the editor is not completion. Distinguish raw response JSON from Response objects; no helper-invented result envelope unless explicitly implemented on the backend.
In notes, preserve required entry gestures and action placement (record click, direct action, menu action). Distinguish available catalogue choices from initially selected values; optional actions must follow user intent, not unconditional fixture-derived defaults.
Identify shared layout and component owners: routes with the same navigation/header reuse one layout; repeated record editors and actions reuse one implementation. Put those owners in modules. App.jsx owns routing/composition; normally keep each application module below 18000 characters by extracting cohesive pages, reusable record views/editors and API/state modules before they become a monolith. Split layouts only when requirements differ; do not create pass-through modules merely to meet a number. Keep this concrete and minimal, not a configurable application framework.
"""

CODEGEN_SYSTEM = """You write complete, minimal web apps. Reply only with <<<FILE relative/path>>> ... <<<END FILE>>> blocks using exact delimiters, or exactly <<<NO CHANGE>>> when already satisfied.
Return each changed file once, with complete contents. No EDIT blocks, diffs, unchanged files or iterative self-review. Implement the active requirements and their prerequisites; the shared design is a contract, not a request to regenerate every other feature. Preserve existing behavior. Stop immediately when complete."""

CODEGEN_RULES = """\
Files: frontend/src/index.html is a small shell; put substantial CSS/JS in local modules. backend/server.js serves ../frontend/dist on process.env.PORT||{port}; put routes in backend/routes/<area>.js.{ports} Keep the entry stable. For each HTTP method, register literal paths before overlapping :parameter paths (DELETE /api/items/trash before DELETE /api/items/:id). For pushState links set frontend/package.json arc.spa=true. Preserve the installed frontend stack, exact dependency versions and lockfile; add task-required packages to the correct package.json. Local assets only: no CDN URLs or remote browser imports. npm install may download packages. JSX/TSX must be bundled, not copied to dist.
Packages: update package.json and the build script only when needed by new dependencies; keep the fixed baseline.
Data: seed only a new store or migration; preserve edits/deletions across restarts. Use atomic aggregate updates for related state and server-side validation. Persist deadlines, distinguish calendar dates from timestamps. Label rich-text textbox regions; use native select when native selection is required.
Rules: handle general inputs and preserve working behavior. Use accessible controls and unique IDs. Per-item actions target their item; hidden menus must not intercept input. Use distinct names for menu triggers versus destinations. Closing an editor saves pending fields/options only if required; explicit Cancel discards the draft. Navigation renders the selected view; visual options visibly change the item. Derive behavior from requirements, not test outputs.
Async: clicks do not await handlers. Mount usable editor/dialog controls before the first await; isolate background only for modal overlays. Await save and list refresh (or update optimistically); retain edits on failure.
Output: complete FILE blocks for changed files only; do not re-emit unchanged modules. If already satisfied, reply exactly <<<NO CHANGE>>>.
"""

GENERIC_TEMPLATE_NOTE = COLLECTION_MIGRATION_CONTRACT + """\
Shared task-neutral files already exist. backend/server.js is an Express 5 entry: JSON/form parsers, frontend/dist, and automatic backend/routes/*.js registration. Route modules export (app) => { app.get/post/patch/delete(...); }; use req.body/params, res.json/status. Register literal paths before :parameter paths; keep server.js unchanged for ordinary routes.
From backend/routes/: require('../lib/store') exports read(name,fallback), write(name,value), update(name,fallback,synchronousChange). Prefer require('../lib/collection').collection(name,{idKey,initial,migrations,normalize}) for ordinary CRUD instead of regenerating persistence; it exports all/list/get/create/patch/remove/transact. initial applies only to a new store; persist changes to existing data via versioned migrations up(data) mutating data.items synchronously, preserving __arcMigrations. Never reseed deleted records. Optional normalize(record) returns an object with the SAME id on reads/create/patch and before/after transact; choose defaults from requirements, not fixtures. Reads do not persist normalization. transact(items => result) synchronously mutates one collection in one write; duplicate/missing IDs and async callbacks fail. Atomicity is single-store/single-process only; cross-store effects need one aggregate or transactional storage. require('../lib/errors').HttpError(status,message) gives explicit 4xx {error:message}; 5xx details are hidden. Define domain validation, authorization and messages from requirements.
Optional require('../lib/query') exports optionalBoolean(value) (missing/true/false, invalid => 400) and matchesFlags(record,flags) (strict booleans, undefined ignored). Whitelist fields, resolve view defaults once, combine filters, and enforce ownership separately; clients cannot recover server-excluded rows.
Frontend ./shared/request.js exports requestJson(url,options): raw parsed JSON (204 => null) or an Error with {error} message and numeric status; no {ok,value} envelope. React uses main.jsx/App.jsx. Plain scaffold uses app.js, shared/dom.js (escapeHtml) and shared/router.js (startRouter(render), arc.spa=true). Optional build.mjs/vite.config.mjs: build is "node build.mjs"; bundle JSX/local assets. frontend/public copies to dist root. Define fields, pages, sessions and seed data from the task. Do not output FILE blocks for unchanged shared helpers.
"""

TASK_NEUTRAL_HELPERS = {
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
"""

UI_CONTRACT_SESSION = """\
- Derive authentication routes, redirects, labels and session lifetime from the requirements and existing app. Keep authentication state isolated between users; preserve sessions only as required. Failed authentication must not create a session or mutate protected data. Choose error disclosure appropriate to the security requirements.
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
- Preserve the platform contract: frontend/ has npm run build producing frontend/dist/; backend/ has npm start and reads PORT (default {port}). Within that contract, preserve the existing application architecture and choose libraries or storage appropriate to the requirements and available environment.
- Preserve the installed stack and exact dependency pins. Fresh complex apps use React/Vite/Radix/React Router and Express routes; keep simple or existing apps in their own architecture. Use the recommended optional libraries only for actual requirements. Declare dependencies and make npm run build produce all pages and assets. Browser pages must load scripts, styles, fonts and media from local output, never a CDN or remote import. Registry downloads during npm install are allowed.
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
Fix frontend/ and/or backend/ so the failing tests listed below pass without breaking the passing ones. Work within the configured request budget. Use the supplied evidence to identify the cause, read relevant sources when needed, and make focused edits. For a failed post-action assertion, trace the preceding actions and identify the element and record actually acted on. With repeated controls, inspect locator scope, ordering, visibility, and hover/focus state before assuming a storage or rendering failure. Preserve keyboard access and the required interaction semantics when resolving ambiguity. Preserve behavior beyond the tested inputs. The harness rebuilds and re-runs the official tests right after your turn. The spec files are read-only ground truth.
For persistent data, initialize required records only for a new store or an explicit migration. Later startups must preserve user edits, deletions and archive state; a missing record does not mean the store is new. Reset data only when the requirements explicitly demand it.
""" + PORT_RULES + """
{sources}
The official acceptance tests for requirement node {node_id} just ran against your app: {passed}/{total} passed. Failing tests (Feature / where it failed / what was observed / the last steps before failure):
{failures}
{test_location}
{corrections}{slow}
"""

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
        # Batch generation still verifies every leaf. Record its first-pass
        # yield so subsequent runs can distinguish batching cost from repairs.
        self.batched_groups: dict[str, tuple[str, ...]] = {}
        self.batch_first_pass: dict[str, bool] = {}
        self.checkpoint_regressions: set[str] = set()
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

    def final_retry_admission(self) -> float:
        """Budget needed to measure, repair, then preserve a final measurement."""
        return 2 * self.final_measurement_reserve() + self.repair_minimum()

    # -- helpers ----------------------------------------------------------
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
            log(f"[guard] cost guard tripped: {tokens} billable tokens, {self.turn_count} turns "
                f"(limits {self.max_total_tokens} / {self.max_turns} / abs {self.max_total_tokens_abs}); no further repair turns")
        return bool(over)

    def remaining(self) -> float:
        return self.budget - (time.time() - self.t_start)

    def time_up(self) -> bool:
        return self.remaining() <= 0

    def mark(self, kind: str, node_id: str, message: str | None = None) -> None:
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
            proxy.mode = impl_mode if (impl_mode and is_implement and self.minimal_mode(getattr(self, "n_nodes", 99))) else base_mode
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
        self.turn_count += 1
        ok, text = self.driver.run(prompt, max(1, int(timeout)), monitor)
        if proxy is not None and getattr(proxy, "hard_budget_exhausted", False) is True:
            ok, text = False, "local_turn_budget_exhausted: partial edits retained; acceptance must measure them."
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
        return VERIFY_MINIMAL if minimal else VERIFY_FULL.format(smoke=self.smoke_port)

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
        return int(os.environ.get("OCTOS_ARC_CODEGEN_CONTEXT_CHARS", "90000"))

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
                                 must_include: set[str] | None = None) -> str | None:
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
        if len(spec) >= limit * 0.6:
            # Cheapest refusal there is; decided before any source file is read.
            self.codegen_budget = dict(spec=len(spec), entry=0, room=0, limit=limit,
                                       reason="spec_at_or_above_60_percent")
            return None
        small = self.codegen_reasoning(len(spec)) == "none"
        rules = CODEGEN_RULES.format(port=self.web_port, ports=self.codegen_ports_clause())
        if getattr(self, "generic_template_installed", False):
            rules += GENERIC_TEMPLATE_NOTE
        rules += stack_note(self.output_dir)
        # The harness has already written package.json, which is enough for
        # has_app() but not for a runnable backend. Keep existing sources while
        # explicitly requiring the missing entry in this generation request.
        missing_entry = missing_backend_entry(self.output_dir)
        if missing_entry:
            rules += f"Startup prerequisite: {missing_entry} is missing. Create it in this response so the configured backend start command can run.\n"
        task = CODEGEN_TASK.format(node_id=str(node.get("id")),
            description=describe_node(node) if node.get("scenarios") or node.get("dependencies")
            else str(node.get("description") or "").strip(), spec=spec,
            size_rule=CODEGEN_SIZE_SMALL if small else CODEGEN_SIZE_FULL)
        existing = self.has_app()
        if existing:
            rules = rules.replace("Files:", "Existing app below; preserve working behavior. Files:", 1)
        entry = backend_entry(self.output_dir) if existing else None
        if must_include is None:
            must_include = set(getattr(self, "refused_paths", ()))
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
        sources = select_source_snapshot(scored, room, stable_order=True, max_output_chars=room,
                                         change_counts=change_counts)
        if sources is None or (entry is not None and str(entry.relative_to(self.output_dir)) not in quoted_paths(sources)):
            self.codegen_budget["reason"] = "serialized_sources_or_entry_exceed_budget"
            return None
        # Rules, a design that fits whole (identical for every node), the sources in
        # stability order -- unchanged low-churn files precede frequently edited
        # ones for prefix reuse -- then the per-node design slice, if any, with the
        # other node-specific text.
        return rules + design_stable + sources + "\n" + design_slice + corrections + evidence + task

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
        if os.environ.get("OCTOS_ARC_REASONING", "none") not in {"auto", "none", "off", "disabled"}:
            return None
        threshold = int(os.environ.get("OCTOS_ARC_CODEGEN_REASONING_CHARS", "5000"))
        return "none" if spec_chars and spec_chars < threshold else None

    def text_turn(self, prompt: str, timeout: int, label: str, *, system: str = CODEGEN_SYSTEM,
                  spec_chars: int = 0) -> tuple[bool, str]:
        """One tool-less request; the reply is returned as text. Tool policy and
        the system prompt live on the proxy/driver for the duration and are
        restored whatever happens. codegen_turn parses file blocks out of it;
        app_design parses a JSON object."""
        proxy = self.llm_proxy
        proxy.no_tools = True
        proxy.system_override = system
        mode_override = self.codegen_reasoning(spec_chars)
        saved_cap = getattr(proxy, "codegen_max_tokens", 0)
        phase = phase_for_label(label)
        recovering = getattr(self, "codegen_degenerated", False) and phase != "design"
        phase_cap = max(0, int(os.environ.get("OCTOS_ARC_REPAIR_MAX_TOKENS", "8192"))) if phase == "repair" else 0
        if phase == "design":
            design_default = max(4096, min(16384, 128 * getattr(self, "n_nodes", 32)))
            phase_cap = max(0, int(os.environ.get("OCTOS_ARC_DESIGN_MAX_TOKENS", str(design_default))))
        recovery_cap = self.generation_recovery_cap() if recovering and phase == "implement" else (
            max(0, int(os.environ.get("OCTOS_ARC_DEGENERATE_MAX_TOKENS", "8192"))) if recovering else 0)
        proxy.codegen_max_tokens = min([cap for cap in (phase_cap, recovery_cap) if cap] or [0])
        recovery_mode = os.environ.get("OCTOS_ARC_RECOVERY_REASONING", "none")
        if recovering and recovery_mode in {"low", "medium", "high"}:
            mode_override = recovery_mode  # opt-in; default thinking remains off
        saved_base = getattr(self, "base_reasoning_mode", proxy.mode)
        if mode_override:
            self.base_reasoning_mode = mode_override
        try:
            with self.driver.without_tools():
                return self.turn(prompt, timeout, label, expect_verification=False,
                                 request_budget=int(os.environ.get("OCTOS_ARC_CODEGEN_REQUESTS", "3")))
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
                                               react=len(ordered) >= 3,
                                               capabilities=recommended_capabilities(tree))
            written += write_codegen_manifests(build_dir)
            if written:
                self.commit("chore: install task-neutral web scaffold")
                log(f"[flow] generic template: installed {written}")
            self.generic_template_installed = generic_template_active(build_dir)
        if self.codegen_mode() and os.environ.get("OCTOS_SKELETON_ALWAYS") != "1":
            if not self.evolution:
                log(f"[flow] {len(ordered)}-node tree: codegen mode, harness manifests replace the skeleton turn")
            self.app_design(tree, ordered)
        elif not self.evolution and (len(ordered) >= self.skeleton_min_nodes
                                     or os.environ.get("OCTOS_SKELETON_ALWAYS") == "1"):
            self.skeleton(tree)
            self.driver.end_scope("node")
        elif not self.evolution:
            log(f"[flow] {len(ordered)}-node tree: skeleton folded into the first node turn")
        # The tree before any node of this run: the first suite repair quotes
        # what changed since it.
        self.last_checkpoint_sha = self.head()

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
        prompt = stack_note(self.output_dir) + APP_DESIGN_PROMPT.format(outline=outline)
        deadline = time.monotonic() + self.design_timeout
        ok, text = self.text_turn(prompt, self.design_timeout, "application design", system=APP_DESIGN_SYSTEM,
                                  spec_chars=len(outline))
        def parse_design(reply):
            found = re.search(r"```json\s*(\{.*?\})\s*```", reply or "", re.S) or re.search(r"(\{.*\})", reply or "", re.S)
            try:
                return valid_app_design(json.loads(found.group(1))) if found else None
            except json.JSONDecodeError:
                return None

        design = parse_design(text) if ok else None
        retry_seconds = min(120, int(deadline - time.monotonic()), int(self.remaining()))
        if ok and not design and retry_seconds >= 30 and not self.wound_down():
            log("[flow] application design: invalid schema/JSON; one bounded format retry")
            ok, text = self.text_turn(
                prompt + "\nThe preceding reply was not a valid design object. Return ONLY the JSON object "
                "with data_model (object), routes/pages/modules/contracts (arrays of objects), notes (string). "
                "Use compact entries and no code, prose or FILE blocks.\n",
                retry_seconds, "application design (format retry)", system=APP_DESIGN_SYSTEM,
                spec_chars=len(outline))
            design = parse_design(text) if ok else None
        if not design:
            log("[flow] application design: no usable JSON object in the reply; nodes proceed without one")
            return None
        self.app_design_doc = design
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

    def repair_tool_turn(self, prompt, timeout, label):
        before = self.repair_source_index().versions
        prompt += self.repair_memory_context(prompt)
        ok, text = self.turn(prompt, timeout, label)
        after = self.repair_source_index().versions
        self.last_codegen_written = sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))
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
        """Unknown/global changes escalate, never reuse a cached passing verdict."""
        if not changed or not self.tests_dir:
            return []
        all_specs = sorted(str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob("*.spec.ts"))
        index = self.repair_source_index()
        affected = index.affected(changed)
        targets = self.requirement_source_targets()
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
        tool_prompt = self.compact_tool_repair_prompt(tool_prompt, failures)
        if prefer_codegen and self.codegen_mode(node_block=False):
            prompt = self.suite_repair_prompt(failing_ids, failures)
            if prompt is not None:
                spec_chars = getattr(self, "suite_spec_chars", 0)
                for attempt in range(2):
                    left = deadline - time.monotonic()
                    if left <= 0 or self.wound_down():
                        break
                    ok, reason = self.codegen_turn(prompt, left, label if not attempt else label + " (protocol retry)",
                                                   spec_chars=spec_chars)
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
        if reason:
            tool_prompt += "\nCodegen repair did not fully apply; inspect current files before editing. " + reason[:300] + "\n"
        self.last_turn_changed = None
        _, text = self.repair_tool_turn(tool_prompt, left, label)
        changed = getattr(self, "last_turn_changed", None)
        self.last_repair_changed = True if self.last_repair_changed else changed
        return "tools", text

    def codegen_turn(self, prompt: str, timeout: int, label: str, spec_chars: int = 0,
                     system: str = CODEGEN_SYSTEM, format_instructions: str = FORMAT_INSTRUCTIONS,
                     raw_target: str | None = None, defer_shared_refusals: bool = False) -> tuple[bool, str]:
        """Run a tool-less turn; apply complete files or exact anchored edits.
        `raw_target`: when the reply is a bare HTML document (tiny tier), write it there."""
        self.last_codegen_refused = set()
        self.last_codegen_deferred = set()
        self.last_codegen_written = []
        self.last_codegen_no_change = False
        self.last_codegen_degenerated = False
        if not raw_target and self.use_structured_edits(prompt, label):
            return self.structured_edit_turn(prompt, timeout, label)
        if phase_for_label(label) == 'repair':
            prompt += self.repair_memory_context(prompt)
        started = time.monotonic()
        def result(ok: bool, text: str, outcome: str):
            self.last_codegen_outcome = outcome
            self.remember_repair(label, prompt, outcome)
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
                                  timeout, label, system=system, spec_chars=spec_chars)
        truncated = False
        proxy = getattr(self, "llm_proxy", None)
        if not ok and "output_truncated" in text and isinstance(proxy, LlmProxy):
            retained = proxy.take_truncated_reply(label)
            if retained:
                text, truncated = retained, True
                log(f"[codegen] {label}: recovering only terminated blocks from truncated response")
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
            normalized = normalize_bare_file_reply(text)
            if normalized:
                text = normalized
                files = parse_file_blocks(text)
                self.metric("protocol_normalized", label=label, format="bare_file_sections", files=len(files))
                log(f"[codegen] {label}: normalized completed bare FILE sections; applying normal write guards")
        if ok and not files and not edits and text.strip() == "<<<NO CHANGE>>>":
            self.last_codegen_no_change = True
            log(f"[codegen] {label}: existing implementation declared complete; acceptance will verify it")
            return result(True, text, "unchanged")
        if ok and not files and not edits and raw_target:
            html = strip_code_fences(text)
            if looks_like_markup(html):
                files = {raw_target: html}
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
            refused = sorted({rel for rel in [*files, *(row[0] for row in edits)]
                              if rel != raw_target and rel not in shown and (self.output_dir / rel).exists()})
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
            if not files:
                return result(False, f"codegen reply only changed files it was not shown: {', '.join(refused)}", "guard_refused")
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
        paths = quoted_paths(prompt)
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

    def structured_edit_turn(self, prompt: str, timeout: int, label: str) -> tuple[bool, str]:
        """Use the native read/edit/write loop, bounded by the caller's deadline.

        Keep requirements and test evidence; replace only verified whole-source
        quotations with an index. Native calls get individual application results.
        The protected-file hook rejects unsafe fuzzy/no-op edits before execution.
        """
        before = {str(p.relative_to(self.output_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in app_source_files(self.output_dir, exts=None)}
        if phase_for_label(label) == 'repair':
            prompt += self.repair_memory_context(prompt)
        from source_index import SourceIndex
        sources = {str(p.relative_to(self.output_dir)): p.read_text(encoding="utf-8", errors="replace")
                   for p in app_source_files(self.output_dir)}
        prompt += "\n" + SourceIndex(sources).render(quoted_paths(prompt)) + "\n"
        retained = 0
        for rel in sorted(quoted_paths(prompt)):
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
        proxy.compact_reads = True
        proxy.extra_drop_tools = saved | self.SHELL_TOOLS | {"diff_edit", "apply_patch"}
        proxy.tool_max_tokens = max(1024, int(os.environ.get("OCTOS_ARC_EDIT_MAX_TOKENS", "4096")))
        started = time.monotonic()
        try:
            ok, text = self.turn(prompt, timeout, label + " (structured edits)", expect_verification=False,
                                 request_budget=max(1, int(os.environ.get("OCTOS_ARC_EDIT_REQUESTS", "8"))))
        finally:
            proxy.extra_drop_tools = saved
            proxy.tool_max_tokens = saved_cap
            proxy.compact_reads = saved_compaction
        after = {str(p.relative_to(self.output_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in app_source_files(self.output_dir, exts=None)}
        self.last_codegen_written = sorted(rel for rel in before.keys() | after.keys() if before.get(rel) != after.get(rel))
        self.last_codegen_no_change = ok and not self.last_codegen_written
        self.last_codegen_outcome = "applied" if ok and self.last_codegen_written else "unchanged" if ok else "tool_incomplete"
        self.remember_repair(label, prompt, self.last_codegen_outcome)
        self.metric("structured_edit", label=label, outcome=self.last_codegen_outcome,
                    elapsed_seconds=round(time.monotonic() - started, 3),
                    changed_files=len(self.last_codegen_written))
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
            return "(none)"
        specs = list(self.spec_map.get(node_id) or [])
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
        return "\n".join(parts) or "(none)"

    def batch_spec_bodies(self, node_ids: list[str]) -> str:
        """Quote a batch's specs and reachable helpers once, not once per leaf."""
        if not self.tests_dir:
            return "(none)"
        specs = list(dict.fromkeys(path for node_id in node_ids for path in (self.spec_map.get(node_id) or [])))
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
        return "\n".join(f"--- {rel} ---\n{texts[rel]}" for rel in specs + helpers if texts.get(rel)) or "(none)"

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

    def tests_prompt_for(self, node_id: str | None, skeleton: bool = False) -> str:
        if not self.tests_dir:
            return ""
        if skeleton:
            support = sorted(str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob("*.ts")
                             if not p.name.endswith(".spec.ts"))
            n_specs = len(list(self.tests_dir.rglob("*.spec.ts")))
            return (f"The official Playwright specs ({n_specs} files) live under {self.tests_dir}; each later turn "
                    f"receives the spec files for its own node. In THIS turn read only the shared helpers "
                    f"({', '.join(support[:10]) or 'none'}) and at most two spec files to learn the base URL, "
                    f"navigation and header conventions; do not implement the features yet.\n"
                    + acceptance_tests_prompt(self.tests_dir, self.web_port, self.smoke_port, []).split("\n", 1)[-1])
        files = list(self.spec_map.get(node_id) or [])
        support = sorted(str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob("*.ts")
                         if not p.name.endswith(".spec.ts"))
        if not files:  # node without its own spec: show everything
            files = sorted(str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob("*.spec.ts"))
        return acceptance_tests_prompt(self.tests_dir, self.web_port, self.smoke_port, files + support,
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
        env_extra: dict = {}
        root = find_playwright_root(playwright_candidates(BUNDLE_DIR, self.tests_dir, self.output_dir))
        if root is None:
            root = find_playwright_by_search(log)
        if root is None and os.environ.get("OCTOS_ARC_INSTALL_PLAYWRIGHT", "1") != "0":
            version = playwright_version_hint(self.tests_dir)
            log(f"[acceptance] no preinstalled Playwright found; private install of @playwright/test@{version}")
            self.private_playwright = Path(tempfile.mkdtemp(prefix="octos-arc-playwright-"))
            installed = ensure_playwright(self.private_playwright, log, version=version)
            if installed:
                root, env_extra = installed
        if root is None:
            log("[acceptance] Playwright unavailable; nodes will be judged by the final check only")
            return
        limit = container_memory_limit()
        self.mem_limit = limit
        workers = workers_for_memory(limit, int(os.environ.get("OCTOS_ARC_TEST_WORKERS", "2")))
        self.runner = AcceptanceRunner(root, self.tests_dir, acceptance_work_dir(root), log,
                                       timeout_ms=int(os.environ.get("OCTOS_ARC_TEST_TIMEOUT_MS", "10000")),
                                       workers=workers, env_extra=env_extra)
        log(f"[acceptance] using Playwright at {root}; workers={workers}"
            + (f" (container memory limit {limit // (1024 * 1024)} MiB)" if limit else ""))

    def snapshot_protected(self) -> None:
        """Copy the official tests dir (and requirements) so any edit the model
        sneaks past the hook (e.g. via a shell redirect) is undone after the
        turn — the platform grades with THESE files."""
        self.protected_snapshots = []
        for live in (self.tests_dir, self.req_dir):
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
        """Default to thinking off; explicit auto/effort settings opt back in.
        Exact per-request usage lands in .arc/llm-usage.jsonl."""
        mode = os.environ.get("OCTOS_ARC_REASONING", "none")
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
               "sse_chunks": 0, "no_usage": 0}
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
                                ("label", "phase", "status", "elapsed_ms", "request_bytes", "response_bytes")})
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

    def app_server(self, grader_like: bool) -> AppServer:
        return AppServer(self.output_dir, self.smoke_port, log, grader_like=grader_like,
                         extra_ports=[p for p in spec_base_ports(self.tests_dir) if p != self.web_port])

    def run_specs(self, specs: list[str], workers: int | None = None, grader_like: bool = False) -> RunSummary:
        """Build, start, run the specs, then undo whatever the test run mutated
        (a persisted counter at -1 would otherwise be committed as the seed).
        `grader_like` starts the backend with only PORT set, as the platform does."""
        started = time.monotonic()
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
            summary = self.runner.run(specs, f"http://127.0.0.1:{self.smoke_port}", workers=workers,
                                      wall_timeout=max(1, min(900, int(self.remaining()))))
            expected = sorted(str(p.relative_to(self.tests_dir)) for p in self.tests_dir.rglob("*.spec.ts")) if self.tests_dir else []
            if grader_like and sorted(specs) == expected and self.suite_is_measured(summary, specs):
                self.last_suite_seconds = time.monotonic() - started
            return summary
        finally:
            server.stop()
            # Ask before restoring: afterwards there is nothing left to compare.
            if summary is not None:
                summary.stores_written = mutated_by_tests(git_run)
            restore_worktree(git_run)

    def record_tests(self, node_id: str, specs: list[str], summary: RunSummary) -> None:
        try:
            for r in summary.results:
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
        if compact is not None:
            for attempt in range(2):
                left = deadline - time.monotonic()
                if left <= 0 or self.wound_down():
                    return applied
                self.last_codegen_refused = set()
                self.last_codegen_written = []
                ok, reason = self.codegen_turn(compact, left, label if attempt == 0 else f"{label} (application retry)",
                                          spec_chars=getattr(self, "current_spec_chars", 0))
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
        self.repair_tool_turn(self.compact_tool_repair_prompt(build_prompt(), failures), left, label)
        changed = getattr(self, "last_turn_changed", None)
        if changed is False and not applied:
            log(f"[flow] {label}: no source changes after repair fallback; skipping duplicate acceptance")
            return False
        return True

    def acceptance_loop(self, node_id: str, specs: list[str], deadline: float,
                        rebuild_prompt=None, initial_summary: RunSummary | None = None) -> bool | None:
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
        initial_versions = self.repair_source_index().versions
        self.codegen_blocked = False  # same failure twice in codegen mode -> tool mode for this node
        for attempt in range(self.repair_rounds + 1):
            summary = initial_summary if attempt == 0 and initial_summary is not None else self.run_specs(specs)
            if summary.error and summary.killed:
                log(f"[acceptance] {node_id}: test runner killed ({summary.error[:120]}); no verdict from this round")
                return None
            infrastructure_error = summary.error or ("\n".join(summary.load_errors) if summary.load_errors else "")
            measured = not infrastructure_error and not summary.killed and summary.total > 0
            self.verify_repair_memory(summary, measured)
            if infrastructure_error:
                log(f"[acceptance] {node_id} infrastructure error: {infrastructure_error[:300]}")
                failures = f"- Feature: app startup\n  Failed at: build/start\n  Observation: {startup_error_digest(infrastructure_error, 600)}\n  Steps: npm run build -> npm start"
                passed = 0
            else:
                passed = summary.passed
                failures = failure_summaries(summary) + failure_source_context(summary, self.tests_dir)
                if measured:
                    self.record_tests(node_id, specs, summary)
            log(f"[acceptance] {node_id} round {attempt}: {passed}/{summary.total}")
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
            if measured and passed == summary.total:
                current_versions = self.repair_source_index().versions
                changed = {p for p in initial_versions.keys() | current_versions.keys()
                           if initial_versions.get(p) != current_versions.get(p)}
                regression_specs = self.affected_regression_specs(changed, specs)
                if regression_specs and not self.wound_down() and self.remaining() > self.final_measurement_reserve():
                    regression = self.run_specs(regression_specs, grader_like=True)
                    self.metric("acceptance", scope="affected_regression", node_id=node_id,
                                passed=regression.passed, total=regression.total,
                                changed_files=sorted(changed))
                    if not regression.all_passed or not self.suite_is_measured(regression, regression_specs):
                        self.pending_corrections.append("Related regression checks after the targeted repair:\n" +
                            balanced_failure_evidence(failure_summaries(regression) or regression.error or "Incomplete regression verdict", 4000))
                        # Do not certify a repair that broke its surrounding behaviour.
                        return False
                self.commit(f"{node_id} (accepted): {passed}/{summary.total} acceptance tests pass")
                return True
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
            if attempt == self.repair_rounds or self.wound_down():
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
                return REPAIR_PROMPT.format(node_id=node_id, passed=passed, total=summary.total,
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
        if best_passed > 0 and best_sha:
            self.restore_app(best_sha)
            self.commit(f"{node_id}: keep best acceptance state {best_passed}")
        return False if best_passed >= 0 else None

    # -- per node ---------------------------------------------------------
    def design(self, node: dict, ordered: list[dict], deadline: float) -> dict | None:
        node_id = str(node.get("id"))
        prompt = DESIGN_PROMPT.format(node_id=node_id, node_spec=describe_node(node),
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
        if (os.environ.get("OCTOS_ARC_WHOLE_APP", "1") == "0" or self.evolution
                or len(ids) < 3 or self.runner is None or not self.codegen_mode()
                or not self.tests_dir or any(not self.spec_map.get(node_id) for node_id in ids)
                or self.wound_down() or self.remaining() < self.min_repair_seconds + 180):
            return False
        spec = self.batch_spec_bodies(ids)
        if spec == "(none)":
            return False
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
        ok, text = self.codegen_turn(prompt, timeout, label, spec_chars=spec_chars)
        if ok and (getattr(self, "last_codegen_written", [])
                   or getattr(self, "last_codegen_no_change", False) is True):
            return ok, text
        format_error = (text.startswith("codegen reply contained no ")
                        or text.startswith("mixed FILE and EDIT blocks"))
        correction = ("\nThe preceding answer was discarded without writing files: " + text[:240] +
                      "\nReturn ONLY complete <<<FILE ...>>> blocks, with exact "
                      "<<<END FILE>>> terminators. One block per path. "
                      "Do not explain the implementation.\n")
        retry_seconds = min(360, int(deadline - time.monotonic()))
        if (format_error and not getattr(self, "last_codegen_degenerated", False)
                and retry_seconds >= 30 and not self.wound_down()
                and self.remaining() >= self.min_repair_seconds + 120
                and len(prompt) + len(correction) + len(FORMAT_INSTRUCTIONS) + 1
                <= self.codegen_context_chars()):
            log(f"[flow] {label}: format rejected; one corrected reply before splitting")
            self.whole_app_generation_requests += 1
            return self.codegen_turn(prompt + correction, retry_seconds, label + " (format retry)",
                                     spec_chars=spec_chars)
        return ok, text

    def whole_app_waves(self, tree: dict, ordered: list[dict]) -> bool:
        """Generate contiguous, dependency-ordered feature groups before testing.

        The planner halves a group when its shared prompt exceeds the input
        budget or its reply exceeds the output limit. A single unfittable leaf
        hands control back to the established per-node tool fallback. The
        application design is the common contract across waves. If the model's
        design turn failed, a bounded whole-tree outline supplies that context
        instead. No task- or test-specific code is preloaded.
        """
        global_context = ""
        if not getattr(self, "app_design_doc", None):
            global_context = ("Whole-tree requirement map (keep a common data and route contract "
                              "across waves):\n" + tree_outline(tree, max_chars=12000) + "\n\n")
            log("[flow] whole-app waves: design reply unavailable; using bounded requirement map")
        max_nodes = max(1, int(os.environ.get("OCTOS_ARC_WHOLE_APP_WAVE_NODES", "6")))
        configured_max_nodes = max_nodes
        clean_waves = 0
        max_spec = min(30000, int(self.codegen_context_chars() * 0.35))
        max_details = min(24000, int(self.codegen_context_chars() * 0.25))
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
        attempts = 0
        requests_before = getattr(self, "whole_app_generation_requests", 0)
        while start < len(ordered):
            if self.remaining() < self.min_repair_seconds + 120 or self.wound_down():
                log("[flow] whole-app waves: insufficient budget; measuring any partial application")
                return wave > 0
            size = min(max_nodes, len(ordered) - start)
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
                spec = self.batch_spec_bodies(ids)
                details = "\n\n".join(describe_node(node) for node in group)
                estimated = generation_tokens(group, len(spec))
                if (len(spec) > max_spec or len(details) > max_details
                        or estimated > self.generation_output_budget()) and size > 1:
                    size = max(1, size // 2)
                    continue
                combined = {"id": f"application wave {wave + 1}",
                            "description": "Implement ALL of these requirements as one coherent feature group "
                                           "within the shared application. Preserve previously generated "
                                           "features and their data contracts. Do not defer a listed requirement "
                                           "to a later wave.\n\n" + global_context + details}
                prompt = self.codegen_implement_prompt(combined, spec)
                if prompt is None:
                    if size > 1:
                        size = max(1, size // 2)
                        continue
                    log(f"[flow] whole-app waves: {ids[0]} cannot fit alone; using node flow")
                    self.whole_app_deferred_ids.update(ids)
                    start += size
                    break
                write_codegen_manifests(self.output_dir)
                timeout = min(int(os.environ.get("OCTOS_ARC_WHOLE_APP_TIMEOUT", "1800")),
                              max(120, self.remaining() - self.min_repair_seconds))
                log(f"[flow] whole-app wave {wave + 1}: generating {ids} "
                    f"({len(prompt)} prompt chars, {len(spec)} spec chars, "
                    f"estimated output {estimated}/{self.generation_output_budget()} tokens)")
                attempts += 1
                ok, text = self.whole_app_generation_turn(prompt, timeout,
                                                          f"whole application wave {wave + 1}",
                                                          spec_chars=len(spec))
                if not ok or not (getattr(self, "last_codegen_written", [])
                                  or getattr(self, "last_codegen_no_change", False) is True):
                    clean_waves = 0
                    if getattr(self, "last_codegen_written", []):
                        self.commit(f"whole application wave {wave + 1} (partial; requires verification)")
                        self.whole_app_partial_ids.update(ids)
                        start += size
                        wave += 1
                        log(f"[flow] partial wave retained for {ids}; continuing remaining feature groups")
                        break
                    if size > 1:
                        log(f"[flow] whole-app wave {wave + 1}: no complete write "
                            f"({text[-120:]}); splitting group")
                        max_nodes = min(max_nodes, (size + 1) // 2)
                        size = max(1, size // 2)
                        continue
                    log(f"[flow] whole-app wave {wave + 1}: deferring {ids[0]} to targeted repair; "
                        "continuing remaining feature groups")
                    self.whole_app_deferred_ids.update(ids)
                    start += size
                    break
                self.commit(f"whole application wave {wave + 1} (experimental implement)")
                self.whole_app_generated_ids.update(ids)
                clean_waves += 1
                if clean_waves >= 2:
                    max_nodes = min(configured_max_nodes, max_nodes * 2)
                    clean_waves = 0
                start += size
                wave += 1
                break
        log(f"[flow] whole-app waves: {len(self.whole_app_generated_ids)} complete, "
            f"{len(self.whole_app_partial_ids)} partial, {len(self.whole_app_deferred_ids)} deferred leaves "
            f"in {wave} applied waves "
            f"({attempts} group attempts, "
            f"{getattr(self, 'whole_app_generation_requests', 0) - requests_before} model turns); "
            "running first full suite")
        return wave > 0

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
                  "of the same method, register the literal handler first. Do not rewrite unrelated files.\n"
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
            preflight = "generic scaffold route checks failed:\n" + "\n".join(issues[:8])
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
            if not summary.error or summary.killed or summary.error in attempted_errors:
                break
            attempted_errors.add(summary.error)
            if not self.whole_app_startup_repair(summary.error):
                break
            log(f"[flow] whole-app first suite: repaired startup failure {attempt + 1}/2; retrying full suite")
            summary = measure()
        observed_files = {Path(result.file or "").name for result in summary.results}
        if (summary.error or summary.load_errors or not summary.results or summary.total != len(summary.results)
                or any(Path(spec).name not in observed_files for spec in specs)):
            log(f"[flow] whole-app first suite: no reliable verdict "
                f"({(summary.error or 'incomplete results')[:150]}); preserving app for final repair")
            return None
        grouped = nodes_for_failures(summary.results, self.spec_map)
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
        grouped = nodes_for_failures(summary.results, self.spec_map)
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
        """Generate globally, verify globally, then repair only failing leaves."""
        if not self.whole_app_codegen(tree, ordered):
            return False
        failing = self.whole_app_first_suite(ordered)
        if failing is not None:
            failing = self.whole_app_shared_repair(ordered, failing)
        generated = getattr(self, "whole_app_generated_ids", None)
        if generated is None:
            generated = {str(node.get("id")) for node in ordered}
        if failing is None:
            # The application has already been written. A build/start problem is
            # not evidence that all features need regenerating. Preserve the
            # tree for the final suite's targeted startup-repair path.
            log("[flow] whole-app first suite unavailable; preserving generated app for final targeted repair")
            for index, node in enumerate(ordered, 1):
                node_id = str(node.get("id"))
                if node_id not in generated:
                    if self.time_up():
                        self.mark("implementation_failed", node_id, "wave did not reach this node: time budget exhausted")
                        self.impl_failed.append(node_id)
                    else:
                        self.node_cycle(node, ordered, index, len(ordered))
                        self.driver.end_scope("node")
                    continue
                self.mark("design_started", node_id)
                self.mark("design_done", node_id, "covered by whole-application design")
                self.mark("implementation_started", node_id)
                self.mark("implementation_done", node_id, "implemented by whole-app generation")
                self.mark("test_failed", node_id, "first full suite could not report reliable results")
                self.test_verdict[node_id] = False
            return True
        repair_budget = self.remaining()
        repair_count = sum(str(node.get("id")) in failing for node in ordered)
        repairs_done = 0
        for index, node in enumerate(ordered, 1):
            node_id = str(node.get("id"))
            if node_id not in failing:
                self.mark("design_started", node_id)
                self.mark("design_done", node_id, "covered by whole-application design")
                self.mark("implementation_started", node_id)
                self.mark("implementation_done", node_id, "implemented by whole-app generation")
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
        self.codegen_blocked = False  # a previous node's fallback to tool mode must not leak into this one
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
        design_text = stack_note(self.output_dir) + design_text
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
        elif not corrections and self.codegen_mode() and self.tiny_mode(len(self.spec_bodies(node_id))):
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
                        log(f"[flow] {node_id}: {', '.join(sorted(refused))} cannot be quoted whole within the budget; no retry")
            else:
                if self.codegen_mode():
                    self.log_codegen_fallback(node_id)
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
        timed_out = (not ok) and "timed out" in text.lower()
        if ok and not self.has_app():
            # v6-counter: one package.json missing after the turn. Do not give
            # up — the acceptance loop's build error becomes the repair prompt.
            log(f"[flow] {node_id}: app layout incomplete after the turn; acceptance loop will drive the repair")
            self.pending_corrections.append(
                "Your turn ended without both frontend/package.json and backend/package.json (with `build` and "
                "`start` scripts) on disk; the harness could not even build the app. Create the missing files.")
        can_verify_existing = self.has_app() and self.runner is not None and bool(specs)
        if not ok and not timed_out and not can_verify_existing:
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

        verdict = self.acceptance_loop(node_id, specs, deadline, rebuild_prompt=rebuild_prompt)
        self.test_verdict[node_id] = verdict
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
                out.add(node_id)
                self.probe_summaries[node_id] = summary  # regression_cycle reuses it
        return out

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
                verdict = summary.all_passed
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

    def regression_checkpoint(self, index: int, total: int) -> None:
        start = int(os.environ.get("OCTOS_ARC_REGRESSION_CHECKPOINT", "4"))
        reserve = self.final_phase_reserve()
        if (not regression_checkpoint_due(index, total, start) or self.runner is None
                or not self.tests_dir or self.remaining() < self.min_repair_seconds + reserve):
            return
        tracked = getattr(self, "checkpoint_regressions", set())
        self.checkpoint_regressions = tracked
        verified = {node: self.spec_map.get(node, []) for node, verdict in self.test_verdict.items()
                    if verdict is True or node in tracked}
        specs = sorted({spec for paths in verified.values() for spec in paths})
        if len(specs) < 2:
            return
        workers = workers_for_final(getattr(self, "mem_limit", None),
                                    self.final_workers())
        summary = self.run_specs(specs, workers=workers, grader_like=True)
        if summary.error or summary.killed:
            log(f"[acceptance] checkpoint {index}: no reliable verdict; {summary.error or 'runner killed'}")
            return
        grouped = nodes_for_failures(summary.results, verified)
        log(f"[acceptance] checkpoint {index}: {summary.passed}/{summary.total}; "
            f"regressed nodes {sorted(node for node in grouped if node)}")
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
                self.test_verdict[node] = True
                self.mark("test_passed", node, "previously regressed behavior passed its checkpoint specs")
        regressed = bool(grouped)
        if grouped:
            self.queue_checkpoint_evidence(summary)
            regressed = self.repair_regressions(index, specs, verified, tracked, summary, grouped, workers)
        if not regressed:
            # The tree the suite agreed with: the next suite repair quotes what
            # changed since it first. A checkpoint still regressed keeps the
            # previous baseline, so the files that introduced the regression
            # stay in the diff until it is fixed.
            self.last_checkpoint_sha = self.head()

    def queue_checkpoint_evidence(self, summary: RunSummary) -> None:
        """Bound checkpoint evidence, keeping both ends when source context is large."""
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
        for attempt in range(rounds):
            reserve = self.final_phase_reserve()
            if (not grouped or self.remaining() < self.repair_minimum() + reserve
                    or self.wound_down()):
                break
            # Re-read after admission so time consumed between rounds cannot be
            # lent to this turn by a stale sample.
            available = self.remaining() - reserve
            failing_ids = sorted(node for node in grouped if node)
            failing = failing_ids or ["the regressed behaviours"]
            failures = failure_summaries(summary) + failure_source_context(summary, self.tests_dir)
            repaired = True
            tool_prompt = REPAIR_PROMPT.format(
                node_id=", ".join(failing), passed=summary.passed, total=summary.total, failures=failures,
                test_location=self.repair_test_location(),
                sources=self.repair_requirements() + self.sources_text(),
                corrections=self.corrections_text(), slow="",
                smoke=self.smoke_port, port=self.web_port)
            # The first round is one codegen request; a second round, if configured,
            # is the changed approach.
            self.suite_repair_turn(f"checkpoint {index} repair {attempt + 1}/{rounds}", failing_ids, failures,
                                   min(self.suite_repair_timeout(), max(1, available)),
                                   tool_prompt=tool_prompt, prefer_codegen=attempt == 0)
            self.commit(f"fix: checkpoint {index} regression repair {attempt + 1}")
            if getattr(self, "last_repair_changed", None) is False:
                log(f"[acceptance] checkpoint {index}: no source changes; skipping duplicate acceptance")
                break
            observed = self.run_specs(specs, workers=workers, grader_like=True)
            if observed.error or observed.killed:
                self.queue_checkpoint_evidence(summary)
                return True
            summary = observed
            grouped = nodes_for_failures(summary.results, verified)
            log(f"[acceptance] checkpoint {index} after repair: {summary.passed}/{summary.total}; "
                f"still regressed {sorted(node for node in grouped if node)}")
            for node in verified:
                if node and node not in grouped:
                    tracked.discard(node)
                    self.test_verdict[node] = True
                elif node:
                    tracked.add(node)
                    self.test_verdict[node] = False

        if repaired and grouped:
            # corrections_text consumed the initial checkpoint evidence. Keep
            # the latest still-failing observations for the next implementation.
            self.queue_checkpoint_evidence(summary)
        return bool(grouped)

    def final_acceptance(self) -> None:
        """Run EVERY spec file together against one server with the configured workers.
        Per-node runs cannot see cross-node interference through shared server
        state; this pass can, and it repairs the nodes whose tests fail."""
        self.final_repair_no_change = False
        self.final_suite_progress = False
        self.final_suite_green = False
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
        rounds = int(os.environ.get("OCTOS_FINAL_REPAIR_ROUNDS", "3"))
        confirm_runs = max(1, int(os.environ.get("OCTOS_ARC_FINAL_CONFIRM_RUNS", "2")))
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
            summary = measured_suite()
            if (best is not None and last_repair_mode == "codegen" and wrote_last
                    and self.suite_is_measured(summary, all_specs) and best["passed"] - summary.passed >= 3):
                # A one-request rewrite that breaks several previously passing
                # behaviours is different from a single flaky spec or a tool
                # turn interrupted halfway through. Keep the measured evidence,
                # but repair from the last good tree rather than spending another
                # codegen round on the damage (Keep 62886df9bde1: 31 -> 25).
                damaged = nodes_for_failures(summary.results, self.spec_map)
                newly_broken = {n for n in damaged if n and n not in best["grouped"]}
                if len(newly_broken) >= 2 and best["sha"]:
                    log(f"[acceptance] full suite: codegen repair regressed {best['passed']} -> "
                        f"{summary.passed}, newly failing {sorted(newly_broken)}; restoring best state")
                    self.restore_app(best["sha"])
                    restored_this_round = True
                    self.pending_corrections.append(
                        f"The last broad codegen repair broke {', '.join(sorted(newly_broken))}. "
                        "The harness restored frontend/ and backend/ to the best state. "
                        "Repair the original failure with a targeted edit; preserve passing behaviours.")
                    summary = measured_suite()
                    force_tool_repair = True
                    last_repair_mode = ""
            if summary.all_passed and self.suite_is_measured(summary, all_specs):
                # A single lucky 32/32 did not reproduce in the platform's next
                # clean run (Keep 62886df9bde1: 32/32 -> 30/32). Confirmation
                # uses the unchanged app and costs no model tokens.
                for confirmation in range(1, confirm_runs):
                    confirmed = measured_suite()
                    if not confirmed.all_passed or not self.suite_is_measured(confirmed, all_specs):
                        owners = {Path(path).name: node for node, paths in self.spec_map.items()
                                  for path in (paths or [])}
                        passed_a_round.update(owners.get(Path(r.file or "").name)
                                              for r in summary.results if r.ok)
                        passed_a_round.discard(None)
                        log(f"[acceptance] full suite confirmation {confirmation + 1}/{confirm_runs}: "
                            f"{confirmed.passed}/{confirmed.total}; first green run was not stable")
                        summary = confirmed
                        break
                    log(f"[acceptance] full suite confirmation {confirmation + 1}/{confirm_runs}: "
                        f"{confirmed.passed}/{confirmed.total}")
            if summary.error and summary.killed:
                log(f"[acceptance] full suite could not run ({summary.error[:120]}); keeping per-node verdicts")
                break
            measured = self.suite_is_measured(summary, all_specs)
            self.verify_repair_memory(summary, measured)
            if not measured:
                error = summary.error or "\n".join(summary.load_errors) or "Incomplete acceptance report; not all specs produced results"
                log(f"[acceptance] full suite has no complete verdict: {error[:300]}")
                for node_id in self.spec_map:
                    if node_id:
                        self.test_verdict[node_id] = None
                grouped = {None: []}
                failures = (f"- Feature: application startup exactly as the grader runs it (only PORT set)\n"
                            f"  Failed at: build/start/test loading\n  Observation: {startup_error_digest(error)}\n"
                            "  No complete functional verdict. Fix the reported infrastructure problem in place; do not rewrite the app.")
            else:
                grouped = nodes_for_failures(summary.results, self.spec_map)
                failures = failure_summaries(summary) + failure_source_context(summary, self.tests_dir)
                failures += self.interference_note(grouped, passed_alone, summary.stores_written)
                failures += self.intermittent_note(grouped, passed_a_round)
                failures += self.worker_parity_note(workers)
                owners = {Path(path).name: node for node, paths in self.spec_map.items()
                          for path in (paths or [])}
                passed_a_round |= {owners.get(Path(r.file or "").name)
                                   for r in summary.results if r.ok} - {None}
            log(f"[acceptance] full suite round {attempt}: {summary.passed}/{summary.total}; failing nodes "
                f"{sorted(k for k in grouped if k) or ('all' if None in grouped and not summary.results else [])}")
            self.metric("acceptance", scope="final_suite", round=attempt, passed=summary.passed,
                        total=summary.total, after_applied_repair=wrote_last and not restored_this_round,
                        restored_before_measurement=restored_this_round,
                        verdict="measured" if measured else "unknown", error=summary.error,
                        load_errors=summary.load_errors)
            self.record_full_suite(summary, grouped)
            self.remember_delivery_checkpoint(summary, grouped)
            last_passed = summary.passed if measured else -1
            if measured and (best is None or summary.passed > best["passed"]):
                if best is not None and wrote_last and not restored_this_round:
                    self.final_suite_progress = True
                if attempt > 0:
                    self.commit(f"chore: full acceptance suite {summary.passed}/{summary.total} (best so far)")
                best = {"passed": summary.passed, "sha": self.head(), "summary": summary, "grouped": grouped}
                regressions = 0
            elif measured and best is not None and summary.passed < best["passed"]:
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
            if measured and not grouped:
                self.final_suite_green = True
                self.commit(f"chore: full acceptance suite {summary.passed}/{summary.total} pass (full suite)")
                return
            # A spec that has passed once in this pass and fails now is unstable;
            # letting it count as progress hides a stall in everything else.
            unstable = frozenset(spec for node in passed_a_round
                                 for spec in (self.spec_map.get(node) or []))
            failing_signature = failure_signature(summary, unstable)
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
                from source_index import failure_groups
                clusters = failure_groups({k: v for k, v in grouped.items() if k}, self.requirement_source_targets())
                visits = getattr(self, "_repair_group_visits", {})
                active = min(clusters, key=lambda ids: (visits.get(tuple(ids), 0), -len(ids), ids))
                visits[tuple(active)] = visits.get(tuple(active), 0) + 1
                self._repair_group_visits = visits
                if len(clusters) > 1:
                    overview = f"All failing requirement IDs: {', '.join(failing)}. Active repair group: {', '.join(active)}. Other groups are deferred, not passed.\n"
                    focused = RunSummary(results=[r for n in active for r in grouped[n]])
                    failures = overview + failure_summaries(focused) + failure_source_context(focused, self.tests_dir)
                    failing = active
                    self.metric("repair_group", active=active, groups=clusters)
            failures += self.unfinished_repair_note(unfinished)
            prompt = REPAIR_PROMPT.format(
                node_id=", ".join(failing), passed=summary.passed, total=summary.total, failures=failures,
                test_location=self.repair_test_location(),
                sources="\n".join(self.repair_requirements(n) for n in failing) + self.sources_text(),
                corrections=self.corrections_text() + "The full suite runs all spec files against one "
                "server; tests from different files must not interfere through shared server state "
                "(e.g. a counter that every browser session shares). Keep persisted data only where the "
                "requirement demands persistence.\n",
                slow="", smoke=self.smoke_port, port=self.web_port)
            # One codegen request first; a round that reproduced the previous failures
            # is the changed approach, and that one uses tools.
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
                self._force_final_tool_repair = True
                self.pending_corrections.append(
                    "The previous full-suite repair changed no application source. Do not only describe a fix: "
                    "inspect the current implementation and apply a concrete, targeted source edit before verification.")
                log("[acceptance] full suite: repair changed no application sources; "
                    "deferring remeasurement and changing approach on the next pass")
                break
        # L17 (ported from the Rust harness): deliver the best full-suite round, not the last one.
        if best is not None and best["sha"] and last_passed < best["passed"]:
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
                    and all(r.status in {"passed", "failed", "timedOut"} for r in summary.results)
                    and all(any(path == spec or path.endswith("/" + spec) for path in observed) for spec in specs))

    def final_acceptance_passes(self) -> None:
        """Repeat the full-suite pass while it still fails and the budget allows.

        Cloud 3ffe9702bf15 delivered 25/32 after spending 5754 s of a 48000 s
        budget: one pass ran, its repairs stalled, and the run ended with the
        rest of the time unused. Every pass keeps its own best state, so a
        repeat starts from a state at least as good as the one before it.
        """
        configured_passes = os.environ.get("OCTOS_FINAL_SUITE_PASSES")
        # By default the run-wide time/token/turn guards, not a three-pass
        # constant, decide when a still-red suite must stop.  Keep an explicit
        # override for controlled comparisons and constrained deployments.
        passes = max(1, int(configured_passes)) if configured_passes is not None else \
            max(3, int(getattr(self, "max_turns", 3)) if getattr(self, "max_turns", -1) > 0 else 3)
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
            self.final_acceptance()
            if self.driver:
                self.driver.end_scope("node")
            if (getattr(self, "final_suite_green", False)
                    or (self.test_verdict and all(verdict is True for verdict in self.test_verdict.values()))):
                break
            if self.wound_down() or self.remaining() < self.final_retry_admission():
                log(f"[flow] full suite still failing, but {self.remaining():.0f}s is below the "
                    f"{self.final_retry_admission():.0f}s needed to measure, repair, and remeasure")
                break
            if getattr(self, "final_repair_no_change", False) is True:
                log("[flow] full-suite repair made no source change; retrying with a changed repair approach")
                continue
            if getattr(self, "final_suite_progress", False) is not True:
                self._force_final_tool_repair = True
                self.pending_corrections.append(
                    "The previous full-suite pass did not increase the measured pass count. Reinspect the failing "
                    "interaction end to end and use a different targeted repair approach; preserve the best state.")
                log("[flow] full-suite pass made no measured pass-count improvement; "
                    "budget remains, so changing approach instead of stopping")

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
        if best and summary.passed <= best["summary"].passed:
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
        if not best or best["summary"].passed <= 0:
            return False
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

    def record_full_suite(self, summary: RunSummary, grouped: dict) -> None:
        """Per-node verdicts and traceability from one full-suite round."""
        if summary.error or summary.killed or summary.load_errors:
            return
        for node_id, specs in self.spec_map.items():
            if node_id and specs and summary.results:
                rows = [r for r in summary.results if any(
                    str(r.file or "").replace("\\", "/") == p or
                    str(r.file or "").replace("\\", "/").endswith("/" + p) for p in specs)]
                local = RunSummary(results=rows, total=len(rows), passed=sum(r.ok for r in rows))
                if self.suite_is_measured(local, specs):
                    self.record_tests(node_id, specs, local)
                    self.test_verdict[node_id] = local.all_passed
                else:
                    self.test_verdict[node_id] = None

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

    # -- final ------------------------------------------------------------
    def rehearsal(self) -> bool:
        for attempt in range(1, 4):
            log(f"[rehearsal] startup rehearsal {attempt}/3 (smoke port {self.smoke_port}, grader-like env)")
            server = self.app_server(grader_like=True)
            err = server.build() or server.start()
            server.stop()
            if err is None:
                log("[rehearsal] app builds and starts cleanly")
                return True
            log(f"[rehearsal] FAILED: {err.splitlines()[0][:200]}")
            if attempt == 3 or self.remaining() < self.repair_minimum() or self.wound_down():
                log("[rehearsal] giving up; submitting as-is")
                return False
            self.turn(REHEARSAL_REPAIR_PROMPT.format(error=clip_ends(err, 1200), port=self.web_port, smoke=self.smoke_port),
                      min(self.node_timeout, max(1, self.remaining())), f"rehearsal repair {attempt}")
            # Any post-acceptance edit invalidates the earlier verdicts.
            if self.last_turn_changed:
                self.test_verdict = {key: None for key in self.test_verdict}
            self.commit("fix: startup rehearsal repair")
        return False

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

    # -- run --------------------------------------------------------------
    def run(self) -> int:
        self.runtime = AgentRuntime.from_env(project_dir=str(self.output_dir))
        self.events = self.runtime.events
        self.events.mark_run_started("octos bundle started")
        ordered: list[dict] = []
        watchdog_stop = threading.Event()
        try:
            previous = previous_requirement_records(self.output_dir)
            tree = load_requirement_tree(self.req_dir)
            self.runtime.traceability.store_requirement_tree(tree)
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
                log("[tests] no acceptance specs found; building from requirement text only")

            self.maybe_probe(node_ids)
            self.runtime.git.ensure_repo()
            self.setup_playwright()
            if self.evolution and self.runner is not None:
                # The platform's template app carries no traceability records, so
                # fingerprints cannot tell what is new. A node whose specs already
                # pass against the existing app is unchanged — no LLM turn for it.
                unchanged |= self.already_passing_nodes([n for n in node_ids if n not in unchanged])
                if self.probe_count and not unchanged:
                    # Nothing of the existing app satisfies any spec (a scaffold/placeholder
                    # template, or an app the new specs no longer accept): it is not a usable
                    # base. Set it aside and build the task fresh (cloud c30b29eab45b/10b04d36f704:
                    # implement-then-rewrite on a placeholder cost 40-80x the fresh build).
                    self.discard_template()
                    self.evolution = False
                self.nodes_to_implement = len([n for n in node_ids if n not in unchanged])
                log(f"[flow] {'evolution' if self.evolution else 'fresh build'} after probing the existing app: "
                    f"unchanged {sorted(unchanged)}, to implement {[i for i in node_ids if i not in unchanged]}")

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
            self.snapshot_protected()
            env["PORT"] = str(self.smoke_port)  # a bare `npm start` inside a turn must not hit the grading port
            self.driver = DryRunDriver() if dry_run else OctosDriver(
                octos_bin, self.output_dir, env, data_dir, int(os.environ.get("OCTOS_MAX_ITERATIONS", "500")),
                events_log=self.output_dir / ".arc" / "octos-events.jsonl")
            self.driver.hooks = protected_hooks(protected)
            threading.Thread(target=_port_watchdog, args=(self.web_port, self.output_dir, watchdog_stop),
                             daemon=True).start()
            try:
                self.prepare_build(tree, ordered)
                if (self.evolution and self.runner is not None and self.tests_dir
                        and unchanged == set(node_ids) and len(node_ids) > 1):
                    # Repair-only evolution has no new leaves to generate. One
                    # full baseline reveals shared failures and establishes a
                    # comparable delivery checkpoint before spending model tokens.
                    log("[flow] unchanged requirements: measure and repair the existing application as one suite")
                    for node_id in node_ids:
                        self.mark("design_started", node_id)
                        self.mark("design_done", node_id, "unchanged requirement; carried over")
                        self.mark("implementation_started", node_id)
                        self.mark("implementation_done", node_id, "existing application; acceptance pending")
                elif not self.whole_app_experiment(tree, ordered):
                    batch_size = int(os.environ.get("OCTOS_ARC_SIBLING_BATCH_SIZE", "3"))
                    batch_starts = {group[0]: group for group in sibling_batches(tree, ordered, batch_size)}
                    preimplemented: set[str] = set()
                    for index, node in enumerate(ordered, 1):
                        node_id = str(node.get("id"))
                        if self.time_up():
                            log(f"[flow] time budget exhausted; skipping {node_id}")
                            self.mark("implementation_started", node_id)
                            self.mark("implementation_failed", node_id, "skipped: time budget exhausted")
                            self.impl_failed.append(node_id)
                            continue
                        if node_id in unchanged:
                            self.regression_cycle(node)
                        else:
                            group = batch_starts.get(node_id)
                            if group and not any(member in unchanged for member in group):
                                group_nodes = [ordered[index - 1 + offset] for offset in range(len(group))]
                                if self.batch_codegen(group_nodes):
                                    preimplemented.update(group)
                            self.node_cycle(node, ordered, index, len(ordered),
                                            preimplemented=node_id in preimplemented)
                        self.regression_checkpoint(index, len(ordered))
                        self.driver.end_scope("node")

                self.final_acceptance_passes()
                undecided = [i for i in node_ids if self.test_verdict.get(i) is None and i not in self.impl_failed]
                final_ok = None
                if undecided and self.runner is None and not self.time_up() and not self.wound_down():
                    log(f"[flow] final check turn for nodes without a local verdict: {undecided}")
                    final_ok, _ = self.turn(FINAL_CHECK_PROMPT.format(smoke=self.smoke_port, port=self.web_port,
                                                                      tests=self.tests_prompt_for(None),
                                                                      performance=self.perf_text(), ui=self.ui_contract()),
                                            self.node_timeout, "final check")
                    self.commit("chore: final verification pass")
                rehearsed = self.rehearsal()
                if rehearsed and any(value is None for value in self.test_verdict.values()) and self.runner is not None:
                    self.final_acceptance_passes()
                for node_id in undecided:
                    if self.runner is not None and self.spec_map.get(node_id):
                        # Starting the server is not proof that a feature works.
                        continue
                    if rehearsed and final_ok is not False:
                        self.mark("test_passed", node_id, "final check and startup rehearsal passed")
                    else:
                        self.mark("test_failed", node_id, "final check or startup rehearsal failed")
                    self.test_verdict[node_id] = bool(rehearsed and final_ok is not False)
            finally:
                watchdog_stop.set()
                self.postflight()
            for node_id in node_ids:  # final per-node verdicts (full-suite run may have changed them)
                if self.test_verdict.get(node_id) is True:
                    self.mark("test_passed", node_id, "acceptance specs pass (node run and full parallel suite)")
                elif self.test_verdict.get(node_id) is False:
                    self.mark("test_failed", node_id, "acceptance specs failing")
            self.mark_folders()
            self.commit("chore: traceability and acceptance state")
            failed = [i for i in node_ids if self.test_verdict.get(i) is not True]
            if failed:
                self.events.mark_run_completed(f"completed; nodes not verified: {', '.join(failed)}")
            else:
                self.events.mark_run_completed("all requirement nodes implemented and verified")
            _reap_stray_processes("postflight", self.output_dir)
            _postflight_structure_check(self.output_dir)
            _free_web_port(self.web_port, self.output_dir)
            self.write_preview_ready()
            return 0
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
