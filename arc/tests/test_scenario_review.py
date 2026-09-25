import json
import re
import unittest

from scenario_review import (allowed_literals, ancestor_context, build_prompt, compile_reply, parse_reply,
                             review_targets, validate_proposal)
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
    def test_should_target_only_scenarios_without_a_mechanical_script(self):
        targets = review_targets([MERGE], suite_fixtures([MERGE]))
        self.assertEqual([t["title"] for t in targets], ["REQ-6-5: Scenario 1"])
        self.assertEqual(targets[0]["node_id"], "REQ-6-5")
        self.assertIn("Merge pull request", targets[0]["allowed"])
        self.assertIn("acme-docs", targets[0]["allowed"])

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
        self.assertIn("no clipboard setup", prompt)
        self.assertIn("not a reason to skip", prompt)


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
