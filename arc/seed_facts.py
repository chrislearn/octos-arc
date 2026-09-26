"""Resolve the requirement tree to one seed before anything is generated from it.

A requirement tree may describe the same seeded record differently in
different scenarios. hackathon--sheet seeds workbook `Q3 Sales` five ways;
two put other values into A1 (`Item/Qty` at A1:B2 for 22 scenarios, `A1=2,
B1=3` for 15). The application can ship only one seed, so a run that follows
each node's GIVEN rewrites the seed per node and every checkpoint reports the
previous node as regressed (v10.0 819388a5f77b: A1 `Item` -> `2` -> `Region`).

Resolution is mechanical and conservative:
- only placed cell values (`A1=2`, `cell A1 value X`, a range with header/row
  values) are compared; records named elsewhere are never in conflict;
- the variant that governs the most scenarios wins, and compatible variants
  merge into the canonical seed in the same order;
- a conflicting scenario keeps its non-cell seed and gains an explicit
  "Scenario setup" sentence: the user enters its starting values first, as the
  grader itself does (it builds its own cells in fresh workbooks).

The platform keeps the original tree; generation, contracts, derived tests and
reviews read the resolved copy.
"""
from __future__ import annotations

import copy
import re
from collections import Counter
from dataclasses import dataclass, field

SETUP_MARKER = "Scenario setup (not part of the seed):"

_LEAD = re.compile(r"\b(?:the\s+)?(?:evaluation\s+seed|seeded\s+data|seed\s+data)\s+(?:is|includes|contains)\s+", re.I)
_CELL = r"[A-Z]{1,3}[1-9][0-9]{0,4}"
_RANGE_VALUES = re.compile(rf"\brange\s+`({_CELL}):({_CELL})`\s+(?:containing|with)\b(?P<rest>.*)", re.I | re.S)
_ASSIGNED = re.compile(rf"`({_CELL})=([^`]*)`")
_CELL_VALUE = re.compile(rf"\bcell\s+({_CELL})\s+value\s+`([^`]+)`", re.I)
_FORMULAS = re.compile(r"^\s*(?:and\s+)?formulas?\b", re.I)
_WORKBOOK = re.compile(r"\bworkbook\s+`([^`]+)`", re.I)
_WORKSHEET = re.compile(r"\bworksheet\s+`([^`]+)`", re.I)
_LITERAL = re.compile(r"`([^`]*)`")
_SETUP_CELL = re.compile(rf"`([^`]*)` in ({_CELL})\b")


def _column(letters: str) -> int:
    number = 0
    for char in letters:
        number = number * 26 + ord(char) - 64
    return number


def _letters(number: int) -> str:
    out = ""
    while number:
        number, rem = divmod(number - 1, 26)
        out = chr(65 + rem) + out
    return out


def _split_ref(ref: str) -> tuple[int, int]:
    match = re.fullmatch(r"([A-Z]+)(\d+)", ref)
    return _column(match.group(1)), int(match.group(2))


@dataclass
class SeedFacts:
    workbook: str = ""
    worksheet: str = ""
    cells: dict[tuple[str, str], str] = field(default_factory=dict)  # (workbook or "", ref) -> value
    formulas: list[str] = field(default_factory=list)                 # formulas without a stated cell
    kept: list[str] = field(default_factory=list)                     # clauses that are not cell values
    cell_clauses: list[str] = field(default_factory=list)


def _clauses(body: str) -> list[str]:
    """Top-level comma clauses; a clause that starts with a literal continues
    the previous one (`rows `a`, `b`, `c``, `cells `A1=2`, `B1=3``)."""
    parts, depth, start = [], False, 0
    for index, char in enumerate(body):
        if char == "`":
            depth = not depth
        elif char == "," and not depth:
            parts.append(body[start:index])
            start = index + 1
    parts.append(body[start:])
    clauses: list[str] = []
    for part in (p.strip() for p in parts):
        if not part:
            continue
        if clauses and re.match(r"^(?:and\s+)?`", part):
            clauses[-1] += ", " + part
        else:
            clauses.append(part)
    return clauses


def parse_seed_body(body: str) -> SeedFacts:
    facts = SeedFacts()
    workbook = _WORKBOOK.search(body)
    facts.workbook = workbook.group(1) if workbook else ""
    sheet = _WORKSHEET.search(body)
    facts.worksheet = sheet.group(1) if sheet else ""
    for clause in _clauses(body):
        placed: dict[str, str] = {}
        ranged = _RANGE_VALUES.search(clause)
        if ranged:
            values = _LITERAL.findall(ranged.group("rest"))
            if values:
                col0, row0 = _split_ref(ranged.group(1))
                for dr, value in enumerate(values):
                    for dc, cell in enumerate(value.split("/")):
                        placed[f"{_letters(col0 + dc)}{row0 + dr}"] = cell
        for ref, value in _ASSIGNED.findall(clause):
            placed[ref] = value
        for ref, value in _CELL_VALUE.findall(clause):
            placed[ref] = value
        if placed:
            facts.cells.update({(facts.workbook, ref): value for ref, value in placed.items()})
            facts.cell_clauses.append(clause)
        elif _FORMULAS.match(clause) and any(v.startswith("=") for v in _LITERAL.findall(clause)):
            facts.formulas += [v for v in _LITERAL.findall(clause) if v.startswith("=")]
            facts.cell_clauses.append(clause)
        else:
            facts.kept.append(re.sub(r"^and\s+", "", clause))
    return facts


def seed_sentences(text: str) -> list[tuple[int, int]]:
    """(start, end) of every seed body in `text`; a period inside a literal
    (`alice.dev@example.test`, `README.md`) does not end the body."""
    spans = []
    for lead in _LEAD.finditer(text):
        quoted, index = False, lead.end()
        while index < len(text):
            char = text[index]
            if char == "`":
                quoted = not quoted
            elif char == "." and not quoted and (index + 1 == len(text) or text[index + 1].isspace()):
                break
            index += 1
        spans.append((lead.end(), index))
    return spans


def setup_cells(text: str) -> list[tuple[str, str]]:
    """(ref, value) pairs a rewritten GIVEN asks the user to enter first."""
    if SETUP_MARKER not in text:
        return []
    tail = text.split(SETUP_MARKER, 1)[1]
    return [(ref, value) for value, ref in _SETUP_CELL.findall(tail)]


@dataclass
class Variant:
    body: str
    facts: SeedFacts
    scenarios: int = 0
    conflicts: dict[str, tuple[str, str]] = field(default_factory=dict)  # ref -> (this value, canonical value)


@dataclass
class SeedResolution:
    tree: dict
    canonical: dict[tuple[str, str], str]
    variants: list[Variant]
    conflicting: dict[str, Variant]
    rewritten: int
    workbook: str = ""
    worksheet: str = ""


def _scenarios(node: dict):
    for scenario in node.get("scenarios") or []:
        if isinstance(scenario, dict):
            yield scenario
    for child in node.get("children") or []:
        if isinstance(child, dict):
            yield from _scenarios(child)


def _given_bodies(scenario: dict) -> list[str]:
    bodies = []
    for step in scenario.get("steps") or []:
        if isinstance(step, dict) and str(step.get("keyword") or "").strip().upper() == "GIVEN":
            text = str(step.get("content") or "")
            bodies += [text[start:end] for start, end in seed_sentences(text)]
    return bodies


def _join(clauses: list[str]) -> str:
    if len(clauses) <= 1:
        return "".join(clauses)
    return ", ".join(clauses[:-1]) + ", and " + clauses[-1]


def place_formulas(cells: dict[str, str], formulas: list[str]) -> dict[str, str]:
    """Put formulas stated without a cell into the next cells of the last
    placed row (`A1=2`, `B1=3`, formulas `=A1+B1` and `=C1*2` -> C1, D1), but
    only when every reference then points at a cell placed before it."""
    if not cells or not formulas:
        return {}
    col, row = max((_split_ref(ref) for ref in cells), key=lambda cr: (cr[1], cr[0]))
    placed: dict[str, str] = {}
    known = set(cells)
    for offset, formula in enumerate(formulas, 1):
        ref = f"{_letters(col + offset)}{row}"
        refs = set(re.findall(rf"\$?([A-Z]{{1,3}})\$?([1-9][0-9]*)", formula))
        if not refs or any(f"{c}{r}" not in known for c, r in refs):
            return {}
        placed[ref] = formula
        known.add(ref)
    return placed


def _setup_sentence(variant: Variant, workbook: str) -> str:
    values = {ref: value for (_, ref), value in variant.facts.cells.items()}
    formulas = place_formulas(values, variant.facts.formulas)
    cells = ", ".join(f"`{value}` in {ref}" for ref, value in {**values, **formulas}.items())
    where = f"after opening `{workbook}`, " if workbook else ""
    loose = [] if formulas else variant.facts.formulas
    extra = (f"; the formulas {' and '.join(f'`{f}`' for f in loose)} are entered where the scenario uses them"
             if loose else "")
    return f"{SETUP_MARKER} {where}the user enters these starting values first: {cells}{extra}."


def resolve_seeds(tree: dict) -> SeedResolution:
    variants: dict[str, Variant] = {}
    for scenario in _scenarios(tree):
        for body in dict.fromkeys(_given_bodies(scenario)):
            variant = variants.setdefault(body, Variant(body, parse_seed_body(body)))
            variant.scenarios += 1
    workbooks = Counter()
    sheets = Counter()
    for variant in variants.values():
        if variant.facts.workbook:
            workbooks[variant.facts.workbook] += variant.scenarios
        if variant.facts.worksheet:
            sheets[variant.facts.worksheet] += variant.scenarios
    default = workbooks.most_common(1)[0][0] if workbooks else ""
    sheet = sheets.most_common(1)[0][0] if sheets else ""
    canonical: dict[tuple[str, str], str] = {}
    conflicting: dict[str, Variant] = {}
    # Most scenarios first; ties keep document order (dict insertion order is stable in sorted()).
    for variant in sorted(variants.values(), key=lambda v: -v.scenarios):
        cells = {(wb or default, ref): value for (wb, ref), value in variant.facts.cells.items()}
        clash = {ref: (value, canonical[(wb, ref)]) for (wb, ref), value in cells.items()
                 if (wb, ref) in canonical and canonical[(wb, ref)] != value}
        if clash:
            variant.conflicts = clash
            conflicting[variant.body] = variant
        else:
            canonical.update(cells)
    resolved = copy.deepcopy(tree)
    rewritten = 0
    if conflicting:
        for scenario in _scenarios(resolved):
            bodies = [body for body in _given_bodies(scenario) if body in conflicting]
            if not bodies:
                continue
            rewritten += 1
            for body in bodies:
                variant = conflicting[body]
                kept = _join(variant.facts.kept)
                setup = _setup_sentence(variant, variant.facts.workbook or default)
                values = ", ".join(f"`{value}` in {ref}" for (_, ref), value in variant.facts.cells.items())
                for step in scenario.get("steps") or []:
                    if not isinstance(step, dict):
                        continue
                    text = str(step.get("content") or "")
                    if str(step.get("keyword") or "").strip().upper() == "GIVEN" and body in text:
                        start = text.index(body)
                        end = text.find(".", start + len(body))
                        end = len(text) if end < 0 else end + 1
                        text = text[:start] + kept + "." + " " + setup + text[end:]
                    else:
                        text = text.replace(body, f"{kept}, plus the scenario setup values {values}")
                    step["content"] = text
    return SeedResolution(resolved, canonical, list(variants.values()), conflicting, rewritten, default, sheet)


def seed_contract_note(resolution: SeedResolution, max_cells: int = 40) -> str:
    """Prompt block: the one seed to ship. Empty when the tree had no conflict."""
    if not resolution.conflicting:
        return ""
    cells = sorted(resolution.canonical.items(), key=lambda item: (item[0][0], _split_ref(item[0][1])[::-1]))
    listing = ", ".join(f"{ref} `{value}`" for (_, ref), value in cells[:max_cells])
    where = f"workbook `{resolution.workbook}`" + (f", worksheet `{resolution.worksheet}`" if resolution.worksheet else "")
    return (f"SEED CONTRACT (harness-resolved; the requirement GIVENs describe the seed in {len(resolution.variants)} "
            f"ways): ship exactly this one seed and never change it to satisfy a single scenario. {where}: {listing}. "
            f"{resolution.rewritten} scenario(s) whose GIVEN named other starting cell values now enter them "
            f"themselves (\"{SETUP_MARKER}\"); those values are user input, not seed data.\n")
