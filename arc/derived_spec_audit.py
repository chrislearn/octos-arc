"""Conservative, requirement-grounded repairs for failing generated specs.

Only the harness's own specs may pass through this module. Each change either
derives an expected value from the fixture used by the test, or inserts an
explicit prerequisite stated by the requirement. Unknown failures stay with
the normal application repair path.
"""
from __future__ import annotations

import ast
import csv
import io
import re
from dataclasses import dataclass
from typing import Iterable, Mapping

from scenario_tests import Fixtures


_TEST_START = re.compile(r"^test\('((?:\\.|[^'\\])*)',", re.M)
_UPLOAD = re.compile(r"h\.uploadFile\(page,\s*'(?:\\.|[^'\\])*',\s*('(?:\\.|[^'\\])*')\)")
_VISIBLE = re.compile(r"(?m)^\s*await h\.expectTextsVisible\(page,\s*(\[(?:\\.|[^;])*?\])\);\s*$")
_CELL_SEED = re.compile(r"\bcell\s+([A-Z]{1,3}[1-9]\d*)\s+value\s+`([^`]+)`", re.I)
_NAME = re.compile(r"^derived-[0-9a-f]{6}$")
_POSSIBLE_CODE = re.compile(
    r"(?m)^\s*await h\.(?:expectReachable|expectTextsVisible|expectRole)\([^;]*Verification code[^;]*\);")
_RESET_PREREQ = re.compile(
    r"\bAfter\b[^.]{0,600}?\bclicks?\s+[“\"](?P<button>[^”\"]+)[”\"][^.]{0,600}?Verification code",
    re.I,
)
_SEEDED_RECORD = re.compile(
    r"\b(?:workbook|repository|organization|project|document|board|dataset)\s+(?:is\s+|named\s+)?`([^`]+)`",
    re.I)


@dataclass(frozen=True)
class SpecRepair:
    source: str
    changed_titles: tuple[str, ...]
    reasons: tuple[str, ...]


def _literal(value: str) -> str:
    return repr(value)


def _csv_rows(block: str) -> list[list[str]] | None:
    matches = list(_UPLOAD.finditer(block))
    # Multiple imports make it ambiguous which file an assertion describes.
    if len(matches) != 1:
        return None
    try:
        value = ast.literal_eval(matches[0].group(1))
        return list(csv.reader(io.StringIO(value, newline="")))
    except (SyntaxError, ValueError, csv.Error):
        return None


def _seed_cells(node: Mapping) -> dict[str, str]:
    """Map an old visible value to its cell only when that cell is unique."""
    found: dict[str, set[str]] = {}
    for scenario in node.get("scenarios") or []:
        for step in scenario.get("steps") or []:
            if str(step.get("keyword") or "").upper() != "GIVEN":
                continue
            for ref, value in _CELL_SEED.findall(str(step.get("content") or "")):
                found.setdefault(value, set()).add(ref.upper())
    return {value: next(iter(refs)) for value, refs in found.items() if len(refs) == 1}


def _seeded_record_names(node: Mapping) -> set[str]:
    names: set[str] = set()
    for scenario in node.get("scenarios") or []:
        for step in scenario.get("steps") or []:
            if str(step.get("keyword") or "").upper() == "GIVEN":
                names.update(_SEEDED_RECORD.findall(str(step.get("content") or "")))
    return names


def _csv_cell(rows: list[list[str]], ref: str) -> str | None:
    match = re.fullmatch(r"([A-Z]{1,3})([1-9]\d*)", ref)
    if not match:
        return None
    column = 0
    for char in match.group(1):
        column = column * 26 + ord(char) - ord("A") + 1
    row = int(match.group(2)) - 1
    return rows[row][column - 1] if row < len(rows) and column <= len(rows[row]) else None


def _fix_visible_after_upload(block: str, node: Mapping) -> tuple[str, list[str]]:
    rows = _csv_rows(block)
    if not rows:
        return block, []
    upload = _UPLOAD.search(block)
    assert upload is not None
    old_cells = _seed_cells(node)
    seeded_records = _seeded_record_names(node)
    imported = {value for row in rows for value in row}
    reasons: list[str] = []

    def replace(match: re.Match) -> str:
        try:
            values = ast.literal_eval(match.group(1))
        except (SyntaxError, ValueError):
            return match.group(0)
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            return match.group(0)
        # Only assertions after the upload describe the new workbook.
        if match.start() < upload.start():
            return match.group(0)
        since_upload = block[upload.end():match.start()]
        if any(re.search(r"h\.(?:clickNamed|openNamed)\(page,\s*" + re.escape(_literal(name)), since_upload)
               for name in seeded_records):
            return match.group(0)
        keep: list[str] = []
        cells: list[tuple[str, str]] = []
        for value in values:
            old_ref = old_cells.get(value)
            expected = _csv_cell(rows, old_ref) if old_ref else None
            if old_ref and expected is not None and value not in imported and expected != value:
                cells.append((old_ref, expected))
                reasons.append(f"{old_ref} belongs to the seeded workbook ({value}); imported CSV gives {expected}")
            elif _NAME.fullmatch(value) and not re.search(
                    r"h\.fillField\([^;]*" + re.escape(value), block[:match.start()]):
                keep.append("derived-import")
                reasons.append(f"imported workbook name comes from derived-import.csv, not {value}")
            else:
                keep.append(value)
        if not cells and keep == values:
            return match.group(0)
        indent = re.match(r"\s*", match.group(0)).group(0)
        lines = []
        if keep:
            lines.append(f"{indent}await h.expectTextsVisible(page, [{', '.join(_literal(v) for v in keep)}]);")
        lines.extend(f"{indent}await h.expectCell(page, {_literal(ref)}, {_literal(expected)});"
                     for ref, expected in cells)
        return "\n".join(lines)

    return _VISIBLE.sub(replace, block), reasons


def _fix_conditional_code(block: str, node: Mapping, fixtures: Fixtures) -> tuple[str, list[str]]:
    description = str(node.get("description") or "")
    prerequisite = _RESET_PREREQ.search(description)
    assertion = _POSSIBLE_CODE.search(block)
    if not prerequisite or not assertion:
        return block, []
    button = prerequisite.group("button")
    before = block[:assertion.start()]
    if re.search(r"h\.clickNamed\(page,\s*" + re.escape(_literal(button)), before):
        return block, []
    # The requirement states that an address must be entered before this click.
    email_field = re.search(r"\benters?\s+an?\s+address\s+in\s+the\s+([A-Za-z ]+)\s+field\s+and\s+clicks?",
                            prerequisite.group(0), re.I)
    missing_email = email_field and not re.search(r"h\.fillField\(page,\s*" +
                                                   re.escape(_literal(email_field.group(1).strip())), before)
    if missing_email:
        # A global fixture address might contradict a negative scenario. Only
        # supply it when this scenario is identifiable and asks for a normal
        # address; otherwise the correction is not grounded well enough.
        title_match = _TEST_START.search(block)
        title = title_match.group(1) if title_match else ""
        scenarios = node.get("scenarios") or []
        scenario = next((item for item in scenarios if title.startswith(str(item.get("name") or ""))
                         and item.get("name")), None)
        if scenarios and scenario is None:
            return block, []
        scenario_text = " ".join(str(step.get("content") or "") for step in (scenario or {}).get("steps") or [])
        if not fixtures.email or re.search(r"\b(?:unknown|unregistered|invalid|nonexistent|not registered)\b",
                                           scenario_text, re.I):
            return block, []
    insert = ""
    if missing_email:
        label = email_field.group(1).strip()
        insert += f"  await h.fillField(page, {_literal(label)}, {_literal(fixtures.email)});\n"
    insert += f"  await h.clickNamed(page, {_literal(button)});\n"
    return block[:assertion.start()] + insert + block[assertion.start():], [
        f"{button} is required before Verification code appears"]


def repair_failed_generated_specs(source: str, failed_titles: Iterable[str], node: Mapping,
                                  fixtures: Fixtures) -> SpecRepair:
    """Repair only failed tests with a provable fixture or prerequisite error."""
    wanted = set(failed_titles)
    starts = list(_TEST_START.finditer(source))
    if not starts or not wanted:
        return SpecRepair(source, (), ())
    output = [source[:starts[0].start()]]
    changed: list[str] = []
    reasons: list[str] = []
    for index, start in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(source)
        block = source[start.start():end]
        title = start.group(1).replace("\\'", "'")
        if title in wanted:
            original = block
            block, value_reasons = _fix_visible_after_upload(block, node)
            block, code_reasons = _fix_conditional_code(block, node, fixtures)
            if block != original:
                changed.append(title)
                reasons.extend(value_reasons + code_reasons)
        output.append(block)
    return SpecRepair("".join(output), tuple(changed), tuple(reasons))
