import json
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
