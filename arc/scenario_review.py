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

from scenario_tests import (Fixtures, _ANY_LITERAL, _compile_scenario, _descriptive, _node_text, _sentences, _ts,
                            literal_prefix)

OPS = {"open", "click", "fill", "check", "press", "set_clipboard", "expect_visible", "expect_absent",
       "cell_click", "cell_type", "expect_cell", "expect_role", "upload", "expect_download",
       "expect_clipboard"}
# "open the home page" needs no literal: it is the application root.
HOME_TARGET = re.compile(r"^(?:the\s+)?(?:application\s+|app\s+|workbook\s+)?home(?:\s*page)?$", re.I)
# Template wording of the task itself ("the requested workflow") is never a literal.
TEMPLATE_TEXT = re.compile(r"the\s+requested\s+workflow|follows?\s+the\s+visible\s+controls", re.I)
CELL = re.compile(r"^[A-Z]{1,3}[0-9]{1,4}$")
RANGE = re.compile(r"^[A-Z]{1,3}[0-9]{1,4}:[A-Z]{1,3}[0-9]{1,4}$")
# A typed formula or a spreadsheet error token is structure the model may
# choose freely: a wrong one fails visibly, it cannot mislead an assertion.
FORMULA = re.compile(r"^=[A-Za-z0-9_+\-*/^().,:$%<>=&\" ]{1,60}$")
ERROR_TOKEN = re.compile(r"^#[A-Z0-9/!?]{2,12}$")
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
    "$NEW_NAME": "a new, unused record name (repository, team, workbook, worksheet, branch, label): lowercase "
                 "letters, digits, hyphens; assert it afterwards to prove the record was created",
    "$TEXT": "a short free-form text (comment body, title, description)",
    "$BLANK": "whitespace only (an invalid empty input for a required field)",
    "$CSV": "a CSV file of the seeded `label/value` rows in seed order, no header row -- after import A1 holds "
            "the first seeded label, B1 its value, A2 the second label ... (only as the value of an upload step)",
    "$CSV_NAME": "the name derived from the uploaded derived-import.csv file: derived-import "
                 "(assertion after upload only, not a new-record fill value)",
    "$TABLE": "a tab/newline-delimited two-dimensional table of the seeded rows, for an external paste test",
}


def seed_parts(value: str) -> list[str]:
    """A seeded row `East/1200` is shown as separate cells, never as one string
    (sheet review S13: `expect_visible "East/1200"` fails on a correct app)."""
    value = str(value)
    if "/" not in value or value.count("/") > 3 or "://" in value or value.startswith(("#", "=")):
        return [value]
    parts = [part.strip() for part in value.split("/") if len(part.strip()) >= 3]
    return parts or [value]


def seed_csv(seeds: list[str]) -> str:
    """A CSV the import scenarios can use: seeded `Label/Value` rows when the
    task names some, else a fixed two-column sample."""
    # No header row: the model is told A1 holds the first seeded label, so the
    # file must start with the rows themselves (v2 sheet-io review: A1=East).
    rows = [value.split("/") for value in seeds if value.count("/") == 1 and " " not in value.split("/")[1]]
    if len(rows) >= 2:
        return "\n".join(",".join(part.strip() for part in row) for row in rows)
    return "East,1200\nNorth,800"


def expand_placeholder(value: str, scope: str) -> str:
    """Deterministic per scenario: the same placeholder expands identically
    within one script, differently across scenarios (parallel tests)."""
    slug = hashlib.sha1(scope.encode("utf-8")).hexdigest()[:6]
    return {
        "$NEW_USERNAME": f"user-{slug}",
        "$NEW_EMAIL": f"user-{slug}@example.test",
        "$NEW_PASSWORD": f"Derived-pass-{slug}!",
        "$NEW_NAME": f"derived-{slug}",
        "$CSV_NAME": "derived-import",
        "$TEXT": f"Derived text {slug}",
        "$BLANK": "   ",
    }.get(value, value)
KEYS = {"Enter", "Escape", "Tab", "Delete", "Backspace", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
        "Home", "End", "PageUp", "PageDown", "Shift+Enter", "Shift+Tab", "Control+Enter", "Control+C", "Control+V",
        "Control+X", "Control+Z", "Control+Y", "Control+A"}
MIN_CONFIDENCE = 0.5
MAX_STEPS = 20

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
  {"op": "set_clipboard", "value": "$TABLE"}  put the seeded two-dimensional table on the browser clipboard
                                         before testing paste from an external source
  {"op": "expect_visible", "target": L}  assert the text or control L is visible
  {"op": "expect_absent", "target": L}   assert the text L is not visible
  {"op": "cell_click", "target": "A1"}   select a spreadsheet cell by its coordinate (ARIA gridcell name);
                                         "A1:B2" selects that range (click A1, shift-click B2)
  {"op": "cell_type", "target": "A1", "value": V}  select the cell and type V (a seeded value, a number or a
                                         formula quoted by the requirement); commit with {"op": "press", "key": "Enter"}
  {"op": "expect_cell", "target": "C1", "value": V}  assert the cell shows V (seeded value or number; "" = the
                                         cell is empty, e.g. after Escape cancels an edit or after Undo)
  {"op": "expect_role", "role": R, "target": L}  assert an element with ARIA role R and accessible name L
                                         (roles: grid, gridcell, tab, dialog, menu, menuitem, button, link, ...)
  {"op": "upload", "target": L, "value": "$CSV"}  choose a file in the file input named/labelled L; $CSV is a
                                         CSV of the seeded label/value rows, no header (A1 = first label)
  {"op": "expect_download", "target": L, "value": ".csv", "contains": ["Region"]}
                                         click L; assert the download suffix and file contents. For CSV
                                         export, include a seeded cell value (or an imported row value).
  {"op": "expect_clipboard", "target": L, "protocol": "HTTPS"}  read the browser clipboard and
                                         assert it contains L and has the selected clone protocol.
A scenario that says "the requested workflow" (or "follows the visible controls") means: perform the
operation that the Requirement text of that scenario describes, on the seeded record, with the concrete
values the scenario lists; then assert the observable result the Requirement text promises. When the
scenario does not say which cell, row or column to use, choose one from the seeds yourself (the cell named
in the seed, the row holding a seeded value, the next empty cell): a concrete reasonable choice is
expected, "not specified" is not a reason to skip. "the requested workflow" is NOT a placeholder and never a
reason to skip: the Requirement text of that scenario says what the workflow is.
A literal that the requirement writes with a placeholder ("Last updated: <last updated value>",
"Filter <header text>") appears in ALLOWED LITERALS as its fixed prefix only ("Last updated:", "Filter");
match it as that prefix, never expect the placeholder text itself.
Cell coordinates (A1, B2, C10 ...) are ALWAYS allowed as targets of cell_click/cell_type/expect_cell and
expect_role, whether or not they appear in ALLOWED LITERALS. Numbers, formulas (=A1+B1, =1/0, =SUM(A1:A2))
and spreadsheet error tokens (#DIV/0!, #REF!) are always allowed as cell values.
Controls (targets of open/click/check/fill/upload) may also be any control named anywhere in the
requirement (the CONTROLS list), or such a name followed by a seeded value ("Remove bob-reviewer");
expect_visible/expect_absent targets must come from the scenario's own ALLOWED LITERALS.
Copy, cut, paste, undo and redo are done with press Control+C / Control+X / Control+V / Control+Z /
Control+Y on the selected cell. A paste script must first copy in this script or use set_clipboard; an empty
fresh browser clipboard is not a valid fixture. Import is scripted with the upload step and
$CSV; after import, assert the file-derived workbook name with $CSV_NAME, not $NEW_NAME.
Export uses expect_download on the control that triggers it.
After each "Copy clone value" click, use expect_clipboard for that protocol and the seeded repository name;
the "Copied" toast alone does not prove the clipboard contains the clone value.
For a pivot table, formula, or other numeric result, assert the result in a destination cell with expect_cell;
seeing the original source labels and values somewhere on the page does not prove the calculation.
L and V MUST be copied verbatim from the ALLOWED LITERALS list of that scenario (control names the
requirement quotes, seeded record names, or the fixture account/email/password). Never invent names.
Values the user must make up are written as placeholders, allowed as fill values and as
expect_visible/expect_absent targets (and cell_type values): $NEW_USERNAME, $NEW_EMAIL, $NEW_PASSWORD
(also for the confirmation field), $NEW_NAME (the name of a repository, team, workbook, worksheet,
branch or label the script creates -- assert it afterwards), $TEXT (comment body, title, description).
$CSV_NAME is different: it is only an expect_visible target after $CSV upload.
Never register or create records with the fixture account or with a word taken from the requirement
prose as a name; use the placeholders for anything new. Placeholders are for records the script
CREATES; to refer to an EXISTING account, repository or record (adding a member, assigning a reviewer)
use the seeded name from ALLOWED LITERALS -- a $NEW_USERNAME account does not exist yet.
If the scenario needs a starting state that the allowed literals cannot establish (an existing record
the requirement does not name, a second account with credentials), set "skip".
"signed_in": true means the script first signs in with the fixture account; do not add sign-in steps.
Prefer the shortest path that a real user of this product would take: open the seeded record, then
the tab or page the scenario names, then act. End with at least one expect_visible/expect_absent taken
from the THEN step (a quoted literal, a seeded name, or a status word the requirement names).
Set confidence below 0.5 only when you are guessing at controls the requirement does not name."""


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


def allowed_literals(node: Mapping, fixtures: Fixtures, context: str = "",
                     scenario: Mapping | None = None) -> list[str]:
    """Literal vocabulary for one scenario, plus the leaf contract and fixtures.

    The old leaf-wide union let one scenario's seed or title leak into another
    scenario's assertions. Navigation may still use suite_controls.
    """
    text = _node_text(node) + "\n" + context
    values: list[str] = []
    chosen = [scenario] if scenario is not None else (node.get("scenarios") or [])
    for item in chosen:
        for step in item.get("steps") or []:
            text += "\n" + str(step.get("content") or "")
    for item in chosen:
        # Templated titles carry their concrete values unquoted: "... the
        # requested workflow Pivot1 the requested workflow Region ...".
        title = str(item.get("name") or item.get("title") or "")
        if TEMPLATE_TEXT.search(title):
            title = re.sub(r"^\s*(?:REQ[\w-]+\s*(?::|-)?\s*)+", "", title, flags=re.I)
            for token in re.split(r"the\s+requested\s+workflow|[,;]", title, flags=re.I):
                token = token.strip(" -:")
                if 1 < len(token) <= 40 and not TEMPLATE_TEXT.search(token) and not _descriptive(token):
                    values.append(token)
    for match in _ANY_LITERAL.finditer(text):
        # "Last updated: <last updated value>" is a pattern; only its fixed
        # prefix is something a script may look for.
        value = literal_prefix((match.group(1) or match.group(2) or match.group(3)).strip())
        if value and not TEMPLATE_TEXT.search(value) and not _descriptive(value):
            values.append(value)
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


def suite_controls(leaves: Iterable[Mapping], fixtures: Fixtures, shared: str = "") -> list[str]:
    """Every literal the whole requirement names: a control quoted for one
    leaf ("Issues", "Code", "Branch") is a real control of the product, so any
    script may navigate through it. Assertions stay local to the scenario."""
    values: list[str] = []
    for node in leaves:
        values += allowed_literals(node, fixtures)
    values += allowed_literals({"name": "", "description": shared}, fixtures)
    return list(dict.fromkeys(values))


def review_targets(leaves: Iterable[Mapping], fixtures: Fixtures, context: Mapping[str, str] | None = None,
                   shared: str = "") -> list[dict]:
    """Scenarios that got no mechanical script, with what a proposal may name."""
    targets: list[dict] = []
    seen_steps: set[tuple] = set()
    leaves = list(leaves)
    controls = suite_controls(leaves, fixtures, shared)
    for node in leaves:
        node_id = str(node.get("id"))
        node_text = _node_text(node)
        for scenario in node.get("scenarios") or []:
            allowed = allowed_literals(node, fixtures, (context or {}).get(node_id, ""), scenario)
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
                            "seed_kinds": parsed.seed_kinds,
                            "controls": controls, "signed_in": parsed.signed_in,
                            "has_grid": bool(re.search(r"\bgrid\b|gridcell|\bcells?\b|worksheet|workbook|spreadsheet|"
                                                       r"\b[A-Z]{1,3}[0-9]{1,4}\s*=",
                                                       node_text + " " + shared + " " + " ".join(steps), re.I))})
    return targets


def build_prompt(targets: list[dict], fixtures: Fixtures) -> str:
    parts = ["Write one check script per scenario below, as JSON: {\"scenarios\": [ ... ]}.\n" + DSL]
    parts.append(f"\nFixture account: `{fixtures.account}` / `{fixtures.password}` (email `{fixtures.email}`).")
    controls = [c for c in (targets[0].get("controls") or []) if len(c) <= 60][:160] if targets else []
    if controls:
        parts.append("\nCONTROLS (named anywhere in the requirement; usable as open/click/check/fill targets): "
                     + json.dumps(controls, ensure_ascii=False))
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
        if HOME_TARGET.match(str(target).strip()):
            return "await h.openHome(page);"
        return f"await h.openNamed(page, {_ts(target)});"
    if op == "click":
        return f"await h.clickNamed(page, {_ts(target)});"
    if op == "fill":
        return f"await h.fillField(page, {_ts(target)}, {_ts(str(step.get('value')))});"
    if op == "check":
        return f"await h.checkNamed(page, {_ts(target)});"
    if op == "press":
        return f"await h.pressKey(page, {_ts(str(step.get('key')))});"
    if op == "set_clipboard":
        value = str(step.get("table") or "")
        return f"await h.setClipboardText(page, {_ts(value)});"
    parts = seed_parts if step.get("seed_row") else (lambda value: [str(value)])
    if op == "expect_visible":
        return f"await h.expectTextsVisible(page, [{', '.join(_ts(part) for part in parts(target))}]);"
    if op == "expect_absent":
        return f"await h.expectAbsent(page, {_ts(parts(target)[0])});"
    if op == "cell_click":
        return f"await h.clickCell(page, {_ts(target)});"
    if op == "cell_type":
        # A seeded row `Item/Qty` names two cells; the first part goes in this one.
        return f"await h.typeInCell(page, {_ts(target)}, {_ts(parts(str(step.get('value')))[0])});"
    if op == "expect_cell":
        return f"await h.expectCell(page, {_ts(target)}, {_ts(parts(str(step.get('value') or ''))[0] if step.get('value') else '')});"
    if op == "expect_role":
        return f"await h.expectRole(page, {_ts(str(step.get('role')))}, {_ts(target)});"
    if op == "upload":
        csv = str(step.get("csv") or "").replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
        return f"await h.uploadFile(page, {_ts(target)}, '{csv}');"
    if op == "expect_download":
        content = step.get("contains") or []
        return (f"await h.expectDownload(page, {_ts(target)}, {_ts(str(step.get('value')))}, "
                f"[{', '.join(_ts(item) for item in content)}]);")
    if op == "expect_clipboard":
        return f"await h.expectClipboard(page, {_ts(target)}, {_ts(str(step.get('protocol')))});"
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
    # A seeded row `East/1200` is shown as its parts once imported or listed.
    for seed in target.get("seeds") or []:
        if "/" in seed and seed.count("/") <= 3:
            allowed |= {part.strip() for part in seed.split("/") if len(part.strip()) >= 3}
    controls = allowed | set(target.get("controls") or [])

    def is_control(value: object) -> bool:
        """A control the requirement names anywhere, or a composed name such
        as "Remove bob-reviewer" / "Worksheet options for Sheet1" whose prefix
        is a named control and whose remainder is a seeded or allowed value."""
        if not isinstance(value, str):
            return False
        value = value.strip()
        if value in controls:
            return True
        for prefix in controls:
            if value.startswith(prefix + " ") and value[len(prefix):].strip() in allowed:
                return True
        return False
    asserted = False
    clipboard_ready = False
    clipboard_rows: list[list[str]] | None = None
    selected_cell = ""
    pasted_cells: dict[str, str] = {}
    uploaded_csv: list[list[str]] | None = None
    uploaded = False
    edited_cells: set[str] = set()
    pending_clone_copies: list[tuple[int, str]] = []
    selected_protocol = ""
    cell_seeds = [value for kind, value in target.get("seed_kinds") or []
                  if re.search(r"\bcell\s+[A-Z]{1,3}[0-9]{1,4}\s+value\b", kind, re.I)]
    repository_seeds = {value for kind, value in target.get("seed_kinds") or []
                        if re.search(r"\brepository\b", kind, re.I)}
    reset_prerequisite = re.search(
        r"\bAfter\b[^.]{0,600}?\bclicks?\s+[“\"]([^”\"]+)[”\"][^.]{0,600}?Verification code",
        str(target.get("description") or ""), re.I)
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict) or step.get("op") not in OPS:
            problems.append(f"step {index}: unknown op {json.dumps(step.get('op') if isinstance(step, dict) else step)}; "
                            f"use one of {sorted(OPS)}")
            continue
        op = step["op"]
        if op == "expect_clipboard":
            value = step.get("target")
            if not isinstance(value, str) or value.strip() not in allowed:
                problems.append(f"step {index}: expect_clipboard target must be a seeded or quoted literal")
            if pending_clone_copies and value not in repository_seeds:
                problems.append(f"step {index}: clone clipboard target must be the seeded repository name")
            if step.get("protocol") not in {"HTTPS", "SSH"}:
                problems.append(f"step {index}: expect_clipboard protocol must be HTTPS or SSH")
            elif pending_clone_copies and pending_clone_copies[-1][1] == step.get("protocol"):
                pending_clone_copies.pop()
            asserted = True
            continue
        if op == "set_clipboard":
            if not target.get("has_grid", True):
                problems.append(f"step {index}: set_clipboard needs a spreadsheet grid")
            if step.get("value") != "$TABLE":
                problems.append(f"step {index}: set_clipboard value must be $TABLE")
            clipboard_ready = True
            clipboard_rows = [row.split(",") for row in seed_csv(target.get("seeds") or []).splitlines()]
            continue
        if op == "press":
            if step.get("key") not in KEYS:
                problems.append(f"step {index}: key {json.dumps(step.get('key'))} is not one of {sorted(KEYS)}")
            if step.get("key") in {"Control+C", "Control+X"}:
                clipboard_ready = True
                clipboard_rows = None  # The browser copies the selected live cells.
            if step.get("key") == "Control+V" and not clipboard_ready:
                problems.append(f"step {index}: Control+V has no clipboard source; copy cells or set_clipboard first")
            if step.get("key") == "Control+V" and clipboard_rows and CELL.match(selected_cell):
                anchor = re.fullmatch(r"([A-Z]+)([1-9]\d*)", selected_cell)
                if anchor:
                    base_col = 0
                    for char in anchor.group(1):
                        base_col = base_col * 26 + ord(char) - ord('A') + 1
                    for row_offset, row in enumerate(clipboard_rows):
                        for col_offset, item in enumerate(row):
                            column, letters = base_col + col_offset, ""
                            while column:
                                column, rem = divmod(column - 1, 26)
                                letters = chr(ord('A') + rem) + letters
                            pasted_cells[f"{letters}{int(anchor.group(2)) + row_offset}"] = item
            if step.get("key") in {"Control+Z", "Control+Y"}:
                pasted_cells.clear()
            continue
        value = step.get("target")
        if op in {"click", "open"} and value in {"HTTPS", "SSH"}:
            selected_protocol = str(value)
        if (op == "click" and isinstance(value, str) and re.search(r"\bcopy\s+clone\s+value\b", value, re.I)):
            pending_clone_copies.append((index, selected_protocol))
        if op in {"cell_click", "cell_type", "expect_cell"}:
            if not target.get("has_grid", True):
                problems.append(f"step {index}: {op} needs a spreadsheet grid; this product has none")
                continue
            if not isinstance(value, str) or not (CELL.match(value.strip())
                                                  or (op == "cell_click" and RANGE.match(value.strip()))):
                problems.append(f"step {index}: {op} target {json.dumps(value, ensure_ascii=False)} is not a cell "
                                f"coordinate such as A1" + (" or a range such as A1:B2" if op == "cell_click" else ""))
            if op == "cell_click" and isinstance(value, str):
                selected_cell = value.strip().split(":", 1)[0]
            if op != "cell_click":
                typed = step.get("value")
                if isinstance(typed, (int, float)) and not isinstance(typed, bool):
                    typed = step["value"] = str(typed)
                if not isinstance(typed, str) or not (typed.strip() in allowed or typed.strip() in PLACEHOLDERS
                                                      or NUMBER.match(typed.strip())
                                                      or FORMULA.match(typed.strip())
                                                      or (op == "expect_cell" and (typed.strip() == ""
                                                                                   or ERROR_TOKEN.match(typed.strip())))):
                    problems.append(f"step {index}: {op} value {json.dumps(typed, ensure_ascii=False)} is not a seeded "
                                    f"value, number, placeholder or literal the requirement quotes")
            # v9.2.2 (cce3f5ad4f21): expect_cell did not count as an assertion, so
            # every cell-only script was rejected for "no expect step".
            if op == "cell_type" and isinstance(value, str):
                edited_cells.add(value.strip())
            if (op == "expect_cell" and isinstance(value, str) and value.strip() in pasted_cells
                    and value.strip() not in edited_cells and str(step.get("value")) != pasted_cells[value.strip()]):
                problems.append(f"step {index}: pasted {value} should be {pasted_cells[value.strip()]!r}, "
                                f"not {step.get('value')!r}")
            if op == "expect_cell" and uploaded_csv and isinstance(value, str) and value.strip() not in edited_cells:
                cell = re.fullmatch(r"([A-Z]+)([1-9]\d*)", value.strip())
                if cell:
                    column = 0
                    for char in cell.group(1):
                        column = column * 26 + ord(char) - ord('A') + 1
                    row = int(cell.group(2)) - 1
                    column -= 1
                    if row < len(uploaded_csv) and column < len(uploaded_csv[row]):
                        expected = uploaded_csv[row][column]
                        if str(step.get("value")) != expected:
                            problems.append(f"step {index}: after CSV import {value} should be {expected!r}, "
                                            f"not {step.get('value')!r}")
            asserted = asserted or op == "expect_cell"
            continue
        if op == "upload":
            if not is_control(value):
                problems.append(f"step {index}: upload target {json.dumps(value, ensure_ascii=False)} is not an allowed literal")
            if str(step.get("value") or "").strip() != "$CSV":
                problems.append(f"step {index}: upload value must be $CSV")
            else:
                uploaded_csv = [row.split(",") for row in seed_csv(target.get("seeds") or []).splitlines()]
                uploaded = True
                edited_cells.clear()
            continue
        if op == "expect_download":
            if not is_control(value):
                problems.append(f"step {index}: expect_download target {json.dumps(value, ensure_ascii=False)} is not an allowed literal")
            suffix = str(step.get("value") or "").strip()
            if not re.match(r"^\.[a-z0-9]{1,8}$", suffix):
                problems.append(f"step {index}: expect_download value must be a file suffix such as .csv")
            if index > 1 and isinstance(steps[index - 2], dict) and steps[index - 2].get("op") == "click" \
                    and steps[index - 2].get("target") == value:
                problems.append(f"step {index}: expect_download already clicks {value!r}; remove the prior click")
            content = step.get("contains", [])
            if not isinstance(content, list) or any(not isinstance(item, str) or not item.strip()
                                                    or item.strip() not in allowed for item in content):
                problems.append(f"step {index}: expect_download contains must be a list of nonempty allowed literals")
            elif suffix == ".csv" and re.search(r"\bexport\b", target.get("name", "") + " "
                                                  + target.get("description", ""), re.I):
                needed = [item for row in uploaded_csv for item in row] if uploaded_csv else cell_seeds
                if needed and not any(item in content for item in needed):
                    problems.append(f"step {index}: CSV export must check downloaded contents for a seeded "
                                    "cell or imported row value")
            asserted = True
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
        if op == "expect_visible" and uploaded and isinstance(value, str):
            imported = {item for row in uploaded_csv or [] for item in row}
            if value in cell_seeds and value not in imported:
                problems.append(f"step {index}: {value!r} is a seeded cell value from the old workbook, "
                                "not a result of the uploaded CSV")
            if value == "$NEW_NAME" and not any(
                    isinstance(previous, dict) and previous.get("op") == "fill"
                    and previous.get("value") == "$NEW_NAME" for previous in steps[:index - 1]):
                problems.append(f"step {index}: $NEW_NAME was never entered; a CSV import uses its uploaded "
                                "file name, so assert $CSV_NAME instead")
        if value == "$CSV_NAME" and (op != "expect_visible" or not uploaded):
            problems.append(f"step {index}: $CSV_NAME is an assertion only after uploading $CSV")
        if (reset_prerequisite and isinstance(value, str) and "Verification code" in value
                and op.startswith("expect_") and not any(
                    isinstance(previous, dict) and previous.get("op") == "click"
                    and previous.get("target") == reset_prerequisite.group(1)
                    for previous in steps[:index - 1])):
            problems.append(f"step {index}: click {reset_prerequisite.group(1)!r} before asserting "
                            "Verification code; the requirement shows it only in the next step")
        if op == "open" and isinstance(value, str) and HOME_TARGET.match(value.strip()):
            continue
        if op in {"open", "click"} and uploaded_csv and value in (target.get("seeds") or []):
            uploaded_csv = None  # Explicitly reopened the original seeded record.
            uploaded = False
        if not placeholder_ok and is_control(value):
            pass
        elif not isinstance(value, str) or not (value.strip() in allowed or (placeholder_ok and value.strip() in PLACEHOLDERS)):
            problems.append(f"step {index}: {op} target {json.dumps(value, ensure_ascii=False)} is not an allowed literal"
                            + ("" if placeholder_ok else " (placeholders are not control names)"))
        if op == "fill":
            typed = step.get("value")
            if typed == "$CSV_NAME":
                problems.append(f"step {index}: $CSV_NAME is derived from the upload and cannot be filled")
            if not isinstance(typed, str) or not (typed.strip() in allowed or typed.strip() in PLACEHOLDERS):
                problems.append(f"step {index}: fill value {json.dumps(typed, ensure_ascii=False)} is not an allowed "
                                f"literal or placeholder ({', '.join(PLACEHOLDERS)})")
            # github review S14/S15: the fixture username typed as a repository
            # or fork name. Names of new records are $NEW_NAME.
            elif (fixtures.account and typed.strip() == fixtures.account and isinstance(value, str)
                    and not re.search(r"user|account|email|login|member|assignee|reviewer|owner|collaborator|"
                                      r"search|find|filter|sign|name of the (?:user|account)", value, re.I)):
                problems.append(f"step {index}: fill value {json.dumps(typed)} is the fixture account, typed into "
                                f"{json.dumps(value)}; a record the script creates is named $NEW_NAME")
        asserted = asserted or op.startswith("expect_")
    if not asserted:
        problems.append("no expect_visible/expect_absent step: the script must assert something from the THEN step")
    else:
        # Sheet review S11: "click Add worksheet ... expect_visible Add worksheet".
        # An expectation is evidence only when it is not a control the script
        # itself pressed or a value it typed into a cell or field.
        acted = {str(step.get("target") or "").strip().lower() for step in steps if isinstance(step, dict)
                 and step.get("op") in {"open", "click", "check", "fill", "upload"}}
        typed_at = {}
        for index, step in enumerate(steps):
            if isinstance(step, dict) and step.get("op") in {"fill", "cell_type"}:
                typed_at.setdefault(str(step.get("value") or "").strip().lower(), index)
        submits = [index for index, step in enumerate(steps) if isinstance(step, dict)
                   and (step.get("op") in {"click", "check", "upload"} or (step.get("op") == "press"
                                                                            and step.get("key") in {"Enter", "Control+Enter"}))]

        seeded_lower = {seed.lower() for seed in target.get("seeds") or []}
        for seed in target.get("seeds") or []:
            seeded_lower |= {part.lower() for part in seed_parts(seed)}

        def is_evidence(index: int, step: dict) -> bool:
            if step.get("op") in {"expect_cell", "expect_role", "expect_download"}:
                return True
            shown = str(step.get("target") or "").strip().lower()
            if shown in acted:
                return False
            if shown in typed_at:
                # Sheet review S31: typing the seeded `East` into an empty cell
                # and expecting `East` visible passes on the untouched seed row.
                if shown in seeded_lower:
                    return False
                # A typed name shown again after Create/Save proves the record.
                return any(typed_at[shown] < submit < index for submit in submits)
            return True

        expects = [(index, step) for index, step in enumerate(steps) if isinstance(step, dict)
                   and str(step.get("op") or "").startswith("expect_")]
        evidence = [step for index, step in expects if is_evidence(index, step)]
        if expects and not evidence:
            problems.append("every expect step names a control the script itself clicked or a value it typed; assert "
                            "the outcome the THEN step promises (a message, a new record, a changed status) instead")
    if pending_clone_copies:
        problems.append("each Copy clone value click needs expect_clipboard with the selected HTTPS/SSH protocol")
    if (re.search(r"\bpivot\s+table\b", str(target.get("name") or ""), re.I)
            and any(isinstance(step, dict) and step.get("op") == "click" and step.get("target") == "Apply"
                    for step in steps)
            and not any(isinstance(step, dict) and step.get("op") == "expect_cell" for step in steps)):
        problems.append("pivot table Apply needs expect_cell on the result worksheet; source text is not aggregation evidence")
    # v9.2.4 github (1307196473c1): a script typed the verification code
    # "123456" into its field and then expected "123456" to be visible; secrets
    # and codes are not echoed as page text. Reject that pairing explicitly.
    secret_values = {str(step.get("value")).strip() for step in steps if isinstance(step, dict)
                     and step.get("op") == "fill" and isinstance(step.get("value"), str)
                     and re.search(r"password|code|token|secret|pin\b", str(step.get("target") or ""), re.I)}
    for index, step in enumerate(steps, 1):
        if (isinstance(step, dict) and step.get("op") == "expect_visible"
                and str(step.get("target") or "").strip() in secret_values):
            problems.append(f"step {index}: expect_visible {json.dumps(step.get('target'))} is a value typed into a "
                            f"password/code field; such values are not shown as page text -- assert the outcome instead")
    # Sheet review S23: "type East, press Escape, expect_absent East" -- `East`
    # is a seeded row that exists before the scenario, so a correct app fails
    # the check. Absence of a seeded value needs a step that removes it first.
    seeded = set(target.get("seeds") or [])
    for seed in list(seeded):
        seeded |= set(seed_parts(seed))
    removing = False
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            continue
        if step.get("op") in {"click", "open", "press"} and re.search(
                r"delete|remove|discard|clear|\bcut\b|Control\+X|^Delete$|^Backspace$|^closed?$|^open$|filter|search|"
                r"find|sort|status|label|assignee|author|milestone|\bonly\b|^all\b|hide|collapse|archive",
                str(step.get("target") or step.get("key") or ""), re.I):
            removing = True  # deleted, or hidden by a filter/search/status tab
        if step.get("op") == "fill":
            removing = True  # a search/filter box narrows the list
        if step.get("op") == "expect_absent" and str(step.get("target") or "").strip() in seeded and not removing:
            hint = ("assert the cell instead (expect_cell with the seeded value, or with \"\" for an emptied cell)"
                    if target.get("has_grid") else "assert what the THEN step promises instead")
            problems.append(f"step {index}: expect_absent {json.dumps(step.get('target'))} is a seeded value that exists "
                            f"before the scenario; it stays on a correct app unless a step deletes or filters it out -- {hint}")
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
        if step["op"] == "upload":
            step["csv"] = seed_csv(target.get("seeds") or [])
        if step["op"] == "set_clipboard":
            step["table"] = seed_csv(target.get("seeds") or []).replace(",", "\t")
        # Only a seeded `label/value` row splits into cells; "src/search.ts" is a path.
        step["seed_row"] = str(step.get("target") or "") in set(target.get("seeds") or []) \
            or str(step.get("value") or "") in set(target.get("seeds") or [])
        if step["op"] not in {"press", "set_clipboard"}:
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
    # Templated tasks yield the same script for sibling scenarios (sheet
    # REQ-1-3-1 x3): one copy per leaf is enough.
    def body(test: str) -> str:
        return re.sub(r"^test\('[^']*',", "", test.strip(), count=1)
    present = {body("test(" + part) for part in spec_source.split("\ntest(")[1:]}
    titles = set(re.findall(r"^test\('((?:[^'\\]|\\.)*)'", spec_source, re.M))
    kept: list[str] = []
    for test in tests:
        title = re.match(r"^test\('((?:[^'\\]|\\.)*)'", test.strip())
        # Playwright refuses a file with two tests of one title (sheet
        # REQ-1-2-1 lost all its model tests to that).
        if body(test) in present or (title and title.group(1) in titles):
            continue
        present.add(body(test))
        if title:
            titles.add(title.group(1))
        kept.append(test)
    if not kept:
        return spec_source
    return spec_source.rstrip("\n") + "\n\n" + "\n\n".join(kept) + "\n"
