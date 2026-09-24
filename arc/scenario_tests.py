"""Compile requirements.yaml scenarios into Playwright checks, deterministically.

No model is involved and no behaviour is invented. Two kinds of test come out:

* reach checks: a scenario's entry control (the first control its WHEN step acts
  on) must be reachable from the scenario's start state, signed in when the
  scenario says so. Generic "follow the visible controls" scenarios instead
  require their public seed values to be reachable.
* scripts: a scenario whose every GIVEN and WHEN clause is understood becomes
  an action sequence; only positive THEN clauses naming a quoted literal become
  assertions. One clause that is not understood and the scenario gets no script,
  because acting from a state we could not establish would fail for our reasons,
  not the application's.

Every asserted literal is quoted in the requirement. Locators and navigation in
blueprints/derived-helpers.ts are at least as tolerant as the official helpers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

HELPERS = Path(__file__).with_name("blueprints") / "derived-helpers.ts"

_Q = r"(?:“(?P<q1>[^”]+)”|\"(?P<q2>[^\"]+)\")"
_CLICK = re.compile(
    r"\b(?:click|clicks|clicking|choose|chooses|select|selects|press|presses|activate|activates|tap|taps|"
    r"open|opens)\s+(?:on\s+)?(?:the\s+)?" + _Q +
    r"(?:\s+(?:tab|button|link|menu item|menu|item|option|filter|entry|control))?", re.I)
_ENTER = re.compile(
    r"\b(?:enter|enters|type|types|fill|fills|input|inputs)\s+(?P<what>[^“\";,]{0,90}?)\s+(?:in|into)\s+"
    r"(?:the\s+)?" + _Q + r"(?:\s+(?:field|box|input))?", re.I)
_OPEN_MENU = re.compile(r"\bopens?\s+(?:the\s+|their\s+|its\s+)?[\w -]{1,30}?\s+menu\b", re.I)
_CHECK = re.compile(r"\b(?:check|checks|tick|ticks)\s+(?:the\s+)?" + _Q + r"(?:\s+checkbox)?", re.I)
_SIGN_IN = re.compile(r"\bsigns?\s+in\s+as\s+`(?P<u>[^`]+)`\s+with\s+`(?P<p>[^`]+)`", re.I)
_ACTION_WORDS = re.compile(
    r"\b(click|clicks|choose|chooses|select|selects|press|presses|activate|tap|open|opens|enter|enters|type|"
    r"types|fill|fills|input|check|checks|hover|drag|drop|submit|submits|upload|toggle|navigate|go to|search|"
    r"scroll|follow|follows|confirm|cancel|delete|create|add|edit|change|apply|assign|remove|request|merge|"
    r"close|reopen|comment|review|compare|switch|copy|fork|record|records|expand|collapse|sort|filter|"
    r"prepare|prepared|filled|entered|selected|opened|signs? in|logs? in)\b", re.I)
_NO_STATE = re.compile(
    r"^(?:the\s+)?(?:visitor|user)\s+starts\s+at\s+the\s+application\s+home\s+page|"
    r"fresh\s+unauthenticated\s+browser\s+session|^the\s+seeded\s+data\s+(?:is|includes)\b|^seed\s+values\b|"
    r"^(?:the\s+)?system\s+contains\b|^(?:the\s+)?(?:user|visitor)\s+is\s+on\s+the\s+home\s+page\.?$|"
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
_SIGNED_IN_STATE = re.compile(r"\b(?:a|the)\s+signed[- ]in\s+user\b|\bsigned[- ]in\b|\blogged[- ]in\b", re.I)
_POSITIVE = re.compile(r"\b(display|displays|displayed|show|shows|shown|see|sees|visible|appear|appears|"
                       r"opens|opened|titled|lists|listed|includes|contains)\b", re.I)
_NEGATIVE = re.compile(r"\b(not|no|never|cannot|can't|without|unless|if|only|fail|fails|failed|error|"
                       r"rejected|except|instead|hidden|removed|longer)\b", re.I)
_SEED_LIST = re.compile(r"\bseeded\s+data\s+(?:is|includes)\s+(?:the\s+existing\s+)?(?P<body>[^.]+)", re.I)
_SEED_ITEM = re.compile(r"(?P<kind>(?:[A-Za-z-]+\s+){0,3}?)`(?P<value>[^`]+)`")
_NON_PUBLIC = re.compile(r"private|secret|inaccessible|deleted|outsider|unknown|invalid|restricted", re.I)


def _quoted(match: re.Match) -> str:
    return match.group("q1") or match.group("q2")


def _ts(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ") + "'"


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\s*Seed values:.*$", "", re.sub(r"\s+", " ", str(text or "")).strip())
    return [part.strip() for part in re.split(r"(?<=[.;])\s+", text) if part.strip()]


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


def _value_for(what: str, fixtures: Fixtures) -> str | None:
    literal = re.search(r"`([^`]+)`", what)
    if literal:
        return literal.group(1)
    low = what.lower()
    if "password" in low:
        if re.search(r"\b(new|candidate|confirmation|confirm)\b", low):
            return None
        return fixtures.password
    if "confirmation" in low:
        return None
    if re.search(r"\b(username|account)\b", low):
        return fixtures.account
    if "email" in low:
        return fixtures.email
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


def _compile_actions(sentence: str, fixtures: Fixtures, out: _Scenario) -> bool:
    """Append the sentence's actions; False when any action is not understood."""
    spans: list[tuple[int, int, str, str | None]] = []
    for match in _SIGN_IN.finditer(sentence):
        spans.append((match.start(), match.end(), f"await h.signIn(page, {_ts(match.group('u'))}, "
                                                  f"{_ts(match.group('p'))});", None))
        out.signed_in = True
        out.credentials = (match.group("u"), match.group("p"))
    for match in _ENTER.finditer(sentence):
        value = _value_for(match.group("what"), fixtures)
        label = _quoted(match)
        if value is None:
            spans.append((match.start(), match.end(), "", label))
            out.compiled = False
        else:
            spans.append((match.start(), match.end(), f"await h.fillField(page, {_ts(label)}, {_ts(value)});", label))
    for match in _CHECK.finditer(sentence):
        spans.append((match.start(), match.end(), f"await h.checkNamed(page, {_ts(_quoted(match))});", _quoted(match)))
    for match in _CLICK.finditer(sentence):
        if any(start <= match.start() < end for start, end, _, _ in spans):
            continue
        spans.append((match.start(), match.end(), f"await h.clickNamed(page, {_ts(_quoted(match))});", _quoted(match)))
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
    rest = _OPEN_MENU.sub(" ", rest)
    leftover = _ACTION_WORDS.search(re.sub(r"\b(?:and|then|the|user|visitor)\b", " ", rest))
    if leftover or re.search(r"\bif\b", rest, re.I):
        out.compiled = False
    return out.compiled


def _compile_scenario(scenario: Mapping, fixtures: Fixtures) -> _Scenario:
    out = _Scenario(title=str(scenario.get("name") or "scenario"))
    phase = ""
    for step in scenario.get("steps") or []:
        keyword = str(step.get("keyword") or "").strip().upper()
        phase = keyword if keyword in {"GIVEN", "WHEN", "THEN"} else phase
        for sentence in _sentences(step.get("content")):
            if phase == "GIVEN":
                for seeds in _SEED_LIST.finditer(sentence):
                    out.seeds += [m.group("value") for m in _SEED_ITEM.finditer(seeds.group("body"))
                                  if not _NON_PUBLIC.search(m.group("kind") or "")]
                if _NO_STATE.search(sentence):
                    continue
                if _SIGNED_IN_STATE.search(sentence):
                    out.signed_in = True
                    if not (_CLICK.search(sentence) or _ENTER.search(sentence)):
                        out.compiled = out.compiled and not _ACTION_WORDS.search(
                            _SIGNED_IN_STATE.sub(" ", sentence))
                        continue
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
                if not (_CLICK.search(sentence) or _ENTER.search(sentence) or _SIGN_IN.search(sentence)):
                    out.compiled = False
                    continue
                _compile_actions(sentence, fixtures, out)
            elif phase == "WHEN":
                _compile_actions(sentence, fixtures, out)
            elif phase == "THEN":
                for clause in re.split(r";|,\s*and\s+|\band\s+(?=\w+s\b)", sentence):
                    quotes = [m.group(1) or m.group(2) for m in re.finditer(r"“([^”]+)”|\"([^\"]+)\"", clause)]
                    if quotes and _POSITIVE.search(clause) and not _NEGATIVE.search(clause):
                        out.assertions += quotes
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


def compile_leaf(node: Mapping, fixtures: Fixtures) -> CompiledLeaf:
    node_id = str(node.get("id"))
    tests: list[str] = []
    seen: set[tuple] = set()
    scripts = reach_checks = 0
    for scenario in node.get("scenarios") or []:
        parsed = _compile_scenario(scenario, fixtures)
        title = parsed.title if parsed.title.startswith(node_id) else f"{node_id}: {parsed.title}"
        # Reach check: the entry control, or public seeds for generic scenarios.
        scripted = parsed.compiled and bool([a for a in parsed.actions if not a.startswith("await h.signIn(")]) \
            and bool(parsed.assertions)
        # A script already requires its entry control; do not count one cause twice.
        targets = [] if scripted else [parsed.entry] if parsed.entry else parsed.seeds[:2]
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
            tests.append(f"test({_ts(f'{title} [reach] {target}')}, async ({{ page }}) => {{\n"
                         "  test.setTimeout(120_000);\n" + "\n".join(lines) + "\n});")
            reach_checks += 1
        actions = [a for a in parsed.actions if not a.startswith("await h.signIn(")]
        if parsed.compiled and actions and parsed.assertions:
            lines = []
            if _start(lines, parsed):
                lines += ["  " + action for action in actions]
                lines.append(f"  await h.expectTextsVisible(page, [{', '.join(_ts(a) for a in dict.fromkeys(parsed.assertions))}]);")
                tests.append(f"test({_ts(f'{title} [script]')}, async ({{ page }}) => {{\n"
                             "  test.setTimeout(120_000);\n" + "\n".join(lines) + "\n});")
                scripts += 1
    header = (f"// requirement: {node_id}\n// Derived mechanically from requirements.yaml; not an official test.\n"
              "import { test } from '@playwright/test';\nimport * as h from './helpers';\n\n")
    return CompiledLeaf(node_id, header + "\n\n".join(tests) + ("\n" if tests else ""), scripts, reach_checks)


def compile_suite(leaves: Iterable[Mapping]) -> dict[str, str]:
    """{relative path: source}; leaves without any derivable check get no spec."""
    leaves = list(leaves)
    fixtures = suite_fixtures(leaves)
    files = {"helpers.ts": HELPERS.read_text(encoding="utf-8")}
    for node in leaves:
        compiled = compile_leaf(node, fixtures)
        if compiled.scripts or compiled.reach_checks:
            files[f"{compiled.node_id}.spec.ts"] = compiled.source
    return files


def write_suite(directory: Path, files: Mapping[str, str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for rel, source in files.items():
        (directory / rel).write_text(source, encoding="utf-8")
