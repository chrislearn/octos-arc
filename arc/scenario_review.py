"""Requirement-grounded model proposals for generated acceptance scripts.

The model proposes; the harness verifies. A proposal is a short list of
whitelisted operations (including open/click/fill/check/press/reload/sign_in
and grounded assertions). Every target and value must be a literal the requirement
itself quotes (“…”, "…" or `…`), a seeded value, or a suite fixture. A
proposal naming anything else, using an unknown operation, asserting nothing,
or reporting low confidence is dropped as one case -- a partial sequence would fail
for our reasons, not the application's. The model therefore adds navigation
order and which literal is the assertion; it cannot invent controls or data.
"""
from __future__ import annotations

from quality_control import valid_json_schema

import hashlib
import csv
import io
import json
import re
from typing import Iterable, Mapping

from seed_facts import setup_cells
from scenario_tests import (Fixtures, spec_header, _ANY_LITERAL, _compile_scenario, _descriptive, _node_text, _sentences, _ts,
                            literal_prefix)

OPS = {"open", "click", "hover", "fill", "check", "press", "reload", "sign_in", "expect_sign_in_rejected", "set_clipboard", "expect_visible", "expect_absent",
       "cell_click", "cell_type", "expect_cell", "expect_role", "upload", "expect_download",
       "expect_input_value", "select_option", "drag", "upload_fixture", "expect_count", "expect_attribute",
       "snapshot_response", "expect_response_unchanged", "expect_clipboard", "cell_context", "header_context", "expect_selected", "watch_response", "expect_response"}
HEADER = re.compile(r"^(?:[1-9][0-9]{0,4}|[A-Z]{1,3})$")
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
    "$UNKNOWN_EMAIL": "a syntactically valid email address that is not a registered account",
    "$NEW_PASSWORD": "a new compliant password (12+ chars); reuse it for the confirmation field",
    "$WRONG_PASSWORD": "a compliant password different from the fixture password; rejection checks only",
    "$NEW_NAME": "a new, unused record name (repository, team, workbook, worksheet, branch, label): lowercase "
                 "letters, digits, hyphens; assert it afterwards to prove the record was created",
    "$TEXT": "a short free-form text (comment body, title, description)",
    "$BLANK": "whitespace only (an invalid empty input for a required field)",
    "$CSV": "a CSV file of the seeded `label/value` rows in seed order, no header row -- after import A1 holds "
            "the first seeded label, B1 its value, A2 the second label ... (only as the value of an upload step)",
    "$CSV_FORMAT": "a UTF-8 CSV fixture with ordinary first-row data, empty fields, numeric and Chinese text, "
                   "a quoted comma, an escaped quote, and a line break inside a quoted field; use only when the "
                   "import requirement explicitly promises these formats",
    "$CSV_NAME": "the name derived from the uploaded derived-import.csv file: derived-import "
                 "(assertion after upload only, not a new-record fill value)",
    "$CSV_FORMAT_NAME": "the name derived from derived-format.csv: derived-format (assertion after $CSV_FORMAT upload)",
    "$INVALID_CSV": "a fixed malformed CSV with a field whose opening quote is never closed; "
                    "only for upload when the requirement explicitly requires invalid CSV rejection",
    "$INVALID_CSV_NAME": "the absent workbook name derived from derived-invalid.csv: derived-invalid "
                         "(assertion after invalid upload only)",
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


CSV_FORMAT_ROWS = [["Region", "East,West", 'Say "Hi"', "第一行\n第二行", "", "1200"],
                   ["North", "800", "", "", "中文", "0"],
                   ["0012", "1.00", " spaced ", "", "", ""], ["", "", "", "", "", ""]]


def csv_format_fixture() -> str:
    """Exercise the concrete CSV formats an import contract explicitly names."""
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\n").writerows(CSV_FORMAT_ROWS)
    return buffer.getvalue()


def csv_format_contract(target: Mapping) -> bool:
    name = str(target.get("name") or "")
    if re.search(r"\bexport\b", name, re.I) and not re.search(r"\bimport\b", name, re.I):
        return False
    text = str(target.get("description") or "")
    return bool(re.search(r"\bimport\b.*\bCSV\b", name + " " + text, re.I)
                and re.search(r"(?:commas?\s+(?:enclosed\s+in\s+)?double\s+quotes?|escaped\s+(?:pairs?\s+of\s+)?double\s+quotes?)", text, re.I)
                and re.search(r"line\s+breaks?\s+within\s+fields?|UTF-8", text, re.I))


def csv_export_contract(target: Mapping) -> bool:
    name = str(target.get("name") or "")
    if re.search(r"\bimport\b", name, re.I) and not re.search(r"\bexport\b", name, re.I):
        return False
    text = str(target.get("description") or "")
    return bool(re.search(r"\bexport\b.*\bCSV\b", name + " " + text, re.I)
                and re.search(r"\bescapes?\b|\bempty\s+cells?\b|\brow\s+and\s+column\s+order\b", text, re.I))


def expand_placeholder(value: str, scope: str) -> str:
    """Deterministic per scenario: the same placeholder expands identically
    within one script, differently across scenarios (parallel tests)."""
    slug = hashlib.sha1(scope.encode("utf-8")).hexdigest()[:6]
    return {
        "$NEW_USERNAME": f"user-{slug}",
        "$NEW_EMAIL": f"user-{slug}@example.test",
        "$UNKNOWN_EMAIL": f"unknown-{slug}@example.test",
        "$NEW_PASSWORD": f"Derived-pass-{slug}!",
        "$WRONG_PASSWORD": f"Wrong-pass-{slug}!",
        "$NEW_NAME": f"derived-{slug}",
        "$CSV_NAME": "derived-import",
        "$CSV_FORMAT_NAME": "derived-format",
        "$INVALID_CSV_NAME": "derived-invalid",
        "$TEXT": f"Derived text {slug}",
        "$BLANK": "   ",
    }.get(value, value)
MAX_CASES = 8

KEYS = {"Enter", "Escape", "Tab", "Delete", "Backspace", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
        "Home", "End", "PageUp", "PageDown", "Shift+Enter", "Shift+Tab", "Control+Enter", "Control+C", "Control+V",
        "Control+X", "Control+Z", "Control+Y", "Control+A"}
MIN_CONFIDENCE = 0.5
MAX_STEPS = 60

SYSTEM = ("You convert product requirement scenarios into short browser check scripts. "
          "Reply with one JSON object only; no prose, no markdown.")

DSL = """Independent branches may use {"id":..., "title":..., "cases":[{"signed_in":false,"confidence":0.9,"steps":[...]}, ...]}.
At most 8 cases per scenario and 60 steps per case for all formats; separate setup/action/assertion phases.
Optional test_data maps $DATA_NAME to {"type":"string"|"number"|"boolean","value":...}.
Use these deterministic values for new records and boundary inputs; they are test-generated, not official product labels.
Never use test_data to invent control labels, product error text, HTTP contracts or expected derived calculations.
Every case starts with a fresh reset/browser;
never rely on state from another case. Keep all required positive/negative outcomes across the cases.
If using cases, do not also supply steps or skip. Case titles are assigned by the harness.
Each script is {"id": <the [S..] id shown before the scenario>, "title": <scenario title verbatim>,
 "signed_in": true|false, "confidence": 0..1, "steps": [ ... ], "skip": "<reason>" }. The "id" is mandatory.
Operations (use only these):
  {"op": "open", "target": L}            navigate to where L (a page, tab or menu entry name) is visible; click it if it is a control
  {"op": "click", "target": L}           click the control named L
  {"op": "hover", "target": L}           hover the seeded record or named control L before opening its actions
  {"op": "fill", "target": L, "value": V} type V into the field labelled L
  {"op": "expect_input_value", "target": L, "value": V} assert the exact labelled input value, not nearby text
  {"op": "select_option", "target": L, "value": V} select an actual named option in a labelled native select
  {"op": "snapshot_response", "target": API_PATH, "key": "before"} save the watched successful JSON response
  {"op": "expect_response_unchanged", "target": API_PATH, "key": "before"} compare a NEW successful watched response
      to the snapshot after rejection/reload; watch_response and trigger a fresh read before this check
  {"op": "check", "target": L}           check the checkbox named L
  {"op": "press", "key": "Enter"}        press a key: Enter, Escape, Tab, Delete, Backspace, Arrow keys,
                                         Home, End, Shift+Enter, Shift+Tab, Control+C/V/X/Z/Y/A, Control+Enter
  {"op": "reload"}                      reload the current browser page before checking persistence
  {"op": "sign_in", "target": V, "value": V}  sign in after a prior workflow with the named account/email
                                         and password; use the SAME $NEW_USERNAME/$NEW_EMAIL/$NEW_PASSWORD
                                         placeholders entered during registration, never the seeded account
  {"op": "expect_sign_in_rejected", "target": V, "value": V}  try these credentials through the login UI;
                                         assert the session stays anonymous (for unknown email or old password)
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
  {"op": "cell_context", "target": "A1"}  right-click the cell (opens the grid context menu, e.g. "Paste")
  {"op": "header_context", "target": "2"}  right-click row header "2" or column header "B" (opens its menu;
                                         then click the menu command the requirement names)
  {"op": "expect_selected", "target": "A1:B2"}  assert exactly this rectangle is selected: every gridcell in it
                                         has aria-selected="true" and the cells just outside it "false"
  {"op": "expect_role", "role": R, "target": L}  assert an element with ARIA role R and accessible name L
                                         (roles: grid, gridcell, tab, dialog, menu, menuitem, button, link, ...)
  {"op": "upload", "target": L, "value": "$CSV"|"$CSV_FORMAT"|"$INVALID_CSV"} choose a file in the named file input.
                                         $CSV has seeded rows, no header; $INVALID_CSV is a fixed unclosed quote
                                         and is allowed only when the leaf requires invalid CSV rejection.
                                         $CSV_FORMAT covers quoted commas, escaped quotes, multiline fields,
                                         empty fields, numeric and UTF-8 text when the import requirement names them.
  {"op": "expect_download", "target": L, "value": ".csv", "contains": ["Region"]}
                                         click L; assert the download suffix and file contents. For CSV
                                         export, include a seeded cell value (or an imported row value).
                                         Add "csv_rows":"$UPLOADED_CSV" after importing a known CSV fixture
                                         to compare every downloaded row and field exactly, including empty fields.
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
If the import requirement promises quoted commas, escaped quotes, multiline fields and UTF-8,
use $CSV_FORMAT and verify every cell of its two rows (A1:F2) after import, then reload and
recheck A1, D1 and E2. Its file-derived name is $CSV_FORMAT_NAME.
expect_response and expect_download accept schema (type/enum/required/properties/items/additionalProperties)
and exact_json for strict JSON equality including null/false/0/empty values. JSON object key order is irrelevant.
expect_download also accepts exact_text for byte-decoded UTF-8 content comparison. These expected contracts must
come from original requirements or an independently computed example, never the application's output.
Unsupported schema keywords are rejected, not ignored.
Additional supported operations:
  {"op":"drag","target":L,"destination":L} uses a real pointer drag; optional role selects unique accessible role/name targets.
      Cell coordinates on both ends use role=gridcell automatically, not visible cell text.
  {"op":"expect_count","role":"row","target":L,"count":2} counts exact accessible-role/name matches.
  {"op":"expect_attribute","role":"tab","target":L,"attribute":"aria-selected","value":"true"}
      checks state on one unique named control; allowed attributes aria-selected/multiselectable/checked/expanded/disabled, disabled, data-status.
  {"op":"upload_fixture","target":L,"filename":"sample.json","mime":"application/json","content":"..."}
      supplies constructed UTF-8 data for a format grounded in the original requirement. Pair with parsed-state assertions.
Every expected attribute/count/file format must be supported by the original requirement and independently audited.
Export uses expect_download on the control that triggers it.
If export explicitly promises CSV escaping, row order or empty fields, first import a known CSV
fixture when the product provides import, then use csv_rows:$UPLOADED_CSV in expect_download.
After each "Copy clone value" click, use expect_clipboard for that protocol and the seeded repository name;
the "Copied" toast alone does not prove the clipboard contains the clone value.
For a pivot table, formula, or other numeric result, assert the result in a destination cell with expect_cell;
seeing the original source labels and values somewhere on the page does not prove the calculation.
Literal rules: reuse ALLOWED LITERALS and source-grounded DEPENDENCY LITERALS for assertions and inputs.
CONTROLS from the whole requirement may name navigation/setup controls. The coordinate/numeric/formula
exceptions above take precedence. For freely chosen inputs use typed test_data ($DATA_MIN, $DATA_MAX, etc.);
these are not permission to invent validation thresholds, control names, enum options or expected calculations.
Do not skip simply because a free input number is absent from ALLOWED LITERALS. Ground required enum options
and prerequisite values in the source contract; report a missing dependency contract explicitly.
Values the user must make up are written as placeholders, allowed as fill values and as
expect_visible/expect_absent targets (and cell_type values): $NEW_USERNAME, $NEW_EMAIL, $NEW_PASSWORD
(also for the confirmation field), $NEW_NAME (the name of a repository, team, workbook, worksheet,
branch or label the script creates -- assert it afterwards), $TEXT (comment body, title, description).
$CSV_NAME is only an expect_visible target after $CSV upload. $CSV_FORMAT_NAME is only
an expect_visible target after $CSV_FORMAT upload. $INVALID_CSV_NAME is only
an expect_absent target after $INVALID_CSV upload and an attempted import. An invalid
CSV check must assert the documented error, then return home/reload and assert the
invalid workbook absent; do not replace that negative oracle with entry/reach.
Never register or create records with the fixture account or with a word taken from the requirement
prose as a name; use the placeholders for anything new. Placeholders are for records the script
CREATES; to refer to an EXISTING account, repository or record (adding a member, assigning a reviewer)
use the seeded name from ALLOWED LITERALS -- a $NEW_USERNAME account does not exist yet.
A GIVEN sentence starting "Scenario setup (not part of the seed):" lists starting cell values that are NOT
in the seed: right after opening the seeded record, enter each listed value with cell_type (in the listed cell)
followed by press Enter, then perform the scenario. Never expect a setup value before typing it.
If the scenario needs a starting state that the allowed literals cannot establish (an existing record
the requirement does not name, a second account with credentials), set "skip".
"signed_in": true means the script first signs in with the fixture account; do not add sign-in steps.
Prefer the shortest path that a real user of this product would take: open the seeded record, then
the tab or page the scenario names, then act. End with a grounded expect step taken from the THEN
outcome: expect_visible/expect_absent for a named result or expect_sign_in_rejected for credentials
the requirement explicitly says must fail.
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


def contract_outcomes(description: str) -> list[dict]:
    """Conservative verbatim display/error obligations, with their source quote.

    Conditional branches stay separate. This vocabulary is not an inferred
    complete semantic oracle and never proves a test's runtime result.
    """
    outcomes = {}
    quote = r'[“"`]([^”"`]+)[”"`]'
    for sentence in _sentences(description):
        patterns = [r'\b(?:shows?|displays?|returns?)\s+[^“"`.;]{0,100}' + quote,
                    quote + r'\s+(?:error|error message)\b']
        for pattern in patterns:
            for match in re.finditer(pattern, sentence, re.I):
                value = match.group(1).strip()
                if re.search(r"(?:not|never|without)\s+(?:directly\s+)?$", sentence[max(0, match.start() - 24):match.start()], re.I):
                    continue
                if value and not _descriptive(value) and not TEMPLATE_TEXT.search(value):
                    outcomes[value] = {"literal": value, "requirement_quote": sentence}
    return list(outcomes.values())


def semantic_contracts(steps: Iterable[str]) -> list[dict]:
    """Small, explicit state transitions a visible-text oracle cannot prove.

    These are derived from the scenario's own THEN text, never inferred from
    its title or generic workflow template. Unknown contracts remain outside
    this bounded vocabulary rather than being counted as covered.
    """
    then = [str(step) for step in steps if str(step).startswith("THEN:")]
    rules = (
        ("new_account_sign_in", r"(?:new account|account.s email).{0,100}(?:sign.in|sign in)|"
         r"(?:sign.in|sign in).{0,100}new account"),
        ("unknown_email_recovery", r"unknown email.{0,180}(?:does not|do not|no account|not modify|verification)"),
        ("unknown_email_no_account", r"unknown email.{0,180}(?:does not modify any account|does not create an account|"
         r"no account is created)"),
        ("cancel_keeps_session", r"cancel.{0,100}(?:session remains|session is retained|session remains valid|"
         r"remains signed.in|original page remains accessible)"),
        ("sign_out_survives_reload", r"(?:refresh|reopen).{0,180}(?:unauthenticated|re.authenticat|signed.out session)"),
    )
    found = []
    for kind, pattern in rules:
        quote = next((step for step in then if re.search(pattern, step, re.I | re.S)), None)
        if quote:
            found.append({"kind": kind, "requirement_quote": quote})
    return found


def semantic_contract_evidence(source: str, title: str, kind: str) -> bool:
    """Require an action and its outcome in one independently reset test case."""
    from test_policy import test_block
    block = test_block(source, title) or ""
    if not block:
        return False
    if kind == "new_account_sign_in":
        filled = re.search(r"h\.fillField\([^;]*['\"]user-([0-9a-f]{6})['\"]\)", block)
        if not filled:
            return False
        signed = re.search(r"h\.signIn\([^;]*['\"]user-" + filled.group(1)
                           + r"(?:@example\.test)?['\"]", block[filled.end():])
        return bool(signed and re.search(r"h\.expectIdentity\([^;]*,\s*true\)",
                                         block[filled.end() + signed.end():]))
    if kind == "unknown_email_recovery":
        return bool(re.search(r"h\.fillField\([^;]*['\"]unknown-[0-9a-f]{6}@example\.test['\"].*?"
                              r"h\.clickNamed\([^;]*Send reset link.*?"
                              r"h\.expect(?:TextsVisible|Role)\([^;]*123456", block, re.S))
    if kind == "unknown_email_no_account":
        filled = re.search(r"h\.fillField\([^;]*['\"]unknown-([0-9a-f]{6})@example\.test['\"]", block)
        return bool(filled and re.search(r"h\.clickNamed\([^;]*Reset password.*?"
                                         r"h\.expectSignInRejected\([^;]*['\"]unknown-" + filled.group(1)
                                         + r"@example\.test['\"]", block[filled.end():], re.S))
    if kind == "cancel_keeps_session":
        return bool(re.search(r"h\.clickNamed\(page, ['\"]Cancel['\"]\);.*?"
                              r"h\.expectIdentity\([^;]*,\s*true\)", block, re.S))
    if kind == "sign_out_survives_reload":
        return bool(re.search(r"Confirm sign out.*?page\.reload\(.*?"
                              r"h\.expectIdentity\([^;]*,\s*false\)", block, re.S))
    return False


def review_targets(leaves: Iterable[Mapping], fixtures: Fixtures, context: Mapping[str, str] | None = None,
                   shared: str = "", *, include_all: bool = False, dependency_tree: Mapping | None = None,
                   canonical_cells: Mapping[tuple[str, str], str] | None = None) -> list[dict]:
    """Scenario plans with requirement-grounded literals and controls.

    The legacy default selects unscripted scenarios. The no-official-spec
    planner reviews every scenario, including those with a mechanical script:
    a parser recognising some actions is not evidence of a sound oracle.
    """
    targets: list[dict] = []
    seen_steps: set[tuple] = set()
    leaves = list(leaves)
    controls = suite_controls(leaves, fixtures, shared)
    nodes = {str(node.get("id")): node for node in leaves}
    def dependency_literals(node):
        evidence = {}
        from requirement_order import dependency_ids
        def deps(item):
            return dependency_ids(dependency_tree, item) if dependency_tree else list(item.get("dependencies") or [])
        todo = deps(node)
        visited = {str(node.get("id"))}
        while todo:
            nid = str(todo.pop())
            if nid in visited or nid not in nodes:
                continue
            visited.add(nid)
            dependency = nodes[nid]
            # Dependency contracts, never another scenario's fixture/outcome.
            for match in _ANY_LITERAL.finditer(str(dependency.get("description") or "")):
                literal = literal_prefix((match.group(1) or match.group(2) or match.group(3)).strip())
                if literal and not _descriptive(literal):
                    evidence.setdefault(literal, []).append(nid)
            todo.extend(deps(dependency))
        return evidence
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
            workbook = next((value for kind, value in parsed.seed_kinds
                             if re.search(r"\bworkbook\b", kind, re.I)), "")
            seed_cells = {ref: value for (owner, ref), value in (canonical_cells or {}).items()
                          if owner == workbook}
            actions = [a for a in parsed.actions if not a.startswith("await h.signIn(")]
            scripted = parsed.compiled and not parsed.generic and bool(actions) and (
                bool(parsed.assertions) or not parsed.failure_path)
            when_text = " ".join(str(step.get("content") or "") for step in scenario.get("steps") or []
                                 if str(step.get("keyword") or "").upper() == "WHEN")
            then_text = " ".join(str(step.get("content") or "") for step in scenario.get("steps") or []
                                 if str(step.get("keyword") or "").upper() == "THEN")
            preceding_text = " ".join(str(step.get("content") or "") for step in scenario.get("steps") or []
                                      if str(step.get("keyword") or "").upper() in {"GIVEN", "WHEN"})
            def quoted(text: str) -> list[str]:
                return [literal_prefix((match.group(1) or match.group(2) or match.group(3)).strip())
                        for match in _ANY_LITERAL.finditer(text)]
            novel_outcomes = list(dict.fromkeys(value for value in quoted(then_text)
                                                if value and value not in quoted(preceding_text)
                                                and not TEMPLATE_TEXT.search(value)
                                                and not re.match(r"^[A-Z]{1,3}[1-9]\d*\s*=", value)
                                                and not _descriptive(value)))
            required_actions = ([] if not include_all or re.search(r"\sor\s", when_text, re.I) else [
                match.group(1) for match in re.finditer(
                    r"\b(?:clicks?|chooses?|selects?|presses?|activates?|opens?)\b[^.;]{0,70}?[“\"`]([^”\"`]+)[”\"`]",
                    when_text, re.I)])
            # "follows the visible controls for the X workflow" carries nothing a
            # proposal could act on; "the requested workflow" (templated tasks)
            # does: the operation is in the requirement text.
            if not include_all and (scripted or (parsed.generic and re.search(
                    r"follows?\s+the\s+visible\s+controls", when_text, re.I))):
                continue
            title = parsed.title if parsed.title.startswith(node_id) else f"{node_id}: {parsed.title}"
            steps = [f"{str(step.get('keyword') or '').upper()}: "
                     + " ".join(_sentences(step.get("content")))
                     for step in scenario.get("steps") or []]
            targets.append({"id": f"S{len(targets) + 1}", "node_id": node_id, "title": title,
                            "name": str(node.get("name") or ""),
                            "description": re.sub(r"\s+", " ", str(node.get("description") or ""))[:2600],
                            "steps": steps, "allowed": allowed, "seeds": parsed.seeds,
                            "required_actions": required_actions[:8],
                            "required_then_literal": (novel_outcomes[0] if include_all
                                                      and len(novel_outcomes) == 1 else ""),
                            "seed_kinds": parsed.seed_kinds,
                            "seed_cells": seed_cells, "seed_workbook": workbook,
                            "setup_cells": [cell for step in scenario.get("steps") or []
                                            if str(step.get("keyword") or "").upper() == "GIVEN"
                                            for cell in setup_cells(str(step.get("content") or ""))],
                            "contract_outcomes": contract_outcomes(str(node.get("description") or "")),
                            "semantic_contracts": semantic_contracts(steps),
                            "actor_precondition": ("team maintainer role has no proven fixture account"
                                                   if re.search(r"\bteam maintainer\b", " ".join(
                                                       step for step in steps if step.startswith("GIVEN:")), re.I)
                                                   else ""),
                            "dependency_literals": dependency_literals(node),
                            "controls": controls, "signed_in": parsed.signed_in,
                            "has_grid": bool(re.search(r"\bgrid\b|gridcell|\bcells?\b|worksheet|workbook|spreadsheet|"
                                                       r"\b[A-Z]{1,3}[0-9]{1,4}\s*=",
                                                       node_text + " " + shared + " " + " ".join(steps), re.I))})
            transition = transition_contract(targets[-1])
            if include_all and transition["kind"] and len(set(transition["literals"])) == 1:
                # A newly created name can occur in WHEN; a toast may be the
                # only novel THEN quote. Require the state value instead.
                targets[-1]["required_then_literal"] = transition["literals"][0]
            targets[-1]["negative_contracts"] = negative_contracts(targets[-1])
    if include_all:
        title_counts: dict[tuple[str, str], int] = {}
        for target in targets:
            key = (target["node_id"], target["title"])
            title_counts[key] = title_counts.get(key, 0) + 1
        for target in targets:
            if title_counts[(target["node_id"], target["title"])] > 1:
                target["title"] += f" [scenario {target['id']}]"
    return targets


def authentication_invariants(leaves: Iterable[Mapping], fixtures: Fixtures,
                              shared: str = "") -> list[dict]:
    """Bounded baseline contracts for an explicitly required password login.

    These are inferred safety properties, not verbatim requirement scenarios.
    Keep their origin visible and send them through the same independent audit.
    Passwordless/guest login and products without login get no such targets.
    """
    leaves = list(leaves)
    for node in leaves:
        description = str(node.get("description") or "")
        text = str(node.get("name") or "") + " " + description
        if not (re.search(r"\blog\s*in\b|\bsign[ -]?in\b|登录", text, re.I)
                and re.search(r"password|密码", description, re.I)):
            continue
        if re.search(r"passwordless|without (?:a )?password|guest|anonymous login|免密|游客", text, re.I):
            continue
        node_id = str(node.get("id"))
        controls = suite_controls(leaves, fixtures, shared)
        email_only = bool(re.search(r"email|邮箱", description, re.I) and not re.search(r"username|用户名", description, re.I))
        pairs = [("unregistered_account", "$UNKNOWN_EMAIL" if email_only else "$NEW_USERNAME", "$NEW_PASSWORD",
                  "An account that has not been registered cannot establish an authenticated session.")]
        existing_account = fixtures.email if email_only else fixtures.account
        if existing_account and fixtures.password:
            pairs.append(("wrong_password", existing_account, "$WRONG_PASSWORD",
                          "An existing account cannot establish an authenticated session with an incorrect password."))
        return [{"id": f"I-{kind}", "node_id": node_id,
                 "title": f"{node_id}: invariant {kind}", "name": str(node.get("name") or ""),
                 "description": description, "origin": "baseline_invariant",
                 "invariant_kind": kind, "invariant_credentials": [account, password],
                 "steps": ["GIVEN: A fresh anonymous browser; reset seed state; no registration in this case.",
                           f"WHEN: Attempt password login with `{account}` and `{password}`.",
                           "THEN: " + outcome],
                 "allowed": allowed_literals(node, fixtures), "controls": controls,
                 "signed_in": False, "seeds": [], "has_grid": False}
                for kind, account, password, outcome in pairs]
    return []


def prioritize_review_targets(targets: list[dict]) -> list[dict]:
    """Give every feature a first AI planning chance before extra scenarios."""
    first: list[dict] = []
    rest: list[dict] = []
    seen: set[str] = set()
    for target in targets:
        node_id = str(target["node_id"])
        (rest if node_id in seen else first).append(target)
        seen.add(node_id)
    return first + rest


def behavior_test_titles(source: str) -> set[str]:
    """Titles with an action followed by a behavioral assertion.

    Reach and entry smoke checks do not count, even if they are executable.
    This structural check is intentionally narrower than Playwright loading:
    loading proves syntax, while an assertion after an action provides at
    least a candidate for feature evidence.
    """
    starts = list(re.finditer(r"^test\('((?:\\.|[^'\\])*)',", source, re.M))
    valid: set[str] = set()
    for index, start in enumerate(starts):
        title = start.group(1).replace("\\'", "'")
        if not title.endswith((" [script]", " [model]")):
            continue
        end = starts[index + 1].start() if index + 1 < len(starts) else len(source)
        body = source[start.end():end]
        body = "\n".join(line for line in body.splitlines() if not re.search(r"test\.step\(['\"]setup:", line))
        action = re.search(r"await h\.(?!expect|openHome\(|signIn\(|watchResponse\()\w+\(", body)
        assertion = re.search(r"await h\.expect\w+\(", body)
        download = re.search(r"await h\.(?:expectDownload|expectSignInRejected)\(", body)
        if (action and assertion and action.start() < assertion.start()) or download:
            valid.add(title)
    return valid


def transition_contract(target: Mapping) -> dict:
    """Infer only explicit state transitions from the scenario's WHEN/THEN.

    This is deliberately format agnostic. A broad leaf description supplies
    the action only when the scenario has a templated WHEN; the THEN must still
    describe the corresponding result.
    """
    steps = [str(step) for step in target.get("steps") or []]
    when = " ".join(step for step in steps if step.startswith("WHEN:"))
    then = " ".join(step for step in steps if step.startswith("THEN:"))
    description = str(target.get("description") or "")
    templated_action = bool(re.search(r"requested workflow|visible controls", when, re.I))
    templated_outcome = bool(re.search(r"observable result for.*requested workflow", then, re.I))
    # A generic WHEN cannot turn a read-only scenario into a mutation merely
    # because its description mentions edits elsewhere. Leave ambiguous cases
    # to semantic review rather than imposing an invented commit button.
    action = when
    intent = " ".join(str(target.get(key) or "") for key in ("name", "title"))
    read_only_intent = (bool(re.match(r"\s*(?:view|open|display|inspect|read|browse|list)\b", intent, re.I))
                        and not re.search(r"(?:\band\b|[,/&])\s*(?:create|add|delete|remove|import|rename|edit|update|save)\b", intent, re.I))
    if templated_action and not read_only_intent:
        action = description
    # A display label such as "Last updated" is not an update command.
    action = re.sub(r"\blast[ -]updated\b", "", action, flags=re.I)
    outcome = description if templated_outcome else then
    candidates = []
    for name, action_words, result_words in (
            ("delete", r"delet\w*|remov\w*|discard\w*", r"delet\w*|remov\w*|absent|disappear\w*|no longer"),
            ("create", r"creat\w*|add\w*|insert\w*|import\w*", r"new|creat\w*|add\w*|insert\w*|appear\w*|listed|shows?"),
            ("update", r"renam\w*|updat\w*|edit(?:s|ed|ing)?|sav(?:e|es|ed|ing)",
             r"renam\w*|updat\w*|chang\w*|sav(?:e|es|ed|ing)|shows?|appear\w*")):
        if re.search(r"\b(?:" + action_words + r")\b", action, re.I) and re.search(
                r"\b(?:" + result_words + r")\b", outcome, re.I):
            candidates.append(name)
    kind = candidates[0] if len(candidates) == 1 else ""
    if kind == "update" and re.search(r"\b(?:successfully|toast|notice|notification|message)\b", outcome, re.I) \
            and not re.search(r"\b(?:renamed|updated|changed|new\s+value|appears)\b", outcome, re.I):
        kind = ""  # An explicitly promised notification is not a state contract.
    literals = []
    for match in _ANY_LITERAL.finditer(outcome):
        value = literal_prefix((match.group(1) or match.group(2) or match.group(3)).strip())
        nearby = outcome[max(0, match.start() - 28):match.start()] + " " + outcome[match.end():match.end() + 28]
        control_prefix = outcome[max(0, match.start() - 28):match.start()]
        control_suffix = outcome[match.end():match.end() + 18]
        if value and not _descriptive(value) and not re.search(
                r"\b(?:button|control|menuitem|menu|field|textbox|link|tab)\b[^.;]{0,28}$", control_prefix, re.I) and not re.search(
                r"^\s*(?:button|link|tab|control|menuitem|field|textbox)\b", control_suffix, re.I) and not re.search(
                r"\b(?:cannot be empty|required|invalid|failed|denied|forbidden)\b", value, re.I) and not re.search(
                r"\b(?:toast|notice|notification|message|error|success(?:fully)?)\b", nearby, re.I):
            literals.append(value)
    if templated_outcome:
        for match in re.finditer(r"\bnamed\s+([A-Za-z][\w-]*)\b", outcome, re.I):
            before = outcome[max(0, match.start() - 35):match.start()]
            if not re.search(r"\b(?:button|link|control|tab|menu|field|textbox)\b", before, re.I):
                literals.append(match.group(1))
    persistence = bool(re.search(
        r"(?:after|across|through|upon|on)\s+(?:a\s+)?(?:page\s+)?(?:refresh|reload|reopen)\b|"
        r"(?:persist|remain|surviv\w*).{0,80}\b(?:refresh|reload|reopen)\b",
        then + " " + description, re.I))
    return {"kind": kind, "literals": literals,
            "persistence": persistence}


def negative_contracts(target: Mapping) -> list[dict]:
    """Reproducible error paths explicitly named by the business requirement.

    Unsupported failure injection remains a gap rather than a fabricated test.
    The initial bounded trigger is a required text field submitted blank.
    """
    description = str(target.get("description") or "")
    preserved = next((value for kind, value in target.get("seed_kinds") or []
                      if re.search(r"\b(?:workbook|repository|team|record|document|project)\b", str(kind), re.I)), "")
    found = []
    for sentence in _sentences(description):
        if not re.search(r"\b(?:empty|blank|required)\b", sentence, re.I) or not re.search(
                r"\b(?:reject\w*|error|cannot be empty|must not be empty)\b", sentence, re.I):
            continue
        quoted = [m.group(1) or m.group(2) or m.group(3) for m in _ANY_LITERAL.finditer(sentence)]
        error = next((value for value in quoted if re.search(r"\b(?:cannot be empty|required|must not be empty)\b",
                                                              value, re.I)), "")
        if error:
            found.append({"kind": "blank_validation", "error": error, "preserved": preserved,
                          "testable": bool(preserved), "requirement_quote": sentence,
                          "persistence": bool(re.search(r'\b(?:refresh|reload|reopen)\b', sentence, re.I))})
    return found


def rejection_case_evidence(steps: list, contract: Mapping) -> bool:
    """A rejected command needs an error and the old business object intact."""
    if contract.get("kind") != "blank_validation" or not contract.get("testable"):
        return False
    blank_at = next((i for i, step in enumerate(steps) if isinstance(step, dict)
                     and step.get("op") == "fill" and step.get("value") == "$BLANK"), -1)
    commit_at = next((i for i, step in enumerate(steps) if i > blank_at and isinstance(step, dict)
                      and step.get("op") == "click" and _COMMIT_ACTION.search(str(step.get("target") or ""))), -1)
    if blank_at < 0 or commit_at < 0:
        return False
    old = contract['preserved']
    if not any(i < commit_at and isinstance(step, dict)
               and ((step.get('op') == 'open' and step.get('target') == old)
                    or (step.get('op') == 'expect_visible' and step.get('target') == old))
               for i, step in enumerate(steps)):
        return False
    if contract.get('persistence'):
        reload_at = next((i for i, step in enumerate(steps) if i > commit_at and isinstance(step, dict)
                          and (step.get('op') == 'reload'
                               or (step.get('op') == 'open' and step.get('target') == old))), -1)
        if reload_at < 0 or not any(i > reload_at and isinstance(step, dict)
                                  and step.get('op') == 'expect_visible' and step.get('target') == old
                                  for i, step in enumerate(steps)):
            return False
    return all(any(i > commit_at and isinstance(step, dict) and step.get("op") == "expect_visible"
                   and step.get("target") == value for i, step in enumerate(steps))
               for value in (contract["error"], contract["preserved"]))


def source_rejection_evidence(source: str, title: str, target: Mapping) -> bool:
    from test_policy import test_block
    block = test_block(source, title) or ""
    for contract in target.get("negative_contracts") or negative_contracts(target):
        if not contract.get("testable"):
            continue
        blank = re.search(r"await h\.fillField\(page,\s*'[^']+',\s*'   '\);", block)
        commit = re.search(r"await h\.clickNamed\(page,\s*'[^']*(?:Save|Create|Submit|Update|Rename)[^']*'\);",
                           block[blank.end():] if blank else "", re.I)
        if not blank or not commit:
            continue
        before = block[:blank.end()]
        old = _ts(contract['preserved'])
        if (f'await h.openNamed(page, {old});' not in before
                and f'await h.expectTextsVisible(page, [{old}]);' not in before):
            continue
        after = block[blank.end() + commit.end():]
        if contract.get('persistence'):
            reloads = [index for index in (after.find('await page.reload('),
                                            after.find(f'await h.openNamed(page, {old});')) if index >= 0]
            reload_at = min(reloads) if reloads else -1
            if reload_at < 0 or f'await h.expectTextsVisible(page, [{old}]);' not in after[reload_at:]:
                continue
        if all(f"await h.expectTextsVisible(page, [{_ts(value)}]);" in after
               for value in (contract["error"], contract["preserved"])):
            return True
    return False


_COMMIT_ACTION = re.compile(r"\b(?:create|add|delete|remove|discard|save|update|rename|confirm|apply|submit|import)\b", re.I)


def proposal_transition_problems(steps: list, target: Mapping) -> list[str]:
    """Require a changed-state witness after the decisive action, not UI chrome."""
    contract = transition_contract(target)
    kind = contract["kind"]
    if not kind or csv_format_contract(target) or csv_export_contract(target):
        return []
    selection = bool(re.search(r"\bselect\w*\b", str(target.get("description") or ""), re.I)
                     and re.search(r"aria-selected|complete selection|selected range",
                                   str(target.get("description") or ""), re.I))
    commits = [i for i, step in enumerate(steps) if isinstance(step, dict) and
               ((step.get("op") == "click" and _COMMIT_ACTION.search(str(step.get("target") or ""))) or
                (selection and step.get("op") == "cell_click") or
                (step.get("op") == "press" and step.get("key") in {"Enter", "Control+Enter"}))]
    if not commits:
        return [f"{kind} scenario has no commit action before its outcome assertion"]
    commit = commits[-1]
    assertions = [(i, step) for i, step in enumerate(steps) if i > commit and isinstance(step, dict)
                  and str(step.get("op") or "").startswith("expect_")]
    typed = {str(step.get("value") or "") for step in steps[:commit]
             if isinstance(step, dict) and step.get("op") in {"fill", "cell_type"}}
    seeded = {str(value) for value in target.get("seeds") or []}
    controls = {str(step.get("target") or "") for step in steps[:commit + 1]
                if isinstance(step, dict) and step.get("op") in {"open", "click", "check"}}
    outcome_values = set(contract["literals"]) | typed
    selected_target = str(steps[commit].get("target") or "") if steps[commit].get("op") == "cell_click" else ""
    if kind == "delete" and not contract["literals"]:
        outcome_values |= set(target.get("seeds") or [])
    if kind == "create" and any(isinstance(step, dict) and step.get("op") == "upload" for step in steps):
        outcome_values |= {"$CSV_NAME", "$CSV_FORMAT_NAME"}

    def witnesses(item: dict) -> bool:
        op, value = item.get("op"), str(item.get("target") or "")
        if kind == "delete":
            return op == "expect_absent" and value in outcome_values
        if selection and op == "expect_selected":
            return bool(selected_target and value == selected_target)
        if op in {"expect_cell", "expect_input_value"}:
            return str(item.get("value")) in outcome_values
        if op in {'expect_attribute', 'expect_count'}:
            return True  # candidate only; independent review must ground the specific state/count
        if op == 'expect_response' and type(item.get('status')) is int and 200 <= item['status'] < 300:
            return 'exact_json' in item or bool(item.get('json'))
        if op in {"expect_visible", "expect_role"}:
            return value in outcome_values and value not in seeded and value not in controls
        return False

    positive = [(i, item) for i, item in assertions if witnesses(item)]
    # A valid rejected-create branch still needs to prove no record was made.
    negative = any(rejection_case_evidence(steps, contract)
                   for contract in target.get("negative_contracts") or negative_contracts(target)) or (kind == "create" and any(item.get("op") == "expect_absent"
                 and str(item.get("target") or "") in typed - seeded for _, item in assertions)
                and any(item.get("op") in {"expect_visible", "expect_role"}
                        and str(item.get("target") or "") not in controls for _, item in assertions))
    negative = negative or (any(item.get('op') == 'expect_response_unchanged' for _, item in assertions)
        and any((item.get('op') == 'expect_response' and type(item.get('status')) is int and 400 <= item['status'] <= 499)
                or (item.get('op') == 'expect_visible' and item.get('target') not in controls | seeded)
                for _, item in assertions))
    if not positive and not negative:
        return [f"{kind} scenario needs a post-commit assertion of the created, changed, or removed state; "
                "an entry control, pre-existing seed, or toast alone is insufficient"]
    if contract["persistence"] and positive:
        reloads = [i for i, step in enumerate(steps) if i > commit and isinstance(step, dict)
                   and step.get("op") == "reload"]
        before = {(item.get("op"), item.get("target"), item.get("value"))
                  for i, item in positive if reloads and i < reloads[0]}
        after = {(item.get("op"), item.get("target"), item.get("value"))
                 for i, item in positive if reloads and i > reloads[0]}
        if not reloads or not after or (before and not before.intersection(after)):
            return ["the requirement says the changed state survives refresh/reopen; reload and assert it again"]
    return []


def source_transition_evidence(source: str, title: str, target: Mapping) -> bool:
    """Recheck the emitted (or mechanical) case before it can be reviewed."""
    contract = transition_contract(target)
    kind = contract["kind"]
    if not kind or csv_format_contract(target) or csv_export_contract(target):
        return True
    if source_rejection_evidence(source, title, target):
        return True
    from test_policy import test_block
    block = test_block(source, title) or ""
    selection = bool(re.search(r"\bselect\w*\b", str(target.get("description") or ""), re.I)
                     and re.search(r"aria-selected|complete selection|selected range",
                                   str(target.get("description") or ""), re.I))
    calls = [(m.start(), m.group(1), m.group(2)) for m in re.finditer(
        r"await h\.(\w+)\(([^;]*)\);", block)]
    commits = [i for i, name, args in calls if
               (name == "clickNamed" and _COMMIT_ACTION.search(args)) or
               (selection and name == "clickCell") or
               (name == "pressKey" and re.search(r"['\"](?:Enter|Control\+Enter)['\"]", args))]
    if not commits:
        return False
    commit = commits[-1]
    selected = next((args for i, name, args in calls if i == commit and name == "clickCell"), "")
    typed = {m.group(1) for m in re.finditer(
        r"await h\.(?:fillField|typeInCell)\(page,\s*'(?:\\.|[^'])*',\s*('(?:\\.|[^'])*')\);",
        block[:commit])}
    outcome = {_ts(value) for value in contract["literals"]} | typed
    if kind == "delete" and not contract["literals"]:
        outcome |= {_ts(part) for seed in target.get("seeds") or [] for part in seed_parts(seed)}
    if kind == "create" and "await h.uploadFile(" in block:
        outcome |= {_ts("derived-import"), _ts("derived-format")}
    seeded = {_ts(str(value)) for value in target.get("seeds") or []}
    clicked = {m.group(1) for m in re.finditer(
        r"await h\.(?:clickNamed|openNamed)\(page,\s*('(?:\\.|[^'])*')\);", block[:commit + 1])}
    positive = []
    negative = False
    for position, name, args in calls:
        if position <= commit:
            continue
        if kind == "delete" and name == "expectAbsent" and any(value in args for value in outcome):
            positive.append(position)
        elif selection and name == "expectSelected" and selected and args == selected:
            positive.append(position)
        elif kind != "delete" and name in {"expectTextsVisible", "expectRole"} and any(
                value in args and value not in seeded and value not in clicked for value in outcome):
            positive.append(position)
        elif kind != "delete" and name in {"expectCell", "expectInputValue"} and any(value in args for value in outcome):
            positive.append(position)
        elif kind != 'delete' and name in {'expectNamedAttribute', 'expectNamedCount'}:
            positive.append(position)
        elif kind != 'delete' and name == 'expectResponse' and re.search(r',\s*2[0-9]{2}\s*,', args) and (
                '"exact_json"' in args or re.search(r',\s*2[0-9]{2}\s*,\s*\{\s*"', args)):
            positive.append(position)
        elif kind == "create" and name == "expectAbsent" and any(value in args for value in typed - seeded):
            negative = True
    if any(name == 'expectResponseUnchanged' for i, name, _ in calls if i > commit) and any(
            (name == 'expectResponse' and re.search(r",\s*4[0-9]{2}\s*,", args)) or name in {'expectTextsVisible', 'expectRole'}
            for i, name, args in calls if i > commit):
        return True  # semantic review still verifies the specific rejection and unchanged business fields
    if not positive and not (negative and any(name in {"expectTextsVisible", "expectRole"}
                                           for i, name, _ in calls if i > commit)):
        return False
    if contract["persistence"] and positive:
        reload_at = block.find("await page.reload", commit)
        before = {(name, args) for i, name, args in calls if i in positive and i < reload_at}
        after = {(name, args) for i, name, args in calls if i in positive and i > reload_at}
        if reload_at < 0 or not after or (before and not before.intersection(after)):
            return False
    return True


def grounded_behavior_test(source: str, title: str, target: Mapping) -> bool:
    """Require the scenario's explicit actions and unique THEN literal in its test.

    This is a conservative check for claims the requirement states verbatim.
    Scenarios without such a literal still use the structural behavior check.
    """
    if title not in behavior_test_titles(source):
        return False
    if not source_transition_evidence(source, title, target):
        return False
    from test_policy import test_block
    format_block = test_block(source, title) or ""
    if (csv_format_contract(target) and "h.uploadFile(" in format_block
            and "'derived-invalid.csv'" not in format_block
            and not format_contract_evidence(source, title, target)):
        return False
    if (csv_export_contract(target) and "h.expectDownload(" in format_block
            and not format_contract_evidence(source, title, target)):
        return False
    if target.get("invariant_credentials"):
        account, password = target["invariant_credentials"]
        scope = re.sub(r" \[(?:model|script)\]$", "", title)
        account = expand_placeholder(account, scope)
        password = expand_placeholder(password, scope)
        block = test_block(source, title) or ""
        return f"h.expectSignInRejected(page, {_ts(account)}, {_ts(password)})" in block
    starts = list(re.finditer(r"^test\('((?:\\.|[^'\\])*)',", source, re.M))
    for index, start in enumerate(starts):
        if start.group(1).replace("\\'", "'") != title:
            continue
        end = starts[index + 1].start() if index + 1 < len(starts) else len(source)
        body = source[start.end():end]
        actions = list(re.finditer(r"await h\.(?!expect|openHome\(|signIn\()\w+\((.*?)\);", body, re.S))
        assertions = list(re.finditer(r"await h\.expect\w+\((.*?)\);", body, re.S))
        actions.extend(item for item in assertions if body[item.start():].startswith("await h.expectDownload("))
        actions.sort(key=lambda item: item.start())
        cursor = -1
        for required in target.get("required_actions") or []:
            action = next((item for item in actions if item.start() > cursor
                           and _ts(required) in item.group(1)), None)
            if action is None:
                return False
            cursor = action.start()
        if actions:
            cursor = max(cursor, actions[0].start())
        literal = "" if source_rejection_evidence(source, title, target) else target.get("required_then_literal")
        return not literal or any(item.start() >= cursor and _ts(literal) in item.group(1)
                                  for item in assertions)
    return False


def format_contract_evidence(source: str, title: str, target: Mapping) -> bool:
    """Exact data-format evidence, separate from a negative or entry case."""
    from test_policy import test_block
    block = test_block(source, title) or ""
    if csv_format_contract(target):
        if "'derived-format.csv'" not in block or "page.reload" not in block:
            return False
        if any(f"h.expectCell(page, {_ts(f'{chr(ord('A') + col)}{row}')}, {_ts(value)})" not in block
               for row, cells in enumerate(CSV_FORMAT_ROWS, 1) for col, value in enumerate(cells)):
            return False
        after_reload = block.split("page.reload", 1)[1]
        return all(f"h.expectCell(page, {_ts(ref)}, {_ts(value)})" in after_reload for ref, value in
                   (("A1", "Region"), ("D1", "第一行\n第二行"), ("E2", "中文")))
    if csv_export_contract(target):
        return bool(re.search(r"h\.expectDownload\([^;]+,\s*\[\[", block, re.S))
    return False


def positive_contract_evidence(source: str, title: str, literal: str) -> bool:
    """A required displayed outcome cannot be covered by its absence."""
    from test_policy import test_block
    block = test_block(source, title)
    if not block:
        return False
    action = re.search(r"await h\.(?!expect|openHome\(|signIn\()\w+\(", block)
    if not action:
        return False
    for match in re.finditer(r"await h\.(expectTextsVisible|expectRole|expectIdentity|expectCell|expectInputValue)\((.*?)\);", block, re.S):
        if match.start() <= action.start() or _ts(literal) not in match.group(2):
            continue
        if match.group(1) == "expectIdentity" and re.search(r",\s*false\s*$", match.group(2)):
            continue
        if match.group(1) in {"expectCell", "expectInputValue"} and not match.group(2).rstrip().endswith(_ts(literal)):
            continue
        return True
    return False


def compact_source_references(prompt: str, targets: list[dict]) -> str:
    """Lossless within-request references; never truncate or summarize evidence."""
    candidates = set()
    for target in targets:
        for key in ('description', 'controls', 'obligations', 'api_contracts', 'allowed',
                    'dependency_literals', 'contract_outcomes', 'semantic_contracts', 'negative_contracts', 'seed_cells'):
            value = target.get(key)
            if value:
                candidates.add(value if isinstance(value, str) else json.dumps(
                    value, ensure_ascii=False, sort_keys=(key == 'seed_cells')))
    prefix = '@@SOURCE_' + hashlib.sha256(prompt.encode()).hexdigest()[:16] + '_'
    while prefix in prompt:
        prefix += 'X'
    compact, sources = prompt, {}
    for value in sorted(candidates, key=lambda text: (-len(text), text)):
        marker = prefix + str(len(sources) + 1) + '@@'
        count = compact.count(value)
        if len(value) >= 80 and count >= 2 and count * (len(value) - len(marker)) > len(
                json.dumps({marker: value}, ensure_ascii=False)):
            compact = compact.replace(value, marker)
            sources[marker] = value
    if not sources:
        return prompt
    restored = re.sub(re.escape(prefix) + r'\d+@@', lambda match: sources[match[0]], compact)
    if restored != prompt:
        raise ValueError('source reference expansion changed evidence')
    result = compact + '\nEXACT SOURCE TABLE (expand references before interpreting evidence):\n' + json.dumps(
        sources, ensure_ascii=False)
    return result if len(result) < len(prompt) else prompt


def build_prompt(targets: list[dict], fixtures: Fixtures, phase_context: str = "") -> str:
    parts = ["Plan and write one behavioural check per scenario below, as JSON: "
             "{\"scenarios\": [ ... ]}. Each check must perform the WHEN operation and verify the "
             "observable THEN outcome; merely finding an entry control is a smoke check, not feature evidence. "
             "Use skip with a concrete reason if the requirement cannot ground a sound check.\n" + DSL]
    parts.append("\nCheck basic invariants as separate isolated cases when supported by this scenario's contract: "
                 "required fields reject missing input; cancel preserves saved data; reload preserves committed changes; "
                 "failed actions do not create or mutate records; protected resources enforce the stated access rules. "
                 "Cover both valid and invalid branches. Establish all prerequisites in each case and assert the resulting "
                 "state, not just a toast. Do not invent error wording, validation limits, roles, routes or product policies. "
                 "If a prerequisite or oracle cannot be established with this DSL and these fixtures, report a concrete gap.")
    parts.append("\nFor every state-changing workflow, identify the commit action and prove the promised state afterwards: "
                 "a created record or value exists, a deleted one is absent, or an edited value actually changed. "
                 "Observing a dialog, clicked button, existing seed, field echo, or success toast is insufficient. "
                 "If the requirement promises persistence across refresh or reopen, reload and repeat the state assertion. "
                 "For a rejected operation, verify both the rejection and that no unintended state change occurred.")
    parts.append("\nTreat explicitly specified data formats as exact contracts: use the stated field order, empty fields, "
                 "quoting/escaping, Unicode, filename, error text, accessible role/name and calculated values. "
                 "Check the resulting parsed data or named cell/field after the action and after reload where persistence "
                 "is required. A file suffix, source label, toast, or one substring does not prove a complete format. "
                 "For ordinary workflows also check one relevant boundary or opposite branch when the requirement "
                 "supports it; keep each case isolated and do not invent product rules.")
    parts.append('\nFor a prerequisite enum/limit from another requirement, add source_values '
                 '[{value,requirement_id,quote}] with an exact quote containing the value from SOURCE CONTRACTS. '
                 'Do not invent controls, enum options or error messages. For arbitrary inputs use test_data instead.')
    parts.append(f"\nFixture account: `{fixtures.account}` / `{fixtures.password}` (email `{fixtures.email}`).")
    parts.append('\nMark steps with phase setup/action/assertion. Setup cannot earn behavior credit. '
                 'Use a real command and a changed-state assertion; preserve exact raw values, empty fields and boundaries. '
                 'Each category needs a successful chain and an applicable rejection chain before extra entry checks. '
                 'Read writes back through the normal UI, reload and another actor where required. '
                 'Optional watch_response {target:path,method:METHOD} before the UI action and '
                 'expect_response {target:path,status:integer,json:optional-object-subset} afterward supplement UI assertions. '
                 'Only declared API paths are allowed; expected status/body must follow the branch requirement.')
    if phase_context:
        parts.append("\nTOP-LEVEL CATEGORY CONTRACT (shared context for these scenarios; "
                     "each assertion must still be grounded in its own scenario): " + phase_context)
    shared_sources: dict[str, str] = {}
    for target in targets:
        source = target.get('source_contracts')
        if isinstance(source, Mapping):
            for requirement_id, description in source.items():
                shared_sources[str(requirement_id)] = str(description)
    if shared_sources:
        parts.append("\nSOURCE CONTRACTS (original YAML descriptions for dependency source_values; "
                     "each scenario may cite only its listed SOURCE CONTRACT IDS): "
                     + json.dumps(shared_sources, ensure_ascii=False))
    for target in targets:
        source = target.get('source_contracts')
        if isinstance(source, Mapping) and source:
            parts.append(f"\nSOURCE CONTRACT IDS for [{target['id']}]: "
                         + json.dumps(list(source), ensure_ascii=False))
        elif source:
            # Legacy callers may supply a list of source excerpts.
            parts.append(f"\nSOURCE CONTRACTS for [{target['id']}]: "
                         + json.dumps(source, ensure_ascii=False))
        controls = [c for c in (target.get("controls") or []) if len(c) <= 60][:160]
        if controls:
            parts.append(f"\nCONTROLS for [{target['id']}] (named in this requirement; "
                         "usable as open/click/check/fill targets): "
                         + json.dumps(controls, ensure_ascii=False))
        if target.get('obligations'):
            parts.append("\nSOURCE-GROUNDED OBLIGATIONS (cover independent branches in separate cases): "
                         + json.dumps(target['obligations'], ensure_ascii=False))
        if target.get("api_contracts"):
            parts.append("\nDECLARED API CONTRACTS: " + json.dumps(target["api_contracts"], ensure_ascii=False))
        if target.get("origin") == "baseline_invariant":
            parts.append("\nBASELINE INVARIANT (inferred from the required password login, not a quoted scenario). "
                         "Use exactly one expect_sign_in_rejected step with target/value "
                         + json.dumps(target["invariant_credentials"]) +
                         "; signed_in=false. Do not register an account or assert an invented error message.")
        parts.append(f"\n### [{target['id']}] {target['title']}\nRequirement {target['node_id']} ({target['name']}): "
                     f"{target['description']}\n" + "\n".join(target["steps"]) +
                     ("\nCANONICAL SEED CELLS (before scenario setup; preserve row coordinates through edits): "
                      + json.dumps(target["seed_cells"], ensure_ascii=False, sort_keys=True)
                      if target.get("seed_cells") else "") +
                     "\nALLOWED LITERALS: " + json.dumps(target["allowed"], ensure_ascii=False)
                     + "\nDEPENDENCY LITERALS (value -> requirement IDs): "
                     + json.dumps(target.get("dependency_literals") or {}, ensure_ascii=False)
                     + "\nCONTRACT OUTCOMES (cover in separate cases where conditional): "
                     + json.dumps(target.get("contract_outcomes") or [], ensure_ascii=False)
                     + "\nSEMANTIC OUTCOMES (each needs action and proof in one independent case): "
                     + json.dumps(target.get("semantic_contracts") or [], ensure_ascii=False)
                     + "\nNEGATIVE BUSINESS BRANCHES (cover each reproducible branch in an isolated case; "
                       "if testable=false, report the missing trigger or fixture rather than inventing it): "
                     + json.dumps(target.get("negative_contracts") or [], ensure_ascii=False)
                     + ("\nUNVERIFIED GIVEN ACTOR: " + target["actor_precondition"]
                        + "; use skip or a grounded validator dispute, not a different account."
                        if target.get("actor_precondition") else ""))
    return compact_source_references("\n".join(parts), targets)


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


def parse_failure_review(text: str) -> dict | None:
    """Read one structured test-failure verdict and its proposed scenarios."""
    decoder = json.JSONDecoder()
    source = str(text or "")
    for start in (match.start() for match in re.finditer(r"\{", source)):
        try:
            value, _ = decoder.raw_decode(source[start:])
        except json.JSONDecodeError:
            continue
        if (isinstance(value, dict)
                and value.get("verdict") in {"app_error", "spec_error", "oracle_dispute", "uncertain"}
                and isinstance(value.get("evidence"), str)):
            scenarios = value.get("scenarios", [])
            if isinstance(scenarios, list):
                return {**value, "scenarios": scenarios}
    return None


def _emit(step: dict) -> str | None:
    if step["op"] == "watch_response":
        return f"await h.watchResponse(page, {_ts(step['target'])}, {_ts(step['method'])});"
    if step["op"] == "expect_response":
        contract = {k: step[k] for k in ('schema', 'exact_json') if k in step}
        return f"await h.expectResponse(page, {_ts(step['target'])}, {step['status']}, {json.dumps(step.get('json', {}), ensure_ascii=False)}, {json.dumps(contract, ensure_ascii=False)});"
    op, target = step.get("op"), step.get("target")
    if op == 'drag':
        role = step.get('role') or ('gridcell' if CELL.fullmatch(str(target)) and CELL.fullmatch(str(step.get('destination'))) else None)
        suffix = f", {_ts(role)}" if role else ""
        return f"await h.dragNamed(page, {_ts(target)}, {_ts(step['destination'])}{suffix});"
    if op == 'expect_count':
        return f"await h.expectNamedCount(page, {_ts(step['role'])}, {_ts(target)}, {step['count']});"
    if op == 'expect_attribute':
        return f"await h.expectNamedAttribute(page, {_ts(step['role'])}, {_ts(target)}, {_ts(step['attribute'])}, {_ts(step['value'])});"
    if op == 'upload_fixture':
        return f"await h.uploadFile(page, {_ts(target)}, {_ts(step['content'])}, {_ts(step['filename'])}, {_ts(step['mime'])});"
    if op == "open":
        if HOME_TARGET.match(str(target).strip()):
            return "await h.openHome(page);"
        return f"await h.openNamed(page, {_ts(target)});"
    if op == "click":
        return f"await h.clickNamed(page, {_ts(target)});"
    if op == "hover":
        return f"await h.hoverNamed(page, {_ts(target)});"
    if op == "expect_input_value":
        return f"await h.expectInputValue(page, {_ts(target)}, {_ts(str(step.get('value')))});"
    if op == "select_option":
        return f"await h.selectOption(page, {_ts(target)}, {_ts(str(step.get('value')))});"
    if op == "snapshot_response":
        return f"await h.snapshotResponse(page, {_ts(target)}, {_ts(step['key'])});"
    if op == "expect_response_unchanged":
        return f"await h.expectResponseUnchanged(page, {_ts(target)}, {_ts(step['key'])});"
    if op == "fill":
        return f"await h.fillField(page, {_ts(target)}, {_ts(str(step.get('value')))});"
    if op == "reload":
        return "await page.reload({ waitUntil: 'domcontentloaded' });"
    if op == "sign_in":
        return f"await h.signIn(page, {_ts(target)}, {_ts(str(step.get('value')))});"
    if op == "expect_sign_in_rejected":
        return f"await h.expectSignInRejected(page, {_ts(target)}, {_ts(str(step.get('value')))});"
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
    if op == "cell_context":
        return f"await h.contextClickCell(page, {_ts(target)});"
    if op == "header_context":
        return f"await h.contextClickHeader(page, {_ts(target)});"
    if op == "expect_selected":
        return f"await h.expectSelected(page, {_ts(target)});"
    if op == "upload":
        csv = str(step.get("csv") or "").replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
        if step.get("value") == "$INVALID_CSV":
            return f"await h.uploadFile(page, {_ts(target)}, '{csv}', 'derived-invalid.csv');"
        if step.get("value") == "$CSV_FORMAT":
            return f"await h.uploadFile(page, {_ts(target)}, '{csv}', 'derived-format.csv');"
        return f"await h.uploadFile(page, {_ts(target)}, '{csv}');"
    if op == "expect_download":
        content = step.get("contains") or []
        rows = step.get("csv_rows")
        contract = {k: step[k] for k in ('schema', 'exact_json', 'exact_text') if k in step}
        exact = ", " + (json.dumps(rows, ensure_ascii=False) if isinstance(rows, list) else "undefined") if contract or isinstance(rows, list) else ""
        if contract:
            exact += ", " + json.dumps(contract, ensure_ascii=False)
        return (f"await h.expectDownload(page, {_ts(target)}, {_ts(str(step.get('value')))}, "
                f"[{', '.join(_ts(item) for item in content)}]{exact});")
    if op == "expect_clipboard":
        return f"await h.expectClipboard(page, {_ts(target)}, {_ts(str(step.get('protocol')))});"
    return None


def public_display_literal(target: Mapping, value: str) -> bool:
    for sentence in _sentences(target.get("description") or ""):
        if (value in [(m.group(1) or m.group(2) or m.group(3)).strip() for m in _ANY_LITERAL.finditer(sentence)]
                and re.search(r"show|display|visible|reveal", sentence, re.I)
                and not re.search(r"(?:not|never)\s+(?:(?:be|directly|visibly|publicly)\s+)*(?:show|display|reveal|visible)", sentence, re.I)
                and re.search(r"verification[-\s]+code|fixed[-\s]+code|one.time\s+code|\bpin\b", sentence, re.I)):
            return True
    return False


def identity_transition(steps: list, index: int, step: Mapping, fixtures: Fixtures, signed_in: bool = False) -> bool:
    if step.get("op") not in {"expect_visible", "expect_absent"} or not fixtures.account:
        return False
    if str(step.get("target") or "").strip().lower() != fixtures.account.lower():
        return False
    prior = [item for item in steps[:index] if isinstance(item, dict)]
    if step["op"] == "expect_visible" and signed_in and any(
            item.get("op") == "click" and re.fullmatch(r"cancel", str(item.get("target") or ""), re.I)
            for item in prior) and any(item.get("op") == "click" and re.fullmatch(
                r"sign\s*out|log\s*out", str(item.get("target") or ""), re.I) for item in prior):
        return not any(item.get("op") == "click" and re.fullmatch(
            r"confirm\s+(?:sign\s*out|log\s*out)", str(item.get("target") or ""), re.I) for item in prior)
    action = r"^(?:sign\s*in|log\s*in)$" if step["op"] == "expect_visible" else r"^(?:sign\s*out|log\s*out|confirm\s+(?:sign\s*out|log\s*out))$"
    if not any(item.get("op") == "click" and re.match(action, str(item.get("target") or ""), re.I) for item in prior):
        return False
    if step["op"] == "expect_absent":
        return signed_in or any(item.get("op") == "click" and re.match(r"^(?:sign\s*in|log\s*in)$", str(item.get("target") or ""), re.I)
                                for item in prior)  # Hide a previously authenticated identity, not stored data.
    return any(item.get("op") == "fill" and str(item.get("value") or "").strip() in {fixtures.account, fixtures.email}
               and re.search(r"username|email|login", str(item.get("target") or ""), re.I) for item in prior)


def signed_out_entry_transition(steps: list, index: int, step: Mapping, target: Mapping,
                                signed_in: bool = False) -> bool:
    """A requirement-grounded sign-in LINK after terminating a session."""
    if step.get("op") != "expect_visible" or not re.fullmatch(r"sign\s*in|log\s*in", str(step.get("target") or ""), re.I):
        return False
    description = str(target.get("description") or "")
    value = re.escape(str(step['target']))
    if not re.search(r'(?:displays?|shows?)\s+(?:the\s+)?[“"`]' + value + r'[”"`]\s+link\b', description, re.I):
        return False
    prior = [item for item in steps[:index] if isinstance(item, dict)]
    ending = r'^confirm\s+(?:sign\s*out|log\s*out)$' if re.search(r'confirm\s+(?:sign\s*out|log\s*out)', description, re.I) else r'^(?:sign\s*out|log\s*out)$'
    ended_at = next((i for i, item in reversed(list(enumerate(prior)))
                     if item.get('op') == 'click' and re.match(ending, str(item.get('target') or ''), re.I)), None)
    return ended_at is not None and (signed_in or any(
        item.get('op') == 'click' and re.fullmatch(r'sign\s*in|log\s*in', str(item.get('target') or ''), re.I)
        for item in prior[:ended_at]))


def _seeded_column_oracle_problems(steps: list, target: Mapping) -> list[str]:
    """Reject assertions contradicted by a known seed after a column edit.

    The generated case may choose a column, but inserting one cannot move a
    seeded value to a different row. This check uses only placed seed cells;
    unknown cells and formula results remain outside its oracle.
    """
    cells = {str(ref): str(value) for ref, value in (target.get("seed_cells") or {}).items()}
    if not cells:
        return []
    header: str | None = None
    shifted = False
    problems: list[str] = []
    column_actions = {"Insert 1 column left", "Insert 1 column right", "Delete column"}
    for index, step in enumerate(steps):
        if not isinstance(step, Mapping):
            continue
        op = step.get("op")
        ref = str(step.get("target") or "").strip().upper()
        # After an unrelated action, the seeded grid may have changed in ways
        # this narrow column model cannot prove. Keep already found errors.
        if (shifted and op not in {"expect_cell", "expect_visible", "expect_absent", "reload", "header_context"}
                and not (op == "click" and header and step.get("target") in column_actions)):
            break
        known_entry = (op == "click" and not shifted and index == 0
                       and step.get("target") == target.get("seed_workbook"))
        column_click = op == "click" and header and step.get("target") in column_actions
        if (op not in {"cell_type", "header_context", "expect_cell", "expect_visible", "expect_absent", "reload"}
                and not known_entry and not column_click
                and not (op == "press" and step.get("key") == "Enter")):
            break
        if op == "cell_type" and CELL.fullmatch(ref):
            cells[ref] = str(step.get("value") or "")
        elif op == "header_context":
            header = ref if re.fullmatch(r"[A-Z]+", ref) else None
        elif op == "click" and header and step.get("target") in column_actions:
            action = step["target"]
            at = 0
            for char in header:
                at = at * 26 + ord(char) - 64
            moved: dict[str, str] = {}
            for cell, value in cells.items():
                match = re.fullmatch(r"([A-Z]+)([1-9]\d*)", cell)
                if not match:
                    continue
                column = 0
                for char in match.group(1):
                    column = column * 26 + ord(char) - 64
                if action == "Delete column" and column == at:
                    continue
                if ((action == "Insert 1 column left" and column >= at)
                        or (action == "Insert 1 column right" and column > at)):
                    column += 1
                elif action == "Delete column" and column > at:
                    column -= 1
                letters = ""
                while column:
                    column, digit = divmod(column - 1, 26)
                    letters = chr(65 + digit) + letters
                moved[letters + match.group(2)] = value
            cells = moved
            shifted = True
            header = None
        elif op == "expect_cell" and shifted and ref in cells:
            known = cells[ref]
            claimed = str(step.get("value") or "")
            if known and not known.startswith("=") and claimed != known:
                problems.append(f"step {index}: after the column operation seeded {ref} should be "
                                f"{known!r}, not {claimed!r}; preserve its original row")
    return problems


def generated_values(proposal: Mapping) -> dict[str, str]:
    data = proposal.get("test_data", {})
    if not isinstance(data, dict) or len(data) > 24:
        raise ValueError("test_data must be an object with at most 24 named values")
    result = {}
    for key, item in data.items():
        if not re.fullmatch(r"\$DATA_[A-Z0-9_]{1,40}", str(key)) or not isinstance(item, dict):
            raise ValueError("test data keys must be $DATA_NAME objects")
        value, kind = item.get("value"), item.get("type")
        valid = ((kind == "string" and isinstance(value, str)) or
                 (kind == "number" and type(value) in (int, float) and __import__('math').isfinite(value)) or
                 (kind == "boolean" and type(value) is bool))
        if not valid or len(str(value)) > 4096:
            raise ValueError("test data requires a finite typed string/number/boolean value <=4096 characters")
        result[key] = value if isinstance(value, str) else json.dumps(value)
    return result


def sourced_values(proposal: Mapping, target: Mapping) -> set[str]:
    """Explicit dependency enum/limit values must cite original descriptions."""
    items = proposal.get('source_values', [])
    if not isinstance(items, list) or len(items) > 32:
        raise ValueError('source_values must be an array of at most 32 source citations')
    values = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('source_values requires value, requirement_id and quote')
        value, quote, owner = (item.get(k) for k in ('value', 'quote', 'requirement_id'))
        if (not isinstance(value, str) or not value or len(value) > 4096
                or not isinstance(quote, str) or len(quote.strip()) < 12
                or not isinstance(owner, str) or value not in quote
                or quote not in (target.get('source_contracts') or {}).get(owner, '')):
            raise ValueError('source_values must quote an original requirement containing the exact value')
        values.add(value)
    return values


def proposal_problems(proposal: Mapping, target: Mapping, fixtures: Fixtures) -> list[str]:
    """Every rule the proposal breaks, worded so the model can fix it."""
    problems: list[str] = []
    try:
        data_values = generated_values(proposal)
        dependency_values = sourced_values(proposal, target)
    except ValueError as exc:
        return [str(exc)]
    if proposal.get("validator_dispute"):
        dispute = proposal["validator_dispute"]
        if (isinstance(dispute, dict) and isinstance(dispute.get("requirement_quote"), str)
                and len(dispute["requirement_quote"].strip()) >= 12
                and dispute["requirement_quote"] in str(target.get("description") or "")
                and isinstance(dispute.get("reason"), str) and dispute["reason"].strip()):
            return ["validator_dispute (unresolved, not quarantined): " + json.dumps(dispute, ensure_ascii=False)]
        return ["validator_dispute lacks a verbatim requirement quote and concrete reason"]
    if proposal.get("skip"):
        return [f"skipped by the model: {proposal.get('skip')}"]
    try:
        confidence = float(proposal.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < MIN_CONFIDENCE:
        problems.append(f"confidence {confidence:.2f} is below {MIN_CONFIDENCE}")
    steps = proposal.get("steps")
    if target.get("actor_precondition"):
        return problems + ["unverified GIVEN actor: " + str(target["actor_precondition"])]
    if not isinstance(steps, list) or not steps:
        return problems + ["no steps"]
    problems.extend(_seeded_column_oracle_problems(steps, target))
    explicit_phases = any(isinstance(step, dict) and "phase" in step for step in steps)
    if explicit_phases:
        if any(step.get("phase") not in {"setup", "action", "assertion"} for step in steps if isinstance(step, dict)):
            problems.append("every step needs setup/action/assertion phase when phases are used")
        action_indices = [i for i, step in enumerate(steps) if isinstance(step, dict) and step.get("phase") == "action"
                          and step.get("op") not in ({"open", "reload", "hover", "watch_response"}
                              if transition_contract(target)['kind'] else {"hover", "watch_response", "snapshot_response"})
                          and not str(step.get("op", "")).startswith("expect_")]
        if not action_indices or not any(i > min(action_indices) and step.get("phase") == "assertion"
                and str(step.get("op", "")).startswith("expect_") for i, step in enumerate(steps) if isinstance(step, dict)):
            problems.append("setup-only scripts have no behavior credit; require action then outcome assertion")
    max_steps = MAX_STEPS
    if len(steps) > max_steps:
        problems.append(f"{len(steps)} steps; at most {max_steps}")
    if target.get("invariant_credentials"):
        account, password = target["invariant_credentials"]
        if proposal.get("signed_in") or steps != [{"op": "expect_sign_in_rejected", "target": account, "value": password}]:
            problems.append("baseline login invariant requires exactly its anonymous credential rejection step")
    typed_at: dict[str, int] = {}
    for index, step in enumerate(steps):
        if isinstance(step, dict) and step.get("op") == "cell_type":
            typed_at.setdefault(str(step.get("target") or "").strip().upper(), index)
    for ref, value in target.get("setup_cells") or []:
        if ref not in typed_at:
            problems.append(f"the GIVEN scenario setup enters {value!r} in {ref}: start with cell_type {ref} "
                            f"{value!r} + press Enter (it is not seed data)")
            continue
        early = next((index for index, step in enumerate(steps) if isinstance(step, dict)
                      and step.get("op") == "expect_cell" and str(step.get("target") or "").strip().upper() == ref
                      and index < typed_at[ref]), None)
        if early is not None:
            problems.append(f"expect_cell {ref} before the scenario setup typed it; type the setup values first")
    action_steps = [(index, str(step.get("target") or "")) for index, step in enumerate(steps)
                    if isinstance(step, dict) and step.get("op") in {"open", "click", "check", "expect_download"}]
    cursor = -1
    for required in target.get("required_actions") or []:
        found = next((index for index, value in action_steps if index > cursor and value == required), None)
        if found is None:
            problems.append(f"WHEN requires acting on {required!r} in order before asserting the result")
        else:
            cursor = found
    allowed = set(target["allowed"]) | set(target.get("seeds") or []) | set(target.get("dependency_literals") or {})
    # A seeded row `East/1200` is shown as its parts once imported or listed.
    for seed in target.get("seeds") or []:
        if "/" in seed and seed.count("/") <= 3:
            allowed |= {part.strip() for part in seed.split("/") if len(part.strip()) >= 3}
    allowed |= dependency_values
    controls = allowed | set(target.get("controls") or [])
    allowed |= set(data_values)

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
    uploaded_format = False
    uploaded_invalid = False
    any_invalid_upload = False
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
        if not isinstance(step, dict) or not isinstance(step.get('op'), str) or step.get("op") not in OPS:
            problems.append(f"step {index}: unknown op {json.dumps(step.get('op') if isinstance(step, dict) else step)}; "
                            f"use one of {sorted(OPS)}")
            continue
        op = step["op"]
        if op in {'drag', 'expect_count', 'expect_attribute', 'upload_fixture'}:
            cell_drag = op == 'drag' and bool(CELL.fullmatch(str(step.get('target'))) and CELL.fullmatch(str(step.get('destination'))))
            if op == 'drag' and step.get('role') is not None and step['role'] not in ROLES:
                problems.append(f"step {index}: invalid drag accessible role")
            if not is_control(step.get('target')) and not cell_drag:
                problems.append(f"step {index}: target must be a requirement-grounded name")
            if op == 'drag' and not is_control(step.get('destination')) and not cell_drag:
                problems.append(f"step {index}: drag destination must be a requirement-grounded name")
            if op in {'expect_count', 'expect_attribute'} and (not isinstance(step.get('role'), str) or step.get('role') not in ROLES):
                problems.append(f"step {index}: invalid accessible role")
            if op == 'expect_count' and (type(step.get('count')) is not int or not 0 <= step['count'] <= 10000):
                problems.append(f"step {index}: count must be a bounded nonnegative integer")
            if op == 'expect_attribute' and (step.get('attribute') not in (
                    'aria-selected', 'aria-multiselectable', 'aria-checked', 'aria-expanded', 'aria-disabled', 'disabled', 'data-status')
                    or not isinstance(step.get('value'), str)):
                problems.append(f"step {index}: attribute must be an explicit supported state attribute")
            if op == 'upload_fixture':
                if not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]{0,79}', str(step.get('filename', ''))):
                    problems.append(f"step {index}: invalid fixture filename")
                if not re.fullmatch(r'[a-z0-9.+-]+/[a-z0-9.+-]+', str(step.get('mime', ''))):
                    problems.append(f"step {index}: invalid fixture MIME type")
                if not isinstance(step.get('content'), str) or len(step['content']) > 32000:
                    problems.append(f"step {index}: fixture content must be a UTF-8 string up to 32000 characters")
            asserted = asserted or op.startswith('expect_')
            continue
        if 'schema' in step and (op not in {'expect_response', 'expect_download'} or not valid_json_schema(step['schema'])):
            problems.append(f"step {index}: unsupported JSON schema; use type/enum/required/properties/items/additionalProperties")
        if 'exact_text' in step and (op != 'expect_download' or not isinstance(step['exact_text'], str)):
            problems.append(f"step {index}: exact_text must be a string download oracle")
        if any(len(json.dumps(step.get(key), ensure_ascii=False)) > 12000 for key in ('schema', 'exact_json', 'exact_text')):
            problems.append(f"step {index}: format oracle exceeds 12000 characters")
        if op in {"watch_response", "expect_response", "snapshot_response", "expect_response_unchanged"}:
            route = step.get("target")
            declared = [r for r in target.get("api_contracts", []) if r.get("path") == route]
            if not declared:
                problems.append(f"step {index}: response path must have a declared API contract")
            if op == "watch_response" and not any(r.get("method") == step.get("method") for r in declared):
                problems.append(f"step {index}: response method must match the declared route")
            if op in {"snapshot_response", "expect_response_unchanged"}:
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", str(step.get("key", ""))):
                    problems.append(f"step {index}: snapshot key must be a short identifier")
                earlier = steps[:index - 1]
                snapshots = [i for i, s in enumerate(earlier) if isinstance(s, dict)
                             and s.get("op") == "snapshot_response" and s.get("key") == step.get("key")
                             and s.get("target") == route]
                if op == "expect_response_unchanged" and not snapshots:
                    problems.append(f"step {index}: unchanged assertion requires a prior same-route snapshot")
                after = snapshots[-1] + 1 if op == "expect_response_unchanged" and snapshots else 0
                watchers = [s for s in earlier[after:] if isinstance(s, dict) and
                            s.get('op') == 'watch_response' and s.get('target') == route]
                if not watchers or watchers[-1].get('method') != 'GET':
                    problems.append(f"step {index}: snapshot requires a fresh watched GET response")
                asserted = asserted or op == "expect_response_unchanged"
            if op == "expect_response":
                earlier = steps[:index - 1]
                if not any(s.get("op") == "watch_response" and s.get("target") == route for s in earlier if isinstance(s, dict)):
                    problems.append(f"step {index}: watch the response before triggering its action")
                if type(step.get("status")) is not int or not 100 <= step["status"] <= 599:
                    problems.append(f"step {index}: invalid response status")
                if not isinstance(step.get("json", {}), dict):
                    problems.append(f"step {index}: json must be an object subset")
                asserted = True
            continue
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
        if op == "reload":
            if step.get("target") not in (None, "") or step.get("value") not in (None, ""):
                problems.append(f"step {index}: reload takes no target or value")
            continue
        if op in {"sign_in", "expect_sign_in_rejected"}:
            value = step.get("target")
            if not isinstance(value, str) or value.strip() not in (allowed | {"$NEW_USERNAME", "$NEW_EMAIL", "$UNKNOWN_EMAIL"}):
                problems.append(f"step {index}: {op} target must be a seeded account/email or account placeholder")
            password = step.get("value")
            password_values = allowed | {"$NEW_PASSWORD"}
            if op == "expect_sign_in_rejected":
                password_values.add("$WRONG_PASSWORD")
            if not isinstance(password, str) or password.strip() not in password_values:
                problems.append(f"step {index}: {op} password must be a seeded or new password")
            if op == "sign_in" and value == "$UNKNOWN_EMAIL":
                problems.append(f"step {index}: unknown email cannot be a successful sign-in fixture")
            if value in {"$NEW_USERNAME", "$NEW_EMAIL"} and op == "sign_in" and not any(
                    isinstance(previous, dict) and previous.get("op") == "fill"
                    and previous.get("value") == value for previous in steps[:index - 1]):
                problems.append(f"step {index}: sign_in uses {value} before this case registered it")
            asserted = asserted or op == "expect_sign_in_rejected"
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
                imported_values = {item for row in uploaded_csv or [] for item in row} if op == "expect_cell" else set()
                if not isinstance(typed, str) or not (typed.strip() in allowed or typed in imported_values
                                                      or typed.strip() in PLACEHOLDERS
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
            upload_value = str(step.get("value") or "").strip()
            if upload_value == "$CSV":
                uploaded_csv = list(csv.reader(io.StringIO(seed_csv(target.get("seeds") or []), newline="")))
                uploaded = True
                uploaded_format = False
                uploaded_invalid = False
                edited_cells.clear()
            elif upload_value == "$CSV_FORMAT":
                if not (csv_format_contract(target) or csv_export_contract(target)):
                    problems.append(f"step {index}: $CSV_FORMAT needs an explicit CSV import or export format contract")
                uploaded_csv = CSV_FORMAT_ROWS
                uploaded = True
                uploaded_format = True
                uploaded_invalid = False
                edited_cells.clear()
            elif upload_value == "$INVALID_CSV":
                contract = str(target.get("description") or "") + " " + " ".join(
                    map(str, target.get("steps") or []))
                if not re.search(r"invalid\s+CSV|unclosed\s+(?:double\s+)?quote|no\s+closing\s+double\s+quote",
                                 contract, re.I):
                    problems.append(f"step {index}: invalid CSV fixture is not authorized by this requirement")
                if "Invalid CSV file format. Import failed." not in contract:
                    problems.append(f"step {index}: the fixed invalid CSV error oracle is not in this requirement")
                uploaded_csv = None
                uploaded = False
                uploaded_format = False
                uploaded_invalid = True
                any_invalid_upload = True
            else:
                problems.append(f"step {index}: upload value must be $CSV, $CSV_FORMAT or an authorized $INVALID_CSV")
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
                if needed and not any(item in content for item in needed) and step.get("csv_rows") != "$UPLOADED_CSV":
                    problems.append(f"step {index}: CSV export must check downloaded contents for a seeded "
                                    "cell or imported row value")
            if "csv_rows" in step:
                if suffix != ".csv" or step.get("csv_rows") != "$UPLOADED_CSV" or not uploaded_csv or edited_cells:
                    problems.append(f"step {index}: csv_rows must be $UPLOADED_CSV after an unchanged valid CSV upload")
            elif csv_export_contract(target):
                problems.append(f"step {index}: explicit CSV row/column/escaping contract needs csv_rows:$UPLOADED_CSV; "
                                "a substring check cannot verify the format")
            asserted = True
            continue
        if op in {"cell_context", "header_context", "expect_selected"}:
            if not target.get("has_grid", True):
                problems.append(f"step {index}: {op} needs a spreadsheet grid; this product has none")
                continue
            text = value.strip() if isinstance(value, str) else ""
            if op == "cell_context" and not CELL.match(text):
                problems.append(f"step {index}: cell_context target {json.dumps(value)} is not a cell such as A1")
            if op == "header_context" and not HEADER.match(text):
                problems.append(f"step {index}: header_context target {json.dumps(value)} is not a row number "
                                "such as 2 or a column letter such as B")
            if op == "expect_selected":
                if not (CELL.match(text) or RANGE.match(text)):
                    problems.append(f"step {index}: expect_selected target {json.dumps(value)} is not a cell or "
                                    "a range such as A1:B2")
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
        if value == "$CSV_FORMAT_NAME" and (op != "expect_visible" or not uploaded_format):
            problems.append(f"step {index}: $CSV_FORMAT_NAME is an assertion only after uploading $CSV_FORMAT")
        if value == "$INVALID_CSV_NAME" and (op != "expect_absent" or not uploaded_invalid):
            problems.append(f"step {index}: $INVALID_CSV_NAME is an absence assertion only after $INVALID_CSV upload")
        if (reset_prerequisite and isinstance(value, str)
                and ("Verification code" in value or public_display_literal(target, value))
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
            uploaded_format = False
        if not placeholder_ok and is_control(value):
            pass
        elif not isinstance(value, str) or not (value.strip() in allowed or (placeholder_ok and value.strip() in PLACEHOLDERS)):
            problems.append(f"step {index}: {op} target {json.dumps(value, ensure_ascii=False)} is not an allowed literal"
                            + ("" if placeholder_ok else " (placeholders are not control names)"))
        if op in {"fill", "expect_input_value", "select_option"}:
            typed = step.get("value")
            if isinstance(value, str) and value.startswith('$DATA_'):
                problems.append(f"step {index}: test data cannot invent a control label")
            if op == 'select_option' and isinstance(typed, str) and typed.startswith('$DATA_'):
                problems.append(f"step {index}: selectable enum must be grounded in the product contract")
            if typed == "$CSV_NAME":
                problems.append(f"step {index}: $CSV_NAME is derived from the upload and cannot be filled")
            if typed == "$CSV_FORMAT_NAME":
                problems.append(f"step {index}: $CSV_FORMAT_NAME is derived from the upload and cannot be filled")
            if typed == "$INVALID_CSV_NAME":
                problems.append(f"step {index}: $INVALID_CSV_NAME is derived from the upload and cannot be filled")
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
    if csv_format_contract(target):
        ordinary = any(isinstance(step, dict) and step.get("op") == "upload"
                       and step.get("value") == "$CSV" for step in steps)
        if ordinary:
            problems.append("this import contract explicitly names CSV quoting, UTF-8 and multiline fields; "
                            "use $CSV_FORMAT rather than the two-row basic $CSV fixture")
    format_at = next((i for i, step in enumerate(steps) if isinstance(step, dict)
                      and step.get("op") == "upload" and step.get("value") == "$CSV_FORMAT"), -1)
    if format_at >= 0 and csv_format_contract(target):
        submit_at = next((i for i, step in enumerate(steps) if i > format_at and isinstance(step, dict)
                          and step.get("op") == "click" and re.search(r"confirm\s+import|^import$",
                                                                       str(step.get("target") or ""), re.I)), -1)
        reload_at = next((i for i, step in enumerate(steps) if i > submit_at and isinstance(step, dict)
                          and step.get("op") == "reload"), -1) if submit_at >= 0 else -1
        if submit_at < 0 or reload_at < 0:
            problems.append("$CSV_FORMAT must be confirmed and the imported workbook reloaded")
        elif not any(i > submit_at and isinstance(step, dict) and step.get("op") == "expect_visible"
                     and step.get("target") == "$CSV_FORMAT_NAME" for i, step in enumerate(steps)):
            problems.append("$CSV_FORMAT import must show the file-derived workbook name $CSV_FORMAT_NAME")
        if submit_at >= 0 and reload_at >= 0:
            for row_index, row in enumerate(CSV_FORMAT_ROWS, 1):
                for col_index, expected in enumerate(row):
                    ref = f"{chr(ord('A') + col_index)}{row_index}"
                    if not any(submit_at < i < reload_at and isinstance(step, dict)
                               and step.get("op") == "expect_cell" and step.get("target") == ref
                               and step.get("value") == expected for i, step in enumerate(steps)):
                        problems.append(f"$CSV_FORMAT requires {ref}={expected!r} before reload")
            for ref, expected in (("A1", "Region"), ("D1", "第一行\n第二行"), ("E2", "中文")):
                if not any(i > reload_at and isinstance(step, dict) and step.get("op") == "expect_cell"
                           and step.get("target") == ref and step.get("value") == expected
                           for i, step in enumerate(steps)):
                    problems.append(f"$CSV_FORMAT requires persisted {ref}={expected!r} after reload")
    if format_at >= 0 and csv_export_contract(target):
        submit_at = next((i for i, step in enumerate(steps) if i > format_at and isinstance(step, dict)
                          and step.get("op") == "click" and re.search(r"confirm\s+import|^import$",
                                                                       str(step.get("target") or ""), re.I)), -1)
        observed_at = next((i for i, step in enumerate(steps) if i > submit_at and isinstance(step, dict)
                            and step.get("op") == "expect_cell" and step.get("target") == "A1"
                            and step.get("value") == "Region"), -1) if submit_at >= 0 else -1
        if submit_at < 0 or observed_at < 0:
            problems.append("CSV export setup must confirm the known format fixture and observe A1=Region before export")
    if any_invalid_upload:
        invalid_at = next((i for i, step in enumerate(steps) if isinstance(step, dict)
                           and step.get("op") == "upload" and step.get("value") == "$INVALID_CSV"), -1)
        submit_at = next((i for i, step in enumerate(steps) if i > invalid_at and isinstance(step, dict)
                          and step.get("op") == "click" and re.search(r"confirm\s+import|import", str(step.get("target") or ""), re.I)), -1)
        error_text = "Invalid CSV file format. Import failed."
        error_at = next((i for i, step in enumerate(steps) if i > submit_at and isinstance(step, dict)
                         and step.get("op") == "expect_visible" and step.get("target") == error_text), -1)
        home_at = next((i for i, step in enumerate(steps) if i > error_at and isinstance(step, dict)
                        and (step.get("op") == "reload" or (step.get("op") == "open"
                        and HOME_TARGET.match(str(step.get("target") or "").strip())))), -1)
        absence_at = next((i for i, step in enumerate(steps) if i > home_at and isinstance(step, dict)
                           and step.get("op") == "expect_absent"
                           and step.get("target") == "$INVALID_CSV_NAME"), -1)
        if min(submit_at, error_at, home_at, absence_at) < 0:
            problems.append("invalid CSV must be submitted, show the exact rejection message, "
                            "return home or reload, then assert $INVALID_CSV_NAME absent")
        seeded_workbooks = [seed for kind, seed in target.get("seed_kinds") or []
                            if re.search(r"\bworkbook\b", str(kind), re.I)]
        seeded_cells = [(match.group(1), seed) for kind, seed in target.get("seed_kinds") or []
                        if (match := re.search(r"\bcell\s+([A-Z]{1,3}[0-9]{1,4})\s+value\b", str(kind), re.I))]
        if seeded_workbooks and seeded_cells:
            workbook_at = next((i for i, step in enumerate(steps) if i > absence_at and isinstance(step, dict)
                                and step.get("op") == "open" and step.get("target") == seeded_workbooks[0]), -1)
            cell, seed = seeded_cells[0]
            retained_at = next((i for i, step in enumerate(steps) if i > workbook_at and isinstance(step, dict)
                                and step.get("op") == "expect_cell" and step.get("target") == cell
                                and step.get("value") == seed), -1)
            if workbook_at < 0 or retained_at < 0:
                problems.append("invalid CSV must leave the original seeded workbook and cell unchanged "
                                "after checking that no new workbook was created")
    if not asserted:
        problems.append("no expect step: the script must assert something from the THEN step")
    else:
        first_effect = next((index for index, step in enumerate(steps)
                             if isinstance(step, dict) and step.get("op") in {
                                 "click", "fill", "check", "press", "reload", "sign_in", "cell_type", "upload", "upload_fixture", "drag", "select_option"}), None)
        required_outcome = target.get("required_then_literal")
        cancel_branch = (any(isinstance(step, dict) and step.get("op") == "click"
                             and re.fullmatch(r"cancel", str(step.get("target") or ""), re.I)
                             for step in steps)
                         and not any(isinstance(step, dict) and step.get("op") == "click"
                                     and re.fullmatch(r"confirm\s+(?:sign\s*out|log\s*out)",
                                                      str(step.get("target") or ""), re.I)
                                     for step in steps)
                         and re.search(r"(?:cancel|closing the dialog)[^.]{0,100}(?:retain|remain|keep)",
                                       " ".join(target.get("steps") or []) + " " + str(target.get("description") or ""), re.I))
        if cancel_branch and required_outcome and re.fullmatch(r"sign\s*in|log\s*in", required_outcome, re.I):
            # The mother's THEN names the confirmed branch's sign-in entry;
            # requiring it after Cancel would demand the opposite behavior.
            required_outcome = ""
        if any(rejection_case_evidence(steps, contract)
               for contract in target.get("negative_contracts") or negative_contracts(target)):
            required_outcome = ""
        if required_outcome and not any(
                index > max(cursor, first_effect if first_effect is not None else -1)
                and isinstance(step, dict) and str(step.get("op") or "").startswith("expect_")
                and required_outcome in {step.get("target"), step.get("value")}
                for index, step in enumerate(steps)):
            problems.append(f"THEN requires asserting {required_outcome!r} after the action; "
                            "an earlier visible value is not evidence")
        if first_effect is not None and not any(
                isinstance(step, dict) and str(step.get("op") or "").startswith("expect_")
                for step in steps[first_effect + 1:]):
            problems.append("the check has no assertion after its action; assert the observable THEN outcome")
        # Sheet review S11: "click Add worksheet ... expect_visible Add worksheet".
        # An expectation is evidence only when it is not a control the script
        # itself pressed or a value it typed into a cell or field.
        acted = {str(step.get("target") or "").strip().lower() for step in steps if isinstance(step, dict)
                 and step.get("op") in {"open", "click", "hover", "check", "fill", "upload"}}
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
            if step.get("op") in {"expect_cell", "expect_role", "expect_download", "expect_input_value",
                                  "expect_count", "expect_attribute", "expect_response", "expect_response_unchanged"}:
                return True
            shown = str(step.get("target") or "").strip().lower()
            if signed_out_entry_transition(steps, index, step, target, bool(proposal.get("signed_in"))):
                return True
            if identity_transition(steps, index, step, fixtures, bool(proposal.get("signed_in"))) or (step.get("op") == "expect_visible" and public_display_literal(target, str(step.get("target") or ""))):
                return True
            if shown in acted:
                if step.get("op") == "expect_absent" and any(
                        isinstance(prior, dict) and prior.get("op") in {"click", "press"}
                        and re.search(r"delete|remove|discard|archive|trash|hide|filter", str(
                            prior.get("target") or prior.get("key") or ""), re.I)
                        for prior in steps[:index]):
                    return True
                return False
            if shown in typed_at:
                # Sheet review S31: typing the seeded `East` into an empty cell
                # and expecting `East` visible passes on the untouched seed row.
                if shown in seeded_lower:
                    return identity_transition(steps, index, step, fixtures, bool(proposal.get("signed_in")))
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
    # Passwords remain private. A requirement may explicitly DISPLAY a code;
    # future code entry must not invalidate that earlier observation.
    secret_entries = [(i, str(step.get("value")).strip(), str(step.get("target") or ""))
                      for i, step in enumerate(steps) if isinstance(step, dict)
                      and step.get("op") == "fill" and isinstance(step.get("value"), str)
                      and re.search(r"password|code|token|secret|pin\b", str(step.get("target") or ""), re.I)]
    for index, step in enumerate(steps):
        if not isinstance(step, dict) or step.get("op") != "expect_visible":
            continue
        value = str(step.get("target") or "").strip()
        for entered_at, secret, field in secret_entries:
            if value != secret:
                continue
            public_code = (re.search(r"code|pin\b", field, re.I)
                           and not re.search(r"password|token|secret", field, re.I)
                           and public_display_literal(target, value))
            if not public_code:
                problems.append(f"step {index + 1}: expect_visible {json.dumps(value)} is a value typed into a "
                                "password/code field without an explicit public display contract; assert the outcome instead")
                break
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
        if (step.get("op") == "expect_absent" and str(step.get("target") or "").strip() in seeded
                and not removing and not identity_transition(steps, index - 1, step, fixtures, bool(proposal.get("signed_in")))):
            hint = ("assert the cell instead (expect_cell with the seeded value, or with \"\" for an emptied cell)"
                    if target.get("has_grid") else "assert what the THEN step promises instead")
            problems.append(f"step {index}: expect_absent {json.dumps(step.get('target'))} is a seeded value that exists "
                            f"before the scenario; it stays on a correct app unless a step deletes or filters it out -- {hint}")
    if proposal.get("signed_in") and not (fixtures.account and fixtures.password):
        problems.append("signed_in requested but the suite has no fixture account")
    problems.extend(proposal_transition_problems(steps, target))
    return problems


def validate_proposal(proposal: Mapping, target: Mapping, fixtures: Fixtures) -> str | None:
    """The proposal's test source, or None with nothing applied when any rule fails."""
    if proposal_problems(proposal, target, fixtures):
        return None
    lines: list[str] = []
    scope = str(target["title"])
    data_values = generated_values(proposal)
    active_csv_rows: list[list[str]] | None = None
    for step_index, original_step in enumerate(proposal["steps"]):
        step = dict(original_step)
        for field in ("target", "value"):
            if isinstance(step.get(field), str) and step[field] in data_values:
                step[field] = data_values[step[field]]
        if step["op"] == "upload":
            step["csv"] = ('Region,"unterminated\n' if step.get("value") == "$INVALID_CSV"
                           else csv_format_fixture() if step.get("value") == "$CSV_FORMAT"
                           else seed_csv(target.get("seeds") or []))
            active_csv_rows = (None if step.get("value") == "$INVALID_CSV" else
                               CSV_FORMAT_ROWS if step.get("value") == "$CSV_FORMAT" else
                               list(csv.reader(io.StringIO(step["csv"], newline=""))))
        if step["op"] in {"open", "click"} and step.get("target") in (target.get("seeds") or []):
            active_csv_rows = None
        if step["op"] == "expect_download" and step.get("csv_rows") == "$UPLOADED_CSV":
            step["csv_rows"] = active_csv_rows
        if step["op"] == "set_clipboard":
            step["table"] = seed_csv(target.get("seeds") or []).replace(",", "\t")
        # Only a seeded `label/value` row splits into cells; "src/search.ts" is a path.
        step["seed_row"] = str(step.get("target") or "") in set(target.get("seeds") or []) \
            or str(step.get("value") or "") in set(target.get("seeds") or [])
        if step["op"] not in {"press", "reload", "set_clipboard"}:
            step["target"] = expand_placeholder(str(step["target"]).strip(), scope)
            if step["op"] in {"fill", "expect_input_value", "select_option", "sign_in", "expect_sign_in_rejected", "cell_type", "expect_cell"}:
                step["value"] = expand_placeholder(str(step["value"]), scope)
                if original_step.get("value") == "$WRONG_PASSWORD" and step["value"] == fixtures.password:
                    return None  # never certify a correct password as an invalid credential
            if target.get("invariant_kind") == "unregistered_account" and step["target"] in {fixtures.account, fixtures.email}:
                return None
        if signed_out_entry_transition(proposal["steps"], step_index, original_step, target, bool(proposal.get("signed_in"))):
            code = f"await h.expectRole(page, 'link', {_ts(step['target'])});"
        elif identity_transition(proposal["steps"], step_index, original_step, fixtures, bool(proposal.get("signed_in"))):
            code = f"await h.expectIdentity(page, {_ts(step['target'])}, {'false' if step['op'] == 'expect_absent' else 'true'});"
        else:
            code = _emit(step)
        if code is None:
            return None
        if explicit_phase := original_step.get("phase"):
            lines.append(f"  await test.step({_ts(explicit_phase + ': ' + step['op'])}, async () => {{ {code} }});")
        else:
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
        seen.add(key)
        cases = proposal.get("cases")
        if cases is not None:
            if (not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES or proposal.get("skip")
                    or "steps" in proposal or not all(isinstance(case, dict) for case in cases)):
                dropped.append(f"{target['title']}: cases must be 1..{MAX_CASES} independent objects without parent steps/skip")
                retryable.append({"id": target.get("id"), "title": target["title"], "reasons": [dropped[-1]], "previous_proposal": proposal})
                continue
        else:
            cases = [proposal]
        emitted = []
        problems = []
        if len(cases) < target.get('minimum_case_count', 1):
            problems.append(f"missing previously proposed cases: expected at least {target['minimum_case_count']}")
        for index, case in enumerate(cases, 1):
            case_target = dict(target, title=target['title'] + (f" [case {index}]" if proposal.get("cases") is not None else ""))
            case_proposal = {**proposal, **case}
            case_proposal.pop("cases", None)
            case_problems = proposal_problems(case_proposal, case_target, fixtures)
            if case_problems:
                problems.extend((f"case {index}: " if proposal.get("cases") is not None else "") + item for item in case_problems)
                continue
            source = validate_proposal(case_proposal, case_target, fixtures)
            if source is None:
                problems.append(f"case {index}: could not be emitted")
            else:
                emitted.append(source)
        if (csv_format_contract(target)
                and not re.search(r"\binvalid\s+CSV\b|\bunclosed\s+quote\b",
                                  " ".join(str(step) for step in target.get("steps") or []), re.I)
                and not any(isinstance(step, dict) and step.get("op") == "upload"
                            and step.get("value") == "$CSV_FORMAT"
                            for case in cases for step in case.get("steps", []) if isinstance(case, dict))):
            problems.append("this scenario needs a positive $CSV_FORMAT import case in addition to any invalid CSV branch")
        for contract in target.get("negative_contracts") or negative_contracts(target):
            if contract.get("testable") and not any(rejection_case_evidence(case.get("steps") or [], contract)
                                                    for case in cases):
                problems.append(f"missing independent {contract['kind']} branch: submit $BLANK, assert "
                                f"{contract['error']!r}, and retain {contract['preserved']!r}")
        if (any(contract.get("testable") for contract in target.get("negative_contracts") or negative_contracts(target))
                and transition_contract(target)["kind"]
                and not any(not any(rejection_case_evidence(case.get("steps") or [], contract)
                                    for contract in target.get("negative_contracts") or negative_contracts(target))
                            for case in cases)):
            problems.append("missing positive business branch alongside the rejection case")
        if emitted:
            scripts.setdefault(target["node_id"], []).extend(emitted)
        if problems:
            dropped.append(f"{target['title']}: " + "; ".join(problems))
            if not proposal.get("skip") and not proposal.get("validator_dispute"):
                retryable.append({"id": target.get("id"), "title": target["title"], "reasons": problems, "previous_proposal": proposal})
            # Keep independently valid cases; dropped reasons keep scenario coverage incomplete.
    for target in targets:
        if (target.get('id') or target['title']) not in seen:
            reason = 'requested scenario omitted from reply'
            dropped.append(f"{target['title']}: {reason}")
            retryable.append({'id': target.get('id'), 'title': target['title'], 'reasons': [reason]})
    return (scripts, dropped, retryable) if with_retryable else (scripts, dropped)


def rejection_category(reason: str) -> str:
    """Deterministic labels for proposal failures; never changes admission."""
    text = str(reason).lower()
    if any(term in text for term in ('after action', 'after submit', 'after commit', 'state change',
                                     'transition', 'post-action', 'outcome assertion')):
        return 'missing_post_action_assertion'
    if 'reload' in text or 'reopen' in text or 'persistence' in text:
        return 'missing_persistence_assertion'
    if 'csv' in text or 'field order' in text or 'escaping' in text:
        return 'format_or_csv'
    if 'literal' in text or 'unsupported value' in text or 'not allowed' in text:
        return 'unsupported_literal'
    if 'fixture' in text or 'seed' in text:
        return 'fixture'
    if 'omitted' in text or 'duplicate' in text:
        return 'missing_or_duplicate'
    return 'dsl_or_other'


def retry_prompt(rejected: list[dict], targets: list[dict], fixtures: Fixtures, phase_context: str = "") -> str:
    """One correction round: the same scenarios, each with why it was rejected."""
    by_key = {target.get("id") or target["title"]: target for target in targets}
    by_key.update({target["title"]: target for target in targets})
    chosen: list[dict] = []
    for item in rejected:
        target = by_key.get(item.get("id")) or by_key.get(item["title"])
        if target is not None and target not in chosen:
            chosen.append(target)
    prompt = build_prompt(chosen, fixtures, phase_context)
    feedback = "\n".join(f"- [{target.get('id')}] {target['title']}: " + "; ".join(item["reasons"])
                         for item in rejected
                         for target in [by_key.get(item.get("id")) or by_key.get(item["title"])] if target is not None)
    previous = [item['previous_proposal'] for item in rejected if 'previous_proposal' in item]
    prompt += ("\nPREVIOUS PROPOSALS (retain case order and unchanged valid cases; fix failed cases in place):\n"
               + json.dumps(previous, ensure_ascii=False))
    return (prompt + "\n\nYour previous scripts for these scenarios were REJECTED for the reasons below. "
            "Fix exactly these problems (use ALLOWED LITERALS, source-quoted dependency values or typed test_data "
            "according to the literal rules above; use only the "
            "listed operations, end with an expect step). Preserve required outcomes; never replace an error message "
            "with an entry control to satisfy validation. Split independent branches into cases instead of deleting assertions. "
            "If the validator contradicts the requirement, return validator_dispute with the original quote and rule reason; "
            "this records an unresolved proposal, not a passed test or a quarantine.\n" + feedback)


def append_tests(spec_source: str, tests: list[str], node_id: str) -> str:
    """Add model-proposed tests to a leaf's derived spec (creating the header when new)."""
    if not spec_source:
        spec_source = spec_header(node_id)
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
