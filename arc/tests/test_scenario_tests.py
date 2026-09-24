import unittest

from scenario_tests import compile_leaf, compile_suite, suite_fixtures


def leaf(node_id, scenarios, description=""):
    return {"id": node_id, "name": node_id, "type": "ATOMIC", "description": description,
            "scenarios": [{"name": f"{node_id}: {name}",
                           "steps": [{"keyword": k, "content": c} for k, c in steps]}
                          for name, steps in scenarios]}


SEED = ("The visitor starts at the application home page in a fresh unauthenticated browser session. "
        "The seeded data is account `alice-dev`, email `alice.dev@example.test`, password `Valid-password-123!`.")


class ScenarioCompilerTests(unittest.TestCase):
    def test_should_compile_a_fully_understood_sign_in_scenario(self):
        node = leaf("REQ-1-1-2", [("Scenario 1", [
            ("GIVEN", SEED),
            ("WHEN", "The visitor enters the username or verified email in “Username or email”, "
                     "enters the correct password in “Password”, and clicks “Sign in”."),
            ("THEN", "The system enters the user's workspace, and the page shows “Your repositories”."),
        ])])
        fixtures = suite_fixtures([node])
        source = compile_leaf(node, fixtures).source
        self.assertIn("h.fillField(page, 'Username or email', 'alice-dev')", source)
        self.assertIn("h.fillField(page, 'Password', 'Valid-password-123!')", source)
        self.assertIn("h.clickNamed(page, 'Sign in')", source)
        self.assertIn("h.expectTextsVisible(page, ['Your repositories'])", source)
        self.assertNotIn("[reach]", source)

    def test_should_not_script_a_scenario_with_an_uncompiled_state_change(self):
        node = leaf("REQ-2.1.3", [("Register", [
            ("GIVEN", "The user is on the registration page with all required fields filled with valid values."),
            ("WHEN", 'Click the "Register" button.'),
            ("THEN", 'The system persists the user information and shows "Registration successful.".'),
        ])])
        compiled = compile_leaf(node, suite_fixtures([node]))
        self.assertEqual(compiled.scripts, 0)
        self.assertNotIn("Registration successful.", compiled.source)
        # The workflow entry control is still required to exist.
        self.assertIn("h.expectReachable(page, 'Register')", compiled.source)

    def test_should_not_script_a_page_state_with_prepared_field_values(self):
        # 12306 REQ-2.1.5: the page state carries a prepared duplicate value;
        # clicking Register on an empty form would fail for our reasons.
        node = leaf("REQ-2.1.5", [("Duplicate", [
            ("GIVEN", "The user is on the registration page with a passport number that already exists in "
                      "the system and all other required fields are valid."),
            ("WHEN", 'Click the "Register" button.'),
            ("THEN", 'The page shows "Passport number already exists." and does not complete registration.'),
        ])])
        self.assertEqual(compile_leaf(node, suite_fixtures([node])).scripts, 0)
        empty = leaf("REQ-2.1.4", [("Missing", [
            ("GIVEN", "The user is on the registration page with all required fields empty."),
            ("WHEN", 'Click the "Register" button.'),
            ("THEN", 'The page shows "Please fill in all required fields.".'),
        ])])
        self.assertEqual(compile_leaf(empty, suite_fixtures([empty])).scripts, 1)

    def test_should_skip_negative_and_conditional_then_clauses(self):
        node = leaf("REQ-1-2", [("Scenario 1", [
            ("GIVEN", SEED),
            ("WHEN", "The user signs in as `alice-dev` with `Valid-password-123!`; "
                     "the user opens the account menu and clicks “Sign out”."),
            ("THEN", "The system returns to an unauthenticated access state, displays the “Sign in” entry, "
                     "and no longer displays that user's account menu; if the user cancels the confirmation "
                     "dialog, the session remains valid and “Cancel” is shown."),
        ])])
        source = compile_leaf(node, suite_fixtures([node])).source
        self.assertIn("h.signIn(page, 'alice-dev', 'Valid-password-123!')", source)
        self.assertIn("h.expectTextsVisible(page, ['Sign in'])", source)
        self.assertNotIn("'Cancel'", source)

    def test_should_check_reachable_public_seeds_for_generic_workflow_scenarios(self):
        node = leaf("REQ-3-3", [("Scenario 2", [
            ("GIVEN", "The visitor starts at the application home page in a fresh unauthenticated browser "
                      "session. The seeded data is public repository `acme-docs`, private repository "
                      "`secret-research`, owner `Acme Demo`."),
            ("WHEN", "The user signs in as `alice-dev` with `Valid-password-123!` and follows the visible "
                     "controls for the view a public repository overview workflow."),
            ("THEN", "The page displays the required headings, controls, values, and status for the view a "
                     "public repository overview workflow."),
        ])])
        compiled = compile_leaf(node, suite_fixtures([node]))
        self.assertEqual(compiled.scripts, 0)
        self.assertIn("h.signIn(page, 'alice-dev', 'Valid-password-123!')", compiled.source)
        self.assertIn("h.expectReachable(page, 'acme-docs')", compiled.source)
        self.assertNotIn("secret-research", compiled.source)

    def test_should_start_signed_in_only_when_the_scenario_says_so(self):
        node = leaf("REQ-2-1-2", [("Scenario 1", [
            ("GIVEN", "A signed-in user opens the account menu."),
            ("WHEN", "The user clicks “Your organizations”, then clicks “New organization”."),
            ("THEN", "The page shows “Create organization”."),
        ]), ("Scenario 2", [
            ("GIVEN", "A visitor has opened the home page."),
            ("WHEN", "The visitor clicks “Explore”."),
            ("THEN", "The page shows “Trending”."),
        ])])
        other = leaf("REQ-1-1-1", [("Seed", [("GIVEN", SEED), ("WHEN", "The visitor clicks “Sign up”."),
                                             ("THEN", "The page shows “Create account”.")])])
        compiled = compile_leaf(node, suite_fixtures([other, node]))
        tests = compiled.source.split("test(")[1:]
        signed = [t for t in tests if "Your organizations" in t]
        anonymous = [t for t in tests if "Explore" in t]
        self.assertTrue(signed and all("h.signIn(page, 'alice-dev'" in t for t in signed))
        self.assertTrue(anonymous and not any("h.signIn" in t for t in anonymous))

    def test_should_quote_literals_safely_and_emit_one_spec_per_leaf(self):
        node = leaf("REQ-9", [("Quote", [
            ("GIVEN", "User is on the home page."),
            ("WHEN", 'Click the "Don\'t save" button.'),
            ("THEN", 'The page shows "It\'s done".'),
        ])])
        files = compile_suite([node])
        self.assertEqual(sorted(files), ["REQ-9.spec.ts", "helpers.ts"])
        self.assertIn("'Don\\'t save'", files["REQ-9.spec.ts"])
        self.assertIn("export async function reach", files["helpers.ts"])


class CalibrationTests(unittest.TestCase):
    """Derived literals must be the ones the official public tests use."""

    def test_should_assert_only_literals_the_official_tests_also_use(self):
        import re
        from pathlib import Path
        import yaml

        def leaves(node):
            if isinstance(node, list):
                for item in node:
                    yield from leaves(item)
                return
            if node.get("type") == "ATOMIC":
                yield node
            for child in node.get("children") or []:
                yield from leaves(child)

        bundle = Path(__file__).resolve().parents[1]
        literal = re.compile(r"h\.(?:clickNamed|checkNamed|expectReachable)\(page, '((?:[^'\\]|\\.)*)'\)|"
                             r"h\.fillField\(page, '((?:[^'\\]|\\.)*)'|h\.expectTextsVisible\(page, \[([^\]]*)\]\)")
        for task in ("arc-bench-web--12306", "arc-bench-web--keep"):
            files = compile_suite(list(leaves(yaml.safe_load(
                (bundle / "tasks" / task / "requirements.yaml").read_text(encoding="utf-8")))))
            helpers = (bundle / "public-tests" / task / "helpers.ts").read_text(encoding="utf-8").lower()
            hits = total = 0
            for rel, source in files.items():
                if rel == "helpers.ts":
                    continue
                official_path = bundle / "public-tests" / task / rel
                official = official_path.read_text(encoding="utf-8").lower() if official_path.exists() else ""
                for match in literal.finditer(source):
                    values = ([match.group(1) or match.group(2)] if (match.group(1) or match.group(2))
                              else re.findall(r"'((?:[^'\\]|\\.)*)'", match.group(3)))
                    for value in values:
                        value = value.replace("\\'", "'").lower()
                        total += 1
                        hits += value in official or value in helpers
            self.assertGreater(total, 5, task)
            self.assertGreaterEqual(hits / total, 0.95, f"{task}: {hits}/{total}")

if __name__ == "__main__":
    unittest.main()
