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

import hashlib
import json
import re
from typing import Iterable, Mapping

from scenario_tests import Fixtures, _ANY_LITERAL, _compile_scenario, _node_text, _sentences, _ts

OPS = {"open", "click", "fill", "check", "press", "expect_visible", "expect_absent",
       "cell_click", "cell_type", "expect_cell", "expect_role"}
CELL = re.compile(r"^[A-Z]{1,3}[0-9]{1,4}$")
NUMBER = re.compile(r"^-?\d+(?:\.\d+)?%?$")
ROLES = {"grid", "gridcell", "tab", "tablist", "tabpanel", "dialog", "menu", "menuitem", "button", "link", "textbox",
         "combobox", "listbox", "option", "table", "row", "columnheader", "rowheader", "heading", "region",
         "navigation", "alert", "status", "checkbox", "radio", "switch", "toolbar"}
# Values a scenario must make up (a new account, a comment body): the harness
# expands them per scenario, so a script never reuses the seeded account for a
# record it creates (registering `alice-dev` again fails once the seed exists).
PLACEHOLDERS = {
    "$NEW_USERNAME": "a new, unused username (lowercase letters, digits, hyphens)",
    "$NEW_EMAIL": "a new, unused email address",
    "$NEW_PASSWORD": "a new compliant password (12+ chars); reuse it for the confirmation field",
    "$TEXT": "a short free-form text (comment body, title, description)",
}


def expand_placeholder(value: str, scope: str) -> str:
    """Deterministic per scenario: the same placeholder expands identically
    within one script, differently across scenarios (parallel tests)."""
    slug = hashlib.sha1(scope.encode("utf-8")).hexdigest()[:6]
    return {
        "$NEW_USERNAME": f"user-{slug}",
        "$NEW_EMAIL": f"user-{slug}@example.test",
        "$NEW_PASSWORD": f"Derived-pass-{slug}!",
        "$TEXT": f"Derived text {slug}",
    }.get(value, value)
KEYS = {"Enter", "Escape", "Tab", "Delete", "Backspace", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
        "Home", "End", "PageUp", "PageDown", "Shift+Enter", "Shift+Tab", "Control+Enter", "Control+C", "Control+V",
        "Control+X", "Control+Z", "Control+Y", "Control+A"}
MIN_CONFIDENCE = 0.6
MAX_STEPS = 14

SYSTEM = ("You convert product requirement scenarios into short browser check scripts. "
          "Reply with one JSON object only; no prose, no markdown.")

DSL = """Each script is {"id": <the [S..] id shown before the scenario>, "title": <scenario title verbatim>,
 "signed_in": true|false, "confidence": 0..1, "steps": [ ... ], "skip": "<reason>" }. The "id" is mandatory.
Operations (use only these):
  {"op": "open", "target": L}            navigate to where L (a page, tab or menu entry name) is visible; click it if it is a control
  {"op": "click", "target": L}           click the control named L
  {"op": "fill", "target": L, "value": V} type V into the field labelled L
  {"op": "check", "target": L}           check the checkbox named L
  {"op": "press", "key": "Enter"}        press a key: Enter, Escape, Tab, Delete, Backspace, Arrow keys,
                                         Home, End, Shift+Enter, Shift+Tab, Control+C/V/X/Z/Y/A, Control+Enter
  {"op": "expect_visible", "target": L}  assert the text or control L is visible
  {"op": "expect_absent", "target": L}   assert the text L is not visible
  {"op": "cell_click", "target": "A1"}   select a spreadsheet cell by its coordinate (ARIA gridcell name)
  {"op": "cell_type", "target": "A1", "value": V}  select the cell and type V (a seeded value, a number or a
                                         formula quoted by the requirement); commit with {"op": "press", "key": "Enter"}
  {"op": "expect_cell", "target": "C1", "value": V}  assert the cell shows V (seeded value or number)
  {"op": "expect_role", "role": R, "target": L}  assert an element with ARIA role R and accessible name L
                                         (roles: grid, gridcell, tab, dialog, menu, menuitem, button, link, ...)
A scenario that says "the requested workflow" (or "follows the visible controls") means: perform the
operation that the Requirement text of that scenario describes, on the seeded record, with the concrete
values the scenario lists; then assert the observable result the Requirement text promises. When the
scenario does not say which cell, row or column to use, choose one from the seeds yourself (the cell named
in the seed, the row holding a seeded value, the next empty cell): a concrete reasonable choice is
expected, "not specified" is not a reason to skip.
Cell coordinates (A1, B2, C10 ...) are ALWAYS allowed as targets of cell_click/cell_type/expect_cell and
expect_role, whether or not they appear in ALLOWED LITERALS. Numbers are always allowed as values.
Copy, cut, paste, undo and redo are done with press Control+C / Control+X / Control+V / Control+Z /
Control+Y on the selected cell (no clipboard setup is needed). File upload/download cannot be scripted:
skip only those scenarios.
L and V MUST be copied verbatim from the ALLOWED LITERALS list of that scenario (control names the
requirement quotes, seeded record names, or the fixture account/email/password). Never invent names.
Values the user must make up are written as placeholders, allowed ONLY as fill values and as
expect_visible/expect_absent targets: $NEW_USERNAME, $NEW_EMAIL, $NEW_PASSWORD (also for the
confirmation field), $TEXT (comment body, title, description). Never register or create records with
the fixture account; use the placeholders for anything new.
If the scenario needs a starting state that the allowed literals cannot establish (an existing record
the requirement does not name, a second account with credentials), set "skip".
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


def folder_text(tree: Mapping | None) -> str:
    """Every folder description of the tree: module-level contracts ("the grid
    uses the ARIA grid role ...") hold for all leaves, not only the folder's own."""
    parts: list[str] = []

    def walk(node: Mapping) -> None:
        if node.get("type") != "ATOMIC":
            text = str(node.get("description") or "").strip()
            if text:
                parts.append(text)
            for child in node.get("children") or []:
                if isinstance(child, Mapping):
                    walk(child)

    if isinstance(tree, Mapping):
        walk(tree)
    return "\n".join(parts)


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
    seen_steps: set[tuple] = set()
    for node in leaves:
        node_id = str(node.get("id"))
        node_text = _node_text(node)
        allowed = allowed_literals(node, fixtures, (context or {}).get(node_id, ""))
        for scenario in node.get("scenarios") or []:
            # Templated tasks repeat the same scenario text several times under
            # one leaf; one script serves all copies.
            signature = (node_id,) + tuple(" ".join(_sentences(step.get("content")))
                                          for step in scenario.get("steps") or [])
            if signature in seen_steps:
                continue
            seen_steps.add(signature)
            parsed = _compile_scenario(scenario, fixtures, node_text)
            actions = [a for a in parsed.actions if not a.startswith("await h.signIn(")]
            scripted = parsed.compiled and not parsed.generic and bool(actions) and (
                bool(parsed.assertions) or not parsed.failure_path)
            when_text = " ".join(str(step.get("content") or "") for step in scenario.get("steps") or []
                                 if str(step.get("keyword") or "").upper() == "WHEN")
            # "follows the visible controls for the X workflow" carries nothing a
            # proposal could act on; "the requested workflow" (templated tasks)
            # does: the operation is in the requirement text.
            if scripted or (parsed.generic and re.search(r"follows?\s+the\s+visible\s+controls", when_text, re.I)):
                continue
            title = parsed.title if parsed.title.startswith(node_id) else f"{node_id}: {parsed.title}"
            steps = [f"{str(step.get('keyword') or '').upper()}: "
                     + " ".join(_sentences(step.get("content")))
                     for step in scenario.get("steps") or []]
            targets.append({"id": f"S{len(targets) + 1}", "node_id": node_id, "title": title,
                            "name": str(node.get("name") or ""),
                            "description": re.sub(r"\s+", " ", str(node.get("description") or ""))[:2600],
                            "steps": steps, "allowed": allowed, "seeds": parsed.seeds,
                            "signed_in": parsed.signed_in})
    return targets


def build_prompt(targets: list[dict], fixtures: Fixtures) -> str:
    parts = ["Write one check script per scenario below, as JSON: {\"scenarios\": [ ... ]}.\n" + DSL]
    parts.append(f"\nFixture account: `{fixtures.account}` / `{fixtures.password}` (email `{fixtures.email}`).")
    for target in targets:
        parts.append(f"\n### [{target['id']}] {target['title']}\nRequirement {target['node_id']} ({target['name']}): "
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
    if op == "cell_click":
        return f"await h.clickCell(page, {_ts(target)});"
    if op == "cell_type":
        return f"await h.typeInCell(page, {_ts(target)}, {_ts(str(step.get('value')))});"
    if op == "expect_cell":
        return f"await h.expectCell(page, {_ts(target)}, {_ts(str(step.get('value')))});"
    if op == "expect_role":
        return f"await h.expectRole(page, {_ts(str(step.get('role')))}, {_ts(target)});"
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
        if op in {"cell_click", "cell_type", "expect_cell"}:
            if not isinstance(value, str) or not CELL.match(value.strip()):
                problems.append(f"step {index}: {op} target {json.dumps(value, ensure_ascii=False)} is not a cell "
                                f"coordinate such as A1")
            if op != "cell_click":
                typed = step.get("value")
                if not isinstance(typed, str) or not (typed.strip() in allowed or typed.strip() in PLACEHOLDERS
                                                      or NUMBER.match(typed.strip())):
                    problems.append(f"step {index}: {op} value {json.dumps(typed, ensure_ascii=False)} is not a seeded "
                                    f"value, number, placeholder or literal the requirement quotes")
            # v9.2.2 (cce3f5ad4f21): expect_cell did not count as an assertion, so
            # every cell-only script was rejected for "no expect step".
            asserted = asserted or op == "expect_cell"
            continue
        if op == "expect_role":
            role = step.get("role")
            if role not in ROLES:
                problems.append(f"step {index}: expect_role role {json.dumps(role)} is not one of {sorted(ROLES)}")
            if not isinstance(value, str) or not (value.strip() in allowed or CELL.match(value.strip())):
                problems.append(f"step {index}: expect_role target {json.dumps(value, ensure_ascii=False)} is not an "
                                f"allowed literal or cell coordinate")
            asserted = True
            continue
        placeholder_ok = op.startswith("expect_")
        if not isinstance(value, str) or not (value.strip() in allowed or (placeholder_ok and value.strip() in PLACEHOLDERS)):
            problems.append(f"step {index}: {op} target {json.dumps(value, ensure_ascii=False)} is not an allowed literal"
                            + ("" if placeholder_ok else " (placeholders are not control names)"))
        if op == "fill":
            typed = step.get("value")
            if not isinstance(typed, str) or not (typed.strip() in allowed or typed.strip() in PLACEHOLDERS):
                problems.append(f"step {index}: fill value {json.dumps(typed, ensure_ascii=False)} is not an allowed "
                                f"literal or placeholder ({', '.join(PLACEHOLDERS)})")
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
    scope = str(target["title"])
    for step in proposal["steps"]:
        step = dict(step)
        if step["op"] != "press":
            step["target"] = expand_placeholder(str(step["target"]).strip(), scope)
            if step["op"] in {"fill", "cell_type", "expect_cell"}:
                step["value"] = expand_placeholder(str(step["value"]).strip(), scope)
        code = _emit(step)
        if code is None:
            return None
        lines.append("  " + code)
    start = ["  await h.openHome(page);"]
    if proposal.get("signed_in"):
        start.append(f"  await h.signIn(page, {_ts(fixtures.account)}, {_ts(fixtures.password)});")
    title = f"{target['title']} [model]"
    return (f"test({_ts(title)}, async ({{ page }}) => {{\n  test.setTimeout(120_000);\n"
            + "\n".join(start + lines) + "\n});")


def compile_reply(text: str, targets: list[dict], fixtures: Fixtures, with_retryable: bool = False):
    """{node_id: [test source, ...]} for accepted proposals, plus a reason per drop.

    With `with_retryable`, also return the rejected proposals the model can fix
    (rule violations with their reasons); its own "skip" is final.
    """
    by_id = {target.get("id"): target for target in targets if target.get("id")}
    by_title = {target["title"]: target for target in targets}
    scripts: dict[str, list[str]] = {}
    dropped: list[str] = []
    retryable: list[dict] = []
    seen: set[str] = set()
    for proposal in parse_reply(text) or []:
        title = str(proposal.get("title") or "").strip()
        target = by_id.get(str(proposal.get("id") or "").strip()) or by_title.get(title)
        if target is None:
            dropped.append(f"{title or '(untitled)'}: not a requested scenario")
            continue
        key = target.get("id") or target["title"]
        if key in seen:
            dropped.append(f"{target['title']}: duplicate proposal")
            continue
        problems = proposal_problems(proposal, target, fixtures)
        if problems:
            dropped.append(f"{target['title']}: " + "; ".join(problems))
            if not proposal.get("skip"):
                retryable.append({"id": target.get("id"), "title": target["title"], "reasons": problems})
            continue
        source = validate_proposal(proposal, target, fixtures)
        if source is None:
            dropped.append(f"{target['title']}: could not be emitted")
            continue
        seen.add(key)
        scripts.setdefault(target["node_id"], []).append(source)
    return (scripts, dropped, retryable) if with_retryable else (scripts, dropped)


def retry_prompt(rejected: list[dict], targets: list[dict], fixtures: Fixtures) -> str:
    """One correction round: the same scenarios, each with why it was rejected."""
    by_key = {target.get("id") or target["title"]: target for target in targets}
    by_key.update({target["title"]: target for target in targets})
    chosen: list[dict] = []
    for item in rejected:
        target = by_key.get(item.get("id")) or by_key.get(item["title"])
        if target is not None and target not in chosen:
            chosen.append(target)
    prompt = build_prompt(chosen, fixtures)
    feedback = "\n".join(f"- [{target.get('id')}] {target['title']}: " + "; ".join(item["reasons"])
                         for item in rejected
                         for target in [by_key.get(item.get("id")) or by_key.get(item["title"])] if target is not None)
    return (prompt + "\n\nYour previous scripts for these scenarios were REJECTED for the reasons below. "
            "Fix exactly these problems (copy every target and value verbatim from ALLOWED LITERALS, use only the "
            "listed operations, end with an expect step) or set \"skip\" with a reason:\n" + feedback)


def append_tests(spec_source: str, tests: list[str], node_id: str) -> str:
    """Add model-proposed tests to a leaf's derived spec (creating the header when new)."""
    if not spec_source:
        spec_source = (f"// requirement: {node_id}\n// Derived mechanically from requirements.yaml; not an official test.\n"
                       "import { test } from '@playwright/test';\nimport * as h from './helpers';\n\n")
    return spec_source.rstrip("\n") + "\n\n" + "\n\n".join(tests) + "\n"
