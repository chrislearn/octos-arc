#!/usr/bin/env python3
"""Platform glue for the Rust harness (`OCTOS_ARC_ENGINE=rust`).

`main.py` still holds the default Python strategy; when the switch is on it
hands over to this module, which keeps only the platform-facing work:

    read the task and locate the tests  ->  write .arc/runner-spec.json
    prepare the workspace (git, ARC traceability tables)
    run `octos arc run --spec ... --policy arc/arc-policy.toml`
    translate the kernel's event stream into ARC runner-events / traceability
    postflight (stray processes, nested app, grading port, preview marker)

Every strategy decision (turn shapes, budgets, repairs, prompts) lives in the
kernel and in arc-policy.toml / prompts/*.md.
"""

from __future__ import annotations

import json
import os
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path

BUNDLE_DIR = Path(__file__).resolve().parent
EVENT_PREFIX = "@@arc-event "

# (phase, status) -> EventClient.mark_* name
MARKS = {
    ("design", "running"): "mark_design_started",
    ("design", "completed"): "mark_design_done",
    ("design", "failed"): "mark_design_failed",
    ("implement", "running"): "mark_implementation_started",
    ("implement", "completed"): "mark_implementation_done",
    ("implement", "failed"): "mark_implementation_failed",
    ("test", "passed"): "mark_test_passed",
    ("test", "failed"): "mark_test_failed",
}


def parse_event(line: str) -> dict | None:
    """`@@arc-event {json}` -> dict; anything else -> None."""
    if not line.startswith(EVENT_PREFIX):
        return None
    try:
        payload = json.loads(line[len(EVENT_PREFIX):])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


class Translator:
    """Turn kernel events into ARC SDK calls. Pure with respect to the
    runtime object so it can be tested with a stub."""

    def __init__(self, runtime, log) -> None:
        self.runtime = runtime
        self.log = log
        self.final: dict | None = None
        self.test_passed: set[str] = set()

    def handle(self, event: dict) -> None:
        kind = event.get("event")
        if kind == "requirement_state":
            method = MARKS.get((event.get("phase"), event.get("status")))
            if method is None:
                return
            node_id = str(event.get("node_id") or "")
            message = event.get("message")
            getattr(self.runtime.events, method)(node_id, message)
            for alias in event.get("aliases") or []:
                getattr(self.runtime.events, method)(str(alias), message)
            if (event.get("phase"), event.get("status")) == ("test", "passed") and node_id not in self.test_passed:
                self.test_passed.add(node_id)
                try:
                    for iface in self.runtime.traceability.list_interfaces(req_id=node_id):
                        self.runtime.traceability.set_interface_implemented(iface["interface_id"], True, emit_event=False)
                except Exception:  # noqa: BLE001
                    pass
        elif kind == "test_result":
            try:
                self.runtime.traceability.upsert_test(
                    test_id=str(event.get("test_id") or "")[:120], req_id=str(event.get("node_id") or ""),
                    type=str(event.get("type") or "e2e"), file_path=event.get("file") or None,
                    passed=bool(event.get("ok")), emit_event=False)
            except Exception as exc:  # noqa: BLE001
                self.log(f"[trace] test row not recorded: {exc}")
        elif kind == "design":
            node_id = str(event.get("node_id") or "")
            design = event.get("design") or {}
            try:
                self.runtime.traceability.upsert_node_contract(node_id, design)
                for i, route in enumerate(design.get("routes") or []):
                    if isinstance(route, dict):
                        self.runtime.traceability.upsert_interface(
                            interface_id=f"{node_id}:route:{i}", req_ids=[node_id], type="http",
                            content=f"{route.get('method', '')} {route.get('path', '')}".strip(), emit_event=False)
            except Exception as exc:  # noqa: BLE001
                self.log(f"[trace] design not recorded: {exc}")
        elif kind == "commit":
            self.runtime.events.notify_commit_history_changed("git_commit", preview=True)
        elif kind in ("run_completed", "run_failed"):
            self.final = event


def log_factory():
    def log(msg: str) -> None:
        print(msg, flush=True)
        print(msg, file=sys.stderr, flush=True)
    return log


def snapshot_previous_requirements(output_dir: Path) -> Path:
    """Copy the previous run's `.arc/traceability/requirements.json` (committed with an
    Evolution template) to `.arc/previous-requirements.json` before the runtime stores
    the new tree over it. Always written — `{}` when the template carries no table — so
    the kernel never mistakes the freshly stored tree for the previous one."""
    source = output_dir / ".arc" / "traceability" / "requirements.json"
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    target = output_dir / ".arc" / "previous-requirements.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def write_runner_spec(path: Path, *, req_dir: Path, output_dir: Path, web_port: int, tests_dir: Path | None,
                      previous_requirements: Path | None = None) -> dict:
    base_url = os.environ.get("OPENAI_BASE_URL", "")
    provider = os.environ.get("OCTOS_PROVIDER") or ("anthropic" if "anthropic" in base_url else "openai")
    spec = {
        "schema_version": 1,
        "requirement_path": str(req_dir),
        "output_dir": str(output_dir),
        "web_port": int(web_port),
        "tests_dir": str(tests_dir) if tests_dir else None,
        "bundle_dir": str(BUNDLE_DIR),
        "previous_requirements": str(previous_requirements) if previous_requirements else None,
        "model": {
            "provider": provider,
            "model": os.environ.get("OCTOS_MODEL") or os.environ.get("MODEL", ""),
            "base_url": base_url,
            "api_key_env": "OPENAI_API_KEY",
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    return spec


def kernel_env() -> dict:
    env = os.environ.copy()
    env.setdefault("OCTOS_DANGER_FULL_ACCESS", "1")  # the container is the sandbox
    env.setdefault("npm_config_registry", "https://registry.npmmirror.com")
    env.setdefault("NPM_CONFIG_REGISTRY", "https://registry.npmmirror.com")
    return env


def run_kernel(octos_bin: str, spec_path: Path, policy_path: Path, translator: Translator, log, env: dict) -> int:
    cmd = [octos_bin, "arc", "run", "--spec", str(spec_path), "--policy", str(policy_path)]
    from llm_proxy import configured_model_routes
    routes = configured_model_routes(env)
    if routes:
        # Explicit option makes unsupported older kernels fail instead of ignoring routes.
        cmd.extend(["--model-routes-json", routes])
    if os.environ.get("OCTOS_ARC_DRYRUN") == "1":
        cmd.append("--dry-run")
    log(f"[engine] {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=None, text=True, errors="replace",
                            bufsize=1, env=env, start_new_session=True)
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            event = parse_event(line)
            if event is None:
                log(line)
                continue
            if event.get("event") == "log":
                continue  # already printed as a plain line by the kernel
            try:
                translator.handle(event)
            except Exception as exc:  # noqa: BLE001 - translation must never kill the run
                log(f"[engine] event {event.get('event')} not translated: {exc}")
        return proc.wait()
    except BaseException:
        # An interrupted or broken stream must not leave a paid kernel and its
        # child processes running after the adapter records a failed run.
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            proc.wait()
        raise
    finally:
        try:
            proc.stdout.close()
        except OSError:
            pass


def main(args) -> int:
    import main as legacy  # the Python adapter: reused for platform plumbing only

    log = log_factory()
    output_dir = None
    try:
        from arcbench_agent_runtime import AgentRuntime
        req_src = Path(args.requirement_path).resolve()
        if args.output_dir:
            output_dir = Path(args.output_dir).resolve()
        elif os.environ.get("ARCBENCH_TEMPLATE_DIR"):
            output_dir = Path(os.environ["ARCBENCH_TEMPLATE_DIR"]).resolve()
        else:
            output_dir = Path.cwd() / "workspace" / f"run-{time.strftime('%Y%m%d-%H%M%S')}"
        output_dir.mkdir(parents=True, exist_ok=True)
        if os.environ.get("ARCBENCH_TEMPLATE_DIR"):
            req_dir = req_src
        else:
            req_dir = output_dir / "requirements"
            if req_dir.exists():
                shutil.rmtree(req_dir)
            shutil.copytree(req_src, req_dir)
        runtime = AgentRuntime.from_env(project_dir=str(output_dir))
        runtime.events.mark_run_started("octos bundle started (rust engine)")
    except Exception as exc:  # noqa: BLE001 - kernel setup needs a terminal verdict too
        log(f"[engine] setup failed: {type(exc).__name__}")
        if output_dir is not None:
            legacy.write_minimal_terminal_state(output_dir, "failed", f"rust setup: {type(exc).__name__}")
        return 1

    translator = Translator(runtime, log)
    completed = False
    interrupted = False
    completion_message = "completed"
    failure_reason = "rust engine did not complete"
    def terminate(_signum, _frame):
        raise KeyboardInterrupt
    try:
        old_term_handler = signal.signal(signal.SIGTERM, terminate)
    except Exception as exc:  # noqa: BLE001 - cannot safely supervise the child
        log(f"[engine] signal setup failed: {type(exc).__name__}")
        legacy.write_minimal_terminal_state(output_dir, "failed", f"rust signal setup: {type(exc).__name__}")
        return 1
    try:
        # Evolution: the template's committed requirement table is what the kernel
        # compares fingerprints against; store_requirement_tree() below overwrites
        # it with the new tree, so keep a copy first (main.py reads it in the same
        # order, before storing).
        previous_path = snapshot_previous_requirements(output_dir)
        tree = legacy.load_requirement_tree(req_dir)
        runtime.traceability.store_requirement_tree(tree)
        tests_dir = legacy.locate_acceptance_tests(tree, BUNDLE_DIR)
        octos_bin = legacy.find_octos()
        from embedded_suites import materialize, prefer_embedded
        suite_name = getattr(args, 'test_suite', None) or os.environ.get('OCTOS_ARC_TEST_SUITE')
        if suite_name or not tests_dir or prefer_embedded(args):
            embedded = materialize(octos_bin, tree, output_dir, suite_name, log,
                                   requirements_path=req_dir / 'requirements.yaml')
            if embedded:
                tests_dir, _manifest = embedded
        runtime.git.ensure_repo()
        spec_path = output_dir / ".arc" / "runner-spec.json"
        write_runner_spec(spec_path, req_dir=req_dir, output_dir=output_dir, web_port=args.web_port, tests_dir=tests_dir,
                          previous_requirements=previous_path)
        policy_path = Path(os.environ.get("OCTOS_ARC_POLICY") or (BUNDLE_DIR / "arc-policy.toml"))
        log(f"[octos] binary {octos_bin}")
        env = kernel_env()
        env["PORT"] = str(int(os.environ.get("OCTOS_SMOKE_PORT", "3100")))
        rc = run_kernel(octos_bin, spec_path, policy_path, translator, log, env)
        log(f"[engine] octos arc run exited {rc}")
        runtime.git.commit("chore: traceability and acceptance state")
        final = translator.final or {}
        if rc == 0 and final.get("event") == "run_completed":
            completion_message = final.get("message") or "completed"
            completed = True
        else:
            failure_reason = (f"octos arc run exited {rc}; final event {final.get('event') or 'missing'}: "
                              f"{final.get('message') or 'no message'}")
            runtime.events.mark_run_failed(failure_reason[:1000])
    except KeyboardInterrupt:
        interrupted = True
        failure_reason = "rust engine interrupted by user"
        try:
            runtime.events.mark_run_failed(failure_reason)
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001 - the platform judges by events, not exit code
        log(f"[engine] aborted: {exc!r}")
        failure_reason = f"rust engine exception: {type(exc).__name__}"
        try:
            runtime.events.mark_run_failed(str(exc)[:1000])
        except Exception:  # noqa: BLE001 - terminal file remains the fallback
            pass
    try:
        legacy._reap_stray_processes("postflight", output_dir)
        legacy._postflight_structure_check(output_dir)
        legacy._free_web_port(args.web_port, output_dir)
    except KeyboardInterrupt:
        interrupted = True
        completed = False
        failure_reason = "rust engine interrupted during postflight"
        try:
            runtime.events.mark_run_failed(failure_reason)
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001 - postflight cannot erase the verdict
        log(f"[engine] postflight failed: {type(exc).__name__}")
        failure_reason = f"rust postflight: {type(exc).__name__}"
        completed = False
        try:
            runtime.events.mark_run_failed(failure_reason)
        except Exception:  # noqa: BLE001
            pass
    if completed:
        try:
            runtime.events.mark_run_completed(completion_message)
        except Exception as exc:  # noqa: BLE001
            completed = False
            failure_reason = f"rust completion event: {type(exc).__name__}"
    legacy.write_minimal_terminal_state(
        output_dir, "completed" if completed else "interrupted_by_user" if interrupted else "failed",
        "rust engine completed" if completed else failure_reason)
    artifacts_dir = os.environ.get("ARCBENCH_ARTIFACTS_DIR")
    if artifacts_dir and completed:
        try:
            Path(artifacts_dir).mkdir(parents=True, exist_ok=True)
            (Path(artifacts_dir) / "preview-ready.json").write_text(
                json.dumps({"ready": True, "reason": "octos bundle completed"}) + "\n", encoding="utf-8")
        except OSError:
            pass
    try:
        signal.signal(signal.SIGTERM, old_term_handler)
    except Exception as exc:  # noqa: BLE001 - terminal verdict is already durable
        log(f"[engine] signal restoration failed: {type(exc).__name__}")
    return 0 if completed else 130 if interrupted else 1
