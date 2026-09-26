"""One seed for the whole requirement tree.

hackathon--sheet describes the seeded workbook five ways; two put other values
in A1 (`Item/Qty` at A1:B2 for 22 scenarios, `A1=2, B1=3` for 15). The app can
ship only one seed, so v10.0 (819388a5f77b) rewrote its seed per node
(A1 `Item` -> `2` -> `Region`) and the review called each flip an app error.
"""
import copy
import unittest
from pathlib import Path

import yaml

from seed_facts import SETUP_MARKER, parse_seed_body, resolve_seeds, seed_contract_note, setup_cells

SHEET = Path(__file__).resolve().parents[1] / "tasks/hackathon--sheet/requirements.yaml"


def tree_with(*givens):
    scenarios = [{"name": f"S{i}", "steps": [
        {"keyword": "GIVEN", "content": f"The visitor starts at home. The evaluation seed contains {body}."},
        {"keyword": "WHEN", "content": "The user opens the entry."},
        {"keyword": "THEN", "content": f"The page shows the result using the same seeded names and values ({body})."}]}
        for i, body in enumerate(givens)]
    return {"id": "ROOT", "type": "FOLDER", "children": [{"id": "REQ-1", "type": "ATOMIC", "scenarios": scenarios}]}


class ParseTests(unittest.TestCase):
    def test_should_place_cells_ranges_headers_and_rows(self):
        facts = parse_seed_body("the seeded worksheet range `A1:C6` with headers `Region/Sales/Status` and rows "
                                "`East/1200/Open`, `North/800/Closed`, `South/700/Open`")
        self.assertEqual(facts.cells[("", "A1")], "Region")
        self.assertEqual(facts.cells[("", "C1")], "Status")
        self.assertEqual(facts.cells[("", "B3")], "800")
        self.assertEqual(facts.cells[("", "C4")], "Open")
        facts = parse_seed_body("the seeded workbook `Q3 Sales`, range `A1:B2` containing `Item/Qty` and `Pen/4`, "
                                "and target range `D1:E2`")
        self.assertEqual(facts.workbook, "Q3 Sales")
        self.assertEqual({k[1]: v for k, v in facts.cells.items()}, {"A1": "Item", "B1": "Qty", "A2": "Pen", "B2": "4"})
        facts = parse_seed_body("the seeded workbook `Q3 Sales`, cells `A1=2`, `B1=3`, and formulas `=A1+B1` and `=C1*2`")
        self.assertEqual({k[1]: v for k, v in facts.cells.items()}, {"A1": "2", "B1": "3"})
        self.assertEqual(facts.formulas, ["=A1+B1", "=C1*2"])
        facts = parse_seed_body("the seeded workbook `Q3 Sales`, worksheet `Sheet1`, and cell A1 value `Region`")
        self.assertEqual((facts.worksheet, facts.cells[("Q3 Sales", "A1")]), ("Sheet1", "Region"))

    def test_should_keep_dots_inside_literals(self):
        tree = tree_with("account `alice-dev`, email `alice.dev@example.test`, file `README.md`")
        resolution = resolve_seeds(tree)
        self.assertEqual(resolution.conflicting, {})
        self.assertEqual(resolution.tree, tree)


class ResolveTests(unittest.TestCase):
    def test_should_choose_the_majority_seed_and_turn_conflicting_cells_into_scenario_setup(self):
        compatible = "the seeded workbook `Q3 Sales`, worksheet `Sheet1`, and cell A1 value `Region`"
        table = ("the seeded worksheet range `A1:C3` with headers `Region/Sales/Status` and rows "
                 "`East/1200/Open`, `North/800/Closed`")
        other = "the seeded workbook `Q3 Sales`, range `A1:B2` containing `Item/Qty` and `Pen/4`, and target range `D1:E2`"
        tree = tree_with(table, table, compatible, other)
        original = copy.deepcopy(tree)
        resolution = resolve_seeds(tree)
        self.assertEqual(tree, original, "the input tree is never modified")
        self.assertEqual(resolution.canonical[("Q3 Sales", "A1")], "Region")
        self.assertEqual(resolution.canonical[("Q3 Sales", "B2")], "1200")
        self.assertEqual(list(resolution.conflicting), [other])
        steps = resolution.tree["children"][0]["scenarios"][3]["steps"]
        given, then = steps[0]["content"], steps[2]["content"]
        self.assertIn("The evaluation seed contains the seeded workbook `Q3 Sales`, and target range `D1:E2`.", given)
        self.assertNotIn("`Item/Qty`", given.split(SETUP_MARKER)[0])
        self.assertIn(SETUP_MARKER, given)
        self.assertEqual(setup_cells(given), [("A1", "Item"), ("B1", "Qty"), ("A2", "Pen"), ("B2", "4")])
        self.assertNotIn("range `A1:B2` containing", then)
        self.assertIn("`Item` in A1", then)
        untouched = resolution.tree["children"][0]["scenarios"][0]
        self.assertEqual(untouched, original["children"][0]["scenarios"][0])

    def test_setup_sentence_is_not_promoted_to_required_initial_data(self):
        from requirement_contracts import compile_contract
        other = "the seeded workbook `Q3 Sales`, cells `A1=2`, `B1=3`, and formulas `=A1+B1` and `=C1*2`"
        base = "the seeded workbook `Q3 Sales`, worksheet `Sheet1`, and cell A1 value `Region`"
        resolution = resolve_seeds(tree_with(base, base, other))
        leaf = resolution.tree["children"][0]
        initial = "\n".join(compile_contract(leaf)["required_initial_data"])
        self.assertIn("`Region`", initial)
        self.assertNotIn("`A1=2`", initial)
        self.assertNotIn("starting values", initial)
        given = leaf["scenarios"][2]["steps"][0]["content"]
        # `=C1*2` refers to the first formula's cell: the only consistent layout is C1, D1.
        self.assertEqual(setup_cells(given), [("A1", "2"), ("B1", "3"), ("C1", "=A1+B1"), ("D1", "=C1*2")])

    def test_should_leave_formulas_unplaced_when_a_reference_would_dangle(self):
        from seed_facts import place_formulas
        self.assertEqual(place_formulas({"A1": "2"}, ["=A1+Z9"]), {})
        self.assertEqual(place_formulas({"A1": "2", "B1": "3"}, ["=SUM(A1:B1)"]), {"C1": "=SUM(A1:B1)"})

    def test_should_resolve_the_real_sheet_task_to_the_header_table(self):
        resolution = resolve_seeds(yaml.safe_load(SHEET.read_text()))
        cells = {cell: value for (_, cell), value in resolution.canonical.items()}
        self.assertEqual((cells["A1"], cells["B1"], cells["C1"], cells["A2"], cells["B2"]),
                         ("Region", "Sales", "Status", "East", "1200"))
        self.assertEqual(sorted(v.scenarios for v in resolution.conflicting.values()), [15, 22])
        self.assertEqual(resolution.rewritten, 37)
        note = seed_contract_note(resolution)
        self.assertIn("A1 `Region`", note)
        self.assertIn("`Q3 Sales`", note)
        self.assertIn("37 scenario", note)
        text = yaml.safe_dump(resolution.tree, allow_unicode=True)
        self.assertNotIn("containing `Item/Qty`", text.split("Scenario setup")[0])

    def test_should_leave_compatible_trees_alone(self):
        tree = tree_with("organization `Acme Demo`, repository `acme-docs`, member `bob-reviewer`",
                         "public repository `acme-docs`, private repository `secret-research`, owner `alice-dev`")
        resolution = resolve_seeds(tree)
        self.assertEqual((resolution.rewritten, resolution.conflicting), (0, {}))
        self.assertEqual(seed_contract_note(resolution), "")


if __name__ == "__main__":
    unittest.main()


class ConsumerTests(unittest.TestCase):
    def setUp(self):
        self.resolution = resolve_seeds(yaml.safe_load(SHEET.read_text()))
        self.leaves = {}

        def walk(node):
            if node.get("type") == "ATOMIC":
                self.leaves[node["id"]] = node
            for child in node.get("children") or []:
                walk(child)
        walk(self.resolution.tree)

    def test_entry_scripts_type_the_setup_values_and_assert_only_the_one_seed(self):
        from scenario_tests import compile_suite
        files = compile_suite(list(self.leaves.values()))
        formulas = files["REQ-4-1-1.spec.ts"]
        self.assertIn("await h.typeCells(page, [['A1', '2'], ['B1', '3'], ['C1', '=A1+B1'], ['D1', '=C1*2']]);",
                      formulas)
        self.assertIn("await h.expectCell(page, 'A1', '2');", formulas)
        self.assertLess(formulas.index("h.typeCells("), formulas.index("h.expectCell(page, 'A1', '2')"))
        seeded = files["REQ-1-1-1.spec.ts"]
        self.assertIn("await h.expectCell(page, 'A1', 'Region');", seeded)
        for rel, source in files.items():
            if rel == "helpers.ts":
                continue
            for line in source.splitlines():
                if "h.expectCell(page, 'A1'," in line and "'Region'" not in line:
                    self.assertIn("h.typeCells(", source.split(line)[0].rsplit("test(", 1)[-1],
                                  f"{rel}: A1 asserted as a non-seed value without typing it first")

    def test_review_requires_typing_setup_cells_before_asserting_them(self):
        from scenario_review import proposal_problems, review_targets
        from scenario_tests import suite_fixtures
        fixtures = suite_fixtures(list(self.leaves.values()))
        target = next(t for t in review_targets([self.leaves["REQ-3-1-2"]], fixtures, include_all=True)
                      if t["setup_cells"])
        self.assertEqual(target["setup_cells"], [("A1", "Item"), ("B1", "Qty"), ("A2", "Pen"), ("B2", "4")])
        base = {"id": target["id"], "title": target["title"], "signed_in": False, "confidence": 0.9}
        lazy = dict(base, steps=[{"op": "click", "target": "Q3 Sales"},
                                 {"op": "expect_cell", "target": "A1", "value": "Item"}])
        problems = "\n".join(proposal_problems(lazy, target, fixtures))
        self.assertIn("start with cell_type A1 'Item'", problems)
        typed = [{"op": "click", "target": "Q3 Sales"}]
        for ref, value in target["setup_cells"]:
            typed += [{"op": "cell_type", "target": ref, "value": value}, {"op": "press", "key": "Enter"}]
        good = dict(base, steps=typed + [{"op": "expect_cell", "target": "A1", "value": "Item"}])
        self.assertNotIn("scenario setup", "\n".join(proposal_problems(good, target, fixtures)))


class FlowTests(unittest.TestCase):
    def test_flow_generates_from_the_resolved_tree_and_states_the_seed_contract(self):
        import argparse
        import tempfile
        from unittest.mock import Mock, patch
        import main as m
        with tempfile.TemporaryDirectory() as folder:
            flow = m.Flow(argparse.Namespace(web_port=3000), Path(folder), Path(folder))
            flow.metric = Mock()
            original = yaml.safe_load(SHEET.read_text())
            logged = []
            with patch.object(m, "log", logged.append):
                resolved = flow.resolve_seed_conflicts(original)
            self.assertIsNot(resolved, original)
            self.assertIn("37 scenario(s) rewritten", "\n".join(logged))
            self.assertIn("A1='Item' (seed 'Region')", "\n".join(logged))
            self.assertIn("SEED CONTRACT", m.seed_contract_text(flow))
            flow.metric.assert_called_once()
            flow2 = m.Flow(argparse.Namespace(web_port=3000), Path(folder), Path(folder))
            flow2.metric = Mock()
            plain = {"id": "ROOT", "children": []}
            self.assertIs(flow2.resolve_seed_conflicts(plain), plain)
            self.assertEqual(m.seed_contract_text(flow2), "")


class GridDslTests(unittest.TestCase):
    """v10.2 sheet 17d24626341c: the reviewer skipped row/column menus ("no control is provided to
    open the column-header menu") and range selection ("none of the operations can inspect
    aria-selected"), leaving REQ-2-2-x and REQ-3-1-3 without behavioural specs."""

    def setUp(self):
        from scenario_review import review_targets
        from scenario_tests import suite_fixtures
        resolution = resolve_seeds(yaml.safe_load(SHEET.read_text()))
        leaves = {}

        def walk(node):
            if node.get("type") == "ATOMIC":
                leaves[node["id"]] = node
            for child in node.get("children") or []:
                walk(child)
        walk(resolution.tree)
        self.fixtures = suite_fixtures(list(leaves.values()))
        self.rows = review_targets([leaves["REQ-2-2-1"]], self.fixtures, include_all=True)[0]
        self.select = review_targets([leaves["REQ-3-1-3"]], self.fixtures, include_all=True)[0]

    def proposal(self, target, steps):
        return {"id": target["id"], "title": target["title"], "signed_in": False, "confidence": 0.9, "steps": steps}

    def test_header_menu_script_is_accepted_and_emitted(self):
        from scenario_review import _emit, proposal_problems
        steps = [{"op": "click", "target": "Q3 Sales"}, {"op": "header_context", "target": "2"},
                 {"op": "click", "target": "Insert 1 row above"}, {"op": "expect_cell", "target": "A3", "value": "East"}]
        self.assertEqual(proposal_problems(self.proposal(self.rows, steps), self.rows, self.fixtures), [])
        self.assertEqual(_emit(steps[1]), "await h.contextClickHeader(page, '2');")
        self.assertEqual(_emit({"op": "cell_context", "target": "B3"}), "await h.contextClickCell(page, 'B3');")
        bad = proposal_problems(self.proposal(self.rows, [steps[0], {"op": "header_context", "target": "Row 2"},
                                                          steps[3]]), self.rows, self.fixtures)
        self.assertTrue(any("header_context target" in p for p in bad))

    def test_expect_selected_is_an_assertion_for_range_selection(self):
        from scenario_review import _emit, proposal_problems
        setup = [step for ref, value in self.select["setup_cells"]
                 for step in ({"op": "cell_type", "target": ref, "value": value}, {"op": "press", "key": "Enter"})]
        steps = [{"op": "click", "target": "Q3 Sales"}] + setup + [
            {"op": "cell_click", "target": "A1:B2"}, {"op": "expect_selected", "target": "A1:B2"}]
        self.assertEqual(proposal_problems(self.proposal(self.select, steps), self.select, self.fixtures), [])
        self.assertEqual(_emit(steps[-1]), "await h.expectSelected(page, 'A1:B2');")
        bad = proposal_problems(self.proposal(self.select, steps[:-1] + [{"op": "expect_selected", "target": "A1-B2"}]),
                                self.select, self.fixtures)
        self.assertTrue(any("expect_selected target" in p for p in bad))
