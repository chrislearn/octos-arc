"""Model-proposed scripts for scenarios the mechanical compiler cannot script.

The model proposes; the harness verifies. A proposal is a short list of
whitelisted operations (open/click/fill/check/press/expect_visible/
expect_absent). Every target and value must be a literal the requirement
itself quotes (“…”, "…" or `…`), a seeded value, or a suite fixture. A
proposal naming anything else, using an unknown operation, asserting nothing,
or reporting low confidence is dropped whole -- a partial sequence would fail
for our reasons, not the application's. The model therefore adds navigation
order and which literal is the assertion; it cannot invent controls or data.
"""
from __future__ import annotations

import json
import re
from typing import Iterable, Mapping

from scenario_tests import Fixtures, _ANY_LITERAL, _compile_scenario, _node_text, _sentences, _ts

OPS = {"open", "click", "fill", "check", "press", "expect_visible", "expect_absent"}
KEYS = {"Enter", "Escape", "Tab"}
MIN_CONFIDENCE = 0.6
MAX_STEPS = 14

SYSTEM = ("You convert product requirement scenarios into short browser check scripts. "
          "Reply with one JSON object only; no prose, no markdown.")

DSL = """Each script is {"title": <scenario title verbatim>, "signed_in": true|false, "confidence": 0..1,
 "steps": [ ... ], "skip": "<reason>" }.
Operations (use only these):
  {"op": "open", "target": L}            navigate to where L (a page, tab or menu entry name) is visible; click it if it is a control
  {"op": "click", "target": L}           click the control named L
  {"op": "fill", "target": L, "value": V} type V into the field labelled L
  {"op": "check", "target": L}           check the checkbox named L
  {"op": "press", "key": "Enter"}        press a key (Enter, Escape, Tab)
  {"op": "expect_visible", "target": L}  assert the text or control L is visible
  {"op": "expect_absent", "target": L}   assert the text L is not visible
L and V MUST be copied verbatim from the ALLOWED LITERALS list of that scenario (control names the
requirement quotes, seeded record names, or the fixture account/email/password). Never invent names.
If the scenario needs data or a starting state that the allowed literals cannot establish (a value the
user must make up, an existing record the requirement does not name, a second account), set "skip".
"signed_in": true means the script first signs in with the fixture account; do not add sign-in steps.
Prefer the shortest path that a real user of this product would take: open the seeded record, then
the tab or page the scenario names, then act. End with at least one expect_visible/expect_absent taken
from the THEN step (a quoted literal, a seeded name, or a status word the requirement names).
Set confidence below 0.6 when you are guessing."""


def ancestor_context(tree: Mapping | None) -> dict[str, str]:
    """{leaf id: descriptions of its folder ancestors} -- shared controls such
    as “Sign in” are usually named on the module, not on every leaf."""
    context: dict[str, str] = {}

    def walk(node: Mapping, trail: list[str]) -> None:
        if node.get("type") == "ATOMIC":
            context[str(node.get("id"))] = "\n".join(trail)
            return
        text = " ".join([str(node.get("name") or ""), str(node.get("description") or "")]).strip()
        for child in node.get("children") or []:
            if isinstance(child, Mapping):
                walk(child, trail + ([text] if text else []))

    if isinstance(tree, Mapping):
        walk(tree, [])
    return context


def allowed_literals(node: Mapping, fixtures: Fixtures, context: str = "") -> list[str]:
    """Every literal the requirement quotes, the scenario seeds, and fixtures."""
    text = _node_text(node) + "\n" + context
    values: list[str] = []
    for scenario in node.get("scenarios") or []:
        for step in scenario.get("steps") or []:
            text += "\n" + str(step.get("content") or "")
    for match in _ANY_LITERAL.finditer(text):
        values.append((match.group(1) or match.group(2) or match.group(3)).strip())
    for match in re.finditer(r"\b(?:displays?|shows?|marked(?:\s+as)?|status\s+(?:is|becomes|of)|becomes)\s+"
                             r"(?:the\s+)?([A-Z][a-z]{2,})\b", text):
        values.append(match.group(1))
    # "accessibly named Add comment", "a single editor labeled Comment with ..."
    for match in re.finditer(r"\b(?:accessibly\s+)?(?:named|labell?ed)\s+(?:exactly\s+)?([A-Z][\w-]*(?:\s+[\w-]+){0,4}?)"
                             r"(?=\s*(?:[,.;:()]|\s+(?:and|or|with|that|which|to|in|on|for|button|link|tab|menuitem)\b|$))",
                             text, re.M):
        values.append(match.group(1))
    values += [v for v in (fixtures.account, fixtures.email, fixtures.password) if v]
    return list(dict.fromkeys(v for v in values if v and len(v) <= 120))


def review_targets(leaves: Iterable[Mapping], fixtures: Fixtures, context: Mapping[str, str] | None = None) -> list[dict]:
    """Scenarios that got no mechanical script, with what a proposal may name."""
    targets: list[dict] = []
    for node in leaves:
        node_id = str(node.get("id"))
        node_text = _node_text(node)
        allowed = allowed_literals(node, fixtures, (context or {}).get(node_id, ""))
        for scenario in node.get("scenarios") or []:
            parsed = _compile_scenario(scenario, fixtures, node_text)
            actions = [a for a in parsed.actions if not a.startswith("await h.signIn(")]
            scripted = parsed.compiled and not parsed.generic and bool(actions) and (
                bool(parsed.assertions) or not parsed.failure_path)
            if scripted or parsed.generic:
                continue
            title = parsed.title if parsed.title.startswith(node_id) else f"{node_id}: {parsed.title}"
            steps = [f"{str(step.get('keyword') or '').upper()}: "
                     + " ".join(_sentences(step.get("content")))
                     for step in scenario.get("steps") or []]
            targets.append({"node_id": node_id, "title": title, "name": str(node.get("name") or ""),
                            "description": re.sub(r"\s+", " ", str(node.get("description") or ""))[:1400],
                            "steps": steps, "allowed": allowed, "seeds": parsed.seeds,
                            "signed_in": parsed.signed_in})
    return targets


def build_prompt(targets: list[dict], fixtures: Fixtures) -> str:
    parts = ["Write one check script per scenario below, as JSON: {\"scenarios\": [ ... ]}.\n" + DSL]
    parts.append(f"\nFixture account: `{fixtures.account}` / `{fixtures.password}` (email `{fixtures.email}`).")
    for target in targets:
        parts.append(f"\n### {target['title']}\nRequirement {target['node_id']} ({target['name']}): "
                     f"{target['description']}\n" + "\n".join(target["steps"]) +
                     "\nALLOWED LITERALS: " + json.dumps(target["allowed"], ensure_ascii=False))
    return "\n".join(parts)


def parse_reply(text: str) -> list[dict] | None:
    text = str(text or "")
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidates = [fenced.group(1)] if fenced else []
    start = text.find("{")
    if start >= 0:
        candidates.append(text[start:text.rfind("}") + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        scenarios = data.get("scenarios") if isinstance(data, dict) else None
        if isinstance(scenarios, list):
            return [item for item in scenarios if isinstance(item, dict)]
    return None


def _emit(step: dict) -> str | None:
    op, target = step.get("op"), step.get("target")
    if op == "open":
        return f"await h.openNamed(page, {_ts(target)});"
    if op == "click":
        return f"await h.clickNamed(page, {_ts(target)});"
    if op == "fill":
        return f"await h.fillField(page, {_ts(target)}, {_ts(str(step.get('value')))});"
    if op == "check":
        return f"await h.checkNamed(page, {_ts(target)});"
    if op == "press":
        return f"await h.pressKey(page, {_ts(str(step.get('key')))});"
    if op == "expect_visible":
        return f"await h.expectTextsVisible(page, [{_ts(target)}]);"
    if op == "expect_absent":
        return f"await h.expectAbsent(page, {_ts(target)});"
    return None


def proposal_problems(proposal: Mapping, target: Mapping, fixtures: Fixtures) -> list[str]:
    """Every rule the proposal breaks, worded so the model can fix it."""
    problems: list[str] = []
    if proposal.get("skip"):
        return [f"skipped by the model: {proposal.get('skip')}"]
    try:
        confidence = float(proposal.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < MIN_CONFIDENCE:
        problems.append(f"confidence {confidence:.2f} is below {MIN_CONFIDENCE}")
    steps = proposal.get("steps")
    if not isinstance(steps, list) or not steps:
        return problems + ["no steps"]
    if len(steps) > MAX_STEPS:
        problems.append(f"{len(steps)} steps; at most {MAX_STEPS}")
    allowed = set(target["allowed"]) | set(target.get("seeds") or [])
    asserted = False
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict) or step.get("op") not in OPS:
            problems.append(f"step {index}: unknown op {json.dumps(step.get('op') if isinstance(step, dict) else step)}; "
                            f"use one of {sorted(OPS)}")
            continue
        op = step["op"]
        if op == "press":
            if step.get("key") not in KEYS:
                problems.append(f"step {index}: key {json.dumps(step.get('key'))} is not one of {sorted(KEYS)}")
            continue
        value = step.get("target")
        if not isinstance(value, str) or value.strip() not in allowed:
            problems.append(f"step {index}: {op} target {json.dumps(value, ensure_ascii=False)} is not an allowed literal")
        if op == "fill":
            typed = step.get("value")
            if not isinstance(typed, str) or typed.strip() not in allowed:
                problems.append(f"step {index}: fill value {json.dumps(typed, ensure_ascii=False)} is not an allowed literal")
        asserted = asserted or op.startswith("expect_")
    if not asserted:
        problems.append("no expect_visible/expect_absent step: the script must assert something from the THEN step")
    if proposal.get("signed_in") and not (fixtures.account and fixtures.password):
        problems.append("signed_in requested but the suite has no fixture account")
    return problems


def validate_proposal(proposal: Mapping, target: Mapping, fixtures: Fixtures) -> str | None:
    """The proposal's test source, or None with nothing applied when any rule fails."""
    if proposal_problems(proposal, target, fixtures):
        return None
    lines: list[str] = []
    for step in proposal["steps"]:
        step = dict(step)
        if step["op"] != "press":
            step["target"] = str(step["target"]).strip()
            if step["op"] == "fill":
                step["value"] = str(step["value"]).strip()
        code = _emit(step)
        if code is None:
            return None
        lines.append("  " + code)
    start = ["  await h.openHome(page);"]
    if proposal.get("signed_in"):
        start.append(f"  await h.signIn(page, {_ts(fixtures.account)}, {_ts(fixtures.password)});")
    title = f"{target['title']} [model]"
    return (f"test({_ts(title)}, async ({{ page }}) => {{\n  test.setTimeout(120_000);\n"
            + "\n".join(start + lines) + "\n}});")


def compile_reply(text: str, targets: list[dict], fixtures: Fixtures, with_retryable: bool = False):
    """{node_id: [test source, ...]} for accepted proposals, plus a reason per drop.

    With `with_retryable`, also return the rejected proposals the model can fix
    (rule violations with their reasons); its own "skip" is final.
    """
    by_title = {target["title"]: target for target in targets}
    scripts: dict[str, list[str]] = {}
    dropped: list[str] = []
    retryable: list[dict] = []
    seen: set[str] = set()
    for proposal in parse_reply(text) or []:
        title = str(proposal.get("title") or "").strip()
        target = by_title.get(title)
        if target is None:
            dropped.append(f"{title or '(untitled)'}: not a requested scenario")
            continue
        if title in seen:
            dropped.append(f"{title}: duplicate proposal")
            continue
        problems = proposal_problems(proposal, target, fixtures)
        if problems:
            dropped.append(f"{title}: " + "; ".join(problems))
            if not proposal.get("skip"):
                retryable.append({"title": title, "reasons": problems})
            continue
        source = validate_proposal(proposal, target, fixtures)
        if source is None:
            dropped.append(f"{title}: could not be emitted")
            continue
        seen.add(title)
        scripts.setdefault(target["node_id"], []).append(source)
    return (scripts, dropped, retryable) if with_retryable else (scripts, dropped)


def retry_prompt(rejected: list[dict], targets: list[dict], fixtures: Fixtures) -> str:
    """One correction round: the same scenarios, each with why it was rejected."""
    by_title = {target["title"]: target for target in targets}
    chosen = [by_title[item["title"]] for item in rejected if item["title"] in by_title]
    prompt = build_prompt(chosen, fixtures)
    feedback = "\n".join(f"- {item['title']}: " + "; ".join(item["reasons"]) for item in rejected
                         if item["title"] in by_title)
    return (prompt + "\n\nYour previous scripts for these scenarios were REJECTED for the reasons below. "
            "Fix exactly these problems (copy every target and value verbatim from ALLOWED LITERALS, use only the "
            "listed operations, end with an expect step) or set \"skip\" with a reason:\n" + feedback)


def append_tests(spec_source: str, tests: list[str], node_id: str) -> str:
    """Add model-proposed tests to a leaf's derived spec (creating the header when new)."""
    if not spec_source:
        spec_source = (f"// requirement: {node_id}\n// Derived mechanically from requirements.yaml; not an official test.\n"
                       "import { test } from '@playwright/test';\nimport * as h from './helpers';\n\n")
    return spec_source.rstrip("\n") + "\n\n" + "\n\n".join(tests) + "\n"
