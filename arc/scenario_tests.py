"""Compile requirements.yaml scenarios into Playwright checks, deterministically.

No model is involved and no behaviour is invented. Two kinds of test come out:

* reach checks: a scenario's entry control (the first control its WHEN step acts
  on) must be reachable from the scenario's start state, signed in when the
  scenario says so. Generic "follow the visible controls" scenarios instead
  require their public seed values to be reachable.
* scripts: a scenario whose every WHEN clause is understood becomes an action
  sequence. GIVEN sentences that describe context ("a verified account
  exists", "the list contains a member") establish nothing the script must
  reproduce and are skipped; a GIVEN that names a page in quotes is reached by
  clicking that name; a GIVEN that describes prepared form state the script
  cannot reproduce blocks the script. Positive THEN clauses naming a literal
  the requirement quotes (“…”, "…" or `…`) become assertions; a status word
  after "displays"/"shows" counts only when the requirement itself names it.
  A script without any assertion still proves the path is usable: every
  action found its control, and the page ends in no error state.

Every asserted literal appears in the requirement. Locators and navigation in
blueprints/derived-helpers.ts are at least as tolerant as the official helpers.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

from requirement_contracts import _ui_bindings

HELPERS = Path(__file__).with_name("blueprints") / "derived-helpers.ts"

_Q = r"(?:“(?P<q1>[^”]+)”|\"(?P<q2>[^\"]+)\")"
_QB = r"(?:“(?P<q1>[^”]+)”|\"(?P<q2>[^\"]+)\"|`(?P<q3>[^`]+)`)"
_ANY_LITERAL = re.compile(r"“([^”]+)”|\"([^\"]+)\"|`([^`]+)`")
_DET = r"(?:(?:the|that|this|its|their|an?)\s+)?(?:(?:visible|seeded|existing|first|new|selected)\s+)?"
_CLICK_VERB = (r"\b(?:click|clicks|clicking|choose|chooses|select|selects|press|presses|activate|activates|tap|taps|"
               r"open|opens)\s+(?:on\s+)?" + _DET)
_CONTROL_SUFFIX = (r"(?:\s+(?:tab|button|link|menu item|menuitem|menu|item|option|filter|entry|control|type filter|"
                   r"result type|row|workbook entry|repository entry|record))?")
_CLICK = re.compile(_CLICK_VERB + _QB + _CONTROL_SUFFIX, re.I)
_CLICK_MORE = re.compile(r"\s*(?P<join>,\s*(?:and\s+)?|\s+and\s+|\s+or\s+)" + _DET + _QB + _CONTROL_SUFFIX, re.I)
_ENTER = re.compile(
    r"\b(?:enter|enters|type|types|fill|fills|input|inputs)\s+(?P<what>[^“\";,]{0,90}?)\s+(?:in|into)\s+"
    + _DET + _Q + r"(?:\s+(?:field|box|input))?", re.I)
# "..., a compliant email in “Email”, an identical confirmation password in “Confirm password”"
_ENTER_MORE = re.compile(
    r"\s*,\s*(?:and\s+)?(?P<what>[^“\";,]{0,90}?)\s+(?:in|into)\s+" + _DET + _Q + r"(?:\s+(?:field|box|input))?", re.I)
# "enters organization identifier `mobile-guild`, a display name `Mobile Guild`"
_ENTER_VALUE = re.compile(
    r"\b(?:enter|enters|type|types|input|inputs|fill\s+in|fills\s+in)\s+(?:the\s+|an?\s+)?(?P<label>[A-Za-z][\w /-]{1,40}?)"
    r"\s+`(?P<value>[^`]+)`(?P<more>(?:,\s*(?:and\s+)?(?:the\s+|an?\s+)?[A-Za-z][\w /-]{1,40}?\s+`[^`]+`)*)", re.I)
_VALUE_ITEM = re.compile(r"(?:the\s+|an?\s+)?(?P<label>[A-Za-z][\w /-]{1,40}?)\s+`(?P<value>[^`]+)`", re.I)
_LABEL_NOISE = re.compile(r"^(?:(?:valid|new|unique|exact|full|compliant|correct|optional|target|candidate)\s+)+", re.I)
_OPEN_MENU = re.compile(r"\bopens?\s+(?:the\s+|their\s+|its\s+|that\s+)?[\w -]{1,30}?\s+menu\b", re.I)
_CHECK = re.compile(r"\b(?:check|checks|tick|ticks)\s+" + _DET + _QB + r"(?:\s+checkbox)?", re.I)
_PRESS = re.compile(r"\bpress(?:es)?\s+(?:the\s+)?(?P<key>Enter|Escape|Tab)(?:\s+key)?\b", re.I)
_SIGN_IN = re.compile(r"\bsigns?\s+in\s+as\s+`(?P<u>[^`]+)`\s+with\s+`(?P<p>[^`]+)`", re.I)
# "has opened the organization's “People” page", "enters the “Your organizations” page".
# Intermediate words never include a preposition: "entered in “New password”" is typing.
_PAGE_WORDS = r"(?:(?:the|an?|its|their|that|this)\s+)?(?:(?!(?:in|into|at|from|with|on|to)\b)[\w'’-]+\s+){0,3}?"
_PAGE_SUFFIX = r"\s+(?:page|tab|view|section|dialog|form)"
_QB2 = _QB.replace("q1", "q4").replace("q2", "q5").replace("q3", "q6")
_OPENS_PAGE = re.compile(
    r"\b(?:(?:opens?|opened|is\s+on|navigates?\s+to|goes?\s+to|visits?)\s+" + _PAGE_WORDS + _QB +
    r"(?:" + _PAGE_SUFFIX + r")?|(?:enters?|entered)\s+" + _PAGE_WORDS + _QB2 + _PAGE_SUFFIX + r")", re.I)
# "clicks the repository name", "clicks the public repository's name"
_CLICK_KIND = re.compile(
    r"\b(?:click|clicks|select|selects|open|opens|choose|chooses)\s+(?:on\s+)?" + _DET +
    r"(?:(?:public|private|matching|target|that)\s+)?(?P<kind>repository|repositories|organization|team|branch|issue|"
    r"pull request|file|member|milestone|label|commit)(?:'s|’s)?\s+(?:name|title|link|row)\b", re.I)
_CONFIRMS = re.compile(r"\b(?:confirms?|verif(?:y|ies)|sees?|notes?)\s+that\b[^,;.]*", re.I)
_GENERIC = re.compile(r"\bfollows?\s+the\s+visible\s+controls\s+for\s+the\b[^.;]*?\bworkflow\b|"
                      r"\bthe\s+requested\s+workflow\b", re.I)
_TO_PAGE = re.compile(r"\bto\s+(?:enter|open|reach)\s+(?:the\s+)?[\w -]{1,40}?\s+page\b", re.I)
_ACTION_WORDS = re.compile(
    r"\b(click|clicks|choose|chooses|select|selects|press|presses|activate|tap|open|opens|enter|enters|type|"
    r"types|fill|fills|input|check|checks|hover|drag|drop|submit|submits|upload|toggle|navigate|go to|search|"
    r"scroll|follow|follows|confirm|cancel|delete|create|add|edit|change|apply|assign|remove|request|merge|"
    r"close|reopen|comment|review|compare|switch|copy|fork|record|records|expand|collapse|sort|filter|"
    r"prepare|prepared|filled|entered|selected|opened|signs? in|logs? in|attempts?|clears?|saves?|limits?|"
    r"searches|unchecks?|reopens?|hovers?|uses|updates?|keeps?|scrolls?|expands?)\b", re.I)
# Form state a script cannot reproduce: values the user is said to have typed
# or chosen before the scenario starts, or records that "already exist".
_PREPARED_STATE = re.compile(
    r"\b(?:filled|prepared|pre-?populated|already\s+exists?|entered|typed|selected|chosen|"
    r"with\s+(?:valid|invalid)\s+(?:values|data)|(?:are|is)\s+(?:valid|filled))\b", re.I)
_NO_STATE = re.compile(
    r"^(?:the\s+)?(?:visitor|user)\s+starts\s+at\s+the\s+application\s+home\s+page|"
    r"fresh\s+unauthenticated\s+browser\s+session|^the\s+seeded\s+data\s+(?:is|includes)\b|^seed\s+values\b|"
    r"^(?:the\s+)?system\s+contains\b|^(?:the\s+)?(?:user|visitor)\s+is\s+on\s+(?:the\s+home|any)\s+page\.?$|"
    r"^(?:a\s+)?(?:user|visitor)\s+has\s+opened\s+the\s+home\s+page\.?$", re.I)
_ON_PAGE = re.compile(
    r"\b(?:is|are|stays?|remains?)\s+on\s+the\s+(?P<page>home|login|log-in|sign-in|signin|account-access|"
    r"registration|register|sign-up|signup)\s+page\b(?:\s+with\s+[^.;]*?\bempty\b[^.;]*)?", re.I)
# Entry controls for pages requirements refer to by kind rather than by name.
_PAGE_ENTRY = {
    "home": [],
    **{name: ["/^\\s*(?:log\\s*-?\\s*in|sign\\s*-?\\s*in)\\s*$/i", "/log\\s*-?\\s*in|sign\\s*-?\\s*in/i"]
       for name in ("login", "log-in", "sign-in", "signin", "account-access")},
    **{name: ["/^\\s*(?:register|sign\\s*-?\\s*up)\\s*$/i", "/register|sign\\s*-?\\s*up|create\\s+(?:an\\s+)?account/i"]
       for name in ("registration", "register", "sign-up", "signup")},
}
_SIGNED_IN_STATE = re.compile(r"\b(?:a|the)\s+signed[- ]in\s+\w+\b|\bsigned[- ]in\b|\blogged[- ]in\b", re.I)
_POSITIVE = re.compile(r"\b(display|displays|displayed|show|shows|shown|see|sees|visible|appear|appears|"
                       r"opens|opened|titled|lists|listed|includes|contains|updated|created|saved|stored|"
                       r"persisted|marked|redirects|enters|navigates|returns|remains)\b", re.I)
_NEGATIVE = re.compile(r"\b(not|no|never|cannot|can't|without|unless|if|only|fail|fails|failed|error|"
                       r"rejected|except|instead|hidden|removed|longer|absent|denied|unavailable|disabled|"
                       r"empty-results|unchanged)\b", re.I)
_STATUS_WORD = re.compile(
    r"\b(?:displays?|shows?|marked(?:\s+as)?|status\s+(?:is|becomes|of)|becomes|remains|is)\s+(?:the\s+|an?\s+)?"
    r"([A-Z][a-z]{2,})\b")
_STATUS_STOP = {"The", "This", "That", "After", "When", "Then", "System", "User", "Visitor", "Owner", "Admin",
                "Page", "Both", "Each", "Its", "Their", "Only", "All", "Any", "Some", "One", "New", "Same"}
_FIXTURE_REFERENCE = re.compile(r"\b(?:the\s+)?(?:username|account\s+name|signed[- ]in\s+user(?:'s)?\s+name)\b", re.I)
_SEED_LIST = re.compile(r"\b(?:seeded\s+data|evaluation\s+seed|seed\s+data)\s+(?:is|includes|contains)\s+"
                        r"(?:the\s+existing\s+|the\s+seeded\s+)?(?P<body>[^.]+)", re.I)
# Seeds that name the record a scenario opens first (the "entry" of the app).
_ENTRY_KINDS = re.compile(r"\b(?:workbook|repository|organization|project|document|board|book|shelf|note|page|"
                          r"issue|pull request|team|dataset|order)\b", re.I)
_CELL_SEED = re.compile(r"^(?P<cell>[A-Z]{1,3}[0-9]{1,4})=(?P<value>.+)$")
_CELL_REF = re.compile(r"^[A-Z]{1,3}[0-9]{1,4}(?::[A-Z]{1,3}[0-9]{1,4})?$")
_ARIA_ROLES = {"grid", "gridcell", "tab", "tablist", "tabpanel", "dialog", "menu", "menuitem", "button", "link",
               "textbox", "combobox", "listbox", "option", "table", "row", "columnheader", "rowheader", "heading",
               "region", "navigation", "banner", "alert", "status", "checkbox", "radio", "switch", "toolbar"}
_ARIA_NAMED = re.compile(r"\b(?:ARIA\s+)?(\w+)\s+role\b[^.;]{0,120}?accessible\s+name\s+\"([^\"]+)\"", re.I)
_ARIA_CELLS = re.compile(r"\b(\w+)\s+role\s+with\s+their\s+cell\s+coordinates\s+as\s+accessible\s+names\s*"
                         r"\((?:for\s+example,?\s*)?([A-Z]{1,3}[0-9]{1,4})\)", re.I)


def _aria_contracts(text: str) -> list[tuple[str, str]]:
    """Explicit role/name promises in requirement prose ("uses the ARIA grid
    role, has the accessible name "Worksheet grid""; "gridcell role with their
    cell coordinates as accessible names (for example, A1)")."""
    found: list[tuple[str, str]] = []
    for match in _ARIA_NAMED.finditer(text):
        role = match.group(1).lower()
        if role in _ARIA_ROLES and (role, match.group(2)) not in found:
            found.append((role, match.group(2)))
    for match in _ARIA_CELLS.finditer(text):
        role = match.group(1).lower()
        if role in _ARIA_ROLES and (role, match.group(2)) not in found:
            found.append((role, match.group(2)))
    return found


def _seed_expectations(out: "_Scenario", entry: str | None) -> tuple[list[str], list[tuple[str, str]]]:
    """Plain seed values the app must show once the entry record is open, and
    cell=value seeds. Ranges and formulas are structure, not visible text."""
    values: list[str] = []
    cells: list[tuple[str, str]] = []
    for kind, value in out.seed_kinds:
        if _NON_PUBLIC.search(kind) or value == entry:
            continue
        cell = _CELL_SEED.match(value)
        kind_cell = re.search(r"\bcell\s+([A-Z]{1,3}[0-9]{1,4})\s+value\b", kind)
        if cell or kind_cell:
            ref, shown = (cell.group("cell"), cell.group("value")) if cell else (kind_cell.group(1), value)
            if not shown.startswith("="):
                cells.append((ref, shown))
            continue
        if value.startswith("=") or _CELL_REF.match(value):
            continue
        parts = [part.strip() for part in value.split("/")] if "/" in value and value.count("/") <= 3 else [value]
        for part in parts:
            if part and part not in values and not _CELL_REF.match(part) and not part.startswith("="):
                values.append(part)
    return values[:6], cells[:4]
_SEED_ITEM = re.compile(r"(?P<kind>(?:[A-Za-z0-9-]+\s+){0,3}?)`(?P<value>[^`]+)`")
_NON_PUBLIC = re.compile(r"private|secret|inaccessible|deleted|outsider|unknown|invalid|restricted", re.I)


def _quoted(match: re.Match) -> str:
    for name, value in match.groupdict().items():
        if name.startswith("q") and value:
            return value
    return ""


def _ts(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ") + "'"


def _ts_match(values: list[str]) -> str:
    return _ts(values[0]) if len(values) == 1 else "[" + ", ".join(_ts(v) for v in values) + "]"


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\s*Seed values:.*$", "", re.sub(r"\s+", " ", str(text or "")).strip())
    return [part.strip() for part in re.split(r"(?<=[.;])\s+", text) if part.strip()]


def _placeholder(literal: str) -> bool:
    """“owner/repository name” describes a pattern, not a visible value."""
    return "/" in literal and " " in literal


@dataclass
class Fixtures:
    account: str | None = None
    email: str | None = None
    password: str | None = None


def suite_fixtures(leaves: Iterable[Mapping]) -> Fixtures:
    """The first seeded account with a password, or the first explicit sign-in."""
    fixtures = Fixtures()
    for node in leaves:
        for scenario in node.get("scenarios") or []:
            for step in scenario.get("steps") or []:
                text = str(step.get("content") or "")
                seed = re.search(r"account\s+`([^`]+)`,\s*email\s+`([^`]+)`,\s*password\s+`([^`]+)`", text)
                if seed and not fixtures.password:
                    fixtures.account, fixtures.email, fixtures.password = seed.groups()
                signed = _SIGN_IN.search(text)
                if signed and not fixtures.password:
                    fixtures.account, fixtures.password = signed.group("u"), signed.group("p")
    return fixtures


_NEW_VALUE = re.compile(r"\b(?:new|compliant|unique|valid|another|fresh|different|unused|candidate)\b", re.I)


def _generated(kind: str, scope: str) -> str:
    """A made-up but valid value for a record the scenario creates; the same
    within one scenario, different across scenarios."""
    slug = hashlib.sha1(scope.encode("utf-8")).hexdigest()[:6]
    return {"username": f"user-{slug}", "email": f"user-{slug}@example.test",
            "password": f"Derived-pass-{slug}!"}[kind]


def _value_for(what: str, fixtures: Fixtures, scope: str = "") -> str | None:
    literal = re.search(r"`([^`]+)`", what)
    if literal:
        return literal.group(1)
    low = what.lower()
    fresh = bool(_NEW_VALUE.search(low))
    if "password" in low:
        if fresh or re.search(r"\b(confirmation|confirm)\b", low):
            # A new password and its confirmation are the same generated value;
            # the fixture password is never re-entered as a "new" one.
            return _generated("password", scope)
        return fixtures.password
    if "confirmation" in low:
        return None
    if re.search(r"\b(username|account)\b", low):
        return _generated("username", scope) if fresh else fixtures.account
    if "email" in low:
        return _generated("email", scope) if fresh else fixtures.email
    return None


@dataclass
class _Scenario:
    title: str
    signed_in: bool = False
    credentials: tuple[str, str] | None = None
    actions: list[str] = field(default_factory=list)
    entry: str | None = None
    compiled: bool = True
    assertions: list[str] = field(default_factory=list)
    seeds: list[str] = field(default_factory=list)
    seed_kinds: list[tuple[str, str]] = field(default_factory=list)  # (kind words, value)
    generic: bool = False
    failure_path: bool = False   # every THEN clause describes a rejection
    fallback_entry: str | None = None


def _seed_for_kind(out: _Scenario, kind: str) -> str | None:
    kind = kind.lower().rstrip("s").replace("repositorie", "repository")
    for words, value in out.seed_kinds:
        if kind in words.lower() and not _NON_PUBLIC.search(words):
            return value
    return None


def _compile_actions(sentence: str, fixtures: Fixtures, out: _Scenario, lenient: bool = False) -> bool:
    """Append the sentence's actions.

    Strict (WHEN): every action must be understood and every quoted literal
    attached to one, else the scenario gets no script. Lenient (GIVEN): what is
    not understood is context, unless it describes prepared form state.
    """
    spans: list[tuple[int, int, str, str | None]] = []

    def free(start: int, end: int) -> bool:
        return not any(s < end and start < e for s, e, _, _ in spans)

    for match in _SIGN_IN.finditer(sentence):
        spans.append((match.start(), match.end(), f"await h.signIn(page, {_ts(match.group('u'))}, "
                                                  f"{_ts(match.group('p'))});", None))
        out.signed_in = True
        out.credentials = (match.group("u"), match.group("p"))
    for match in _GENERIC.finditer(sentence):
        if free(match.start(), match.end()):
            spans.append((match.start(), match.end(), "", None))
            out.generic = True
    for match in _CONFIRMS.finditer(sentence):
        if free(match.start(), match.end()):
            spans.append((match.start(), match.end(), "", None))
    for match in _ENTER.finditer(sentence):
        if not free(match.start(), match.end()):
            continue
        items = [(match.group("what"), _quoted(match))]
        end = match.end()
        while True:
            more = _ENTER_MORE.match(sentence, end)
            if not more or not free(more.start(), more.end()):
                break
            items.append((more.group("what"), _quoted(more)))
            end = more.end()
        code = []
        for what, label in items:
            value = _value_for(what, fixtures, out.title)
            if value is None:
                out.compiled = False
                break
            code.append(f"await h.fillField(page, {_ts(label)}, {_ts(value)});")
        spans.append((match.start(), end, "\n".join(code) if out.compiled else "", items[0][1]))
    for match in _ENTER_VALUE.finditer(sentence):
        if not free(match.start(), match.end()):
            continue
        items = [(match.group("label"), match.group("value"))]
        items += [(m.group("label"), m.group("value")) for m in _VALUE_ITEM.finditer(match.group("more") or "")]
        code = []
        for label, value in items:
            label = _LABEL_NOISE.sub("", label.strip())
            code.append(f"await h.fillField(page, {_ts(label)}, {_ts(value)});")
        spans.append((match.start(), match.end(), "\n".join(code), items[0][0]))
    for match in _CHECK.finditer(sentence):
        if free(match.start(), match.end()):
            spans.append((match.start(), match.end(), f"await h.checkNamed(page, {_ts(_quoted(match))});", _quoted(match)))
    for match in _PRESS.finditer(sentence):
        if free(match.start(), match.end()):
            spans.append((match.start(), match.end(), f"await h.pressKey(page, {_ts(match.group('key').title())});", None))
    for match in _OPENS_PAGE.finditer(sentence):
        if free(match.start(), match.end()):
            spans.append((match.start(), match.end(), f"await h.openNamed(page, {_ts(_quoted(match))});", _quoted(match)))
    for match in _CLICK.finditer(sentence):
        if not free(match.start(), match.end()):
            continue
        end = match.end()
        names, alternatives, rest_code = [_quoted(match)], False, []
        while True:
            more = _CLICK_MORE.match(sentence, end)
            if not more or not free(more.start(), more.end()):
                break
            end = more.end()
            if "or" in more.group("join").split():
                alternatives = True
                names.append(_quoted(more))
            elif alternatives:
                break
            else:
                rest_code.append(_quoted(more))
        code = [f"await h.clickNamed(page, {_ts_match(names)});"] + [f"await h.clickNamed(page, {_ts(n)});" for n in rest_code]
        spans.append((match.start(), end, "\n".join(code), names[0]))
    for match in _CLICK_KIND.finditer(sentence):
        if not free(match.start(), match.end()):
            continue
        value = _seed_for_kind(out, match.group("kind"))
        if value is None:
            spans.append((match.start(), match.end(), "", None))
            out.compiled = False
        else:
            spans.append((match.start(), match.end(), f"await h.clickNamed(page, {_ts(value)});", value))
    spans.sort()
    rest = sentence
    for start, end, _, _ in reversed(spans):
        rest = rest[:start] + " " + rest[end:]
    for _, _, code, control in spans:
        if control and out.entry is None:
            out.entry = control
        if code:
            out.actions.append(code)
    # "opens the account menu" names no control; reach() opens menus itself.
    rest = _TO_PAGE.sub(" ", _OPEN_MENU.sub(" ", rest))
    leftover = _ACTION_WORDS.search(re.sub(r"\b(?:and|then|the|user|visitor|owner|admin)\b", " ", rest, flags=re.I))
    unattached = _ANY_LITERAL.search(rest)
    if lenient:
        if _PREPARED_STATE.search(rest):
            out.compiled = False
    elif leftover or unattached or re.search(r"\bif\b", rest, re.I):
        out.compiled = False
    return out.compiled


def _then_literals(clause: str, fixtures: Fixtures, node_text: str) -> list[str]:
    values = [m.group(1) or m.group(2) or m.group(3) for m in _ANY_LITERAL.finditer(clause)]
    values = [v for v in values if not _placeholder(v)]
    for match in _STATUS_WORD.finditer(clause):
        word = match.group(1)
        if word in _STATUS_STOP or word in values:
            continue
        if re.search(r"\b" + re.escape(word) + r"\b", node_text):
            values.append(word)
    if fixtures.account and _FIXTURE_REFERENCE.search(clause) and fixtures.account not in values:
        values.append(fixtures.account)
    return values


def _compile_scenario(scenario: Mapping, fixtures: Fixtures, node_text: str = "") -> _Scenario:
    out = _Scenario(title=str(scenario.get("name") or "scenario"))
    phase = ""
    then_clauses = 0
    negative_clauses = 0
    for step in scenario.get("steps") or []:
        keyword = str(step.get("keyword") or "").strip().upper()
        phase = keyword if keyword in {"GIVEN", "WHEN", "THEN"} else phase
        for sentence in _sentences(step.get("content")):
            if phase == "GIVEN":
                for seeds in _SEED_LIST.finditer(sentence):
                    for m in _SEED_ITEM.finditer(seeds.group("body")):
                        out.seed_kinds.append(((m.group("kind") or "").strip(), m.group("value")))
                        if not _NON_PUBLIC.search(m.group("kind") or ""):
                            out.seeds.append(m.group("value"))
                if _NO_STATE.search(sentence):
                    continue
                if _SIGNED_IN_STATE.search(sentence):
                    out.signed_in = True
                    sentence = _SIGNED_IN_STATE.sub(" ", sentence)
                page = _ON_PAGE.search(sentence)
                residue = re.sub(r"^\W*(?:the\s+|a\s+)?(?:user|visitor)\W*|\W+$", "",
                                 _ON_PAGE.sub(" ", sentence), flags=re.I)
                if page and not residue.strip():
                    # "is on the login page (with the fields empty)": empty is
                    # the default state; the page is reached by its entry link.
                    names = _PAGE_ENTRY.get(page.group("page").lower())
                    if names is None:
                        out.compiled = False
                    elif names:
                        out.actions.append(f"await h.clickNamed(page, [{', '.join(names)}]);")
                    continue
                _compile_actions(sentence, fixtures, out, lenient=True)
            elif phase == "WHEN":
                if out.fallback_entry is None:
                    literal = _ANY_LITERAL.search(sentence)
                    if literal:
                        out.fallback_entry = (literal.group(1) or literal.group(2) or literal.group(3)).rstrip(":. ")
                _compile_actions(sentence, fixtures, out)
            elif phase == "THEN":
                for clause in re.split(r";|,\s*and\s+|\band\s+(?=\w+s\b)", sentence):
                    if not clause.strip():
                        continue
                    then_clauses += 1
                    if _NEGATIVE.search(clause):
                        negative_clauses += 1
                        continue
                    if _POSITIVE.search(clause):
                        out.assertions += _then_literals(clause, fixtures, node_text)
    out.failure_path = then_clauses > 0 and negative_clauses == then_clauses
    if out.signed_in and out.credentials is None and fixtures.password:
        out.credentials = (fixtures.account, fixtures.password)
    return out


@dataclass
class CompiledLeaf:
    node_id: str
    source: str
    scripts: int
    reach_checks: int


def _start(lines: list[str], scenario: _Scenario) -> bool:
    lines.append("  await h.openHome(page);")
    if scenario.signed_in:
        if not scenario.credentials:
            return False
        account, password = scenario.credentials
        lines.append(f"  await h.signIn(page, {_ts(account)}, {_ts(password)});")
    return True


def _node_text(node: Mapping) -> str:
    return " ".join([str(node.get("name") or ""), str(node.get("description") or "")])


def _entry_script(parsed: "_Scenario", node_text: str, context: str,
                  shared: str = "") -> tuple[list[str], tuple] | None:
    """A templated scenario ("... and the requested workflow with concrete
    values ...") carries its contract in the seeds and the requirement prose:
    open the seeded entry record, then require the seeded values, the cell
    seeds, every explicit ARIA role/name promise and the named controls."""
    entry = next((value for kind, value in parsed.seed_kinds
                  if _ENTRY_KINDS.search(kind) and not _NON_PUBLIC.search(kind)), None)
    if entry is None:
        return None
    values, cells = _seed_expectations(parsed, entry)
    aria = _aria_contracts(node_text + "\n" + context + "\n" + shared)[:4]
    controls = [item["name"] for item in _ui_bindings(node_text)
                if item["name"] != entry and item["name"] not in values][:4]
    lines = [f"  await h.clickNamed(page, {_ts(entry)});"]
    if values:
        lines.append(f"  await h.expectTextsVisible(page, [{', '.join(_ts(v) for v in values)}]);")
    lines += [f"  await h.expectCell(page, {_ts(cell)}, {_ts(value)});" for cell, value in cells]
    lines += [f"  await h.expectRole(page, {_ts(role)}, {_ts(name)});" for role, name in aria]
    lines += [f"  await h.expectReachable(page, {_ts(name)});" for name in controls]
    key = ("entry", parsed.signed_in, entry, tuple(values), tuple(cells), tuple(aria), tuple(controls))
    return lines, key


def compile_leaf(node: Mapping, fixtures: Fixtures, context: str = "", shared: str = "") -> CompiledLeaf:
    node_id = str(node.get("id"))
    tests: list[str] = []
    seen: set[tuple] = set()
    titles: dict[str, int] = {}
    scripts = reach_checks = 0
    node_text = _node_text(node)

    def unique(title: str) -> str:
        titles[title] = titles.get(title, 0) + 1
        return title if titles[title] == 1 else f"{title} ({titles[title]})"

    for scenario in node.get("scenarios") or []:
        parsed = _compile_scenario(scenario, fixtures, node_text)
        title = parsed.title if parsed.title.startswith(node_id) else f"{node_id}: {parsed.title}"
        actions = [a for a in parsed.actions if not a.startswith("await h.signIn(")]
        scripted = parsed.compiled and not parsed.generic and bool(actions) and (
            bool(parsed.assertions) or not parsed.failure_path)
        entry_script = _entry_script(parsed, node_text, context, shared) if parsed.generic and not scripted else None
        if entry_script is not None:
            lines_, key = entry_script
            if key not in seen:
                seen.add(key)
                lines = []
                if _start(lines, parsed):
                    tests.append(f"test({_ts(unique(f'{title} [entry]'))}, async ({{ page }}) => {{\n"
                                 "  test.setTimeout(120_000);\n" + "\n".join(lines + lines_) + "\n});")
                    reach_checks += 1
            continue
        # Reach check: the entry control, or public seeds for generic scenarios.
        if scripted:
            targets = []
        elif parsed.entry:
            targets = [parsed.entry]
        elif parsed.seeds:
            targets = parsed.seeds[:2]
        else:
            targets = [parsed.fallback_entry] if parsed.fallback_entry else []
        for target in targets:
            key = ("reach", parsed.signed_in, target)
            if not target or key in seen:
                continue
            seen.add(key)
            lines: list[str] = []
            if not _start(lines, parsed):
                continue
            # Actions before the entry (sign-in) belong to the start state.
            lines.append(f"  await h.expectReachable(page, {_ts(target)});")
            tests.append(f"test({_ts(unique(f'{title} [reach] {target}'))}, async ({{ page }}) => {{\n"
                         "  test.setTimeout(120_000);\n" + "\n".join(lines) + "\n});")
            reach_checks += 1
        if scripted:
            lines = []
            if _start(lines, parsed):
                lines += ["  " + line for action in actions for line in action.split("\n")]
                if parsed.assertions:
                    lines.append(f"  await h.expectTextsVisible(page, [{', '.join(_ts(a) for a in dict.fromkeys(parsed.assertions))}]);")
                else:
                    lines.append("  await h.expectNoErrorState(page);")
                tests.append(f"test({_ts(unique(f'{title} [script]'))}, async ({{ page }}) => {{\n"
                             "  test.setTimeout(120_000);\n" + "\n".join(lines) + "\n});")
                scripts += 1
    header = (f"// requirement: {node_id}\n// Derived mechanically from requirements.yaml; not an official test.\n"
              "import { test } from '@playwright/test';\nimport * as h from './helpers';\n\n")
    return CompiledLeaf(node_id, header + "\n\n".join(tests) + ("\n" if tests else ""), scripts, reach_checks)


def compile_suite(leaves: Iterable[Mapping], context: Mapping[str, str] | None = None,
                  shared: str = "") -> dict[str, str]:
    """{relative path: source}; leaves without any derivable check get no spec.
    `context` maps a leaf id to its ancestors' descriptions; `shared` is every
    folder description (an ARIA contract stated on one module holds app-wide)."""
    leaves = list(leaves)
    fixtures = suite_fixtures(leaves)
    files = {"helpers.ts": HELPERS.read_text(encoding="utf-8")}
    for node in leaves:
        compiled = compile_leaf(node, fixtures, (context or {}).get(str(node.get("id")), ""), shared)
        if compiled.scripts or compiled.reach_checks:
            files[f"{compiled.node_id}.spec.ts"] = compiled.source
    return files


def write_suite(directory: Path, files: Mapping[str, str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for rel, source in files.items():
        (directory / rel).write_text(source, encoding="utf-8")
