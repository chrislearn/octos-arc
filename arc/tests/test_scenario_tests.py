import re
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
    def test_should_reset_to_code_seeds_before_every_derived_test(self):
        from scenario_review import append_tests
        from scenario_tests import HELPERS
        node = leaf("REQ-1", [("sign in", [
            ("GIVEN", SEED),
            ("WHEN", "The visitor enters the username or verified email in “Username or email”, "
                     "enters the correct password in “Password”, and clicks “Sign in”."),
            ("THEN", "The system enters the user's workspace, and the page shows “Your repositories”.")])])
        compiled = compile_leaf(node, suite_fixtures([node]))
        prelude = "test.beforeEach(async ({ request }) => { await h.resetState(request); });"
        self.assertEqual(compiled.source.count(prelude), 1)
        self.assertLess(compiled.source.index(prelude), compiled.source.index("\ntest("))
        self.assertIn(prelude, append_tests("", ["test('x', async ({ page }) => {});"], "REQ-2"))
        helpers = HELPERS.read_text()
        self.assertIn("export async function resetState(request: APIRequestContext)", helpers)
        self.assertIn("'/__arc/reset'", helpers)
        self.assertIn("failOnStatusCode: false", helpers)

    def test_suite_compiler_reports_progress_for_nodes_without_checks(self):
        empty = leaf("A", [])
        action = leaf("B", [("Open", [
            ("WHEN", "The visitor clicks “Open”."),
            ("THEN", "The page shows “Done”.")])])
        progress = []
        compile_suite([empty, action], progress=lambda *row: progress.append(row))
        self.assertEqual([(row[0], row[1], row[2]) for row in progress],
                         [("A", 1, 2), ("B", 2, 2)])
        self.assertEqual(progress[0][-1], 0)
        self.assertGreater(progress[1][-1], 0)

    def test_semantic_field_description_uses_declared_accessible_label(self):
        node = leaf("REQ-2-1-2", [("Create", [
            ("GIVEN", SEED),
            ("WHEN", "The user enters organization identifier `mobile-guild`, a display name `Mobile Guild`, "
                     "and clicks “Create organization”."),
            ("THEN", "The new page shows `mobile-guild`."),
        ])], description='The form has fields labeled “Organization name” and “Display name” and a button '
                        '“Create organization”.')
        source = compile_leaf(node, suite_fixtures([node])).source
        self.assertIn("h.fillField(page, 'Organization name', 'mobile-guild')", source)
        self.assertIn("h.fillField(page, 'Display name', 'Mobile Guild')", source)
        self.assertNotIn("h.fillField(page, 'organization identifier'", source)

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
        # The public seeded repository is the entry record. Other seeded
        # records need not be visible on this page.
        self.assertIn("[entry]", compiled.source)
        self.assertIn("h.clickNamed(page, 'acme-docs')", compiled.source)
        self.assertNotIn("h.expectTextsVisible(page, ['Acme Demo'])", compiled.source)
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
        # Actions and assertions must match what the official tests act on and
        # assert. Reach hints (expectReachable/openNamed) only require a quoted
        # literal to exist somewhere on the way, so they are held to a looser bar.
        literal = re.compile(r"h\.(?P<kind>clickNamed|checkNamed|expectReachable|openNamed)\(page, '((?:[^'\\]|\\.)*)'\)|"
                             r"h\.fillField\(page, '((?:[^'\\]|\\.)*)'|h\.expectTextsVisible\(page, \[([^\]]*)\]\)")
        for task in ("arc-bench-web--12306", "arc-bench-web--keep"):
            files = compile_suite(list(leaves(yaml.safe_load(
                (bundle / "tasks" / task / "requirements.yaml").read_text(encoding="utf-8")))))
            helpers = (bundle / "public-tests" / task / "helpers.ts").read_text(encoding="utf-8").lower()
            hits = {"strict": 0, "reach": 0}
            total = {"strict": 0, "reach": 0}
            for rel, source in files.items():
                if rel == "helpers.ts":
                    continue
                official_path = bundle / "public-tests" / task / rel
                official = official_path.read_text(encoding="utf-8").lower() if official_path.exists() else ""
                for match in literal.finditer(source):
                    bucket = "reach" if match.group("kind") in ("expectReachable", "openNamed") else "strict"
                    values = ([match.group(2) or match.group(3)] if (match.group(2) or match.group(3))
                              else re.findall(r"'((?:[^'\\]|\\.)*)'", match.group(4)))
                    for value in values:
                        value = value.replace("\\'", "'").lower()
                        total[bucket] += 1
                        hits[bucket] += value in official or value in helpers
            self.assertGreater(total["strict"] + total["reach"], 5, task)
            if total["strict"]:
                self.assertGreaterEqual(hits["strict"] / total["strict"], 0.95, f"{task}: {hits}/{total}")
            if total["reach"]:
                # Reach hints are quoted literals the official tests may not use; suite-level
                # dedupe removed repeated hits, so the bar is 0.8 (12306: 31/37).
                self.assertGreaterEqual(hits["reach"] / total["reach"], 0.80, f"{task}: {hits}/{total}")

if __name__ == "__main__":
    unittest.main()


class ScenarioCompilerV2Tests(unittest.TestCase):
    """GitHub-task wording (v9.0 run): narrative GIVENs, backtick literals, page navigation."""

    def test_should_treat_narrative_given_sentences_as_context(self):
        node = leaf("REQ-1-1-2", [("Scenario 1", [
            ("GIVEN", SEED + " The visitor enters the account-access page from the home page; a verified and "
                      "available account exists, and the visitor has the account's username or verified email "
                      "and current password."),
            ("WHEN", "The visitor enters the username or verified email in “Username or email”, enters the "
                     "correct password in “Password”, and clicks “Sign in”."),
            ("THEN", "The system enters the user's workspace, the account menu displays the username, and the "
                     "user can access organizations. An unknown account produces the same generic failure "
                     "message, remains on the sign-in page, and does not display the account menu."),
        ])])
        compiled = compile_leaf(node, suite_fixtures([node]))
        self.assertEqual(compiled.scripts, 1)
        self.assertIn("h.fillField(page, 'Username or email', 'alice-dev')", compiled.source)
        self.assertIn("h.clickNamed(page, 'Sign in')", compiled.source)
        # "displays the username" names the seeded account without quoting it.
        self.assertIn("h.expectTextsVisible(page, ['alice-dev'])", compiled.source)

    def test_should_click_a_quoted_page_opened_in_the_given(self):
        node = leaf("REQ-2-2-4", [("Scenario 1", [
            ("GIVEN", SEED + " The seeded data is organization `Acme Demo`, member `bob-reviewer`. An organization "
                      "Owner is signed in and has opened the organization's “People” page; the list contains a "
                      "member who also has an accessible personal account."),
            ("WHEN", "The Owner locates the row by the member's username, clicks “Remove from organization” in "
                     "the action menu, and clicks “Remove” in the confirmation dialog."),
            ("THEN", "The system removes the account from the organization-member list; after refreshing the "
                     "“People” page, the account is still absent from the member list."),
        ])])
        source = compile_leaf(node, suite_fixtures([node])).source
        # The only outcome is absence of a member after removal. A click path
        # ending in "no error" cannot prove that mutation, so no script is emitted.
        self.assertNotIn("[script]", source)
        self.assertIn("h.expectReachable(page, 'People')", source)

    def test_should_assert_backtick_literals_and_status_words_named_by_the_requirement(self):
        node = leaf("REQ-6-5", [("Scenario 1", [
            ("GIVEN", SEED + " A signed-in maintainer has opened “Conversation” of a mergeable pull request."),
            ("WHEN", "The maintainer clicks “Merge pull request”, and clicks “Confirm merge” in the confirmation box."),
            ("THEN", "The PR displays Merged, the merger, time, and resulting commit identifier; the `main` "
                     "branch head is updated to the merge result."),
        ])], description="After the merge the pull request shows Merged and the `main` branch advances.")
        source = compile_leaf(node, suite_fixtures([node])).source
        self.assertIn("h.expectTextsVisible(page, ['Merged', 'main'])", source)
        other = leaf("REQ-X", [("S", [
            ("GIVEN", SEED + " A signed-in user opens “Settings”."),
            ("WHEN", "The user clicks “Save”."),
            ("THEN", "The page displays Saved."),
        ])], description="No status vocabulary here.")
        # A capitalized word the requirement never names is not a literal.
        self.assertNotIn("'Saved'", compile_leaf(other, suite_fixtures([other])).source)

    def test_should_compile_backtick_field_values_and_press_enter(self):
        node = leaf("REQ-2-1-2", [("Scenario 1", [
            ("GIVEN", SEED + " A signed-in user enters the “Your organizations” page from the account menu and "
                      "clicks “New organization”; the identifier `mobile-guild` is unused."),
            ("WHEN", "The user enters organization identifier `mobile-guild`, a display name `Mobile Guild`, "
                     "and clicks “Create organization”."),
            ("THEN", "The system creates the organization and displays its overview page titled `Mobile Guild`."),
        ]), ("Scenario 2", [
            ("GIVEN", "The user is on the home page."),
            ("WHEN", "The user enters `acme-docs` in “Search” and presses Enter, then selects the “Repositories” "
                     "filter."),
            ("THEN", "The page shows `acme-docs`."),
        ])])
        source = compile_leaf(node, suite_fixtures([node])).source
        self.assertIn("h.openNamed(page, 'Your organizations')", source)
        self.assertIn("h.clickNamed(page, 'New organization')", source)
        self.assertIn("h.fillField(page, 'organization identifier', 'mobile-guild')", source)
        self.assertIn("h.fillField(page, 'display name', 'Mobile Guild')", source)
        self.assertIn("h.expectTextsVisible(page, ['Mobile Guild'])", source)
        self.assertIn("h.fillField(page, 'Search', 'acme-docs')", source)
        self.assertIn("h.pressKey(page, 'Enter')", source)
        self.assertIn("h.clickNamed(page, 'Repositories')", source)

    def test_should_click_seed_records_named_by_kind(self):
        node = leaf("REQ-3-3", [("Scenario 1", [
            ("GIVEN", "The seeded data is public repository `acme-docs`, private repository `secret-research`, "
                      "owner `alice-dev`. A visitor has a search result for a public repository."),
            ("WHEN", "The visitor clicks the repository name."),
            ("THEN", "The system enters the “owner/repository name” overview page and displays `acme-docs`."),
        ])])
        source = compile_leaf(node, suite_fixtures([node])).source
        self.assertIn("h.clickNamed(page, 'acme-docs')", source)
        self.assertIn("h.expectTextsVisible(page, ['acme-docs'])", source)

    def test_should_not_script_when_a_when_step_is_only_partly_understood(self):
        node = leaf("REQ-4-3-1", [("Scenario 1", [
            ("GIVEN", "The user has opened the default branch of an accessible repository."),
            ("WHEN", "The user opens the branch selector currently showing `main`, enters `feature-search`, "
                     "and clicks that branch name."),
            ("THEN", "The page shows `feature-search`."),
        ])])
        compiled = compile_leaf(node, suite_fixtures([node]))
        self.assertEqual(compiled.scripts, 0)
        self.assertNotIn("[reach]", compiled.source)  # no named UI target to test honestly


class GeneratedFixtureValueTests(unittest.TestCase):
    """Creating a record must not reuse the seeded account: registering
    `alice-dev` again fails as soon as the seed exists (v9.1 run 2a839b37d3e8
    lost REQ-1-1-2's work to that false regression)."""

    def test_new_account_fields_get_generated_values_not_the_fixture(self):
        node = leaf("REQ-1-1-1", [("Scenario 1", [
            ("GIVEN", SEED + " The visitor clicks “Create an account”."),
            ("WHEN", "The visitor enters a compliant username in “Username”, a compliant email in “Email”, a "
                     "compliant password in “Password”, an identical confirmation password in “Confirm password”, "
                     "checks “I agree” and clicks “Create account”."),
            ("THEN", "The page shows “Welcome”."),
        ])])
        source = compile_leaf(node, suite_fixtures([node])).source
        self.assertEqual(source.count("[script]"), 1)
        self.assertNotIn("'alice-dev'", source.split("[script]", 1)[1])
        username = re.search(r"h\.fillField\(page, 'Username', '([^']+)'\)", source).group(1)
        self.assertRegex(username, r"^[a-z0-9-]{3,39}$")
        password = re.search(r"h\.fillField\(page, 'Password', '([^']+)'\)", source).group(1)
        self.assertGreaterEqual(len(password), 12)
        self.assertIn(f"h.fillField(page, 'Confirm password', '{password}')", source)
        self.assertIn("h.checkNamed(page, 'I agree')", source)

    def test_existing_account_fields_still_use_the_fixture(self):
        node = leaf("REQ-1-1-2", [("Scenario 1", [
            ("GIVEN", SEED),
            ("WHEN", "The visitor enters the username in “Username or email”, enters the correct password in "
                     "“Password”, and clicks “Sign in”."),
            ("THEN", "The page shows “Sign out”."),
        ])])
        source = compile_leaf(node, suite_fixtures([node])).source
        self.assertIn("h.fillField(page, 'Username or email', 'alice-dev')", source)


SHEET_SEED = ("The visitor starts at the application home page in a fresh unauthenticated browser session. "
              "The evaluation seed contains the seeded workbook `Q3 Sales`, worksheet `Sheet1`, rows `East/1200` "
              "and `North/800`, and cell A1 value `Region`.")
SHEET_WHEN = ("The user opens the workbook home page, clicks the visible `Q3 Sales` workbook entry, and the requested "
              "workflow with concrete values `East`, `1200`, `North`, and `800`. Every value is entered through a "
              "visible, labelled control; no implementation-specific navigation is assumed.")
SHEET_THEN = ("The application exposes the observable result for \"the requested workflow\" using the same seeded "
              "names and values (the seeded workbook `Q3 Sales`, worksheet `Sheet1`); validation or permission "
              "failures are shown beside the named control and do not create a partial record.")


class TemplatedScenarioTests(unittest.TestCase):
    """hackathon--sheet (run ef2ab916a57d, 0/100): every scenario is a template
    ("... and the requested workflow with concrete values ...") and the contract
    lives in the description and the seeds. One reach check per leaf let a
    hollow app pass 24/24 locally."""

    def _node(self):
        return leaf("REQ-1-1-1", [("REQ-1-1-1 -the requested workflow", [
            ("GIVEN", SHEET_SEED), ("WHEN", SHEET_WHEN), ("THEN", SHEET_THEN)]),
            ("REQ-1-1-1 -the requested workflow", [
            ("GIVEN", SHEET_SEED), ("WHEN", SHEET_WHEN), ("THEN", SHEET_THEN)])],
            description='Each record provides a link whose accessible name is the workbook name and a button '
                        'named "New blank workbook". The grid uses the ARIA grid role, has the accessible name '
                        '"Worksheet grid", and grid cells use the ARIA gridcell role with their cell coordinates as '
                        'accessible names (for example, A1).')

    def test_templated_scenario_becomes_an_entry_script_from_seeds_and_contracts(self):
        node = self._node()
        compiled = compile_leaf(node, suite_fixtures([node]))
        source = compiled.source
        self.assertIn("[entry]", source)
        self.assertIn("h.clickNamed(page, 'Q3 Sales')", source)
        # Seeded rows can live on another sheet; assert only coordinates tied
        # to the opened record, plus explicit UI contracts.
        self.assertNotIn("h.expectTextsVisible(page, ['East'", source)
        self.assertIn("h.expectCell(page, 'A1', 'Region')", source)
        # Explicit ARIA contracts from the requirement text are asserted by role.
        self.assertIn("h.expectRole(page, 'grid', 'Worksheet grid')", source)
        self.assertIn("h.expectRole(page, 'gridcell', 'A1')", source)
        self.assertIn("h.expectReachable(page, 'New blank workbook')", source)
        self.assertNotIn("'East/1200'", source)

    def test_duplicate_scenario_names_get_unique_test_titles(self):
        node = self._node()
        source = compile_leaf(node, suite_fixtures([node])).source
        titles = re.findall(r"^test\('([^']+)'", source, re.M)
        self.assertEqual(len(titles), len(set(titles)), titles)

    def test_ancestor_contracts_are_used_when_given(self):
        node = leaf("REQ-3-1-1", [("REQ-3-1-1 -the requested workflow", [
            ("GIVEN", SHEET_SEED), ("WHEN", SHEET_WHEN), ("THEN", SHEET_THEN)])], description="Edit a cell.")
        context = 'The active worksheet grid uses the ARIA grid role, has the accessible name "Worksheet grid".'
        source = compile_leaf(node, suite_fixtures([node]), context=context).source
        self.assertIn("h.expectRole(page, 'grid', 'Worksheet grid')", source)
        files = compile_suite([node], context={"REQ-3-1-1": context})
        self.assertIn("Worksheet grid", files["REQ-3-1-1.spec.ts"])

    def test_entry_check_does_not_require_a_closed_menu_item(self):
        node = leaf("REQ-3-1-2", [("REQ-3-1-2 -the requested workflow", [
            ("GIVEN", SHEET_SEED), ("WHEN", SHEET_WHEN), ("THEN", SHEET_THEN)])],
            description='The context menu uses the ARIA menuitem role with accessible name "Paste". '
                        'The grid uses the ARIA grid role with accessible name "Worksheet grid".')
        source = compile_leaf(node, suite_fixtures([node])).source
        self.assertNotIn("h.expectRole(page, 'menuitem', 'Paste')", source)
        self.assertIn("h.expectRole(page, 'grid', 'Worksheet grid')", source)


class SharedContractTests(unittest.TestCase):
    def test_folder_level_aria_contracts_apply_to_every_entry_script(self):
        node = leaf("REQ-4-1-1", [("REQ-4-1-1 -the requested workflow", [
            ("GIVEN", SHEET_SEED), ("WHEN", SHEET_WHEN), ("THEN", SHEET_THEN)])], description="Formulas.")
        shared = 'The active worksheet grid uses the ARIA grid role, has the accessible name "Worksheet grid".'
        files = compile_suite([node], shared=shared)
        self.assertIn("h.expectRole(page, 'grid', 'Worksheet grid')", files["REQ-4-1-1.spec.ts"])


class PlaceholderLiteralTests(unittest.TestCase):
    """v9.2.4 sheet run 1d804e9973c6: the suite asserted "Last updated: <last updated
    value>" verbatim, the model made the app print that placeholder, and the next
    leaf's correct rendering was rolled back as a regression."""

    def test_then_literals_with_angle_placeholders_become_their_prefix(self):
        node = leaf("REQ-1-1-1", [("Scenario 1", [
            ("GIVEN", "The user is on the home page."),
            ("WHEN", "The user clicks “Open”."),
            ("THEN", "The page displays \"Last updated: <last updated value>\" and \"<cell coordinate>\"."),
        ])])
        source = compile_leaf(node, suite_fixtures([node])).source
        self.assertIn("h.expectTextsVisible(page, ['Last updated:'])", source)
        self.assertNotIn("<last updated value>", source)
        self.assertNotIn("<cell coordinate>", source)

    def test_entry_controls_with_placeholders_become_their_prefix(self):
        node = leaf("REQ-3-2-1", [("REQ-3-2-1 -the requested workflow", [
            ("GIVEN", SHEET_SEED), ("WHEN", SHEET_WHEN), ("THEN", SHEET_THEN)])],
            description='Each header has a button named "Filter <header text>" and a button named "Apply".')
        source = compile_leaf(node, suite_fixtures([node])).source
        self.assertIn("h.expectReachable(page, 'Filter')", source)
        self.assertIn("h.expectReachable(page, 'Apply')", source)
        self.assertNotIn("<header text>", source)


class ReachTargetHygieneTests(unittest.TestCase):
    def test_messages_and_patterns_are_never_reach_targets(self):
        node = leaf("REQ-2-1-4", [("REQ-2-1-4 -the requested workflow", [
            ("GIVEN", SHEET_SEED), ("WHEN", SHEET_WHEN), ("THEN", SHEET_THEN)])],
            description='Clicking "Delete" in the dialog "Delete worksheet" removes it; with one worksheet left the '
                        'dialog displays "A workbook must contain at least one worksheet".')
        source = compile_leaf(node, suite_fixtures([node])).source
        self.assertNotIn("A workbook must contain", source)
        self.assertIn("h.expectReachable(page, 'Delete worksheet')", source)
        other = leaf("REQ-3-3", [("Scenario 1", [
            ("GIVEN", "The user is on the home page."),
            ("WHEN", "The visitor opens the “owner/repository name” page by typing its address."),
            ("THEN", "The page shows the repository."),
        ])])
        self.assertNotIn("owner/repository name", compile_leaf(other, suite_fixtures([other])).source)


class SuiteHygieneTests(unittest.TestCase):
    """Local generation for both tasks: 46/116 github tests and 8/24 sheet tests had
    byte-identical bodies across leaves; entry scripts repeated a control and
    asserted one-character seed values."""

    def test_identical_tests_across_leaves_are_emitted_once(self):
        seed = SEED
        a = leaf("REQ-1-1-1", [("Scenario 2", [("GIVEN", seed), ("WHEN", "The user signs in as `alice-dev` with "
                 "`Valid-password-123!` and follows the visible controls for the register workflow."),
                 ("THEN", "The page displays the required headings for the register workflow.")])],
                 description='The “Repositories” tab opens the list.')
        b = leaf("REQ-1-1-2", [("Scenario 2", [("GIVEN", seed), ("WHEN", "The user signs in as `alice-dev` with "
                 "`Valid-password-123!` and follows the visible controls for the sign in workflow."),
                 ("THEN", "The page displays the required headings for the sign in workflow.")])],
                 description='The “Repositories” tab opens the list.')
        c = leaf("REQ-1-1-3", [("Scenario 2", [("GIVEN", seed), ("WHEN", "The user signs in as `alice-dev` with "
                 "`Valid-password-123!` and follows the visible controls for the sign in workflow."),
                 ("THEN", "The page displays the required headings for the sign in workflow.")]),
                 ("Scenario 3", [("GIVEN", seed), ("WHEN", "The user signs in as `alice-dev` with `Valid-password-123!` "
                 "and opens the \u201cRepositories\u201d tab."), ("THEN", "The page shows \u201cacme-docs\u201d.")])],
                 description='The “Repositories” tab opens the list.')
        files = compile_suite([a, b, c])
        self.assertIn("REQ-1-1-1.spec.ts", files)
        # The second leaf's only test is identical to the first's: it still keeps
        # its own spec file (a leaf without one has no acceptance in the measured
        # flow), but a leaf that also has a distinct check drops the repeat.
        self.assertIn("REQ-1-1-2.spec.ts", files)
        self.assertEqual(files["REQ-1-1-2.spec.ts"].count("\ntest("), 1)
        self.assertEqual(files["REQ-1-1-3.spec.ts"].count("\ntest("), 1)
        self.assertNotIn("[reach] alice-dev", files["REQ-1-1-3.spec.ts"])

    def test_entry_scripts_do_not_repeat_controls_or_assert_trivial_values(self):
        node = leaf("REQ-3-1-1", [("REQ-3-1-1 -the requested workflow", [
            ("GIVEN", "The visitor starts at the application home page in a fresh unauthenticated browser session. "
                      "The evaluation seed contains the seeded workbook `Q3 Sales`, range `A1:B2` containing "
                      "`Item/Qty` and `Pen/4`."),
            ("WHEN", SHEET_WHEN), ("THEN", SHEET_THEN)])],
            description='The "Code" tab and the "Code" link open the code view.')
        source = compile_leaf(node, suite_fixtures([node])).source
        self.assertEqual(source.count("h.expectReachable(page, 'Code')"), 1)
        self.assertNotIn("h.expectTextsVisible(page, ['Pen'", source)
        self.assertNotIn("'4'", source)

    def test_mechanical_scripts_assert_typed_names_rather_than_the_control_they_opened(self):
        node = leaf("REQ-2-1-2", [("Scenario 1", [
            ("GIVEN", SEED + " A signed-in user enters the “Your organizations” page and clicks “New organization”."),
            ("WHEN", "The user enters organization identifier `mobile-guild`, a display name `Mobile Guild`, "
                     "and clicks “Create organization”."),
            ("THEN", "The organization appears under “Your organizations”."),
        ])])
        source = compile_leaf(node, suite_fixtures([node])).source
        self.assertRegex(source, r"h\.expectTextsVisible\(page, \[[^\]]*'Mobile Guild'[^\]]*\]\)")
        self.assertNotIn("['Your organizations']", source)


class LeafKeepsOwnSpecTests(unittest.TestCase):
    def test_every_leaf_keeps_a_spec_file_when_its_checks_duplicate_a_sibling(self):
        def templated(node_id):
            return leaf(node_id, [(f"{node_id} -the requested workflow", [
                ("GIVEN", "The evaluation seed contains the seeded workbook `Q3 Sales`, rows `East/1200` and `North/800`."),
                ("WHEN", "The user opens the workbook and the requested workflow."),
                ("THEN", "The application exposes the observable result for \"the requested workflow\"."),
            ])])
        files = compile_suite([templated("REQ-3-1-1"), templated("REQ-3-1-3")])
        self.assertIn("REQ-3-1-1.spec.ts", files)
        self.assertIn("REQ-3-1-3.spec.ts", files)
        self.assertEqual(files["REQ-3-1-3.spec.ts"].count("\ntest("), 1)


class DescriptivePhraseTests(unittest.TestCase):
    def test_descriptive_phrases_are_not_reach_targets(self):
        from scenario_tests import _descriptive
        for phrase in ("organization name/repository name", "organization identifier", "clone page entry",
                       "Last updated: <last updated value>"):
            self.assertTrue(_descriptive(phrase), phrase)
        for control in ("New team", "Sign in", "Password and authentication", "acme-docs", "sign in"):
            self.assertFalse(_descriptive(control), control)
        node = leaf("REQ-2-1-2", [("Scenario 1", [("GIVEN", SEED),
                    ("WHEN", "The user opens the organization page using the “organization identifier” "
                             "and the “New team” button."),
                    ("THEN", "The page shows “bob-reviewer”.")])])
        source = compile_suite([node]).get("REQ-2-1-2.spec.ts", "")
        self.assertNotIn("organization identifier", source)
