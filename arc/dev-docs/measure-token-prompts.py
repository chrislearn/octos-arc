"""Offline character/prefix comparison against an explicit Git baseline.

No provider calls. Source fixtures deliberately stay unchanged between nodes;
the measurements cannot establish real cached tokens, prices or pass rates.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types

ARC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ARC))
import main as current


def load_baseline(ref):
    code = subprocess.run(["git", "show", f"{ref}:arc/main.py"], cwd=ARC.parent,
                          check=True, capture_output=True, text=True).stdout
    module = types.ModuleType("arc_prompt_baseline")
    module.__file__ = str(ARC / "main.py")
    exec(compile(code, module.__file__, "exec"), module.__dict__)
    return module


def flow(module, root, task):
    return module.Flow(argparse.Namespace(web_port=3000), root, ARC / "tasks" / task)


def legacy_codegen(module, f, node, spec):
    small = f.codegen_reasoning(len(spec)) == "none"
    prompt = module.CODEGEN_PROMPT.format(node_id=node["id"], description=node["description"],
        spec=spec, port=f.web_port, ports=f.codegen_ports_clause(),
        size_rule=module.CODEGEN_SIZE_SMALL if small else module.CODEGEN_SIZE_FULL)
    return (prompt.replace("Files:", "Existing app below; keep everything that works and output "
                          "every changed file complete. Files:", 1)
            + module.relevant_sources(f.output_dir, spec, max(8000, f.codegen_context_chars() - len(spec))))


def repair(module, f, node_id, failures):
    return module.REPAIR_PROMPT.format(node_id=node_id, passed=1, total=2, failures=failures,
        test_location="read-only tests", sources=f.repair_requirements(), corrections="", slow="",
        smoke=f.smoke_port, port=f.web_port)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", required=True)
    args = parser.parse_args()
    baseline = load_baseline(args.baseline_ref)
    report = {"baseline": args.baseline_ref, "unit": "characters; not tokens", "suite": []}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        current.write_codegen_manifests(root)
        (root / "frontend/src").mkdir(parents=True)
        (root / "backend/server.js").write_text("// stable entry\n" + "e" * 600)
        (root / "frontend/src/index.html").write_text("<h1>Notes</h1>" + "p" * 600)
        (root / "frontend/src/settings.html").write_text("<h1>Settings</h1>" + "s" * 600)
        old = flow(baseline, root, "smoke--counter")
        new = flow(current, root, "smoke--counter")
        nodes = [{"id": "REQ-1", "description": "Notes"}, {"id": "REQ-2", "description": "Settings"}]
        specs = ["notes", "settings"]
        old_prompts = [legacy_codegen(baseline, old, n, s) for n, s in zip(nodes, specs)]
        new_prompts = [new.codegen_implement_prompt(n, s) for n, s in zip(nodes, specs)]
        report["codegen_unchanged_source_fixture"] = {
            "old_common_prefix": len(os.path.commonprefix(old_prompts)),
            "new_common_prefix": len(os.path.commonprefix(new_prompts)),
            "old_message_chars": [len(p + "\n" + baseline.FORMAT_INSTRUCTIONS) for p in old_prompts],
            "new_message_chars": [len(p + "\n" + current.FORMAT_INSTRUCTIONS) for p in new_prompts]}
        # Keep identical sources and cross the default 5,000-char reasoning
        # threshold. The size rule must not precede the quoted source blocks.
        new.codegen_reasoning = lambda n: "none" if n < 5000 else None
        cross_specs = ["a" * 4999, "b" * 5000]
        old_cross = [legacy_codegen(baseline, old, n, s) for n, s in zip(nodes, cross_specs)]
        new_cross = [new.codegen_implement_prompt(n, s) for n, s in zip(nodes, cross_specs)]
        # Reconstruct the immediately preceding working layout, changing only
        # placement of size_rule. All fixture files fit under either layout.
        def preceding_layout(node, spec):
            rules = current.CODEGEN_RULES.replace(
                "Return only requested file blocks.\n", "Return only requested file blocks. {size_rule}\n")
            rules = rules.format(port=new.web_port, ports=new.codegen_ports_clause(),
                size_rule=current.CODEGEN_SIZE_SMALL if len(spec) < 5000 else current.CODEGEN_SIZE_FULL)
            rules = rules.replace("Files:", "Existing app below; keep everything that works and output "
                                  "every changed file complete. Files:", 1)
            task = current.CODEGEN_TASK.replace("{size_rule}\n", "").format(
                node_id=node["id"], description=node["description"], spec=spec)
            sources = current.relevant_sources(root, spec, 80000, stable_order=True)
            return rules + sources + "\n" + task
        preceding_cross = [preceding_layout(n, s) for n, s in zip(nodes, cross_specs)]
        report["codegen_cross_size_threshold_fixture"] = {
            "preceding_working_layout_common_prefix": len(os.path.commonprefix(preceding_cross)),
            "old_common_prefix": len(os.path.commonprefix(old_cross)),
            "new_common_prefix": len(os.path.commonprefix(new_cross)),
            "source_remains_in_common_prefix": "--- frontend/src/settings.html ---" in os.path.commonprefix(new_cross)}
        for task in sorted((ARC / "tasks").glob("arc-bench-web--*")):
            old = flow(baseline, root, task.name)
            new = flow(current, root, task.name)
            nodes = current.topo_order(current.load_requirement_tree(task))
            old.requirement_nodes = new.requirement_nodes = {str(n["id"]): n for n in nodes}
            old_prompts = [repair(baseline, old, n["id"], "failure " + n["id"]) for n in nodes[:2]]
            new_prompts = [repair(current, new, n["id"], "failure " + n["id"]) for n in nodes[:2]]
            report["suite"].append({"task": task.name, "nodes": len(nodes),
                "requirements_unchanged": old.repair_requirements() == new.repair_requirements(),
                "old_common_prefix": len(os.path.commonprefix(old_prompts)),
                "new_common_prefix": len(os.path.commonprefix(new_prompts))})
        old = flow(baseline, root, "smoke--counter")
        new = flow(current, root, "smoke--counter")
        for f in (old, new):
            f.tests_dir = ARC / "public-tests/smoke--counter"
            f.spec_map = {"REQ-1": ["REQ-1.spec.ts"]}
        node = current.topo_order(current.load_requirement_tree(new.req_dir))[0]
        old_text = "Requirement: " + json.dumps(node, ensure_ascii=False) + "\nPublic example:\n" + old.spec_bodies("REQ-1")
        new_text = "Requirement:\n" + current.describe_node(node) + "\nPublic example:\n" + new.spec_bodies("REQ-1")
        report["tiny_smoke_counter"] = {
            "old_prompt_chars": len(baseline.TINY_PROMPT.format(spec=old_text)),
            "new_prompt_chars": len(current.TINY_PROMPT.format(spec=new_text)),
            "all_described_constraints_retained": current.describe_node(node) in new_text}
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
