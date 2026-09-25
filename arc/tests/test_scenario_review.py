import json
import re
import unittest

from scenario_review import (allowed_literals, ancestor_context, behavior_test_titles, build_prompt, compile_reply,
                             grounded_behavior_test,
                             parse_failure_review, parse_reply,
                             prioritize_review_targets, review_targets, validate_proposal)
from scenario_tests import suite_fixtures


def leaf(node_id, scenarios, description=""):
    return {"id": node_id, "name": node_id, "type": "ATOMIC", "description": description,
            "scenarios": [{"name": f"{node_id}: {name}",
                           "steps": [{"keyword": k, "content": c} for k, c in steps]}
                          for name, steps in scenarios]}


SEED = ("The visitor starts at the application home page in a fresh unauthenticated browser session. "
        "The seeded data is account `alice-dev`, email `alice.dev@example.test`, password `Valid-password-123!`, "
        "repository `acme-docs`, pull request `Improve onboarding`.")

MERGE = leaf("REQ-6-5", [("Scenario 1", [
    ("GIVEN", SEED + " A signed-in maintainer has opened the “Conversation” page of a mergeable pull request."),
    ("WHEN", "The maintainer opens the pull request, chooses the merge method, clicks “Merge pull request”, "
             "and clicks “Confirm merge” in the confirmation box."),
    ("THEN", "The PR displays Merged and the `main` branch head is updated."),
]), ("Scenario 2", [
    ("GIVEN", SEED),
    ("WHEN", "The user clicks “Pull requests”."),
    ("THEN", "The page shows “Improve onboarding”."),
])], description="The pull request page has a “Pull requests” tab and shows Merged after merging.")


class ReviewTargetTests(unittest.TestCase):
    def test_only_action_then_assertion_tests_count_as_behavior(self):
        source = ("test('A: smoke [reach]', async ({ page }) => { await h.expectReachable(page, 'Open'); });\n"
                  "test('A: weak [model]', async ({ page }) => { await h.expectTextsVisible(page, ['Done']); });\n"
                  "test('A: backwards [script]', async ({ page }) => {\n"
                  "  await h.expectTextsVisible(page, ['Done']);\n  await h.clickNamed(page, 'Open');\n});\n"
                  "test('A: behavior [model]', async ({ page }) => {\n"
                  "  await h.clickNamed(page, 'Open');\n  await h.expectTextsVisible(page, ['Done']);\n});\n")
        self.assertEqual(behavior_test_titles(source), {"A: behavior [model]"})

    def test_navigation_setup_is_not_a_feature_action(self):
        source = ("test('A: weak [model]', async ({ page }) => {\n"
                  "  await h.openHome(page);\n"
                  "  await h.expectTextsVisible(page, ['Done']);\n});\n")
        self.assertEqual(behavior_test_titles(source), set())

    def test_download_assertion_can_perform_the_export_action(self):
        source = ("test('A: export [model]', async ({ page }) => {\n"
                  "  await h.expectDownload(page, 'Export', '.csv', ['East']);\n});\n")
        target = {"required_actions": ["Export"], "required_then_literal": "East"}
        self.assertTrue(grounded_behavior_test(source, "A: export [model]", target))

    def test_coverage_requires_explicit_when_and_then_evidence(self):
        target = {"required_actions": ["Open"], "required_then_literal": "Done"}
        wrong_result = ("test('A: example [model]', async ({ page }) => {\n"
                        "  await h.clickNamed(page, 'Open');\n"
                        "  await h.expectTextsVisible(page, ['Open']);\n});\n")
        self.assertIn("A: example [model]", behavior_test_titles(wrong_result))
        self.assertFalse(grounded_behavior_test(wrong_result, "A: example [model]", target))
        wrong_action = wrong_result.replace("h.clickNamed(page, 'Open')", "h.clickNamed(page, 'Other')")\
                                  .replace("['Open']", "['Done']")
        self.assertFalse(grounded_behavior_test(wrong_action, "A: example [model]", target))
        valid = wrong_result.replace("['Open']", "['Done']")
        self.assertTrue(grounded_behavior_test(valid, "A: example [model]", target))
        early_result = ("test('A: example [model]', async ({ page }) => {\n"
                        "  await h.expectTextsVisible(page, ['Done']);\n"
                        "  await h.clickNamed(page, 'Open');\n"
                        "  await h.expectTextsVisible(page, ['Open']);\n});\n")
        self.assertFalse(grounded_behavior_test(early_result, "A: example [model]", target))

    def test_failure_review_uses_one_structured_verdict(self):
        reply = ('Here is the review:\n```json\n'
                 '{"verdict":"oracle_dispute","evidence":"The \\"Done\\" assertion conflicts",'
                 '"scenarios":[]}\n```')
        self.assertEqual(parse_failure_review(reply)["evidence"], 'The "Done" assertion conflicts')
        self.assertEqual(parse_failure_review('{"verdict":"spec_error","evidence":"wrong"}')["scenarios"], [])
        self.assertIsNone(parse_failure_review('{"verdict":"spec_error","evidence":17}'))

    def test_should_target_only_scenarios_without_a_mechanical_script(self):
        targets = review_targets([MERGE], suite_fixtures([MERGE]))
        self.assertEqual([t["title"] for t in targets], ["REQ-6-5: Scenario 1"])
        self.assertEqual(targets[0]["node_id"], "REQ-6-5")
        self.assertIn("Merge pull request", targets[0]["allowed"])
        self.assertIn("acme-docs", targets[0]["allowed"])

    def test_full_plan_includes_mechanical_scripts_and_prioritizes_one_per_feature(self):
        first = leaf("A", [("one", [("WHEN", "Click “Open A”."), ("THEN", "Shows “Done A”.")]),
                           ("two", [("WHEN", "Click “Other A”."), ("THEN", "Shows “Other done”.")])])
        second = leaf("B", [("one", [("WHEN", "Click “Open B”."), ("THEN", "Shows “Done B”.")])])
        targets = review_targets([first, second], suite_fixtures([first, second]), include_all=True)
        self.assertEqual([t["node_id"] for t in prioritize_review_targets(targets)], ["A", "B", "A"])

    def test_duplicate_scenario_names_get_distinct_behavior_titles(self):
        node = leaf("A", [("Same", [("WHEN", "Clicks “One”."), ("THEN", "Shows “First”.")]),
                          ("Same", [("WHEN", "Clicks “Two”."), ("THEN", "Shows “Second”.")])])
        targets = review_targets([node], suite_fixtures([node]), include_all=True)
        self.assertEqual(len(targets), 2)
        self.assertEqual(len({target["title"] for target in targets}), 2)

    def test_full_plan_requires_the_when_actions_and_can_hover_a_seeded_record(self):
        node = leaf("REQ-N", [("Delete", [
            ("GIVEN", "The system contains note `Delete me`."),
            ("WHEN", "Hover over `Delete me`, click “More options”, and choose “Delete Note”."),
            ("THEN", "The note `Delete me` is removed."),
        ])])
        fixtures = suite_fixtures([node])
        target = review_targets([node], fixtures, include_all=True)[0]
        missing = {"confidence": 0.9, "steps": [
            {"op": "hover", "target": "Delete me"},
            {"op": "click", "target": "More options"},
            {"op": "expect_absent", "target": "Delete me"}]}
        from scenario_review import proposal_problems
        self.assertIn("Delete Note", " | ".join(proposal_problems(missing, target, fixtures)))
        missing["steps"].insert(2, {"op": "click", "target": "Delete Note"})
        self.assertEqual(proposal_problems(missing, target, fixtures), [])
        self.assertIn("h.hoverNamed(page, 'Delete me')", validate_proposal(missing, target, fixtures))

    def test_full_plan_rejects_an_assertion_about_an_existing_given_value(self):
        node = leaf("A", [("Create", [
            ("GIVEN", "The page already shows “Existing”."),
            ("WHEN", "The visitor clicks “Create”."),
            ("THEN", "The page shows “Created”."),
        ])])
        fixtures = suite_fixtures([node])
        target = review_targets([node], fixtures, include_all=True)[0]
        from scenario_review import proposal_problems
        proposal = {"confidence": 0.9, "steps": [
            {"op": "click", "target": "Create"},
            {"op": "expect_visible", "target": "Existing"}]}
        self.assertIn("Created", " | ".join(proposal_problems(proposal, target, fixtures)))
        proposal["steps"][-1]["target"] = "Created"
        self.assertEqual(proposal_problems(proposal, target, fixtures), [])
        proposal["steps"] = [{"op": "expect_visible", "target": "Created"},
                             {"op": "click", "target": "Create"},
                             {"op": "expect_visible", "target": "Existing"}]
        self.assertIn("Created", " | ".join(proposal_problems(proposal, target, fixtures)))

    def test_allowed_literals_include_context_and_fixtures(self):
        allowed = allowed_literals(MERGE, suite_fixtures([MERGE]), context="Visitors use “Sign in” on the home page.")
        for value in ("Sign in", "Pull requests", "Confirm merge", "Merged", "main", "alice-dev", "Valid-password-123!"):
            self.assertIn(value, allowed, value)

    def test_allowed_literals_include_controls_named_without_quotes(self):
        node = leaf("REQ-6-3-3", [], description=(
            "Click the button visually shown as “+” and accessibly named Add comment, and choose “Add single "
            "comment”. Activating one opens a single editor labeled Comment with Add single comment and Start a "
            "review buttons. Start a review displays the body and Pending review to its author."))
        allowed = allowed_literals(node, suite_fixtures([node]))
        for value in ("+", "Add comment", "Add single comment", "Comment"):
            self.assertIn(value, allowed, value)
        self.assertNotIn("Add comment, and choose", allowed)

    def test_prompt_lists_steps_literals_and_the_dsl(self):
        targets = review_targets([MERGE], suite_fixtures([MERGE]))
        prompt = build_prompt(targets, suite_fixtures([MERGE]))
        self.assertIn("REQ-6-5: Scenario 1", prompt)
        self.assertIn("Confirm merge", prompt)
        self.assertIn('"expect_visible"', prompt)
        self.assertIn("alice-dev", prompt)


class ProposalValidationTests(unittest.TestCase):
    def setUp(self):
        self.fixtures = suite_fixtures([MERGE])
        self.target = review_targets([MERGE], self.fixtures)[0]

    def test_should_emit_a_script_from_a_valid_proposal(self):
        proposal = {"title": "REQ-6-5: Scenario 1", "signed_in": True, "confidence": 0.8, "steps": [
            {"op": "click", "target": "acme-docs"},
            {"op": "click", "target": "Pull requests"},
            {"op": "click", "target": "Improve onboarding"},
            {"op": "click", "target": "Merge pull request"},
            {"op": "click", "target": "Confirm merge"},
            {"op": "expect_visible", "target": "Merged"},
        ]}
        source = validate_proposal(proposal, self.target, self.fixtures)
        self.assertIsNotNone(source)
        self.assertIn("h.signIn(page, 'alice-dev', 'Valid-password-123!')", source)
        self.assertIn("h.clickNamed(page, 'Pull requests')", source)
        self.assertIn("h.expectTextsVisible(page, ['Merged'])", source)
        self.assertIn("[model]", source)

    def test_should_reject_a_proposal_naming_a_control_the_requirement_never_quotes(self):
        proposal = {"title": "REQ-6-5: Scenario 1", "signed_in": True, "confidence": 0.9, "steps": [
            {"op": "click", "target": "Pull requests"},
            {"op": "click", "target": "Merge now"},
            {"op": "expect_visible", "target": "Merged"},
        ]}
        self.assertIsNone(validate_proposal(proposal, self.target, self.fixtures))

    def test_should_reject_low_confidence_unknown_ops_and_assertionless_proposals(self):
        base = {"title": "REQ-6-5: Scenario 1", "signed_in": True, "steps": [
            {"op": "click", "target": "Pull requests"}, {"op": "expect_visible", "target": "Merged"}]}
        self.assertIsNone(validate_proposal({**base, "confidence": 0.3}, self.target, self.fixtures))
        self.assertIsNone(validate_proposal({**base, "confidence": 0.9, "steps": [
            {"op": "drag", "target": "Pull requests"}, {"op": "expect_visible", "target": "Merged"}]},
            self.target, self.fixtures))
        self.assertIsNone(validate_proposal({**base, "confidence": 0.9, "steps": [
            {"op": "click", "target": "Pull requests"}]}, self.target, self.fixtures))

    def test_fill_values_must_be_fixtures_seeds_or_quoted(self):
        good = {"title": "REQ-6-5: Scenario 1", "signed_in": False, "confidence": 0.9, "steps": [
            {"op": "fill", "target": "Pull requests", "value": "acme-docs"},
            {"op": "press", "key": "Enter"},
            {"op": "expect_visible", "target": "Improve onboarding"}]}
        source = validate_proposal(good, self.target, self.fixtures)
        self.assertIn("h.fillField(page, 'Pull requests', 'acme-docs')", source)
        self.assertIn("h.pressKey(page, 'Enter')", source)
        bad = {**good, "steps": [{"op": "fill", "target": "Pull requests", "value": "made up"},
                                 {"op": "expect_visible", "target": "Merged"}]}
        self.assertIsNone(validate_proposal(bad, self.target, self.fixtures))


class AncestorContextTests(unittest.TestCase):
    def test_leaves_inherit_their_folder_descriptions(self):
        tree = {"id": "ROOT", "type": "FOLDER", "description": "Visitors use “Sign in”.", "children": [
            {"id": "REQ-1", "type": "FOLDER", "description": "Account menu shows “Sign out”.", "children": [
                {"id": "REQ-1-1", "type": "ATOMIC", "description": "leaf"}]},
            {"id": "REQ-2", "type": "ATOMIC", "description": "other leaf"}]}
        context = ancestor_context(tree)
        self.assertIn("Sign in", context["REQ-1-1"])
        self.assertIn("Sign out", context["REQ-1-1"])
        self.assertNotIn("Sign out", context["REQ-2"])
        self.assertEqual(ancestor_context(None), {})


class ReplyTests(unittest.TestCase):
    def test_should_parse_json_inside_a_fenced_reply(self):
        reply = "Here you go:\n```json\n" + json.dumps({"scenarios": [{"title": "x", "steps": []}]}) + "\n```"
        self.assertEqual(parse_reply(reply), [{"title": "x", "steps": []}])
        self.assertIsNone(parse_reply("no json here"))

    def test_compile_reply_groups_valid_scripts_by_node_and_reports_drops(self):
        fixtures = suite_fixtures([MERGE])
        targets = review_targets([MERGE], fixtures)
        reply = json.dumps({"scenarios": [
            {"title": "REQ-6-5: Scenario 1", "signed_in": True, "confidence": 0.9, "steps": [
                {"op": "click", "target": "Pull requests"}, {"op": "expect_visible", "target": "Merged"}]},
            {"title": "REQ-6-5: Scenario 1", "signed_in": True, "confidence": 0.9, "steps": [
                {"op": "click", "target": "Nope"}, {"op": "expect_visible", "target": "Merged"}]},
            {"title": "REQ-9-9: unknown", "signed_in": False, "confidence": 0.9, "steps": [
                {"op": "click", "target": "Pull requests"}, {"op": "expect_visible", "target": "Merged"}]},
        ]})
        scripts, dropped = compile_reply(reply, targets, fixtures)
        self.assertEqual(list(scripts), ["REQ-6-5"])
        self.assertEqual(len(scripts["REQ-6-5"]), 1)
        self.assertEqual(len(dropped), 2)


if __name__ == "__main__":
    unittest.main()


class RejectionFeedbackTests(unittest.TestCase):
    """A rejected proposal gets one retry with the exact reason, not silence."""

    def setUp(self):
        from scenario_review import proposal_problems, retry_prompt
        self.problems = proposal_problems
        self.retry_prompt = retry_prompt
        self.fixtures = suite_fixtures([MERGE])
        self.target = review_targets([MERGE], self.fixtures)[0]

    def test_problems_name_the_offending_literal_op_and_missing_assertion(self):
        proposal = {"title": "REQ-6-5: Scenario 1", "signed_in": True, "confidence": 0.9, "steps": [
            {"op": "click", "target": "Merge now"}, {"op": "drag", "target": "Pull requests"},
            {"op": "fill", "target": "Pull requests", "value": "made up"}]}
        problems = self.problems(proposal, self.target, self.fixtures)
        joined = " | ".join(problems)
        self.assertIn("Merge now", joined)
        self.assertIn("drag", joined)
        self.assertIn("made up", joined)
        self.assertIn("assert", joined.lower())
        self.assertEqual(self.problems({"title": "x", "confidence": 0.9, "steps": [
            {"op": "click", "target": "Pull requests"}, {"op": "expect_visible", "target": "Merged"}]},
            self.target, self.fixtures), [])

    def test_compile_reply_reports_retryable_rejections_with_reasons(self):
        reply = json.dumps({"scenarios": [
            {"title": "REQ-6-5: Scenario 1", "signed_in": True, "confidence": 0.9, "steps": [
                {"op": "click", "target": "Nope"}, {"op": "expect_visible", "target": "Merged"}]}]})
        scripts, dropped, retryable = compile_reply(reply, [self.target], self.fixtures, with_retryable=True)
        self.assertEqual(scripts, {})
        self.assertEqual([r["title"] for r in retryable], ["REQ-6-5: Scenario 1"])
        self.assertIn("Nope", retryable[0]["reasons"][0])
        skipped = json.dumps({"scenarios": [{"title": "REQ-6-5: Scenario 1", "skip": "needs a second account"}]})
        _, dropped, retryable = compile_reply(skipped, [self.target], self.fixtures, with_retryable=True)
        self.assertEqual(retryable, [])  # the model's own skip is final
        self.assertIn("second account", dropped[0])

    def test_retry_prompt_quotes_the_reasons_and_the_allowed_literals(self):
        prompt = self.retry_prompt([{"title": "REQ-6-5: Scenario 1", "reasons": ["click target \"Nope\" is not an allowed literal"]}],
                                   [self.target], self.fixtures)
        self.assertIn("Nope", prompt)
        self.assertIn("not an allowed literal", prompt)
        self.assertIn("Confirm merge", prompt)
        self.assertIn("REQ-6-5: Scenario 1", prompt)


class EmittedSourceTests(unittest.TestCase):
    """The local run github-req1-local: every model-proposed test ended in `}});`
    and failed to load; the load gate dropped them all. Emitted TS must be
    syntactically closed."""

    def test_emitted_test_is_balanced_and_closed(self):
        fixtures = suite_fixtures([MERGE])
        target = review_targets([MERGE], fixtures)[0]
        source = validate_proposal({"title": "REQ-6-5: Scenario 1", "signed_in": True, "confidence": 0.9, "steps": [
            {"op": "click", "target": "Pull requests"}, {"op": "expect_visible", "target": "Merged"}]}, target, fixtures)
        self.assertTrue(source.endswith("\n});"), source[-40:])
        self.assertEqual(source.count("{"), source.count("}"))
        self.assertEqual(source.count("("), source.count(")"))


class GeneratedValueTests(unittest.TestCase):
    """Scenarios that create records need values the requirement does not
    quote: the DSL offers placeholders the harness expands, never the fixture
    account (registering `alice-dev` again fails once the seed exists)."""

    def test_placeholders_are_allowed_for_fill_values_and_assertions(self):
        from scenario_review import PLACEHOLDERS
        register = leaf("REQ-1-1-1", [("Scenario 1", [
            ("GIVEN", SEED + " The visitor clicks “Create an account”."),
            ("WHEN", "The visitor enters a compliant username, a compliant email and password, checks "
                     "“I agree” and clicks “Create account”."),
            ("THEN", "The account menu displays the new username."),
        ])], description="Fields “Username”, “Email”, “Password”, “Confirm password”.")
        fixtures = suite_fixtures([register])
        target = review_targets([register], fixtures)[0]
        for name in ("$NEW_USERNAME", "$NEW_EMAIL", "$NEW_PASSWORD", "$TEXT"):
            self.assertIn(name, PLACEHOLDERS)
        proposal = {"title": "REQ-1-1-1: Scenario 1", "signed_in": False, "confidence": 0.9, "steps": [
            {"op": "click", "target": "Create an account"},
            {"op": "fill", "target": "Username", "value": "$NEW_USERNAME"},
            {"op": "fill", "target": "Email", "value": "$NEW_EMAIL"},
            {"op": "fill", "target": "Password", "value": "$NEW_PASSWORD"},
            {"op": "fill", "target": "Confirm password", "value": "$NEW_PASSWORD"},
            {"op": "check", "target": "I agree"},
            {"op": "click", "target": "Create account"},
            {"op": "expect_visible", "target": "$NEW_USERNAME"},
        ]}
        source = validate_proposal(proposal, target, fixtures)
        self.assertIsNotNone(source)
        self.assertNotIn("$NEW_USERNAME", source)
        self.assertNotIn("alice-dev", source)
        username = re.search(r"h\.fillField\(page, 'Username', '([^']+)'\)", source).group(1)
        self.assertRegex(username, r"^[a-z0-9-]{3,39}$")
        self.assertIn(f"h.expectTextsVisible(page, ['{username}'])", source)
        password = re.search(r"h\.fillField\(page, 'Password', '([^']+)'\)", source).group(1)
        self.assertGreaterEqual(len(password), 12)
        self.assertIn(f"h.fillField(page, 'Confirm password', '{password}')", source)
        email = re.search(r"h\.fillField\(page, 'Email', '([^']+)'\)", source).group(1)
        self.assertIn("@", email)
        # Different scenarios get different values so parallel tests do not collide.
        other = dict(proposal, title="REQ-1-1-1: Scenario 1")
        self.assertIn(username, validate_proposal(other, target, fixtures))
        self.assertIn("$NEW_USERNAME", build_prompt([target], fixtures))

    def test_placeholder_target_for_click_is_still_rejected(self):
        from scenario_review import proposal_problems
        fixtures = suite_fixtures([MERGE])
        target = review_targets([MERGE], fixtures)[0]
        problems = proposal_problems({"title": "x", "confidence": 0.9, "steps": [
            {"op": "click", "target": "$TEXT"}, {"op": "expect_visible", "target": "Merged"}]}, target, fixtures)
        self.assertTrue(any("$TEXT" in p for p in problems))


class SpreadsheetOpsTests(unittest.TestCase):
    """The sheet task needs cell-level operations; without them the model
    skipped all 100 scenarios ("no input controls listed for the concrete values")."""

    def _target(self):
        node = leaf("REQ-3-1-1", [("REQ-3-1-1 -the requested workflow", [
            ("GIVEN", "The visitor starts at the application home page. The evaluation seed contains the seeded "
                      "workbook `Q3 Sales`, cells `A1=2`, `B1=3`, and formulas `=A1+B1`."),
            ("WHEN", "The user opens the workbook home page, clicks the visible `Q3 Sales` workbook entry, and the "
                     "requested workflow with concrete values `East`, `1200`."),
            ("THEN", "The application exposes the observable result for \"the requested workflow\"."),
        ])], description='Pressing Enter commits; the "Formula bar" shows the original formula.')
        fixtures = suite_fixtures([node])
        return review_targets([node], fixtures)[0], fixtures

    def test_cell_ops_with_seeded_values_and_key_combos_are_accepted(self):
        target, fixtures = self._target()
        proposal = {"title": "REQ-3-1-1 -the requested workflow", "signed_in": False, "confidence": 0.9, "steps": [
            {"op": "click", "target": "Q3 Sales"},
            {"op": "cell_click", "target": "A1"},
            {"op": "cell_type", "target": "C1", "value": "=A1+B1"},
            {"op": "press", "key": "Enter"},
            {"op": "cell_click", "target": "C1"},
            {"op": "press", "key": "Control+C"},
            {"op": "expect_cell", "target": "C1", "value": "5"},
            {"op": "expect_role", "role": "textbox", "target": "Formula bar"},
        ]}
        from scenario_review import proposal_problems
        self.assertEqual(proposal_problems(proposal, target, fixtures), [])
        source = validate_proposal(proposal, target, fixtures)
        self.assertIn("h.clickCell(page, 'A1')", source)
        self.assertIn("h.typeInCell(page, 'C1', '=A1+B1')", source)
        self.assertIn("h.pressKey(page, 'Control+C')", source)
        self.assertIn("h.expectCell(page, 'C1', '5')", source)
        self.assertIn("h.expectRole(page, 'textbox', 'Formula bar')", source)

    def test_expect_cell_counts_as_an_assertion(self):
        from scenario_review import proposal_problems
        target, fixtures = self._target()
        self.assertEqual(proposal_problems({"title": "REQ-3-1-1 -the requested workflow", "confidence": 0.9, "steps": [
            {"op": "click", "target": "Q3 Sales"}, {"op": "expect_cell", "target": "A1", "value": "2"}]},
            target, fixtures), [])

    def test_cell_targets_must_be_coordinates_and_values_known(self):
        from scenario_review import proposal_problems
        target, fixtures = self._target()
        bad = {"title": "REQ-3-1-1 -the requested workflow", "confidence": 0.9, "steps": [
            {"op": "cell_click", "target": "Region"},
            {"op": "cell_type", "target": "A1", "value": "made up text"},
            {"op": "press", "key": "F13"},
            {"op": "expect_cell", "target": "A1", "value": "2"}]}
        problems = proposal_problems(bad, target, fixtures)
        joined = " | ".join(problems)
        self.assertIn("Region", joined)
        self.assertIn("made up text", joined)
        self.assertIn("F13", joined)

    def test_prompt_explains_templated_workflows_and_cell_ops(self):
        target, fixtures = self._target()
        prompt = build_prompt([target], fixtures)
        self.assertIn("the requested workflow", prompt)
        self.assertIn('"cell_type"', prompt)
        self.assertIn("Control+C", prompt)
        # v9.2.1 run 4aff4d2f6cd4: 58/100 skipped as "cell coordinates not in allowed literals",
        # "cannot simulate clipboard", "which cell is not specified".
        self.assertIn("ALWAYS allowed", prompt)
        self.assertIn("set_clipboard", prompt)
        self.assertIn("empty\nfresh browser clipboard is not a valid fixture", prompt)
        self.assertIn("not a reason to skip", prompt)

    def test_external_paste_requires_a_clipboard_fixture(self):
        from scenario_review import proposal_problems
        target, fixtures = self._target()
        paste = {"title": target["title"], "confidence": 0.9, "steps": [
            {"op": "click", "target": "Q3 Sales"},
            {"op": "cell_click", "target": "D1"},
            {"op": "press", "key": "Control+V"},
            {"op": "expect_cell", "target": "D1", "value": "East"},
        ]}
        self.assertIn("no clipboard source", " | ".join(proposal_problems(paste, target, fixtures)))
        paste["steps"].insert(2, {"op": "set_clipboard", "value": "$TABLE"})
        source = validate_proposal(paste, target, fixtures)
        self.assertIsNotNone(source)
        self.assertIn("h.setClipboardText(page, 'East\t1200\\nNorth\t800')", source)
        paste["steps"][-1]["value"] = "North"
        self.assertIn("pasted D1 should be 'East'", " | ".join(proposal_problems(paste, target, fixtures)))

    def test_import_rejects_a_conflicting_old_cell_value(self):
        from scenario_review import proposal_problems
        node = leaf("REQ-1-3-1", [("Import", [
            ("GIVEN", "The evaluation seed contains the seeded workbook `Q3 Sales`, cell A1 value `Region`."),
            ("WHEN", "The user follows the requested workflow using “Import CSV”, “CSV file”, "
                     "and “Confirm import”."),
            ("THEN", "A new workbook opens with imported cells."),
        ])], description='Import CSV accepts a file in “CSV file” and creates a new workbook.')
        fixtures = suite_fixtures([node])
        target = review_targets([node], fixtures)[0]
        proposal = {"title": target["title"], "confidence": 0.9, "steps": [
            {"op": "click", "target": "Import CSV"},
            {"op": "upload", "target": "CSV file", "value": "$CSV"},
            {"op": "click", "target": "Confirm import"},
            {"op": "expect_cell", "target": "A1", "value": "Region"},
        ]}
        self.assertIn("after CSV import A1 should be 'East'", " | ".join(proposal_problems(proposal, target, fixtures)))
        proposal["steps"].insert(3, {"op": "cell_type", "target": "A1", "value": "Region"})
        proposal["steps"].insert(4, {"op": "press", "key": "Enter"})
        self.assertEqual(proposal_problems(proposal, target, fixtures), [])

    def test_reopening_seeded_workbook_allows_its_original_cell_value(self):
        from scenario_review import proposal_problems
        node = leaf("REQ-1-3-1", [("Import", [
            ("GIVEN", "The seeded workbook `Q3 Sales` has cell A1 value `Region` and rows `East/1200`."),
            ("WHEN", "The user clicks “Import CSV”, uploads through “CSV file”, and clicks “Confirm import”."),
            ("THEN", "The imported workbook opens."),
        ])], description='The home page has “Import CSV”, “CSV file”, and “Confirm import”.')
        fixtures = suite_fixtures([node])
        target = review_targets([node], fixtures)[0]
        proposal = {"title": target["title"], "confidence": 0.9, "steps": [
            {"op": "click", "target": "Import CSV"},
            {"op": "upload", "target": "CSV file", "value": "$CSV"},
            {"op": "click", "target": "Confirm import"},
            {"op": "open", "target": "Q3 Sales"},
            {"op": "expect_visible", "target": "Region"},
        ]}
        self.assertEqual(proposal_problems(proposal, target, fixtures), [])

    def test_imported_file_name_has_its_own_assertion_placeholder(self):
        from scenario_review import proposal_problems
        node = leaf("REQ-1-3-1", [("Import", [
            ("GIVEN", "The seeded workbook `Q3 Sales` has rows `East/1200` and `North/800`."),
            ("WHEN", "The user clicks “Import CSV”, uploads through “CSV file”, and clicks “Confirm import”."),
            ("THEN", "A new workbook is named after the CSV file."),
        ])], description='The home page has “Import CSV”, “CSV file”, and “Confirm import”.')
        fixtures = suite_fixtures([node])
        target = review_targets([node], fixtures)[0]
        proposal = {"title": target["title"], "confidence": 0.9, "steps": [
            {"op": "click", "target": "Import CSV"},
            {"op": "upload", "target": "CSV file", "value": "$CSV"},
            {"op": "click", "target": "Confirm import"},
            {"op": "expect_visible", "target": "$NEW_NAME"},
        ]}
        self.assertIn("never entered", " | ".join(proposal_problems(proposal, target, fixtures)))
        proposal["steps"][-1]["target"] = "$CSV_NAME"
        self.assertEqual(proposal_problems(proposal, target, fixtures), [])
        self.assertIn("h.expectTextsVisible(page, ['derived-import'])", validate_proposal(proposal, target, fixtures))


class ProposalIdentityTests(unittest.TestCase):
    """v9.2.2 sheet run cce3f5ad4f21: 71/100 proposals rejected although many were
    valid -- the model shortened the long, duplicated template titles, so they
    matched no target ("not a requested scenario"). Proposals are matched by a
    short id the prompt assigns; identical scenarios share one target."""

    def _node(self):
        given = ("The visitor starts at the application home page. The evaluation seed contains the seeded "
                 "workbook `Q3 Sales`, cells `A1=2`.")
        when = ("The user opens the workbook home page, clicks the visible `Q3 Sales` workbook entry, and the "
                "requested workflow with concrete values `East`.")
        then = "The application exposes the observable result for \"the requested workflow\"."
        return leaf("REQ-4-1-1", [("REQ-4-1-1 -the requested workflow,the requested workflow", [
            ("GIVEN", given), ("WHEN", when), ("THEN", then)]),
            ("REQ-4-1-1 -the requested workflow,the requested workflow", [("GIVEN", given), ("WHEN", when), ("THEN", then)]),
            ("REQ-4-1-1 -the requested workflow", [("GIVEN", given), ("WHEN", when + " Extra."), ("THEN", then)])],
            description='The "Formula bar" shows the formula.')

    def test_identical_scenarios_collapse_and_targets_carry_ids(self):
        node = self._node()
        targets = review_targets([node], suite_fixtures([node]))
        self.assertEqual(len(targets), 2)
        self.assertEqual([t["id"] for t in targets], ["S1", "S2"])
        prompt = build_prompt(targets, suite_fixtures([node]))
        self.assertIn("[S1]", prompt)
        self.assertIn('"id"', prompt)

    def test_replies_match_by_id_even_with_a_mangled_title(self):
        node = self._node()
        fixtures = suite_fixtures([node])
        targets = review_targets([node], fixtures)
        reply = json.dumps({"scenarios": [
            {"id": "S1", "title": "the requested workflow", "signed_in": False, "confidence": 0.9, "steps": [
                {"op": "click", "target": "Q3 Sales"}, {"op": "expect_cell", "target": "A1", "value": "2"}]},
            {"id": "S2", "title": "", "signed_in": False, "confidence": 0.9, "steps": [
                {"op": "click", "target": "Nope"}, {"op": "expect_cell", "target": "A1", "value": "2"}]},
        ]})
        scripts, dropped, retryable = compile_reply(reply, targets, fixtures, with_retryable=True)
        self.assertEqual(len(scripts["REQ-4-1-1"]), 1)
        self.assertIn("[model]", scripts["REQ-4-1-1"][0])
        self.assertEqual([r["id"] for r in retryable], ["S2"])
        from scenario_review import retry_prompt
        retry = retry_prompt(retryable, targets, fixtures)
        self.assertIn("[S2]", retry)
        self.assertIn("Nope", retry)


class PlaceholderAllowedLiteralTests(unittest.TestCase):
    def test_allowed_literals_carry_prefixes_not_placeholders(self):
        node = leaf("REQ-1-1-1", [], description='Each record displays "Last updated: <last updated value>" and '
                                                  'a button named "Edit <cell coordinate>".')
        allowed = allowed_literals(node, suite_fixtures([node]))
        self.assertIn("Last updated:", allowed)
        self.assertIn("Edit", allowed)
        self.assertFalse(any("<" in value for value in allowed), allowed)
        self.assertIn("never expect the placeholder", build_prompt(review_targets([node], suite_fixtures([node])) or [
            {"id": "S1", "node_id": "x", "title": "t", "name": "n", "description": "", "steps": [], "allowed": []}],
            suite_fixtures([node])))


class SecretEchoTests(unittest.TestCase):
    def test_a_typed_code_is_not_an_acceptable_visible_assertion(self):
        from scenario_review import proposal_problems
        node = leaf("REQ-1-1-3", [("Scenario 1", [
            ("GIVEN", SEED), ("WHEN", "The visitor enters the code “123456” in “Verification code” and clicks “Reset password”."),
            ("THEN", "The page shows “Password updated”.")])])
        fixtures = suite_fixtures([node])
        target = review_targets([node], fixtures)[0]
        bad = {"title": target["title"], "confidence": 0.9, "steps": [
            {"op": "fill", "target": "Verification code", "value": "123456"},
            {"op": "click", "target": "Reset password"},
            {"op": "expect_visible", "target": "123456"}]}
        self.assertTrue(any("typed into a password/code field" in p for p in proposal_problems(bad, target, fixtures)))
        good = dict(bad, steps=bad["steps"][:2] + [{"op": "expect_visible", "target": "Password updated"}])
        self.assertEqual(proposal_problems(good, target, fixtures), [])


class FileOpsTests(unittest.TestCase):
    def _target(self):
        node = leaf("REQ-1-3-1", [("REQ-1-3-1 -the requested workflow", [
            ("GIVEN", "The visitor starts at the application home page. The evaluation seed contains the seeded "
                      "workbook `Q3 Sales`, rows `East/1200` and `North/800`."),
            ("WHEN", "The user opens the workbook home page and the requested workflow."),
            ("THEN", "The application exposes the observable result for \"the requested workflow\"."),
        ])], description='The home page has a button "Import CSV", a file input "CSV file", a button '
                         '"Confirm import" and a button "Export CSV".')
        fixtures = suite_fixtures([node])
        return review_targets([node], fixtures)[0], fixtures

    def test_upload_and_download_steps_are_scripted(self):
        target, fixtures = self._target()
        proposal = {"title": target["title"], "confidence": 0.9, "steps": [
            {"op": "click", "target": "Import CSV"},
            {"op": "upload", "target": "CSV file", "value": "$CSV"},
            {"op": "click", "target": "Confirm import"},
            {"op": "expect_visible", "target": "East"},
            {"op": "expect_download", "target": "Export CSV", "value": ".csv", "contains": ["East"]}]}
        from scenario_review import proposal_problems
        self.assertEqual(proposal_problems(proposal, target, fixtures), [])
        source = validate_proposal(proposal, target, fixtures)
        self.assertIn("h.uploadFile(page, 'CSV file', 'East,1200\\nNorth,800')", source)
        self.assertIn("h.expectDownload(page, 'Export CSV', '.csv', ['East'])", source)

    def test_export_requires_downloaded_seed_content(self):
        target, fixtures = self._target()
        target["name"] = "Export the Current Worksheet as CSV"
        target["seed_kinds"] = [("cell A1 value", "Region")]
        target["allowed"].append("Region")
        proposal = {"confidence": 0.9, "steps": [
            {"op": "expect_download", "target": "Export CSV", "value": ".csv"}]}
        from scenario_review import proposal_problems
        self.assertTrue(any("downloaded contents" in problem
                            for problem in proposal_problems(proposal, target, fixtures)))
        proposal["steps"][0]["contains"] = ["Region"]
        self.assertEqual(proposal_problems(proposal, target, fixtures), [])
        proposal["steps"].insert(0, {"op": "click", "target": "Export CSV"})
        self.assertTrue(any("already clicks" in problem for problem in proposal_problems(proposal, target, fixtures)))

    def test_clone_copy_requires_clipboard_value_for_each_protocol(self):
        target, fixtures = self._target()
        target["allowed"].extend(["acme-docs", "Code", "HTTPS", "SSH", "Copy clone value", "Copied"])
        target["seed_kinds"] = [("public repository", "acme-docs")]
        proposal = {"confidence": 0.9, "steps": [
            {"op": "click", "target": "Code"},
            {"op": "click", "target": "HTTPS"},
            {"op": "click", "target": "Copy clone value"},
            {"op": "expect_visible", "target": "Copied"},
            {"op": "click", "target": "SSH"},
            {"op": "click", "target": "Copy clone value"},
            {"op": "expect_clipboard", "target": "acme-docs", "protocol": "SSH"},
        ]}
        from scenario_review import proposal_problems
        self.assertTrue(any("each Copy clone value" in problem
                            for problem in proposal_problems(proposal, target, fixtures)))
        proposal["steps"].insert(3, {"op": "expect_clipboard", "target": "acme-docs", "protocol": "HTTPS"})
        self.assertEqual(proposal_problems(proposal, target, fixtures), [])
        self.assertIn("h.expectClipboard(page, 'acme-docs', 'HTTPS')", validate_proposal(proposal, target, fixtures))
        proposal["steps"][3]["target"] = "Copied"
        self.assertTrue(any("seeded repository name" in problem
                            for problem in proposal_problems(proposal, target, fixtures)))
        proposal["steps"][3]["target"] = "acme-docs"
        proposal["steps"][3]["protocol"] = "SSH"
        self.assertTrue(any("each Copy clone value" in problem
                            for problem in proposal_problems(proposal, target, fixtures)))

    def test_pivot_source_text_is_not_a_result_assertion(self):
        target, fixtures = self._target()
        target["name"] = "Create and Refresh a Basic Pivot Table"
        target["allowed"].extend(["Apply", "East"])
        proposal = {"confidence": 0.9, "steps": [
            {"op": "click", "target": "Apply"}, {"op": "expect_visible", "target": "East"}]}
        from scenario_review import proposal_problems
        self.assertTrue(any("aggregation evidence" in problem
                            for problem in proposal_problems(proposal, target, fixtures)))
        proposal["steps"].append({"op": "expect_cell", "target": "B2", "value": "1200"})
        self.assertEqual(proposal_problems(proposal, target, fixtures), [])

    def test_template_wording_is_never_an_allowed_literal(self):
        target, _ = self._target()
        self.assertFalse(any("requested workflow" in value for value in target["allowed"]), target["allowed"])


class HomeAndSeedRowTests(unittest.TestCase):
    def _target(self):
        node = leaf("REQ-1-1-1", [("REQ-1-1-1 -the requested workflow", [
            ("GIVEN", "The evaluation seed contains the seeded workbook `Q3 Sales`, rows `East/1200` and `North/800`."),
            ("WHEN", "The user opens the workbook home page and the requested workflow."),
            ("THEN", "The application exposes the observable result for \"the requested workflow\"."),
        ])], description='The home page lists workbooks; a button "Delete row" removes the selected row.')
        fixtures = suite_fixtures([node])
        return review_targets([node], fixtures)[0], fixtures

    def test_home_page_open_needs_no_literal_and_maps_to_open_home(self):
        target, fixtures = self._target()
        proposal = {"title": target["title"], "confidence": 0.9, "steps": [
            {"op": "open", "target": "workbook home page"},
            {"op": "click", "target": "Q3 Sales"},
            {"op": "expect_visible", "target": "Delete row"}]}
        source = validate_proposal(proposal, target, fixtures)
        self.assertIn("await h.openHome(page);", source)
        self.assertNotIn("openNamed(page, 'workbook home page')", source)

    def test_seed_rows_are_asserted_as_their_cells(self):
        target, fixtures = self._target()
        proposal = {"title": target["title"], "confidence": 0.9, "steps": [
            {"op": "open", "target": "Q3 Sales"},
            {"op": "click", "target": "Delete row"},
            {"op": "expect_absent", "target": "East/1200"},
            {"op": "expect_visible", "target": "North/800"}]}
        source = validate_proposal(proposal, target, fixtures)
        self.assertIn("h.expectTextsVisible(page, ['North', '800']);", source)
        self.assertIn("h.expectAbsent(page, 'East');", source)
        self.assertNotIn("East/1200", source)


class SeededAbsenceTests(unittest.TestCase):
    def _target(self):
        node = leaf("REQ-3-1-1", [("REQ-3-1-1 -Escape the requested workflow", [
            ("GIVEN", "The evaluation seed contains the seeded workbook `Q3 Sales`, rows `East/1200` and `North/800`."),
            ("WHEN", "The user opens the workbook and the requested workflow."),
            ("THEN", "The application exposes the observable result for \"the requested workflow\"."),
        ])], description='A button "Delete row" removes the selected row.')
        fixtures = suite_fixtures([node])
        return review_targets([node], fixtures)[0], fixtures

    def test_absence_of_a_seeded_value_without_removal_is_rejected(self):
        from scenario_review import proposal_problems
        target, fixtures = self._target()
        proposal = {"title": target["title"], "confidence": 0.9, "steps": [
            {"op": "open", "target": "Q3 Sales"},
            {"op": "cell_type", "target": "D1", "value": "East"},
            {"op": "press", "key": "Escape"},
            {"op": "expect_absent", "target": "East"}]}
        problems = proposal_problems(proposal, target, fixtures)
        self.assertTrue(any("seeded value" in p for p in problems), problems)

    def test_absence_after_a_removing_step_is_accepted(self):
        from scenario_review import proposal_problems
        target, fixtures = self._target()
        proposal = {"title": target["title"], "confidence": 0.9, "steps": [
            {"op": "open", "target": "Q3 Sales"},
            {"op": "cell_click", "target": "A2"},
            {"op": "click", "target": "Delete row"},
            {"op": "expect_absent", "target": "East/1200"}]}
        self.assertEqual(proposal_problems(proposal, target, fixtures), [])


class NewNamePlaceholderTests(unittest.TestCase):
    def test_new_name_placeholder_creates_and_asserts_a_unique_record_name(self):
        node = leaf("REQ-3-2-1", [("REQ-3-2-1: Create a Repository - Scenario 1", [
            ("GIVEN", "Seed values: account `alice-dev`, email `alice.dev@example.test`, password `Valid-password-123!`."),
            ("WHEN", "The user opens “New repository”, fills “Repository name” and clicks "
                     "“Create repository”."),
            ("THEN", "The repository page shows the new name."),
        ])])
        fixtures = suite_fixtures([node])
        target = review_targets([node], fixtures)[0]
        proposal = {"title": target["title"], "confidence": 0.9, "signed_in": True, "steps": [
            {"op": "open", "target": "New repository"},
            {"op": "fill", "target": "Repository name", "value": "$NEW_NAME"},
            {"op": "click", "target": "Create repository"},
            {"op": "expect_visible", "target": "$NEW_NAME"}]}
        source = validate_proposal(proposal, target, fixtures)
        names = re.findall(r"derived-[0-9a-f]{6}", source)
        self.assertEqual(len(names), 2, source)
        self.assertEqual(names[0], names[1])
        self.assertNotIn("$NEW_NAME", source)
        self.assertIn("$NEW_NAME", build_prompt([target], fixtures))

    def test_fixture_account_is_not_a_new_record_name(self):
        from scenario_review import proposal_problems
        node = leaf("REQ-3-2-2", [("REQ-3-2-2: Fork a Repository - Scenario 1", [
            ("GIVEN", "Seed values: account `alice-dev`, email `alice.dev@example.test`, password `Valid-password-123!`, "
                      "repository `acme-docs`."),
            ("WHEN", "The user clicks “Fork”, fills “Repository name” and clicks “Create fork”."),
            ("THEN", "The page shows “Forked from”."),
        ])])
        fixtures = suite_fixtures([node])
        target = review_targets([node], fixtures)[0]
        steps = [{"op": "open", "target": "acme-docs"}, {"op": "click", "target": "Fork"},
                 {"op": "fill", "target": "Repository name", "value": "alice-dev"},
                 {"op": "click", "target": "Create fork"}, {"op": "expect_visible", "target": "Forked from"}]
        problems = proposal_problems({"title": target["title"], "confidence": 0.9, "signed_in": True, "steps": steps},
                                     target, fixtures)
        self.assertTrue(any("$NEW_NAME" in p for p in problems), problems)
        steps[2]["value"] = "$NEW_NAME"
        self.assertEqual(proposal_problems({"title": target["title"], "confidence": 0.9, "signed_in": True,
                                            "steps": steps}, target, fixtures), [])


class VacuousAssertionTests(unittest.TestCase):
    def _target(self):
        node = leaf("REQ-2-1-1", [("REQ-2-1-1 -the requested workflow", [
            ("GIVEN", "The evaluation seed contains the seeded workbook `Q3 Sales` with worksheet `Sheet1`."),
            ("WHEN", "The user opens the workbook and the requested workflow."),
            ("THEN", "A worksheet named \"Sheet2\" appears."),
        ])], description='The editor has a button "Add worksheet".')
        fixtures = suite_fixtures([node])
        return review_targets([node], fixtures)[0], fixtures

    def test_asserting_only_the_clicked_control_is_rejected(self):
        from scenario_review import proposal_problems
        target, fixtures = self._target()
        steps = [{"op": "open", "target": "Q3 Sales"}, {"op": "click", "target": "Add worksheet"},
                 {"op": "expect_visible", "target": "Add worksheet"}, {"op": "expect_visible", "target": "Q3 Sales"}]
        problems = proposal_problems({"title": target["title"], "confidence": 0.9, "steps": steps}, target, fixtures)
        self.assertTrue(any("clicked" in p for p in problems), problems)
        steps.append({"op": "expect_visible", "target": "Sheet2"})
        self.assertEqual(proposal_problems({"title": target["title"], "confidence": 0.9, "steps": steps},
                                           target, fixtures), [])

    def test_a_typed_name_shown_after_create_is_evidence(self):
        from scenario_review import proposal_problems
        node = leaf("REQ-2-2-1", [("REQ-2-2-1: Create an Organization Team - Scenario 1", [
            ("GIVEN", "Seed values: account `alice-dev`, email `alice.dev@example.test`, password `Valid-password-123!`, organization `Acme Demo`."),
            ("WHEN", "The user opens “Teams”, clicks “New team”, fills “Team name” with "
                     "“mobile-team” and clicks “Create team”."),
            ("THEN", "The team list shows the new team."),
        ])])
        fixtures = suite_fixtures([node])
        target = review_targets([node], fixtures)[0]
        steps = [{"op": "open", "target": "Acme Demo"}, {"op": "open", "target": "Teams"},
                 {"op": "click", "target": "New team"}, {"op": "fill", "target": "Team name", "value": "mobile-team"},
                 {"op": "click", "target": "Create team"}, {"op": "expect_visible", "target": "mobile-team"}]
        self.assertEqual(proposal_problems({"title": target["title"], "confidence": 0.9, "signed_in": True,
                                            "steps": steps}, target, fixtures), [])
        # Typed and expected with nothing submitted in between: the field echo, not an outcome.
        steps = steps[:4] + [steps[5]]
        problems = proposal_problems({"title": target["title"], "confidence": 0.9, "signed_in": True,
                                      "steps": steps}, target, fixtures)
        self.assertTrue(any("clicked" in p for p in problems), problems)


class AppendDedupeTests(unittest.TestCase):
    def test_identical_model_tests_are_appended_once_per_leaf(self):
        from scenario_review import append_tests
        body = "async ({ page }) => {\n  await h.openHome(page);\n  await h.expectTextsVisible(page, ['East']);\n});"
        a = "test('REQ-1-3-1 -a [model]', " + body
        b = "test('REQ-1-3-1 -b [model]', " + body
        c = "test('REQ-1-3-1 -c [model]', async ({ page }) => {\n  await h.openHome(page);\n});"
        source = append_tests("", [a, b], "REQ-1-3-1")
        self.assertEqual(source.count("\ntest("), 1)
        source = append_tests(source, [b, c], "REQ-1-3-1")
        self.assertEqual(source.count("\ntest("), 2)
        self.assertIn("-c [model]", source)


class CellSeedTests(unittest.TestCase):
    def _target(self):
        node = leaf("REQ-3-1-1", [("REQ-3-1-1 -the requested workflow", [
            ("GIVEN", "The evaluation seed contains the seeded workbook `Q3 Sales`, rows `Item/Qty` and `Pen/4`."),
            ("WHEN", "The user opens the workbook and the requested workflow."),
            ("THEN", "The application exposes the observable result for \"the requested workflow\"."),
        ])], description='A button "Undo" reverts the last edit.')
        fixtures = suite_fixtures([node])
        return review_targets([node], fixtures)[0], fixtures

    def test_seed_rows_in_cell_ops_use_their_first_cell_and_empty_cells_are_assertable(self):
        from scenario_review import proposal_problems
        target, fixtures = self._target()
        proposal = {"title": target["title"], "confidence": 0.9, "steps": [
            {"op": "open", "target": "Q3 Sales"},
            {"op": "cell_type", "target": "D1", "value": "Item/Qty"},
            {"op": "press", "key": "Enter"},
            {"op": "expect_cell", "target": "D1", "value": "Item/Qty"},
            {"op": "click", "target": "Undo"},
            {"op": "expect_cell", "target": "D1", "value": ""}]}
        self.assertEqual(proposal_problems(proposal, target, fixtures), [])
        source = validate_proposal(proposal, target, fixtures)
        self.assertIn("h.typeInCell(page, 'D1', 'Item');", source)
        self.assertIn("h.expectCell(page, 'D1', 'Item');", source)
        self.assertIn("h.expectCell(page, 'D1', '');", source)

    def test_undo_does_not_license_absence_of_a_seeded_value(self):
        from scenario_review import proposal_problems
        target, fixtures = self._target()
        proposal = {"title": target["title"], "confidence": 0.9, "steps": [
            {"op": "open", "target": "Q3 Sales"},
            {"op": "cell_type", "target": "D1", "value": "Pen"},
            {"op": "press", "key": "Enter"},
            {"op": "click", "target": "Undo"},
            {"op": "expect_absent", "target": "Pen"}]}
        problems = proposal_problems(proposal, target, fixtures)
        self.assertTrue(any("seeded value" in p for p in problems), problems)

    def test_typing_a_seeded_value_and_expecting_it_visible_is_not_evidence(self):
        from scenario_review import proposal_problems
        target, fixtures = self._target()
        steps = [{"op": "open", "target": "Q3 Sales"},
                 {"op": "cell_type", "target": "D1", "value": "Item"}, {"op": "press", "key": "Enter"},
                 {"op": "expect_visible", "target": "Item"}]
        problems = proposal_problems({"title": target["title"], "confidence": 0.9, "steps": steps}, target, fixtures)
        self.assertTrue(any("clicked" in p for p in problems), problems)
        steps[3] = {"op": "expect_cell", "target": "D1", "value": "Item"}
        self.assertEqual(proposal_problems({"title": target["title"], "confidence": 0.9, "steps": steps},
                                           target, fixtures), [])


class SuiteControlTests(unittest.TestCase):
    def _targets(self):
        issues = leaf("REQ-5-1-1", [("REQ-5-1-1: List Issues - Scenario 1", [
            ("GIVEN", "Seed values: account `alice-dev`, email `alice.dev@example.test`, password `Valid-password-123!`, "
                      "repository `acme-docs`, member `bob-reviewer`."),
            ("WHEN", "The user opens the “Issues” tab."), ("THEN", "The list shows “Open” issues.")])],
            description='The repository page has tabs "Code", "Issues" and "Pull requests"; a button "Remove <username>" removes a member.')
        comment = leaf("REQ-5-2-3", [("REQ-5-2-3: Comment on an Issue - Scenario 1", [
            ("GIVEN", "Seed values: account `alice-dev`, email `alice.dev@example.test`, password `Valid-password-123!`, "
                      "repository `acme-docs`, member `bob-reviewer`, issue `Improve search`."),
            ("WHEN", "The user opens the issue and fills “Comment”, then clicks “Add comment”."),
            ("THEN", "The comment appears with “bob-reviewer” removed via the member action.")])])
        fixtures = suite_fixtures([issues, comment])
        targets = review_targets([issues, comment], fixtures, shared='The header offers a link "Your organizations".')
        return {t["node_id"]: t for t in targets}, fixtures

    def test_controls_named_elsewhere_are_navigable_but_not_evidence(self):
        from scenario_review import proposal_problems
        targets, fixtures = self._targets()
        target = targets["REQ-5-2-3"]
        steps = [{"op": "open", "target": "Your organizations"}, {"op": "open", "target": "acme-docs"},
                 {"op": "open", "target": "Issues"}, {"op": "open", "target": "Improve search"},
                 {"op": "fill", "target": "Comment", "value": "$TEXT"}, {"op": "click", "target": "Add comment"},
                 {"op": "click", "target": "Remove bob-reviewer"}, {"op": "expect_visible", "target": "$TEXT"}]
        self.assertEqual(proposal_problems({"title": target["title"], "confidence": 0.9, "signed_in": True,
                                            "steps": steps}, target, fixtures), [])
        steps[-1] = {"op": "expect_visible", "target": "Pull requests"}
        problems = proposal_problems({"title": target["title"], "confidence": 0.9, "signed_in": True,
                                      "steps": steps}, target, fixtures)
        self.assertTrue(any("Pull requests" in p for p in problems), problems)
        self.assertIn("CONTROLS", build_prompt([target], fixtures))


class CellValueTests(unittest.TestCase):
    def _target(self):
        node = leaf("REQ-4-2-2", [("REQ-4-2-2 -the requested workflow Pivot1 the requested workflow Region", [
            ("GIVEN", "The evaluation seed contains the seeded workbook `Q3 Sales`, cell `A1=2`, rows `East/1200`."),
            ("WHEN", "The user opens the workbook and the requested workflow."),
            ("THEN", "The application exposes the observable result for \"the requested workflow\"."),
        ])])
        fixtures = suite_fixtures([node])
        return review_targets([node], fixtures)[0], fixtures

    def test_formulas_error_tokens_numbers_ranges_and_title_tokens(self):
        from scenario_review import proposal_problems
        target, fixtures = self._target()
        self.assertIn("Pivot1", target["allowed"])
        self.assertIn("Region", target["allowed"])
        steps = [{"op": "open", "target": "Q3 Sales"}, {"op": "cell_click", "target": "A1:B2"},
                 {"op": "cell_type", "target": "C1", "value": "=1/0"}, {"op": "press", "key": "Enter"},
                 {"op": "expect_cell", "target": "C1", "value": "#DIV/0!"},
                 {"op": "cell_type", "target": "D1", "value": 2000}, {"op": "press", "key": "Enter"},
                 {"op": "expect_cell", "target": "D1", "value": 2000}]
        self.assertEqual(proposal_problems({"title": target["title"], "confidence": 0.9, "steps": steps},
                                           target, fixtures), [])
        source = validate_proposal({"title": target["title"], "confidence": 0.9, "steps": steps}, target, fixtures)
        self.assertIn("h.clickCell(page, 'A1:B2');", source)
        self.assertIn("h.expectCell(page, 'C1', '#DIV/0!');", source)
        self.assertIn("h.expectCell(page, 'D1', '2000');", source)

    def test_blank_placeholder_expands_to_whitespace(self):
        target, fixtures = self._target()
        from scenario_review import expand_placeholder
        self.assertEqual(expand_placeholder("$BLANK", "x"), "   ")


class AppendTitleDedupeTests(unittest.TestCase):
    def test_a_repeated_title_is_not_appended(self):
        from scenario_review import append_tests
        a = "test('REQ-1 -x [model]', async ({ page }) => {\n  await h.openHome(page);\n});"
        b = "test('REQ-1 -x [model]', async ({ page }) => {\n  await h.openHome(page);\n  await h.expectTextsVisible(page, ['A']);\n});"
        source = append_tests("", [a], "REQ-1")
        self.assertEqual(append_tests(source, [b], "REQ-1").count("\ntest("), 1)


class NonGridTaskTests(unittest.TestCase):
    def _target(self):
        node = leaf("REQ-5-1-1", [("REQ-5-1-1: List Issues - Scenario 2", [
            ("GIVEN", "Seed values: account `alice-dev`, email `alice.dev@example.test`, password `Valid-password-123!`, "
                      "repository `acme-docs`, issue `Improve onboarding`, file `src/search.ts`."),
            ("WHEN", "The user narrows the issue list to closed issues."),
            ("THEN", "The list shows “Legacy welcome text” and the file “src/search.ts”.")])],
            description='The issues page has tabs "Open" and "Closed" and a tab "Issues".')
        fixtures = suite_fixtures([node])
        return review_targets([node], fixtures)[0], fixtures

    def test_filters_hide_seeded_values_and_paths_are_not_split(self):
        from scenario_review import proposal_problems
        target, fixtures = self._target()
        steps = [{"op": "open", "target": "acme-docs"}, {"op": "open", "target": "Issues"},
                 {"op": "click", "target": "Closed"}, {"op": "expect_visible", "target": "Legacy welcome text"},
                 {"op": "expect_absent", "target": "Improve onboarding"},
                 {"op": "expect_visible", "target": "src/search.ts"}]
        self.assertEqual(proposal_problems({"title": target["title"], "confidence": 0.9, "steps": steps},
                                           target, fixtures), [])
        source = validate_proposal({"title": target["title"], "confidence": 0.9, "steps": steps}, target, fixtures)
        self.assertIn("h.expectTextsVisible(page, ['src/search.ts']);", source)

    def test_cell_ops_are_rejected_without_a_grid(self):
        from scenario_review import proposal_problems
        target, fixtures = self._target()
        self.assertFalse(target["has_grid"])
        steps = [{"op": "open", "target": "Issues"}, {"op": "expect_cell", "target": "A1", "value": "Legacy welcome text"}]
        problems = proposal_problems({"title": target["title"], "confidence": 0.9, "steps": steps}, target, fixtures)
        self.assertTrue(any("spreadsheet grid" in p for p in problems), problems)
