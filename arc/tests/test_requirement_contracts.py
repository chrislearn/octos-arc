import json
import tempfile
import unittest
from pathlib import Path

from requirement_contracts import (compile_contracts, render_contracts, save_contracts,
                                   seed_gaps_by_node, source_literal_gaps, source_seed_gaps)


def requirement():
    return {
        "id": "REQ-1",
        "type": "ATOMIC",
        "name": "Create item",
        "dependencies": ["REQ-0"],
        "description": (
            'The textbox labeled “Title” and button named “Create item” are visible. '
            'The system contains an item titled “Seed item” with initial content “Seed body”. '
            'An invalid title displays exactly the message “Title is required”. '
            'A successful item persists after reload and unauthorized users must not create it. '
            'Reference image: ![create form](./reference/create-item.png)'
        ),
        "scenarios": [{
            "name": "Create and reload",
            "steps": [
                {"keyword": "GIVEN", "content": "A signed-in owner has opened the list."},
                {"keyword": "WHEN", "content": "They enter a title and activate “Create item”."},
                {"keyword": "THEN", "content": "The item is visible after reload."},
            ],
        }],
    }


class RequirementContractTests(unittest.TestCase):
    def test_compiles_yaml_scenarios_without_model_authored_cases(self):
        contracts = compile_contracts([requirement()])
        node = contracts["nodes"][0]
        self.assertEqual(node["dependencies"], ["REQ-0"])
        self.assertIn("Title is required", node["description"])
        self.assertEqual(node["cases"][0]["when"],
                         ["They enter a title and activate “Create item”."])
        self.assertIn({"role": "textbox", "name": "Title"}, node["ui"])
        self.assertIn({"role": "button", "name": "Create item"}, node["ui"])
        self.assertIn("Title is required", node["exact_messages"])
        self.assertEqual(node["required_initial_data"], [
            'The system contains an item titled “Seed item” with initial content “Seed body”.'])
        self.assertEqual(node["reference_images"], ["./reference/create-item.png"])
        self.assertEqual(node["verification_dimensions"], [
            "persistence/reload", "negative path/no mutation",
            "authorization/session isolation", "accessible role/name",
        ])

    def test_renders_explicitly_non_official_contract_and_saves_json(self):
        contracts = compile_contracts([requirement()])
        rendered = render_contracts(contracts, ["REQ-1"])
        self.assertIn("not official Playwright tests", rendered)
        self.assertIn("GIVEN: A signed-in owner", rendered)
        self.assertIn("INITIAL: The system contains an item titled", rendered)
        self.assertIn('button="Create item"', rendered)
        self.assertIn("./reference/create-item.png", rendered)
        self.assertIn("image-capable tool/model", rendered)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".arc" / "requirement-contracts.json"
            save_contracts(path, contracts)
            self.assertEqual(json.loads(path.read_text())["nodes"][0]["id"], "REQ-1")

    def test_literal_audit_is_advisory_and_skips_parameterized_names(self):
        contracts = compile_contracts([requirement()])
        gaps = source_literal_gaps(contracts, {"frontend/App.jsx": "<button>Create item</button>"})
        self.assertTrue(any('"Title"' in gap for gap in gaps))
        self.assertFalse(any('"Create item"' in gap for gap in gaps))

    def test_seed_audit_uses_only_explicit_initial_data_literals(self):
        contracts = compile_contracts([requirement()])
        gaps = source_seed_gaps(contracts, {
            "frontend/App.jsx": '<button>Create item</button>',
            "backend/items.js": 'const items = [{ title: "Seed item" }];',
        })
        self.assertTrue(any('"Seed body"' in gap for gap in gaps))
        self.assertFalse(any('signed-in owner' in gap for gap in gaps))
        gaps = source_seed_gaps(contracts, {
            "backend/items.js": 'const items = [{ title: "Seed item", content: "Seed body" }];',
        })
        self.assertEqual(gaps, [])

    def test_ordinary_given_navigation_is_not_promoted_to_seed_data(self):
        item = requirement()
        item["description"] = "Create an item from the list."
        contracts = compile_contracts([item])
        self.assertEqual(contracts["nodes"][0]["required_initial_data"], [])

    def test_scenario_input_values_are_not_promoted_to_seed_data(self):
        item = requirement()
        item["description"] = (
            'Seed update values are “Replacement title” and “Replacement body” '
            'for a successful update. Seed records include an item titled “Existing item”.')
        contracts = compile_contracts([item])
        self.assertEqual(contracts["nodes"][0]["required_initial_data"], [
            'Seed records include an item titled “Existing item”.'])

        item["description"] = 'Seed data provides a default record titled “Provided example”.'
        contracts = compile_contracts([item])
        self.assertEqual(contracts["nodes"][0]["required_initial_data"], [
            'Seed data provides a default record titled “Provided example”.'])

    def test_should_not_promote_candidate_inputs_when_seed_wording_names_a_scenario(self):
        # Verbatim ARC-Bench REQ-1-3 wording (run 2af4ff49f3c5): the "seed"
        # values are candidate passwords typed during the scenarios.
        item = requirement()
        item["description"] = (
            "Seed password-change values are `New-password-456!` for the successful update and\n"
            "`Required-password-789!` for the missing-current-password scenario.")
        item["scenarios"] = []
        contracts = compile_contracts([item])
        self.assertEqual(contracts["nodes"][0]["required_initial_data"], [])
        self.assertEqual(source_seed_gaps(contracts, {"backend/users.js": ""}), [])

    def test_should_group_seed_gaps_by_owning_node(self):
        other = requirement()
        other["id"] = "REQ-2"
        other["description"] = "The system contains an item titled “Complete item”."
        contracts = compile_contracts([requirement(), other])
        grouped = seed_gaps_by_node(contracts, {"backend/items.js": '"Complete item"'})
        self.assertEqual(set(grouped), {"REQ-1"})
        self.assertTrue(all(gap.startswith("SEED_DATA REQ-1:") for gap in grouped["REQ-1"]))

    def test_active_contract_never_drops_scenarios_to_meet_render_budget(self):
        first = requirement()
        second = requirement()
        second["id"] = "REQ-2"
        second["scenarios"][0]["steps"][0]["content"] = "Distinct second-node precondition."
        contracts = compile_contracts([first, second])
        rendered = render_contracts(
            contracts, ["REQ-1", "REQ-2"], max_chars=500, include_steps=True, require_all=True)
        self.assertIn("[REQ-1]", rendered)
        self.assertIn("[REQ-2]", rendered)
        self.assertIn("GIVEN: Distinct second-node precondition.", rendered)
        self.assertNotIn("contract prompt omitted", rendered)


if __name__ == "__main__":
    unittest.main()
